from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_comic_drama_workflow.exporter import build_delivery_archive
from ai_comic_drama_workflow.kernel import WorkflowKernel
from ai_comic_drama_workflow.layout import (
    ADAPTED_PROMPT_PACKAGE,
    CANONICAL_PROMPT_PACKAGE,
    FINAL_DELIVERY_INDEX,
    P03,
    P07,
    P09,
    P10,
    P11,
    P12,
    P13,
    SHOT_PLAN,
    SHOT_TIMELINE_INDEX,
)
from ai_comic_drama_workflow.validation import validate_project

from tests.helpers import drive_to_completion


class EndToEndTests(unittest.TestCase):
    def test_chapter_batches_update_dynamic_memory_before_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            novel = "\n\n".join(
                f"第{label}章 标题{index}\n第{index}章的内容。"
                for index, label in enumerate(["一", "二", "三", "四", "五", "六"], start=1)
            )
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", [novel], input_type="novel")
            drive_to_completion(
                kernel,
                choices={"chapter_batch_size": 2},
                storyboard_durations=[10],
            )
            plan = kernel.store.read(f"{P03}/source-batches.json")
            self.assertEqual(3, len(plan["batches"]))
            self.assertEqual(2, plan["batch_size"])
            memory = kernel.store.read(f"{P03}/narrative-memory.json")
            self.assertEqual(3, len(memory["batch_updates"]))
            bundle = kernel.store.read(f"{P03}/narrative-bundle.json")
            self.assertEqual(3, bundle["batch_count"])
            narrative_tasks = list((kernel.store.root / "runtime" / "tasks").glob("narrative_extract-*.json"))
            self.assertEqual(3, len(narrative_tasks))
            for task_path in narrative_tasks:
                task = json.loads(task_path.read_text(encoding="utf-8"))
                self.assertIsNotNone(task["source_batch"])
                self.assertEqual(1, len([path for path in task["input_artifacts"] if "runtime/source-batches/" in path]))

    def test_prompt_only_novel_flow_is_valid_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            kernel = WorkflowKernel.initialize(project, ["少女在雨夜收到未来来信。"], input_type="novel")
            result = drive_to_completion(kernel, storyboard_durations=[20, 10, 15, 8])
            self.assertEqual("complete", result["status"])
            delivery = kernel.store.read(FINAL_DELIVERY_INDEX)
            self.assertEqual("prompt_ready", delivery["status"])
            self.assertTrue(kernel.store.exists(f"{P13}/cover-package.json"))
            self.assertTrue(kernel.store.exists(f"{P13}/publication-copy.json"))
            self.assertFalse(kernel.store.read(f"{P13}/publication-checklist.json")["publication_performed"])
            shots = kernel.store.read(SHOT_TIMELINE_INDEX)
            self.assertEqual(6, shots["shot_count"])
            self.assertEqual(6, len(list((project / P10 / "shots").glob("*.txt"))))
            self.assertEqual(6, len(list((project / P11 / "adapted").glob("*.txt"))))
            self.assertTrue((project / P07 / "assets" / "prompts" / "ASSET-CHAR-001.txt").exists())
            self.assertTrue((project / P12 / "derived" / "voice-script.txt").exists())
            self.assertTrue((project / P13 / "publish" / "cover-prompt.txt").exists())
            tasks = list((project / "runtime" / "tasks").glob("shot_timeline_specs-*.json"))
            self.assertEqual(2, len(tasks))
            report = validate_project(project, final=True)
            self.assertTrue(report["valid"], report)
            first = build_delivery_archive(kernel.store)
            second = build_delivery_archive(kernel.store)
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["aggregate_hash"], second["aggregate_hash"])

    def test_ten_fifteen_twenty_segments_become_one_to_twelve_second_shots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            drive_to_completion(kernel, storyboard_durations=[10, 15, 20])
            storyboard = kernel.store.read(SHOT_PLAN)
            self.assertEqual([10.0, 7.5, 7.5, 10.0, 10.0], [shot["duration_s"] for shot in storyboard["shots"]])
            self.assertTrue(all(1 <= shot["duration_s"] <= 12 for shot in storyboard["shots"]))

    def test_seedance_adapter_preserves_canonical_fact_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            drive_to_completion(
                kernel,
                choices={"target_platform": "seedance-2.0-doubao"},
                storyboard_durations=[10],
            )
            canonical = kernel.store.read(CANONICAL_PROMPT_PACKAGE)
            adapted = kernel.store.read(ADAPTED_PROMPT_PACKAGE)
            source = {item["shot_id"]: item["canonical_fact_hash"] for item in canonical["prompts"]}
            self.assertEqual(
                source,
                {item["shot_id"]: item["canonical_fact_hash"] for item in adapted["prompts"]},
            )
            self.assertTrue(adapted["warnings"])
            capability = kernel.store.read(f"{P11}/capability-snapshot.json")
            self.assertEqual("unknown", capability["capabilities"]["seedance_2_doubao"]["status"])


if __name__ == "__main__":
    unittest.main()
