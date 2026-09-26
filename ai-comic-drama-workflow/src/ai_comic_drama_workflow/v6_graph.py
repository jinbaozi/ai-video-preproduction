"""Strict, data-driven stage graph for the V6 coordinator.

The graph decides which stage may run and which stages need an explicit
NOT_APPLICABLE record. Task state transitions and evidence validation belong to
the V6 kernel; this module does not turn a graph edge into an acceptance claim.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
GRAPH_PATH = ROOT / "workflow-v6.json"
EXECUTOR_KINDS = frozenset({"specialist", "reviewer", "host", "kernel"})
SCOPES = frozenset({"project", "scene", "asset", "panel", "shot", "adjacent_pair", "generation_request", "take"})
CHECKERS = frozenset({
    "source_integrity", "reference_observation", "canon_contract", "module_receipt",
    "native_validator", "handoff", "image_prompt_contract", "image_call_evidence",
    "image_visual_review", "control_verify", "compile_manifest", "compile_semantics",
    "preproduction_final", "freeze_request", "execution_provenance", "take_probe",
    "shot_coverage", "selected_take", "adjacent_coverage", "assembly_edl",
    "post_obligations", "whole_review", "video_final",
})
CONDITION_FIELDS = {
    "delivery": {"full", "text-only"},
    "production_target": {"none", "video"},
    "observation_required": {True, False},
    "control_required": {True, False},
    "visual_jobs_present": {True, False},
    "board_jobs_present": {True, False},
}
CONDITION_REQUIRED_VALUES = {
    "delivery": "full",
    "production_target": "video",
    "observation_required": True,
    "control_required": True,
    "visual_jobs_present": True,
    "board_jobs_present": True,
}
NODE_KEYS = frozenset({
    "id", "label", "role", "executor_kind", "scope", "locked_skill", "depends_on",
    "output_types", "checkers", "review", "handoff_required", "applicability", "skip",
})
IMAGE_SKIP_FIELDS = {"visual_prompts": "visual_jobs_present",
                     "visual_media": "visual_jobs_present",
                     "board_prompts": "board_jobs_present",
                     "board_media": "board_jobs_present"}
GRAPH_KEYS = frozenset({"schema_version", "workflow_id", "execution_mode", "limits", "locked_skills", "nodes"})


def _keys(value: Any, expected: frozenset[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        missing = sorted(expected - set(value)) if isinstance(value, dict) else sorted(expected)
        extra = sorted(set(value) - expected) if isinstance(value, dict) else []
        raise ValueError(f"{label} keys differ: missing={missing}, extra={extra}")


def _nonempty(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")


def _string_list(value: Any, label: str, *, nonempty: bool = False) -> None:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{label} must be a {'nonempty ' if nonempty else ''}list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} contains an empty or non-string item")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicates")


def _condition(stage: dict[str, Any]) -> tuple[str | None, Any]:
    condition = stage["applicability"]
    if not isinstance(condition, dict):
        raise ValueError(f"{stage['id']} applicability must be an object")
    if condition == {"kind": "always"}:
        if stage["skip"] is not None:
            raise ValueError(f"{stage['id']} unconditional stage cannot have a skip rule")
        return None, None
    _keys(condition, frozenset({"kind", "field", "equals"}), f"{stage['id']} applicability")
    if condition["kind"] != "equals" or condition["field"] not in CONDITION_FIELDS:
        raise ValueError(f"{stage['id']} has an unsupported applicability rule")
    field = condition["field"]
    expected = CONDITION_REQUIRED_VALUES[field]
    if type(condition["equals"]) is not type(expected) or condition["equals"] != expected:
        raise ValueError(f"{stage['id']} applicability must require {field}={expected}")
    skip = stage["skip"]
    _keys(skip, frozenset({"reason_code", "reason", "affected_outputs"}), f"{stage['id']} skip")
    _nonempty(skip["reason_code"], f"{stage['id']} skip reason_code")
    _nonempty(skip["reason"], f"{stage['id']} skip reason")
    _string_list(skip["affected_outputs"], f"{stage['id']} affected_outputs", nonempty=True)
    if not set(skip["affected_outputs"]).issubset(stage["output_types"]):
        raise ValueError(f"{stage['id']} skip outputs must be declared stage outputs")
    if stage['id'] in IMAGE_SKIP_FIELDS:
        extra = stage['skip_if_empty']
        _keys(extra, frozenset({"field", "reason_code", "reason", "affected_outputs"}),
              f"{stage['id']} skip_if_empty")
        if (field != 'delivery' or extra['field'] != IMAGE_SKIP_FIELDS[stage['id']]
                or extra['reason_code'] != 'NO_APPLICABLE_ASSETS'):
            raise ValueError(f"{stage['id']} empty-image skip rule differs from graph facts")
        _nonempty(extra['reason'], f"{stage['id']} empty-image skip reason")
        _string_list(extra['affected_outputs'], f"{stage['id']} empty-image outputs", nonempty=True)
        if set(extra['affected_outputs']) != set(stage['output_types']):
            raise ValueError(f"{stage['id']} empty-image skip must cover all outputs")
    return field, expected


def validate_graph(graph: dict[str, Any], *, module_names: set[str] | None = None) -> dict[str, Any]:
    """Reject malformed stages, unknown controls, cycles and undeclared Skills."""
    _keys(graph, GRAPH_KEYS, "workflow graph")
    if graph["schema_version"] != "6.0" or graph["workflow_id"] != "ai-comic-drama-v6":
        raise ValueError("Expected ai-comic-drama-v6 graph version 6.0")
    if graph["execution_mode"] != "codex-agents":
        raise ValueError("V6 requires the Codex agent execution mode")
    _keys(graph["limits"], frozenset({"specialists", "reviewers"}), "workflow limits")
    if (type(graph["limits"]["specialists"]) is not int or graph["limits"]["specialists"] != 2
            or type(graph["limits"]["reviewers"]) is not int or graph["limits"]["reviewers"] != 1):
        raise ValueError("V6 concurrency limits must be two specialists and one reviewer")
    _string_list(graph["locked_skills"], "locked_skills", nonempty=True)
    declared_skills = set(graph["locked_skills"])
    if module_names is not None and declared_skills != set(module_names):
        raise ValueError("Graph locked_skills differ from the supplied module lock")
    nodes = graph["nodes"]
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Graph nodes must be a nonempty list")
    seen: set[str] = set()
    used_skills: set[str] = set()
    for node in nodes:
        expected_keys = NODE_KEYS | ({"skip_if_empty"} if node.get('id') in IMAGE_SKIP_FIELDS else set())
        _keys(node, expected_keys, "workflow node")
        stage_id = node["id"]
        _nonempty(stage_id, "node id")
        if stage_id in seen:
            raise ValueError(f"Duplicate node ID: {stage_id}")
        for field in ("label", "role"):
            _nonempty(node[field], f"{stage_id} {field}")
        if node["executor_kind"] not in EXECUTOR_KINDS:
            raise ValueError(f"{stage_id} has an unsupported executor kind")
        if node["scope"] not in SCOPES:
            raise ValueError(f"{stage_id} has an unsupported scope")
        skill = node["locked_skill"]
        if skill is not None:
            _nonempty(skill, f"{stage_id} locked_skill")
            if skill not in declared_skills or node["executor_kind"] not in ("specialist", "reviewer"):
                raise ValueError(f"{stage_id} has an invalid locked Skill assignment")
            used_skills.add(skill)
        if node["executor_kind"] == "specialist" and node["role"] != "canon" and skill is None:
            raise ValueError(f"{stage_id} specialist must have a locked Skill")
        if node["executor_kind"] in ("host", "kernel") and skill is not None:
            raise ValueError(f"{stage_id} host/kernel cannot claim a Skill receipt")
        _string_list(node["depends_on"], f"{stage_id} depends_on")
        if any(dep not in seen for dep in node["depends_on"]):
            raise ValueError(f"{stage_id} has an unknown, future or cyclic dependency")
        _string_list(node["output_types"], f"{stage_id} output_types", nonempty=True)
        _string_list(node["checkers"], f"{stage_id} checkers", nonempty=True)
        if not set(node["checkers"]).issubset(CHECKERS):
            raise ValueError(f"{stage_id} names an unknown checker")
        if node["review"] not in ("independent", "none"):
            raise ValueError(f"{stage_id} review must be independent or none")
        if node["executor_kind"] == "reviewer" and node["review"] != "none":
            raise ValueError(f"{stage_id} reviewer tasks cannot recurse into review")
        if node["executor_kind"] == "specialist" and node["review"] != "independent":
            raise ValueError(f"{stage_id} specialist requires independent review")
        if type(node["handoff_required"]) is not bool:
            raise ValueError(f"{stage_id} handoff_required must be Boolean")
        if node["executor_kind"] == "specialist" and not node["handoff_required"]:
            raise ValueError(f"{stage_id} specialist requires a handoff")
        _condition(node)
        seen.add(stage_id)
    if used_skills != declared_skills:
        raise ValueError("Every locked Skill must be used by a graph stage")
    return graph


def load_graph(path: str | Path | None = None, *, module_lock: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load and validate a graph; default source graph is bundled with the suite."""
    source = Path(path) if path is not None else GRAPH_PATH
    if path is None and not source.is_file():
        source = Path(sys.prefix) / "share" / "ai-comic-drama-workflow" / "workflow-v6.json"
    graph = json.loads(source.read_text(encoding="utf-8"))
    if module_lock is None and path is None:
        lock_path = source.parent / "modules.lock.json"
        module_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    modules = set(module_lock["modules"]) if module_lock is not None else None
    return validate_graph(graph, module_names=modules)


def stage_by_id(graph: dict[str, Any], stage_id: str) -> dict[str, Any]:
    for node in graph["nodes"]:
        if node["id"] == stage_id:
            return node
    raise KeyError(stage_id)


def graph_to_mermaid(graph: dict[str, Any]) -> str:
    """Render the validated executable graph as a deterministic Mermaid diagram."""
    validate_graph(graph)
    node_ids = {node["id"]: f"n{index}" for index, node in enumerate(graph["nodes"])}
    lines = ["flowchart TD"]
    for node in graph["nodes"]:
        parts = [node["label"], f"角色: {node['role']}"]
        if node["locked_skill"] is not None:
            parts.append(f"Skill: {node['locked_skill']}")
        condition = node["applicability"]
        if condition["kind"] == "equals":
            value = condition["equals"]
            parts.append(f"条件: {condition['field']}={str(value).lower() if isinstance(value, bool) else value}")
        label = "<br/>".join(escape(part, quote=True) for part in parts)
        lines.append(f'    {node_ids[node["id"]]}["{label}"]')
    for node in graph["nodes"]:
        for dependency in node["depends_on"]:
            lines.append(f"    {node_ids[dependency]} --> {node_ids[node['id']]}")
    return "\n".join(lines) + "\n"


def _applies(stage: dict[str, Any], context: dict[str, Any]) -> tuple[bool, str | None, Any, Any, dict | None]:
    field, expected = _condition(stage)
    if field is None:
        return True, None, None, None, None
    if field not in context:
        raise ValueError(f"Missing applicability fact: {field}")
    observed = context[field]
    if type(observed) is not type(expected) or observed not in CONDITION_FIELDS[field]:
        raise ValueError(f"Invalid applicability fact: {field}")
    if observed != expected:
        return False, field, expected, observed, stage['skip']
    if stage['id'] in IMAGE_SKIP_FIELDS:
        field = stage['skip_if_empty']['field']
        if field not in context:
            raise ValueError(f"Missing applicability fact: {field}")
        observed = context[field]
        if type(observed) is not bool:
            raise ValueError(f"Invalid applicability fact: {field}")
        return observed, field, True, observed, stage['skip_if_empty']
    return True, field, expected, observed, None


def stage_applicability(stage: dict[str, Any], context: dict[str, Any], *, evidence_ref: str | None = None) -> dict[str, Any]:
    """Evaluate a typed condition; require evidence before materializing a skip."""
    applies, field, expected, observed, skip = _applies(stage, context)
    if applies:
        return {"node_id": stage["id"], "status": "APPLICABLE"}
    _nonempty(evidence_ref, f"{stage['id']} skip evidence_ref")
    return {
        "node_id": stage["id"], "status": "NOT_APPLICABLE",
        "rule": {"field": field, "equals": expected}, "observed_value": observed,
        "reason_code": skip["reason_code"], "reason": skip["reason"],
        "affected_outputs": list(skip["affected_outputs"]),
        "evidence_ref": evidence_ref,
    }


def validate_skip_record(stage: dict[str, Any], context: dict[str, Any], record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        raise ValueError("NOT_APPLICABLE record must be an object")
    evidence = record.get("evidence_ref")
    expected = stage_applicability(stage, context, evidence_ref=evidence)
    if expected["status"] != "NOT_APPLICABLE" or record != expected:
        raise ValueError(f"Invalid or stale NOT_APPLICABLE record: {stage['id']}")


def ready_stages(graph: dict[str, Any], states: dict[str, dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return unstarted or stale stages whose predecessors have evidence-backed completion."""
    known = {node["id"] for node in graph["nodes"]}
    if not isinstance(states, dict) or set(states) - known:
        raise ValueError("State map contains unknown graph nodes")
    complete: set[str] = set()
    pending: list[dict[str, Any]] = []
    for node in graph["nodes"]:
        record = states.get(node["id"])
        if record is None:
            if set(node["depends_on"]) <= complete:
                pending.append(node)
            continue
        if not isinstance(record, dict):
            raise ValueError(f"{node['id']} state must be a record")
        status = record.get("status")
        if status == "NOT_APPLICABLE":
            validate_skip_record(node, context, record)
            complete.add(node["id"])
        elif status == "ACCEPTED":
            if not _applies(node, context)[0]:
                raise ValueError(f"{node['id']} accepted result is stale under current applicability")
            complete.add(node["id"])
        elif status in {"PENDING", "STALE"}:
            if set(node["depends_on"]) <= complete:
                pending.append(node)
        elif status not in {"PENDING", "READY", "DISPATCHING", "RUNNING", "RESULT_SUBMITTED", "VALIDATING",
                            "REVIEW_REQUIRED", "BLOCKED", "FAILED", "UNKNOWN", "STALE", "CANCELLED"}:
            raise ValueError(f"{node['id']} has an unknown task status")
    for node in graph["nodes"]:
        if node["id"] in complete and any(dep not in complete for dep in node["depends_on"]):
            raise ValueError(f"{node['id']} completed before a dependency")
    return pending
