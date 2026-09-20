from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import importlib.util
from pathlib import Path

from ai_comic_drama_workflow.kernel import WorkflowKernel
from ai_comic_drama_workflow.layout import (
    ASSET_REGISTRY,
    FINAL_DELIVERY_INDEX,
    MEDIA_EXECUTION_INDEX,
    P07,
    P09,
    P11,
    P12,
)

from tests.helpers import drive_to_completion


class RecoveryAndMediaTests(unittest.TestCase):
    def test_upstream_revision_invalidates_downstream_and_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            drive_to_completion(kernel, storyboard_durations=[10])
            status = kernel.invalidate_from("visual_bible")
            self.assertEqual("visual_bible", status["current_stage"])
            state = kernel.state
            self.assertEqual("invalidated", state["stage_status"]["platform_choice"])
            self.assertNotIn("target_platform", state["decisions"])
            self.assertTrue((kernel.store.root / ".history").exists())

    def test_existing_project_repairs_only_missing_artifact_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            kernel = WorkflowKernel.initialize(project, ["小说正文"], input_type="novel")
            drive_to_completion(kernel, storyboard_durations=[10])
            (project / P07 / "visual-bible.json").unlink()
            resumed = WorkflowKernel(project).run()
            self.assertEqual("awaiting_agent_result", resumed["status"])
            self.assertEqual("visual_bible", resumed["current_stage"])
            self.assertEqual("complete", WorkflowKernel(project).state["stage_status"]["segment_plan"])
            self.assertEqual("invalidated", WorkflowKernel(project).state["stage_status"]["storyboard_plan"])
            self.assertNotIn("target_platform", WorkflowKernel(project).state["decisions"])

    def test_fourth_identical_agent_failure_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kernel = WorkflowKernel.initialize(Path(temporary) / "project", ["小说正文"], input_type="novel")
            status = kernel.run()
            request = status["decision_request"]
            status = kernel.resume(
                {
                    "request_id": request["request_id"],
                    "context_fingerprint": request["context_fingerprint"],
                    "selections": {"delivery_target": "prompt-draft", "work_depth": "standard", "adaptation_policy": "limited-expansion"},
                }
            )
            for attempt in range(1, 5):
                task = status["task_envelope"]
                status = kernel.submit(
                    {
                        "schema_version": "3.0",
                        "result_id": f"failed-{attempt}",
                        "project_id": task["project_id"],
                        "stage_id": task["stage_id"],
                        "context_fingerprint": task["context_fingerprint"],
                        "status": "failed",
                        "artifact": {},
                        "findings": [{"code": "same-failure"}],
                        "provenance": [],
                    }
                )
            self.assertEqual("blocked", status["status"])
            self.assertEqual(4, kernel.state["failure_counts"]["intake_normalize"])

    def test_unverified_rights_prevent_fixture_upload_or_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixtures"
            fixture.mkdir()
            (fixture / "SHOT-001.mp4").write_bytes(b"not-used-because-rights-blocked")
            kernel = WorkflowKernel.initialize(
                root / "project",
                ["小说正文"],
                input_type="novel",
                environment={"AI_COMIC_DRAMA_MEDIA_FIXTURE_DIR": str(fixture)},
            )
            drive_to_completion(
                kernel,
                choices={"rights_status": "unverified-prompt-only"},
                storyboard_durations=[1],
            )
            execution = kernel.store.read(MEDIA_EXECUTION_INDEX)
            self.assertTrue(execution["external_generation_blocked"])
            self.assertEqual(0, execution["generated_video_count"])
            self.assertEqual("rights-or-authorization-boundary", execution["manual_operations"][0]["reason"])

    def test_paid_provider_creates_external_action_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = {
                "AI_COMIC_DRAMA_VIDEO_GENERATION_STATUS": "requires_payment",
                "AI_COMIC_DRAMA_VIDEO_GENERATION_PROVIDER": "declared-paid-provider",
            }
            kernel = WorkflowKernel.initialize(
                Path(temporary) / "project",
                ["小说正文"],
                input_type="novel",
                environment=environment,
            )
            drive_to_completion(kernel, storyboard_durations=[1])
            self.assertEqual("prompt-only", kernel.state["decisions"]["video_external_action"])
            capability = kernel.store.read(f"{P11}/capability-snapshot.json")
            self.assertEqual("requires_payment", capability["capabilities"]["video_generation"]["status"])
            self.assertEqual(0, kernel.store.read(MEDIA_EXECUTION_INDEX)["generated_video_count"])

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow required")
    def test_golden_image_available_generates_assets_storyboard_and_video_prompts(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixtures"
            fixture.mkdir()
            for name in (
                "ASSET-STYLE-001",
                "ASSET-CHAR-001",
                "ASSET-CHAR-002",
                "ASSET-SCENE-001",
                "ASSET-PROP-001",
                "SHOT-001-start",
                "SHOT-001-key",
                "SHOT-001-end",
            ):
                Image.new("RGB", (64, 64), color=(20, 80, 140)).save(fixture / f"{name}.png")
            kernel = WorkflowKernel.initialize(
                root / "project",
                ["小说正文"],
                input_type="novel",
                environment={"AI_COMIC_DRAMA_MEDIA_FIXTURE_DIR": str(fixture)},
            )
            drive_to_completion(
                kernel,
                choices={"asset_image_strategy": "generate-if-available"},
                storyboard_durations=[1],
            )
            capability = kernel.store.read(f"{P07}/capability-snapshot.json")["capabilities"]
            self.assertEqual("available", capability["image_generation"]["status"])
            self.assertEqual("unavailable", capability["video_generation"]["status"])
            assets = kernel.store.read(ASSET_REGISTRY)
            self.assertEqual("media_verified", assets["execution_status"])
            references = kernel.store.read(f"{P09}/reference-image-index.json")
            self.assertEqual("media_verified", references["status"])
            execution = kernel.store.read(MEDIA_EXECUTION_INDEX)
            self.assertEqual(0, execution["generated_video_count"])
            self.assertTrue(any(item["kind"] == "video" for item in execution["manual_operations"]))
            self.assertEqual("prompt_ready", kernel.store.read(FINAL_DELIVERY_INDEX)["status"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
    def test_local_fixture_media_requires_real_file_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixtures"
            fixture.mkdir()
            subprocess.run(
                [
                    shutil.which("ffmpeg") or "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=320x568:d=1",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=1",
                    "-shortest",
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    "-pix_fmt",
                    "yuv420p",
                    "-y",
                    str(fixture / "SHOT-001.mp4"),
                ],
                check=True,
            )
            environment = {"AI_COMIC_DRAMA_MEDIA_FIXTURE_DIR": str(fixture)}
            kernel = WorkflowKernel.initialize(
                root / "project",
                ["小说正文"],
                input_type="novel",
                environment=environment,
            )
            drive_to_completion(
                kernel,
                choices={"voice_strategy": "original-audio", "media_execution_mode": "execute-if-available"},
                storyboard_durations=[1],
            )
            execution = kernel.store.read(MEDIA_EXECUTION_INDEX)
            self.assertEqual(1, execution["generated_video_count"])
            self.assertTrue(execution["outputs"][0]["verified"])
            render = kernel.store.read(f"{P12}/render-package.json")
            self.assertTrue(render["final_video"]["verified"])
            delivery = kernel.store.read(FINAL_DELIVERY_INDEX)
            self.assertEqual("media_verified", delivery["status"])


if __name__ == "__main__":
    unittest.main()
