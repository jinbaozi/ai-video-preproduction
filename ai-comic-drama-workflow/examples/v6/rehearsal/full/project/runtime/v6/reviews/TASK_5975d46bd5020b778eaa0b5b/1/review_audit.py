"""Independent static review of the frozen PROP_BACKPACK visual prompt."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ai_comic_drama_workflow.v6_protocol import candidate_digest, validate_v6_protocol


ROOT = Path("/private/tmp/ai-video-v6-full-demo/project")
TASK = "TASK_5975d46bd5020b778eaa0b5b"
PREFIX = f"runtime/v6/reviews/{TASK}/1/"
REVIEW = ROOT / PREFIX


def read(uri: str) -> dict:
    return json.loads((ROOT / uri).read_text(encoding="utf-8"))


def sha(uri: str) -> str:
    return hashlib.sha256((ROOT / uri).read_bytes()).hexdigest()


def save(name: str, payload: dict) -> None:
    (REVIEW / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


row = read("runtime/v6/state.json")["tasks"][TASK]
envelope = row["envelope"]
dispatch = row["review_dispatch"]
candidate_uri = f"runtime/v6/candidates/{TASK}/1/candidate-result.json"
candidate = read(candidate_uri)
role = read(candidate["result_uri"])
art_uri, task_uri = [item["uri"] for item in envelope["inputs"]]
art, frozen_task = read(art_uri), read(task_uri)
visual_uri = candidate["artifacts"][0]["uri"]
visual = read(visual_uri)
contract_uri = visual["production_contract"]
contract = read(contract_uri)
native = read(PREFIX + "native-contract-validation.raw.json")

assert row["state"] == "REVIEW_REQUIRED"
assert dispatch["agent_id"] == "/root/host_bridge/full_rehearsal/v6_4d56a993103fabdf7afa6223"
assert dispatch["agent_id"] != candidate["agent_id"]
assert candidate["task_id"] == role["task_id"] == visual["task_id"] == TASK
assert candidate["batch"] == envelope["batch"] == 1
assert candidate["input_digest"] == envelope["input_digest"]
assert [item["id"] for item in candidate["checks"]] == [item["id"] for item in envelope["validators"]]
assert candidate["artifacts"][0]["kind"] == envelope["expected_artifacts"][0]["kind"]
assert candidate["artifacts"][0]["slot"] == envelope["expected_artifacts"][0]["slot"]
assert visual_uri.startswith(envelope["expected_artifacts"][0]["uri_prefix"])
assert sha(visual_uri) == candidate["artifacts"][0]["sha256"] == role["artifact_sha256"]
assert sha(candidate["result_uri"]) == candidate["result_sha256"]
assert role["artifact"] == str(ROOT / visual_uri)
assert role["context_fingerprint"] == frozen_task["context_fingerprint"]
assert role["complete"] is True and not role["conflicts"] and not role["unresolved"]

for item in envelope["inputs"] + envelope["resources"]:
    assert sha(item["uri"]) == item["sha256"]
resources = {item["uri"]: item["sha256"] for item in envelope["resources"]}
receipt = role["module_receipt"]
assert candidate["module_receipts"] == [envelope["module"]]
assert (receipt["name"], receipt["version"]) == (
    envelope["module"]["name"], envelope["module"]["version"]
)
assert receipt["skill_sha256"] == next(
    digest for uri, digest in resources.items() if uri.endswith("/SKILL.md")
)
reads = {str(Path(item["path"]).relative_to(ROOT)): item["sha256"] for item in receipt["reads"]}
assert all(reads[uri] == digest for uri, digest in resources.items())
assert all(hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"] for item in receipt["reads"])
save("module-receipt.review.json", {
    "status": "PASS",
    "candidate_result_sha256": sha(candidate_uri),
    "role_result_sha256": sha(candidate["result_uri"]),
    "visual_artifact_sha256": sha(visual_uri),
    "frozen_input_sha256": {item["uri"]: sha(item["uri"]) for item in envelope["inputs"]},
    "resource_sha256": resources,
    "module": envelope["module"],
    "note": "Hash and receipt match; semantics reviewed separately.",
})

asset, reference = art["assets"][3], art["references"][3]
assert asset["id"] == visual["asset_id"] == "PROP_BACKPACK"
assert visual["scope_key"] == envelope["scope"]["ids"][0]
assert visual["art_source"] == {"uri": art_uri, "sha256": sha(art_uri), "pointer": "/assets/3"}
assert asset["identity_locks"] == frozen_task["job"]["brief"]["locks"]
assert reference["id"] == visual["reference_plan"]["id"] == "PLAN_PROP_BACKPACK"
assert reference["status"] == visual["reference_plan"]["status"] == "planned"
assert reference["file"] is reference["sha256"] is None
assert visual["reference_plan"]["file"] is visual["reference_plan"]["sha256"] is None
assert visual["params"]["reference_files"] == contract["icir"]["references"] == []
assert visual["params"]["target_model"] is None
assert visual["params"]["requested_pixels"] is None
assert contract["compilations"][0]["native_params"] == {}
assert contract["compilations"][0]["capability"]["status"] == "unknown"
assert contract["sources"][0]["sha256"] == sha(art_uri)
assert contract["sources"][1]["sha256"] == sha(task_uri)
assert visual["production_contract_sha256"] == sha(contract_uri)
prompt = visual["prompt"]
assert contract["compilations"][0]["prompt"] == role["prompt"] == prompt
assert prompt in (ROOT / visual["prompt_document"]).read_text(encoding="utf-8")
assert all(clause in prompt for clause in contract["compilations"][0]["constraint_clauses"].values())
assert {item["id"] for item in contract["constraints"]} == {"H1", "H2", "H3", "H4", "H5", "H6"}
assert {item["status"] for item in contract["acceptance"] if item["stage"] == "static"} == {"PASS"}
assert {item["status"] for item in contract["acceptance"] if item["stage"] == "visual"} == {"NOT_RUN"}
assert {item["status"] for item in contract["execution"] if item["id"] in {"S2", "S3"}} == {"NOT_RUN"}
assert visual["media_status"] == visual["visual_review_status"] == "NOT_RUN"
assert native["status"] == "STATIC_VALID" and native["errors"] == []
required_phrases = [
    "同一只乙收信所用背包", "深色无标识软质织物", "低反光哑面",
    "包体形状和包口位置清楚", "中性平整承托面", "乙右手能够触及",
    "可容纳一封普通纸质信的内腔", "尚待收纳信件", "不出现人物、手或信",
    "不拼接入包前后两个时刻", "后续 EVENT_STOW", "同一背包外观与同一包口位置",
    "信由包内承托且完全不外露", "终帧不留信纸在包口", "低饱和蓝灰雨夜",
    "不表现可识别城市、建筑或具体室内外", "不增加品牌、贴章、可读文字、明显破损",
]
assert all(phrase in prompt for phrase in required_phrases)
assert "具体背法与品牌不定义" in asset["design"]
assert visual["params"]["surface"] == "generic"
save("image-prompt-contract.review.json", {
    "status": "PASS",
    "native_validator": native,
    "production_contract_sha256": sha(contract_uri),
    "prompt_document_sha256": sha(visual["prompt_document"]),
    "verified_semantic_phrases": required_phrases,
    "reference_binding": "PLAN_PROP_BACKPACK planned; no file, hash, or attachment slot",
    "temporal_reading": "The single still is pre-stow; enclosed letter and no exposure apply to later EVENT_STOW.",
    "media_status": "NOT_RUN",
    "visual_review_status": "NOT_RUN",
    "scope": "Independent static review; no actual image or video inspected",
})

assert len(candidate["handoffs"]) == len(envelope["handoffs"]) == 1
handoff = envelope["handoffs"][0]
assert {key: candidate["handoffs"][0][key] for key in handoff} == handoff
assert handoff["target_slot"] == candidate["artifacts"][0]["slot"]
save("handoff.review.json", {
    "status": "PASS",
    "requirement_id": handoff["requirement_id"],
    "source_slot": handoff["source_slot"],
    "source_version": handoff["source_version"],
    "source_art_sha256": sha(art_uri),
    "source_asset_id": asset["id"],
    "identity_locks": asset["identity_locks"],
    "target_slot": handoff["target_slot"],
    "target_artifact_sha256": sha(visual_uri),
    "finding": "Same backpack, usable opening, and later hidden-letter condition retained in static prompt.",
})

record = {
    "schema": "review-record/6.0",
    "task_id": TASK,
    "batch": 1,
    "reviewer_agent_id": dispatch["agent_id"],
    "reviewer_dispatch_id": dispatch["dispatch_id"],
    "candidate_digest": candidate_digest(candidate),
    "checks": [
        {"id": "module_receipt", "status": "PASS", "evidence": [PREFIX + "module-receipt.review.json"]},
        {"id": "image_prompt_contract", "status": "PASS", "evidence": [PREFIX + "image-prompt-contract.review.json", PREFIX + "native-contract-validation.raw.json"]},
        {"id": "handoff", "status": "PASS", "evidence": [PREFIX + "handoff.review.json"]},
    ],
    "failure_owner": None,
    "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}
assert [item["id"] for item in record["checks"]] == [item["id"] for item in envelope["validators"]]
validate_v6_protocol("review-record", record)
save("review-record.json", record)
print(json.dumps({
    "review_record": PREFIX + "review-record.json",
    "sha256": sha(PREFIX + "review-record.json"),
    "candidate_digest": record["candidate_digest"],
    "checks": [item["id"] + ":" + item["status"] for item in record["checks"]],
}, ensure_ascii=False))
