from __future__ import annotations

import json
import math
import re
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .exporter import build_delivery_archive
from .graph import ENTRY_SKIPS, Stage, WorkflowGraph
from .ingest import determine_entry_mode, ingest_inputs
from .layout import (
    ADAPTED_PROMPT_PACKAGE,
    ASSET_REGISTRY,
    CANONICAL_PROMPT_PACKAGE,
    DYNAMIC_MEMORY,
    FINAL_DELIVERY_INDEX,
    GENERATION_SEGMENTS,
    MEDIA_EXECUTION_INDEX,
    NARRATIVE_BUNDLE,
    P01,
    P02,
    P03,
    P04,
    P05,
    P06,
    P07,
    P08,
    P09,
    P10,
    P11,
    P12,
    P13,
    PHASES,
    LEGACY_PATH_MAP,
    SCENE_SPACE_PLAN,
    SHOT_PLAN,
    SHOT_TIMELINE_INDEX,
    SOURCE_REGISTRY,
)
from .pipeline import DeterministicPipeline, decision_fields, validate_decision
from .schema import load_schema, validate, validate_artifact
from .storage import ProjectStore
from .transactions import project_transaction
from .capabilities import probe_capabilities
from .utils import (
    PACKAGE_ROOT,
    SCHEMA_VERSION,
    aggregate_hash,
    canonical_json,
    read_json,
    sha256_bytes,
    sha256_file,
    stable_id,
)


class WorkflowError(RuntimeError):
    pass


class StaleContextError(WorkflowError):
    pass


class WorkflowKernel:
    """Authoritative workflow state machine and artifact commit boundary."""

    def __init__(
        self,
        project_dir: Path | str,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.store = ProjectStore(project_dir)
        if self.store.exists("project.json"):
            with self.store.transaction():
                pass  # Recover an interrupted write set before reading control files.
        self.graph = WorkflowGraph()
        self.pipeline = DeterministicPipeline(self.store, environment=environment)
        if not self.store.exists("project.json"):
            raise WorkflowError(f"Not an AI comic-drama project: {self.store.root}")
        raw_project = self.store.read("project.json")
        if raw_project.get('schema_version') not in {'1.0', '2.0', SCHEMA_VERSION}:
            raise WorkflowError('Unsupported project schema; preserve it and supply a supported migration contract')
        self._legacy_v1 = (
            raw_project.get("schema_version") != SCHEMA_VERSION
            or raw_project.get("workflow_id") != self.graph.workflow_id
        )

    @classmethod
    def initialize(
        cls,
        project_dir: Path | str,
        inputs: list[str],
        *,
        title: str | None = None,
        input_type: str | None = None,
        project_format: str = "short-drama",
        work_depth: str = "standard",
        adaptation_policy: str = "limited-expansion",
        environment: Mapping[str, str] | None = None,
    ) -> "WorkflowKernel":
        if not inputs:
            raise WorkflowError("At least one source input is required")
        store = ProjectStore(project_dir)
        if store.exists("project.json"):
            raise WorkflowError("Project already exists; use run or resume")
        store.root.mkdir(parents=True, exist_ok=True)
        for phase in PHASES:
            store.path(str(phase["folder"])).mkdir(parents=True, exist_ok=True)
        store.path("runtime").mkdir(parents=True, exist_ok=True)
        store.path(".history").mkdir(parents=True, exist_ok=True)
        records, entry_mode = ingest_inputs(store, inputs, input_type=input_type)
        project_title = (title or store.root.name).strip()
        source_identity = aggregate_hash((record["source_id"], record["sha256"]) for record in records)
        project_id = stable_id("project", project_title, source_identity)
        project = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "project",
            "artifact_id": stable_id("artifact", project_id, "project"),
            "project_id": project_id,
            "revision": 1,
            "stage_id": "project_setup",
            "role_provenance": "kernel",
            "title": project_title,
            "format": project_format,
            "work_depth": work_depth,
            "adaptation_policy": adaptation_policy,
            "selected_config": {},
            "external_generation_blocked": True,
            "entry_mode": entry_mode,
            "workflow_id": WorkflowGraph().workflow_id,
        }
        validate_artifact(project)
        store.commit("project.json", project)
        registry = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "source-registry",
            "artifact_id": stable_id("artifact", project_id, "source-registry"),
            "project_id": project_id,
            "revision": 1,
            "stage_id": "source_ingest",
            "role_provenance": "kernel",
            "entry_mode": entry_mode,
            "sources": records,
        }
        store.commit(SOURCE_REGISTRY, registry)
        graph = WorkflowGraph()
        phase_index = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "phase-index",
            "artifact_id": stable_id("artifact", project_id, "phase-index"),
            "project_id": project_id,
            "revision": 1,
            "stage_id": "project_setup",
            "role_provenance": "kernel",
            "workflow_id": graph.workflow_id,
            "phases": [
                {
                    **phase,
                    "stage_ids": [stage.id for stage in graph.stages if stage.phase_id == phase["id"]],
                }
                for phase in PHASES
            ],
        }
        store.commit("phase-index.json", phase_index)
        skipped = list(ENTRY_SKIPS.get(entry_mode, ()))
        stage_status = {stage.id: "pending" for stage in graph.stages}
        stage_status["project_setup"] = "complete"
        stage_status["source_ingest"] = "complete"
        for stage_id in skipped:
            stage_status[stage_id] = "complete"
        state = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "workflow-state",
            "artifact_id": stable_id("artifact", project_id, "state"),
            "project_id": project_id,
            "revision": 1,
            "stage_id": "source_ingest",
            "role_provenance": "kernel",
            "status": "running",
            "current_stage": None,
            "active_task": None,
            "active_decision": None,
            "stage_status": stage_status,
            "decisions": {},
            "decision_approvals": {},
            "decision_stages": {},
            "failure_counts": {},
            "skipped_stages": skipped,
            "skip_reasons": {
                stage_id: f"Skipped for {entry_mode} entry; downstream tasks receive explicit missing-input constraints."
                for stage_id in skipped
            },
            "invalidated_stages": [],
            "narrative_completed_batches": [],
        }
        store.commit("state.json", state)
        store.rebuild_manifest()
        return cls(store.root, environment=environment)

    def _legacy_fingerprint(self) -> str:
        entries: list[tuple[str, str]] = []
        for path in sorted(self.store.root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.store.root)
            if relative.parts and relative.parts[0] in {".git", ".history", "runtime"}:
                continue
            entries.append((relative.as_posix(), sha256_file(path)))
        return aggregate_hash(entries)

    def _migration_status(self) -> dict[str, Any]:
        read_only_path = "runtime/migration/read-only.json"
        if self.store.exists(read_only_path):
            return {
                "project_id": self.project.get("project_id"),
                "project_dir": str(self.store.root),
                "status": "blocked",
                "current_stage": "migration_v1",
                "migration_mode": "read-only",
                "next_action": "inspect_only",
                "boundary": "No Schema 3.0 artifact or approval was inferred from the legacy project.",
            }
        fingerprint = self._legacy_fingerprint()
        request_id = stable_id("decision", self.project.get("project_id"), "migration_v1", fingerprint)
        relative = "runtime/migration/decision-request.json"
        field = decision_fields(["migration_action"])[0]
        copy_target = self.store.root.with_name(f"{self.store.root.name}-v3")
        for option in field["options"]:
            if option["id"] == "copy-new":
                option["consequence"] = f"Create and migrate a separate project at {copy_target}."
        request = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "decision-request",
            "artifact_id": stable_id("artifact", self.project.get("project_id"), request_id),
            "project_id": self.project.get("project_id"),
            "revision": self.store.revision_for(relative),
            "stage_id": "migration_v1",
            "role_provenance": "kernel",
            "request_id": request_id,
            "status": "open",
            "fields": [field],
            "context_fingerprint": fingerprint,
            "impact": "The v1 project remains unchanged until an explicit migration action is selected.",
        }
        if not self.store.exists(relative) or self.store.read(relative).get("request_id") != request_id:
            self.store.commit(relative, request)
        else:
            request = self.store.read(relative)
        return {
            "project_id": self.project.get("project_id"),
            "project_dir": str(self.store.root),
            "status": "awaiting_choice",
            "current_stage": "migration_v1",
            "next_action": "submit_decision",
            "decision_request_path": str(self.store.path(relative)),
            "decision_request": request,
        }

    def _resume_migration(self, decision: Path | str | dict[str, Any]) -> dict[str, Any]:
        status = self._migration_status()
        if status["status"] != "awaiting_choice":
            raise WorkflowError("The legacy project is already open in read-only mode")
        request = status["decision_request"]
        payload = read_json(Path(decision)) if isinstance(decision, (str, Path)) else deepcopy(decision)
        if payload.get("request_id") != request["request_id"]:
            raise StaleContextError("Migration decision request ID does not match")
        if payload.get("context_fingerprint", request["context_fingerprint"]) != request["context_fingerprint"]:
            raise StaleContextError("Migration decision context is stale")
        selections = payload.get("selections")
        if not isinstance(selections, dict) or set(selections) != {"migration_action"}:
            raise WorkflowError("Migration selections must contain exactly migration_action")
        validate_decision(request["fields"][0], selections["migration_action"])
        action = selections["migration_action"]
        approval = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "approval-record",
            "artifact_id": stable_id("artifact", self.project["project_id"], "migration-approval"),
            "project_id": self.project["project_id"],
            "revision": self.store.revision_for("runtime/migration/approval.json"),
            "stage_id": "migration_v1",
            "role_provenance": "kernel",
            "approval_id": stable_id("approval", request["request_id"], action),
            "request_id": request["request_id"],
            "selections": selections,
            "context_fingerprint": request["context_fingerprint"],
            "impact_scope": ["v1-project-migration"],
            "valid": True,
        }
        self.store.commit("runtime/migration/approval.json", approval)
        if action == "read-only":
            self.store.write_text(
                "runtime/migration/read-only.json",
                canonical_json({"action": action, "approval_id": approval["approval_id"]}),
            )
            return self._migration_status()
        if action == "copy-new":
            target = self.store.root.with_name(f"{self.store.root.name}-v3")
            if target.exists():
                raise WorkflowError(f"Copy target already exists: {target}")
            shutil.copytree(
                self.store.root,
                target,
                ignore=shutil.ignore_patterns(".git", ".history", "runtime"),
            )
            copied = WorkflowKernel(target, environment=self.pipeline.environment)
            copied._perform_v1_migration(action="copy-new", source_root=self.store.root)
            result = copied.run()
            result["copied_project_dir"] = str(target)
            result["original_project_unchanged"] = True
            return result
        self._perform_v1_migration(action="non-destructive-migrate", source_root=self.store.root)
        return self.run()

    @staticmethod
    def _rewrite_legacy_paths(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: WorkflowKernel._rewrite_legacy_paths(item) for key, item in value.items()}
        if isinstance(value, list):
            return [WorkflowKernel._rewrite_legacy_paths(item) for item in value]
        if isinstance(value, str):
            return LEGACY_PATH_MAP.get(value, value)
        return value

    def _perform_v1_migration(self, *, action: str, source_root: Path) -> None:
        if self.project.get('schema_version') == '2.0':
            from .migration_v3 import migrate_v2
            migrate_v2(self, action=action, source_root=source_root)
            return
        for phase in PHASES:
            self.store.path(str(phase["folder"])).mkdir(parents=True, exist_ok=True)
        old_project = deepcopy(self.store.read("project.json"))
        old_state = deepcopy(self.store.read("state.json")) if self.store.exists("state.json") else {}
        snapshot_root = self.store.path(".history/migrations/v1/tree")
        snapshot_entries: list[tuple[str, str]] = []
        source_files = [path for path in self.store.root.rglob("*") if path.is_file()]
        for path in source_files:
            relative = path.relative_to(self.store.root)
            if relative.parts and relative.parts[0] in {".git", ".history"}:
                continue
            if relative.parts[:2] == ("runtime", "transactions"):
                continue
            target = snapshot_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            snapshot_entries.append((relative.as_posix(), sha256_file(path)))
        snapshot_hash = aggregate_hash(snapshot_entries)
        self.store.write_text(
            ".history/migrations/v1/snapshot-manifest.json",
            canonical_json(
                {
                    "source_root": str(source_root),
                    "file_count": len(snapshot_entries),
                    "aggregate_hash": snapshot_hash,
                    "files": [{"path": path, "sha256": digest} for path, digest in snapshot_entries],
                }
            ),
        )

        project_id = str(old_project.get("project_id") or stable_id("project", self.store.root.name, snapshot_hash))
        old_registry = (
            deepcopy(self.store.read("sources/source-registry.json"))
            if self.store.exists("sources/source-registry.json")
            else None
        )
        migrated_paths: list[str] = []
        rejected_paths: list[dict[str, str]] = []
        if old_registry:
            records = []
            for index, source in enumerate(old_registry.get("sources", []), start=1):
                record = deepcopy(source)
                source_id = str(record.get("source_id") or f"SOURCE-{index:03d}")
                record["source_id"] = source_id
                for key, subfolder in (("stored_path", "original"), ("text_path", "text")):
                    legacy_relative = record.get(key)
                    if not legacy_relative or not self.store.exists(str(legacy_relative)):
                        continue
                    legacy_file = self.store.path(str(legacy_relative))
                    new_relative = f"{P01}/sources/{subfolder}/{source_id}-{legacy_file.name}"
                    self.store.copy_source(legacy_file, new_relative)
                    record[key] = new_relative
                    if key == "stored_path":
                        record["sha256"] = sha256_file(self.store.path(new_relative))
                record.setdefault("rights_status", "unknown")
                record.setdefault("authority", "source")
                records.append(record)
            entry_mode = str(old_registry.get("entry_mode") or determine_entry_mode(item.get("kind", "other") for item in records))
            registry = {
                **old_registry,
                "schema_version": SCHEMA_VERSION,
                "artifact_type": "source-registry",
                "artifact_id": stable_id("artifact", project_id, "source-registry"),
                "project_id": project_id,
                "revision": self.store.revision_for(SOURCE_REGISTRY),
                "stage_id": "source_ingest",
                "role_provenance": "kernel",
                "entry_mode": entry_mode,
                "sources": records,
            }
            self.store.commit(SOURCE_REGISTRY, registry)
            migrated_paths.append(SOURCE_REGISTRY)
        else:
            entry_mode = str(old_project.get("entry_mode") or "legacy-project")

        for legacy_path, target_path in LEGACY_PATH_MAP.items():
            if legacy_path == "sources/source-registry.json" or not self.store.exists(legacy_path):
                continue
            value = self._rewrite_legacy_paths(deepcopy(self.store.read(legacy_path)))
            producer_id = self.graph.producer_for(target_path)
            if producer_id:
                stage = self.graph.get(producer_id)
                artifact_type = stage.artifact_type or str(value.get("artifact_type") or "migrated-artifact")
                role = stage.role
            else:
                producer_id = "narrative_extract"
                artifact_type = str(value.get("artifact_type") or "dynamic-memory")
                role = "kernel"
            value.update(
                {
                    "schema_version": SCHEMA_VERSION,
                    "artifact_type": artifact_type,
                    "artifact_id": stable_id("artifact", project_id, producer_id, target_path),
                    "project_id": project_id,
                    "revision": self.store.revision_for(target_path),
                    "stage_id": producer_id,
                    "role_provenance": role,
                    "migration_source_path": legacy_path,
                    "migration_source_sha256": sha256_file(self.store.path(legacy_path)),
                }
            )
            try:
                self.store.commit(target_path, value)
            except Exception as error:
                rejected_paths.append({"path": legacy_path, "reason": str(error)})
            else:
                migrated_paths.append(target_path)

        valid_depths = {"quick", "standard", "deep"}
        valid_policies = {"source-strict", "limited-expansion", "creative-first"}
        work_depth = old_project.get("work_depth") if old_project.get("work_depth") in valid_depths else "standard"
        adaptation_policy = (
            old_project.get("adaptation_policy")
            if old_project.get("adaptation_policy") in valid_policies
            else "limited-expansion"
        )
        upstream_decision_ids = {
            "work_depth",
            "adaptation_policy",
            "rights_status",
            "conflict_policy",
            "core_conflict_resolution",
            "likeness_authorization",
            "unreadable_source_action",
            "chapter_batch_size",
            "segment_duration_s",
        }
        decisions: dict[str, Any] = {}
        candidates = {
            **old_state.get("decisions", {}),
            "work_depth": work_depth,
            "adaptation_policy": adaptation_policy,
        }
        for field_id in upstream_decision_ids:
            if field_id not in candidates:
                continue
            try:
                validate_decision(decision_fields([field_id])[0], candidates[field_id])
            except (KeyError, ValueError):
                continue
            decisions[field_id] = candidates[field_id]

        project = {
            **old_project,
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "project",
            "artifact_id": stable_id("artifact", project_id, "project"),
            "project_id": project_id,
            "revision": self.store.revision_for("project.json"),
            "stage_id": "project_setup",
            "role_provenance": "kernel",
            "title": str(old_project.get("title") or self.store.root.name),
            "format": old_project.get("format") if old_project.get("format") in {"short-drama", "film-narrative", "visual-concept"} else "short-drama",
            "work_depth": work_depth,
            "adaptation_policy": adaptation_policy,
            "selected_config": decisions,
            "external_generation_blocked": bool(old_project.get("external_generation_blocked", True)),
            "entry_mode": entry_mode,
            "workflow_id": self.graph.workflow_id,
            "migration": {"from_schema": "1.0", "action": action, "snapshot_hash": snapshot_hash},
        }
        self.store.commit("project.json", project)

        phase_index = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "phase-index",
            "artifact_id": stable_id("artifact", project_id, "phase-index"),
            "project_id": project_id,
            "revision": self.store.revision_for("phase-index.json"),
            "stage_id": "project_setup",
            "role_provenance": "kernel",
            "workflow_id": self.graph.workflow_id,
            "phases": [
                {
                    **phase,
                    "stage_ids": [stage.id for stage in self.graph.stages if stage.phase_id == phase["id"]],
                }
                for phase in PHASES
            ],
        }
        self.store.commit("phase-index.json", phase_index)

        if {"work_depth", "adaptation_policy"} <= decisions.keys():
            configuration_stage = self.graph.get("project_configuration")
            configuration = self._formal_artifact(
                configuration_stage,
                {
                    "work_depth": work_depth,
                    "adaptation_policy": adaptation_policy,
                    "migration_carried": True,
                },
            )
            self.store.commit(str(configuration_stage.output), configuration)
            migrated_paths.append(str(configuration_stage.output))

        migration_report_path = f"{P01}/migration-report.json"
        migration_report = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "migration-report",
            "artifact_id": stable_id("artifact", project_id, "migration-report", snapshot_hash),
            "project_id": project_id,
            "revision": self.store.revision_for(migration_report_path),
            "stage_id": "project_setup",
            "role_provenance": "kernel",
            "action": action,
            "source_schema": "1.0",
            "target_schema": SCHEMA_VERSION,
            "snapshot_path": ".history/migrations/v1/tree",
            "snapshot_aggregate_hash": snapshot_hash,
            "migrated_paths": sorted(migrated_paths),
            "rejected_paths": rejected_paths,
            "invalidated_phases": [f"phase-{index:02d}" for index in range(7, 14)],
            "old_approvals_accepted": False,
        }
        self.store.commit(migration_report_path, migration_report)

        stage_status = {stage.id: "pending" for stage in self.graph.stages}
        stage_status["project_setup"] = "complete"
        if self.store.exists(SOURCE_REGISTRY):
            stage_status["source_ingest"] = "complete"
        for stage in self.graph.stages:
            if self.graph.phase(stage.phase_id).index <= 6 and stage.output and self.store.exists(stage.output):
                try:
                    validate_artifact(self.store.read(stage.output))
                except Exception:
                    continue
                stage_status[stage.id] = "complete"
            elif self.graph.phase(stage.phase_id).index >= 7:
                stage_status[stage.id] = "invalidated"
        skipped = list(ENTRY_SKIPS.get(entry_mode, ()))
        for stage_id in skipped:
            if self.graph.phase_for_stage(stage_id).index <= 6:
                stage_status[stage_id] = "complete"
        state = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "workflow-state",
            "artifact_id": stable_id("artifact", project_id, "state"),
            "project_id": project_id,
            "revision": self.store.revision_for("state.json"),
            "stage_id": "project_setup",
            "role_provenance": "kernel",
            "status": "running",
            "current_stage": None,
            "active_task": None,
            "active_decision": None,
            "stage_status": stage_status,
            "decisions": decisions,
            "decision_approvals": {field_id: migration_report_path for field_id in decisions},
            "decision_stages": {field_id: "project_setup" for field_id in decisions},
            "failure_counts": {},
            "skipped_stages": skipped,
            "skip_reasons": {stage_id: "Preserved entry-mode skip during approved v1 migration." for stage_id in skipped},
            "invalidated_stages": [stage.id for stage in self.graph.stages if self.graph.phase_for_stage(stage.id).index >= 7],
            "narrative_completed_batches": [],
            "migration_report": migration_report_path,
        }
        self.store.commit("state.json", state)

        for root_name in (
            "sources",
            "intake",
            "story",
            "planning",
            "reviews",
            "storyboard",
            "design",
            "assets",
            "prompts",
            "media",
            "edit",
            "delivery",
            "publish",
            "decisions",
        ):
            legacy_root = self.store.path(root_name)
            if legacy_root.exists():
                from .transactions import before_write
                for old_file in sorted(legacy_root.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                    if old_file.is_file():
                        before_write(self.store.root, old_file)
                        old_file.unlink()
                    elif old_file.is_dir():
                        old_file.rmdir()
                legacy_root.rmdir()
        runtime = self.store.path("runtime")
        for old in list(runtime.iterdir()) if runtime.exists() else []:
            if old.name == "transactions":
                continue
            if old.is_dir():
                from .transactions import before_write
                for old_file in sorted(old.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                    if old_file.is_file():
                        before_write(self.store.root, old_file)
                        old_file.unlink()
                    elif old_file.is_dir():
                        old_file.rmdir()
                old.rmdir()
            else:
                from .transactions import before_write
                before_write(self.store.root, old)
                old.unlink()
        self.store.path("runtime").mkdir(parents=True, exist_ok=True)
        self.store.rebuild_manifest()
        self._legacy_v1 = False

    @property
    def project(self) -> dict[str, Any]:
        return self.store.read("project.json")

    @property
    def state(self) -> dict[str, Any]:
        return self.store.read("state.json")

    def _save_state(self, state: dict[str, Any]) -> None:
        state = deepcopy(state)
        state["revision"] = self.store.revision_for("state.json")
        state["stage_id"] = state.get("current_stage") or state.get("stage_id") or "project_setup"
        self.store.commit("state.json", state)

    def _save_project(self, project: dict[str, Any]) -> None:
        project = deepcopy(project)
        project["revision"] = self.store.revision_for("project.json")
        self.store.commit("project.json", project)

    def _formal_artifact(
        self,
        stage: Stage,
        body: dict[str, Any],
        *,
        output_path: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        if not stage.output and output_path is None:
            raise WorkflowError(f"Stage has no output contract: {stage.id}")
        relative = output_path or str(stage.output)
        value = deepcopy(body)
        value.update(
            {
                "schema_version": SCHEMA_VERSION,
                "artifact_type": stage.artifact_type,
                "artifact_id": stable_id("artifact", self.project["project_id"], stage.id, relative),
                "project_id": self.project["project_id"],
                "revision": self.store.revision_for(relative),
                "stage_id": stage.id,
                "role_provenance": role or stage.role,
            }
        )
        return value

    def _commit_stage_output(self, stage: Stage, body: dict[str, Any]) -> dict[str, Any]:
        if not stage.output:
            raise WorkflowError(f"Stage {stage.id} has no output")
        artifact = self._formal_artifact(stage, body)
        if stage.id == 'audio_edit_plan':
            validate_artifact(artifact)
            from .editing import validate_edit_plan
            validate_edit_plan(artifact, shot_ids={s['shot_id'] for s in self._planned_shots()},
                               subtitle_language=self.state['decisions']['subtitle_language'])
        self.store.commit(stage.output, artifact)
        self._write_stage_views(stage, artifact)
        return artifact

    @staticmethod
    def _safe_view_name(value: object) -> str:
        normalized = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value)).strip("-.")
        return normalized or "item"

    def _replace_text_views(
        self,
        directory: str,
        views: dict[str, str],
    ) -> None:
        target = self.store.path(directory)
        target.mkdir(parents=True, exist_ok=True)
        expected = set(views)
        for existing in target.glob("*.txt"):
            if existing.name not in expected:
                from .transactions import before_write
                before_write(self.store.root, existing)
                existing.unlink()
        for name, content in sorted(views.items()):
            self.store.write_text(f"{directory}/{name}", content)

    def _view_header(self, source_path: str) -> str:
        return (
            f"Canonical source: {source_path}\n"
            f"Canonical SHA-256: {sha256_file(self.store.path(source_path))}\n\n"
        )

    def _write_stage_views(self, stage: Stage, artifact: dict[str, Any]) -> None:
        if stage.id == "canonical_prompt_compile":
            source = str(stage.output)
            views = {
                f"{self._safe_view_name(item['shot_id'])}.txt": (
                    self._view_header(source)
                    + f"Shot ID: {item['shot_id']}\n"
                    + f"Canonical fact hash: {item['canonical_fact_hash']}\n\n"
                    + item["execution_prompt"]
                    + "\n"
                )
                for item in artifact["prompts"]
            }
            self._replace_text_views(f"{P10}/shots", views)
        elif stage.id == "platform_adaptation":
            source = str(stage.output)
            views = {
                f"{self._safe_view_name(item['shot_id'])}.txt": (
                    self._view_header(source)
                    + f"Adapter: {artifact['adapter_id']}\n"
                    + f"Shot ID: {item['shot_id']}\n"
                    + f"Canonical fact hash: {item['canonical_fact_hash']}\n\n"
                    + item["adapted_prompt"]
                    + "\n"
                )
                for item in artifact["prompts"]
            }
            self._replace_text_views(f"{P11}/adapted", views)
        elif stage.id == "asset_generation_or_prompt":
            source = str(stage.output)
            views = {
                f"{self._safe_view_name(item['asset_id'])}.txt": (
                    self._view_header(source)
                    + f"Asset ID: {item['asset_id']}\n"
                    + f"Reference IDs: {json.dumps(item.get('reference_ids', []), ensure_ascii=False)}\n\n"
                    + item["prompt"]
                    + "\n"
                )
                for item in artifact.get("assets", [])
            }
            self._replace_text_views(f"{P07}/assets/prompts", views)
        elif stage.id == "storyboard_reference_generation_or_prompt":
            source = str(stage.output)
            views = {
                f"{self._safe_view_name(item['reference_id'])}.txt": (
                    self._view_header(source)
                    + f"Reference ID: {item['reference_id']}\n"
                    + f"Shot ID: {item['shot_id']}\n"
                    + f"Time: {item['time_s']}s\n\n"
                    + item["prompt"]
                    + "\n"
                )
                for item in artifact.get("references", [])
            }
            self._replace_text_views(f"{P09}/reference-prompts", views)
        elif stage.id == "audio_edit_plan":
            source = str(stage.output)
            lines = [self._view_header(source).rstrip(), ""]
            for index, item in enumerate(artifact.get("dialogue_table", []), start=1):
                line_id = item.get("line_id", f"LINE-{index:03d}")
                start = item.get("start_s", "unknown")
                end = item.get("end_s", "unknown")
                speaker = item["speaker_id"]
                lines.append(f"[{line_id}] {start}-{end} | {speaker}: {item.get('text', '')}")
            if not artifact.get("dialogue_table"):
                lines.append("No dialogue lines in the approved edit plan.")
            self._replace_text_views(f"{P12}/derived", {"voice-script.txt": "\n".join(lines) + "\n"})

    def _prepare_export_bundle(self, stage: Stage, body: dict[str, Any]) -> dict[str, Any]:
        prepared = deepcopy(body)
        extras = prepared.pop("_extra_artifacts", [])
        for item in extras:
            relative = str(item["path"])
            value = deepcopy(item["body"])
            value.update(
                {
                    "schema_version": SCHEMA_VERSION,
                    "artifact_type": item["artifact_type"],
                    "artifact_id": stable_id("artifact", self.project["project_id"], relative),
                    "project_id": self.project["project_id"],
                    "revision": self.store.revision_for(relative),
                    "stage_id": stage.id,
                    "role_provenance": "kernel",
                }
            )
            self.store.commit(relative, value)
            if item["artifact_type"] == "cover-package":
                self.store.write_text(
                    f"{P13}/publish/cover-prompt.txt",
                    self._view_header(relative) + value["prompt"] + "\n",
                )
            elif item["artifact_type"] == "publication-copy":
                self.store.write_text(
                    f"{P13}/publish/copy.txt",
                    self._view_header(relative)
                    + f"{value['title']}\n\n{value['synopsis']}\n",
                )
            elif item["artifact_type"] == "publication-checklist":
                checklist = "\n".join(
                    f"- {entry['id']}: {entry['status']}" for entry in value["items"]
                )
                self.store.write_text(
                    f"{P13}/publish/checklist.txt",
                    self._view_header(relative) + checklist + "\n",
                )
        self.store.rebuild_manifest()
        prepared["artifacts"] = [
            {**item, "delivery_status": "included"}
            for item in self.store.read("manifest.json").get("files", [])
            if item.get("path") not in {"state.json", "state.md", FINAL_DELIVERY_INDEX, str(Path(FINAL_DELIVERY_INDEX).with_suffix('.md'))}
            and not str(item.get("path", "")).startswith(("runtime/", ".history/"))
        ]
        return prepared

    def _usable_inputs(self, stage: Stage, state: dict[str, Any]) -> tuple[list[str], list[str]]:
        available: list[str] = []
        missing: list[str] = []
        for relative in stage.inputs:
            producer = self.graph.producer_for(relative)
            if self.store.exists(relative) and (producer is None or state["stage_status"].get(producer) == "complete"):
                available.append(relative)
            else:
                missing.append(relative)
        if stage.id == "shot_timeline_specs" and self.store.exists(DYNAMIC_MEMORY):
            available.append(DYNAMIC_MEMORY)
        if missing and self.store.exists(SOURCE_REGISTRY) and SOURCE_REGISTRY not in available:
            available.append(SOURCE_REGISTRY)
        return available, missing

    def _context_fingerprint(
        self,
        stage: Stage,
        state: dict[str, Any],
        input_paths: list[str],
        resources: list[str],
        shot_batch: dict[str, Any] | None = None,
        source_batch: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "workflow_id": self.graph.workflow_id,
            "workflow_hash": sha256_file(PACKAGE_ROOT / "workflow-graph.json"),
            "schema_hashes": [(p.name, sha256_file(p)) for p in sorted((PACKAGE_ROOT / "schemas").glob("*.json"))],
            "runtime_hashes": [(p.name, sha256_file(p)) for p in sorted(Path(__file__).parent.glob("*.py"))],
            "capabilities": probe_capabilities(environment=self.pipeline.environment),
            "stage_id": stage.id,
            "inputs": [(path, sha256_file(self.store.path(path))) for path in sorted(input_paths)],
            "decisions": state.get("decisions", {}),
            "resources": [
                (resource, sha256_file(PACKAGE_ROOT / resource)) for resource in sorted(resources)
            ],
            "shot_batch": shot_batch,
            "source_batch": source_batch,
        }
        return sha256_bytes(canonical_json(payload).encode("utf-8"))

    def _dynamic_required_decisions(self, stage: Stage, state: dict[str, Any]) -> list[str]:
        required = list(stage.required_decisions)
        if stage.id == 'project_configuration':
            required.append('delivery_target')
        if stage.id in {'asset_generation_or_prompt', 'storyboard_reference_generation_or_prompt'} and state['decisions'].get('asset_image_strategy') == 'codex-native':
            required.append('image_job_budget')
        if stage.id == 'platform_adaptation' and state['decisions'].get('delivery_target') == 'dual-reference-previs' and state['decisions'].get('target_platform') != 'platform-neutral':
            required.append('platform_reference_action')
        if stage.id == "gap_resolution":
            registry = self.store.read(SOURCE_REGISTRY)
            if registry["entry_mode"] == "mixed":
                required.append("conflict_policy")
            if self.store.exists(f"{P02}/intake-brief.json"):
                brief = self.store.read(f"{P02}/intake-brief.json")
                conflicts = brief.get("conflicts", [])
                if any(item.get("severity") == "core" for item in conflicts if isinstance(item, dict)):
                    required.append("core_conflict_resolution")
                if brief.get("real_person_likeness"):
                    required.append("likeness_authorization")
            if self._unreadable_narrative_sources(registry):
                required.append("unreadable_source_action")
        if stage.id == "narrative_extract" and len(self._novel_chapters()) > 1:
            required.append("chapter_batch_size")
        if stage.id == "asset_generation_or_prompt" and self.store.exists(f"{P07}/capability-snapshot.json"):
            capabilities = self.store.read(f"{P07}/capability-snapshot.json")["capabilities"]
            image_capability = capabilities["image_generation"]
            if state["decisions"].get("asset_image_strategy") == "generate-if-available":
                if not self._can_execute_local_image_fixture(image_capability):
                    required.append("asset_image_fallback")
                if image_capability["status"] in {"requires_account", "requires_payment"}:
                    required.append("visual_external_action")
        if (
            stage.id == "storyboard_reference_generation_or_prompt"
            and "reference-images" in state["decisions"].get("storyboard_views", [])
            and self.store.exists(f"{P07}/capability-snapshot.json")
        ):
            image_capability = self.store.read(f"{P07}/capability-snapshot.json")["capabilities"]["image_generation"]
            if state['decisions'].get('asset_image_strategy') not in {'codex-native', 'use-provided-only'} and not self._can_execute_local_image_fixture(image_capability):
                required.append("storyboard_image_fallback")
            if image_capability["status"] in {"requires_account", "requires_payment"}:
                required.append("visual_external_action")
        if stage.id == "media_execution_or_fallback" and self.store.exists(f"{P11}/capability-snapshot.json"):
            capabilities = self.store.read(f"{P11}/capability-snapshot.json")["capabilities"]
            if any(
                capabilities[name]["status"] in {"requires_account", "requires_payment"}
                for name in ("video_generation",)
            ):
                required.append("video_external_action")
        if stage.id == "audio_edit_plan" and self.store.exists(f"{P11}/capability-snapshot.json"):
            capabilities = self.store.read(f"{P11}/capability-snapshot.json")["capabilities"]
            if state["decisions"].get("voice_strategy") == "tts" and capabilities["tts"]["status"] in {
                "requires_account",
                "requires_payment",
            }:
                required.append("audio_external_action")
        return list(dict.fromkeys(required))

    def _can_execute_local_image_fixture(self, capability: dict[str, Any]) -> bool:
        fixture = self.pipeline.environment.get("AI_COMIC_DRAMA_MEDIA_FIXTURE_DIR")
        return bool(
            not self.project.get("external_generation_blocked", True)
            and fixture
            and capability.get("status") == "available"
            and capability.get("provider") == "local-fixture"
        )

    @staticmethod
    def _unreadable_narrative_sources(registry: dict[str, Any]) -> list[dict[str, Any]]:
        readable_statuses = {"extracted", "extracted-with-replacement"}
        narrative_kinds = {"novel", "screenplay", "storyboard", "legacy-project"}
        return [
            source
            for source in registry.get("sources", [])
            if source.get("kind") in narrative_kinds
            and not source.get("excluded")
            and source.get("extraction_status") not in readable_statuses
        ]

    def _novel_chapters(self) -> list[dict[str, Any]]:
        registry = self.store.read(SOURCE_REGISTRY)
        chapters: list[dict[str, Any]] = []
        heading_pattern = re.compile(
            r"(?im)^(第[0-9一二三四五六七八九十百千万两零〇○]{1,12}章(?:[ \t　:：-]+[^\n]*)?|chapter\s+\d+(?:[ \t:：-]+[^\n]*)?)\s*$"
        )
        for source in registry["sources"]:
            if source.get("kind") != "novel" or not source.get("text_path"):
                continue
            text = self.store.path(source["text_path"]).read_text(encoding="utf-8")
            matches = list(heading_pattern.finditer(text))
            if not matches:
                chapters.append(
                    {
                        "source_id": source["source_id"],
                        "chapter_index": 1,
                        "title": "全文",
                        "text": text,
                    }
                )
                continue
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                chapters.append(
                    {
                        "source_id": source["source_id"],
                        "chapter_index": index + 1,
                        "title": match.group(1).strip(),
                        "text": text[match.start() : end].strip(),
                    }
                )
        return chapters

    def _ensure_source_batch_plan(self, state: dict[str, Any]) -> dict[str, Any] | None:
        chapters = self._novel_chapters()
        if len(chapters) <= 1:
            return None
        batch_size = int(state["decisions"]["chapter_batch_size"])
        source_hash = sha256_bytes(canonical_json(chapters).encode("utf-8"))
        relative = f"{P03}/source-batches.json"
        if self.store.exists(relative):
            existing = self.store.read(relative)
            if existing.get("batch_size") == batch_size and existing.get("source_hash") == source_hash:
                return existing
        batches = []
        for offset in range(0, len(chapters), batch_size):
            selected = chapters[offset : offset + batch_size]
            batch_index = len(batches) + 1
            batch_id = f"NOVEL-BATCH-{batch_index:03d}"
            text_path = f"runtime/source-batches/{batch_id}.txt"
            text = "\n\n".join(item["text"] for item in selected) + "\n"
            text_sha256 = self.store.write_text(text_path, text)
            batches.append(
                {
                    "batch_id": batch_id,
                    "index": batch_index,
                    "chapter_start": selected[0]["chapter_index"],
                    "chapter_end": selected[-1]["chapter_index"],
                    "chapter_titles": [item["title"] for item in selected],
                    "source_ids": sorted({item["source_id"] for item in selected}),
                    "text_path": text_path,
                    "text_sha256": text_sha256,
                }
            )
        plan = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "source-batch-plan",
            "artifact_id": stable_id("artifact", self.project["project_id"], "source-batch-plan"),
            "project_id": self.project["project_id"],
            "revision": self.store.revision_for(relative),
            "stage_id": "narrative_extract",
            "role_provenance": "kernel",
            "batch_size": batch_size,
            "recommendation": "2-4 chapters for short works; 5-8 chapters for long works",
            "source_hash": source_hash,
            "chapter_count": len(chapters),
            "batches": batches,
        }
        self.store.commit(relative, plan)
        return plan

    def _create_decision_request(
        self,
        stage: Stage,
        state: dict[str, Any],
        field_ids: list[str],
    ) -> dict[str, Any]:
        fields = decision_fields(field_ids)
        if state['decisions'].get('delivery_target') == 'dual-reference-previs':
            for field in fields:
                if field['id'] == 'storyboard_views':
                    field['question'] += ' 正式双图目标必须包含参考图；不自动替你勾选。'
                if field['id'] == 'asset_image_strategy':
                    for option in field['options']:
                        if option['id'] in {'prompt-only', 'generate-if-available'}:
                            option.update(availability='unavailable', reason='当前正式双图目标不能用草稿或测试图片替代；可显式导出草稿。')
        for field in fields:
            if field["id"] != "spatial_representation" or not self.store.exists(f"{P07}/capability-snapshot.json"):
                continue
            capability = self.store.read(f"{P07}/capability-snapshot.json")["capabilities"].get("true_3d", {})
            for option in field["options"]:
                if option["id"] == "verified-3d" and capability.get("status") == "available" and capability.get("executable"):
                    option["availability"] = "available"
                    option["reason"] = str(capability.get("evidence"))
        input_paths, _ = self._usable_inputs(stage, state)
        resources = list(stage.resources)
        context = self._context_fingerprint(stage, state, input_paths, resources)
        request_id = stable_id("decision", self.project["project_id"], stage.id, context, *field_ids)
        phase = self.graph.phase_for_stage(stage.id)
        relative = f"{phase.folder}/decisions/requests/{stage.id}-{request_id}.json"
        body = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "decision-request",
            "artifact_id": stable_id("artifact", self.project["project_id"], request_id),
            "project_id": self.project["project_id"],
            "revision": self.store.revision_for(relative),
            "stage_id": stage.id,
            "role_provenance": "kernel",
            "request_id": request_id,
            "status": "open",
            "fields": fields,
            "context_fingerprint": context,
            "impact": "The stage cannot continue until every field has an explicit selection.",
        }
        self.store.commit(relative, body)
        state["status"] = "awaiting_choice"
        state["current_stage"] = stage.id
        state["active_decision"] = relative
        state["active_task"] = None
        state["stage_status"][stage.id] = "awaiting_choice"
        self._save_state(state)
        self.store.rebuild_manifest()
        return self.status()

    def _planned_shots(self) -> list[dict[str, Any]]:
        if not self.store.exists(SHOT_PLAN):
            return []
        storyboard = self.store.read(SHOT_PLAN)
        return list(storyboard.get("shots", []))

    def _shot_batch(self) -> dict[str, Any]:
        planned = self._planned_shots()
        completed: set[str] = set()
        if self.store.exists(SHOT_TIMELINE_INDEX):
            index = self.store.read(SHOT_TIMELINE_INDEX)
            completed = {str(item["shot_id"]) for item in index.get("shots", [])}
        remaining = [item for item in planned if str(item["shot_id"]) not in completed]
        selected = remaining[: self.graph.max_shots_per_task]
        return {
            "batch_index": len(completed) // self.graph.max_shots_per_task + 1,
            "shot_ids": [str(item["shot_id"]) for item in selected],
            "start_index": selected[0]["index"] if selected else None,
            "end_index": selected[-1]["index"] if selected else None,
            "planned_count": len(planned),
            "completed_count": len(completed),
        }

    def _create_task(self, stage: Stage, state: dict[str, Any], media_job: dict | None = None) -> dict[str, Any]:
        input_paths, missing = self._usable_inputs(stage, state)
        if media_job and 'codex-imagegen' in media_job.get('allowed_providers', ['codex-imagegen', 'provided']):
            dispatched = int(state.get('native_image_dispatches', 0))
            budget = state['decisions'].get('image_job_budget')
            if budget == 'pause':
                state['status'], state['stage_status'][stage.id] = 'blocked', 'blocked'
                self._save_state(state)
                return self.status()
            if not isinstance(budget, int) or dispatched >= budget:
                state['decisions'].pop('image_job_budget', None)
                self._save_state(state)
                return self._create_decision_request(stage, state, ['image_job_budget'])
            state['native_image_dispatches'] = dispatched + 1
        if media_job:
            job_path = f"runtime/media-jobs/{media_job['input_hash']}.json"
            media_job = self._formal_artifact(stage, media_job, output_path=job_path, role='kernel')
            media_job['artifact_type'] = 'media-job'
            self.store.commit(job_path, media_job)
            input_paths.append(job_path)
        source_batch = None
        if stage.id == "narrative_extract":
            plan = self._ensure_source_batch_plan(state)
            if plan:
                completed = set(state.get("narrative_completed_batches", []))
                source_batch = next(
                    (item for item in plan["batches"] if item["batch_id"] not in completed),
                    None,
                )
                if source_batch is None:
                    raise WorkflowError("Narrative batch plan is complete but the stage is not committed")
                input_paths.extend([f"{P03}/source-batches.json", source_batch["text_path"]])
                input_paths = list(dict.fromkeys(input_paths))
        phase = self.graph.phase_for_stage(stage.id)
        resources = list(
            dict.fromkeys(
                [f"references/phases/{phase.id}.md", "references/artifact-contracts.md"]
                + list(stage.resources)
                + (["references/quality-gates.md"] if stage.kind == "review" else [])
            )
        )
        if media_job:
            resources.append('references/codex-imagegen.md')
        if state['decisions'].get('delivery_target') == 'dual-reference-previs' and stage.id in {'spatial_blocking', 'shot_timeline_specs'}:
            resources.append('references/blender-execution.md')
        if int(state.get("failure_counts", {}).get(stage.id, 0)) > 0 or self.project.get("work_depth") == "deep":
            resources.append("references/recovery.md")
            resources = list(dict.fromkeys(resources))
        shot_batch = self._shot_batch() if stage.kind == "semantic-batch" else None
        if stage.kind == "semantic-batch" and not shot_batch["shot_ids"]:
            raise WorkflowError("Storyboard contains no remaining planned shots")
        context = self._context_fingerprint(
            stage,
            state,
            input_paths,
            resources,
            shot_batch,
            source_batch,
        )
        attempt = int(state.get("failure_counts", {}).get(stage.id, 0)) + 1
        task_id = stable_id("task", self.project["project_id"], stage.id, context, attempt)
        relative = f"runtime/tasks/{stage.id}-{task_id}.json"
        schema_name = {
            "generation-segment-plan": "generation-segment-plan.schema.json",
            "shot-timeline-index": "shot-timeline-spec.schema.json",
            "scene-space-plan": "scene-space-plan.schema.json",
            "director-treatment": "director-treatment.schema.json",
            "asset-plan": "asset-plan.schema.json",
            "edit-plan": "edit-plan.schema.json",
        }.get(stage.artifact_type, "artifact.schema.json")
        task = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "task-envelope",
            "artifact_id": stable_id("artifact", self.project["project_id"], task_id),
            "project_id": self.project["project_id"],
            "revision": self.store.revision_for(relative),
            "stage_id": stage.id,
            "phase_id": phase.id,
            "phase_folder": phase.folder,
            "role_provenance": "kernel",
            "task_id": task_id,
            "context_fingerprint": context,
            "input_artifacts": input_paths,
            "loaded_resources": resources,
            "output_contract": {
                "path": stage.output,
                "artifact_type": stage.artifact_type,
                "schema": f"schemas/{schema_name}",
                "agent_result_schema": "schemas/agent-result.schema.json",
            },
            "constraints": {
                "revision_scope": state.get('revision_scope'),
                "missing_inputs": missing,
                "fact_priority": [
                    "current explicit user instruction or approval",
                    "approved downstream artifact within its responsibility",
                    "untouched source fact",
                    "labeled inference or adaptation addition",
                    "platform compromise that never writes back to canonical facts",
                ],
                "required_labels": ["inferred", "adaptation_addition", "platform_compromise"],
                "max_shots": self.graph.max_shots_per_task if stage.kind == "semantic-batch" else None,
                "entry_mode": self.project.get("entry_mode"),
            },
            "shot_batch": shot_batch,
            "source_batch": source_batch,
            "capability_snapshot": (
                f"{P11}/capability-snapshot.json"
                if self.store.exists(f"{P11}/capability-snapshot.json")
                else f"{P07}/capability-snapshot.json"
                if self.store.exists(f"{P07}/capability-snapshot.json")
                else None
            ),
        }
        if media_job:
            task['media_job'] = media_job
            task['output_contract']['schema'] = 'schemas/media-result.schema.json'
        self.store.commit(relative, task)
        state["status"] = "awaiting_agent_result"
        state["current_stage"] = stage.id
        state["active_task"] = relative
        state["active_decision"] = None
        state["stage_status"][stage.id] = "running"
        self._save_state(state)
        self.store.rebuild_manifest()
        return self.status()

    def _create_agent_decision_request(
        self,
        stage: Stage,
        state: dict[str, Any],
        task: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        proposal = result.get("artifact", {}).get("decision_request")
        if not isinstance(proposal, dict):
            for finding in result.get("findings", []):
                if isinstance(finding, dict) and isinstance(finding.get("decision_request"), dict):
                    proposal = finding["decision_request"]
                    break
        fields = proposal.get("fields") if isinstance(proposal, dict) else None
        if not isinstance(fields, list) or not fields:
            state["status"] = "blocked"
            state["stage_status"][stage.id] = "blocked"
            self._save_state(state)
            self.store.rebuild_manifest()
            return self.status()
        for field in fields:
            if not isinstance(field, dict) or not field.get("id") or not field.get("question"):
                raise WorkflowError("Agent-proposed decision fields require id and question")
            options = field.get("options")
            if not isinstance(options, list) or len(options) < 2 or any(
                not isinstance(option, dict) or "id" not in option for option in options
            ):
                raise WorkflowError("Agent-proposed decisions require at least two options with IDs")
            field.setdefault("allow_custom", False)
            field.setdefault("selection_mode", "single")
            field.setdefault("min_selections", 1)
            if field["selection_mode"] == "multi":
                field.setdefault("max_selections", len(options))
            for index, option in enumerate(options):
                option.setdefault("label", str(option["id"]))
                option.setdefault("availability", "available")
                option.setdefault("recommended", index == 0)
                option.setdefault("consequence", "This choice affects the current stage dependency closure.")
        request_id = stable_id(
            "decision",
            self.project["project_id"],
            stage.id,
            task["context_fingerprint"],
            canonical_json(fields),
        )
        phase = self.graph.phase_for_stage(stage.id)
        relative = f"{phase.folder}/decisions/requests/{stage.id}-{request_id}.json"
        request = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "decision-request",
            "artifact_id": stable_id("artifact", self.project["project_id"], request_id),
            "project_id": self.project["project_id"],
            "revision": self.store.revision_for(relative),
            "stage_id": stage.id,
            "role_provenance": "kernel",
            "request_id": request_id,
            "status": "open",
            "fields": fields,
            "context_fingerprint": task["context_fingerprint"],
            "agent_result_id": result["result_id"],
            "impact": proposal.get("impact") if isinstance(proposal, dict) else None,
        }
        self.store.commit(relative, request)
        state["status"] = "awaiting_choice"
        state["stage_status"][stage.id] = "awaiting_choice"
        state["active_task"] = None
        state["active_decision"] = relative
        state["current_stage"] = stage.id
        self._save_state(state)
        self.store.rebuild_manifest()
        return self.status()

    def _first_drifted_stage(self, state: dict[str, Any]) -> str | None:
        if not self.store.exists("manifest.json"):
            return None
        manifest_entries = {
            str(item["path"]): str(item["sha256"])
            for item in self.store.read("manifest.json").get("files", [])
        }
        skipped = set(state.get("skipped_stages", []))
        for stage in self.graph.stages:
            if stage.id in skipped or state["stage_status"].get(stage.id) != "complete":
                continue
            relative = (
                "project.json"
                if stage.id == "project_setup"
                else SOURCE_REGISTRY
                if stage.id == "source_ingest"
                else stage.output
            )
            if not relative:
                continue
            restart_stage = (
                "intake_normalize"
                if stage.id in {"project_setup", "source_ingest"}
                else stage.id
            )
            if not self.store.exists(relative):
                if stage.id == "source_ingest":
                    raise WorkflowError(f"{SOURCE_REGISTRY} is missing; reinitialize or restore it before resume")
                return restart_stage
            recorded = manifest_entries.get(relative)
            if recorded is None or sha256_file(self.store.path(relative)) != recorded:
                return restart_stage
            if stage.id in {'asset_generation_or_prompt', 'storyboard_reference_generation_or_prompt'}:
                registry = self.store.read(relative)
                for item in registry.get('assets', registry.get('references', [])):
                    media_path = item.get('media_path') or item.get('path')
                    if media_path and (not self.store.exists(media_path) or sha256_file(self.store.path(media_path)) != item.get('sha256')):
                        return restart_stage
        return None

    @project_transaction
    def run(self) -> dict[str, Any]:
        if self._legacy_v1:
            return self._migration_status()
        state = self.state
        drifted_stage = self._first_drifted_stage(state)
        if drifted_stage:
            return self.invalidate_from(drifted_stage)
        if state["status"] in {"awaiting_choice", "awaiting_agent_result", "blocked", "complete"}:
            return self.status()
        while True:
            stage = self.graph.first_incomplete(state["stage_status"], state.get("skipped_stages", []))
            if stage is None:
                state["status"] = "complete"
                state["current_stage"] = None
                state["active_task"] = None
                state["active_decision"] = None
                self._save_state(state)
                self.store.rebuild_manifest()
                return self.status()
            state["current_stage"] = stage.id
            state["status"] = "running"
            state["stage_status"][stage.id] = "running"
            self._save_state(state)
            state = self.state
            required = self._dynamic_required_decisions(stage, state)
            missing = [field_id for field_id in required if field_id not in state["decisions"]]
            if missing:
                return self._create_decision_request(stage, state, missing)
            if stage.kind in {"semantic", "semantic-batch", "review"}:
                return self._create_task(stage, state)
            try:
                with self.store.transaction(savepoint=True):
                    body = self.pipeline.execute(stage.id, self.project, state)
                    if stage.id == "export":
                        body = self._prepare_export_bundle(stage, body)
                    self._commit_stage_output(stage, body)
            except Exception as error:
                from .media_bridge import HostMediaRequired
                if isinstance(error, HostMediaRequired):
                    return self._create_task(stage, state, error.job)
                from .references import ReferenceCapacityError
                if isinstance(error, ReferenceCapacityError):
                    return self._create_decision_request(stage, state, ['reference_overflow_action'])
                from .blender_adapter import BlenderUnavailable
                if isinstance(error, BlenderUnavailable):
                    state['capability_failure'] = str(error)
                    self._save_state(state)
                    return self._create_decision_request(stage, state, ['spatial_execution_fallback'])
                return self._record_deterministic_failure(stage, state, error)
            state["stage_status"][stage.id] = "complete"
            state["current_stage"] = None
            state["failure_counts"][stage.id] = 0
            self._save_state(state)
            self.store.rebuild_manifest()
            state = self.state
            if stage.id == "export":
                state["status"] = "complete"
                state["current_stage"] = None
                self._save_state(state)
                self.store.rebuild_manifest()
                package = build_delivery_archive(self.store)
                result = self.status()
                result["delivery_package"] = package
                return result

    def _record_deterministic_failure(
        self, stage: Stage, state: dict[str, Any], error: Exception
    ) -> dict[str, Any]:
        count = int(state["failure_counts"].get(stage.id, 0)) + 1
        state["failure_counts"][stage.id] = count
        relative = f"runtime/failures/{stage.id}-{count}.json"
        body = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "failure-record",
            "artifact_id": stable_id("failure", self.project["project_id"], stage.id, count),
            "project_id": self.project["project_id"],
            "revision": 1,
            "stage_id": stage.id,
            "role_provenance": "kernel",
            "failure_count": count,
            "error_type": type(error).__name__,
            "message": str(error),
            "retry_scope": stage.id,
        }
        self.store.commit(relative, body)
        if count >= 4:
            state["status"] = "blocked"
            state["stage_status"][stage.id] = "failed"
        else:
            state["status"] = "running"
            state["stage_status"][stage.id] = "failed"
        self._save_state(state)
        self.store.rebuild_manifest()
        return self.status()

    @project_transaction
    def resume(self, decision: Path | str | dict[str, Any]) -> dict[str, Any]:
        if self._legacy_v1:
            return self._resume_migration(decision)
        state = self.state
        if state["status"] != "awaiting_choice" or not state.get("active_decision"):
            raise WorkflowError("No active decision request")
        payload = read_json(Path(decision)) if isinstance(decision, (str, Path)) else deepcopy(decision)
        request = self.store.read(state["active_decision"])
        if payload.get("request_id") != request["request_id"]:
            raise StaleContextError("Decision request ID does not match the active request")
        if payload.get("context_fingerprint", request["context_fingerprint"]) != request["context_fingerprint"]:
            raise StaleContextError("Decision context is stale")
        selections = payload.get("selections")
        if not isinstance(selections, dict):
            raise WorkflowError("Decision file must contain a selections object")
        expected = {field["id"] for field in request["fields"]}
        if set(selections) != expected:
            raise WorkflowError(f"Selections must contain exactly: {sorted(expected)}")
        for field in request["fields"]:
            validate_decision(field, selections[field["id"]])
        if (state['decisions'].get('delivery_target') == 'dual-reference-previs'
                and 'storyboard_views' in selections and 'reference-images' not in selections['storyboard_views']):
            raise WorkflowError('Formal dual-reference target requires the reference-images view; explicitly select it or export a draft')
        if state['decisions'].get('delivery_target') == 'dual-reference-previs':
            if selections.get('asset_review_decision') == 'approve':
                from .pipeline import inspect_image
                for asset in self.store.read(ASSET_REGISTRY)['assets']:
                    path = asset.get('media_path')
                    if (not path or not self.store.exists(path) or sha256_file(self.store.path(path)) != asset.get('sha256')
                            or not inspect_image(self.store.path(path))['verified']):
                        raise WorkflowError('Formal asset approval requires actual current images for every planned asset')
            if selections.get('storyboard_review_decision') == 'approve':
                from .references import dual_bindings, ReferenceCapacityError
                try:
                    for shot in self.store.read(SHOT_TIMELINE_INDEX)['shots']:
                        dual_bindings(self.store, self.store.read(shot['path']), state, require_storyboard_approval=False)
                except ReferenceCapacityError:
                    return self._create_decision_request(self.graph.get(request['stage_id']), state, ['reference_overflow_action'])
        stage = self.graph.get(request["stage_id"])
        phase = self.graph.phase_for_stage(stage.id)
        approval_relative = f"{phase.folder}/decisions/approvals/{request['request_id']}.json"
        approval = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "approval-record",
            "artifact_id": stable_id("artifact", self.project["project_id"], "approval", request["request_id"]),
            "project_id": self.project["project_id"],
            "revision": self.store.revision_for(approval_relative),
            "stage_id": stage.id,
            "role_provenance": "kernel",
            "approval_id": stable_id("approval", request["request_id"], canonical_json(selections)),
            "request_id": request["request_id"],
            "selections": selections,
            "context_fingerprint": request["context_fingerprint"],
            "impact_scope": [stage.id] + [item.id for item in self.graph.downstream(stage.id)],
            "approved_inputs": [{"path": path, "sha256": sha256_file(self.store.path(path))}
                                for path in stage.inputs if self.store.exists(path)],
        }
        self.store.commit(approval_relative, approval)
        resolved = deepcopy(request)
        resolved["revision"] = self.store.revision_for(state["active_decision"])
        resolved["status"] = "resolved"
        resolved["resolution_ref"] = approval_relative
        self.store.commit(state["active_decision"], resolved)
        state["decisions"].update(selections)
        for field_id in selections:
            state.setdefault("decision_approvals", {})[field_id] = approval_relative
            state.setdefault("decision_stages", {})[field_id] = stage.id
        state["active_decision"] = None
        state["status"] = "running"
        state["stage_status"][stage.id] = "pending"
        project = self.project
        project["selected_config"].update(selections)
        if "work_depth" in selections:
            project["work_depth"] = selections["work_depth"]
        if "adaptation_policy" in selections:
            project["adaptation_policy"] = selections["adaptation_policy"]
        if "rights_status" in selections:
            project["external_generation_blocked"] = selections["rights_status"] == "unverified-prompt-only"
            registry = self.store.read(SOURCE_REGISTRY)
            registry["revision"] = self.store.revision_for(SOURCE_REGISTRY)
            for source in registry["sources"]:
                source["rights_status"] = selections["rights_status"]
            self.store.commit(SOURCE_REGISTRY, registry)
        if selections.get("likeness_authorization") in {"prompt-only", "exclude-likeness"}:
            project["external_generation_blocked"] = True
        if selections.get("unreadable_source_action") == "exclude-unreadable":
            registry = self.store.read(SOURCE_REGISTRY)
            for source in self._unreadable_narrative_sources(registry):
                source["excluded"] = True
                source["authority"] = "advisory"
                source["exclusion_reason"] = "explicit user decision"
            registry["revision"] = self.store.revision_for(SOURCE_REGISTRY)
            self.store.commit(SOURCE_REGISTRY, registry)
            readable = [
                source
                for source in registry["sources"]
                if source.get("kind") in {"novel", "screenplay", "storyboard", "legacy-project"}
                and not source.get("excluded")
                and source.get("extraction_status") in {"extracted", "extracted-with-replacement"}
            ]
            if not readable:
                state["status"] = "blocked"
                state["stage_status"][stage.id] = "blocked"
        if selections.get("unreadable_source_action") == "pause-and-supply-text":
            state["status"] = "blocked"
            state["stage_status"][stage.id] = "blocked"
        if selections.get('reference_overflow_action'):
            state['status'], state['stage_status'][stage.id] = 'blocked', 'blocked'
        if selections.get('spatial_execution_fallback'):
            state['status'], state['stage_status'][stage.id] = 'blocked', 'blocked'
        fallback_pause = {
            selections.get("asset_image_fallback"),
            selections.get("storyboard_image_fallback"),
            selections.get('platform_reference_action'),
        } & {"supply-capability", "pause"}
        if fallback_pause:
            state["status"] = "blocked"
            state["stage_status"][stage.id] = "blocked"
        self._save_project(project)
        revision_target = {
            "asset_review_decision": "visual_bible",
            "spatial_review_decision": "spatial_blocking",
            "storyboard_review_decision": "storyboard_plan",
        }
        for field_id, restart_stage in revision_target.items():
            if selections.get(field_id) == "revise":
                self._save_state(state)
                self.store.rebuild_manifest()
                return self.invalidate_from(restart_stage)
        if selections.get("core_conflict_resolution") == "pause" or state["status"] == "blocked":
            state["status"] = "blocked"
            state["stage_status"][stage.id] = "blocked"
            self._save_state(state)
            self.store.rebuild_manifest()
            return self.status()
        self._save_state(state)
        self.store.rebuild_manifest()
        return self.run()

    def _normalize_segment_plan(self, artifact: dict[str, Any]) -> dict[str, Any]:
        decision_duration = float(self.state["decisions"]["segment_duration_s"])
        artifact.setdefault("target_duration_s", decision_duration)
        segments = artifact.get("segments")
        if not isinstance(segments, list) or not segments:
            raise WorkflowError("Generation segment plan must contain at least one segment")
        for index, segment in enumerate(segments, start=1):
            segment.setdefault("segment_id", f"SEG-{index:03d}")
            segment["index"] = index
            segment.setdefault("target_duration_s", decision_duration)
            segment.setdefault("source_refs", [])
        return artifact

    def _normalize_shot_plan(self, artifact: dict[str, Any]) -> dict[str, Any]:
        segment_plan = (
            self.store.read(GENERATION_SEGMENTS)
            if self.store.exists(GENERATION_SEGMENTS)
            else {"segments": []}
        )
        planned_segments = list(segment_plan.get("segments", []))
        raw_shots = artifact.get("shots")
        if not isinstance(raw_shots, list) or not raw_shots:
            if not self.store.exists(GENERATION_SEGMENTS):
                raise WorkflowError("Shot plan must contain planned shots")
            raw_shots = [
                {
                    "segment_id": segment["segment_id"],
                    "duration_s": segment["target_duration_s"],
                    "narrative_purpose": "unknown; expert detail required in ShotSpec",
                }
                for segment in self.store.read(GENERATION_SEGMENTS)["segments"]
            ]
        normalized: list[dict[str, Any]] = []
        next_index = 1
        for source_index, raw in enumerate(raw_shots, start=1):
            if not isinstance(raw, dict):
                raise WorkflowError("Every planned shot must be an object")
            duration = float(raw.get("duration_s", 0))
            if duration <= 0:
                raise WorkflowError("Every storyboard shot requires a positive duration_s")
            pieces = max(1, math.ceil(duration / 12))
            piece_duration = duration / pieces
            base_id = str(raw.get("shot_id") or f"SHOT-{source_index:03d}")
            segment_id = raw.get("segment_id")
            if not segment_id and source_index <= len(planned_segments):
                segment_id = planned_segments[source_index - 1]["segment_id"]
            for piece in range(1, pieces + 1):
                shot = deepcopy(raw)
                shot["shot_id"] = base_id if pieces == 1 else f"{base_id}-{piece}"
                shot["index"] = next_index
                shot["duration_s"] = round(piece_duration, 3)
                shot["split_from_long_segment"] = pieces > 1
                shot["segment_id"] = segment_id or "SEG-UNMAPPED"
                normalized.append(shot)
                next_index += 1
        ids = [shot["shot_id"] for shot in normalized]
        if len(set(ids)) != len(ids):
            raise WorkflowError("Shot plan IDs must be unique")
        artifact["shots"] = normalized
        artifact["shot_count"] = len(normalized)
        artifact["generation_segments"] = [
            {
                "segment_id": segment["segment_id"],
                "target_duration_s": segment["target_duration_s"],
                "shot_ids": [
                    shot["shot_id"]
                    for shot in normalized
                    if shot.get("segment_id") == segment["segment_id"]
                ],
                "actual_duration_s": round(
                    sum(
                        float(shot["duration_s"])
                        for shot in normalized
                        if shot.get("segment_id") == segment["segment_id"]
                    ),
                    3,
                ),
            }
            for segment in planned_segments
        ]
        return artifact

    @staticmethod
    def _timed_event_start(event: dict[str, Any], duration: float, label: str) -> float:
        if event.get("time_mode") == "full_shot" or event.get('full_shot') is True:
            if "start_s" in event or "end_s" in event or "time_s" in event:
                raise WorkflowError(f"{label} full_shot events must not duplicate timecodes")
            return 0.0
        if "time_s" in event:
            time_s = float(event["time_s"])
            if not 0 <= time_s <= duration:
                raise WorkflowError(f"{label} time_s must be within the shot duration")
            return time_s
        if "start_s" not in event or "end_s" not in event:
            raise WorkflowError(f"{label} requires start_s/end_s, time_s, or time_mode=full_shot")
        start_s = float(event["start_s"])
        end_s = float(event["end_s"])
        if not 0 <= start_s <= end_s <= duration:
            raise WorkflowError(f"{label} interval must be ordered and within the shot duration")
        return start_s

    def _validate_shot_timeline_semantics(
        self,
        shot: dict[str, Any],
        committed_entries: list[dict[str, Any]],
    ) -> None:
        from .timing import validate_timing
        validate_timing(shot)
        duration = float(shot.get("duration_s", 0))
        if not 1 <= duration <= 12:
            raise WorkflowError("ShotTimelineSpec duration must be 1-12 seconds")
        scene_space = self.store.read(SCENE_SPACE_PLAN)
        scene_by_id = {str(item.get("scene_id")): item for item in scene_space.get("scenes", [])}
        scene_id = str(shot.get("scene_id", ""))
        if scene_id not in scene_by_id:
            raise WorkflowError(f"ShotTimelineSpec references unknown scene_id {scene_id!r}")
        asset_ids = {
            str(item.get("asset_id"))
            for item in self.store.read(ASSET_REGISTRY).get("assets", [])
            if item.get("asset_id")
        }
        required_assets = [str(item) for item in shot.get("required_asset_ids", [])]
        unknown_assets = sorted(set(required_assets) - asset_ids)
        if unknown_assets:
            raise WorkflowError(f"ShotTimelineSpec references unknown required assets: {unknown_assets}")
        selected_refs = [str(item) for item in shot.get("selected_reference_ids", [])]
        if len(selected_refs) > 5:
            raise WorkflowError("ShotTimelineSpec may select at most five upload references")
        source_ids = {
            str(item.get("source_id"))
            for item in self.store.read(SOURCE_REGISTRY).get("sources", [])
            if item.get("source_id")
        }
        unknown_selected = sorted(set(selected_refs) - asset_ids - source_ids)
        if unknown_selected:
            raise WorkflowError(f"ShotTimelineSpec selects unknown references: {unknown_selected}")

        scene = scene_by_id[scene_id]
        from .spatial import validate_spatial_timeline
        spatial_errors = validate_spatial_timeline(scene, shot)
        if spatial_errors:
            raise WorkflowError(canonical_json(spatial_errors))
        placed_characters = {
            str(item.get("character_id"))
            for item in scene.get("character_placements", [])
            if item.get("character_id")
        }
        track_ids: set[str] = set()
        for track in shot.get("character_tracks", []):
            character_id = str(track.get("character_id", ""))
            if not character_id or character_id in track_ids:
                raise WorkflowError("Character tracks require unique non-empty character_id values")
            track_ids.add(character_id)
            if character_id not in placed_characters:
                raise WorkflowError(
                    f"Character {character_id!r} has no placement in SceneSpace {scene_id!r}"
                )
            visible = track.get("visible_interval", {})
            try:
                visible_start = float(visible["start_s"])
                visible_end = float(visible["end_s"])
            except (KeyError, TypeError, ValueError) as error:
                raise WorkflowError("visible_interval requires numeric start_s and end_s") from error
            if not 0 <= visible_start <= visible_end <= duration:
                raise WorkflowError("visible_interval must be ordered and within the shot duration")
            trajectory = track.get("trajectory", [])
            trajectory_times = [float(item.get("time_s", -1)) for item in trajectory]
            if not trajectory_times or trajectory_times != sorted(trajectory_times):
                raise WorkflowError("Trajectory keyframes must be present and ordered by time_s")
            if any(time_s < 0 or time_s > duration for time_s in trajectory_times):
                raise WorkflowError("Trajectory keyframes must stay inside the shot, including offscreen state")
            for key in ("action_events", "emotion_events"):
                events = track.get(key, [])
                starts = [
                    self._timed_event_start(item, duration, f"{character_id}.{key}")
                    for item in events
                ]
                if starts != sorted(starts):
                    raise WorkflowError(f"{character_id}.{key} must be ordered by time")
        for key in ("camera_track", "audio_track", "director_track", "spatial_track", "scene_fixed_track"):
            events = shot.get(key, [])
            starts = [self._timed_event_start(item, duration, key) for item in events]
            if starts != sorted(starts):
                raise WorkflowError(f"{key} must be ordered by time")

        predecessors = [e for e in committed_entries if int(e['index']) < int(shot['index'])]
        if predecessors:
            previous_entry = max(predecessors, key=lambda item: int(item["index"]))
            if int(previous_entry["index"]) + 1 == int(shot["index"]):
                previous = previous_entry.get("_artifact") or self.store.read(str(previous_entry["path"]))
                previous_end = previous.get("continuity", {}).get("end_state")
                current_start = shot.get("continuity", {}).get("start_state")
                same_scene = previous.get("scene_id") == shot.get("scene_id")
                explicit = shot.get('continuity', {}).get('transition', {})
                transition = explicit.get('type') in {'time_jump', 'scene_change'}
                if transition:
                    from .references import current_approval
                    if not explicit.get('reason'):
                        raise WorkflowError('A time jump or scene change needs a narrative reason')
                    current_approval(self.store, explicit.get('approval_ref'))
                if not explicit and self.state['decisions'].get('delivery_target') == 'prompt-draft':
                    transition = shot.get('continuity', {}).get('transition_from_previous')
                if same_scene and not transition and canonical_json(previous_end) != canonical_json(current_start):
                    raise WorkflowError(
                        f"Continuity handoff mismatch from {previous['shot_id']} to {shot['shot_id']}"
                    )

    def _commit_shot_batch(
        self,
        stage: Stage,
        task: dict[str, Any],
        artifact: dict[str, Any],
        result: dict[str, Any],
    ) -> bool:
        shots = artifact.get("shots")
        if not isinstance(shots, list):
            raise WorkflowError("ShotSpec AgentResult artifact must contain a shots array")
        expected = list(task["shot_batch"]["shot_ids"])
        received = [str(shot.get("shot_id")) for shot in shots if isinstance(shot, dict)]
        if received != expected:
            raise WorkflowError(f"Shot batch must contain exactly {expected!r} in order")
        index_entries: list[dict[str, Any]] = []
        if self.store.exists(SHOT_TIMELINE_INDEX):
            index_entries = list(self.store.read(SHOT_TIMELINE_INDEX).get("shots", []))
        prepared: list[tuple[str, dict[str, Any]]] = []
        for shot in shots:
            from .timing import normalize_timing
            shot = normalize_timing(shot)
            planned = next(item for item in self._planned_shots() if item["shot_id"] == shot["shot_id"])
            relative = f"{P09}/shots/{shot['shot_id']}.json"
            formal = deepcopy(shot)
            formal.update(
                {
                    "schema_version": SCHEMA_VERSION,
                    "artifact_type": "shot-timeline-spec",
                    "artifact_id": stable_id("artifact", self.project["project_id"], shot["shot_id"]),
                    "project_id": self.project["project_id"],
                    "revision": self.store.revision_for(relative),
                    "stage_id": "shot_timeline_specs",
                    "role_provenance": "storyboard",
                    "shot_id": shot["shot_id"],
                    "index": planned["index"],
                    "duration_s": planned["duration_s"],
                    "provenance": result.get("provenance", []),
                }
            )
            validate_artifact(formal)
            self._validate_shot_timeline_semantics(formal, index_entries)
            prepared.append((relative, formal))
            index_entries.append(
                {
                    "shot_id": formal["shot_id"],
                    "index": formal["index"],
                    "duration_s": formal["duration_s"],
                    "path": relative,
                    "sha256": sha256_bytes(canonical_json(formal).encode("utf-8")),
                    "_artifact": formal,
                }
            )
        for relative, formal in prepared:
            self.store.commit(relative, formal)
        for entry in index_entries:
            entry.pop("_artifact", None)
        index_entries.sort(key=lambda item: item["index"])
        index_stage = self.graph.get("shot_timeline_specs")
        index_artifact = self._formal_artifact(
            index_stage,
            {
                "shots": index_entries,
                "shot_count": len(index_entries),
                "planned_count": len(self._planned_shots()),
                "last_batch": task["shot_batch"],
            },
        )
        self.store.commit(SHOT_TIMELINE_INDEX, index_artifact)
        self._update_dynamic_memory(shots, result)
        return len(index_entries) == len(self._planned_shots())

    def _update_dynamic_memory(self, shots: list[dict[str, Any]], result: dict[str, Any]) -> None:
        relative = DYNAMIC_MEMORY
        previous = self.store.read(relative) if self.store.exists(relative) else {}
        incoming_ids = {shot["shot_id"] for shot in shots}
        updates = [item for item in previous.get("shot_updates", []) if item.get("shot_id") not in incoming_ids]
        for shot in shots:
            updates.append(
                {
                    "shot_id": shot["shot_id"],
                    "character_tracks": shot.get("character_tracks", []),
                    "environment": shot.get("environment", {}),
                    "continuity": shot.get("continuity", {}),
                    "audio_track": shot.get("audio_track", []),
                }
            )
        memory = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "dynamic-memory",
            "artifact_id": stable_id("artifact", self.project["project_id"], "dynamic-memory"),
            "project_id": self.project["project_id"],
            "revision": self.store.revision_for(relative),
            "stage_id": "shot_timeline_specs",
            "role_provenance": "kernel",
            "shot_updates": updates,
            "latest_expert_update": result.get("artifact", {}).get("memory_update", {}),
            "tracked_fields": [
                "character state",
                "relationships",
                "location",
                "wardrobe",
                "injuries",
                "props",
                "unresolved crises",
                "next hook",
            ],
        }
        self.store.commit(relative, memory)

    def _commit_narrative_batch(
        self,
        stage: Stage,
        task: dict[str, Any],
        artifact: dict[str, Any],
        result: dict[str, Any],
        state: dict[str, Any],
    ) -> bool:
        batch = task["source_batch"]
        batch_id = batch["batch_id"]
        relative = f"{P03}/narrative-batches/{batch_id}.json"
        formal = deepcopy(artifact)
        formal.update(
            {
                "schema_version": SCHEMA_VERSION,
                "artifact_type": "narrative-batch",
                "artifact_id": stable_id("artifact", self.project["project_id"], batch_id),
                "project_id": self.project["project_id"],
                "revision": self.store.revision_for(relative),
                "stage_id": stage.id,
                "role_provenance": stage.role,
                "batch_id": batch_id,
                "chapter_start": batch["chapter_start"],
                "chapter_end": batch["chapter_end"],
                "provenance": result.get("provenance", []),
                "agent_findings": result.get("findings", []),
            }
        )
        self.store.commit(relative, formal)
        completed = list(state.get("narrative_completed_batches", []))
        if batch_id not in completed:
            completed.append(batch_id)
        state["narrative_completed_batches"] = completed
        self._update_narrative_memory(batch_id, formal)
        plan = self.store.read(f"{P03}/source-batches.json")
        if len(completed) < len(plan["batches"]):
            return False
        batch_refs = []
        aggregate_fields = {
            "facts": [],
            "characters": [],
            "locations": [],
            "relationships": [],
            "world_rules": [],
            "open_threads": [],
            "adaptation_additions": [],
            "unknowns": [],
        }
        seen = {key: set() for key in aggregate_fields}
        for planned in plan["batches"]:
            batch_path = f"{P03}/narrative-batches/{planned['batch_id']}.json"
            value = self.store.read(batch_path)
            batch_refs.append({"batch_id": planned["batch_id"], "path": batch_path, "sha256": sha256_file(self.store.path(batch_path))})
            for key in aggregate_fields:
                for item in value.get(key, []):
                    identity = canonical_json(item)
                    if identity not in seen[key]:
                        aggregate_fields[key].append(item)
                        seen[key].add(identity)
        bundle = {
            **aggregate_fields,
            "batch_refs": batch_refs,
            "batch_count": len(batch_refs),
            "dynamic_memory_ref": f"{P03}/narrative-memory.json",
            "provenance": result.get("provenance", []),
        }
        self._commit_stage_output(stage, bundle)
        return True

    def _update_narrative_memory(self, batch_id: str, artifact: dict[str, Any]) -> None:
        relative = f"{P03}/narrative-memory.json"
        previous = self.store.read(relative) if self.store.exists(relative) else {}
        updates = list(previous.get("batch_updates", []))
        updates.append(
            {
                "batch_id": batch_id,
                "characters": artifact.get("characters", []),
                "relationships": artifact.get("relationships", []),
                "locations": artifact.get("locations", []),
                "wardrobe": artifact.get("wardrobe", []),
                "injuries": artifact.get("injuries", []),
                "props": artifact.get("props", []),
                "open_threads": artifact.get("open_threads", []),
                "next_hook": artifact.get("next_hook"),
            }
        )
        memory = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "dynamic-memory",
            "artifact_id": stable_id("artifact", self.project["project_id"], "narrative-memory"),
            "project_id": self.project["project_id"],
            "revision": self.store.revision_for(relative),
            "stage_id": "narrative_extract",
            "role_provenance": "kernel",
            "batch_updates": updates,
            "latest_batch_id": batch_id,
        }
        self.store.commit(relative, memory)

    @project_transaction
    def submit(self, result: Path | str | dict[str, Any]) -> dict[str, Any]:
        state = self.state
        if state["status"] not in {"awaiting_agent_result", "blocked"} or not state.get("active_task"):
            raise WorkflowError("No active TaskEnvelope")
        payload = read_json(Path(result)) if isinstance(result, (str, Path)) else deepcopy(result)
        validate(payload, load_schema("agent-result.schema.json"))
        task = self.store.read(state["active_task"])
        stage = self.graph.get(task["stage_id"])
        if payload["project_id"] != self.project["project_id"] or payload["stage_id"] != stage.id:
            raise StaleContextError("AgentResult targets a different project or stage")
        input_paths = list(task["input_artifacts"])
        current_context = self._context_fingerprint(
            stage,
            state,
            input_paths,
            list(task["loaded_resources"]),
            task.get("shot_batch"),
            task.get("source_batch"),
        )
        if current_context != task["context_fingerprint"] or payload["context_fingerprint"] != current_context:
            raise StaleContextError("Task inputs, decisions, resources, or batch changed; result is stale")
        result_relative = f"runtime/results/{stage.id}-{payload['result_id']}.json"
        self.store.write_text(result_relative, canonical_json(payload))
        if payload["status"] == "failed":
            return self._record_agent_failure(stage, state, payload)
        if payload["status"] == "needs_decision":
            return self._create_agent_decision_request(stage, state, task, payload)
        if any(f.get('severity') in {'critical', 'blocking'} and f.get('resolved') is not True
               for f in payload.get('findings', []) if isinstance(f, dict)):
            return self._create_agent_decision_request(stage, state, task, payload)
        if stage.kind == "review" and payload["status"] != "approved":
            raise WorkflowError("A review stage must return status='approved' before commit")
        artifact = deepcopy(payload["artifact"])
        scope = state.get('revision_scope', {})
        if scope.get('stage_id') == stage.id and stage.output and self.store.exists(stage.output):
            field, identity, target = ('assets', 'asset_id', scope.get('asset_id')) if stage.id == 'asset_plan' else ('scenes', 'scene_id', scope.get('scene_id'))
            if target:
                previous = {item[identity]: item for item in self.store.read(stage.output).get(field, []) if item[identity] != target}
                proposed = {item[identity]: item for item in artifact.get(field, []) if item[identity] != target}
                if previous != proposed:
                    raise WorkflowError('Scoped revision changed unrelated entities; submit only the authorized change')
        if task.get('media_job'):
            from .media_bridge import import_candidate
            receipt = import_candidate(self.store, task['media_job'], artifact)
            receipt_path = task['media_job']['receipt_path']
            receipt = self._formal_artifact(stage, receipt, output_path=receipt_path, role='kernel')
            receipt['artifact_type'] = 'media-result'
            self.store.commit(receipt_path, receipt)
            state['stage_status'][stage.id] = 'pending'
            state['status'], state['active_task'] = 'running', None
            self._save_state(state)
            self.store.rebuild_manifest()
            return self.run()
        if stage.id == "segment_plan":
            artifact = self._normalize_segment_plan(artifact)
        if stage.id == "spatial_blocking":
            artifact["representation"] = state["decisions"]["spatial_representation"]
        if stage.id == "storyboard_plan":
            artifact = self._normalize_shot_plan(artifact)
        if stage.id == 'audio_edit_plan' and state['decisions'].get('voice_strategy') != 'no-dialogue':
            lines = {line.get('text') for line in artifact.get('dialogue_table', [])}
            for entry in self.store.read(SHOT_TIMELINE_INDEX)['shots']:
                for event in self.store.read(entry['path']).get('audio_track', []):
                    if event.get('kind') == 'dialogue' and event.get('text') and event['text'] not in lines:
                        raise WorkflowError('Edit Plan loses approved dialogue; use dialogue_table with speaker and time')
        if stage.id == "narrative_extract" and task.get("source_batch"):
            complete = self._commit_narrative_batch(stage, task, artifact, payload, state)
            state["stage_status"][stage.id] = "complete" if complete else "pending"
        elif stage.id == "shot_timeline_specs":
            complete = self._commit_shot_batch(stage, task, artifact, payload)
            state["stage_status"][stage.id] = "complete" if complete else "pending"
        else:
            artifact["provenance"] = payload.get("provenance", [])
            artifact["agent_findings"] = payload.get("findings", [])
            artifact["agent_result_id"] = payload["result_id"]
            self._commit_stage_output(stage, artifact)
            state["stage_status"][stage.id] = "complete"
        state["status"] = "running"
        state["current_stage"] = None
        state["active_task"] = None
        state["failure_counts"][stage.id] = 0
        self._save_state(state)
        self.store.rebuild_manifest()
        return self.run()

    def _record_agent_failure(
        self, stage: Stage, state: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]:
        count = int(state["failure_counts"].get(stage.id, 0)) + 1
        state["failure_counts"][stage.id] = count
        relative = f"runtime/failures/{stage.id}-{count}.json"
        failure = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "failure-record",
            "artifact_id": stable_id("failure", self.project["project_id"], stage.id, count),
            "project_id": self.project["project_id"],
            "revision": 1,
            "stage_id": stage.id,
            "role_provenance": stage.role,
            "failure_count": count,
            "agent_result_id": result["result_id"],
            "findings": result.get("findings", []),
            "retry_scope": "minimum related stage",
        }
        self.store.commit(relative, failure)
        state["active_task"] = None
        state["stage_status"][stage.id] = "failed"
        state["status"] = "blocked" if count >= 4 else "running"
        self._save_state(state)
        self.store.rebuild_manifest()
        return self.status() if count >= 4 else self.run()

    @project_transaction
    def invalidate_from(self, stage_id: str, *, shot_id: str | None = None,
                        scene_id: str | None = None, asset_id: str | None = None) -> dict[str, Any]:
        state = self.state
        self.graph.get(stage_id)
        if sum(bool(x) for x in (shot_id, scene_id, asset_id)) > 1:
            raise WorkflowError('Choose one revision scope at a time')
        if shot_id and stage_id not in {'shot_timeline_specs', 'storyboard_reference_generation_or_prompt'}:
            raise WorkflowError('Shot-scoped revision targets timeline or storyboard-reference generation')
        if shot_id and shot_id not in {s['shot_id'] for s in self._planned_shots()}:
            raise WorkflowError('Unknown shot ID; nothing was invalidated')
        affected = [stage.id for stage in self.graph.downstream(stage_id, include_self=True)]
        affected_shots = None
        if scene_id:
            if stage_id != 'spatial_blocking' or scene_id not in {s['scene_id'] for s in self.store.read(SCENE_SPACE_PLAN)['scenes']}:
                raise WorkflowError('Scene revision needs a known scene and spatial_blocking stage')
            affected_shots = {s['shot_id'] for s in self._planned_shots() if s.get('scene_id') == scene_id}
        if asset_id:
            assets = {a['asset_id']: a for a in self.store.read(ASSET_REGISTRY)['assets']}
            if stage_id not in {'asset_plan', 'asset_generation_or_prompt'} or asset_id not in assets:
                raise WorkflowError('Asset revision needs an existing asset and asset stage')
            if assets[asset_id]['asset_type'] not in {'character-reference', 'style-reference'}:
                raise WorkflowError('Scene/prop geometry changes require explicit spatial revision, not appearance-only scope')
            preserved = {'spatial_blocking', 'spatial_preview', 'spatial_lock_gate', 'storyboard_choice',
                         'storyboard_plan', 'shot_timeline_specs', 'storyboard_package'}
            affected = [s for s in affected if s not in preserved]
        state['revision_scope'] = {'stage_id': stage_id, 'shot_id': shot_id, 'scene_id': scene_id, 'asset_id': asset_id,
                                   'request_revision': state['revision'] + 1}
        if stage_id == 'asset_generation_or_prompt':
            ids = [asset_id] if asset_id else [a['asset_id'] for a in self.store.read(ASSET_REGISTRY)['assets']]
            for key in ids:
                state.setdefault('creative_revision_tokens', {})['asset:' + key] = state['revision'] + 1
        if stage_id == 'storyboard_reference_generation_or_prompt':
            ids = [shot_id] if shot_id else [s['shot_id'] for s in self._planned_shots()]
            for key in ids:
                state.setdefault('creative_revision_tokens', {})['storyboard:' + key] = state['revision'] + 1
        if "shot_timeline_specs" in affected and self.store.exists(SHOT_TIMELINE_INDEX):
            index = self.store.read(SHOT_TIMELINE_INDEX)
            retained = [item for item in index['shots'] if (shot_id and item['shot_id'] != shot_id)
                        or (affected_shots is not None and item['shot_id'] not in affected_shots)]
            index.update(revision=self.store.revision_for(SHOT_TIMELINE_INDEX), shots=retained, shot_count=len(retained))
            self.store.commit(SHOT_TIMELINE_INDEX, index)
        skipped = set(state.get("skipped_stages", []))
        for affected_stage in affected:
            if affected_stage in skipped:
                continue
            state["stage_status"][affected_stage] = "invalidated"
        removed_fields: set[str] = set()
        for stage in self.graph.stages:
            if stage.id not in affected:
                continue
            for field_id in self._dynamic_required_decisions(stage, state):
                approval_path = state.get("decision_approvals", {}).get(field_id)
                if approval_path and self.store.exists(approval_path):
                    approval = self.store.read(approval_path)
                    approval["revision"] = self.store.revision_for(approval_path)
                    approval["valid"] = False
                    approval["invalidated_by"] = stage_id
                    approval["invalidated_stages"] = affected
                    self.store.commit(approval_path, approval)
                state["decisions"].pop(field_id, None)
                state.get("decision_approvals", {}).pop(field_id, None)
                state.get("decision_stages", {}).pop(field_id, None)
                removed_fields.add(field_id)
        for field_id, decision_stage in list(state.get("decision_stages", {}).items()):
            if decision_stage in affected:
                approval_path = state.get("decision_approvals", {}).get(field_id)
                if approval_path and self.store.exists(approval_path):
                    approval = self.store.read(approval_path)
                    approval["revision"] = self.store.revision_for(approval_path)
                    approval["valid"] = False
                    approval["invalidated_by"] = stage_id
                    approval["invalidated_stages"] = affected
                    self.store.commit(approval_path, approval)
                state["decisions"].pop(field_id, None)
                state.get("decision_approvals", {}).pop(field_id, None)
                state["decision_stages"].pop(field_id, None)
                removed_fields.add(field_id)
        invalidated = set(state.get("invalidated_stages", [])) | set(affected)
        state["invalidated_stages"] = [stage.id for stage in self.graph.stages if stage.id in invalidated]
        if "narrative_extract" in affected:
            state["narrative_completed_batches"] = []
        state["status"] = "running"
        state["current_stage"] = None
        state["active_task"] = None
        state["active_decision"] = None
        if removed_fields:
            project = self.project
            for field_id in removed_fields:
                project.get("selected_config", {}).pop(field_id, None)
            if "rights_status" in removed_fields or "likeness_authorization" in removed_fields:
                project["external_generation_blocked"] = True
            self._save_project(project)
        self._save_state(state)
        self.store.rebuild_manifest()
        return self.run()

    @project_transaction
    def import_video(self, shot_id: str, source: Path | str) -> dict[str, Any]:
        if shot_id not in {s['shot_id'] for s in self._planned_shots()}:
            raise WorkflowError('Import requires a known Canonical shot ID')
        source = Path(source).resolve(strict=True)
        from .pipeline import inspect_video
        inspection = inspect_video(source)
        if not inspection['verified']:
            raise WorkflowError('Imported video failed file validation')
        digest = sha256_file(source)
        relative = f'{P11}/media/imported/{digest[:20]}{source.suffix.lower()}'
        self.store.copy_source(source, relative)
        self.store.write_text(f'runtime/imported-videos/{shot_id}.json', canonical_json({
            'shot_id': shot_id, 'kind': 'video', 'path': relative, 'provider': 'provided-local',
            'source_sha256': digest, **inspection, 'creative_review': 'pending', 'generated_by_workflow': False}))
        self.store.rebuild_manifest()
        if self.state['stage_status'].get('media_execution_or_fallback') == 'complete':
            return self.invalidate_from('media_execution_or_fallback')
        return self.status()

    @project_transaction
    def add_inputs(self, inputs: list[str], *, input_type: str | None = None) -> dict[str, Any]:
        if not inputs:
            raise WorkflowError("At least one additional input is required")
        registry = self.store.read(SOURCE_REGISTRY)
        records, _ = ingest_inputs(
            self.store,
            inputs,
            input_type=input_type,
            start_index=len(registry["sources"]) + 1,
        )
        registry["sources"].extend(records)
        registry["entry_mode"] = determine_entry_mode(item["kind"] for item in registry["sources"])
        registry["revision"] = self.store.revision_for(SOURCE_REGISTRY)
        self.store.commit(SOURCE_REGISTRY, registry)
        project = self.project
        project["entry_mode"] = registry["entry_mode"]
        project["external_generation_blocked"] = True
        self._save_project(project)
        state = self.state
        previous_skips = set(state.get("skipped_stages", []))
        new_skips = set(ENTRY_SKIPS.get(registry["entry_mode"], ()))
        for stage_id in previous_skips - new_skips:
            if not self.store.exists(self.graph.get(stage_id).output or ""):
                state["stage_status"][stage_id] = "pending"
        for stage_id in new_skips:
            state["stage_status"][stage_id] = "complete"
        state["skipped_stages"] = sorted(new_skips)
        state["status"] = "running"
        state["active_task"] = None
        state["active_decision"] = None
        state["current_stage"] = None
        self._save_state(state)
        self.store.rebuild_manifest()
        return self.invalidate_from("intake_normalize")

    @project_transaction
    def status(self) -> dict[str, Any]:
        if self._legacy_v1:
            return self._migration_status()
        state = self.state
        current = state.get("current_stage")
        response: dict[str, Any] = {
            "project_id": state["project_id"],
            "project_dir": str(self.store.root),
            "status": state["status"],
            "current_stage": current,
            "invalidated_stages": state.get("invalidated_stages", []),
            "failure_counts": {key: value for key, value in state.get("failure_counts", {}).items() if value},
            "capability_failure": state.get('capability_failure'),
        }
        if current:
            phase = self.graph.phase_for_stage(current)
            response.update(
                {
                    "current_phase": phase.id,
                    "current_phase_name": phase.name,
                    "current_phase_folder": str(self.store.path(phase.folder)),
                }
            )
        if current and state.get('failure_counts', {}).get(current):
            path = f"runtime/failures/{current}-{state['failure_counts'][current]}.json"
            if self.store.exists(path):
                response['last_failure'] = self.store.read(path)
        if state.get("active_decision"):
            response["next_action"] = "submit_decision"
            response["decision_request_path"] = str(self.store.path(state["active_decision"]))
            response["decision_request"] = self.store.read(state["active_decision"])
        elif state.get("active_task"):
            response["next_action"] = "submit_agent_result"
            response["task_envelope_path"] = str(self.store.path(state["active_task"]))
            response["task_envelope"] = self.store.read(state["active_task"])
        elif state["status"] == "blocked":
            response["next_action"] = "inspect_failure_or_supply_resolution"
        elif state["status"] == "complete":
            response["next_action"] = "validate_or_export"
            archive = self.store.path(f"{P13}/delivery/{state['project_id']}.zip")
            if archive.exists():
                response["delivery_archive"] = str(archive)
                response["delivery_sha256"] = sha256_file(archive)
        else:
            response["next_action"] = "run"
        return response
