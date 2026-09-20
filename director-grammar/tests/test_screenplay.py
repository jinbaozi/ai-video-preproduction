import copy,importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('director_screenplay_protocol',ROOT/'scripts/screenplay_protocol.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
FIX=ROOT/'examples/screenplay'
class ScreenplayHandoffTests(unittest.TestCase):
 def setUp(self):
  self.d=core.read(FIX/'director.json');self.h,self.p=core.load_handoff(FIX/'director-handoff.json');self.m=core.read(FIX/'screenplay-map.json')
 def check(self):return core.validate_mapping(self.d,self.h['requirements'],self.m,self.h['content_sha256'])
 def test_valid_mapping(self):self.assertEqual(self.check(),[])
 def test_dialogue_change_rejected(self):
  self.d['shots'][1]['dialogue'][0]['text']='别问了。';self.assertTrue(self.check())
 def test_speaker_change_rejected(self):
  self.d['shots'][1]['dialogue'][0]['speaker_id']='A';self.assertTrue(self.check())
 def test_knowledge_change_rejected(self):
  self.d['shots'][1]['narrative']['character_knows']=['已经识破全部秘密'];self.assertTrue(self.check())
 def test_ending_change_rejected(self):
  self.d['shots'][2]['end_state']=self.d['shots'][0]['start_state'];self.assertTrue(self.check())
 def test_camera_change_needs_fresh_review_but_no_script_rewrite(self):
  old=core.encoded(self.p);self.d['shots'][0]['camera']['lens_intent']='更宽的观察视角';self.assertTrue(self.check());self.m['director_sha256']=core.content_hash(self.d);self.m['findings']=['仅改变视角，重核全部既有叙事断言。'];self.assertEqual(self.check(),[]);self.assertEqual(old,core.encoded(self.p))
 def test_note_only_mapping_rejected(self):
  row=self.m['mappings'][0];row['target_checks']=[{'path':'/sources/0/claim','op':'exists'}];self.assertTrue(any('not a note' in e for e in self.check()))
 def test_native_hard_clause_required(self):
  self.d['contract']['clauses'][1]['priority']='soft';self.assertTrue(any('hard director clause' in e for e in self.check()))
 def test_missing_mapping(self):
  self.m['mappings'].pop();self.assertTrue(self.check())
 def test_rebinding_does_not_allow_changed_literal(self):
  row=next(r for r in self.m['mappings'] if 'DIALOGUE' in r['requirement_id']);self.d['shots'][1]['dialogue'][0]['text']='另一句';row['target_checks'][0]['value']='另一句';self.m['director_sha256']=core.content_hash(self.d);self.assertTrue(any('Literal' in e for e in self.check()))
 def test_cli_import_and_validate(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'brief.json';p=subprocess.run([sys.executable,str(ROOT/'scripts/dg.py'),'import-screenplay',str(FIX/'director-handoff.json'),'--out',str(out)],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);self.assertNotIn('shots',core.read(out))
   p=subprocess.run([sys.executable,str(ROOT/'scripts/dg.py'),'validate',str(FIX/'director.json'),'--screenplay-handoff',str(FIX/'director-handoff.json'),'--screenplay-map',str(FIX/'screenplay-map.json')],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
 def test_one_binding_flag_rejected(self):
  p=subprocess.run([sys.executable,str(ROOT/'scripts/dg.py'),'validate',str(FIX/'director.json'),'--screenplay-handoff',str(FIX/'director-handoff.json')],capture_output=True,text=True);self.assertNotEqual(p.returncode,0)
 def test_text_and_speaker_must_be_same_utterance(self):
  row=next(r for r in self.m['mappings'] if 'DIALOGUE' in r['requirement_id'])
  self.d['shots'][1]['dialogue'][0]['speaker_id']='A'
  row['target_checks'][1]={'path':'/entities/1/id','op':'equals','value':'B'}
  next(c for c in self.d['contract']['clauses'] if c['id']=='REQ_LINE')['paths'].append('/entities')
  self.m['director_sha256']=core.content_hash(self.d)
  self.assertTrue(any('same utterance' in e for e in self.check()))
 def test_legacy_unbound_not_claimed_conformant(self):
  p=subprocess.run([sys.executable,str(ROOT/'scripts/dg.py'),'validate',str(FIX/'director.json')],capture_output=True,text=True);self.assertEqual(json.loads(p.stdout)['screenplay_binding']['status'],'NOT_CHECKED')
if __name__=='__main__':unittest.main()
