import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import dg


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.ir=dg.read(ROOT/"examples/teahouse.director.json")
        self.temp=tempfile.TemporaryDirectory(prefix="dg-tests-")
        self.directory=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def compile(self,ir=None,target="minimax-hailuo-2.3-t2v",**kwargs):
        return dg.compile_ir(ir or self.ir,target,self.directory,**kwargs)

    def invalid(self,word):
        self.assertTrue(any(word in e for e in dg.validate(self.ir)),dg.validate(self.ir))

    def image_reference(self,ir=None):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("ffmpeg/ffprobe required for media input checks")
        ir=ir or self.ir
        file=self.directory/"first.png"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","color=c=gray:s=64x64",
                        "-frames:v","1",str(file)],check=True,capture_output=True)
        ir["assets"]=[dict(id="F1",filename=file.name,path=file.name,sha256=dg.file_digest(file),status="approved",source_refs=["D1"])]
        for shot in ir["shots"]:
            shot["references"]=[dict(asset_id="F1",entity_id="L",dimension="composition",role="first_frame")]
        return file

    def test_examples_and_schemas(self):
        from jsonschema import Draft202012Validator
        for path in (ROOT/"schemas").glob("*.json"):
            Draft202012Validator.check_schema(dg.read(path))
        for path in (ROOT/"examples").glob("*.json"):
            self.assertEqual(dg.validate(dg.read(path)),[],str(path))

    def test_deterministic_and_edit_vs_generate_duration(self):
        a=self.compile();b=self.compile()
        self.assertEqual(dg.dump(a),dg.dump(b))
        self.assertEqual([j["duration_seconds"] for j in a["jobs"]],[6,6,6])
        self.assertEqual(sum(s["frames"] for s in a["edit_segments"]),360)
        self.assertFalse(a["submitted"])
        self.assertEqual(a["qa"]["G3"],"NOT_RUN")

    def test_narrative_reveal_does_not_leak_to_first_prompt(self):
        r=self.compile()
        self.assertNotIn("藏刃",r["jobs"][0]["prompt"])
        self.assertIn("藏刃",r["jobs"][1]["prompt"])

    def test_task_route_and_named_alias(self):
        d=dg.read(ROOT/"examples/demonstration.director.json")
        self.assertEqual(dg.route(d["intent"])["selected"]["style_id"],"movement_clarity")
        prompt=self.compile(d)["jobs"][0]["prompt"]
        self.assertIn("不增添戏剧冲突",prompt)
        self.assertNotIn("桌面",prompt)
        self.ir["intent"]["style_request"]="李安"
        self.assertEqual(dg.route(self.ir["intent"])["selected"]["style_id"],"intimate_subtext")

    def test_unknown_or_forbidden_named_style(self):
        self.ir["intent"]["style_request"]="unregistered-director"
        with self.assertRaises(ValueError):dg.route(self.ir["intent"])
        self.ir["intent"]["style_request"]="迈克尔·贝"
        with self.assertRaises(ValueError):dg.route(self.ir["intent"])

    def test_unknown_schema_field(self):
        self.ir["shots"][0]["invented_native_camera"]=True
        self.invalid("Additional properties")

    def test_source_and_entity_reference(self):
        self.ir["shots"][0]["source_refs"]=["ABSENT"]
        self.invalid("未知来源")
        self.ir["shots"][0]["start_state"][0]["entity_id"]="ABSENT"
        self.invalid("未知实体")

    def test_duplicate_id(self):
        self.ir["shots"][1]["id"]="S1"
        self.invalid("重复 ID")

    def test_missing_terminal_state(self):
        del self.ir["shots"][0]["end_state"]
        self.invalid("required property")

    def test_phase_overlap_and_total(self):
        self.ir["shots"][0]["phases"][1]["start_frame"]=12
        self.invalid("连续覆盖")
        self.ir["format"]["total_frames"]=359
        self.invalid("总和")

    def test_hidden_face(self):
        self.ir["shots"][1]["performance"][0]["face"]="眉毛收紧"
        self.invalid("不可见面部")

    def test_missing_feet_in_demonstration(self):
        self.ir=dg.read(ROOT/"examples/demonstration.director.json")
        self.ir["shots"][0]["composition"]["subjects"][0]["visible_parts"].remove("feet")
        self.invalid("必要证据")

    def test_axis_and_continuity(self):
        self.ir["shots"][0]["camera"]["axis_side"]="positive"
        self.invalid("轴线侧")
        self.ir["shots"][2]["start_state"][2]["position_m"]=[2,0,.8]
        self.invalid("前驱终态")

    def test_projected_left_right(self):
        self.ir["shots"][0]["composition"]["subjects"][0]["box"][0]=.65
        self.ir["shots"][0]["composition"]["subjects"][2]["box"][0]=.05
        self.invalid("左右顺序")

    def test_contract_invalid_path_and_waiver(self):
        self.ir["contract"]["clauses"][0]["paths"]=["/missing"]
        self.invalid("无效来源字段")
        self.ir["contract"]["acceptance"]["waivers"]=[dict(check_id="QAS1",reason="方便",authorization_ref="test")]
        self.invalid("硬要求不能")

    def test_unique_reference_authority(self):
        self.image_reference()
        self.ir["shots"][0]["references"].append(copy.deepcopy(self.ir["shots"][0]["references"][0]))
        self.invalid("多个权威")

    def test_valid_i2v_and_real_filename(self):
        self.image_reference()
        r=self.compile(target="runway-gen4-ui-i2v")
        self.assertEqual(r["status"],"PLANNED")
        self.assertEqual(r["jobs"][0]["bindings"][0]["filename"],"first.png")
        self.assertEqual(r["jobs"][0]["request_kind"],"ui_fields")

    def test_first_last_roles_cannot_collapse(self):
        self.image_reference()
        self.ir["shots"][0]["references"].append(dict(asset_id="F1",entity_id="A",dimension="identity",role="last_frame"))
        r=self.compile(target="runway-gen4-ui-i2v")
        self.assertEqual(r["status"],"BLOCKED")
        self.assertTrue(any("last_frame" in x for x in r["jobs"][0]["reason"]))
        self.assertEqual(r["jobs"][0]["bindings"][0]["roles"],["first_frame","last_frame"])

    def test_missing_reference_and_metric_both_block(self):
        self.ir=dg.read(ROOT/"examples/missing-reference.director.json")
        self.ir["shots"][0]["camera"]["precision"]="metric"
        r=self.compile(target="runway-gen4-ui-i2v")
        self.assertEqual(r["status"],"BLOCKED")
        reasons=" ".join(r["jobs"][0]["reason"])
        self.assertIn("metric",reasons);self.assertIn("不存在",reasons)

    def test_text_cannot_be_first_frame(self):
        file=self.directory/"first.png";file.write_text("not an image")
        self.ir["assets"]=[dict(id="F1",filename=file.name,path=file.name,sha256=dg.file_digest(file),status="approved",source_refs=["D1"])]
        self.ir["shots"][0]["references"]=[dict(asset_id="F1",entity_id="L",dimension="composition",role="first_frame")]
        r=self.compile(target="runway-gen4-ui-i2v")
        self.assertEqual(r["status"],"BLOCKED")
        self.assertTrue(any("解码" in e for e in r["jobs"][0]["reason"]))

    def audio_clause(self,channels):
        self.ir["shots"][0]["dialogue"]=[dict(speaker_id="A",text="等一下。",delivery="低声，完整清楚",start_frame=0,end_frame=24)]
        self.ir["contract"]["clauses"].append(dict(id="AUDIO",requirement="必须生成普通话原声，逐字说出等一下",priority="hard",source_refs=["U1"],paths=["/shots/0/dialogue"],check_ids=["QAS1"],change_policy="explicit_revision",allowed_channels=channels))

    def test_native_only_audio_cannot_silently_fallback(self):
        self.audio_clause(["native"])
        r=self.compile()
        self.assertEqual(r["status"],"BLOCKED")
        self.assertNotIn("必须生成普通话原声",r["jobs"][0]["prompt"])
        self.assertTrue(any("不允许 post" in x for x in r["jobs"][0]["reason"]))

    def test_unsupported_camera_lexeme_reports_natural_language(self):
        self.ir["shots"][0]["camera"]["movement"]="orbit"
        self.ir["contract"]["clauses"].append(dict(id="LEX_ONLY",requirement="只允许专用运镜词法",
            priority="hard",source_refs=["U1"],paths=["/shots/0/camera"],check_ids=["QAS1"],
            change_policy="explicit_revision",allowed_channels=["lexical"]))
        r=self.compile()
        self.assertEqual(r["status"],"BLOCKED")
        self.assertTrue(any(x["path"]=="/shots/0/camera" and x["channel"]=="natural_language" for x in r["losses"]))

    def test_audio_post_route_keeps_dialogue_without_prompting_silent_model(self):
        self.audio_clause(["post","native"])
        r=self.compile();self.assertEqual(r["status"],"PLANNED")
        self.assertNotIn("等一下",r["jobs"][0]["prompt"])
        dg.write_bundle(self.directory/"bundle",self.ir,r)
        post=dg.read(self.directory/"bundle/post-production.json")
        self.assertEqual(post["sound_and_dialogue"][0]["dialogue"][0]["text"],"等一下。")

    def test_multishot_is_one_job_with_three_edit_segments(self):
        r=self.compile(target="kling-3-ui-multishot")
        self.assertEqual(len(r["jobs"]),1);self.assertEqual(len(r["edit_segments"]),3)
        self.assertEqual(r["jobs"][0]["duration_seconds"],15)
        self.assertEqual([x["source_in_frame"] for x in r["edit_segments"]],[0,96,216])

    def test_agent_and_unknown_entrypoints(self):
        r=self.compile(target="libtv-agent")
        self.assertEqual(set(r["jobs"][0]["request"]),{"message"})
        for target in ("jimeng-entry-unverified","oiioii-entry-unverified","seko-entry-unverified"):
            self.assertEqual(self.compile(target=target)["status"],"BLOCKED")

    def test_no_truncation_and_invalid_resolution(self):
        self.ir["shots"][0]["phases"][0]["action"]="保持观察"*600
        r=self.compile();self.assertEqual(r["status"],"BLOCKED")
        self.assertGreater(len(r["jobs"][0]["prompt"]),2000)
        with self.assertRaises(ValueError):self.compile(resolution="4K")

    def test_empty_qa_and_stale_records_fail(self):
        r=self.compile();dg.write_bundle(self.directory/"bundle",self.ir,r)
        q=dg.read(self.directory/"bundle/qa-report.json")
        self.assertEqual(dg.qa_gate(self.ir,r,q,self.directory)["status"],"BLOCKED")
        self.ir["revision"]+=1
        self.assertIn("STALE"," ".join(dg.qa_gate(self.ir,r,q,self.directory)["errors"]))

    def test_text_cannot_be_media_evidence(self):
        r=self.compile();dg.write_bundle(self.directory/"bundle",self.ir,r)
        q=dg.read(self.directory/"bundle/qa-report.json")
        file=self.directory/"not-media.txt";file.write_text("review record, not video")
        for x in q["records"]:
            x.update(status="PASS",reviewer="test",observation="Synthetic claimed review",evidence_path=file.name,
                     evidence_sha256=dg.file_digest(file),media_path=file.name,media_sha256=dg.file_digest(file))
        result=dg.qa_gate(self.ir,r,q,self.directory)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertTrue(any("不能解码" in e for e in result["errors"]))

    def test_output_cannot_overwrite(self):
        r=self.compile();out=self.directory/"bundle";dg.write_bundle(out,self.ir,r)
        with self.assertRaises(ValueError):dg.write_bundle(out,self.ir,r)


if __name__=="__main__":unittest.main()
