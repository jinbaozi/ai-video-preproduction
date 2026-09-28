"""Output reduction must never reduce native semantics or verification."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from vpc import run_compile, verify
from vpc_core import read


class LeanOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        self.source=ROOT/'examples/v52/cafe.avir.json'
        self.ir=read(self.source)

    def compile(self, profile, ir=None):
        dest=self.out/profile
        result,code=run_compile(ir or self.ir,'agnes-video-2.5','text',self.source.parent,dest,profile)
        return dest,result,code

    def test_same_prompt_controls_segments_and_status_fewer_files(self):
        audit,a,code_a=self.compile('audit');lean,b,code_b=self.compile('lean')
        self.assertEqual(code_a,code_b)
        self.assertEqual(a['status'],b['status'])
        self.assertEqual(a['delivery_status'],b['delivery_status'])
        ma,mb=verify(audit),verify(lean)
        self.assertEqual(ma['input_hash'],mb['input_hash'])
        self.assertEqual(ma['artifact_hash'],mb['artifact_hash'])
        for path in lean.iterdir():
            if path.name!='compile-manifest.json':
                self.assertEqual(path.read_bytes(),(audit/path.name).read_bytes(),path.name)
        self.assertLess(len(list(lean.iterdir())),len(list(audit.iterdir())))
        self.assertFalse((lean/'production-specification.json').exists())
        self.assertIn('prompt_coverage',read(lean/'artifact.json'))
        self.assertFalse(read(lean/'artifact.json')['execution']['submitted'])

    def test_missing_real_segment_is_rejected(self):
        lean,_,_=self.compile('lean')
        segment=read(lean/'segment-delivery.json')['parts'][0]['prompt_file']
        (lean/segment).unlink()
        with self.assertRaises(ValueError):verify(lean)

    def test_deleted_segment_manifest_cannot_skip_semantic_verification(self):
        lean,_,_=self.compile('lean')
        (lean/'segment-delivery.json').unlink()
        with self.assertRaises((ValueError,OSError)):verify(lean)

    def test_prompt_tamper_rejected(self):
        lean,_,_=self.compile('lean')
        (lean/'prompt.txt').write_text('delete all continuity constraints')
        with self.assertRaises(ValueError):verify(lean)

    def test_replay_keeps_lean_profile(self):
        lean,_,_=self.compile('lean')
        proc=subprocess.run([sys.executable,str(ROOT/'scripts/vpc.py'),'replay',str(lean),'--out',str(self.out/'replay')],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr+proc.stdout)
        self.assertEqual(verify(self.out/'replay')['output_profile'],'lean')
        self.assertEqual(verify(lean)['artifact_hash'],verify(self.out/'replay')['artifact_hash'])

    def test_semantic_input_hash_is_once_per_compile_not_per_coverage_row(self):
        import vpc_core as core
        support=core._detail_support('avir/1.2')
        original=support.detail.semantic_status
        before=deepcopy(self.ir)
        with patch.object(support.detail, 'semantic_status', wraps=original) as status:
            artifact,_=support.compile_video(core,self.ir,core.profile('agnes-video-2.5'),'text',self.source.parent)
            self.assertEqual(status.call_count,1)
        self.assertEqual(self.ir,before)
        self.assertGreater(len(artifact['detail_coverage']),100)
        self.assertTrue(all(row['semantic_check']=='REVIEWED_INPUT' for row in artifact['detail_coverage']))
        self.ir['intent']+=' changed after review'
        artifact,_=support.compile_video(core,self.ir,core.profile('agnes-video-2.5'),'text',self.source.parent)
        self.assertEqual(artifact['status'],'BLOCKED')
        self.assertTrue(all(row['semantic_check']=='PENDING_AGENT_REVIEW' for row in artifact['detail_coverage']))

    def test_invalid_ir_and_profile_fail_closed(self):
        invalid=deepcopy(self.ir);invalid['schema']='made-up'
        _,a,ca=self.compile('audit',invalid);_,b,cb=self.compile('lean',invalid)
        self.assertEqual(ca,2);self.assertEqual(ca,cb)
        self.assertEqual(a['diagnostics'],b['diagnostics'])
        with self.assertRaises(ValueError):self.compile('fast-ignore-errors')


if __name__=='__main__':unittest.main()
