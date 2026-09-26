"""Image host boundary for V6 image tool calls and provided media.

These helpers prepare actions and verify returned bytes. They do not call an
image model or register V5 media; V6Runtime performs the host action and
commits V5.submit together with the V6 ACCEPTED event.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from .transactions import before_write, transaction
from .utils import atomic_write
from .v5 import V5Kernel, lock_refs
from .v5_modules import ROOT, digest_file, read
from .v5_protocol import validate_protocol as validate_v5
from .v6_protocol import compact_json, envelope_digest, validate_v6_protocol


def image_action_id(envelope: dict) -> str:
    return "image-" + hashlib.sha256((envelope["task_id"] + ":" + str(envelope["batch"])
              + ":" + envelope_digest(envelope)).encode()).hexdigest()[:24]


def _project_path(root: Path, uri: str) -> Path:
    path = Path(uri)
    if not uri or path.is_absolute() or ".." in path.parts or "\\" in uri:
        raise ValueError("Image host URI must be project-relative")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Image host URI escapes the project")
    return resolved


def _bytes(root: Path, uri: str, expected: str) -> Path:
    path = _project_path(root, uri)
    if not path.is_file() or digest_file(path) != expected:
        raise ValueError(f"Image host bytes missing or changed: {uri}")
    return path


def _content_addressed(root: Path, uri: str, expected: str) -> Path:
    path = _bytes(root, uri, expected)
    if path.parent != root / "runtime/v6/host-evidence" or path.name != expected + ".json":
        raise ValueError("Image host evidence must use its content hash as filename")
    return path


def _bind(envelope: dict, v5_task: dict) -> None:
    validate_v6_protocol("task-envelope", envelope)
    if envelope["execution_class"] != "external_image" or envelope["node_id"] not in (
            "visual_media", "board_media"):
        raise ValueError("Image host action requires an external_image graph task")
    if (v5_task.get("kind") != "image" or v5_task.get("task_id") != envelope["task_id"]
            or v5_task.get("stage") not in (5, 7)):
        raise ValueError("Frozen V5 image task differs from V6 envelope")
    expected_node = "visual_media" if v5_task["stage"] == 5 else "board_media"
    if envelope["node_id"] != expected_node:
        raise ValueError("V5 image stage differs from V6 graph node")


def pending_image_action(envelope: dict, v5_task: dict,
                         project_root: str | Path | None = None) -> dict:
    """Describe a single host image action without submitting or paying for it.

    After V5.begin_image, an in-flight task returns lookup-only. This prevents
    a scheduler restart from repeating a possibly submitted model call.
    """
    _bind(envelope, v5_task)
    root = Path(project_root).expanduser().resolve() if project_root is not None else None
    prompt = v5_task.get("prompt") or {}
    prompt_uri, prompt_sha = prompt.get("uri"), prompt.get("sha256")
    if not isinstance(prompt_uri, str) or not isinstance(prompt_sha, str):
        raise ValueError("Frozen image prompt URI and hash are required")
    if root is not None:
        _bytes(root, prompt_uri, prompt_sha)
    references = [{"key": item["key"], "sha256": item["sha256"]}
                  for item in v5_task["job"]["references"]]
    providers = ["provided"]
    kind = "IMPORT_PROVIDED"
    if root is not None:
        state = read(root / "state.json")
        registered = (state.get("host") or {}).get("providers") or ["provided"]
        providers = [name for name in ("provided", "image_gen") if name in registered]
        if not providers:
            raise ValueError("No registered image provider is available")
        if "image_gen" in providers:
            kind = "CHOOSE_PROVIDER"
        inflight = state.get("inflight")
        if inflight:
            if inflight.get("task_id") != envelope["task_id"]:
                raise ValueError("A different image job is in flight; reconcile it first")
            kind = "RECONCILE_ONLY"
    action = {"schema": "image-host-action/6.0", "action_id": image_action_id(envelope),
              "task_id": envelope["task_id"], "batch": envelope["batch"],
              "task_digest": envelope_digest(envelope), "kind": kind,
              "prompt_uri": prompt_uri, "prompt_sha256": prompt_sha,
              "reference_bindings": references,
              "candidate_dir": f"runtime/v6/candidates/{envelope['task_id']}/{envelope['batch']}/",
              "allowed_providers": providers,
              "generation_authorization_required": "image_gen" in providers}
    validate_v6_protocol("image-host-action", action)
    return action


def store_image_action(project_root: str | Path, action: dict) -> tuple[str, str]:
    """Persist a frozen host action; this records intent and never calls a model."""
    validate_v6_protocol("image-host-action", action)
    root = Path(project_root).expanduser().resolve()
    raw = compact_json(action)
    checksum = hashlib.sha256(raw).hexdigest()
    uri = f"runtime/v6/host-evidence/{checksum}.json"
    target = _project_path(root, uri)
    with transaction(root):
        if target.exists():
            if target.read_bytes() != raw:
                raise ValueError("Stored image host action hash collision")
        else:
            before_write(root, target)
            atomic_write(target, raw)
    return uri, checksum


def _decode_image(path: Path) -> None:
    if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("Media must be a still PNG, JPEG or WebP image")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "stream=codec_type,width,height", "-of", "json", str(path)],
                           capture_output=True, text=True)
    try:
        streams = json.loads(probe.stdout)["streams"]
    except (ValueError, KeyError):
        streams = []
    if probe.returncode or not any(item.get("codec_type") == "video"
                                   and item.get("width", 0) > 0 and item.get("height", 0) > 0
                                   for item in streams):
        raise ValueError("Image file cannot be probed")
    decode = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path),
                             "-frames:v", "1", "-f", "null", "-"], capture_output=True)
    if decode.returncode:
        raise ValueError("Image frame cannot be decoded")


def validate_media_result(project_root: str | Path, envelope: dict, v5_task: dict,
                          candidate: dict, *, skill_root: str | Path = ROOT) -> dict:
    """Verify call provenance, copied media bytes, visual review, and V5 result.

    The returned record is read-only evidence; V5Kernel.submit remains the
    final native importer and should run in the same transaction as V6 ACCEPTED.
    """
    root = Path(project_root).expanduser().resolve()
    _bind(envelope, v5_task)
    validate_v6_protocol("candidate-result", candidate)
    if (candidate["task_id"] != envelope["task_id"] or candidate["batch"] != envelope["batch"]
            or candidate["agent_id"] != "image_host" or candidate["input_digest"] != envelope["input_digest"]
            or candidate["module_receipts"]):
        raise ValueError("Image candidate is not bound to the host task and frozen inputs")
    host_uri, host_sha = candidate.get("host_record_uri"), candidate.get("host_record_sha256")
    if not host_uri or not host_sha:
        raise ValueError("External image candidate needs a host call record")
    record = read(_content_addressed(root, host_uri, host_sha))
    validate_v6_protocol("image-host-record", record)
    if (record["status"] != "COMPLETED" or record["action_id"] != image_action_id(envelope)
            or record["task_id"] != envelope["task_id"] or record["batch"] != envelope["batch"]
            or record["task_digest"] != envelope_digest(envelope)):
        raise ValueError("Image call record is incomplete or refers to another frozen task")
    host = (read(root / "state.json").get("host") or {})
    providers = host.get("providers") or ["provided"]
    if record["provider"] not in providers:
        raise ValueError("Image provider was not registered by the current host")
    if record["provider"] == "image_gen":
        if record["tool"] not in (host.get("image_tools") or []):
            raise ValueError("Image tool was not registered by the current host")
        raw = read(_content_addressed(root, record["tool_result_uri"], record["tool_result_sha256"]))
        if not isinstance(raw, dict) or not raw:
            raise ValueError("Image generation raw tool result is empty")
    else:
        source = Path(record["source_uri"]).expanduser()
        if not source.is_absolute():
            source = _project_path(root, record["source_uri"])
        if not source.is_file() or digest_file(source) != record["source_sha256"]:
            raise ValueError("Provided source media bytes changed")
    expected = envelope["expected_artifacts"]
    if len(expected) != 1 or len(candidate["artifacts"]) != 1:
        raise ValueError("Image task must deliver exactly one graph-declared media artifact")
    spec, artifact = expected[0], candidate["artifacts"][0]
    if artifact["slot"] != spec["slot"] or artifact["kind"] != spec["kind"]:
        raise ValueError("Image candidate artifact differs from declared output")
    media_path = _bytes(root, artifact["uri"], artifact["sha256"])
    candidate_dir = _project_path(root, spec["uri_prefix"])
    if not media_path.is_relative_to(candidate_dir):
        raise ValueError("Image media must be copied into the candidate directory")
    if record["media_uri"] != artifact["uri"] or record["media_sha256"] != artifact["sha256"]:
        raise ValueError("Image call record does not bind delivered media bytes")
    _decode_image(media_path)
    result_uri, result_sha = candidate["result_uri"], candidate["result_sha256"]
    if not result_uri or not result_sha:
        raise ValueError("Image media requires a frozen V5 RoleResult")
    result_path = _bytes(root, result_uri, result_sha)
    if not result_path.is_relative_to(candidate_dir):
        raise ValueError("V5 RoleResult must be copied into the candidate directory")
    result = read(result_path)
    validate_v5("role-result", result, Path(skill_root))
    if (result["task_id"] != v5_task["task_id"]
            or result["context_fingerprint"] != v5_task["context_fingerprint"]
            or result.get("conflicts") or result.get("unresolved")):
        raise ValueError("V5 image RoleResult is stale or unresolved")
    media = result.get("media") or {}
    claimed_path = Path(media.get("path") or "")
    claimed_path = claimed_path.resolve() if claimed_path.is_absolute() else _project_path(root, str(claimed_path))
    if claimed_path != media_path or media.get("sha256") != artifact["sha256"]:
        raise ValueError("V5 media RoleResult does not bind the copied image bytes")
    if media.get("provider") != record["provider"]:
        raise ValueError("V5 image provider differs from host record")
    call_id = record["tool_call_id"] or "provided"
    expected_call = f"v6-image-host-record:{host_sha}:{record['tool']}:{call_id}"
    if media.get("call_evidence") != expected_call:
        raise ValueError("V5 call evidence does not bind the immutable host record")
    bindings = [{"key": item["key"], "sha256": item["sha256"]}
                for item in v5_task["job"]["references"]]
    if media.get("input_bindings") != bindings:
        raise ValueError("Actual image input bindings differ from the frozen job")
    review = media.get("visual_review") or {}
    if (review.get("status") != "PASS" or review.get("sha256") != artifact["sha256"]
            or not review.get("findings")):
        raise ValueError("Visual review must bind and describe the actual image bytes")
    v5 = V5Kernel(root, Path(skill_root))
    v5.receipt_audit(v5_task, result)
    v5.check_image_host(media)
    if v5.audit_required():
        v5.check_findings(review["findings"], lock_refs(v5_task["job"]))
    return {"action_id": record["action_id"], "provider": record["provider"],
            "call_record_uri": host_uri, "call_record_sha256": host_sha,
            "media_uri": artifact["uri"], "media_sha256": artifact["sha256"],
            "result_uri": result_uri, "result_sha256": result_sha,
            "visual_review": review["status"]}
