from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .graph import WorkflowGraph
from .layout import (
    ADAPTED_PROMPT_PACKAGE,
    ASSET_REGISTRY,
    CANONICAL_PROMPT_PACKAGE,
    FINAL_DELIVERY_INDEX,
    MEDIA_EXECUTION_INDEX,
    P07,
    P08,
    P09,
    P10,
    P11,
    P12,
    P13,
    PHASES,
    SCENE_SPACE_PLAN,
    SHOT_PLAN,
    SHOT_TIMELINE_INDEX,
    SOURCE_REGISTRY,
)
from .schema import SchemaValidationError, load_schema, validate, validate_artifact
from .storage import ProjectStore
from .utils import canonical_json, read_json, sha256_bytes, sha256_file


VALID_STAGE_STATES = {
    "pending",
    "running",
    "awaiting_choice",
    "blocked",
    "complete",
    "failed",
    "invalidated",
}


def _issue(code: str, message: str, path: str | None = None) -> dict[str, str]:
    value = {"code": code, "message": message}
    if path:
        value["path"] = path
    return value


def _view_name(value: object) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "-", str(value)).strip("-.") or "item"


def _check_derived_view(
    store: ProjectStore,
    source: str,
    view: str,
    errors: list[dict[str, str]],
) -> None:
    if not store.exists(view):
        errors.append(_issue("missing-derived-view", "Required standalone derived file is missing", view))
        return
    header = store.path(view).read_text(encoding="utf-8", errors="replace")[:2000]
    source_hash = sha256_file(store.path(source))
    if source not in header or source_hash not in header:
        errors.append(_issue("stale-derived-view", "Derived file does not cite the current source and hash", view))


def _timing_start(
    event: dict[str, Any],
    duration: float,
    label: str,
    path: str,
    errors: list[dict[str, str]],
) -> float:
    if event.get("time_mode") == "full_shot" or event.get('full_shot') is True:
        if any(key in event for key in ("time_s", "start_s", "end_s")):
            errors.append(_issue("full-shot-time", f"{label} duplicates timecodes for full_shot", path))
        return 0.0
    try:
        if "time_s" in event:
            time_s = float(event["time_s"])
            if not 0 <= time_s <= duration:
                raise ValueError
            return time_s
        start_s = float(event["start_s"])
        end_s = float(event["end_s"])
        if not 0 <= start_s <= end_s <= duration:
            raise ValueError
        return start_s
    except (KeyError, TypeError, ValueError):
        errors.append(_issue("timeline-time", f"{label} has an invalid or missing time range", path))
        return -1.0


def _validate_timeline_semantics(
    shot: dict[str, Any],
    path: str,
    scenes: dict[str, dict[str, Any]],
    asset_ids: set[str],
    source_ids: set[str],
    errors: list[dict[str, str]],
) -> None:
    from .timing import validate_timing
    try:
        validate_timing(shot)
    except (ValueError, KeyError, ZeroDivisionError) as error:
        errors.append(_issue('frame-timing', str(error), path))
    duration = float(shot.get("duration_s", 0) or 0)
    if not 1 <= duration <= 12:
        errors.append(_issue("shot-duration", "ShotTimelineSpec duration must be 1-12 seconds", path))
    scene_id = str(shot.get("scene_id", ""))
    scene = scenes.get(scene_id)
    if scene is None:
        errors.append(_issue("scene-reference", f"Unknown scene_id {scene_id!r}", path))
        placed_characters: set[str] = set()
    else:
        placed_characters = {
            str(item.get("character_id"))
            for item in scene.get("character_placements", [])
            if item.get("character_id")
        }
    unknown_assets = sorted(set(map(str, shot.get("required_asset_ids", []))) - asset_ids)
    if unknown_assets:
        errors.append(_issue("asset-reference", f"Unknown required assets: {unknown_assets}", path))
    selected = list(map(str, shot.get("selected_reference_ids", [])))
    if len(selected) > 5:
        errors.append(_issue("reference-slots", "At most five upload references are allowed", path))
    unknown_selected = sorted(set(selected) - asset_ids - source_ids)
    if unknown_selected:
        errors.append(_issue("selected-reference", f"Unknown selected references: {unknown_selected}", path))

    character_ids: set[str] = set()
    for track in shot.get("character_tracks", []):
        character_id = str(track.get("character_id", ""))
        if not character_id or character_id in character_ids:
            errors.append(_issue("character-track", "Character track IDs must be unique and non-empty", path))
        character_ids.add(character_id)
        if character_id not in placed_characters:
            errors.append(_issue("character-placement", f"{character_id} is absent from SceneSpace", path))
        visible = track.get("visible_interval", {})
        try:
            visible_start = float(visible["start_s"])
            visible_end = float(visible["end_s"])
            if not 0 <= visible_start <= visible_end <= duration:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            errors.append(_issue("visible-interval", f"{character_id} has an invalid visible interval", path))
            visible_start, visible_end = 0.0, duration
        trajectory = track.get("trajectory", [])
        try:
            times = [float(item["time_s"]) for item in trajectory]
        except (KeyError, TypeError, ValueError):
            times = []
        if not times or times != sorted(set(times)) or any(item < 0 or item > duration for item in times):
            errors.append(_issue("trajectory-time", f"{character_id} trajectory keyframes are invalid", path))
        for field in ("action_events", "emotion_events"):
            starts = [
                _timing_start(event, duration, f"{character_id}.{field}", path, errors)
                for event in track.get(field, [])
            ]
            if starts != sorted(starts):
                errors.append(_issue("track-order", f"{character_id}.{field} is not time-ordered", path))
    for field in ("camera_track", "audio_track", "director_track", "spatial_track", "scene_fixed_track"):
        starts = [
            _timing_start(event, duration, field, path, errors)
            for event in shot.get(field, [])
        ]
        if starts != sorted(starts):
            errors.append(_issue("track-order", f"{field} is not time-ordered", path))


def validate_project(
    project_dir: Path | str,
    *,
    final: bool = False,
    verify_manifest: bool = True,
    check_archive: bool = True,
) -> dict[str, Any]:
    store = ProjectStore(project_dir)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    checked = 0
    if not store.exists("project.json"):
        return {
            "valid": False,
            "errors": [_issue("missing-project", "project.json is missing", "project.json")],
            "warnings": [],
            "checked_artifacts": 0,
        }
    project = store.read("project.json")
    project_id = str(project.get("project_id", ""))
    if project.get("schema_version") != "3.0":
        return {
            "valid": False,
            "errors": [_issue("migration-required", "The project must be explicitly migrated before v3 validation", "project.json")],
            "warnings": [],
            "checked_artifacts": 0,
        }

    graph = WorkflowGraph()
    expected_phase_folders = {str(item["folder"]) for item in PHASES}
    for folder in expected_phase_folders:
        if not store.path(folder).is_dir():
            errors.append(_issue("missing-phase-folder", "Canonical phase folder is missing", folder))
    if not store.exists("phase-index.json"):
        errors.append(_issue("missing-phase-index", "phase-index.json is missing", "phase-index.json"))

    for path in sorted(store.root.rglob("*.json")):
        relative = path.relative_to(store.root)
        if relative.parts and relative.parts[0] == ".history":
            continue
        try:
            payload = read_json(path)
        except (ValueError, json.JSONDecodeError) as error:
            errors.append(_issue("invalid-json", str(error), relative.as_posix()))
            continue
        try:
            if "artifact_type" in payload:
                validate_artifact(payload)
                checked += 1
            elif relative.parts[:2] == ("runtime", "results"):
                validate(payload, load_schema("agent-result.schema.json"))
        except SchemaValidationError as error:
            errors.extend(_issue("schema", item.render(), relative.as_posix()) for item in error.issues)
        if "project_id" in payload and payload["project_id"] != project_id:
            errors.append(_issue("project-id", "Artifact belongs to a different project", relative.as_posix()))
        if "artifact_type" not in payload:
            continue
        markdown = path.with_suffix(".md")
        if not markdown.exists():
            errors.append(_issue("missing-markdown", "Derived Markdown view is missing", relative.as_posix()))
        else:
            header = markdown.read_text(encoding="utf-8", errors="replace")[:1500]
            if sha256_file(path) not in header or relative.as_posix() not in header:
                errors.append(_issue("stale-markdown", "Markdown does not cite current JSON path and SHA-256", markdown.relative_to(store.root).as_posix()))

    state = store.read("state.json") if store.exists("state.json") else {}
    for stage_id, status in state.get("stage_status", {}).items():
        if stage_id not in {stage.id for stage in graph.stages}:
            errors.append(_issue("unknown-stage", f"Unknown stage {stage_id}", "state.json"))
        if status not in VALID_STAGE_STATES:
            errors.append(_issue("stage-status", f"Invalid stage status {status!r}", stage_id))
    for gate, field in (
        ("asset_quality_gate", "asset_review_decision"),
        ("spatial_lock_gate", "spatial_review_decision"),
        ("storyboard_quality_gate", "storyboard_review_decision"),
    ):
        if state.get("stage_status", {}).get(gate) == "complete":
            if state.get("decisions", {}).get(field) != "approve":
                errors.append(_issue("mandatory-review", f"{gate} lacks an explicit approval", "state.json"))
            approval_path = state.get("decision_approvals", {}).get(field)
            if not approval_path or not store.exists(str(approval_path)):
                errors.append(_issue("approval-record", f"{field} approval record is missing", "state.json"))
            elif store.read(str(approval_path)).get("valid") is False:
                errors.append(_issue("stale-approval", f"{field} points to an invalidated approval", str(approval_path)))
            else:
                from .references import current_approval
                try:
                    current_approval(store, approval_path)
                except ValueError as error:
                    errors.append(_issue('stale-approval-inputs', str(error), str(approval_path)))

    scenes: dict[str, dict[str, Any]] = {}
    if store.exists(SCENE_SPACE_PLAN):
        scenes = {str(item.get("scene_id")): item for item in store.read(SCENE_SPACE_PLAN).get("scenes", [])}
    asset_ids: set[str] = set()
    if store.exists(ASSET_REGISTRY):
        asset_ids = {str(item.get("asset_id")) for item in store.read(ASSET_REGISTRY).get("assets", [])}
        for item in store.read(ASSET_REGISTRY).get("assets", []):
            _check_derived_view(store, ASSET_REGISTRY, f"{P07}/assets/prompts/{_view_name(item.get('asset_id'))}.txt", errors)
            if item.get("execution_status") == "generated_verified":
                media_path = item.get("media_path")
                if not media_path or not store.exists(str(media_path)) or not item.get("sha256"):
                    errors.append(_issue("asset-media-claim", "Generated verified asset lacks file evidence", ASSET_REGISTRY))
    source_ids = {
        str(item.get("source_id"))
        for item in store.read(SOURCE_REGISTRY).get("sources", [])
    } if store.exists(SOURCE_REGISTRY) else set()

    shots: list[dict[str, Any]] = []
    shot_paths = sorted(store.path(f"{P09}/shots").glob("*.json")) if store.path(f"{P09}/shots").exists() else []
    for path in shot_paths:
        shot = read_json(path)
        shots.append(shot)
        _validate_timeline_semantics(shot, path.relative_to(store.root).as_posix(), scenes, asset_ids, source_ids, errors)
    shots.sort(key=lambda item: int(item.get("index", 0)))
    shot_ids = [str(item.get("shot_id")) for item in shots]
    if len(shot_ids) != len(set(shot_ids)):
        errors.append(_issue("duplicate-shot-id", "ShotTimelineSpec IDs must be unique", SHOT_TIMELINE_INDEX))
    for previous, current in zip(shots, shots[1:]):
        if previous.get("scene_id") != current.get("scene_id"):
            continue
        if current.get("continuity", {}).get("transition_from_previous"):
            continue
        if canonical_json(previous.get("continuity", {}).get("end_state")) != canonical_json(current.get("continuity", {}).get("start_state")):
            errors.append(_issue("continuity-handoff", f"State mismatch from {previous.get('shot_id')} to {current.get('shot_id')}", SHOT_TIMELINE_INDEX))
    if store.exists(SHOT_TIMELINE_INDEX):
        index = store.read(SHOT_TIMELINE_INDEX)
        indexed = [str(item.get("shot_id")) for item in sorted(index.get("shots", []), key=lambda item: item.get("index", 0))]
        if indexed != shot_ids:
            errors.append(_issue("shot-index", "Timeline index and committed files do not match", SHOT_TIMELINE_INDEX))

    if store.exists(SHOT_PLAN):
        plan = store.read(SHOT_PLAN)
        planned_by_id = {str(item.get("shot_id")): item for item in plan.get("shots", [])}
        for segment in plan.get("generation_segments", []):
            ids = list(map(str, segment.get("shot_ids", [])))
            target = float(segment.get("target_duration_s", 0) or 0)
            actual = sum(float(planned_by_id[item]["duration_s"]) for item in ids if item in planned_by_id)
            if not ids or abs(actual - target) > 0.01:
                errors.append(_issue("generation-segment", f"Segment {segment.get('segment_id')} has invalid shot coverage", SHOT_PLAN))
            if target > 12 and len(ids) < 2:
                errors.append(_issue("segment-split", "Segments longer than 12 seconds require multiple shots", SHOT_PLAN))

    storyboard_package_path = f"{P09}/storyboard-package.json"
    if store.exists(storyboard_package_path):
        package = store.read(storyboard_package_path)
        package_ids = [str(item.get("shot_id")) for item in package.get("shots", [])]
        if shot_ids and package_ids != shot_ids:
            errors.append(_issue("storyboard-coverage", "Storyboard package does not cover every timeline", storyboard_package_path))
        for item in package.get("shots", []):
            moments = item.get("key_moments", [])
            if not 1 <= len(moments) <= 3:
                errors.append(_issue("key-moments", "Each shot requires 1-3 key moments", storyboard_package_path))
            timeline = next((shot for shot in shots if shot.get("shot_id") == item.get("shot_id")), None)
            if timeline and any(not 0 <= float(moment.get("time_s", -1)) <= float(timeline["duration_s"]) for moment in moments):
                errors.append(_issue("key-moment-time", "A key moment falls outside its shot", storyboard_package_path))
            preview = item.get("previsualization")
            if preview:
                preview_path = str(preview.get("path"))
                try:
                    ET.parse(store.path(preview_path))
                except (ET.ParseError, OSError):
                    errors.append(_issue("previsualization-svg", "Structured previsualization SVG is invalid", preview_path))
                if preview.get("verified_3d"):
                    errors.append(_issue("previsualization-boundary", "Structured SVG must not claim verified 3D", preview_path))
    for svg in store.path(f"{P08}/previews").glob("*.svg") if store.path(f"{P08}/previews").exists() else []:
        try:
            ET.parse(svg)
        except (ET.ParseError, OSError):
            errors.append(_issue("spatial-svg", "Spatial preview SVG is invalid", svg.relative_to(store.root).as_posix()))

    reference_index = f"{P09}/reference-image-index.json"
    if store.exists(reference_index):
        references = store.read(reference_index)
        by_shot: dict[str, int] = {}
        for item in references.get("references", []):
            by_shot[str(item.get("shot_id"))] = by_shot.get(str(item.get("shot_id")), 0) + 1
            _check_derived_view(store, reference_index, f"{P09}/reference-prompts/{_view_name(item.get('reference_id'))}.txt", errors)
            if item.get("execution_status") == "generated_verified":
                media_path = item.get("path")
                if not media_path or not store.exists(str(media_path)) or not item.get("sha256"):
                    errors.append(_issue("storyboard-media-claim", "Generated storyboard image lacks file evidence", reference_index))
        if references.get("status") != "not_selected" and any(not 1 <= by_shot.get(shot_id, 0) <= 3 for shot_id in shot_ids):
            errors.append(_issue("reference-count", "Selected reference-image view requires 1-3 entries per shot", reference_index))

    if store.exists(CANONICAL_PROMPT_PACKAGE):
        canonical = store.read(CANONICAL_PROMPT_PACKAGE)
        if set(map(str, canonical.get("shot_ids", []))) != set(shot_ids):
            errors.append(_issue("prompt-coverage", "Canonical prompts do not cover all shots", CANONICAL_PROMPT_PACKAGE))
        source_hashes: dict[str, str] = {}
        for item in canonical.get("prompts", []):
            shot_id = str(item.get("shot_id"))
            record_hash = sha256_bytes(canonical_json(item.get("canonical_record", {})).encode("utf-8"))
            if record_hash != item.get("canonical_fact_hash"):
                errors.append(_issue("canonical-fact-hash", f"Canonical fact hash is stale for {shot_id}", CANONICAL_PROMPT_PACKAGE))
            for source in item.get("source_trace", []):
                path = str(source.get("path", ""))
                if not store.exists(path) or sha256_file(store.path(path)) != source.get("sha256"):
                    errors.append(_issue("prompt-source-trace", f"Stale or missing source trace for {shot_id}", path))
            try:
                from .references import prompt_controls
                controls, coverage = prompt_controls(store, store.read(item['timeline_path']))
                if item.get('execution_controls') != controls or item.get('field_coverage') != coverage:
                    errors.append(_issue('prompt-field-coverage', 'Executable controls omit or change source facts', CANONICAL_PROMPT_PACKAGE))
            except (ValueError, KeyError, FileNotFoundError) as error:
                errors.append(_issue('prompt-field-coverage', str(error), CANONICAL_PROMPT_PACKAGE))
            source_hashes[shot_id] = str(item.get("canonical_fact_hash"))
            _check_derived_view(store, CANONICAL_PROMPT_PACKAGE, f"{P10}/shots/{_view_name(shot_id)}.txt", errors)
        if store.exists(ADAPTED_PROMPT_PACKAGE):
            adapted = store.read(ADAPTED_PROMPT_PACKAGE)
            by_id = {p['shot_id']: p for p in canonical['prompts']}
            for item in adapted.get("prompts", []):
                shot_id = str(item.get("shot_id"))
                if item.get("canonical_fact_hash") != source_hashes.get(shot_id):
                    errors.append(_issue("adapter-fact-drift", f"Adapter changed facts for {shot_id}", ADAPTED_PROMPT_PACKAGE))
                original = by_id.get(shot_id, {})
                mapping = [{'slot': b['slot'], 'path': b['path'], 'sha256': b['sha256'], 'role': b['role']}
                           for b in original.get('reference_bindings', [])]
                if (any(item.get(key) != original.get(key) for key in ('reference_bindings', 'execution_controls', 'field_coverage'))
                        or item.get('request_mapping') != mapping):
                    errors.append(_issue('adapter-control-drift', 'Offline request mapping loses controls or required image bindings', ADAPTED_PROMPT_PACKAGE))
                _check_derived_view(store, ADAPTED_PROMPT_PACKAGE, f"{P11}/adapted/{_view_name(shot_id)}.txt", errors)

    if store.exists(f"{P12}/edit-plan.json"):
        try:
            from .editing import validate_edit_plan
            validate_edit_plan(store.read(f'{P12}/edit-plan.json'), shot_ids=set(shot_ids),
                               subtitle_language=state.get('decisions', {}).get('subtitle_language'))
        except (KeyError, ValueError) as error:
            errors.append(_issue('edit-plan-contract', str(error), f'{P12}/edit-plan.json'))
        _check_derived_view(store, f"{P12}/edit-plan.json", f"{P12}/derived/voice-script.txt", errors)
    if store.exists(MEDIA_EXECUTION_INDEX):
        execution = store.read(MEDIA_EXECUTION_INDEX)
        for output in execution.get("outputs", []):
            output_path = str(output.get("path", ""))
            if not output_path or not store.exists(output_path):
                errors.append(_issue("missing-media", "Registered media file is missing", output_path))
            if output.get("verified") and not output.get("sha256"):
                errors.append(_issue("media-claim", "Verified media requires a file hash", output_path))
        if project.get("external_generation_blocked") and execution.get("outputs"):
            errors.append(_issue("rights-boundary", "Media exists despite the rights boundary", MEDIA_EXECUTION_INDEX))
    else:
        warnings.append(_issue("media-not-run", "No media execution record exists"))

    if store.exists(FINAL_DELIVERY_INDEX):
        delivery = store.read(FINAL_DELIVERY_INDEX)
        if state.get('stage_status', {}).get('export') == 'complete':
            for item in delivery.get('artifacts', []):
                relative = item['path']
                if not store.exists(relative) or sha256_file(store.path(relative)) != item['sha256']:
                    errors.append(_issue('delivery-index-hash', 'Delivery index references stale bytes', relative))
        if delivery.get("status") == "media_verified":
            render = store.read(f"{P12}/render-package.json") if store.exists(f"{P12}/render-package.json") else {}
            final_video = render.get("final_video") or {}
            if not final_video.get("verified") or not final_video.get("path") or not store.exists(str(final_video.get("path", ""))):
                errors.append(_issue("media-status", "media_verified requires a verified final file", FINAL_DELIVERY_INDEX))

    if verify_manifest and store.exists("manifest.json"):
        for entry in store.read("manifest.json").get("files", []):
            relative = str(entry.get("path", ""))
            if relative.startswith(("runtime/", ".history/")):
                errors.append(_issue("manifest-scope", "Runtime/history evidence must not be in the formal manifest", relative))
                continue
            candidate = store.path(relative)
            if not candidate.exists():
                errors.append(_issue("manifest-missing", "Manifest file is missing", relative))
            elif sha256_file(candidate) != entry.get("sha256"):
                errors.append(_issue("manifest-hash", "Manifest hash does not match", relative))

    legacy_roots = [name for name in ("sources", "intake", "story", "planning", "storyboard", "design", "assets", "prompts", "media", "edit", "delivery", "publish", "decisions") if store.path(name).exists()]
    if legacy_roots:
        errors.append(_issue("legacy-active-roots", f"Legacy business roots remain active: {legacy_roots}"))

    if final:
        if state.get("status") != "complete":
            errors.append(_issue("not-complete", "Workflow has not reached complete state", "state.json"))
        for source, view in (
            (f"{P13}/cover-package.json", f"{P13}/publish/cover-prompt.txt"),
            (f"{P13}/publication-copy.json", f"{P13}/publish/copy.txt"),
            (f"{P13}/publication-checklist.json", f"{P13}/publish/checklist.txt"),
        ):
            if not store.exists(source):
                errors.append(_issue("missing-publish-artifact", "Publication handoff artifact is missing", source))
            else:
                _check_derived_view(store, source, view, errors)
        if not store.exists(FINAL_DELIVERY_INDEX):
            errors.append(_issue("missing-delivery", "Final delivery index is missing", FINAL_DELIVERY_INDEX))
        else:
            archive = store.read(FINAL_DELIVERY_INDEX).get("archive")
            if check_archive and (not archive or not store.exists(str(archive))):
                errors.append(_issue("missing-archive", "Deterministic delivery archive is missing", str(archive)))
            elif check_archive and not store.path(str(archive) + ".sha256").exists():
                errors.append(_issue("missing-archive-hash", "Delivery archive hash sidecar is missing", str(archive)))

    if state.get('decisions', {}).get('delivery_target') == 'dual-reference-previs' and (
        final or state.get('stage_status', {}).get('canonical_prompt_compile') == 'complete'
    ):
        try:
            from .references import dual_bindings, prompt_controls
            package = store.read(CANONICAL_PROMPT_PACKAGE)
            for prompt in package['prompts']:
                shot = store.read(prompt['timeline_path'])
                expected = dual_bindings(store, shot, state)
                controls, coverage = prompt_controls(store, shot)
                if prompt.get('reference_bindings') != expected:
                    raise ValueError('Dual reference attachment mapping differs from approved images')
                if prompt.get('execution_controls') != controls or prompt.get('field_coverage') != coverage:
                    raise ValueError('Prompt execution controls lose required timeline facts')
            if package.get('dual_reference_status') != 'ready':
                raise ValueError('Declared dual-reference delivery is not ready')
            storyboards = store.read(f'{P09}/storyboard-package.json')
            for item in storyboards['shots']:
                shot = store.read(item['timeline_path'])
                scene = next(s for s in store.read(SCENE_SPACE_PLAN)['scenes'] if s['scene_id'] == shot['scene_id'])
                expected_hash = sha256_bytes(canonical_json({'scene': scene, 'shot': shot}).encode())
                for key in ('blender_stills', 'blender_motion'):
                    receipt = item.get(key, {})
                    if not receipt.get('execution_verified') or receipt.get('canonical_source_hash') != expected_hash:
                        raise ValueError('Missing or stale actual Blender execution evidence')
                    if not receipt.get('files') or any(not store.exists(f['path']) or sha256_file(store.path(f['path'])) != f['sha256'] for f in receipt['files']):
                        raise ValueError('Blender evidence files are missing or changed')
            if final:
                from .pipeline import inspect_video
                render = store.read(f'{P12}/render-package.json').get('final_video') or {}
                if (not render.get('edit_plan_executed') or not render.get('path')
                        or not store.exists(render['path']) or sha256_file(store.path(render['path'])) != render.get('sha256')
                        or not inspect_video(store.path(render['path']), require_audio=True)['verified']):
                    raise ValueError('Dual-reference/previs delivery lacks an executed and validated local edit')
        except (KeyError, ValueError, FileNotFoundError) as error:
            errors.append(_issue('dual-reference-gate', str(error), CANONICAL_PROMPT_PACKAGE))

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "checked_artifacts": checked,
    }
