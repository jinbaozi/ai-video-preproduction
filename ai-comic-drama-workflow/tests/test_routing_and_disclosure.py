from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_comic_drama_workflow.kernel import WorkflowKernel
from ai_comic_drama_workflow.layout import SOURCE_REGISTRY
from ai_comic_drama_workflow.utils import PACKAGE_ROOT, read_json


class RoutingAndDisclosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_routes_novel_screenplay_storyboard_mixed_and_legacy(self) -> None:
        cases = [
            ("novel", "一封来自未来的信改变了少女的命运。", "novel"),
            ("screenplay", "场1 内 日\n人物：林\n林打开一封信。", "screenplay"),
            ("storyboard", "分镜1：中景。\n分镜2：特写。", "storyboard"),
        ]
        for index, (expected, source, hint) in enumerate(cases):
            kernel = WorkflowKernel.initialize(self.root / f"project-{index}", [source], input_type=hint)
            registry = kernel.store.read(SOURCE_REGISTRY)
            self.assertEqual(expected, registry["entry_mode"])
        novel = self.root / "novel.txt"
        script = self.root / "剧本.md"
        novel.write_text("小说正文", encoding="utf-8")
        script.write_text("场1 内 日\n人物：林", encoding="utf-8")
        mixed = WorkflowKernel.initialize(self.root / "mixed", [str(novel), str(script)])
        self.assertEqual("mixed", mixed.project["entry_mode"])
        legacy_file = self.root / "old-project.json"
        legacy_file.write_text(
            json.dumps({"schema_version": "0.9", "project_id": "old", "artifact_type": "project"}),
            encoding="utf-8",
        )
        legacy = WorkflowKernel.initialize(self.root / "legacy", [str(legacy_file)])
        self.assertEqual("legacy-project", legacy.project["entry_mode"])

    def test_task_envelope_loads_only_current_resources(self) -> None:
        kernel = WorkflowKernel.initialize(self.root / "project", ["小说正文"], input_type="novel")
        status = kernel.run()
        request = status["decision_request"]
        status = kernel.resume(
            {
                "request_id": request["request_id"],
                "context_fingerprint": request["context_fingerprint"],
                "selections": {"delivery_target": "prompt-draft", "work_depth": "standard", "adaptation_policy": "limited-expansion"},
            }
        )
        task = status["task_envelope"]
        catalog = read_json(PACKAGE_ROOT / "resource-catalog.json")["resources"]
        self.assertLess(len(task["loaded_resources"]), len(catalog))
        self.assertIn("references/role-intake.md", task["loaded_resources"])
        self.assertIn("references/phases/phase-02.md", task["loaded_resources"])
        self.assertNotIn("references/seedance-2.0.md", task["loaded_resources"])
        self.assertEqual("phase-02", task["phase_id"])
        self.assertRegex(task["context_fingerprint"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
