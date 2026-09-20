import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import sg
import screenplay_protocol as core

class ScreenplayTests(unittest.TestCase):
 def setUp(self):self.p=core.read(ROOT/'examples/keys.project.json')
 def test_examples_final(self):
  for name in ('keys','lantern','bus-story'):
   p=core.read(ROOT/'examples'/f'{name}.project.json');self.assertEqual(core.validate(p,ROOT/'examples',True),[])
 def test_init_is_draft(self):
  p=sg.initialize('TEST','题目','一句话','screenplay');self.assertFalse(core.validate(p));self.assertTrue(core.validate(p,final=True));self.assertEqual(p['scenes'],[])
 def test_unknown_speaker(self):
  self.p['scenes'][0]['blocks'][1]['speaker']='GHOST';self.assertTrue(any('speaker' in e for e in core.validate(self.p)))
 def test_unknown_source(self):
  self.p['scenes'][0]['blocks'][0]['source_refs']=['MISSING'];self.assertTrue(any('Unknown source' in e for e in core.validate(self.p)))
 def test_duplicate_ids(self):
  self.p['scenes'][0]['blocks'][0]['id']='K2';self.assertTrue(any('Duplicate' in e for e in core.validate(self.p)))
 def test_knowledge_cannot_jump(self):
  p=core.read(ROOT/'examples/lantern.project.json');p['narrative']['events'][0]['preconditions']=[{'actor':'LIN','proposition':'HEARD','state':'knows','source_refs':['DESIGN']}];self.assertTrue(any('Knowledge precondition' in e for e in core.validate(p)))
 def test_suspicion_is_not_knowledge(self):
  p=core.read(ROOT/'examples/lantern.project.json');p['narrative']['events'][1]['preconditions'][0]['state']='knows';self.assertTrue(any('Knowledge precondition' in e for e in core.validate(p)))
 def test_no_future_cause(self):
  self.p['narrative']['events'][0]['causes']=['E2'];self.assertTrue(any('Cause' in e for e in core.validate(self.p)))
 def test_unknown_event_block(self):
  self.p['narrative']['events'][0]['block_ids']=['MISSING'];self.assertTrue(any('Event block' in e for e in core.validate(self.p)))
 def test_reveal_id_checked(self):
  self.p['narrative']['reveal_order']=['NOT_FOUND'];self.assertTrue(any('reveal' in e for e in core.validate(self.p)))
 def test_historical_evidence(self):
  self.p['culture']['claims']=[{'id':'H','statement':'某朝制度断言','kind':'historical','source_refs':['DESIGN'],'verified':True}];self.assertTrue(any('primary evidence' in e for e in core.validate(self.p)))
 def test_unverified_history_draft_only(self):
  self.p['culture']['claims']=[{'id':'H','statement':'待核实制度','kind':'historical','source_refs':['DESIGN'],'verified':False}];self.p['review']['status']='NOT_RUN';self.assertFalse(core.validate(self.p));self.assertTrue(any('Unverified historical' in e for e in core.validate(self.p,final=True)))
 def test_measured_timing_needs_evidence(self):
  self.p['timing']['measured_seconds']=30;self.assertTrue(any('timing' in e for e in core.validate(self.p)))
 def test_static_contract_not_empty(self):
  self.p['contract']['checks'][0]['method']='static';self.assertTrue(any('assertions' in e for e in core.validate(self.p)))
 def test_hard_contract_targets_content(self):
  self.p['contract']['clauses'][0]['paths']=['/title'];self.assertTrue(any('story content' in e for e in core.validate(self.p)))
 def test_stale_review(self):
  self.p['scenes'][0]['blocks'][0]['text']+='新的意思';self.assertTrue(any('Stale' in e for e in core.validate(self.p)))
 def test_proposals_not_approved_by_compile(self):
  self.p['canon']['proposals']=[{'id':'NEW','kind':'entity','text':'新角色','source_refs':['DESIGN'],'status':'proposed'}];self.p['review']['status']='NOT_RUN';self.assertTrue(any('reconciliation' in e for e in core.validate(self.p,final=True)))
 def test_apply_preserves_source_and_invalidates_review(self):
  old=core.encoded(self.p);patch=core.read(ROOT/'examples/keys.patch.json');result=sg.apply_patch(self.p,patch);self.assertEqual(core.encoded(self.p),old);self.assertEqual(result['revision'],2);self.assertEqual(result['review']['status'],'NOT_RUN');self.assertEqual(result['narrative'],self.p['narrative'])
 def patch(self,path,value):return {'schema':'screenplay-patch/1.0','base_sha256':core.content_hash(self.p),'changes':[{'path':path,'value':value,'reason':'test'}]}
 def test_locked_dialogue(self):
  self.p['rewrite_scope']['allowed_paths']=['/scenes'];self.p['review']['status']='NOT_RUN'
  with self.assertRaisesRegex(ValueError,'locked'):sg.apply_patch(self.p,self.patch('/scenes/0/blocks/8/text','我不回来了。'))
 def test_parent_replace_cannot_remove_lock(self):
  self.p['rewrite_scope'].update(level='structure',allowed_paths=['/scenes']);self.p['review']['status']='NOT_RUN'
  with self.assertRaisesRegex(ValueError,'locked'):sg.apply_patch(self.p,self.patch('/scenes',[]))
 def test_diagnose_is_read_only(self):
  self.p['rewrite_scope']['level']='diagnose';self.p['review']['status']='NOT_RUN'
  with self.assertRaisesRegex(ValueError,'read-only'):sg.apply_patch(self.p,self.patch('/scenes/0/blocks/0/text','改变'))
 def test_scope_cannot_expand(self):
  with self.assertRaisesRegex(ValueError,'authorized'):sg.apply_patch(self.p,self.patch('/narrative/ending','别的结局'))
 def test_metadata_not_mutable(self):
  self.p['rewrite_scope']['allowed_paths']=['/canon'];self.p['review']['status']='NOT_RUN'
  with self.assertRaisesRegex(ValueError,'Protected'):sg.apply_patch(self.p,self.patch('/canon',{}))
 def test_stale_patch(self):
  patch=self.patch('/scenes/0/blocks/0/text','改');patch['base_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'base'):sg.apply_patch(self.p,patch)
 def test_invalid_array_path(self):
  with self.assertRaises(ValueError):core.pointer(self.p,'/scenes/-1')
 def test_story_export_is_prose(self):
  p=core.read(ROOT/'examples/bus-story.project.json')
  with tempfile.TemporaryDirectory() as tmp:
   sg.compile_project(p,ROOT/'examples',Path(tmp)/'out');self.assertTrue((Path(tmp)/'out/story.md').exists());self.assertFalse((Path(tmp)/'out/screenplay.fountain').exists())
 def test_deterministic_compile(self):
  with tempfile.TemporaryDirectory() as tmp:
   a,b=Path(tmp)/'a',Path(tmp)/'b';sg.compile_project(self.p,ROOT/'examples',a);sg.compile_project(self.p,ROOT/'examples',b)
   self.assertEqual({str(p.relative_to(a)):p.read_bytes() for p in a.rglob('*') if p.is_file()},{str(p.relative_to(b)):p.read_bytes() for p in b.rglob('*') if p.is_file()})
   self.assertIn('@林岚',(a/'screenplay.fountain').read_text());self.assertIn('林岚：“我带早饭。”',(a/'screenplay.md').read_text())
   core.load_handoff(a/'director-handoff.json')
 def test_no_overwrite(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'out';sg.compile_project(self.p,ROOT/'examples',out)
   with self.assertRaises(ValueError):sg.compile_project(self.p,ROOT/'examples',out)
 def test_tampered_handoff(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'out';sg.compile_project(self.p,ROOT/'examples',out);h=core.read(out/'director-handoff.json');h['requirements']=[];(out/'director-handoff.json').write_bytes(core.encoded(h))
   with self.assertRaisesRegex(ValueError,'modified'):core.load_handoff(out/'director-handoff.json')
 def test_changed_source(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'source.txt';path.write_text('原文');s=self.p['sources'][0];s.update(uri=str(path),sha256=core.file_hash(path),excerpt='原文');self.p['review']['status']='NOT_RUN'
   self.assertFalse(core.validate(self.p,tmp));path.write_text('被改');self.assertTrue(any('changed' in e for e in core.validate(self.p,tmp)))
 def test_source_snapshot_survives_relocation(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'source.txt';path.write_text('原文');self.p['sources'][0].update(uri=str(path),sha256=core.file_hash(path),excerpt='原文');self.p['review']['content_sha256']=core.content_hash(self.p)
   out=Path(tmp)/'out';sg.compile_project(self.p,tmp,out);path.unlink();core.load_handoff(out/'director-handoff.json')
 def test_unknown_route_never_silently_falls_back(self):
  self.p['task']['style_request']='not-a-style'
  with self.assertRaises(ValueError):sg.route(self.p)
 def test_route_respects_forbidden_technique(self):
  self.p['task'].update(style_request='relationship_subtext',forbidden_techniques=['subtext'])
  with self.assertRaises(ValueError):sg.route(self.p)
 def test_duplicate_json_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'bad';path.write_text('{"a":1,"a":2}')
   with self.assertRaises(ValueError):core.read(path)
 def test_overflow_number_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'bad';path.write_text('{"n":1e400}')
   with self.assertRaises(ValueError):core.read(path)
 def test_patch_relocation_preserves_source(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'original.txt').write_text('原文');self.p['sources'][0].update(uri='original.txt',sha256=core.file_hash(root/'original.txt'),excerpt='原文');self.p['review']['status']='NOT_RUN'
   p=sg.relocate_references(sg.apply_patch(self.p,self.patch('/scenes/0/blocks/0/text','纸箱在墙边，桌上两只碗，一只扣着。林岚放下钥匙。'),root),root)
   self.assertEqual(core.validate(p,root/'new-directory'),[])
 def test_completion_keeps_existing_blocks(self):
  before=core.read(ROOT/'examples/complete.before.json');after=core.read(ROOT/'examples/complete.project.json')
  self.assertEqual(before['scenes'][0]['blocks'],after['scenes'][0]['blocks'][:-1]);self.assertFalse(core.validate(after,ROOT/'examples',True))
 def test_expansion_keeps_dialogue_and_ending(self):
  before=core.read(ROOT/'examples/expand.before.json');after=core.read(ROOT/'examples/expand.project.json')
  self.assertEqual(before['narrative'],after['narrative'])
  for a,b in zip(before['scenes'][0]['blocks'],after['scenes'][0]['blocks']):
   if a['kind']=='dialogue':self.assertEqual(a,b)
  self.assertFalse(core.validate(after,ROOT/'examples',True))
 def test_continuation_keeps_previous_scene(self):
  before=core.read(ROOT/'examples/continue.before.json');after=core.read(ROOT/'examples/continue.project.json');self.assertEqual(before['scenes'],after['scenes'][:1]);self.assertEqual(after['narrative']['events'][-1]['causes'],['E2']);self.assertFalse(core.validate(after,ROOT/'examples',True))
 def test_external_canon_has_single_owner(self):
  self.p['canon']['ref']={'uri':'canon.json','sha256':'0'*64};self.p['canon']['facts']=[{'id':'F','text':'重复维护的事实','source_refs':['DESIGN']}];self.assertTrue(any('editable duplicate' in e for e in core.validate(self.p)))

if __name__=='__main__':unittest.main()
