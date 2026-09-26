"""Evidence-gated V6 task state and append-only command journal.

The Codex host performs agent calls. This kernel only accepts their recorded
receipts and never represents a Python method call as an agent dispatch.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import json
import subprocess
import sys

from .transactions import before_write, transaction
from .utils import atomic_write, canonical_json, ensure_relative_path
from .v5_modules import ROOT, digest_file, native_validate, module_path, read
from .v6_graph import load_graph, stage_applicability, stage_by_id
from .v6_stage_adapter import predecessor_task_ids
from .v6_runtime_fingerprint import runtime_resources_changed
from .v6_protocol import (
    V6ProtocolError, candidate_digest, envelope_digest, envelope_input_digest,
    envelope_semantic_digest,
    expected_dispatch_id, expected_review_dispatch_id, sha256_json,
    validate_v6_protocol,
)


MAIN_PATH = {
    "PENDING": {"READY", "ACCEPTED", "NOT_APPLICABLE", "BLOCKED", "CANCELLED"},
    "READY": {"DISPATCHING", "BLOCKED", "STALE", "CANCELLED"},
    "DISPATCHING": {"RUNNING", "UNKNOWN", "FAILED", "STALE", "CANCELLED"},
    "RUNNING": {"RESULT_SUBMITTED", "UNKNOWN", "FAILED", "STALE", "CANCELLED"},
    "RESULT_SUBMITTED": {"VALIDATING", "FAILED", "STALE", "CANCELLED"},
    "VALIDATING": {"REVIEW_REQUIRED", "ACCEPTED", "FAILED", "BLOCKED", "STALE", "CANCELLED"},
    "REVIEW_REQUIRED": {"ACCEPTED", "FAILED", "BLOCKED", "STALE", "CANCELLED"},
    "UNKNOWN": {"RUNNING", "FAILED", "CANCELLED"},
    "BLOCKED": {"READY", "STALE", "CANCELLED"},
    "FAILED": {"STALE", "CANCELLED"},
    "ACCEPTED": {"STALE"},
    "NOT_APPLICABLE": {"STALE"},
    "STALE": {"CANCELLED"},
    "CANCELLED": set(),
}
SKIP_REASONS = {"TEXT_ONLY", "CONTROL_NOT_REQUIRED", "TARGET_NOT_VIDEO", "NO_APPLICABLE_ASSETS"}
HOST_CLASSES = {"external_image", "external_video", "local_media"}
NATIVE_KIND_MAP = {"ScriptIR": "screenplay", "DirectorIR": "director",
                   "ArtIR": "art", "StoryboardIR": "storyboard", "AVIR": "avir"}
ZERO_HASH = "0" * 64


class V6StateError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str):
    raise V6StateError(code, message)


class V6TaskKernel:
    """Transactional project-local V6 task ledger.

    Existing V5 project artifacts remain under V5 ownership. A V6 project
    requires the explicit ``orchestration_protocol`` marker in project.json.
    """

    def __init__(self, project_root: str | Path, schema_root: str | Path = ROOT):
        self.root = Path(project_root).expanduser().resolve()
        self.schema_root = Path(schema_root).resolve()
        self.base = self.root / "runtime/v6"

    def _project(self) -> dict:
        project = read(self.root / "project.json")
        if project.get("schema_version") != "5.0" or project.get("orchestration_protocol") != "6.0":
            _fail("PROJECT_VERSION", "V6 orchestration requires a marked V5 project")
        return project

    def _path(self, uri: str) -> Path:
        if not uri or "\\" in uri:
            _fail("PATH_INVALID", f"Invalid project path: {uri!r}")
        candidate = self.root / ensure_relative_path(uri)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root):
            _fail("PATH_ESCAPE", f"Path escapes project: {uri}")
        return resolved

    def _file_matches(self, uri: str, expected: str, *, label: str) -> None:
        path = self._path(uri)
        if path.is_file() and digest_file(path) == expected:
            return
        if uri == "project.json":
            # Older V6 events could cite the mutable project manifest directly.
            # A later authorized project decision archives those exact bytes so
            # historical evidence remains checkable without trusting the new manifest.
            archived = self.base / "evidence/project-json" / f"{expected}.json"
            if archived.is_file() and digest_file(archived) == expected:
                return
        if uri in ("delivery/index.json", "delivery/index.md"):
            # A later preproduction export replaces these files. The previous
            # bytes stay under a content hash so older delivery evidence still verifies.
            archived = self.base / "evidence/byte-archive" / expected
            if archived.is_file() and digest_file(archived) == expected:
                return
        _fail("FILE_HASH", f"{label} bytes missing or changed: {uri}")

    def _verify_control_package(self, manifest_uri: str) -> dict:
        manifest = self._path(manifest_uri)
        if manifest.name != "package-manifest.json":
            _fail("CONTROL_PACKAGE", "ShotControlPack must bind package-manifest.json")
        try:
            compiler = module_path(self.root, "video-prompt-compiler", self.schema_root)
            result = subprocess.run(
                [sys.executable, str(compiler / "scripts/control_cli.py"),
                 "verify", str(manifest.parent)], capture_output=True, text=True)
            if result.returncode:
                _fail("CONTROL_PACKAGE", (result.stderr or result.stdout)[-800:])
            summary = json.loads(result.stdout)
            if summary.get("status") != "VERIFIED":
                _fail("CONTROL_PACKAGE", "Locked control verifier did not return VERIFIED")
            frames = read(manifest.parent / "review/frames.json")
            if not frames or any(frame["camera"]["status"] == "UNDETERMINED"
                                 for frame in frames):
                _fail("CONTROL_PACKAGE", "Control package has undetermined camera projection frames")
            return summary
        except (OSError, ValueError, KeyError) as error:
            _fail("CONTROL_PACKAGE", str(error))

    @staticmethod
    def _empty_state() -> dict:
        return {"schema_version": "6.0", "revision": 0, "tasks": {},
                "artifacts": {}, "last_event_hash": ZERO_HASH}

    def _read_store(self) -> tuple[dict, list, dict, dict]:
        paths = [self.base / name for name in ("state.json", "events.json", "commands.json", "artifacts.json")]
        present = [path.exists() for path in paths]
        if not any(present):
            return self._empty_state(), [], {}, {}
        if not all(present):
            _fail("STORE_INCOMPLETE", "V6 state files are incomplete; recover the transaction")
        state, events, commands, artifacts = (read(path) for path in paths)
        self._verify_store(state, events, commands, artifacts)
        return state, events, commands, artifacts

    def _verify_store(self, state: dict, events: list, commands: dict, artifacts: dict) -> None:
        if state.get("schema_version") != "6.0" or not isinstance(events, list) or not isinstance(commands, dict):
            _fail("STORE_INVALID", "V6 ledger structure is invalid")
        previous = ZERO_HASH
        for revision, item in enumerate(events, 1):
            if item.get("revision") != revision or item.get("previous_hash") != previous:
                _fail("EVENT_CHAIN", "V6 event sequence has a gap or changed predecessor")
            actual = sha256_json({key: value for key, value in item.items() if key != "hash"})
            if item.get("hash") != actual:
                _fail("EVENT_CHAIN", f"V6 event {revision} changed")
            previous = actual
        if state.get("revision") != len(events) or state.get("last_event_hash") != previous:
            _fail("STORE_REVISION", "V6 state does not match event revision")
        if state.get("artifacts") != artifacts:
            _fail("ARTIFACT_INDEX", "V6 artifact indexes disagree")
        if events:
            tail = events[-1]
            core = {key: value for key, value in state.items() if key != "last_event_hash"}
            if (tail["state_digest"] != sha256_json(core)
                    or tail["commands_digest"] != sha256_json(commands)
                    or tail["artifacts_digest"] != sha256_json(artifacts)):
                _fail("STORE_TAMPERED", "V6 state, commands or artifact index changed outside a transaction")
        for slot, item in artifacts.items():
            self._file_matches(item["uri"], item["sha256"], label=f"accepted artifact {slot}")
        for task_id, task in state["tasks"].items():
            for uri, expected in task.get("evidence_hashes", {}).items():
                self._file_matches(uri, expected, label=f"task evidence {task_id}")
            for message in task["messages"]:
                if message["subject_uri"] is not None:
                    self._file_matches(message["subject_uri"], message["subject_sha256"],
                                       label=f"agent message {message['message_id']}")
            for receipt in [*task["receipt_history"], task["review_dispatch"]]:
                if receipt and receipt["tool_result_uri"] is not None:
                    self._file_matches(receipt["tool_result_uri"], receipt["tool_result_sha256"],
                                       label=f"dispatch evidence {task_id}")
            candidate = task["candidate"]
            if candidate is not None:
                for item in candidate["artifacts"]:
                    self._file_matches(item["uri"], item["sha256"],
                                       label=f"candidate artifact {task_id}")
                if candidate["result_uri"] is not None:
                    self._file_matches(candidate["result_uri"], candidate["result_sha256"],
                                       label=f"candidate result {task_id}")

    def snapshot(self) -> dict:
        """Read and verify without initializing files or changing project state."""
        self._project()
        state, _, _, _ = self._read_store()
        return deepcopy(state)

    def inspect(self, task_id: str) -> dict:
        state = self.snapshot()
        if task_id not in state["tasks"]:
            _fail("TASK_MISSING", task_id)
        return deepcopy(state["tasks"][task_id])

    def recover(self) -> dict:
        """Roll back pending file writes, then replay-check the complete journal."""
        self._project()
        with transaction(self.root):
            state, _, _, _ = self._read_store()
            return deepcopy(state)

    def _write(self, relative: str, value: object) -> None:
        path = self._path("runtime/v6/" + relative)
        before_write(self.root, path)
        atomic_write(path, canonical_json(value).encode("utf-8"))

    def _apply(self, op: str, payload: dict, command_id: str, expected_revision: int,
               mutate) -> dict:
        self._project()
        if not command_id or not isinstance(expected_revision, int) or expected_revision < 0:
            _fail("COMMAND_INVALID", "A command ID and nonnegative expected revision are required")
        fingerprint = sha256_json({"op": op, "payload": payload})
        with transaction(self.root):
            state, events, commands, artifacts = self._read_store()
            seen = commands.get(command_id)
            if seen:
                if seen["fingerprint"] != fingerprint:
                    _fail("COMMAND_COLLISION", f"Command {command_id} was already used for different content")
                return deepcopy(state)
            if state["revision"] != expected_revision:
                _fail("REVISION_CONFLICT", f"Expected project revision {expected_revision}, found {state['revision']}")
            mutate(state, artifacts)
            state["revision"] += 1
            state["artifacts"] = deepcopy(artifacts)
            commands[command_id] = {"fingerprint": fingerprint, "revision": state["revision"]}
            core = {key: value for key, value in state.items() if key != "last_event_hash"}
            item = {"revision": state["revision"], "op": op, "payload": payload,
                    "previous_hash": state["last_event_hash"],
                    "state_digest": sha256_json(core),
                    "commands_digest": sha256_json(commands),
                    "artifacts_digest": sha256_json(artifacts)}
            item["hash"] = sha256_json(item)
            state["last_event_hash"] = item["hash"]
            events.append(item)
            self._write("state.json", state)
            self._write("events.json", events)
            self._write("commands.json", commands)
            self._write("artifacts.json", artifacts)
            return deepcopy(state)

    def _verify_inputs(self, envelope: dict) -> None:
        for item in envelope["inputs"]:
            if item["uri"] is None:
                _fail("INPUT_UNBOUND", f"Input {item['slot']} has no byte-bound URI")
            self._file_matches(item["uri"], item["sha256"], label=f"input {item['slot']}")
            if item["slot"].endswith(":ShotControlPack"):
                self._verify_control_package(item["uri"])
        for item in envelope["resources"]:
            self._file_matches(item["uri"], item["sha256"], label="required resource")

    def _verify_module(self, envelope: dict) -> None:
        module = envelope["module"]
        if module is None:
            if envelope["execution_class"] == "professional" and envelope["node_id"] != "canon":
                _fail("MODULE_REQUIRED", "A professional task needs a locked Skill")
            return
        lock = read(self.root / "modules.lock.json")["modules"].get(module["name"])
        if lock is None or lock["sha256"] != module["sha256"] or lock["version"] != module["version"]:
            _fail("MODULE_LOCK", f"Skill lock mismatch: {module['name']}")
        archive = f"runtime/module-archives/{module['sha256']}.skill"
        self._file_matches(archive, module["sha256"], label="locked Skill archive")

    def _graph_stage(self, node_id: str) -> dict:
        graph = load_graph(module_lock=read(self.root / "modules.lock.json"))
        try:
            return stage_by_id(graph, node_id)
        except KeyError:
            _fail("GRAPH_NODE", f"Task names undeclared workflow node {node_id}")

    def _required_scopes(self, node_id: str) -> list[dict]:
        stage = self._graph_stage(node_id)
        kind = stage["scope"]
        if kind == "project":
            return [{"kind": "project", "ids": []}]
        from .v5 import V5Kernel
        v5 = V5Kernel(self.root, self.schema_root)
        if kind == "scene":
            if not v5.valid("director"):
                _fail("GRAPH_FACT", "Current DirectorIR is required for scene coverage")
            ids = [item["id"] for item in v5.data("director")["scenes"]]
        elif kind in ("asset", "panel"):
            if kind == "asset":
                if not v5.valid("director"):
                    _fail("GRAPH_FACT", "Current DirectorIR is required for asset coverage")
                scenes = v5.data("director")["scenes"]
                if not all(v5.valid("art:" + item["id"]) for item in scenes):
                    _fail("GRAPH_FACT", "Every scene ArtIR is required for asset coverage")
            elif not v5.valid("storyboard"):
                _fail("GRAPH_FACT", "Current StoryboardIR is required for panel coverage")
            ids = [item["key"] for item in v5.image_jobs(5 if kind == "asset" else 7)] or ["ALL"]
        else:
            if self._project().get("production_target") != "video":
                return [{"kind": kind, "ids": ["NO_VIDEO"]}]
            from .production import ProductionLedger
            ledger = ProductionLedger(v5)
            manifest = ledger._load("delivery-manifest.json")
            ledger._verify_manifest(manifest)
            if kind == "shot":
                ids = manifest["shot_ids"]
            elif kind == "generation_request":
                ids = [item["id"] for item in ledger.records()
                       if item["job_id"] in manifest["job_ids"]]
            elif kind == "take":
                ids = [item["id"] for item in ledger.takes()
                       if item["job_id"] in manifest["job_ids"]]
            else:
                _fail("GRAPH_SCOPE", f"No authoritative scope catalogue for {kind}")
        if not ids or len(set(ids)) != len(ids):
            _fail("GRAPH_FACT", f"Authoritative {kind} scope set is empty or ambiguous")
        return [{"kind": kind, "ids": [item]} for item in ids]

    def _scope_links(self, envelope: dict, required: dict[str, list[dict]]) -> dict[str, list[dict]]:
        node_id = envelope["node_id"]
        scope_id = envelope["scope"]["ids"][0] if envelope["scope"]["ids"] else None
        if node_id == "visual_prompts":
            if scope_id == "ALL":
                return {"art": required["art"]}
            from .v5 import V5Kernel
            job = next((item for item in V5Kernel(self.root, self.schema_root).image_jobs(5)
                        if item["key"] == scope_id), None)
            if job is None:
                _fail("GRAPH_SCOPE", "Visual prompt has no authoritative image job")
            scenes = list(dict.fromkeys(item["slot"][4:] for item in job["dependencies"]
                                        if item["slot"].startswith("art:")))
            if not scenes:
                _fail("GRAPH_SCOPE", "Visual image job has no ArtIR scene dependency")
            return {"art": [{"kind": "scene", "ids": [item]} for item in scenes]}
        if node_id in ("board_prompts", "board_media"):
            dep = "visual_prompts" if node_id == "board_prompts" else "visual_media"
            return {dep: required[dep]}
        if node_id == "take_recovery":
            if scope_id == "NO_VIDEO":
                return {"video_execution": required["video_execution"]}
            from .v5 import V5Kernel
            from .production import ProductionLedger
            take = ProductionLedger(V5Kernel(self.root, self.schema_root))._load(
                "takes/" + scope_id + ".json")
            if take.get("id") != scope_id:
                _fail("GRAPH_SCOPE", "Take record differs from frozen task scope")
            return {"video_execution": [{"kind": "generation_request",
                                         "ids": [take["record_id"]]}]}
        if node_id == "shot_acceptance":
            if scope_id == "NO_VIDEO":
                return {"take_recovery": required["take_recovery"]}
            intent = next((item for item in envelope["inputs"]
                           if item["slot"] == "production_intent"), None)
            if intent is None:
                _fail("GRAPH_FACT", "Shot review needs its frozen production intent")
            decision = read(self._path(intent["uri"]))
            take_id = decision.get("take_ids", {}).get(scope_id)
            if not isinstance(take_id, str) or not take_id:
                _fail("GRAPH_SCOPE", "Shot review has no selected Take binding")
            return {"take_recovery": [{"kind": "take", "ids": [take_id]}]}
        return {}

    def _check_graph_envelope(self, state: dict, envelope: dict) -> None:
        stage = self._graph_stage(envelope["node_id"])
        host_classes = {
            "visual_media": "external_image", "board_media": "external_image",
            "video_execution": "external_video",
        }
        expected_class = {"specialist": "professional", "reviewer": "review",
                          "kernel": "system", "host": host_classes.get(envelope["node_id"], "local_media")}[stage["executor_kind"]]
        if (envelope["role"] != stage["role"] or envelope["scope"]["kind"] != stage["scope"]
                or envelope["execution_class"] != expected_class):
            _fail("GRAPH_ASSIGNMENT", "Task role, scope or execution class differs from workflow graph")
        module = envelope["module"]
        if (module["name"] if module else None) != stage["locked_skill"]:
            _fail("GRAPH_SKILL", "Task Skill differs from workflow graph")
        self._check_ids(envelope["validators"], [{"id": item} for item in stage["checkers"]],
                        "id", "GRAPH_CHECKERS")
        kinds = [item["kind"] for item in envelope["expected_artifacts"]]
        if len(set(kinds)) != len(kinds) or set(kinds) != set(stage["output_types"]):
            _fail("GRAPH_OUTPUTS", "Task outputs do not exactly match workflow graph types")
        if stage["handoff_required"] and not envelope["handoffs"]:
            _fail("GRAPH_HANDOFF", "Specialist task must declare a traceable handoff")
        input_versions = {item["slot"]: item["version"] for item in envelope["inputs"]}
        output_slots = {item["slot"] for item in envelope["expected_artifacts"]}
        for handoff in envelope["handoffs"]:
            if (input_versions.get(handoff["source_slot"]) != handoff["source_version"]
                    or handoff["target_slot"] not in output_slots):
                _fail("GRAPH_HANDOFF", "Handoff source version or target slot is not frozen in task inputs")
        dependency_nodes = set()
        for item in envelope["dependencies"]:
            dependency = self._task(state, item["task_id"])
            dependency_nodes.add(dependency["envelope"]["node_id"])
        if dependency_nodes != set(stage["depends_on"]):
            _fail("GRAPH_DEPENDENCIES", "Task dependency nodes do not match workflow graph")
        graph = load_graph(module_lock=read(self.root / "modules.lock.json"))
        required = {name: self._required_scopes(name)
                    for name in [envelope["node_id"], *stage["depends_on"]]}
        links = self._scope_links(envelope, required)
        try:
            expected = predecessor_task_ids(graph, envelope["node_id"], envelope["scope"],
                                            state["tasks"], required, links)
        except (KeyError, ValueError, OSError) as error:
            _fail("GRAPH_DEPENDENCIES", str(error))
        actual = [item["task_id"] for item in envelope["dependencies"]]
        if len(actual) != len(expected) or set(actual) != set(expected):
            _fail("GRAPH_DEPENDENCIES", f"Frozen predecessor IDs differ: expected {expected}, got {actual}")

    def _applicability_context(self) -> dict:
        project = self._project()
        state = read(self.root / "state.json")
        sources = state.get("sources", [])
        video_extensions = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
        observation_required = any(Path(item["uri"]).suffix.lower() in video_extensions for item in sources)
        facts = {"delivery": project["delivery"],
                 "production_target": project.get("production_target", "none"),
                 "observation_required": observation_required}
        try:
            from .v5 import V5Kernel
            v5 = V5Kernel(self.root, self.schema_root)
            if v5.valid("storyboard"):
                facts["control_required"] = v5.control_applicable(v5.data("storyboard"))
                facts["board_jobs_present"] = bool(v5.image_jobs(7))
            if v5.valid("director"):
                scenes = v5.data("director")["scenes"]
                if all(v5.valid("art:" + scene["id"]) for scene in scenes):
                    facts["visual_jobs_present"] = bool(v5.image_jobs(5))
        except (KeyError, ValueError, OSError):
            pass
        return facts

    def _verify_targeted_repair(self, envelope: dict, previous: dict, repeated: set[str]) -> None:
        if (envelope['execution_class'] != 'professional' or envelope['batch'] != 3
                or len(repeated) != 1):
            _fail('REPAIR_REQUIRED', 'Repeated specialist failure needs one frozen final repair batch')
        task_id = envelope['task_id']
        inputs = {item['slot']: item for item in envelope['inputs']}
        repair = inputs.get('repair_brief')
        expected_uri = f'runtime/v6/repair/{task_id}/3/repair-brief.json'
        if repair is None or repair['uri'] != expected_uri or repair['version'] != 3:
            _fail('REPAIR_REQUIRED', 'Final batch must bind its targeted repair brief')
        self._file_matches(repair['uri'], repair['sha256'], label='targeted repair brief')
        brief = read(self._path(repair['uri']))
        validate_v6_protocol('repair-brief', brief, self.schema_root)
        check_id = next(iter(repeated))
        if (brief['task_id'] != task_id or brief['node_id'] != envelope['node_id']
                or brief['next_batch'] != 3 or brief['failed_check'] != check_id
                or [item['batch'] for item in brief['failures']] != [1, 2]):
            _fail('REPAIR_REQUIRED', 'Repair brief does not bind both prior failures')
        prior_events = read(self.base / 'events.json')
        snapshots = {item['envelope']['batch']: item for item in previous.get('history', [])
                     if isinstance(item, dict) and isinstance(item.get('envelope'), dict)}
        snapshots[previous['envelope']['batch']] = previous
        for index, item in enumerate(brief['failures'], 1):
            slot = inputs.get(f'repair_failure_{index}')
            if (slot is None or slot['uri'] != item['failure_uri']
                    or slot['sha256'] != item['failure_sha256'] or slot['version'] != index):
                _fail('REPAIR_REQUIRED', 'Repair evidence input differs from frozen failure')
            self._file_matches(item['failure_uri'], item['failure_sha256'],
                               label='targeted repair failure')
            matches = [(event.get('payload') or {}).get('event') or {}
                       for event in prior_events]
            matches = [event for event in matches
                       if event.get('task_id') == task_id and event.get('batch') == index
                       and event.get('to_state') == 'FAILED'
                       and (event.get('error') or {}).get('failed_check') == check_id]
            if (len(matches) != 1 or matches[0].get('evidence') != [item['failure_uri']]
                    or matches[0]['error']['code'] != item['code']):
                _fail('REPAIR_REQUIRED', 'Repair brief is not backed by actual state events')
            for proof in item['review_evidence']:
                self._file_matches(proof['uri'], proof['sha256'],
                                   label='targeted review evidence')
            prior = snapshots.get(index)
            reviewer_id = ((prior or {}).get('review_dispatch') or {}).get('agent_id')
            required_reviews = {uri for message in (prior or {}).get('messages', [])
                                if message.get('type') == 'RESULT'
                                and message.get('sender_id') == reviewer_id
                                for uri in message.get('evidence', [])}
            if not required_reviews.issubset(
                    {proof['uri'] for proof in item['review_evidence']}):
                _fail('REPAIR_REQUIRED', 'Repair brief omits the independent review evidence')

    def _stage_applies(self, envelope: dict) -> tuple[bool, dict | None]:
        stage = self._graph_stage(envelope["node_id"])
        context = self._applicability_context()
        try:
            decision = stage_applicability(stage, context, evidence_ref="project.json")
        except (KeyError, ValueError) as error:
            _fail("APPLICABILITY_FACT", str(error))
        if decision["status"] == "APPLICABLE":
            return True, None
        return False, {"reason_code": decision["reason_code"],
                       "affected_outputs": decision["affected_outputs"]}

    def _check_task_creation(self, state: dict, envelope: dict) -> dict | None:
        if envelope["project_id"] != self._project()["project_id"]:
            _fail("PROJECT_ID", "Task project_id differs from the project")
        if envelope["input_digest"] != envelope_input_digest(envelope):
            _fail("INPUT_DIGEST", "Frozen task input digest differs")
        self._verify_inputs(envelope)
        self._verify_module(envelope)
        self._check_graph_envelope(state, envelope)
        for field, values in (("input", envelope["inputs"]), ("resource", envelope["resources"]),
                              ("artifact", envelope["expected_artifacts"]),
                              ("validator", envelope["validators"]),
                              ("dependency", envelope["dependencies"]),
                              ("handoff", envelope["handoffs"])):
            key = {"input": "slot", "resource": "uri", "artifact": "slot", "validator": "id",
                   "dependency": "task_id", "handoff": "requirement_id"}[field]
            if len({item[key] for item in values}) != len(values):
                _fail("DUPLICATE_FIELD", f"Duplicate {field} {key}")
        if envelope["task_id"] in {item["task_id"] for item in envelope["dependencies"]}:
            _fail("DEPENDENCY_CYCLE", "Task cannot depend on itself")
        prefix = f"runtime/v6/candidates/{envelope['task_id']}/{envelope['batch']}/"
        for item in envelope["expected_artifacts"]:
            if item["uri_prefix"] != prefix:
                _fail("CANDIDATE_PREFIX", f"Expected artifact {item['slot']} must use {prefix}")
        previous = state["tasks"].get(envelope["task_id"])
        if previous:
            if previous["state"] not in ("FAILED", "BLOCKED", "STALE"):
                _fail("TASK_ACTIVE", "Task may be retried only after failure, block or staleness")
            if envelope["batch"] != previous["envelope"]["batch"] + 1:
                _fail("BATCH_STALE", "Retry batch must increase by exactly one")
            if envelope["execution_class"] in ("external_image", "external_video"):
                authorization = envelope.get("retry_authorization")
                if not authorization:
                    _fail("EXTERNAL_RETRY", "External generation retry requires recorded authorization")
                self._path(authorization["evidence_uri"])
                if not self._path(authorization["evidence_uri"]).is_file():
                    _fail("EXTERNAL_RETRY", "Retry authorization evidence is missing")
            elif envelope["batch"] > 3:
                _fail("RETRY_LIMIT", "Professional/local task attempts are limited to three")
            failures = previous.get("failure_counts", {})
            repeated = {key for key, count in failures.items() if count >= 2}
            if (any(count >= 2 for count in failures.values())
                    and envelope_semantic_digest(envelope) ==
                    envelope_semantic_digest(previous["envelope"])):
                _fail("REVISE_REQUIRED", "Repeated check failure needs revised frozen inputs")
            if repeated:
                self._verify_targeted_repair(envelope, previous, repeated)
        elif envelope["batch"] != 1:
            _fail("BATCH_STALE", "A new task must start at batch 1")
        for other_id, other in state["tasks"].items():
            if other_id == envelope["task_id"] or other["state"] in ("ACCEPTED", "NOT_APPLICABLE", "FAILED", "STALE", "CANCELLED"):
                continue
            other_slots = {item["slot"] for item in other["envelope"]["expected_artifacts"]}
            new_slots = {item["slot"] for item in envelope["expected_artifacts"]}
            if other_slots & new_slots:
                _fail("WRITE_CONFLICT", f"Concurrent task {other_id} owns the same output slot")
            same_scope = (other["envelope"]["scope"]["kind"] == envelope["scope"]["kind"]
                          and (envelope["scope"]["kind"] == "project" or
                               bool(set(other["envelope"]["scope"]["ids"]) & set(envelope["scope"]["ids"]))))
            if other["envelope"]["node_id"] == envelope["node_id"] and same_scope:
                _fail("SCOPE_CONFLICT", f"Concurrent task {other_id} overlaps the same scope")
        return previous

    def create_task(self, envelope: dict, command_id: str, expected_revision: int) -> dict:
        validate_v6_protocol("task-envelope", envelope, self.schema_root)
        def mutate(state, artifacts):
            previous = self._check_task_creation(state, envelope)
            history = (previous.get("history", []) + [{key: deepcopy(value) for key, value in previous.items()
                       if key != "history"}]) if previous else []
            state["tasks"][envelope["task_id"]] = {
                "envelope": deepcopy(envelope), "state": "PENDING", "version": 0,
                "receipt": None, "receipt_history": [], "review_dispatch": None,
                "candidate": None, "review": None, "validation": [], "messages": [],
                "evidence_hashes": {},
                "history": history, "failure_counts": deepcopy(previous.get("failure_counts", {})) if previous else {},
            }
        return self._apply("create_task", envelope, command_id, expected_revision, mutate)

    def _task(self, state: dict, task_id: str, batch: int | None = None) -> dict:
        task = state["tasks"].get(task_id)
        if task is None:
            _fail("TASK_MISSING", task_id)
        if batch is not None and task["envelope"]["batch"] != batch:
            _fail("BATCH_STALE", f"Late result for task {task_id} batch {batch}")
        return task

    def _verify_receipt(self, envelope: dict, receipt: dict, *, review: bool = False) -> None:
        if (receipt["task_id"] != envelope["task_id"] or receipt["batch"] != envelope["batch"]
                or receipt["task_digest"] != envelope_digest(envelope)):
            _fail("DISPATCH_BINDING", "Dispatch receipt does not match frozen task")
        expected = expected_review_dispatch_id(envelope) if review else expected_dispatch_id(envelope)
        if receipt["dispatch_id"] != expected or receipt["action_id"] != expected:
            _fail("DISPATCH_BINDING", "Dispatch ID differs from the deterministic host action")
        if receipt["tool_result_uri"] is not None:
            self._file_matches(receipt["tool_result_uri"], receipt["tool_result_sha256"],
                               label="raw host tool result")
            import json
            path = self._path(receipt["tool_result_uri"])
            if (path.parent != self.base / "host-evidence"
                    or path.name != receipt["tool_result_sha256"] + ".json"):
                _fail("HOST_RESULT_SCOPE", "Raw host result must be stored by content hash")
            raw = json.loads(path.read_text(encoding="utf-8"))
            if receipt["agent_id"] is not None:
                if receipt["host_tool"] == "collaboration.spawn_agent":
                    observed = (isinstance(raw, dict)
                                and (raw.get("task_name") or raw.get("agent_name")) == receipt["agent_id"]
                                and ("agent_name" not in raw or raw["agent_name"] == receipt["agent_id"])
                                and ("task_name" not in raw or raw["task_name"] == receipt["agent_id"]))
                else:
                    observed = (isinstance(raw, dict) and isinstance(raw.get("agents"), list)
                                and sum(isinstance(agent, dict) and agent.get("agent_name") == receipt["agent_id"]
                                        for agent in raw["agents"]) == 1)
                if not observed:
                    _fail("HOST_RESULT_BINDING", "Raw host result does not identify this exact agent")

    def _verify_candidate(self, task: dict, candidate: dict) -> None:
        envelope = task["envelope"]
        receipt = task["receipt"]
        host_creators = {"system": "kernel", "external_image": "image_host",
                         "external_video": "production_host", "local_media": "production_host"}
        creator = receipt["agent_id"] if receipt is not None else host_creators.get(envelope["execution_class"])
        if (candidate["task_id"] != envelope["task_id"] or candidate["batch"] != envelope["batch"]
                or candidate["agent_id"] != creator
                or candidate["input_digest"] != envelope["input_digest"]):
            _fail("CANDIDATE_BINDING", "Candidate is from a different agent, batch or input")
        expected = {item["slot"]: item for item in envelope["expected_artifacts"]}
        actual = {item["slot"]: item for item in candidate["artifacts"]}
        if len(actual) != len(candidate["artifacts"]) or set(actual) != set(expected):
            _fail("OUTPUT_COVERAGE", "Candidate artifact slots do not exactly cover task outputs")
        for slot, item in actual.items():
            prefix = self._path(expected[slot]["uri_prefix"])
            if item["kind"] != expected[slot]["kind"] or not self._path(item["uri"]).is_relative_to(prefix):
                _fail("OUTPUT_SCOPE", f"Artifact {slot} has the wrong kind or candidate directory")
            self._file_matches(item["uri"], item["sha256"], label=f"candidate artifact {slot}")
            if item["kind"] == "ShotControlPack":
                self._verify_control_package(item["uri"])
        if (candidate["result_uri"] is None) != (candidate["result_sha256"] is None):
            _fail("RESULT_BINDING", "Result URI and hash must be paired")
        if candidate["result_uri"] is not None:
            prefix = f"runtime/v6/candidates/{envelope['task_id']}/{envelope['batch']}/"
            if not self._path(candidate["result_uri"]).is_relative_to(self._path(prefix)):
                _fail("RESULT_SCOPE", "Role result must be copied into the candidate directory")
            self._file_matches(candidate["result_uri"], candidate["result_sha256"], label="role result")
            result = read(self._path(candidate["result_uri"]))
            if "artifact" in result:
                result_artifact = Path(result["artifact"])
                if result_artifact.is_absolute():
                    resolved = result_artifact.resolve()
                else:
                    resolved = self._path(result["artifact"])
                candidate_paths = {self._path(item["uri"]) for item in candidate["artifacts"]}
                if resolved not in candidate_paths:
                    _fail("RESULT_ARTIFACT", "RoleResult artifact path is outside declared candidate artifacts")
                matching = next(item for item in candidate["artifacts"] if self._path(item["uri"]) == resolved)
                if result.get("artifact_sha256") != matching["sha256"]:
                    _fail("RESULT_ARTIFACT", "RoleResult artifact hash differs from candidate manifest")
            bindings = candidate.get("reuse_bindings", [])
            if result.get("reused"):
                migration = next((item for item in envelope["inputs"]
                                  if item["slot"] == "migration_report"), None)
                if not bindings or migration is None or migration["uri"] != "imports/migration.json":
                    _fail("REUSE_PROVENANCE", "Reused RoleResult needs frozen migration provenance")
                self._file_matches(migration["uri"], migration["sha256"], label="migration report")
                report = read(self._path(migration["uri"]))
                if report.get("schema") != "migration/5.0" or not isinstance(report.get("files"), list):
                    _fail("REUSE_PROVENANCE", "Migration report has the wrong protocol")
                copied = {(item.get("uri"), item.get("sha256")) for item in report["files"]
                          if isinstance(item, dict)}
                if len({item["target_slot"] for item in bindings}) != len(bindings):
                    _fail("REUSE_PROVENANCE", "Reuse target slots must be unique")
                for binding in bindings:
                    target = actual.get(binding["target_slot"])
                    if ((binding["source_uri"], binding["source_sha256"]) not in copied
                            or target is None or target["sha256"] != binding["source_sha256"]):
                        _fail("REUSE_PROVENANCE", "Reuse source differs from migration or target bytes")
                    self._file_matches(binding["source_uri"], binding["source_sha256"],
                                       label="migrated reuse source")
                if "artifact" not in result or matching["slot"] not in {
                        item["target_slot"] for item in bindings}:
                    _fail("REUSE_PROVENANCE", "Reused primary artifact has no source binding")
            elif bindings:
                _fail("REUSE_PROVENANCE", "Reuse bindings require reused=true in RoleResult")
        elif candidate.get("reuse_bindings"):
            _fail("REUSE_PROVENANCE", "Reuse bindings require a frozen RoleResult")
        module = envelope["module"]
        receipts = candidate["module_receipts"]
        if (receipts != ([] if module is None else [module])):
            _fail("MODULE_RECEIPT", "Candidate Skill receipt differs from frozen lock")
        self._check_ids(candidate["checks"], envelope["validators"], "id", "CANDIDATE_CHECKS")
        self._review_evidence(candidate["checks"])
        self._check_ids(candidate["handoffs"], envelope["handoffs"], "requirement_id", "HANDOFF_COVERAGE")
        specs = {item["requirement_id"]: item for item in envelope["handoffs"]}
        for item in candidate["handoffs"]:
            spec = specs[item["requirement_id"]]
            for key in ("source_slot", "source_version", "target_slot", "target_pointer", "channel"):
                if item[key] != spec[key]:
                    _fail("HANDOFF_BINDING", f"Handoff {item['requirement_id']} differs at {key}")
            if not item["evidence"]:
                _fail("HANDOFF_EVIDENCE", f"Handoff {item['requirement_id']} has no evidence")

    @staticmethod
    def _check_ids(actual: list, expected: list, key: str, code: str) -> None:
        actual_ids = [item[key] for item in actual]
        expected_ids = [item[key] for item in expected]
        if len(set(actual_ids)) != len(actual_ids) or set(actual_ids) != set(expected_ids):
            _fail(code, f"Expected exactly {sorted(expected_ids)}, got {actual_ids}")

    def _review_evidence(self, checks: list) -> None:
        for check in checks:
            if not check["evidence"]:
                _fail("CHECK_EVIDENCE", f"Check {check['id']} has no evidence")
            for uri in check["evidence"]:
                path = self._path(uri)
                if not path.is_file() or path.stat().st_size == 0:
                    _fail("CHECK_EVIDENCE", f"Check evidence is absent or empty: {uri}")

    def _freeze_evidence_uris(self, task: dict, uris: list[str]) -> None:
        index = task.setdefault("evidence_hashes", {})
        mutable_inputs = {item["uri"] for item in
                          [*task["envelope"]["inputs"], *task["envelope"]["resources"]]}
        for uri in uris:
            path = self._path(uri)
            if not path.is_file() or path.stat().st_size == 0:
                _fail("CHECK_EVIDENCE", f"Evidence is absent or empty: {uri}")
            if (uri in mutable_inputs or
                    path.parent == self.root / "runtime/production/executions"):
                # Inputs enter STALE on change; execution records advance in the
                # separately checked production event ledger after submission.
                continue
            observed = digest_file(path)
            if uri in index and index[uri] != observed:
                _fail("EVIDENCE_CHANGED", f"Frozen evidence changed: {uri}")
            index[uri] = observed

    def _freeze_checks(self, task: dict, checks: list) -> None:
        self._freeze_evidence_uris(task, [uri for item in checks for uri in item["evidence"]])

    def _require_origin_result(self, task: dict, sender_id: str, payload: dict) -> None:
        for message in reversed(task["messages"]):
            if message["type"] != "RESULT" or message["sender_id"] != sender_id:
                continue
            uri, expected = message["subject_uri"], message["subject_sha256"]
            self._file_matches(uri, expected, label="agent RESULT payload")
            if read(self._path(uri)) != payload:
                _fail("RESULT_MESSAGE", "Agent RESULT bytes differ from submitted protocol record")
            return
        _fail("RESULT_MESSAGE", "A bound RESULT message from the dispatched agent is required")

    def _native_checks(self, task: dict) -> None:
        envelope, candidate = task["envelope"], task["candidate"]
        for spec in envelope["validators"]:
            if spec["kind"] != "native":
                continue
            if spec["id"] == "control_verify":
                packs = [item for item in candidate["artifacts"]
                         if item["kind"] == "ShotControlPack"]
                if len(packs) != 1:
                    _fail("CONTROL_PACKAGE", "Control validation needs exactly one ShotControlPack")
                self._verify_control_package(packs[0]["uri"])
                continue
            artifacts = [item for item in candidate["artifacts"] if item["kind"] in NATIVE_KIND_MAP]
            if not artifacts:
                _fail("NATIVE_CHECK", f"No native IR artifact for {spec['id']}")
            for item in artifacts:
                try:
                    native_validate(NATIVE_KIND_MAP[item["kind"]], self._path(item["uri"]),
                                    lambda name: module_path(self.root, name, self.schema_root))
                except (ValueError, OSError) as error:
                    _fail("NATIVE_CHECK", f"{spec['id']}: {error}")

    def _input_changed(self, envelope: dict, *, accepted: bool = False) -> bool:
        try:
            self._verify_inputs(envelope)
            self._verify_module(envelope)
        except (V6StateError, FileNotFoundError, KeyError):
            return True
        if runtime_resources_changed(envelope['node_id'], envelope.get('resources', [])):
            return True
        if not accepted:
            return False
        node = envelope['node_id']
        scope_ids = envelope['scope']['ids']
        native_slots = {'canon': 'canon', 'screenplay': 'screenplay',
                        'director': 'director', 'storyboard': 'storyboard',
                        'preproduction_qa': 'qa'}
        slot = 'art:' + scope_ids[0] if node == 'art' and len(scope_ids) == 1 else native_slots.get(node)
        state = read(self.root / 'state.json')
        if slot is not None:
            artifact = state.get('artifacts', {}).get(slot)
            if artifact is None or artifact.get('invalidated') is True:
                return True
            if node in ('director', 'storyboard'):
                try:
                    from .v51_detail_runtime import semantic_status
                    value = read(self._path(artifact['uri']))
                    review = value.get('timeline', {}).get('semantic_review')
                    if review and review.get('status') == 'PASS' and not semantic_status(value):
                        return True
                except (ValueError, OSError, KeyError, TypeError):
                    return True
            return False
        if node in ('visual_prompts', 'board_prompts') and len(scope_ids) == 1 and scope_ids[0] != 'ALL':
            return scope_ids[0] not in state.get('prompts', {})
        if node in ('visual_media', 'board_media') and len(scope_ids) == 1 and scope_ids[0] != 'ALL':
            media = state.get('media', {}).get(scope_ids[0])
            return media is None or media.get('invalidated') is True
        return False

    def _host_record_invalid(self, task: dict, evidence: list[str]) -> bool:
        envelope = task["envelope"]
        if envelope["node_id"] != "video_execution" or task["candidate"] is None:
            return False
        uri = task["candidate"].get("host_record_uri")
        if not uri or uri not in evidence:
            return False
        path = self._path(uri)
        if not path.is_file():
            return True
        try:
            record = read(path)
        except (ValueError, OSError):
            return True
        if not isinstance(record, dict) or record.get("id") not in envelope["scope"]["ids"]:
            return True
        frozen = next((item for item in task["candidate"]["artifacts"]
                       if item["kind"] == "ExecutionRecord"), None)
        if frozen is None:
            return True
        original = read(self._path(frozen["uri"]))
        original_version = original.get("version")
        if type(original_version) is not int or original.get("id") != record["id"]:
            return True
        from .production import _sha
        directory = self.root / "runtime/production/execution-events" / record["id"]
        for event_path in sorted(directory.glob("*.json")):
            event_uri = str(event_path.relative_to(self.root))
            if event_uri not in evidence:
                continue
            try:
                event = read(event_path)
            except (ValueError, OSError):
                continue
            if (event.get("record_id") == record["id"]
                    and type(event.get("version")) is int
                    and event["version"] > original_version
                    and event.get("to") in ("UNKNOWN", "FAILED")
                    and isinstance(event.get("record"), dict)
                    and event["record"].get("state") == event["to"]
                    and event.get("record_sha256") == _sha(event["record"])):
                return True
        return False

    def _verify_host_progress(self, envelope: dict, evidence: list[str]) -> None:
        paths = [self._path(uri) for uri in evidence]
        if any(not path.is_file() or path.stat().st_size == 0 for path in paths):
            _fail("HOST_PROGRESS", "Host progress evidence is missing or empty")
        if envelope["execution_class"] == "external_image":
            from .v6_media_host import image_action_id
            matched = False
            for path in paths:
                if (path.parent != self.base / "host-evidence"
                        or path.name != digest_file(path) + ".json"):
                    continue
                try:
                    record = read(path)
                    schema = record.get("schema") if isinstance(record, dict) else None
                    protocol = {"image-host-action/6.0": "image-host-action",
                                "image-host-record/6.0": "image-host-record"}.get(schema)
                    if protocol is None:
                        continue
                    validate_v6_protocol(protocol, record, self.schema_root)
                except (ValueError, UnicodeDecodeError, V6ProtocolError):
                    continue
                if (isinstance(record, dict) and record.get("task_id") == envelope["task_id"]
                        and record.get("batch") == envelope["batch"]
                        and record.get("task_digest") == envelope_digest(envelope)
                        and record.get("action_id") == image_action_id(envelope)
                        and record.get("schema") in ("image-host-action/6.0", "image-host-record/6.0")):
                    matched = True
                    break
            inflight = read(self.root / "state.json").get("inflight")
            if not matched or not inflight or inflight.get("task_id") != envelope["task_id"]:
                _fail("HOST_PROGRESS", "Image host start must bind the action and V5 in-flight record")
        else:
            prefixes = {"video_execution": "executions", "take_recovery": "takes",
                        "assembly": "assembly"}
            folder = self.root / "runtime/production" / prefixes[envelope["node_id"]]
            matched = False
            for path in paths:
                if path.parent != folder or path.suffix != ".json":
                    continue
                try:
                    record = read(path)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(record, dict) or record.get("id") != path.stem:
                    continue
                if envelope["node_id"] in ("video_execution", "take_recovery"):
                    if envelope["scope"]["ids"] != [record["id"]]:
                        continue
                matched = True
                break
            if not matched:
                _fail("HOST_PROGRESS", "Production host start needs its node-owned ledger record")

    def _validate_host_candidate(self, envelope: dict, candidate: dict) -> None:
        if envelope["execution_class"] == "external_image":
            from .v6_media_host import validate_media_result
            task_path = self._path(f"runtime/tasks/{envelope['task_id']}.json")
            if not task_path.is_file():
                _fail("HOST_EVIDENCE", "Frozen V5 image task is missing")
            try:
                validate_media_result(self.root, envelope, read(task_path), candidate,
                                      skill_root=self.schema_root)
            except (ValueError, OSError) as error:
                _fail("HOST_EVIDENCE", str(error))
        else:
            from .v6_production_runtime import validate_host_node_candidate
            try:
                validate_host_node_candidate(self.root, envelope, candidate)
            except (ValueError, OSError) as error:
                _fail("HOST_EVIDENCE", str(error))

    @staticmethod
    def _active_agent_counts(state: dict, *, excluding: str | None = None) -> tuple[int, int]:
        specialists = reviewers = 0
        for task_id, item in state["tasks"].items():
            if task_id == excluding:
                continue
            if item["state"] in ("DISPATCHING", "RUNNING"):
                if item["envelope"]["execution_class"] == "professional":
                    specialists += 1
                elif item["envelope"]["execution_class"] == "review":
                    reviewers += 1
            if item["state"] == "REVIEW_REQUIRED" and item["review_dispatch"] is not None:
                reviewers += 1
        return specialists, reviewers

    def _transition(self, state: dict, artifacts: dict, event: dict,
                    receipt: dict | None, candidate: dict | None, review: dict | None) -> None:
        task = self._task(state, event["task_id"], event["batch"])
        envelope = task["envelope"]
        old, new = event["from_state"], event["to_state"]
        if event["object_version"] != task["version"] or old != task["state"]:
            _fail("OBJECT_VERSION", "Task version or source state changed")
        if new not in MAIN_PATH[old]:
            _fail("ILLEGAL_TRANSITION", f"{old} -> {new} is not allowed")
        error_record = event.get("error")
        if new in ("FAILED", "BLOCKED", "UNKNOWN"):
            if (not isinstance(error_record, dict) or error_record["owner_node"] != envelope["node_id"]
                    or not error_record["evidence"]):
                _fail("ERROR_REQUIRED", f"{new} needs a structured error bound to this node")
            if new == "UNKNOWN" and error_record["recovery_action"] != "RECONCILE":
                _fail("ERROR_RECOVERY", "UNKNOWN dispatch must be reconciled before retry")
        elif error_record is not None:
            _fail("ERROR_UNEXPECTED", "A successful transition cannot carry an error record")
        if new == "STALE":
            dependency_stale = any(self._task(state, dep["task_id"])["state"] not in
                                   ("ACCEPTED", "NOT_APPLICABLE") for dep in envelope["dependencies"])
            applicability_changed = False
            if event["reason"] == "APPLICABILITY_CHANGED":
                applies_now = self._stage_applies(envelope)[0]
                applicability_changed = ((old == "NOT_APPLICABLE" and applies_now)
                                         or (old == "ACCEPTED" and not applies_now))
            if not ((event["reason"] == "INPUT_CHANGED" and self._input_changed(
                        envelope, accepted=old == "ACCEPTED"))
                    or (event["reason"] == "DEPENDENCY_STALE" and dependency_stale)
                    or (event["reason"] == "HOST_RECORD_CHANGED" and old == "ACCEPTED"
                        and self._host_record_invalid(task, event["evidence"]))
                    or (event["reason"] == "APPLICABILITY_CHANGED" and applicability_changed)):
                _fail("STALE_UNPROVEN", "Staleness needs changed input, invalid dependency or applicability")
            for slot in [item["slot"] for item in envelope["expected_artifacts"]]:
                if artifacts.get(slot, {}).get("task_id") == event["task_id"]:
                    del artifacts[slot]
        elif new not in ("CANCELLED", "UNKNOWN", "FAILED", "BLOCKED", "NOT_APPLICABLE"):
            self._verify_inputs(envelope)
            self._verify_module(envelope)
        if old == "PENDING" and new == "ACCEPTED":
            execution_class = envelope["execution_class"]
            stage = self._graph_stage(envelope["node_id"])
            if (execution_class != "system" or stage["review"] != "none"
                    or event["reason"] != "SYSTEM_VALIDATED"
                    or event["actor_kind"] != "kernel" or candidate is None):
                _fail("SYSTEM_GATE", "Direct completion is reserved for validated kernel tasks")
            if not self._stage_applies(envelope)[0]:
                _fail("APPLICABILITY", "Host task is not applicable to current project facts")
            self._verify_candidate(task, candidate)
            self._check_ids(event["check_results"], envelope["validators"], "id", "VALIDATION_COVERAGE")
            if (any(item["status"] != "PASS" for item in event["check_results"])
                    or any(item["status"] != "PASS" for item in candidate["checks"])
                    or candidate["unresolved"]):
                _fail("VALIDATION_FAILED", "Host checks did not all pass")
            self._review_evidence(event["check_results"])
            self._freeze_checks(task, candidate["checks"])
            self._freeze_checks(task, candidate["handoffs"])
            self._freeze_checks(task, event["check_results"])
            for dep in envelope["dependencies"]:
                if self._task(state, dep["task_id"])["state"] not in ("ACCEPTED", "NOT_APPLICABLE"):
                    _fail("DEPENDENCY_UNREADY", dep["task_id"])
            task["candidate"] = deepcopy(candidate)
            task["validation"] = deepcopy(event["check_results"])
            for item in candidate["artifacts"]:
                owner = artifacts.get(item["slot"])
                if owner and owner["task_id"] != envelope["task_id"]:
                    _fail("OUTPUT_OWNERSHIP", f"Output {item['slot']} belongs to {owner['task_id']}")
                artifacts[item["slot"]] = {**deepcopy(item), "task_id": envelope["task_id"],
                                           "batch": envelope["batch"], "candidate_digest": candidate_digest(candidate)}
        elif old == "PENDING" and new == "READY":
            if event["reason"] != "DEPENDENCIES_SATISFIED":
                _fail("REASON_INVALID", "READY requires dependency evidence")
            if not self._stage_applies(envelope)[0]:
                _fail("APPLICABILITY", "Task must be recorded NOT_APPLICABLE under graph rule")
            for dep in envelope["dependencies"]:
                related = self._task(state, dep["task_id"])
                if related["state"] not in ("ACCEPTED", "NOT_APPLICABLE"):
                    _fail("DEPENDENCY_UNREADY", dep["task_id"])
        elif new == "NOT_APPLICABLE":
            if old != "PENDING" or event["reason"] not in SKIP_REASONS or not event["evidence"]:
                _fail("SKIP_INVALID", "Skipping requires a predefined reason and evidence")
            applies, skip = self._stage_applies(envelope)
            if applies or skip is None or event["reason"] != skip["reason_code"]:
                _fail("SKIP_INVALID", "Authoritative workflow facts do not satisfy this skip rule")
            expected_outputs = set(skip["affected_outputs"])
            if set(event["affected_outputs"]) != expected_outputs or not expected_outputs:
                _fail("SKIP_COVERAGE", "Skip must list every affected output")
            for uri in event["evidence"]:
                if not self._path(uri).is_file():
                    _fail("SKIP_EVIDENCE", f"Skip evidence missing: {uri}")
            self._freeze_evidence_uris(task, event["evidence"])
        elif old == "READY" and new == "DISPATCHING":
            if event["reason"] != "DISPATCH_REQUESTED":
                _fail("REASON_INVALID", "Dispatching requires DISPATCH_REQUESTED")
            specialists, reviewers = self._active_agent_counts(state, excluding=envelope["task_id"])
            if envelope["execution_class"] == "professional" and specialists >= 2:
                _fail("CONCURRENCY_LIMIT", "Two specialist tasks are already active")
            if envelope["execution_class"] == "review" and reviewers >= 1:
                _fail("CONCURRENCY_LIMIT", "A reviewer task is already active")
        elif new == "RUNNING":
            if envelope["execution_class"] in HOST_CLASSES:
                if receipt is not None or not event["evidence"] or event["reason"] != (
                        "HOST_RECONCILED" if old == "UNKNOWN" else "HOST_EXECUTION_STARTED"):
                    _fail("HOST_START", "Host execution needs local start/reconciliation evidence")
                self._verify_host_progress(envelope, event["evidence"])
            else:
                if old not in ("DISPATCHING", "UNKNOWN") or receipt is None:
                    _fail("DISPATCH_REQUIRED", "Running requires a real dispatch receipt")
                self._verify_receipt(envelope, receipt)
                if receipt["status"] != "RUNNING" or receipt["agent_id"] is None:
                    _fail("DISPATCH_STATUS", "Running requires an observed agent ID")
                if old == "UNKNOWN" and task["receipt"] and receipt["dispatch_id"] != task["receipt"]["dispatch_id"]:
                    _fail("DISPATCH_BINDING", "Reconciliation must resume the original dispatch")
                if receipt["host_tool"] == "collaboration.list_agents":
                    if event["reason"] != "HOST_RECONCILED" or not event["evidence"]:
                        _fail("RECONCILIATION", "Agent observation requires reconciliation evidence")
                elif event["reason"] != "DISPATCH_CONFIRMED" or old == "UNKNOWN":
                    _fail("REASON_INVALID", "Spawn receipt has an invalid transition reason")
                task["receipt_history"].append(deepcopy(receipt))
                task["receipt"] = deepcopy(receipt)
        elif new == "UNKNOWN":
            if envelope["execution_class"] in HOST_CLASSES:
                if receipt is not None or event["reason"] != "DISPATCH_UNCERTAIN" or not event["evidence"]:
                    _fail("UNKNOWN_UNPROVEN", "Unknown host result needs original call evidence")
                self._verify_host_progress(envelope, event["evidence"])
            else:
                if event["reason"] != "DISPATCH_UNCERTAIN" or receipt is None:
                    _fail("UNKNOWN_UNPROVEN", "Unknown dispatch requires uncertainty receipt")
                self._verify_receipt(envelope, receipt)
                if receipt["status"] != "UNKNOWN":
                    _fail("UNKNOWN_UNPROVEN", "Receipt must report UNKNOWN")
                task["receipt_history"].append(deepcopy(receipt))
                task["receipt"] = deepcopy(receipt)
        elif old == "RUNNING" and new == "RESULT_SUBMITTED":
            expected_reason = ("HOST_RESULT_RECEIVED" if envelope["execution_class"] in HOST_CLASSES
                               else "RESULT_RECEIVED")
            if event["reason"] != expected_reason or candidate is None:
                _fail("CANDIDATE_REQUIRED", "Result submission requires a candidate")
            if envelope["execution_class"] not in HOST_CLASSES:
                self._require_origin_result(task, task["receipt"]["agent_id"], candidate)
            self._verify_candidate(task, candidate)
            if envelope["execution_class"] in HOST_CLASSES:
                self._validate_host_candidate(envelope, candidate)
            self._freeze_checks(task, candidate["checks"])
            self._freeze_checks(task, candidate["handoffs"])
            task["candidate"] = deepcopy(candidate)
        elif old == "RESULT_SUBMITTED" and new == "VALIDATING":
            if event["reason"] != "VALIDATION_STARTED":
                _fail("REASON_INVALID", "Validation requires VALIDATION_STARTED")
            self._verify_candidate(task, task["candidate"])
        elif old == "VALIDATING" and new == "REVIEW_REQUIRED":
            if self._graph_stage(envelope["node_id"])["review"] != "independent":
                _fail("REVIEW_RECURSION", "This graph node does not require another reviewer")
            if event["reason"] != "VALIDATION_PASSED" or not task["candidate"]:
                _fail("VALIDATION_REQUIRED", "Review requires completed validation")
            self._verify_candidate(task, task["candidate"])
            self._check_ids(event["check_results"], envelope["validators"], "id", "VALIDATION_COVERAGE")
            if any(item["status"] != "PASS" for item in task["candidate"]["checks"]):
                _fail("CANDIDATE_CHECKS", "Candidate reports failed or blocked checks")
            if any(item["status"] != "PASS" for item in event["check_results"]):
                _fail("VALIDATION_FAILED", "Every required validation must pass")
            self._review_evidence(event["check_results"])
            self._freeze_checks(task, event["check_results"])
            self._native_checks(task)
            if task["candidate"]["unresolved"]:
                _fail("UNRESOLVED_ITEMS", "Candidate contains unresolved items")
            task["validation"] = deepcopy(event["check_results"])
        elif old == "VALIDATING" and new == "ACCEPTED":
            stage = self._graph_stage(envelope["node_id"])
            is_host = envelope["execution_class"] in HOST_CLASSES
            if (envelope["execution_class"] != "review" and not is_host) or stage["review"] != "none":
                _fail("HOST_GATE", "Only a declared reviewer/host task may finish without another review")
            expected_reason = "HOST_EXECUTION_CONFIRMED" if is_host else "VALIDATION_PASSED"
            if event["reason"] != expected_reason or task["candidate"] is None:
                _fail("HOST_GATE", "Final validation reason or candidate is missing")
            if candidate is not None and candidate_digest(candidate) != candidate_digest(task["candidate"]):
                _fail("CANDIDATE_BINDING", "Final host candidate differs from submitted result")
            self._verify_candidate(task, task["candidate"])
            if is_host:
                self._validate_host_candidate(envelope, task["candidate"])
            self._check_ids(event["check_results"], envelope["validators"], "id", "VALIDATION_COVERAGE")
            if any(item["status"] != "PASS" for item in task["candidate"]["checks"]):
                _fail("CANDIDATE_CHECKS", "Reviewer candidate reports failed or blocked checks")
            if any(item["status"] != "PASS" for item in event["check_results"]):
                _fail("VALIDATION_FAILED", "Reviewer task checks did not all pass")
            self._review_evidence(event["check_results"])
            self._freeze_checks(task, event["check_results"])
            self._native_checks(task)
            if task["candidate"]["unresolved"]:
                _fail("UNRESOLVED_ITEMS", "Reviewer task has unresolved findings")
            task["validation"] = deepcopy(event["check_results"])
            for item in task["candidate"]["artifacts"]:
                owner = artifacts.get(item["slot"])
                if owner and owner["task_id"] != envelope["task_id"]:
                    _fail("OUTPUT_OWNERSHIP", f"Output {item['slot']} belongs to {owner['task_id']}")
                artifacts[item["slot"]] = {**deepcopy(item), "task_id": envelope["task_id"],
                                           "batch": envelope["batch"],
                                           "candidate_digest": candidate_digest(task["candidate"])}
        elif old == "REVIEW_REQUIRED" and new == "ACCEPTED":
            if event["reason"] != "REVIEW_PASSED" or review is None or task["review_dispatch"] is None:
                _fail("REVIEW_REQUIRED", "Acceptance requires separately dispatched review")
            if (review["task_id"] != envelope["task_id"] or review["batch"] != envelope["batch"]
                    or review["candidate_digest"] != candidate_digest(task["candidate"])):
                _fail("REVIEW_BINDING", "Review refers to an old candidate or batch")
            reviewer = task["review_dispatch"]
            if (review["reviewer_agent_id"] != reviewer["agent_id"]
                    or review["reviewer_dispatch_id"] != reviewer["dispatch_id"]
                    or review["reviewer_agent_id"] == task["receipt"]["agent_id"]):
                _fail("REVIEW_IDENTITY", "Reviewer is not the separately dispatched independent agent")
            self._require_origin_result(task, reviewer["agent_id"], review)
            self._verify_candidate(task, task["candidate"])
            self._check_ids(review["checks"], envelope["validators"], "id", "REVIEW_COVERAGE")
            self._check_ids(event["check_results"], envelope["validators"], "id", "REVIEW_COVERAGE")
            if (any(item["status"] != "PASS" for item in review["checks"])
                    or any(item["status"] != "PASS" for item in event["check_results"])
                    or review["failure_owner"] is not None):
                _fail("REVIEW_FAILED", "Every independent review item must pass")
            self._review_evidence(review["checks"])
            self._review_evidence(event["check_results"])
            self._freeze_checks(task, review["checks"])
            self._freeze_checks(task, event["check_results"])
            for item in task["candidate"]["artifacts"]:
                owner = artifacts.get(item["slot"])
                if owner and owner["task_id"] != envelope["task_id"]:
                    _fail("OUTPUT_OWNERSHIP", f"Output {item['slot']} belongs to {owner['task_id']}")
                artifacts[item["slot"]] = {**deepcopy(item), "task_id": envelope["task_id"],
                                           "batch": envelope["batch"], "candidate_digest": review["candidate_digest"]}
            task["review"] = deepcopy(review)
        elif new == "FAILED":
            if event["reason"] not in ("HOST_FAILED", "VALIDATION_FAILED", "REVIEW_FAILED"):
                _fail("REASON_INVALID", "Failure needs a host, validation or review reason")
            if old == "UNKNOWN" and (not event["evidence"] or event["reason"] != "HOST_FAILED"):
                _fail("RECONCILIATION", "UNKNOWN can fail only after recorded host reconciliation")
            if event["reason"] in ("VALIDATION_FAILED", "REVIEW_FAILED"):
                failed = [item["id"] for item in event["check_results"] if item["status"] == "FAIL"]
                if not failed:
                    _fail("FAILURE_UNPROVEN", "Failure event needs a failed check")
                for check_id in failed:
                    task["failure_counts"][check_id] = task["failure_counts"].get(check_id, 0) + 1
        elif new == "CANCELLED":
            if event["reason"] != "CANCEL_REQUESTED":
                _fail("REASON_INVALID", "Cancellation needs CANCEL_REQUESTED")
        elif new == "BLOCKED":
            if event["reason"] not in ("DEPENDENCY_BLOCKED", "VALIDATION_FAILED", "REVIEW_FAILED"):
                _fail("REASON_INVALID", "Block requires a dependency or failed check")
        elif old == "BLOCKED" and new == "READY":
            if event["reason"] != "DEPENDENCIES_SATISFIED":
                _fail("REASON_INVALID", "Unblock requires satisfied dependencies")
            for dep in envelope["dependencies"]:
                if self._task(state, dep["task_id"])["state"] not in ("ACCEPTED", "NOT_APPLICABLE"):
                    _fail("DEPENDENCY_UNREADY", dep["task_id"])
        if new not in ("RUNNING", "UNKNOWN") and receipt is not None:
            _fail("UNEXPECTED_RECEIPT", "This transition cannot attach a dispatch receipt")
        if (new != "RESULT_SUBMITTED" and not (old == "PENDING" and new == "ACCEPTED")
                and not (old == "VALIDATING" and new == "ACCEPTED"
                         and envelope["execution_class"] in HOST_CLASSES)) and candidate is not None:
            _fail("UNEXPECTED_CANDIDATE", "This transition cannot attach a candidate")
        if new != "ACCEPTED" and review is not None:
            _fail("UNEXPECTED_REVIEW", "This transition cannot attach a review")
        task["state"] = new
        task["version"] += 1

    def transition(self, event: dict, *, receipt: dict | None = None,
                   candidate: dict | None = None, review: dict | None = None) -> dict:
        validate_v6_protocol("state-event", event, self.schema_root)
        if receipt is not None:
            validate_v6_protocol("dispatch-receipt", receipt, self.schema_root)
        if candidate is not None:
            validate_v6_protocol("candidate-result", candidate, self.schema_root)
        if review is not None:
            validate_v6_protocol("review-record", review, self.schema_root)
        payload = {"event": event, "receipt": receipt, "candidate": candidate, "review": review}
        return self._apply("transition", payload, event["command_id"], event["expected_revision"],
                           lambda state, artifacts: self._transition(state, artifacts, event, receipt, candidate, review))

    def record_dispatch(self, event: dict, receipt: dict) -> dict:
        return self.transition(event, receipt=receipt)

    def submit_candidate(self, event: dict, candidate: dict) -> dict:
        return self.transition(event, candidate=candidate)

    def record_review(self, event: dict, review: dict) -> dict:
        return self.transition(event, review=review)

    def complete_host_task(self, event: dict, candidate: dict) -> dict:
        return self.transition(event, candidate=candidate)

    def register_review_dispatch(self, receipt: dict, command_id: str,
                                 expected_revision: int, evidence: list[str] | None = None) -> dict:
        validate_v6_protocol("dispatch-receipt", receipt, self.schema_root)
        evidence = evidence or []
        def mutate(state, artifacts):
            task = self._task(state, receipt["task_id"], receipt["batch"])
            if task["state"] != "REVIEW_REQUIRED" or task["review_dispatch"] is not None:
                _fail("REVIEW_DISPATCH_STATE", "Review may be dispatched once after validation")
            self._verify_receipt(task["envelope"], receipt, review=True)
            if self._active_agent_counts(state, excluding=receipt["task_id"])[1] >= 1:
                _fail("CONCURRENCY_LIMIT", "A reviewer task is already active")
            if (receipt["status"] != "RUNNING" or receipt["host_tool"] not in
                    ("collaboration.spawn_agent", "collaboration.list_agents")
                    or receipt["agent_id"] == task["receipt"]["agent_id"]):
                _fail("REVIEW_IDENTITY", "Review dispatch needs a distinct observed agent")
            if receipt["host_tool"] == "collaboration.list_agents":
                if not evidence:
                    _fail("RECONCILIATION", "Reviewer observation requires evidence")
                for uri in evidence:
                    if not self._path(uri).is_file():
                        _fail("RECONCILIATION", f"Reviewer observation evidence missing: {uri}")
            task["review_dispatch"] = deepcopy(receipt)
            task["version"] += 1
        return self._apply("review_dispatch", {"receipt": receipt, "evidence": evidence},
                           command_id, expected_revision, mutate)

    def record_message(self, message: dict, command_id: str,
                       expected_revision: int) -> dict:
        validate_v6_protocol("agent-message", message, self.schema_root)
        def mutate(state, artifacts):
            task = self._task(state, message["task_id"], message["batch"])
            agents = {item["agent_id"] for item in (task["receipt"], task["review_dispatch"])
                      if item and item["agent_id"]}
            if message["sender_id"] not in agents and message["sender_id"] != "kernel":
                _fail("MESSAGE_SENDER", "Message sender is not a dispatched participant")
            if message["recipient_id"] not in agents and message["recipient_id"] != "kernel":
                _fail("MESSAGE_RECIPIENT", "Message recipient is not a dispatched participant")
            ids = {item["message_id"] for item in task["messages"]}
            if message["message_id"] in ids:
                _fail("MESSAGE_DUPLICATE", message["message_id"])
            if message["in_reply_to"] is not None and message["in_reply_to"] not in ids:
                _fail("MESSAGE_THREAD", "Reply references an unknown message")
            if message["subject_uri"] is not None:
                self._file_matches(message["subject_uri"], message["subject_sha256"],
                                   label="agent message subject")
                if message["type"] == "RESULT":
                    reviewer_result = (task["state"] == "REVIEW_REQUIRED"
                                       and task["review_dispatch"] is not None
                                       and message["sender_id"] == task["review_dispatch"]["agent_id"])
                    if task["state"] == "REVIEW_REQUIRED" and not reviewer_result:
                        _fail("RESULT_SENDER", "Only the dispatched reviewer may submit a review RESULT")
                    directory = "reviews" if reviewer_result else "candidates"
                    prefix = self._path(f"runtime/v6/{directory}/{message['task_id']}/{message['batch']}/")
                    if not self._path(message["subject_uri"]).is_relative_to(prefix):
                        _fail("RESULT_SCOPE", f"Agent RESULT must be written in its {directory} directory")
            if task["state"] in ("ACCEPTED", "NOT_APPLICABLE", "STALE", "CANCELLED"):
                _fail("MESSAGE_LATE", "Terminal task cannot accept a new message")
            task["messages"].append(deepcopy(message))
            task["version"] += 1
        return self._apply("agent_message", message, command_id, expected_revision, mutate)

    def pending_action(self, task_id: str) -> dict | None:
        task = self.inspect(task_id)
        if task["state"] == "DISPATCHING":
            return {"kind": "dispatch", "task_id": task_id,
                    "batch": task["envelope"]["batch"],
                    "dispatch_id": expected_dispatch_id(task["envelope"]),
                    "task_digest": envelope_digest(task["envelope"])}
        if task["state"] == "REVIEW_REQUIRED" and task["review_dispatch"] is None:
            return {"kind": "review_dispatch", "task_id": task_id,
                    "batch": task["envelope"]["batch"],
                    "dispatch_id": expected_review_dispatch_id(task["envelope"]),
                    "task_digest": envelope_digest(task["envelope"])}
        if task["state"] == "UNKNOWN":
            return {"kind": "reconcile", "task_id": task_id,
                    "batch": task["envelope"]["batch"],
                    "dispatch_id": expected_dispatch_id(task["envelope"]),
                    "task_digest": envelope_digest(task["envelope"])}
        return None
