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
from export_hypit import export


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"ffmpeg/ffprobe required")
class HypitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="dg-hypit-test-")
        self.root=Path(self.temp.name)
        self.ir=dg.read(ROOT/"examples/demonstration.director.json")
        self.ir["format"].update(width=64,height=64)
        self.execution=dg.compile_ir(self.ir,"generic-t2v",self.root)
        self.video=self.root/"fixture.mp4"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","color=c=gray:s=64x64:r=24",
            "-f","lavfi","-i","anullsrc=r=48000:cl=stereo","-t","6","-c:v","libx264","-preset","ultrafast",
            "-pix_fmt","yuv420p","-c:a","aac","-shortest",str(self.video)],capture_output=True,check=True)
        (self.root/"review.txt").write_text("Synthetic fixture only. No directing or media-quality acceptance claimed.")
        self.manifest=dict(schema_version="1.0",execution_sha256=dg.digest(self.execution),takes=[dict(id="TEST_TAKE",shot_id="S1",
            path=self.video.name,sha256=dg.file_digest(self.video),frames=144,qa_status="TEST_FIXTURE",evidence_ref="review.txt")])

    def tearDown(self):self.temp.cleanup()

    def test_export_is_actual_sources_and_copies_verified_bytes(self):
        result=export(self.ir,self.execution,self.manifest,self.root,self.root/"export",True)
        self.assertEqual(result["status"],"TEST_SOURCE_EXPORTED")
        self.assertFalse(result["built"])
        self.assertEqual(dg.file_digest(self.root/"export/media/take-1.mp4"),dg.file_digest(self.video))
        self.assertTrue((self.root/"export/main.svml").read_text().startswith("<?svml"))

    def test_changed_take_or_wrong_frames_refused(self):
        self.manifest["takes"][0]["frames"]=143
        with self.assertRaises(ValueError):export(self.ir,self.execution,self.manifest,self.root,self.root/"export",True)
        self.manifest["takes"][0]["frames"]=144
        self.manifest["takes"][0]["sha256"]="0"*64
        with self.assertRaises(ValueError):export(self.ir,self.execution,self.manifest,self.root,self.root/"export",True)

    def test_hypit_010_sources_check_and_plan_without_build(self):
        if not shutil.which("hypit"):self.skipTest("Hypit is optional")
        version=subprocess.run(["hypit","--version"],capture_output=True,text=True,check=True).stdout.strip()
        if version!="0.1.10":self.skipTest("Exporter verified against Hypit 0.1.10 only")
        out=self.root/"export";export(self.ir,self.execution,self.manifest,self.root,out,True)
        for operation,filename in (("check","main.svml"),("check","build.svrun"),("plan","build.svrun")):
            r=subprocess.run(["hypit",operation,str(out/filename),"--workspace",str(out),"--json"],capture_output=True,text=True,check=True)
            self.assertTrue(json.loads(r.stdout)["ok"])

    def test_qa_records_validate_actual_final_frame_count(self):
        out=self.root/"bundle";dg.write_bundle(out,self.ir,self.execution)
        qa=dg.read(out/"qa-report.json")
        evidence=self.root/"review.txt"
        for r in qa["records"]:
            r.update(status="PASS",reviewer="synthetic test",observation="Synthetic integrity test; no artistic claim",
                evidence_path=evidence.name,evidence_sha256=dg.file_digest(evidence),media_path=self.video.name,media_sha256=dg.file_digest(self.video))
        self.assertEqual(dg.qa_gate(self.ir,self.execution,qa,self.root)["status"],"ACCEPTED_RECORDED")
        short=self.root/"short.mp4"
        subprocess.run(["ffmpeg","-v","error","-i",str(self.video),"-frames:v","143","-an",str(short)],capture_output=True,check=True)
        final=next(x for x in qa["records"] if x["check_id"]=="G4FINAL")
        final.update(media_path=short.name,media_sha256=dg.file_digest(short))
        self.assertEqual(dg.qa_gate(self.ir,self.execution,qa,self.root)["status"],"BLOCKED")


if __name__=="__main__":unittest.main()
