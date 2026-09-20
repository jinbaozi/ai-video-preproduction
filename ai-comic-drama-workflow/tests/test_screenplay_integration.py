"""Source-bound native screenplay integration and preserved legacy project locks."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import ROOT,read,digest_file,load_python
from ai_comic_drama_workflow.v5_adapters import encoded
from test_v5_workflow import save,seed_until,submit_fixture,result_for
sys.path.insert(0,str(ROOT/'scripts'))
from screenplay_fixture import screenplay,director_mapping

class ScreenplayIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
  import shutil
  self.author=self.base/'author';shutil.copytree(ROOT/'examples/v5/cafe',self.author)
  self.k=V5Kernel.initialize(self.base/'project',[str(self.author/'cafe.source.txt')],project_id='CAFE_DEMO',delivery='text-only',target='agnes-video-2.5')
 def stage(self,kind):return seed_until(self.k,self.author,kind)
 def submit(self,task,value,handoff=None):
  path=save(self.author/'native-test.json',value)
  return self.k.submit(result_for(task,artifact=str(path),artifact_sha256=digest_file(path),handoff=handoff or []))
 def attest(self,p):p['review']['content_sha256']=self.k.screenplay_protocol().content_hash(p)
 def test_new_stage_has_locked_module(self):
  task=self.stage('screenplay');self.assertEqual(task['module']['name'],'screenplay-grammar');self.assertEqual(len(read(self.k.root/'modules.lock.json')['modules']),6)
 def test_old_content_not_native(self):
  task=self.stage('screenplay')
  with self.assertRaisesRegex(ValueError,'Legacy screenplay'):self.submit(task,{'project_id':'CAFE_DEMO','content':'旧文本','source_refs':[self.k.state['sources'][0]['id']]})
 def test_unknown_character_needs_canon_registration(self):
  task=self.stage('screenplay');p=screenplay(self.k);p['characters'][0]['id']='NEW';self.attest(p)
  with self.assertRaisesRegex(ValueError,'Register screenplay'):self.submit(task,p)
 def test_current_canon_binding_required(self):
  task=self.stage('screenplay');p=screenplay(self.k);p['canon']['ref']=None;self.attest(p)
  with self.assertRaisesRegex(ValueError,'bind the current Canon'):self.submit(task,p)
 def test_source_id_cannot_mask_changed_bytes(self):
  task=self.stage('screenplay');p=screenplay(self.k);q=self.author/'replacement.txt';q.write_text('不是输入原文');p['sources'][0].update(uri=str(q),sha256=digest_file(q),excerpt=q.read_text());self.attest(p)
  with self.assertRaisesRegex(ValueError,'changed narrative source'):self.submit(task,p)
 def test_director_requires_mappings(self):
  task=self.stage('director')
  with self.assertRaisesRegex(ValueError,'requires screenplay mappings'):self.submit(task,read(self.author/'director.json'))
 def test_director_realization_tampering_rejected(self):
  task=self.stage('director');d=read(self.author/'director.json');rows=director_mapping(task,d);d['shots'][1]['dialogue'][0]['text']='不一样了'
  with self.assertRaises(ValueError):self.submit(task,d,rows)
 def test_native_roundtrip_snapshots_originals(self):
  task=self.stage('director');self.assertTrue(task['handoff']['required_handoffs']);submit_fixture(self.k,self.author,task)
  self.assertTrue(self.k.valid('screenplay'));self.assertTrue(self.k.valid('director'))
  value=self.k.data('screenplay');self.assertTrue(Path(value['sources'][0]['uri']).is_file());self.assertTrue(Path(value['canon']['ref']['uri']).is_file())
 def test_screenplay_revision_invalidates_director(self):
  task=self.stage('director');submit_fixture(self.k,self.author,task);self.k.revise('screenplay');self.assertFalse(self.k.valid('director'));self.assertEqual(self.k.run()['task']['kind'],'screenplay')
 def legacy_lock(self):
  lock=read(self.k.root/'modules.lock.json');lock['modules'].pop('screenplay-grammar');self.k.write('modules.lock.json',lock);return encoded(lock)
 def test_legacy_five_module_lock_continues_unchanged(self):
  before=self.legacy_lock();task=self.stage('screenplay');self.assertIsNone(task['module']);submit_fixture(self.k,self.author,task)
  self.assertEqual(self.k.run()['task']['kind'],'director');self.assertEqual((self.k.root/'modules.lock.json').read_bytes(),before)
 def test_upgrade_keeps_archives_and_invalidates_legacy_script(self):
  self.legacy_lock();task=self.stage('director');oldbytes={p.name:p.read_bytes() for p in (self.k.root/'runtime/module-archives').glob('*.skill')}
  self.k.update_modules(ROOT/'modules.lock.json',ROOT/'assets/bundled-skills')
  self.assertFalse(self.k.valid('screenplay'));task=self.k.run()['task'];self.assertEqual(task['kind'],'screenplay');self.assertEqual(task['module']['name'],'screenplay-grammar')
  for name,data in oldbytes.items():self.assertEqual((self.k.root/'runtime/module-archives'/name).read_bytes(),data)
  self.assertTrue(list((self.k.root/'history').glob('modules-*.json')))
 def test_shared_protocol_consistency(self):
  a=self.k.modules('screenplay-grammar');b=self.k.modules('director-grammar');self.assertEqual((a/'scripts/screenplay_protocol.py').read_bytes(),(b/'scripts/screenplay_protocol.py').read_bytes())
  for p in (a/'schemas').glob('*.schema.json'):self.assertEqual(p.read_bytes(),(b/'schemas/screenplay'/p.name).read_bytes())

if __name__=='__main__':unittest.main()
