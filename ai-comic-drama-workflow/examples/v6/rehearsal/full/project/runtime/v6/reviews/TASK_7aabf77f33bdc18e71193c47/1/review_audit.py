"""Independent, read-only audit of CHAR_JIA visual prompt candidate."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ai_comic_drama_workflow.v6_protocol import candidate_digest, validate_v6_protocol


ROOT = Path("/private/tmp/ai-video-v6-full-demo/project")
TASK_ID = "TASK_7aabf77f33bdc18e71193c47"
REVIEW = ROOT / "runtime/v6/reviews" / TASK_ID / "1"
CANDIDATE = ROOT / "runtime/v6/candidates" / TASK_ID / "1"
PREFIX = f"runtime/v6/reviews/{TASK_ID}/1/"


def read(uri: str) -> dict:
    return json.loads((ROOT / uri).read_text(encoding="utf-8"))


def digest(uri: str) -> str:
    return hashlib.sha256((ROOT / uri).read_bytes()).hexdigest()


def save(name: str, value: dict) -> None:
    (REVIEW / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


state = read("runtime/v6/state.json")
row = state["tasks"][TASK_ID]
envelope = row["envelope"]
candidate = read(f"runtime/v6/candidates/{TASK_ID}/1/candidate-result.json")
result = read(candidate["result_uri"])
art_uri = envelope["inputs"][0]["uri"]
art = read(art_uri)
task_uri = envelope["inputs"][1]["uri"]
task = read(task_uri)
visual_uri = candidate["artifacts"][0]["uri"]
visual = read(visual_uri)
contract_uri = visual["production_contract"]
contract = read(contract_uri)
native = json.loads((REVIEW / "native-contract-validation.review.json").read_text())

module_receipt = result["module_receipt"]
resource_expected = {resource["uri"]: resource["sha256"] for resource in envelope["resources"]}
resource_observed = {}
for resource in envelope["resources"]:
    resource_observed[resource["uri"]] = digest(resource["uri"])
assert resource_expected == resource_observed
assert module_receipt["name"] == envelope["module"]["name"]
assert module_receipt["version"] == envelope["module"]["version"]
assert candidate["module_receipts"] == [envelope["module"]]
assert {str(Path(item["path"]).relative_to(ROOT)): item["sha256"] for item in module_receipt["reads"]} == resource_expected
assert module_receipt["skill_sha256"] == resource_expected[next(uri for uri in resource_expected if uri.endswith("/SKILL.md"))]
assert candidate["input_digest"] == envelope["input_digest"]
assert all(digest(item["uri"]) == item["sha256"] for item in envelope["inputs"])
assert digest(candidate["result_uri"]) == candidate["result_sha256"]
assert digest(visual_uri) == candidate["artifacts"][0]["sha256"]
assert result["artifact"] == str(ROOT / visual_uri)
assert result["artifact_sha256"] == digest(visual_uri)
assert result["task_id"] == TASK_ID
assert result["context_fingerprint"] == task["context_fingerprint"]
assert result["complete"] is True and not result["conflicts"] and not result["unresolved"]
save("module-receipt.review.json", {
    "status": "PASS",
    "candidate_result_sha256": digest(f"runtime/v6/candidates/{TASK_ID}/1/candidate-result.json"),
    "role_result_sha256": digest(candidate["result_uri"]),
    "visual_artifact_sha256": digest(visual_uri),
    "frozen_input_sha256": {item["uri"]: digest(item["uri"]) for item in envelope["inputs"]},
    "resource_sha256": resource_observed,
    "module": envelope["module"],
})

prompt = visual["prompt"]
assert visual["asset_id"] == "CHAR_JIA"
assert visual["scope_key"] == "ASSET_SCENE_HANDOFF_CHAR_JIA"
assert visual["art_source"] == {
    "uri": art_uri, "sha256": digest(art_uri), "pointer": "/assets/0"
}
assert visual["reference_plan"]["id"] == art["references"][0]["id"] == "PLAN_CHAR_JIA"
assert art["references"][0]["status"] == visual["reference_plan"]["status"] == "planned"
assert art["references"][0]["file"] is None and art["references"][0]["sha256"] is None
assert visual["reference_plan"]["file"] is None and visual["reference_plan"]["sha256"] is None
assert visual["params"]["reference_files"] == contract["icir"]["references"] == []
assert contract["sources"][0]["sha256"] == digest(art_uri)
assert contract["sources"][1]["sha256"] == digest(task_uri)
assert contract["compilations"][0]["prompt"] == prompt
assert visual["production_contract_sha256"] == digest(contract_uri)
assert contract["compilations"][0]["native_params"] == {}
assert contract["compilations"][0]["capability"]["status"] == "unknown"
assert native["status"] == "STATIC_VALID" and native["errors"] == []
assert visual["media_status"] == visual["visual_review_status"] == "NOT_RUN"
assert {row["status"] for row in contract["acceptance"] if row["stage"] == "visual"} == {"NOT_RUN"}
assert {row["status"] for row in contract["acceptance"] if row["stage"] == "static"} == {"PASS"}
assert len(contract["constraints"]) == 6
for clause in contract["compilations"][0]["constraint_clauses"].values():
    assert clause in prompt
semantic_tokens = [
    "同一位甲", "同一套服装", "深石墨灰", "无标识", "袖口收紧", "右手",
    "未拆信", "闭合封口完整可见", "无可读文字", "雨夜", "面部留在画外",
    "只呈现乙接稳前的一个瞬间", "不展示验封、拆信或放入背包",
    "不表明具体地点或室内外",
]
assert all(token in prompt for token in semantic_tokens)
assert "信封主体和封口、甲的指节与袖口互不遮挡" in prompt
save("image-prompt-contract.review.json", {
    "status": "PASS",
    "native_validator": native,
    "production_contract_sha256": digest(contract_uri),
    "prompt_document_sha256": digest(visual["prompt_document"]),
    "frozen_reference": "PLAN_CHAR_JIA planned; no file or hash",
    "verified_semantic_phrases": semantic_tokens,
    "media_status": "NOT_RUN",
    "visual_review_status": "NOT_RUN",
    "scope": "Independent static prompt and contract review; no image generated or viewed",
})

expected = envelope["handoffs"][0]
actual = candidate["handoffs"][0]
assert {k: actual[k] for k in expected} == expected
assert len(candidate["handoffs"]) == 1
assert candidate["artifacts"][0]["slot"] == expected["target_slot"]
assert candidate["artifacts"][0]["kind"] == "VisualImagePrompt"
assert art["assets"][0]["id"] == "CHAR_JIA"
assert art["assets"][0]["identity_locks"] == [
    "同一人物与同一服装外观跨三镜连续；脸部身份仍由Canon或后续已核参考锁定",
    "右手及袖口不遮住交接的信封",
]
assert "深石墨灰" in art["assets"][0]["design"]
assert "右手" in art["assets"][0]["design"]
assert "封口" in prompt and "右手" in prompt and "袖口" in prompt
save("handoff.review.json", {
    "status": "PASS",
    "requirement_id": expected["requirement_id"],
    "source_slot": expected["source_slot"],
    "source_version": expected["source_version"],
    "source_art_sha256": digest(art_uri),
    "source_asset_id": art["assets"][0]["id"],
    "identity_locks": art["assets"][0]["identity_locks"],
    "target_slot": candidate["artifacts"][0]["slot"],
    "target_artifact_sha256": digest(visual_uri),
    "finding": "Frozen wardrobe and right-hand letter visibility are preserved; face identity and media results remain unverified.",
})

record = {
    "schema": "review-record/6.0",
    "task_id": TASK_ID,
    "batch": envelope["batch"],
    "reviewer_agent_id": row["review_dispatch"]["agent_id"],
    "reviewer_dispatch_id": row["review_dispatch"]["dispatch_id"],
    "candidate_digest": candidate_digest(candidate),
    "checks": [
        {"id": "module_receipt", "status": "PASS", "evidence": [PREFIX + "module-receipt.review.json"]},
        {"id": "image_prompt_contract", "status": "PASS", "evidence": [PREFIX + "image-prompt-contract.review.json", PREFIX + "native-contract-validation.review.json"]},
        {"id": "handoff", "status": "PASS", "evidence": [PREFIX + "handoff.review.json"]},
    ],
    "failure_owner": None,
    "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}
assert row["review_dispatch"]["agent_id"] != candidate["agent_id"]
assert [item["id"] for item in record["checks"]] == [item["id"] for item in envelope["validators"]]
validate_v6_protocol("review-record", record)
save("review-record.json", record)
print(json.dumps({
    "review_record": PREFIX + "review-record.json",
    "sha256": digest(PREFIX + "review-record.json"),
    "candidate_digest": record["candidate_digest"],
    "checks": [item["id"] + ":" + item["status"] for item in record["checks"]],
    "media_status": "NOT_RUN",
}, ensure_ascii=False, indent=2))
