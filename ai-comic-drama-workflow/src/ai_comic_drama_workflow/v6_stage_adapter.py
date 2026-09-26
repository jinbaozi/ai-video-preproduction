"""Pure conversion from V6 graph stages to task-envelope assignments.

The caller supplies a frozen catalogue of required stage instances. Existing
task rows alone cannot prove that a scene, asset, shot or adjacent pair was not
omitted, so predecessor selection refuses to guess missing scope membership.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .v6_graph import CHECKERS, stage_by_id


CHECKER_KINDS = {
    "source_integrity": "hash", "reference_observation": "evidence",
    "canon_contract": "schema", "module_receipt": "hash",
    "native_validator": "native", "handoff": "handoff",
    "image_prompt_contract": "schema", "image_call_evidence": "evidence",
    "image_visual_review": "media", "control_verify": "evidence",
    "compile_manifest": "hash", "compile_semantics": "manual",
    "preproduction_final": "evidence", "freeze_request": "schema",
    "execution_provenance": "evidence", "take_probe": "media",
    "shot_coverage": "manual", "selected_take": "evidence",
    "adjacent_coverage": "manual", "assembly_edl": "media",
    "post_obligations": "manual", "whole_review": "manual",
    "video_final": "evidence",
}
if set(CHECKER_KINDS) != CHECKERS:
    raise RuntimeError("V6 graph checkers and envelope validator kinds have diverged")


def _scope(scope: dict[str, Any], kind: str | None = None) -> tuple[str, tuple[str, ...]]:
    if not isinstance(scope, dict) or set(scope) != {"kind", "ids"}:
        raise ValueError("Scope must contain exactly kind and ids")
    value, ids = scope["kind"], scope["ids"]
    if kind is not None and value != kind:
        raise ValueError(f"Scope kind {value!r} differs from graph kind {kind!r}")
    if not isinstance(value, str) or not isinstance(ids, list):
        raise ValueError("Scope kind and ids have invalid types")
    if len(ids) != (0 if value == "project" else 2 if value == "adjacent_pair" else 1):
        raise ValueError(f"Scope {value} has an invalid number of IDs")
    if any(not isinstance(item, str) or not item or not item[0].isalpha()
           or not all(c.isascii() and (c.isalnum() or c in "_.:-") for c in item) for item in ids):
        raise ValueError("Scope IDs must match the V6 task-envelope identifier contract")
    if len(set(ids)) != len(ids):
        raise ValueError("Scope IDs must be unique")
    return value, tuple(ids)


def slot_for(node_id: str, scope: dict[str, Any], output_type: str) -> str:
    """Injective slot name for a stage, ordered scope IDs and output type."""
    if not isinstance(node_id, str) or not node_id or not node_id[0].isalpha():
        raise ValueError("Invalid graph node ID")
    if not isinstance(output_type, str) or not output_type or not output_type[0].isalpha():
        raise ValueError("Invalid graph output type")
    kind, ids = _scope(scope)
    encoded = "project" if not ids else ".".join(f"{len(raw)}x{raw.hex()}" for raw in (item.encode() for item in ids))
    return f"{node_id}:{kind}:{encoded}:{output_type}"


def _catalogue(graph: dict[str, Any], required_scopes: Mapping[str, Sequence[dict]], node_id: str) -> list[tuple[str, tuple[str, ...]]]:
    if node_id not in required_scopes:
        raise ValueError(f"Frozen required scope catalogue misses {node_id}")
    kind = stage_by_id(graph, node_id)["scope"]
    scopes = required_scopes[node_id]
    if not isinstance(scopes, (list, tuple)) or not scopes:
        raise ValueError(f"Frozen required scope catalogue is empty for {node_id}")
    normalized = [_scope(item, kind) for item in scopes]
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"Duplicate required scope for {node_id}")
    if kind == "project" and normalized != [("project", ())]:
        raise ValueError(f"Project stage {node_id} must have exactly one project scope")
    return normalized


def _rows(task_records: Mapping[str, dict] | Sequence[dict]) -> list[dict]:
    rows = list(task_records.values()) if isinstance(task_records, Mapping) else list(task_records)
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("envelope"), dict):
            raise ValueError("Task records must contain V6 envelopes")
    return rows


def _required_for_edge(graph: dict[str, Any], current: dict, scope: tuple[str, tuple[str, ...]],
                       dep_id: str, required_scopes: Mapping[str, Sequence[dict]],
                       scope_links: Mapping[str, Sequence[dict]]) -> list[tuple[str, tuple[str, ...]]]:
    catalogue = _catalogue(graph, required_scopes, dep_id)
    dep_kind = stage_by_id(graph, dep_id)["scope"]
    if dep_kind == "project":
        expected = catalogue
    elif scope[0] == "project":
        expected = catalogue  # A project stage consumes every required predecessor instance.
    elif dep_kind == scope[0]:
        expected = [scope]
        if scope not in catalogue:
            raise ValueError(f"{current['id']} scope is not represented in {dep_id}")
    else:
        if dep_id not in scope_links:
            raise ValueError(f"Cross-scope edge {dep_id} -> {current['id']} needs frozen scope links")
        links = scope_links[dep_id]
        if not isinstance(links, (list, tuple)) or not links:
            raise ValueError(f"Cross-scope edge {dep_id} -> {current['id']} has no required instances")
        expected = [_scope(item, dep_kind) for item in links]
        if len(set(expected)) != len(expected) or any(item not in catalogue for item in expected):
            raise ValueError(f"Cross-scope edge {dep_id} -> {current['id']} has invalid instance links")
    if dep_id in scope_links and dep_kind == "project":
        if [_scope(item, dep_kind) for item in scope_links[dep_id]] != expected:
            raise ValueError(f"Project predecessor links differ for {dep_id}")
    if dep_id in scope_links and scope[0] == "project" and dep_kind != "project":
        if [_scope(item, dep_kind) for item in scope_links[dep_id]] != expected:
            raise ValueError(f"Project stage must aggregate every {dep_id} instance")
    return expected


def predecessor_task_ids(
    graph: dict[str, Any], node_id: str, scope: dict[str, Any],
    task_records: Mapping[str, dict] | Sequence[dict],
    required_scopes: Mapping[str, Sequence[dict]],
    scope_links: Mapping[str, Sequence[dict]] | None = None,
) -> list[str]:
    """Select each current predecessor instance, including verified skip states.

    ``required_scopes`` must be derived from the frozen project inputs. For
    differing non-project scopes, ``scope_links`` names the exact instances
    consumed by this task; the adapter never infers creative relationships.
    """
    node = stage_by_id(graph, node_id)
    current = _scope(scope, node["scope"])
    if current not in _catalogue(graph, required_scopes, node_id):
        raise ValueError(f"{node_id} scope is absent from the frozen required set")
    scope_links = scope_links or {}
    if set(scope_links) - set(node["depends_on"]):
        raise ValueError("Scope links name a node outside graph dependencies")
    rows = _rows(task_records)
    result: list[str] = []
    for dep_id in node["depends_on"]:
        for required in _required_for_edge(graph, node, current, dep_id, required_scopes, scope_links):
            matches = [row for row in rows if row["envelope"].get("node_id") == dep_id
                       and _scope(row["envelope"].get("scope"), stage_by_id(graph, dep_id)["scope"]) == required]
            if not matches:
                raise ValueError(f"Missing predecessor task: {dep_id} {required}")
            latest_key = max((row["envelope"]["input_revision"], row["envelope"]["batch"]) for row in matches)
            latest = [row for row in matches if (row["envelope"]["input_revision"], row["envelope"]["batch"]) == latest_key]
            if len(latest) != 1:
                raise ValueError(f"Ambiguous current predecessor: {dep_id} {required}")
            row = latest[0]
            if row["state"] not in ("ACCEPTED", "NOT_APPLICABLE"):
                raise ValueError(f"Predecessor is not complete: {dep_id} {required}")
            task_id = row["envelope"]["task_id"]
            if task_id in result:
                raise ValueError(f"Duplicate predecessor task ID: {task_id}")
            result.append(task_id)
    return result


def graph_envelope_fields(
    graph: dict[str, Any], node_id: str, scope: dict[str, Any], task_id: str,
    batch: int, task_records: Mapping[str, dict] | Sequence[dict],
    required_scopes: Mapping[str, Sequence[dict]],
    scope_links: Mapping[str, Sequence[dict]] | None = None,
    handoff_bindings: Sequence[dict] = (),
) -> dict[str, Any]:
    """Build the graph-governed fields of a strict V6 task envelope."""
    node = stage_by_id(graph, node_id)
    _scope(scope, node["scope"])
    if not isinstance(task_id, str) or not task_id or type(batch) is not int or batch < 1:
        raise ValueError("Task ID and positive batch are required")
    predecessors = predecessor_task_ids(graph, node_id, scope, task_records,
                                        required_scopes, scope_links)
    classes = {"specialist": "professional", "reviewer": "review", "kernel": "system"}
    if node["executor_kind"] == "host":
        execution_class = ("external_image" if node_id in {"visual_media", "board_media"} else
                           "external_video" if node_id == "video_execution" else "local_media")
    else:
        execution_class = classes[node["executor_kind"]]
    expected_artifacts = [
        {"slot": slot_for(node_id, scope, kind), "kind": kind,
         "uri_prefix": f"runtime/v6/candidates/{task_id}/{batch}/"}
        for kind in node["output_types"]
    ]
    slots = {item["slot"] for item in expected_artifacts}
    rows = {row["envelope"]["task_id"]: row for row in _rows(task_records)}
    source_slots = {item["slot"]: rows[task_id]["version"] for task_id in predecessors
                    if rows[task_id]["state"] == "ACCEPTED"
                    for item in rows[task_id]["envelope"]["expected_artifacts"]}
    bindings = list(handoff_bindings)
    if node["handoff_required"] and not bindings:
        raise ValueError(f"{node_id} requires concrete predecessor-to-output handoffs")
    if len({item.get("requirement_id") for item in bindings}) != len(bindings):
        raise ValueError("Duplicate handoff requirement ID")
    covered = set()
    for item in bindings:
        if not isinstance(item, dict) or set(item) != {"requirement_id", "source_slot", "source_version",
                                                   "target_slot", "target_pointer", "channel"}:
            raise ValueError("Handoff binding differs from the V6 protocol")
        if item["source_slot"] not in source_slots or item["source_version"] != source_slots[item["source_slot"]]:
            raise ValueError("Handoff source slot/version is not an accepted predecessor output")
        if item["target_slot"] not in slots or not isinstance(item["target_pointer"], str) or (
                item["target_pointer"] and not item["target_pointer"].startswith("/")):
            raise ValueError("Handoff target must be a declared output and JSON pointer")
        if item["channel"] not in {"artifact", "message", "host"}:
            raise ValueError("Handoff channel is not supported")
        covered.add(item["source_slot"])
    if node["handoff_required"] and covered != set(source_slots):
        raise ValueError(f"{node_id} handoffs do not cover every accepted predecessor output")
    return {
        "role": node["role"], "execution_class": execution_class,
        "scope": {"kind": scope["kind"], "ids": list(scope["ids"])},
        "expected_artifacts": expected_artifacts,
        "validators": [{"id": checker, "kind": CHECKER_KINDS[checker]} for checker in node["checkers"]],
        "dependencies": [{"task_id": predecessor} for predecessor in predecessors],
        "handoffs": bindings,
    }
