"""Independent audit of the frozen Director batch-2 candidate."""

import datetime
import hashlib
import json
import zipfile
from pathlib import Path

from ai_comic_drama_workflow.v6_protocol import candidate_digest


ROOT = Path("/private/tmp/ai-video-v6-full-demo/project")
TASK = "TASK_bf0865334b4a88be570a164a"
BASE = ROOT / "runtime/v6/candidates" / TASK / "2"
REVIEW = ROOT / "runtime/v6/reviews" / TASK / "2"
PREFIX = f"runtime/v6/reviews/{TASK}/2/"
MODULE = "1a3d2e6d95e35195499b2c81ea8f04f979d537bc0fb0522d698c4dc96870d9c1"


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    path = REVIEW / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return PREFIX + name


def pointer(value, path):
    for part in path.split("/")[1:]:
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


candidate = read(BASE / "candidate-result.json")
result = read(BASE / "role-result.json")
director = read(BASE / "director-ir.json")
mapping = read(BASE / "screenplay-map.json")
frozen = read(ROOT / "runtime/tasks" / f"{TASK}.json")
canon = read(ROOT / "runtime/v6/candidates/TASK_44ed8445ba9b638fcd7e9fe8/2/canon.json")
script = read(ROOT / "runtime/v6/candidates/TASK_206f1e43fe2d38c84f3fcb2c/1/script-ir.json")

frozen_inputs = [
    ("canon", "runtime/v6/candidates/TASK_44ed8445ba9b638fcd7e9fe8/2/canon.json", "0cc4aebffda6a714d5c58695c11f7d70b96359d930125b04edb8fe14abfc4ef9"),
    ("screenplay", "runtime/v6/candidates/TASK_206f1e43fe2d38c84f3fcb2c/1/script-ir.json", "8e51d23ea14ac97ebdbba754d2be77e8694dbc9bb1a3a89d3b9cb1ca5d3d6c93"),
    ("frozen_task", f"runtime/tasks/{TASK}.json", "a435e4354848649326798f614c5af4748f081481623597804228cde9892970ec"),
]
inputs = [
    {"slot": slot, "uri": uri, "expected_sha256": expected, "actual_sha256": digest(ROOT / uri)}
    for slot, uri, expected in frozen_inputs
]
resources = [
    {"uri": uri, "expected_sha256": expected, "actual_sha256": digest(ROOT / uri)}
    for uri, expected in [
        (f"runtime/modules/{MODULE}/director-grammar/SKILL.md", "ca22158b6ca4c0e654e1df66f25cc02bdfa689869df124bb9ae0b201f1ad2f6f"),
        (f"runtime/modules/{MODULE}/director-grammar/references/current-contract.md", "28e679dff03715b08fd5ca1b066eb952b91eaaf74bc44c055118c4b4570a5d1d"),
        (f"runtime/modules/{MODULE}/director-grammar/references/cooperation-v5.md", "28fb0672d9920bb60bb2800da33cc9ac1d9cd6884d30ceb993fa51672b65bb28"),
        (f"runtime/modules/{MODULE}/director-grammar/references/screenplay-handoff.md", "bc7faaecb662bfed362cbe94697c1d7cfffa813f3f58b79c156c29d1b9344504"),
    ]
]
receipt = result["module_receipt"]
module_pass = (
    all(item["expected_sha256"] == item["actual_sha256"] for item in inputs + resources)
    and candidate["module_receipts"] == [{"name": "director-grammar", "sha256": MODULE, "version": "1.4.4"}]
    and candidate["input_digest"] == "85b2bcd4414232835001b6218d902ef7db0f4872571ef5c617e2e41e417bb6ac"
    and candidate["batch"] == 2
    and receipt["name"] == "director-grammar"
    and receipt["version"] == "1.4.4"
    and receipt["skill_sha256"] == resources[0]["actual_sha256"]
    and len(receipt["reads"]) == 4
    and all(digest(Path(item["path"])) == item["sha256"] for item in receipt["reads"])
    and digest(BASE / "director-ir.json") == candidate["artifacts"][0]["sha256"] == result["artifact_sha256"]
    and digest(BASE / "role-result.json") == candidate["result_sha256"]
)
module_uri = write("module-receipt.review.json", {
    "status": "PASS" if module_pass else "FAIL",
    "method": "Independently checked SHA-256 of frozen inputs, locked resources, artifact, RoleResult and module receipts.",
    "inputs": inputs,
    "resources": resources,
    "candidate_file_sha256": digest(BASE / "candidate-result.json"),
    "candidate_digest": candidate_digest(candidate),
    "director_sha256": digest(BASE / "director-ir.json"),
    "role_result_sha256": digest(BASE / "role-result.json"),
})

raw = read(REVIEW / "native-validator.raw.json")
native_report = json.loads(raw["stdout"])
stow = []
for sample in director["timeline"]["state_samples"]:
    if sample["shot_id"] == "S_STOW" and sample["at_ms"] in (6000, 8500, 9000):
        letter = sample["entities"]["PROP_LETTER"]
        stow.append({
            "at_ms": sample["at_ms"],
            "sample_id": sample["id"],
            "letter_contacts": letter["contacts"],
            "letter_supports": letter["supports"],
            "letter_controllers": letter["controllers"],
            "bag_condition": sample["entities"]["PROP_BACKPACK"]["condition"],
        })
camera = director["timeline"]["camera_operations"][2]
settled = next(item for item in director["timeline"]["composition_tracks"] if item["id"] == "COMP_S_STOW_SETTLED")
subjects = [item["node_id"] for item in settled["subjects"]]
prior = read(ROOT / "runtime/v6/reviews" / TASK / "1/review-record.json")
repair = read(BASE / "evidence/repair-b1.json")
terminal = [item for item in stow if item["at_ms"] >= 8500]
repaired = (
    camera["end_ms"] == 9000
    and camera["start_framing"] == camera["end_framing"]
    and "入包前可见" in camera["end_framing"]
    and "入包后完全遮挡不外露" in camera["end_framing"]
    and settled["start_ms"] == 8500 and settled["end_ms"] == 9000
    and "N_PROP_LETTER" not in subjects
    and len(terminal) == 2
    and all(item["letter_contacts"] == ["PROP_BACKPACK.interior"]
            and item["letter_supports"] == ["PROP_BACKPACK.interior"]
            and item["letter_controllers"] == [] for item in terminal)
    and "信已完全在包内" in director["shots"][2]["camera"]["framing_end"]
    and repair["previous_record_sha256"] == digest(ROOT / "runtime/v6/reviews" / TASK / "1/review-record.json")
    and prior["checks"][1]["status"] == "FAIL"
)
assert raw["exit_code"] == 0 and native_report["status"] == result["validator"]["status"] == "STATIC_VALID"
assert native_report["screenplay_binding"]["status"] == "REVIEW_ATTESTED"
assert repaired
native_uri = write("native-validator.review.json", {
    "status": "PASS",
    "method": "Independently reran the frozen validator and compared timed camera, composition and state fields at the stow ending.",
    "native_command": raw["command_argv"],
    "native_exit_code": raw["exit_code"],
    "native_report": native_report,
    "event_order": [item["semantic_id"] for item in director["timeline"]["actions"]],
    "stow_samples": stow,
    "terminal_composition_interval_ms": [settled["start_ms"], settled["end_ms"]],
    "terminal_composition_subjects": subjects,
    "shot_camera_framing_end": director["shots"][2]["camera"]["framing_end"],
    "timeline_camera_end_ms": camera["end_ms"],
    "timeline_camera_end_framing": camera["end_framing"],
    "finding": "The batch-1 9000 ms camera/composition contradiction is repaired. The camera framing now says the letter is visible before insertion and fully occluded after insertion; the settled composition excludes the letter and explicit 8500/9000 ms state samples place it inside the backpack.",
    "previous_review_record_sha256": digest(ROOT / "runtime/v6/reviews" / TASK / "1/review-record.json"),
    "previous_defect_gone": repaired,
    "media": "NOT_RUN",
})

required = {item["id"]: item["source_fingerprint"] for item in frozen["handoff"]["required_handoffs"]}
rows = mapping["mappings"]
fingerprints_pass = (
    len(required) == len(rows) == 6
    and all(row["requirement_id"] in required and row["source_fingerprint"] == required[row["requirement_id"]] for row in rows)
)
target_checks = []
for row in rows:
    for check in row["target_checks"]:
        actual = pointer(director, check["path"])
        passed = actual == check["value"] if check["op"] == "equals" else check["value"] in actual
        target_checks.append({"requirement_id": row["requirement_id"], "path": check["path"], "op": check["op"], "pass": passed})
clauses = {item["id"] for item in director["contract"]["clauses"]}
clause_pass = all(row["target_clause"] in clauses for row in rows)
canon_evidence = read(BASE / "evidence/handoff-canon.json")
script_evidence = read(BASE / "evidence/handoff-screenplay.json")
source_binding_pass = (
    canon_evidence["source_sha256"] == digest(ROOT / canon_evidence["source_uri"])
    and script_evidence["source_sha256"] == digest(ROOT / script_evidence["source_uri"])
    and canon_evidence["target_sha256"] == script_evidence["target_sha256"] == digest(BASE / "director-ir.json")
)
archive = Path("/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow/assets/bundled-skills/production-design-grammar.skill")
art_sha = digest(archive)
with zipfile.ZipFile(archive) as z:
    art_member = next(name for name in z.namelist() if name.endswith("scripts/art_compile.py"))
    art_compiler = z.read(art_member).decode()
art_lock = read(ROOT / "modules.lock.json")["modules"]["production-design-grammar"]
art_pointer_pass = (
    director["schema_version"] == "1.2"
    and art_sha == art_lock["sha256"] == "6e83e075da45785541fce62f9fcc6ebc8666f48466c382af5980f292613fb5f9"
    and art_lock["version"] == "1.3.3"
    and "timeline/actions/" in art_compiler
    and all(action["shot_ids"] and action["changes"] for action in director["timeline"]["actions"])
)
handoff_pass = (
    fingerprints_pass and clause_pass and source_binding_pass and art_pointer_pass
    and all(item["pass"] for item in target_checks)
    and [item["semantic_id"] for item in director["timeline"]["actions"]] == script["narrative"]["reveal_order"]
    and [item["id"] for item in canon["event_order"]] == script["narrative"]["reveal_order"]
)
handoff_uri = write("handoff.review.json", {
    "status": "PASS" if handoff_pass else "FAIL",
    "method": "Compared frozen Canon and ScriptIR to six native screenplay mappings, resolved target checks and source fingerprints, and checked DirectorIR 1.2 action pointers for Art handoff.",
    "canon_requirement_ids": [item["id"] for item in canon["source_requirements"]],
    "screenplay_requirement_ids": list(required),
    "source_fingerprints_match": fingerprints_pass,
    "target_checks": target_checks,
    "target_clauses_exist": clause_pass,
    "source_artifact_bindings_match": source_binding_pass,
    "event_order": [item["semantic_id"] for item in director["timeline"]["actions"]],
    "art_compiler_sha256": art_sha,
    "art_compiler_member": art_member,
    "art_compiler_action_branch_present": "timeline/actions/" in art_compiler,
    "art_action_pointers": [f"/timeline/actions/{index}" for index in range(len(director["timeline"]["actions"]))],
    "art_pointer_compatibility": art_pointer_pass,
    "limitation": "Art event pointers are available; a separate ArtIR creator must author matching events and run its native validator.",
})

record = {
    "schema": "review-record/6.0",
    "task_id": TASK,
    "batch": 2,
    "reviewer_agent_id": "/root/host_bridge/full_rehearsal/v6_9c8946265ae15cff1637e477",
    "reviewer_dispatch_id": "review-042e3afd47ec05dfe055ac2b",
    "candidate_digest": candidate_digest(candidate),
    "checks": [
        {"id": "module_receipt", "status": "PASS" if module_pass else "FAIL", "evidence": [module_uri]},
        {"id": "native_validator", "status": "PASS", "evidence": [native_uri, PREFIX + "native-validator.raw.json"]},
        {"id": "handoff", "status": "PASS" if handoff_pass else "FAIL", "evidence": [handoff_uri]},
    ],
    "failure_owner": None,
    "at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
}
write("review-record.json", record)
print(json.dumps({"review_record": str(REVIEW / "review-record.json"), "review_sha256": digest(REVIEW / "review-record.json"), "candidate_digest": candidate_digest(candidate), "checks": [(item["id"], item["status"]) for item in record["checks"]], "previous_defect_gone": repaired}, ensure_ascii=False, indent=2))
