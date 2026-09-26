"""Independent static review of the frozen rain-night scene prompt candidate."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ai_comic_drama_workflow.v6_protocol import candidate_digest, validate_v6_protocol


ROOT = Path("/private/tmp/ai-video-v6-full-demo/project")
TASK_ID = "TASK_77a39e38115fc23984108917"
PREFIX = f"runtime/v6/reviews/{TASK_ID}/1/"
REVIEW = ROOT / PREFIX


def read(uri: str) -> dict:
    return json.loads((ROOT / uri).read_text(encoding="utf-8"))


def sha(uri: str) -> str:
    return hashlib.sha256((ROOT / uri).read_bytes()).hexdigest()


def save(name: str, value: dict) -> None:
    (REVIEW / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


row = read("runtime/v6/state.json")["tasks"][TASK_ID]
envelope = row["envelope"]
candidate_uri = f"runtime/v6/candidates/{TASK_ID}/1/candidate-result.json"
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
assert row["review_dispatch"]["agent_id"] != candidate["agent_id"]
assert row["review_dispatch"]["agent_id"].endswith("/v6_0b1cc97fa601a675d86e59c8")
assert candidate["task_id"] == role["task_id"] == visual["task_id"] == TASK_ID
assert candidate["batch"] == envelope["batch"] == 1
assert candidate["input_digest"] == envelope["input_digest"]
assert candidate["artifacts"][0]["kind"] == "VisualImagePrompt"
assert candidate["artifacts"][0]["slot"] == envelope["expected_artifacts"][0]["slot"]
assert visual_uri.startswith(envelope["expected_artifacts"][0]["uri_prefix"])
assert sha(visual_uri) == candidate["artifacts"][0]["sha256"]
assert sha(candidate["result_uri"]) == candidate["result_sha256"]
assert role["artifact"] == str(ROOT / visual_uri)
assert role["artifact_sha256"] == sha(visual_uri)
assert role["context_fingerprint"] == frozen_task["context_fingerprint"]
assert role["complete"] is True and not role["conflicts"] and not role["unresolved"]
assert candidate["unresolved"] == []
assert {item["id"]: item["status"] for item in candidate["checks"]} == {
    item["id"]: "PASS" for item in envelope["validators"]
}

for item in envelope["inputs"] + envelope["resources"]:
    assert sha(item["uri"]) == item["sha256"], item["uri"]
for uri, digest in row["evidence_hashes"].items():
    assert sha(uri) == digest, uri
resources = {item["uri"]: item["sha256"] for item in envelope["resources"]}
receipt = role["module_receipt"]
assert candidate["module_receipts"] == [envelope["module"]]
assert (receipt["name"], receipt["version"]) == (
    envelope["module"]["name"], envelope["module"]["version"]
)
assert receipt["skill_sha256"] == next(
    digest for uri, digest in resources.items() if uri.endswith("/SKILL.md")
)
assert {str(Path(item["path"]).relative_to(ROOT)): item["sha256"] for item in receipt["reads"]} == resources
save("module-receipt.review.json", {
    "status": "PASS",
    "candidate_result_sha256": sha(candidate_uri),
    "role_result_sha256": sha(candidate["result_uri"]),
    "visual_artifact_sha256": sha(visual_uri),
    "frozen_input_sha256": {item["uri"]: sha(item["uri"]) for item in envelope["inputs"]},
    "resource_sha256": resources,
    "candidate_evidence_sha256": row["evidence_hashes"],
    "module": envelope["module"],
})

asset, reference = art["assets"][4], art["references"][4]
assert asset["id"] == visual["asset_id"] == "ENV_RAIN_NIGHT"
assert visual["scope_key"] == envelope["scope"]["ids"][0]
assert visual["art_source"] == {"uri": art_uri, "sha256": sha(art_uri), "pointer": "/assets/4"}
assert reference["id"] == visual["reference_plan"]["id"] == "PLAN_ENV_RAIN_NIGHT"
assert reference["status"] == visual["reference_plan"]["status"] == "planned"
assert reference["file"] is reference["sha256"] is None
assert visual["reference_plan"]["file"] is visual["reference_plan"]["sha256"] is None
assert visual["params"]["reference_files"] == contract["icir"]["references"] == []
assert visual["params"]["target_model"] is None
assert visual["params"]["requested_pixels"] is None
assert contract["compilations"][0]["native_params"] == {}
assert contract["compilations"][0]["capability"]["status"] == "unknown"
assert visual["production_contract_sha256"] == sha(contract_uri)
assert contract["sources"][0]["sha256"] == sha("sources/SRC_69a71adcfaca/source.txt")
assert contract["sources"][1]["sha256"] == sha(art_uri)
assert contract["sources"][2]["sha256"] == sha(task_uri)
prompt = visual["prompt"]
assert contract["compilations"][0]["prompt"] == role["prompt"] == prompt
assert prompt in (ROOT / visual["prompt_document"]).read_text(encoding="utf-8")
assert all(clause in prompt for clause in contract["compilations"][0]["constraint_clauses"].values())
assert {item["id"] for item in contract["constraints"]} == {"H1", "H2", "H3", "H4", "H5"}
assert {item["status"] for item in contract["acceptance"] if item["stage"] == "static"} == {"PASS"}
assert {item["status"] for item in contract["acceptance"] if item["stage"] == "visual"} == {"NOT_RUN"}
assert visual["media_status"] == visual["visual_review_status"] == "NOT_RUN"
assert native["status"] == "STATIC_VALID" and native["errors"] == []
required_phrases = [
    "SCENE_HANDOFF 三镜共享同一雨夜", "同一蓝灰色材与稳定环境光方向",
    "背景雨幕细而低频", "不遮蔽将来交接双手、完整封口与包口",
    "中性平整、稳定可站立、低反光的承托面", "物理连贯的微弱湿润反射",
    "单一平视视点", "两人相向站立和右手交信的通行净空",
    "乙右手触及包口的空间", "本图不画人物、信封或背包",
    "同一方位的画外柔和环境漫反射", "不添加可见灯具",
    "不标定具体地点、城市、建筑、年代或室内外状态",
]
assert all(phrase in prompt for phrase in required_phrases)
assert asset["identity_locks"] == frozen_task["job"]["brief"]["locks"]
assert art["set"]["practical_lights"] == []
save("image-prompt-contract.review.json", {
    "status": "PASS",
    "native_validator": native,
    "production_contract_sha256": sha(contract_uri),
    "prompt_document_sha256": sha(visual["prompt_document"]),
    "verified_semantic_phrases": required_phrases,
    "reference_binding": "PLAN_ENV_RAIN_NIGHT planned; no file, hash or attachment slot",
    "media_status": "NOT_RUN",
    "visual_review_status": "NOT_RUN",
    "scope": "Independent static review of prompt and ArtIR; no image or video inspected",
})

assert len(candidate["handoffs"]) == 1
handoff = envelope["handoffs"][0]
assert {key: candidate["handoffs"][0][key] for key in handoff} == handoff
assert handoff["target_slot"] == candidate["artifacts"][0]["slot"]
assert all(lock in frozen_task["job"]["brief"]["locks"] for lock in asset["identity_locks"])
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
    "finding": "Rain-night continuity and location ambiguity preserved as prompt constraints; actual visual continuity remains untested.",
})

record = {
    "schema": "review-record/6.0",
    "task_id": TASK_ID,
    "batch": 1,
    "reviewer_agent_id": row["review_dispatch"]["agent_id"],
    "reviewer_dispatch_id": row["review_dispatch"]["dispatch_id"],
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
