"""Offline behavior tests; synthetic media only tests evidence bookkeeping."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import art_compile as art
from jsonschema import Draft202012Validator


class ArtTests(unittest.TestCase):
    def setUp(self):
        self.base = art.ROOT / "examples"
        self.a = art.read(self.base / "tavern.art.json")
        self.temp = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def linked(self):
        return art.read(self.base / "teahouse-linked.art.json")

    def invalid(self, fragment, data=None, base=None):
        with self.assertRaisesRegex(ValueError, fragment):
            art.validate(data or self.a, base or self.base)

    def compile(self, data=None, target="generic-keyframe", name="out"):
        out = self.tmp / name
        result = art.compile_art(data or self.a, self.base, target, out)
        return result, out

    def media(self, video=False):
        suffix = ".mp4" if video else ".png"
        path = self.tmp / ("synthetic-evidence" + suffix)
        command = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=64x64:r=10"]
        command += ["-t", "0.3", "-pix_fmt", "yuv420p"] if video else ["-frames:v", "1"]
        subprocess.run(command + [str(path)], check=True, capture_output=True)
        return path

    def reference(self, path):
        return dict(id="REF1", asset_id="BOWL", role="prop", file=str(path), sha256=art.digest(path.read_bytes()),
                    status="ready", inherit=["碗形制"], exclude=["其他物件"], rights="synthetic test fixture only", source_refs=["D1"])

    def test_all_schemas_and_examples(self):
        for path in (art.ROOT / "schemas").glob("*.json"):
            Draft202012Validator.check_schema(art.read(path))
        for path in self.base.glob("*.art.json"):
            with self.subTest(example=path.name):
                self.assertEqual(art.validate(art.read(path), self.base)["status"], "STATIC_VALID")

    def test_contract_schema_parity(self):
        standalone = art.read(art.ROOT / "schemas/production-contract.schema.json")
        embedded = art.read(art.ROOT / "schemas/art-ir.schema.json")["$defs"]["contract"]
        self.assertEqual({k: v for k, v in standalone.items() if k not in {"$id", "$schema"}}, embedded)

    def test_director_fixture_is_self_contained(self):
        a = self.linked()
        art.validate(a, self.base)
        self.assertEqual(art.digest((self.base / a["director"]["uri"]).read_bytes()), a["director"]["sha256"])

    def test_duplicate_ids(self):
        self.a["assets"].append(copy.deepcopy(self.a["assets"][0]))
        self.invalid("Duplicate ID")

    def test_unknown_source(self):
        self.a["assets"][0]["source_refs"] = ["MISSING"]
        self.invalid("Unknown source")

    def test_director_owned_fields_rejected(self):
        for field in ("camera", "performance", "dialogue", "frames"):
            a = copy.deepcopy(self.a)
            a["shots"][0][field] = {}
            self.invalid("Schema", a)

    def test_unknown_material(self):
        self.a["assets"][0]["material_ids"] = ["GOLD"]
        self.invalid("Unknown material")

    def test_structure_count(self):
        self.a["set"]["counts"][0]["count"] = 7
        self.invalid("count mismatch")

    def test_layout_bounds(self):
        self.a["set"]["layout"][0]["position_m"][0] = 100
        self.invalid("outside bounds")

    def test_functional_zone_bounds(self):
        self.a["set"]["functional_zones"][0]["max_m"][0] = -10
        self.invalid("Invalid functional zone")

    def test_state_chain(self):
        self.a["events"][1]["before"] = "table"
        self.invalid("State chain mismatch")

    def test_forbidden_state_field(self):
        self.a["events"][0]["field"] = "face_identity"
        self.invalid("State mutation not allowed")

    def test_state_value(self):
        self.a["events"][0]["after"] = "floating"
        self.invalid("outside contract")

    def test_initial_state(self):
        self.a["assets"][-1]["initial_state"]["holder"] = "floating"
        self.invalid("Invalid initial state")

    def test_state_replay(self):
        result = art.states(self.a)
        self.assertEqual(result["S01"]["before"]["BOWL"]["holder"], "table")
        self.assertEqual(result["S03"]["before"]["BOWL"]["holder"], "host")
        self.assertEqual(result["S03"]["after"]["BOWL"]["holder"], "guest")

    def test_unknown_style_does_not_fallback(self):
        self.a["brief"]["tags"] = ["no-match-tag"]
        self.invalid("No semantic style match")

    def test_locked_style_hard_filter(self):
        self.a["brief"]["locked_style"] = "brand_product"
        self.invalid("Locked style conflicts")

    def test_secondary_is_one_dimension(self):
        self.a["brief"]["secondary"] = dict(style_id="graphic_blocks", dimension="camera", reason="invalid ownership")
        self.invalid("Schema")

    def test_secondary_dimension_compiles(self):
        self.a["brief"]["secondary"] = dict(style_id="graphic_blocks", dimension="palette", reason="强化器物强调色")
        _, out = self.compile()
        text = (out / "prompts/S01.txt").read_text()
        self.assertIn("辅助维度（仅此维度）：palette", text)

    def test_director_hash_invalidation(self):
        a = self.linked()
        a["director"]["sha256"] = "0" * 64
        self.invalid("Stale DirectorIR", a)

    def test_director_canon_alignment(self):
        a = self.linked()
        a["canon"]["uri"] = "local:wrong-canon"
        self.invalid("Canon reference mismatch", a)

    def test_director_entity_alignment(self):
        a = self.linked()
        a["assets"][0]["entity_id"] = "NOT_A"
        self.invalid("Unknown host entity", a)

    def test_expression_visibility(self):
        a = self.linked()
        a["shots"][1]["performance_support"][0]["required_parts"] = ["eyes"]
        self.invalid("not visible", a)

    def test_director_event_owner(self):
        a = self.linked()
        a["events"][0]["director_pointer"] = "/shots/2/phases/1"
        self.invalid("its director phase", a)

    def test_director_context_preserved(self):
        a = self.linked()
        _, out = self.compile(a, "generic-video")
        linked = art.read(self.base / a["director"]["uri"])
        handoff = art.read(out / "handoff.json")
        self.assertEqual([s["director_context"] for s in handoff["shots"]], linked["shots"])

    def test_missing_contract_pointer(self):
        self.a["contract"]["clauses"][0]["paths"] = ["/missing"]
        self.invalid("outside design contract")

    def test_asset_locks_must_be_bound_to_contract(self):
        for clause in self.a["contract"]["clauses"]:
            clause["paths"] = [p for p in clause["paths"] if not p.startswith("/assets/")]
        self.invalid("does not bind visible shot/asset")

    def test_event_clause_scope(self):
        self.a["contract"]["clauses"][-1]["shot_ids"] = []
        self.invalid("acceptance does not cover|explicit shot scope")

    def test_check_scope_not_interchangeable(self):
        self.a["contract"]["clauses"][-1]["check_ids"] = ["QA_S01"]
        self.invalid("does not cover")

    def test_unverified_hard_source(self):
        self.a["sources"][0]["verification"] = "unverified"
        self.invalid("unverified source")

    def test_authorization_source_required(self):
        self.a["contract"]["execution"]["mode"] = "authorized_execution"
        self.invalid("authorization requires")

    def test_inferred_design_cannot_authorize_execution(self):
        self.a["contract"]["execution"].update(mode="authorized_execution", authorization_ref="D1")
        self.invalid("cannot be a design inference")

    def test_planned_reference_blocks_compile(self):
        a = art.read(self.base / "missing-reference.art.json")
        receipt, out = self.compile(a, "generic-i2v")
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any("REFERENCE_NOT_READY" in b for b in receipt["blockers"]))
        self.assertFalse(art.read(out / "handoff.json")["runnable"])

    def test_i2v_without_first_frame(self):
        receipt, _ = self.compile(self.linked(), "generic-i2v")
        self.assertTrue(any("FIRST_FRAME_MISSING" in b for b in receipt["blockers"]))

    def test_video_without_director_blocks(self):
        receipt, _ = self.compile(target="generic-video")
        self.assertTrue(any("DIRECTOR_UNRESOLVED" in b for b in receipt["blockers"]))

    def test_brand_target_is_not_native_adapter(self):
        receipt, out = self.compile(self.linked(), "seedance-handoff")
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(art.read(out / "handoff.json")["api_submission_allowed"])

    def test_unknown_target(self):
        with self.assertRaisesRegex(ValueError, "Unknown target"):
            self.compile(target="invented-api")

    def test_keyframe_does_not_mix_end_state(self):
        _, out = self.compile()
        text = (out / "prompts/S03.txt").read_text()
        self.assertIn('"holder": "host"', text)
        self.assertNotIn('"holder": "guest"', text)
        self.assertNotIn("由 host 变为 guest", text)

    def test_hidden_assets_not_expanded_early(self):
        _, out = self.compile(self.linked(), "generic-video")
        text = (out / "prompts/S1.txt").read_text()
        self.assertNotIn("资产 K（", text)
        self.assertNotIn("STATE_PULL", text)

    def test_deterministic_compilation(self):
        _, first = self.compile(name="first")
        _, second = self.compile(name="second")
        self.assertEqual({str(p.relative_to(first)): p.read_bytes() for p in first.rglob("*") if p.is_file()},
                         {str(p.relative_to(second)): p.read_bytes() for p in second.rglob("*") if p.is_file()})

    def test_no_overwrite(self):
        self.compile()
        with self.assertRaisesRegex(ValueError, "must be empty"):
            self.compile()

    def test_ready_reference_decodes(self):
        path = self.media()
        self.a["references"] = [self.reference(path)]
        self.a["shots"][0]["required_references"] = ["REF1"]
        self.assertEqual(art.validate(self.a, self.base)["status"], "STATIC_VALID")

    def test_text_masquerading_as_reference(self):
        path = self.tmp / "fake.png"
        path.write_text("not a visual reference")
        self.a["references"] = [self.reference(path)]
        self.invalid("cannot be probed|No visual stream|cannot be decoded")

    def test_stale_reference(self):
        path = self.tmp / "missing.png"
        path.write_bytes(b"before")
        self.a["references"] = [self.reference(path)]
        path.write_bytes(b"after")
        self.invalid("Stale reference hash")

    def test_conflicting_reference_authority(self):
        path = self.media()
        one = self.reference(path)
        two = copy.deepcopy(one)
        two["id"] = "REF2"
        self.a["references"] = [one, two]
        self.a["shots"][0]["required_references"] = ["REF1", "REF2"]
        self.invalid("Conflicting reference")

    def test_initial_qa_is_not_acceptance(self):
        _, out = self.compile()
        result = art.verify_qa(out, out / "qa-report.json")
        self.assertEqual(result["status"], "NOT_ACCEPTED")

    def test_forged_acceptance_rejected(self):
        _, out = self.compile()
        qa = art.read(out / "qa-report.json")
        qa["status"] = "ACCEPTED_RECORDED"
        (out / "qa-report.json").write_text(art.dumps(qa))
        with self.assertRaisesRegex(ValueError, "contradicts"):
            art.verify_qa(out, out / "qa-report.json")

    def test_edited_bundle_invalidates_qa(self):
        _, out = self.compile()
        (out / "prompts/S01.txt").write_text("silent free rewrite")
        with self.assertRaisesRegex(ValueError, "Compiled artifact changed"):
            art.verify_qa(out, out / "qa-report.json")

    def test_synthetic_qa_records_can_be_verified(self):
        a = art.read(self.base / "product.art.json")
        _, out = self.compile(a)
        path = self.media()
        report = self.tmp / "synthetic-review.txt"
        report.write_text("Synthetic fixture; bookkeeping test, NOT actual design acceptance.")
        qa = art.read(out / "qa-report.json")
        for record, check in zip(qa["records"], a["contract"]["checks"]):
            file = report if check["method"] == "static" else path
            record.update(result="PASS", reviewer="synthetic-test-fixture", observation="Only testing record validation",
                          evidence=[dict(file=str(file), sha256=art.digest(file.read_bytes()), kind="report" if file == report else "image", locator="frame 0")])
        qa["status"] = "ACCEPTED_RECORDED"
        (out / "qa-report.json").write_text(art.dumps(qa))
        self.assertEqual(art.verify_qa(out, out / "qa-report.json")["status"], "ACCEPTED_RECORDED")
        path.write_text("replaced after review")
        with self.assertRaisesRegex(ValueError, "missing or stale"):
            art.verify_qa(out, out / "qa-report.json")

    def test_text_is_not_media_evidence(self):
        _, out = self.compile()
        qa = art.read(out / "qa-report.json")
        path = self.tmp / "pretend.png"
        path.write_text("not media")
        record = next(r for r in qa["records"] if r["check_id"] == "QA_S01")
        record.update(result="PASS", reviewer="test", observation="test", evidence=[dict(file=str(path), sha256=art.digest(path.read_bytes()), kind="image", locator="frame 0")])
        (out / "qa-report.json").write_text(art.dumps(qa))
        with self.assertRaisesRegex(ValueError, "cannot be probed|No visual stream|cannot be decoded"):
            art.verify_qa(out, out / "qa-report.json")

    def test_duplicate_json_key_rejected(self):
        path = self.tmp / "duplicate.json"
        path.write_text('{"revision":1,"revision":2}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            art.read(path)

    def test_nonfinite_json_rejected(self):
        path = self.tmp / "nan.json"
        path.write_text('{"value":NaN}')
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            art.read(path)


if __name__ == "__main__":
    unittest.main()
