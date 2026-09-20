from __future__ import annotations

from typing import Any

from ai_comic_drama_workflow.kernel import WorkflowKernel
from ai_comic_drama_workflow.layout import GENERATION_SEGMENTS, SHOT_PLAN, SHOT_TIMELINE_INDEX
from ai_comic_drama_workflow.utils import stable_id


DEFAULT_CHOICES: dict[str, Any] = {
    "delivery_target": "prompt-draft",
    "image_job_budget": 3,
    "work_depth": "standard",
    "adaptation_policy": "limited-expansion",
    "rights_status": "owned-or-authorized",
    "conflict_policy": "approved-downstream-priority",
    "core_conflict_resolution": "manual-resolution-attached",
    "likeness_authorization": "authorized",
    "segment_duration_s": 20,
    "chapter_batch_size": 3,
    "visual_style": "premium-2d-anime",
    "aspect_ratio": "9:16",
    "asset_image_strategy": "prompt-only",
    "asset_image_fallback": "prompt-only",
    "visual_external_action": "prompt-only",
    "asset_review_decision": "approve",
    "spatial_representation": "2.5d-structured-previsualization",
    "spatial_review_decision": "approve",
    "storyboard_depth": "full-dimensional",
    "storyboard_views": [
        "action-breakdown",
        "director-track",
        "scene-overview",
        "structured-whitebox",
        "reference-images",
    ],
    "storyboard_image_fallback": "prompt-only",
    "storyboard_review_decision": "approve",
    "target_platform": "platform-neutral",
    "media_execution_mode": "prompt-only",
    "video_external_action": "prompt-only",
    "external_media_action": "prompt-only",
    "voice_strategy": "voice-script-only",
    "subtitle_language": "zh-CN",
    "audio_external_action": "script-only",
}


def _asset_plan() -> dict[str, Any]:
    return {
        "assets": [
            {
                "asset_id": "ASSET-STYLE-001",
                "asset_type": "style-reference",
                "description": "Approved global style sheet",
                "reference_ids": [],
                "continuity_constraints": ["stable line and color language"],
                "forbidden_inheritance": ["temporary weather"],
            },
            {
                "asset_id": "ASSET-CHAR-001",
                "entity_ids": ["CHAR-001"],
                "asset_type": "character-reference",
                "description": "Lin identity sheet",
                "reference_ids": [],
                "continuity_constraints": ["short black hair", "blue coat"],
                "forbidden_inheritance": ["temporary surprise"],
            },
            {
                "asset_id": "ASSET-CHAR-002",
                "entity_ids": ["CHAR-002"],
                "asset_type": "character-reference",
                "description": "Messenger identity sheet",
                "reference_ids": [],
                "continuity_constraints": ["silver rain cape"],
                "forbidden_inheritance": ["temporary pose"],
            },
            {
                "asset_id": "ASSET-SCENE-001",
                "asset_type": "scene-reference",
                "description": "Rainy street scene sheet",
                "reference_ids": [],
                "continuity_constraints": ["street lamp at north-east"],
                "forbidden_inheritance": ["characters"],
            },
            {
                "asset_id": "ASSET-PROP-001",
                "asset_type": "prop-reference",
                "description": "Future letter prop sheet",
                "reference_ids": [],
                "continuity_constraints": ["red wax seal"],
                "forbidden_inheritance": ["hand ownership"],
            },
        ]
    }


def _scene_space(kernel: WorkflowKernel) -> dict[str, Any]:
    segments = kernel.store.read(GENERATION_SEGMENTS).get("segments", [])
    return {
        "representation": kernel.state["decisions"]["spatial_representation"],
        "scenes": [
            {
                "scene_id": "SCENE-001",
                "coordinate_system": {
                    "origin": "south-west ground corner",
                    "units": "normalized",
                    "axes": {"x": "east", "y": "north", "z": "up"},
                    "bounds": {"x": [0, 1], "y": [0, 1], "z": [0, 1]},
                    "world_bounds": {"x": [0, 10], "y": [0, 10], "z": [0, 3]},
                },
                "zones": [
                    {"zone_id": "ZONE-STREET", "position": {"x": 0.5, "y": 0.5, "z": 0}},
                ],
                "entrances": [{"entrance_id": "ENTRY-WEST", "position": {"x": 0, "y": 0.5, "z": 0}}],
                "fixed_elements": [
                    {"element_id": "LAMP-001", "position": {"x": 0.8, "y": 0.8, "z": 0}},
                ],
                "prop_placements": [
                    {"asset_id": "ASSET-PROP-001", "position": {"x": 0.35, "y": 0.45, "z": 0.5}},
                ],
                "factions": [
                    {"faction_id": "FACTION-LIN", "member_ids": ["CHAR-001"]},
                    {"faction_id": "FACTION-MESSENGER", "member_ids": ["CHAR-002"]},
                ],
                "character_placements": [
                    {
                        "character_id": "CHAR-001",
                        "position": {"x": 0.25, "y": 0.5, "z": 0},
                        "facing": "east",
                        "gaze": "CHAR-002",
                        "faction_id": "FACTION-LIN",
                    },
                    {
                        "character_id": "CHAR-002",
                        "position": {"x": 0.75, "y": 0.5, "z": 0},
                        "facing": "west",
                        "gaze": "CHAR-001",
                        "faction_id": "FACTION-MESSENGER",
                    },
                ],
                "movement_paths": [
                    {"path_id": "PATH-LIN", "character_id": "CHAR-001", "points": [{"x": 0.25, "y": 0.5, "z": 0}, {"x": 0.45, "y": 0.5, "z": 0}]},
                ],
                "interaction_distances": [
                    {"characters": ["CHAR-001", "CHAR-002"], "distance": 0.5, "meaning": "opposed"},
                ],
                "camera_axis": {"line": "CHAR-001 to CHAR-002", "allowed_side": "south"},
                "segment_states": [
                    {"segment_id": item["segment_id"], "start_state": {"beat": index - 1}, "end_state": {"beat": index}}
                    for index, item in enumerate(segments, start=1)
                ],
                "continuity_constraints": ["keep both characters on their established screen sides"],
            }
        ],
    }


def _timed_events(duration: float) -> list[dict[str, Any]]:
    phases = ["preparation", "start", "development", "key", "end", "recovery"]
    events = []
    for index, phase in enumerate(phases):
        start = round(duration * index / len(phases), 3)
        end = round(duration * (index + 1) / len(phases), 3)
        events.append(
            {
                "event_id": f"ACTION-{index + 1:02d}",
                "start_s": start,
                "end_s": end,
                "channel": "hands-and-body",
                "phase": phase,
                "description": f"letter handoff {phase}",
                "interaction_target": "CHAR-002",
                "prop_ids": ["ASSET-PROP-001"],
            }
        )
    return events


def _timeline_shot(item: dict[str, Any]) -> dict[str, Any]:
    duration = float(item["duration_s"])
    middle = round(duration / 2, 3)
    index = int(item["index"])
    result = {
        "shot_id": item["shot_id"],
        "index": index,
        "segment_id": item["segment_id"],
        "scene_id": "SCENE-001",
        "duration_s": duration,
        "narrative_purpose": item["narrative_purpose"],
        "character_tracks": [
            {
                "character_id": "CHAR-001",
                "visible_interval": {"start_s": 0, "end_s": duration},
                "trajectory": [
                    {"time_s": 0, "position": {"x": 0.25, "y": 0.5, "z": 0}, "facing": "east", "gaze": "CHAR-002", "pose": "guarded"},
                    {"time_s": middle, "position": {"x": 0.35, "y": 0.5, "z": 0}, "facing": "east", "gaze": "ASSET-PROP-001", "pose": "reaching"},
                    {"time_s": duration, "position": {"x": 0.45, "y": 0.5, "z": 0}, "facing": "east", "gaze": "letter", "pose": "holding letter"},
                ],
                "action_events": _timed_events(duration),
                "emotion_events": [
                    {"start_s": 0, "end_s": middle, "emotion": "cautious", "intensity": 0.3, "visible_cues": ["tight jaw"], "trigger": "messenger approaches"},
                    {"start_s": middle, "end_s": duration, "emotion": "surprised", "intensity": 0.9, "visible_cues": ["eyes widen"], "trigger": "recognizes own handwriting"},
                ],
            },
            {
                "character_id": "CHAR-002",
                "visible_interval": {"start_s": 0, "end_s": duration},
                "trajectory": [
                    {"time_s": 0, "position": {"x": 0.75, "y": 0.5, "z": 0}, "facing": "west", "gaze": "CHAR-001", "pose": "still"},
                    {"time_s": duration, "position": {"x": 0.7, "y": 0.5, "z": 0}, "facing": "west", "gaze": "CHAR-001", "pose": "hand lowered"},
                ],
                "action_events": [
                    {"event_id": "MESSENGER-HANDOFF", "start_s": 0, "end_s": duration, "channel": "right-hand", "phase": "development", "description": "offers the letter", "interaction_target": "CHAR-001", "prop_ids": ["ASSET-PROP-001"]},
                ],
                "emotion_events": [
                    {"start_s": 0, "end_s": duration, "emotion": "controlled", "intensity": 0.2, "visible_cues": ["still face"], "trigger": "full_shot intent"},
                ],
            },
        ],
        "camera_track": [
            {"start_s": 0, "end_s": duration, "shot_size": "medium two-shot", "position": {"x": 5, "y": -5, "z": 3}, "target": {"x": 5, "y": 5, "z": 1}, "projection": "perspective", "focal_length_mm": 35, "sensor_width_mm": 36, "interpolation": "linear", "movement": "locked", "focus": "letter handoff"},
        ],
        "audio_track": [
            {"time_mode": "full_shot", "kind": "ambience", "description": "rain"},
            {"start_s": middle, "end_s": duration, "kind": "sfx", "description": "paper rustle"},
        ],
        "director_track": [
            {"start_s": 0, "end_s": middle, "intent": "hold opposition"},
            {"start_s": middle, "end_s": duration, "intent": "prioritize recognition reaction"},
        ],
        "spatial_track": [
            {"time_mode": "full_shot", "axis": "CHAR-001 to CHAR-002", "allowed_side": "south", "interaction": "distance closes"},
        ],
        "scene_fixed_track": [
            {"time_mode": "full_shot", "fixed_element_ids": ["LAMP-001"], "locked": True},
        ],
        "environment": {"location": "rainy street", "weather": "rain"},
        "lighting": {"key": "street lamp", "continuity": "locked"},
        "continuity": {
            "start_state": {"beat": index - 1},
            "end_state": {"beat": index},
            "wardrobe": {"CHAR-001": "blue coat", "CHAR-002": "silver rain cape"},
        },
        "required_asset_ids": [
            "ASSET-STYLE-001",
            "ASSET-CHAR-001",
            "ASSET-CHAR-002",
            "ASSET-SCENE-001",
            "ASSET-PROP-001",
        ],
        "selected_reference_ids": ["ASSET-CHAR-001", "ASSET-SCENE-001", "ASSET-PROP-001"],
        "negative_constraints": ["identity drift", "axis crossing", "untracked prop teleportation"],
    }
    for track in result['character_tracks']:
        for keyframe in track['trajectory']:
            turn = 2**-0.5 if keyframe['facing'] == 'east' else -(2**-0.5)
            keyframe.update(rotation_quaternion=[2**-0.5, 0, 0, turn], interpolation='linear')
    return result


def artifact_for_stage(
    kernel: WorkflowKernel,
    task: dict[str, Any],
    *,
    storyboard_durations: list[float],
    intake_conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    stage = task["stage_id"]
    if stage == "intake_normalize":
        return {"summary": "normalized source", "conflicts": intake_conflicts or [], "unknowns": [], "real_person_likeness": False}
    if stage == "narrative_extract":
        return {
            "facts": [{"fact_id": "FACT-001", "value": "A letter arrives from the future", "status": "source"}],
            "characters": [{"character_id": "CHAR-001", "name": "Lin"}, {"character_id": "CHAR-002", "name": "Messenger"}],
            "locations": [{"location_id": "SCENE-001", "name": "rainy street"}],
            "relationships": [],
            "world_rules": [],
            "open_threads": ["Who sent the letter?"],
            "adaptation_additions": [],
            "unknowns": [],
        }
    if stage == "adaptation_plan":
        return {"beats": [{"beat_id": "BEAT-001", "purpose": "inciting incident"}], "adaptation_additions": []}
    if stage == "director_treatment":
        return {'scenes': [{'scene_id': 'SCENE-001', 'purpose': 'reveal future letter',
            'pov': 'Lin', 'audience_information': 'recognizes handwriting', 'emotional_start': 'cautious',
            'emotional_end': 'surprised', 'camera_rationale': 'show handoff then reaction',
            'edit_rationale': 'preserve action continuity', 'source_refs': ['FACT-001'],
            'beats': [{'beat_id': 'BEAT-001', 'character_id': 'CHAR-001', 'goal': 'understand sender',
                'obstacle': 'mystery', 'tactic': 'inspect letter', 'action': 'accept letter',
                'reaction': 'recognition', 'trigger': 'own handwriting'}]}]}
    if stage == "screenplay":
        return {"scenes": [{"scene_id": "SCENE-001", "action": "Lin receives the letter", "dialogue": []}]}
    if stage == "screenplay_enhance":
        return {"scenes": [{"scene_id": "SCENE-001", "action": "Lin receives and recognizes the letter in rain", "dialogue": []}]}
    if stage == "story_quality_gate":
        return {"review_status": "approved", "issues": [], "checked_scope": stage}
    if stage == "segment_plan":
        return {
            "target_duration_s": kernel.state["decisions"]["segment_duration_s"],
            "segments": [
                {"segment_id": f"SEG-{index:03d}", "index": index, "target_duration_s": value, "source_refs": ["FACT-001"]}
                for index, value in enumerate(storyboard_durations, start=1)
            ],
        }
    if stage == "visual_bible":
        return {
            "style": {"style_id": "STYLE-001", "invariants": ["premium 2D line language"]},
            "characters": [
                {"character_id": "CHAR-001", "identity_invariants": ["short black hair", "blue coat"]},
                {"character_id": "CHAR-002", "identity_invariants": ["silver rain cape"]},
            ],
            "locations": [{"location_id": "SCENE-001", "anchors": ["street lamp"]}],
            "props": [{"prop_id": "ASSET-PROP-001", "invariants": ["red wax seal"]}],
        }
    if stage == "asset_plan":
        return _asset_plan()
    if stage == "spatial_blocking":
        return _scene_space(kernel)
    if stage == "storyboard_plan":
        return {
            "shots": [
                {
                    "shot_id": f"SHOT-{index:03d}",
                    "index": index,
                    "segment_id": f"SEG-{index:03d}",
                    "duration_s": duration,
                    "narrative_purpose": f"letter handoff beat {index}",
                    "scene_id": "SCENE-001",
                    "source_refs": ["FACT-001"],
                }
                for index, duration in enumerate(storyboard_durations, start=1)
            ]
        }
    if stage == "shot_timeline_specs":
        planned = {item["shot_id"]: item for item in kernel.store.read(SHOT_PLAN)["shots"]}
        return {
            "shots": [_timeline_shot(planned[shot_id]) for shot_id in task["shot_batch"]["shot_ids"]],
            "memory_update": {"next_hook": "letter warning"},
        }
    if stage == "audio_edit_plan":
        index = kernel.store.read(SHOT_TIMELINE_INDEX)
        return {
            "dialogue_table": [],
            "voice_cast": [],
            "sfx": [{"id": "SFX-RAIN", "description": "rain ambience"}],
            "music": [{"mood": "mystery"}],
            "timeline": [{"shot_id": item["shot_id"], "duration_s": item["duration_s"]} for item in index["shots"]],
            "subtitle_language": kernel.state["decisions"]["subtitle_language"],
        }
    raise AssertionError(f"No test artifact for semantic stage {stage}")


def drive_to_completion(
    kernel: WorkflowKernel,
    *,
    choices: dict[str, Any] | None = None,
    storyboard_durations: list[float] | None = None,
    intake_conflicts: list[dict[str, Any]] | None = None,
    max_steps: int = 300,
) -> dict[str, Any]:
    selected = {**DEFAULT_CHOICES, **(choices or {})}
    durations = storyboard_durations or [20]
    status = kernel.run()
    for step in range(1, max_steps + 1):
        if status["status"] == "complete":
            return status
        if status["status"] == "awaiting_choice":
            request = status["decision_request"]
            selections = {field["id"]: selected[field["id"]] for field in request["fields"]}
            status = kernel.resume(
                {
                    "request_id": request["request_id"],
                    "context_fingerprint": request["context_fingerprint"],
                    "selections": selections,
                }
            )
            continue
        if status["status"] == "awaiting_agent_result":
            task = status["task_envelope"]
            artifact = artifact_for_stage(
                kernel,
                task,
                storyboard_durations=durations,
                intake_conflicts=intake_conflicts,
            )
            result = {
                "schema_version": "3.0",
                "result_id": stable_id("result", task["task_id"], step),
                "project_id": task["project_id"],
                "stage_id": task["stage_id"],
                "context_fingerprint": task["context_fingerprint"],
                "status": "approved" if task["stage_id"] == "story_quality_gate" else "draft",
                "artifact": artifact,
                "findings": [],
                "provenance": [{"source": path} for path in task["input_artifacts"]],
                "next_action": None,
            }
            status = kernel.submit(result)
            continue
        raise AssertionError(f"Workflow stopped unexpectedly: {status}")
    raise AssertionError("Workflow did not complete within step limit")
