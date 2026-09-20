from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_comic_drama_workflow.graph import WorkflowGraph
from ai_comic_drama_workflow.kernel import WorkflowKernel
from ai_comic_drama_workflow.layout import (
    ADAPTED_PROMPT_PACKAGE,
    ASSET_REGISTRY,
    CANONICAL_PROMPT_PACKAGE,
    P01,
    P07,
    P08,
    P09,
    PHASES,
    SCENE_SPACE_PLAN,
    SHOT_TIMELINE_INDEX,
    SOURCE_REGISTRY,
)
from ai_comic_drama_workflow.utils import canonical_json, sha256_file, stable_id
from ai_comic_drama_workflow.validation import validate_project

from tests.helpers import DEFAULT_CHOICES, artifact_for_stage, drive_to_completion


def advance_until(
    kernel: WorkflowKernel,
    target_stage: str,
    *,
    choices: dict | None = None,
    durations: list[float] | None = None,
) -> dict:
    selected = {**DEFAULT_CHOICES, **(choices or {})}
    storyboard_durations = durations or [10]
    status = kernel.run()
    for step in range(1, 200):
        if status.get("current_stage") == target_stage:
            return status
        if status["status"] == "awaiting_choice":
            request = status["decision_request"]
            status = kernel.resume(
                {
                    "request_id": request["request_id"],
                    "context_fingerprint": request["context_fingerprint"],
                    "selections": {field["id"]: selected[field["id"]] for field in request["fields"]},
                }
            )
            continue
        if status["status"] == "awaiting_agent_result":
            task = status["task_envelope"]
            artifact = artifact_for_stage(kernel, task, storyboard_durations=storyboard_durations)
            status = kernel.submit(
                {
                    "schema_version": "3.0",
                    "result_id": stable_id("result", task["task_id"], step),
                    "project_id": task["project_id"],
                    "stage_id": task["stage_id"],
                    "context_fingerprint": task["context_fingerprint"],
                    "status": "approved" if task["stage_id"] == "story_quality_gate" else "draft",
                    "artifact": artifact,
                    "findings": [],
                    "provenance": [{"source": path} for path in task["input_artifacts"]],
                }
            )
            continue
        raise AssertionError(status)
    raise AssertionError(f"Did not reach {target_stage}")


def make_v1_project(root: Path) -> None:
    root.mkdir(parents=True)
    source_path = root / "sources" / "original" / "source.txt"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("旧项目小说正文", encoding="utf-8")
    project_id = "legacy-project-001"
    base = {
        "schema_version": "1.0",
        "artifact_id": "legacy-artifact",
        "project_id": project_id,
        "revision": 1,
        "role_provenance": "kernel",
    }
    project = {
        **base,
        "artifact_type": "project",
        "stage_id": "project_setup",
        "title": "旧项目",
        "format": "short-drama",
        "work_depth": "standard",
        "adaptation_policy": "limited-expansion",
        "selected_config": {},
        "external_generation_blocked": False,
        "entry_mode": "novel",
        "workflow_id": "ai-comic-drama-main-v1",
    }
    (root / "project.json").write_text(canonical_json(project), encoding="utf-8")
    state = {
        **base,
        "artifact_type": "workflow-state",
        "stage_id": "segment_plan",
        "status": "complete",
        "stage_status": {},
        "decisions": {
            "work_depth": "standard",
            "adaptation_policy": "limited-expansion",
            "rights_status": "owned-or-authorized",
            "segment_duration_s": 10,
        },
        "failure_counts": {},
    }
    (root / "state.json").write_text(canonical_json(state), encoding="utf-8")
    registry = {
        **base,
        "artifact_type": "source-registry",
        "stage_id": "source_ingest",
        "entry_mode": "novel",
        "sources": [
            {
                "source_id": "SOURCE-001",
                "kind": "novel",
                "stored_path": "sources/original/source.txt",
                "text_path": "sources/original/source.txt",
                "sha256": sha256_file(source_path),
                "rights_status": "owned-or-authorized",
                "authority": "source",
                "extraction_status": "extracted",
            }
        ],
    }
    (root / "sources" / "source-registry.json").write_text(canonical_json(registry), encoding="utf-8")
    artifacts = {
        "intake/brief.json": ("intake-brief", "intake_normalize", {"conflicts": [], "unknowns": []}),
        "intake/gap-resolution.json": ("gap-resolution", "gap_resolution", {"rights_status": "owned-or-authorized"}),
        "story/narrative-bundle.json": ("narrative-bundle", "narrative_extract", {"facts": []}),
        "story/adaptation-plan.json": ("adaptation-plan", "adaptation_plan", {"beats": []}),
        "story/screenplay.json": ("screenplay", "screenplay", {"scenes": []}),
        "story/screenplay-enhanced.json": ("screenplay", "screenplay_enhance", {"scenes": []}),
        "reviews/story-review.json": ("quality-review", "story_quality_gate", {"review_status": "approved"}),
        "planning/generation-segments.json": (
            "generation-segment-plan",
            "segment_plan",
            {"target_duration_s": 10, "segments": [{"segment_id": "SEG-001", "index": 1, "target_duration_s": 10, "source_refs": []}]},
        ),
        "design/visual-bible.json": ("visual-bible", "visual_bible", {"legacy": True}),
    }
    for relative, (artifact_type, stage_id, body) in artifacts.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {**base, "artifact_type": artifact_type, "stage_id": stage_id, **body}
        path.write_text(canonical_json(value), encoding="utf-8")


class WorkflowV2Tests(unittest.TestCase):
    def test_phase_layout_and_phase_index_are_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            phase_index = kernel.store.read("phase-index.json")
            self.assertEqual(13, len(phase_index["phases"]))
            self.assertEqual([item["folder"] for item in PHASES], [item["folder"] for item in phase_index["phases"]])
            for phase in PHASES:
                self.assertTrue(kernel.store.path(str(phase["folder"])).is_dir())
            self.assertTrue(kernel.store.exists("phase-index.md"))

    def test_multi_select_and_unavailable_3d_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            status = advance_until(kernel, "spatial_blocking")
            request = status["decision_request"]
            field = next(item for item in request["fields"] if item["id"] == "spatial_representation")
            true_3d = next(item for item in field["options"] if item["id"] == "verified-3d")
            self.assertEqual("unavailable", true_3d["availability"])
            with self.assertRaises(ValueError):
                kernel.resume(
                    {
                        "request_id": request["request_id"],
                        "context_fingerprint": request["context_fingerprint"],
                        "selections": {"spatial_representation": "verified-3d"},
                    }
                )
            status = kernel.resume(
                {
                    "request_id": request["request_id"],
                    "context_fingerprint": request["context_fingerprint"],
                    "selections": {"spatial_representation": "2.5d-structured-previsualization"},
                }
            )
            status = advance_until(kernel, "storyboard_choice")
            views = next(item for item in status["decision_request"]["fields"] if item["id"] == "storyboard_views")
            self.assertEqual("multi", views["selection_mode"])
            self.assertEqual(5, views["max_selections"])

    def test_three_human_gates_have_current_approval_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            drive_to_completion(kernel, storyboard_durations=[10])
            for field in ("asset_review_decision", "spatial_review_decision", "storyboard_review_decision"):
                path = kernel.state["decision_approvals"][field]
                self.assertTrue(kernel.store.exists(path))
                self.assertEqual("approve", kernel.store.read(path)["selections"][field])
                self.assertNotEqual(False, kernel.store.read(path).get("valid"))

    def test_spatiotemporal_tracks_and_state_handoff_are_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            drive_to_completion(kernel, storyboard_durations=[10, 10])
            index = kernel.store.read(SHOT_TIMELINE_INDEX)
            shots = [kernel.store.read(item["path"]) for item in index["shots"]]
            self.assertEqual(2, len(shots[0]["character_tracks"]))
            self.assertEqual(
                ["preparation", "start", "development", "key", "end", "recovery"],
                [item["phase"] for item in shots[0]["character_tracks"][0]["action_events"]],
            )
            self.assertEqual(
                shots[0]["continuity"]["end_state"],
                shots[1]["continuity"]["start_state"],
            )
            self.assertTrue(validate_project(kernel.store.root, final=True)["valid"])

    def test_storyboard_key_moments_and_svg_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            drive_to_completion(kernel, storyboard_durations=[10])
            package = kernel.store.read(f"{P09}/storyboard-package.json")
            self.assertTrue(1 <= len(package["shots"][0]["key_moments"]) <= 3)
            preview = package["shots"][0]["previsualization"]
            self.assertEqual("structured_previsualization", preview["status"])
            self.assertFalse(preview["verified_3d"])
            self.assertIn("not a verified 3D model", kernel.store.path(preview["path"]).read_text(encoding="utf-8"))

    def test_dependency_closure_does_not_invalidate_unrelated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            drive_to_completion(kernel, storyboard_durations=[10])
            old_approval = kernel.state["decision_approvals"]["asset_review_decision"]
            kernel.invalidate_from("asset_generation_or_prompt")
            state = kernel.state
            self.assertEqual("complete", state["stage_status"]["visual_bible"])
            self.assertEqual("complete", state["stage_status"]["visual_capability_probe"])
            self.assertEqual("awaiting_choice", state["stage_status"]["asset_quality_gate"])
            self.assertEqual("invalidated", state["stage_status"]["canonical_prompt_compile"])
            self.assertFalse(kernel.store.read(old_approval)["valid"])

    def test_prompt_trace_and_adapter_fact_hash_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            drive_to_completion(
                kernel,
                choices={"target_platform": "seedance-2.0-doubao"},
                storyboard_durations=[10],
            )
            canonical = kernel.store.read(CANONICAL_PROMPT_PACKAGE)
            adapted = kernel.store.read(ADAPTED_PROMPT_PACKAGE)
            item = canonical["prompts"][0]
            self.assertGreaterEqual(len(item["source_trace"]), 7)
            for source in item["source_trace"]:
                self.assertEqual(source["sha256"], sha256_file(kernel.store.path(source["path"])))
            self.assertEqual(item["canonical_fact_hash"], adapted["prompts"][0]["canonical_fact_hash"])

    def test_invalid_timeline_time_is_detected_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            drive_to_completion(kernel, storyboard_durations=[10])
            entry = kernel.store.read(SHOT_TIMELINE_INDEX)["shots"][0]
            shot = kernel.store.read(entry["path"])
            shot["revision"] = kernel.store.revision_for(entry["path"])
            shot["character_tracks"][0]["trajectory"][1]["time_s"] = 99
            kernel.store.commit(entry["path"], shot)
            report = validate_project(kernel.store.root, verify_manifest=False)
            self.assertFalse(report["valid"])
            self.assertIn("trajectory-time", {item["code"] for item in report["errors"]})

    def test_v1_migration_choices_are_explicit_and_non_silent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for action in ("read-only", "non-destructive-migrate", "copy-new"):
                root = base / action
                make_v1_project(root)
                kernel = WorkflowKernel(root)
                status = kernel.run()
                self.assertEqual("awaiting_choice", status["status"])
                request = status["decision_request"]
                result = kernel.resume(
                    {
                        "request_id": request["request_id"],
                        "context_fingerprint": request["context_fingerprint"],
                        "selections": {"migration_action": action},
                    }
                )
                if action == "read-only":
                    self.assertEqual("blocked", result["status"])
                    self.assertEqual("1.0", json.loads((root / "project.json").read_text(encoding="utf-8"))["schema_version"])
                    self.assertFalse((root / "phase-index.json").exists())
                elif action == "non-destructive-migrate":
                    self.assertEqual("3.0", WorkflowKernel(root).project["schema_version"])
                    self.assertTrue((root / ".history" / "migrations" / "v1" / "tree" / "design" / "visual-bible.json").exists())
                    self.assertFalse((root / "design").exists())
                    self.assertEqual("invalidated", WorkflowKernel(root).state["stage_status"]["visual_bible"])
                    self.assertFalse(WorkflowKernel(root).store.read(f"{P01}/migration-report.json")["old_approvals_accepted"])
                else:
                    copied = Path(result["copied_project_dir"])
                    self.assertEqual("1.0", json.loads((root / "project.json").read_text(encoding="utf-8"))["schema_version"])
                    self.assertEqual("3.0", WorkflowKernel(copied).project["schema_version"])
                    self.assertTrue(result["original_project_unchanged"])

    def test_screenplay_storyboard_mixed_and_migrated_projects_reach_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            cases = [
                ("screenplay", ["场1 内 日\n人物：林\n林收到一封信。"], "screenplay"),
                ("storyboard", ["分镜1：中景。\n分镜2：特写。"], "storyboard"),
            ]
            novel = base / "mixed-novel.txt"
            script = base / "mixed-script.md"
            novel.write_text("小说正文", encoding="utf-8")
            script.write_text("场1 内 日\n林收到一封信。", encoding="utf-8")
            cases.append(("mixed", [str(novel), str(script)], None))
            for name, inputs, hint in cases:
                kernel = WorkflowKernel.initialize(base / name, inputs, input_type=hint)
                self.assertEqual("complete", drive_to_completion(kernel, storyboard_durations=[10])["status"])
            legacy_root = base / "migrated"
            make_v1_project(legacy_root)
            legacy = WorkflowKernel(legacy_root)
            request = legacy.run()["decision_request"]
            legacy.resume(
                {
                    "request_id": request["request_id"],
                    "context_fingerprint": request["context_fingerprint"],
                    "selections": {"migration_action": "non-destructive-migrate"},
                }
            )
            self.assertEqual("complete", drive_to_completion(WorkflowKernel(legacy_root), storyboard_durations=[10])["status"])

    def test_golden_prompt_only_novel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            result = drive_to_completion(kernel, storyboard_durations=[10])
            self.assertEqual("complete", result["status"])
            self.assertEqual("prompt_ready", kernel.store.read(f"stages/13-最终质检与交付/final-delivery-index.json")["status"])

    def test_golden_image_unavailable_confirmed_prompt_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            drive_to_completion(
                kernel,
                choices={"asset_image_strategy": "generate-if-available"},
                storyboard_durations=[10],
            )
            self.assertEqual("prompt-only", kernel.state["decisions"]["asset_image_fallback"])
            self.assertEqual("prompt-only", kernel.state["decisions"]["storyboard_image_fallback"])
            self.assertEqual("prompt_ready", kernel.store.read(ASSET_REGISTRY)["execution_status"])


if __name__ == "__main__":
    unittest.main()
