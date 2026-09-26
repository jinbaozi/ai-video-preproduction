"""Synthetic local image bytes exercise V6 host evidence, not visual quality."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from ai_comic_drama_workflow.v6_media_host import (
    image_action_id, pending_image_action, validate_media_result,
)
from ai_comic_drama_workflow.v6_protocol import envelope_digest, envelope_input_digest


def stamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save_json(root: Path, uri: str, value: object) -> str:
    path = root / uri
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def png_bytes():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + bytes([80, 120, 160]) * 2) * 2))
            + chunk(b"IEND", b""))


class MediaHostTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        save_json(self.root, "project.json", {"schema_version": "5.0",
                                              "orchestration_protocol": "6.0",
                                              "project_id": "DEMO", "delivery": "full"})
        self.prompt_sha = save_json(self.root, "prompts/asset.txt", {"prompt": "synthetic image"})
        self.task = {"kind": "image", "stage": 5, "task_id": "IMAGE_TASK",
                     "context_fingerprint": "a" * 64, "prompt": {"uri": "prompts/asset.txt",
                     "sha256": self.prompt_sha}, "job": {"references": []}}
        self.envelope = {"schema": "task-envelope/6.0", "project_id": "DEMO",
                         "node_id": "visual_media", "task_id": "IMAGE_TASK", "batch": 1,
                         "role": "image_host", "execution_class": "external_image",
                         "scope": {"kind": "asset", "ids": ["ASSET1"]},
                         "input_revision": 0, "inputs": [], "input_digest": "",
                         "module": None, "resources": [],
                         "expected_artifacts": [{"slot": "ASSET1", "kind": "ReferenceImage",
                                                 "uri_prefix": "runtime/v6/candidates/IMAGE_TASK/1/"}],
                         "validators": [{"id": "image_call_evidence", "kind": "evidence"},
                                        {"id": "image_visual_review", "kind": "media"}],
                         "dependencies": [], "handoffs": []}
        self.envelope["input_digest"] = envelope_input_digest(self.envelope)
        self.media_uri = "runtime/v6/candidates/IMAGE_TASK/1/image.png"
        image = self.root / self.media_uri
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(png_bytes())
        self.media_sha = hashlib.sha256(image.read_bytes()).hexdigest()
        self.source_uri = "provided/original.png"
        source = self.root / self.source_uri
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(image.read_bytes())
        save_json(self.root, "state.json", {"inflight": None})

    def completed(self):
        record = {"schema": "image-host-record/6.0", "action_id": image_action_id(self.envelope),
                  "task_id": "IMAGE_TASK", "batch": 1,
                  "task_digest": envelope_digest(self.envelope), "provider": "provided",
                  "tool": "provided", "tool_call_id": None, "status": "COMPLETED",
                  "submitted_at": stamp(), "observed_at": stamp(),
                  "tool_result_uri": None, "tool_result_sha256": None,
                  "source_uri": self.source_uri, "source_sha256": self.media_sha,
                  "media_uri": self.media_uri, "media_sha256": self.media_sha,
                  "error": None}
        raw = (json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n").encode()
        host_sha = hashlib.sha256(raw).hexdigest()
        host_uri = f"runtime/v6/host-evidence/{host_sha}.json"
        save_json(self.root, host_uri, record)
        role_result = {"schema": "role-result/5.0", "task_id": "IMAGE_TASK",
                       "context_fingerprint": "a" * 64, "checks": ["Synthetic byte check"],
                       "conflicts": [], "unresolved": [],
                       "media": {"path": str(self.root / self.media_uri), "sha256": self.media_sha,
                                 "provider": "provided",
                                 "call_evidence": f"v6-image-host-record:{host_sha}:provided:provided",
                                 "input_bindings": [],
                                 "visual_review": {"status": "PASS", "sha256": self.media_sha,
                                                   "findings": ["Synthetic decoder finding"]}}}
        result_uri = "runtime/v6/candidates/IMAGE_TASK/1/role-result.json"
        result_sha = save_json(self.root, result_uri, role_result)
        candidate = {"schema": "candidate-result/6.0", "task_id": "IMAGE_TASK",
                     "batch": 1, "agent_id": "image_host",
                     "input_digest": self.envelope["input_digest"],
                     "result_uri": result_uri, "result_sha256": result_sha,
                     "artifacts": [{"slot": "ASSET1", "kind": "ReferenceImage",
                                    "uri": self.media_uri, "sha256": self.media_sha}],
                     "module_receipts": [],
                     "checks": [{"id": spec["id"], "status": "PASS", "evidence": [host_uri]}
                                for spec in self.envelope["validators"]],
                     "handoffs": [], "unresolved": [],
                     "host_record_uri": host_uri, "host_record_sha256": host_sha}
        return candidate

    def test_provided_media_is_byte_bound_and_inflight_is_lookup_only(self):
        action = pending_image_action(self.envelope, self.task, self.root)
        self.assertEqual(action["kind"], "IMPORT_PROVIDED")
        self.assertEqual(action["allowed_providers"], ["provided"])
        self.assertFalse(action["generation_authorization_required"])
        candidate = self.completed()
        checked = validate_media_result(self.root, self.envelope, self.task, candidate)
        self.assertEqual(checked["media_sha256"], self.media_sha)
        save_json(self.root, "state.json", {"inflight": {"task_id": "IMAGE_TASK"}})
        self.assertEqual(pending_image_action(self.envelope, self.task, self.root)["kind"],
                         "RECONCILE_ONLY")
        save_json(self.root, "state.json", {"inflight": None,
                                            "host": {"providers": ["provided", "image_gen"],
                                                     "image_tools": ["image_gen.imagegen"]}})
        offer = pending_image_action(self.envelope, self.task, self.root)
        self.assertEqual(offer["kind"], "CHOOSE_PROVIDER")
        self.assertTrue(offer["generation_authorization_required"])

    def test_changed_review_or_call_record_is_rejected(self):
        candidate = self.completed()
        result_path = self.root / candidate["result_uri"]
        result = json.loads(result_path.read_text())
        result["media"]["visual_review"]["sha256"] = "f" * 64
        candidate["result_sha256"] = save_json(self.root, candidate["result_uri"], result)
        with self.assertRaisesRegex(ValueError, "Visual review"):
            validate_media_result(self.root, self.envelope, self.task, candidate)
        candidate = self.completed()
        candidate["host_record_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "bytes missing or changed"):
            validate_media_result(self.root, self.envelope, self.task, candidate)


if __name__ == "__main__":
    unittest.main()
