from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_comic_drama_workflow.kernel import StaleContextError, WorkflowError, WorkflowKernel
from ai_comic_drama_workflow.layout import P02, SOURCE_REGISTRY
from ai_comic_drama_workflow.schema import SchemaValidationError, load_schema, validate


class SchemaAndChoiceTests(unittest.TestCase):
    @staticmethod
    def _advance_to_intake(kernel: WorkflowKernel) -> dict:
        status = kernel.run()
        request = status["decision_request"]
        return kernel.resume(
            {
                "request_id": request["request_id"],
                "context_fingerprint": request["context_fingerprint"],
                "selections": {"delivery_target": "prompt-draft", "work_depth": "standard", "adaptation_policy": "limited-expansion"},
            }
        )

    def test_shot_contract_rejects_long_duration_and_six_references(self) -> None:
        shot = {
            "schema_version": "3.0",
            "artifact_type": "shot-timeline-spec",
            "artifact_id": "a",
            "project_id": "p",
            "revision": 1,
            "stage_id": "shot_timeline_specs",
            "role_provenance": "storyboard",
            "shot_id": "SHOT-001",
            "index": 1,
            "segment_id": "SEG-001",
            "scene_id": "SCENE-001",
            "duration_s": 13,
            "narrative_purpose": "test",
            "character_tracks": [],
            "camera_track": [{}],
            "audio_track": [],
            "director_track": [{}],
            "spatial_track": [{}],
            "scene_fixed_track": [{}],
            "environment": {},
            "lighting": {},
            "continuity": {"start_state": {}, "end_state": {}},
            "required_asset_ids": [],
            "selected_reference_ids": ["1", "2", "3", "4", "5", "6"],
            "negative_constraints": [],
        }
        with self.assertRaises(SchemaValidationError):
            validate(shot, load_schema("shot-timeline-spec.schema.json"))

    def test_missing_or_stale_decision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            status = self._advance_to_intake(kernel)
            task = status["task_envelope"]
            result = {
                "schema_version": "3.0",
                "result_id": "result-intake",
                "project_id": task["project_id"],
                "stage_id": task["stage_id"],
                "context_fingerprint": task["context_fingerprint"],
                "status": "draft",
                "artifact": {"conflicts": [], "unknowns": []},
                "findings": [],
                "provenance": [],
            }
            status = kernel.submit(result)
            request = status["decision_request"]
            with self.assertRaises(WorkflowError):
                kernel.resume({"request_id": request["request_id"], "selections": {}})
            with self.assertRaises(StaleContextError):
                kernel.resume(
                    {
                        "request_id": request["request_id"],
                        "context_fingerprint": "0" * 64,
                        "selections": {"rights_status": "owned-or-authorized"},
                    }
                )

    def test_source_change_invalidates_active_agent_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            status = self._advance_to_intake(kernel)
            task = status["task_envelope"]
            registry = kernel.store.read(SOURCE_REGISTRY)
            registry["revision"] += 1
            registry["sources"][0]["note"] = "changed"
            kernel.store.commit(SOURCE_REGISTRY, registry)
            with self.assertRaises(StaleContextError):
                kernel.submit(
                    {
                        "schema_version": "3.0",
                        "result_id": "stale",
                        "project_id": task["project_id"],
                        "stage_id": task["stage_id"],
                        "context_fingerprint": task["context_fingerprint"],
                        "status": "draft",
                        "artifact": {"conflicts": []},
                        "findings": [],
                        "provenance": [],
                    }
                )

    def test_mixed_core_conflict_creates_explicit_pause_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            novel = root / "novel.txt"
            screenplay = root / "screenplay.md"
            novel.write_text("原著结局：主角离开。", encoding="utf-8")
            screenplay.write_text("场1 内 日\n人物：主角\n结局：主角留下。", encoding="utf-8")
            kernel = WorkflowKernel.initialize(root / "project", [str(novel), str(screenplay)])
            status = self._advance_to_intake(kernel)
            task = status["task_envelope"]
            status = kernel.submit(
                {
                    "schema_version": "3.0",
                    "result_id": "mixed-intake",
                    "project_id": task["project_id"],
                    "stage_id": task["stage_id"],
                    "context_fingerprint": task["context_fingerprint"],
                    "status": "draft",
                    "artifact": {
                        "conflicts": [
                            {
                                "conflict_id": "CONFLICT-001",
                                "severity": "core",
                                "field": "ending",
                                "values": ["leave", "stay"],
                            }
                        ]
                    },
                    "findings": [],
                    "provenance": [],
                }
            )
            request = status["decision_request"]
            self.assertEqual(
                {"rights_status", "conflict_policy", "core_conflict_resolution"},
                {field["id"] for field in request["fields"]},
            )
            status = kernel.resume(
                {
                    "request_id": request["request_id"],
                    "context_fingerprint": request["context_fingerprint"],
                    "selections": {
                        "rights_status": "owned-or-authorized",
                        "conflict_policy": "manual-per-conflict",
                        "core_conflict_resolution": "pause",
                    },
                }
            )
            self.assertEqual("blocked", status["status"])

    def test_unreadable_scan_pauses_and_add_input_reopens_intake(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan = root / "scan.pdf"
            scan.write_bytes(b"not a readable PDF")
            kernel = WorkflowKernel.initialize(root / "project", [str(scan)], input_type="novel")
            status = self._advance_to_intake(kernel)
            task = status["task_envelope"]
            status = kernel.submit(
                {
                    "schema_version": "3.0",
                    "result_id": "scan-intake",
                    "project_id": task["project_id"],
                    "stage_id": task["stage_id"],
                    "context_fingerprint": task["context_fingerprint"],
                    "status": "draft",
                    "artifact": {"conflicts": [], "unknowns": ["scan text"]},
                    "findings": [],
                    "provenance": [],
                }
            )
            request = status["decision_request"]
            self.assertIn("unreadable_source_action", {field["id"] for field in request["fields"]})
            selections = {
                field["id"]: (
                    "owned-or-authorized"
                    if field["id"] == "rights_status"
                    else "pause-and-supply-text"
                )
                for field in request["fields"]
            }
            status = kernel.resume(
                {
                    "request_id": request["request_id"],
                    "context_fingerprint": request["context_fingerprint"],
                    "selections": selections,
                }
            )
            self.assertEqual("blocked", status["status"])
            status = kernel.add_inputs(["补充的小说文字。"], input_type="novel")
            self.assertEqual("awaiting_agent_result", status["status"])
            self.assertEqual("intake_normalize", status["current_stage"])
            self.assertNotIn("rights_status", kernel.state["decisions"])
            self.assertEqual(2, len(kernel.store.read(SOURCE_REGISTRY)["sources"]))

    def test_agent_can_raise_structured_decision_without_committing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            status = self._advance_to_intake(kernel)
            task = status["task_envelope"]
            status = kernel.submit(
                {
                    "schema_version": "3.0",
                    "result_id": "intake-needs-choice",
                    "project_id": task["project_id"],
                    "stage_id": task["stage_id"],
                    "context_fingerprint": task["context_fingerprint"],
                    "status": "needs_decision",
                    "artifact": {
                        "decision_request": {
                            "fields": [
                                {
                                    "id": "story_scope",
                                    "question": "选择本次改编范围",
                                    "options": [
                                        {"id": "chapter-1", "label": "第一章"},
                                        {"id": "full", "label": "全文"},
                                    ],
                                }
                            ]
                        }
                    },
                    "findings": [],
                    "provenance": [],
                }
            )
            self.assertEqual("awaiting_choice", status["status"])
            self.assertFalse(kernel.store.exists(f"{P02}/intake-brief.json"))
            request = status["decision_request"]
            resumed = kernel.resume(
                {
                    "request_id": request["request_id"],
                    "context_fingerprint": request["context_fingerprint"],
                    "selections": {"story_scope": "chapter-1"},
                }
            )
            self.assertEqual("awaiting_agent_result", resumed["status"])
            self.assertEqual("chapter-1", kernel.state["decisions"]["story_scope"])


if __name__ == "__main__":
    unittest.main()
