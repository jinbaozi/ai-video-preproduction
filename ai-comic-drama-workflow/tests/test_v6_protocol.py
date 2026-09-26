"""V6 evidence and transition gates using local synthetic files only."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ai_comic_drama_workflow.v5_modules import ROOT, read
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.production import _sha
from ai_comic_drama_workflow.v6_kernel import V6StateError, V6TaskKernel
from ai_comic_drama_workflow.v6_media_host import pending_image_action, store_image_action
from ai_comic_drama_workflow.v6_protocol import (
    V6ProtocolError, candidate_digest, envelope_digest, envelope_input_digest,
    expected_dispatch_id, expected_review_dispatch_id,
    validate_v6_protocol,
)


def save(root: Path, uri: str, data: object) -> str:
    path = root / uri
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n").encode()
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class V6ProtocolTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        save(self.root, "project.json", {
            "schema_version": "5.0", "orchestration_protocol": "6.0",
            "project_id": "DEMO", "delivery": "full", "production_target": "none",
        })
        self.video_sha = save(self.root, "sources/reference.mp4", {"synthetic": "video bytes"})
        save(self.root, "state.json", {"sources": [{"id": "SRC1", "uri": "sources/reference.mp4",
                                                   "sha256": self.video_sha}]})
        shutil.copyfile(ROOT / "modules.lock.json", self.root / "modules.lock.json")
        self.kernel = V6TaskKernel(self.root)

    def envelope(self, node_id: str, task_id: str, *, batch: int = 1, dependencies=()):
        graph = read(ROOT / "workflow-v6.json")
        node = next(item for item in graph["nodes"] if item["id"] == node_id)
        module = None
        if node["locked_skill"]:
            lock = read(self.root / "modules.lock.json")["modules"][node["locked_skill"]]
            module = {"name": node["locked_skill"], "version": lock["version"], "sha256": lock["sha256"]}
            archive = self.root / "runtime/module-archives" / (lock["sha256"] + ".skill")
            archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "assets/bundled-skills" / (node["locked_skill"] + ".skill"), archive)
        cls = {"kernel": "system", "specialist": "professional", "reviewer": "review"}.get(node["executor_kind"], "local_media")
        prefix = f"runtime/v6/candidates/{task_id}/{batch}/"
        outputs = [{"slot": f"{task_id}:{kind}", "kind": kind, "uri_prefix": prefix}
                   for kind in node["output_types"]]
        handoffs = ([{"requirement_id": "source_contract", "source_slot": "source",
                      "source_version": 1, "target_slot": outputs[0]["slot"],
                      "target_pointer": "", "channel": "artifact"}]
                    if node["handoff_required"] else [])
        envelope = {"schema": "task-envelope/6.0", "project_id": "DEMO",
                    "node_id": node_id, "task_id": task_id, "batch": batch,
                    "role": node["role"], "execution_class": cls,
                    "scope": {"kind": node["scope"], "ids": []},
                    "input_revision": 0,
                    "inputs": [{"slot": "source", "uri": "sources/reference.mp4",
                                "sha256": self.video_sha, "version": 1}],
                    "input_digest": "", "module": module, "resources": [],
                    "expected_artifacts": outputs,
                    "validators": [{"id": name, "kind": "evidence"} for name in node["checkers"]],
                    "dependencies": [{"task_id": item} for item in dependencies],
                    "handoffs": handoffs}
        envelope["input_digest"] = envelope_input_digest(envelope)
        return envelope

    def event(self, task_id: str, to_state: str, reason: str, command_id: str, *, checks=(),
              evidence=(), affected_outputs=(), actor_kind="kernel", error=None):
        state = self.kernel.snapshot()
        task = state["tasks"][task_id]
        item = {"schema": "state-event/6.0", "command_id": command_id,
                "expected_revision": state["revision"], "task_id": task_id,
                "batch": task["envelope"]["batch"], "object_version": task["version"],
                "from_state": task["state"], "to_state": to_state,
                "reason": reason, "check_results": list(checks), "evidence": list(evidence),
                "affected_outputs": list(affected_outputs), "actor_kind": actor_kind,
                "actor_id": "kernel" if actor_kind == "kernel" else "codex-host", "at": now()}
        if error is not None:
            item["error"] = error
        return item

    def candidate(self, envelope, agent_id="kernel"):
        artifacts = []
        prefix = envelope["expected_artifacts"][0]["uri_prefix"]
        for spec in envelope["expected_artifacts"]:
            uri = prefix + spec["kind"] + ".json"
            artifacts.append({"slot": spec["slot"], "kind": spec["kind"],
                              "uri": uri, "sha256": save(self.root, uri, {"kind": spec["kind"]})})
        evidence = artifacts[0]["uri"]
        return {"schema": "candidate-result/6.0", "task_id": envelope["task_id"],
                "batch": envelope["batch"], "agent_id": agent_id,
                "input_digest": envelope["input_digest"],
                "result_uri": None, "result_sha256": None, "artifacts": artifacts,
                "module_receipts": [] if envelope["module"] is None else [envelope["module"]],
                "checks": [{"id": item["id"], "status": "PASS", "evidence": [evidence]}
                           for item in envelope["validators"]],
                "handoffs": [{"requirement_id": item["requirement_id"],
                              "source_slot": item["source_slot"],
                              "source_version": item["source_version"], "target_slot": item["target_slot"],
                              "target_pointer": item["target_pointer"], "channel": item["channel"],
                              "evidence": [evidence]} for item in envelope["handoffs"]],
                "unresolved": []}

    def receipt(self, envelope, agent_id, *, review=False):
        dispatch_id = (expected_review_dispatch_id(envelope) if review else expected_dispatch_id(envelope))
        # The live Codex collaboration.spawn_agent result exposes task_name.
        raw = {"task_name": agent_id}
        raw_sha = hashlib.sha256((json.dumps(raw, ensure_ascii=False, sort_keys=True) + "\n").encode()).hexdigest()
        uri = f"runtime/v6/host-evidence/{raw_sha}.json"
        save(self.root, uri, raw)
        return {"schema": "dispatch-receipt/6.0", "task_id": envelope["task_id"],
                "batch": envelope["batch"], "host": "codex",
                "host_tool": "collaboration.spawn_agent", "host_call_id": None,
                "dispatch_id": dispatch_id, "action_id": dispatch_id,
                "agent_id": agent_id, "task_digest": envelope_digest(envelope),
                "status": "RUNNING", "sent_at": now(), "observed_at": now(),
                "result_uri": None, "error": None,
                "tool_result_uri": uri, "tool_result_sha256": raw_sha}

    def result_message(self, task_id, sender_id, payload, message_id):
        task = self.kernel.inspect(task_id)
        batch = task["envelope"]["batch"]
        directory = "reviews" if task["state"] == "REVIEW_REQUIRED" else "candidates"
        uri = f"runtime/v6/{directory}/{task_id}/{batch}/{message_id}.json"
        sha = save(self.root, uri, payload)
        message = {"schema": "agent-message/6.0", "message_id": message_id,
                   "task_id": task_id, "batch": batch, "sender_id": sender_id,
                   "recipient_id": "kernel", "in_reply_to": None, "type": "RESULT",
                   "summary": "Synthetic protocol result", "evidence": [uri], "at": now(),
                   "subject_uri": uri, "subject_sha256": sha}
        self.kernel.record_message(message, "message-" + message_id,
                                   self.kernel.snapshot()["revision"])

    def create_sources(self):
        envelope = self.envelope("sources", "sources")
        state = self.kernel.create_task(envelope, "create-sources", 0)
        candidate = self.candidate(envelope)
        event = self.event("sources", "ACCEPTED", "SYSTEM_VALIDATED", "accept-sources",
                           checks=candidate["checks"], evidence=[candidate["artifacts"][0]["uri"]])
        state = self.kernel.transition(event, candidate=candidate)
        self.assertEqual(state["tasks"]["sources"]["state"], "ACCEPTED")
        return envelope

    def seed_accepted_predecessors(self, rows):
        def mutate(state, artifacts):
            for task_id, node_id, scope in rows:
                envelope = self.envelope(node_id, task_id)
                envelope["scope"] = scope
                envelope["input_digest"] = envelope_input_digest(envelope)
                state["tasks"][task_id] = {
                    "envelope": envelope, "state": "ACCEPTED", "version": 1,
                    "receipt": None, "receipt_history": [], "review_dispatch": None,
                    "candidate": None, "review": None, "validation": [], "messages": [],
                    "evidence_hashes": {}, "history": [], "failure_counts": {}}
        self.kernel._apply("seed_synthetic_predecessors", {"rows": rows},
                           "seed-predecessors", self.kernel.snapshot()["revision"], mutate)

    def test_strict_schema_and_graph_assignment(self):
        envelope = self.envelope("sources", "sources")
        bad = deepcopy(envelope)
        bad["surprise"] = True
        with self.assertRaises(V6ProtocolError):
            self.kernel.create_task(bad, "bad", 0)
        bad = deepcopy(envelope)
        bad["validators"] = []
        with self.assertRaisesRegex(V6StateError, "GRAPH_CHECKERS"):
            self.kernel.create_task(bad, "bad-checkers", 0)
        bad = deepcopy(envelope)
        bad["batch"] = "1"
        with self.assertRaises(V6ProtocolError):
            self.kernel.create_task(bad, "bad-type", 0)
        bad = deepcopy(envelope)
        del bad["input_digest"]
        with self.assertRaises(V6ProtocolError):
            self.kernel.create_task(bad, "missing-condition", 0)
        bad = deepcopy(envelope)
        bad["role"] = "fake-role"
        bad["input_digest"] = envelope_input_digest(bad)
        with self.assertRaisesRegex(V6StateError, "GRAPH_ASSIGNMENT"):
            self.kernel.create_task(bad, "wrong-role", 0)
        self.assertEqual(self.kernel.snapshot()["revision"], 0)

    def test_observation_register_is_closed_and_byte_addressed(self):
        register = {"schema": "observation-register/6.0", "bundles": [{
            "source_id": "SRC_1", "directory": "runtime/v6/candidates/observe/1/SRC_1/",
            "observation_sha256": "a" * 64, "review_sha256": "b" * 64}]}
        validate_v6_protocol("observation-register", register)
        extra = deepcopy(register)
        extra["bundles"][0]["unknown"] = "x"
        with self.assertRaises(V6ProtocolError):
            validate_v6_protocol("observation-register", extra)
        traversal = deepcopy(register)
        traversal["bundles"][0]["directory"] = "runtime/v6/candidates/observe/1/../"
        with self.assertRaises(V6ProtocolError):
            validate_v6_protocol("observation-register", traversal)

    def test_candidate_checks_and_handoffs_require_evidence(self):
        sources = self.create_sources()
        envelope = self.envelope("reference_observation", "observe", dependencies=["sources"])
        self.kernel.create_task(envelope, "create-observe", self.kernel.snapshot()["revision"])
        candidate = self.candidate(envelope, "/root/creator")
        without_check_proof = deepcopy(candidate)
        without_check_proof["checks"][0]["evidence"] = []
        with self.assertRaises(V6ProtocolError):
            validate_v6_protocol("candidate-result", without_check_proof)
        without_handoff_proof = deepcopy(candidate)
        without_handoff_proof["handoffs"][0]["evidence"] = []
        with self.assertRaises(V6ProtocolError):
            validate_v6_protocol("candidate-result", without_handoff_proof)
        sources_candidate = self.candidate(sources)
        sources_candidate["checks"][0]["evidence"] = ["runtime/v6/candidates/sources/1/missing.json"]
        with self.assertRaisesRegex(V6StateError, "CHECK_EVIDENCE"):
            self.kernel._verify_candidate(self.kernel.inspect("sources"), sources_candidate)

    def test_image_skip_uses_verified_v5_job_fact(self):
        envelope = self.envelope("visual_media", "image_task")
        with self.assertRaisesRegex(V6StateError, "APPLICABILITY_FACT"):
            self.kernel._stage_applies(envelope)
        with (patch.object(V5Kernel, "valid", side_effect=lambda slot: slot in ("director", "art:S1")),
              patch.object(V5Kernel, "data", return_value={"scenes": [{"id": "S1"}]}),
              patch.object(V5Kernel, "image_jobs", return_value=[])):
            self.assertEqual(self.kernel._stage_applies(envelope),
                             (False, {"reason_code": "NO_APPLICABLE_ASSETS",
                                      "affected_outputs": ["ReferenceImage"]}))
        save(self.root, "project.json", {"schema_version": "5.0", "orchestration_protocol": "6.0",
                                         "project_id": "DEMO", "delivery": "text-only",
                                         "production_target": "none"})
        self.assertEqual(self.kernel._stage_applies(envelope),
                         (False, {"reason_code": "TEXT_ONLY", "affected_outputs": ["ReferenceImage"]}))

    def test_nonartifact_check_evidence_is_frozen_after_acceptance(self):
        envelope = self.envelope("sources", "sources")
        self.kernel.create_task(envelope, "create-evidence", 0)
        candidate = self.candidate(envelope)
        proof_uri = "runtime/v6/candidates/sources/1/check-proof.json"
        save(self.root, proof_uri, {"checked": True})
        candidate["checks"][0]["evidence"] = [proof_uri]
        self.kernel.transition(self.event("sources", "ACCEPTED", "SYSTEM_VALIDATED", "accept-evidence",
                                          checks=candidate["checks"]), candidate=candidate)
        save(self.root, proof_uri, {"checked": False})
        with self.assertRaisesRegex(V6StateError, "FILE_HASH"):
            self.kernel.snapshot()

    def test_replaced_delivery_index_remains_checkable_from_its_archive(self):
        envelope = self.envelope("sources", "sources")
        self.kernel.create_task(envelope, "create-delivery-evidence", 0)
        digest = save(self.root, "delivery/index.json", {"status": "OLD"})
        candidate = self.candidate(envelope)
        candidate["checks"][0]["evidence"] = ["delivery/index.json"]
        self.kernel.transition(self.event("sources", "ACCEPTED", "SYSTEM_VALIDATED",
                                          "accept-delivery-evidence", checks=candidate["checks"]),
                               candidate=candidate)
        archive = self.root / "runtime/v6/evidence/byte-archive" / digest
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes((self.root / "delivery/index.json").read_bytes())
        save(self.root, "delivery/index.json", {"status": "NEW"})
        self.kernel.snapshot()

    def test_reused_result_requires_migration_byte_binding(self):
        envelope = self.envelope("sources", "sources")
        candidate = self.candidate(envelope)
        artifact = candidate["artifacts"][0]
        legacy_uri = "imports/legacy/old-source-registry.json"
        source_path = self.root / legacy_uri
        source_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.root / artifact["uri"], source_path)
        report_sha = save(self.root, "imports/migration.json", {
            "schema": "migration/5.0", "files": [{"uri": legacy_uri,
                                                   "sha256": artifact["sha256"]}]})
        envelope["inputs"].append({"slot": "migration_report", "uri": "imports/migration.json",
                                   "sha256": report_sha, "version": 0})
        envelope["input_digest"] = envelope_input_digest(envelope)
        candidate["input_digest"] = envelope["input_digest"]
        result_uri = "runtime/v6/candidates/sources/1/role-result.json"
        candidate["result_uri"] = result_uri
        candidate["result_sha256"] = save(self.root, result_uri, {
            "reused": True, "artifact": artifact["uri"], "artifact_sha256": artifact["sha256"]})
        task = {"envelope": envelope, "receipt": None}
        with self.assertRaisesRegex(V6StateError, "REUSE_PROVENANCE"):
            self.kernel._verify_candidate(task, candidate)
        candidate["reuse_bindings"] = [{"source_uri": legacy_uri, "source_sha256": "f" * 64,
                                        "target_slot": artifact["slot"]}]
        with self.assertRaisesRegex(V6StateError, "REUSE_PROVENANCE"):
            self.kernel._verify_candidate(task, candidate)
        candidate["reuse_bindings"][0]["source_sha256"] = artifact["sha256"]
        self.kernel._verify_candidate(task, candidate)

    def test_retry_revision_does_not_hide_repeated_check_failure(self):
        self.create_sources()
        for batch in (1, 2):
            envelope = self.envelope("reference_observation", "observe", batch=batch,
                                     dependencies=["sources"])
            envelope["input_revision"] = batch
            envelope["input_digest"] = envelope_input_digest(envelope)
            self.kernel.create_task(envelope, f"create-observe-{batch}", self.kernel.snapshot()["revision"])
            self.kernel.transition(self.event("observe", "READY", "DEPENDENCIES_SATISFIED", f"ready-{batch}"))
            self.kernel.transition(self.event("observe", "DISPATCHING", "DISPATCH_REQUESTED",
                                              f"dispatch-{batch}"))
            creator = f"/root/creator-{batch}"
            self.kernel.record_dispatch(self.event("observe", "RUNNING", "DISPATCH_CONFIRMED",
                                                   f"run-{batch}"), self.receipt(envelope, creator))
            candidate = self.candidate(envelope, creator)
            self.result_message("observe", creator, candidate, f"result-message-{batch}")
            self.kernel.submit_candidate(self.event("observe", "RESULT_SUBMITTED", "RESULT_RECEIVED",
                                                    f"result-{batch}"), candidate)
            self.kernel.transition(self.event("observe", "VALIDATING", "VALIDATION_STARTED",
                                              f"validate-{batch}"))
            failed = [{"id": item["id"], "status": "FAIL", "evidence": item["evidence"]}
                      for item in candidate["checks"]]
            error = {"code": "CHECK_FAILED", "owner_node": "reference_observation",
                     "failed_check": failed[0]["id"], "evidence": failed[0]["evidence"],
                     "retryable": True, "recovery_action": "REVISE"}
            self.kernel.transition(self.event("observe", "FAILED", "VALIDATION_FAILED", f"failed-{batch}",
                                              checks=failed, error=error))
        retry = self.envelope("reference_observation", "observe", batch=3,
                              dependencies=["sources"])
        retry["input_revision"] = 3
        retry["input_digest"] = envelope_input_digest(retry)
        with self.assertRaisesRegex(V6StateError, "REVISE_REQUIRED"):
            self.kernel.create_task(retry, "unchanged-third-attempt", self.kernel.snapshot()["revision"])
        arbitrary = deepcopy(retry)
        arbitrary['inputs'].append({'slot': 'arbitrary_change', 'uri': 'sources/reference.mp4',
                                    'sha256': self.video_sha, 'version': 2})
        arbitrary['input_digest'] = envelope_input_digest(arbitrary)
        with self.assertRaisesRegex(V6StateError, 'REPAIR_REQUIRED'):
            self.kernel.create_task(arbitrary, 'unbound-third-attempt',
                                    self.kernel.snapshot()['revision'])

    def test_candidate_handoff_requires_the_frozen_source_slot(self):
        self.create_sources()
        envelope = self.envelope("reference_observation", "observe", dependencies=["sources"])
        self.kernel.create_task(envelope, "create-handoff", self.kernel.snapshot()["revision"])
        self.kernel.transition(self.event("observe", "READY", "DEPENDENCIES_SATISFIED", "ready-handoff"))
        self.kernel.transition(self.event("observe", "DISPATCHING", "DISPATCH_REQUESTED", "dispatch-handoff"))
        self.kernel.record_dispatch(self.event("observe", "RUNNING", "DISPATCH_CONFIRMED", "run-handoff"),
                                    self.receipt(envelope, "/root/creator"))
        candidate = self.candidate(envelope, "/root/creator")
        del candidate["handoffs"][0]["source_slot"]
        self.result_message("observe", "/root/creator", candidate, "bad-handoff-result")
        with self.assertRaises(V6ProtocolError):
            self.kernel.submit_candidate(self.event("observe", "RESULT_SUBMITTED", "RESULT_RECEIVED",
                                                    "bad-handoff"), candidate)

    def test_idempotency_review_identity_and_acceptance(self):
        self.create_sources()
        envelope = self.envelope("reference_observation", "observe", dependencies=["sources"])
        revision = self.kernel.snapshot()["revision"]
        original = self.kernel.create_task(envelope, "create-observe", revision)
        self.assertEqual(original, self.kernel.create_task(envelope, "create-observe", revision))
        conflicting = deepcopy(envelope)
        conflicting["input_revision"] += 1
        conflicting["input_digest"] = envelope_input_digest(conflicting)
        with self.assertRaisesRegex(V6StateError, "COMMAND_COLLISION"):
            self.kernel.create_task(conflicting, "create-observe", revision + 1)
        self.kernel.transition(self.event("observe", "READY", "DEPENDENCIES_SATISFIED", "ready"))
        with self.assertRaisesRegex(V6StateError, "ILLEGAL_TRANSITION"):
            self.kernel.transition(self.event("observe", "ACCEPTED", "REVIEW_PASSED", "bypass"))
        self.kernel.transition(self.event("observe", "DISPATCHING", "DISPATCH_REQUESTED", "dispatch"))
        receipt = self.receipt(envelope, "/root/creator")
        self.kernel.record_dispatch(self.event("observe", "RUNNING", "DISPATCH_CONFIRMED", "running",
                                                actor_kind="host"), receipt)
        candidate = self.candidate(envelope, "/root/creator")
        self.result_message("observe", "/root/creator", candidate, "creator-result")
        self.kernel.submit_candidate(self.event("observe", "RESULT_SUBMITTED", "RESULT_RECEIVED", "result"), candidate)
        self.kernel.transition(self.event("observe", "VALIDATING", "VALIDATION_STARTED", "validating"))
        self.kernel.transition(self.event("observe", "REVIEW_REQUIRED", "VALIDATION_PASSED", "validated",
                                          checks=candidate["checks"]))
        review_receipt = self.receipt(envelope, "/root/reviewer", review=True)
        self.kernel.register_review_dispatch(review_receipt, "review-dispatch", self.kernel.snapshot()["revision"])
        review = {"schema": "review-record/6.0", "task_id": "observe", "batch": 1,
                  "reviewer_agent_id": "/root/creator", "reviewer_dispatch_id": review_receipt["dispatch_id"],
                  "candidate_digest": candidate_digest(candidate),
                  "checks": [{"id": item["id"], "status": "PASS", "evidence": item["evidence"]}
                             for item in candidate["checks"]], "failure_owner": None, "at": now()}
        event = self.event("observe", "ACCEPTED", "REVIEW_PASSED", "accept-observe", checks=candidate["checks"])
        with self.assertRaisesRegex(V6StateError, "REVIEW_IDENTITY"):
            self.kernel.record_review(event, review)
        review["reviewer_agent_id"] = "/root/reviewer"
        wrong_uri = "runtime/v6/candidates/observe/1/reviewer-wrong-place.json"
        wrong_sha = save(self.root, wrong_uri, review)
        wrong_message = {"schema": "agent-message/6.0", "message_id": "reviewer-wrong-place",
                         "task_id": "observe", "batch": 1, "sender_id": "/root/reviewer",
                         "recipient_id": "kernel", "in_reply_to": None, "type": "RESULT",
                         "summary": "Review result in candidate directory", "evidence": [wrong_uri],
                         "at": now(), "subject_uri": wrong_uri, "subject_sha256": wrong_sha}
        with self.assertRaisesRegex(V6StateError, "RESULT_SCOPE"):
            self.kernel.record_message(wrong_message, "wrong-review-result", self.kernel.snapshot()["revision"])
        self.result_message("observe", "/root/reviewer", review, "reviewer-result")
        event = self.event("observe", "ACCEPTED", "REVIEW_PASSED", "accept-observe", checks=candidate["checks"])
        final = self.kernel.record_review(event, review)
        self.assertEqual(final["tasks"]["observe"]["state"], "ACCEPTED")
        self.assertIn(candidate["artifacts"][0]["slot"], final["artifacts"])
        self.assertEqual(self.kernel.recover(), final)

    def test_image_host_has_full_progress_path_and_unknown_reconciliation(self):
        envelope = self.envelope("visual_media", "image_task")
        envelope["execution_class"] = "external_image"
        envelope["input_digest"] = envelope_input_digest(envelope)
        self.kernel._applicability_context = lambda: {
            "delivery": "full", "production_target": "none",
            "observation_required": True, "visual_jobs_present": True}
        with patch.object(self.kernel, "_check_graph_envelope"):
            self.kernel.create_task(envelope, "create-image", 0)
        candidate = self.candidate(envelope, "image_host")
        with self.assertRaisesRegex(V6StateError, "SYSTEM_GATE"):
            self.kernel.transition(self.event("image_task", "ACCEPTED", "SYSTEM_VALIDATED", "host-bypass",
                                              checks=candidate["checks"]), candidate=candidate)
        self.kernel.transition(self.event("image_task", "READY", "DEPENDENCIES_SATISFIED", "image-ready"))
        self.kernel.transition(self.event("image_task", "DISPATCHING", "DISPATCH_REQUESTED", "image-dispatch"))
        prompt_sha = save(self.root, "sources/image-prompt.json", {"prompt": "synthetic"})
        v5_task = {"kind": "image", "task_id": "image_task", "stage": 5,
                   "prompt": {"uri": "sources/image-prompt.json", "sha256": prompt_sha},
                   "job": {"references": []}}
        action = pending_image_action(envelope, v5_task, self.root)
        action_uri, _ = store_image_action(self.root, action)
        save(self.root, "state.json", {"sources": [{"id": "SRC1", "uri": "sources/reference.mp4",
                                                  "sha256": self.video_sha}],
                                        "inflight": {"task_id": "image_task"}})
        with self.assertRaisesRegex(V6StateError, "HOST_START"):
            self.kernel.transition(self.event("image_task", "RUNNING", "DISPATCH_CONFIRMED", "wrong-host-start",
                                              evidence=[action_uri], actor_kind="host"))
        self.kernel.transition(self.event("image_task", "RUNNING", "HOST_EXECUTION_STARTED", "image-start",
                                          evidence=[action_uri], actor_kind="host"))
        error = {"code": "HOST_TIMEOUT", "owner_node": "visual_media",
                 "failed_check": "image_call_evidence", "evidence": [action_uri],
                 "retryable": False, "recovery_action": "RECONCILE"}
        self.kernel.transition(self.event("image_task", "UNKNOWN", "DISPATCH_UNCERTAIN", "image-unknown",
                                          evidence=[action_uri], actor_kind="host", error=error))
        self.kernel.transition(self.event("image_task", "RUNNING", "HOST_RECONCILED", "image-reconciled",
                                          evidence=[action_uri], actor_kind="host"))
        with patch.object(self.kernel, "_validate_host_candidate"):
            self.kernel.submit_candidate(self.event("image_task", "RESULT_SUBMITTED", "HOST_RESULT_RECEIVED",
                                                    "image-result", actor_kind="host"), candidate)
            self.kernel.transition(self.event("image_task", "VALIDATING", "VALIDATION_STARTED",
                                              "image-validating"))
            final = self.kernel.complete_host_task(
                self.event("image_task", "ACCEPTED", "HOST_EXECUTION_CONFIRMED", "image-accepted",
                           checks=candidate["checks"], actor_kind="host"), candidate)
        self.assertEqual(final["tasks"]["image_task"]["state"], "ACCEPTED")

    def test_video_host_start_rejects_another_ledger_scope(self):
        save(self.root, "project.json", {"schema_version": "5.0", "orchestration_protocol": "6.0",
                                         "project_id": "DEMO", "delivery": "full",
                                         "production_target": "video"})
        envelope = self.envelope("video_execution", "execution_task")
        envelope["execution_class"] = "external_video"
        envelope["scope"] = {"kind": "generation_request", "ids": ["EXE_1"]}
        envelope["input_digest"] = envelope_input_digest(envelope)
        with patch.object(self.kernel, "_check_graph_envelope"):
            self.kernel.create_task(envelope, "create-execution", 0)
        self.kernel.transition(self.event("execution_task", "READY", "DEPENDENCIES_SATISFIED", "exec-ready"))
        self.kernel.transition(self.event("execution_task", "DISPATCHING", "DISPATCH_REQUESTED", "exec-dispatch"))
        wrong_uri = "runtime/production/takes/EXE_1.json"
        save(self.root, wrong_uri, {"id": "EXE_1"})
        with self.assertRaisesRegex(V6StateError, "HOST_PROGRESS"):
            self.kernel.transition(self.event("execution_task", "RUNNING", "HOST_EXECUTION_STARTED",
                                              "wrong-ledger-node", evidence=[wrong_uri], actor_kind="host"))
        wrong_uri = "runtime/production/executions/EXE_2.json"
        save(self.root, wrong_uri, {"id": "EXE_2"})
        with self.assertRaisesRegex(V6StateError, "HOST_PROGRESS"):
            self.kernel.transition(self.event("execution_task", "RUNNING", "HOST_EXECUTION_STARTED",
                                              "wrong-ledger-scope", evidence=[wrong_uri], actor_kind="host"))
        uri = "runtime/production/executions/EXE_1.json"
        submitted = {"id": "EXE_1", "state": "SUBMITTED", "version": 1}
        save(self.root, uri, submitted)
        final = self.kernel.transition(self.event("execution_task", "RUNNING", "HOST_EXECUTION_STARTED",
                                                "right-ledger", evidence=[uri], actor_kind="host"))
        self.assertEqual(final["tasks"]["execution_task"]["state"], "RUNNING")
        candidate = self.candidate(envelope, "production_host")
        candidate["artifacts"][0]["sha256"] = save(
            self.root, candidate["artifacts"][0]["uri"], submitted)
        candidate["host_record_uri"] = uri
        candidate["host_record_sha256"] = hashlib.sha256((self.root / uri).read_bytes()).hexdigest()
        candidate["checks"][0]["evidence"] = [uri]
        with patch.object(self.kernel, "_validate_host_candidate"):
            self.kernel.submit_candidate(self.event("execution_task", "RESULT_SUBMITTED",
                                                    "HOST_RESULT_RECEIVED", "exec-result", actor_kind="host"),
                                         candidate)
            self.kernel.transition(self.event("execution_task", "VALIDATING", "VALIDATION_STARTED",
                                              "exec-validating"))
            self.kernel.complete_host_task(self.event("execution_task", "ACCEPTED",
                                                      "HOST_EXECUTION_CONFIRMED", "exec-accepted",
                                                      checks=candidate["checks"], actor_kind="host"), candidate)
        unknown = {"id": "EXE_1", "state": "UNKNOWN", "version": 2}
        event_uri = "runtime/production/execution-events/EXE_1/0002.json"
        save(self.root, event_uri, {"record_id": "EXE_1", "version": 2,
                                   "to": "UNKNOWN", "record": unknown,
                                   "record_sha256": _sha(unknown)})
        save(self.root, uri, {"id": "EXE_1", "state": "SUCCEEDED", "version": 3})
        self.kernel.snapshot()  # Execution records can advance in the production ledger.
        with self.assertRaisesRegex(V6StateError, "STALE_UNPROVEN"):
            self.kernel.transition(self.event("execution_task", "STALE", "HOST_RECORD_CHANGED",
                                              "exec-missing-event", evidence=[uri]))
        stale = self.kernel.transition(self.event("execution_task", "STALE", "HOST_RECORD_CHANGED",
                                                  "exec-invalidated", evidence=[uri, event_uri]))
        self.assertEqual(stale["tasks"]["execution_task"]["state"], "STALE")

    def test_create_task_rejects_partial_asset_and_shot_predecessors(self):
        project_scope = {"kind": "project", "ids": []}
        asset_a = {"kind": "asset", "ids": ["ASSET_A"]}
        asset_b = {"kind": "asset", "ids": ["ASSET_B"]}
        shot_a = {"kind": "shot", "ids": ["SHOT_A"]}
        shot_b = {"kind": "shot", "ids": ["SHOT_B"]}
        self.seed_accepted_predecessors([
            ("story", "storyboard", project_scope), ("control", "control", project_scope),
            ("visual_a", "visual_prompts", asset_a), ("visual_b", "visual_prompts", asset_b),
            ("select_a", "take_selection", shot_a), ("select_b", "take_selection", shot_b),
        ])
        scopes = {"board_prompts": [{"kind": "panel", "ids": ["PANEL_A"]}],
                  "storyboard": [project_scope], "control": [project_scope],
                  "visual_prompts": [asset_a, asset_b],
                  "adjacent_acceptance": [project_scope], "take_selection": [shot_a, shot_b]}
        board = self.envelope("board_prompts", "board", dependencies=["story", "control", "visual_a"])
        board["scope"] = {"kind": "panel", "ids": ["PANEL_A"]}
        board["input_digest"] = envelope_input_digest(board)
        with patch.object(self.kernel, "_required_scopes", side_effect=lambda node: scopes[node]):
            with self.assertRaisesRegex(V6StateError, "GRAPH_DEPENDENCIES"):
                self.kernel.create_task(board, "partial-assets", self.kernel.snapshot()["revision"])
            adjacent = self.envelope("adjacent_acceptance", "adjacent", dependencies=["select_a"])
            adjacent["input_digest"] = envelope_input_digest(adjacent)
            with self.assertRaisesRegex(V6StateError, "GRAPH_DEPENDENCIES"):
                self.kernel.create_task(adjacent, "partial-shots", self.kernel.snapshot()["revision"])

    def test_create_task_rejects_one_missing_art_scene(self):
        project_scope = {"kind": "project", "ids": []}
        art_a = {"kind": "scene", "ids": ["SCENE_A"]}
        art_b = {"kind": "scene", "ids": ["SCENE_B"]}
        asset_a = {"kind": "asset", "ids": ["ASSET_A"]}
        asset_b = {"kind": "asset", "ids": ["ASSET_B"]}
        self.seed_accepted_predecessors([
            ("canon", "canon", project_scope), ("director", "director", project_scope),
            ("art_a", "art", art_a), ("art_b", "art", art_b),
            ("media_a", "visual_media", asset_a), ("media_b", "visual_media", asset_b),
        ])
        scopes = {"storyboard": [project_scope], "canon": [project_scope],
                  "director": [project_scope], "art": [art_a, art_b],
                  "visual_media": [asset_a, asset_b]}
        board = self.envelope("storyboard", "board",
                              dependencies=["canon", "director", "art_a", "media_a", "media_b"])
        with patch.object(self.kernel, "_required_scopes", side_effect=lambda node: scopes[node]):
            with self.assertRaisesRegex(V6StateError, "GRAPH_DEPENDENCIES"):
                self.kernel.create_task(board, "partial-scenes", self.kernel.snapshot()["revision"])

    def test_overlap_cancel_late_result_and_wrong_dispatch_identity(self):
        self.create_sources()
        envelope = self.envelope("reference_observation", "observe_a", dependencies=["sources"])
        self.kernel.create_task(envelope, "create-a", self.kernel.snapshot()["revision"])
        other = self.envelope("reference_observation", "observe_b", dependencies=["sources"])
        with self.assertRaisesRegex(V6StateError, "SCOPE_CONFLICT"):
            self.kernel.create_task(other, "create-b", self.kernel.snapshot()["revision"])
        self.kernel.transition(self.event("observe_a", "READY", "DEPENDENCIES_SATISFIED", "ready-a"))
        self.kernel.transition(self.event("observe_a", "DISPATCHING", "DISPATCH_REQUESTED", "dispatch-a"))
        wrong = self.receipt(envelope, "/root/creator")
        wrong["task_digest"] = "f" * 64
        with self.assertRaisesRegex(V6StateError, "DISPATCH_BINDING"):
            self.kernel.record_dispatch(self.event("observe_a", "RUNNING", "DISPATCH_CONFIRMED", "wrong-receipt"), wrong)
        self.kernel.transition(self.event("observe_a", "CANCELLED", "CANCEL_REQUESTED", "cancel-a"))
        with self.assertRaisesRegex(V6StateError, "ILLEGAL_TRANSITION"):
            self.kernel.record_dispatch(self.event("observe_a", "RUNNING", "DISPATCH_CONFIRMED", "late-receipt"),
                                        self.receipt(envelope, "/root/creator"))

    def test_unknown_dispatch_reconciles_same_action_without_resubmission(self):
        self.create_sources()
        envelope = self.envelope("reference_observation", "observe", dependencies=["sources"])
        self.kernel.create_task(envelope, "create-unknown", self.kernel.snapshot()["revision"])
        self.kernel.transition(self.event("observe", "READY", "DEPENDENCIES_SATISFIED", "ready-unknown"))
        self.kernel.transition(self.event("observe", "DISPATCHING", "DISPATCH_REQUESTED", "dispatch-unknown"))
        receipt = self.receipt(envelope, "/root/creator")
        receipt.update({"status": "UNKNOWN", "agent_id": None, "tool_result_uri": None,
                        "tool_result_sha256": None})
        error = {"code": "HOST_TIMEOUT", "owner_node": "reference_observation",
                 "failed_check": None, "evidence": ["host:timeout"], "retryable": False,
                 "recovery_action": "RECONCILE"}
        self.kernel.record_dispatch(self.event("observe", "UNKNOWN", "DISPATCH_UNCERTAIN", "unknown",
                                               error=error), receipt)
        self.assertEqual(self.kernel.pending_action("observe")["kind"], "reconcile")
        raw = {"agents": [{"agent_name": "/root/creator"}]}
        checksum = hashlib.sha256((json.dumps(raw, sort_keys=True) + "\n").encode()).hexdigest()
        uri = f"runtime/v6/host-evidence/{checksum}.json"
        save(self.root, uri, raw)
        found = self.receipt(envelope, "/root/creator")
        found.update({"host_tool": "collaboration.list_agents", "tool_result_uri": uri,
                      "tool_result_sha256": checksum})
        state = self.kernel.record_dispatch(self.event("observe", "RUNNING", "HOST_RECONCILED",
                                                       "reconciled", evidence=[uri], actor_kind="host"), found)
        self.assertEqual(state["tasks"]["observe"]["state"], "RUNNING")
        self.assertEqual(len(state["tasks"]["observe"]["receipt_history"]), 2)

    def test_transaction_failure_restores_every_ledger_file(self):
        envelope = self.envelope("sources", "sources")
        original_write = self.kernel._write
        def fail_after_state(relative, value):
            if relative == "events.json":
                raise OSError("synthetic crash during event commit")
            return original_write(relative, value)
        with patch.object(self.kernel, "_write", side_effect=fail_after_state):
            with self.assertRaisesRegex(OSError, "synthetic crash"):
                self.kernel.create_task(envelope, "crash", 0)
        self.assertEqual(self.kernel.recover()["revision"], 0)
        self.assertFalse((self.root / "runtime/v6/state.json").exists())

    def test_changed_input_stales_accepted_task_and_rejects_old_bytes(self):
        self.create_sources()
        source_uri = "sources/reference.mp4"
        save(self.root, source_uri, {"changed": True})
        self.kernel.transition(self.event("sources", "STALE", "INPUT_CHANGED", "stale-sources"))
        self.assertEqual(self.kernel.snapshot()["artifacts"], {})
        with self.assertRaisesRegex(V6StateError, "FILE_HASH"):
            self.kernel.create_task(self.envelope("reference_observation", "late", dependencies=["sources"]),
                                    "late-create", self.kernel.snapshot()["revision"])


if __name__ == "__main__":
    unittest.main()
