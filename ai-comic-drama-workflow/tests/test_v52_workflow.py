"""Native 1.2 handoff and exact-consumption dependencies; no real-media claims."""
import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from ai_comic_drama_workflow.v5_adapters import storyboard_to_avir,image_briefs,digest,encoded
from ai_comic_drama_workflow.v52_spatial_runtime import FIELDS,panel_state,content_hash
from ai_comic_drama_workflow.v52_adapters import spatial_panel_dependency
from ai_comic_drama_workflow.v5_handoff import requirements,briefing
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import ROOT,digest_file

class SpatialWorkflowTests(unittest.TestCase):
 def setUp(self):self.base=ROOT/'examples/v52/cafe';self.ir=json.loads((self.base/'storyboard.json').read_text())
 def test_exact_spatial_handoff(self):
  avir,report=storyboard_to_avir(self.ir,self.base);self.assertEqual(report['status'],'MAPPED');self.assertEqual(report['adapter'],'1.2.0')
  for name in FIELDS:self.assertEqual(self.ir['timeline'][name],avir['timeline'][name])
  self.assertEqual(avir['timeline']['audio_events'],self.ir['timeline']['audio_events']);self.assertEqual(avir['timeline']['actions'],self.ir['timeline']['actions'])
 def test_new_relation_enum_and_contract_pointer(self):
  t=self.ir['timeline'];t['spatial_relations'].append({'id':'ABOVE_TEST','subject_node_id':'N_A','object_node_id':'N_B','predicate':'above','frame':'world','scope':{'kind':'point','at_ms':4000},'shot_ids':['S2'],'criterion':'来源明确的端点相对关系','distance_m':None,'attachment':None,'origin':t['spatial_nodes'][0]['origin']})
  path='/timeline/spatial_relations/'+str(len(t['spatial_relations'])-1)+'/predicate';clause=copy.deepcopy(self.ir['contract'][0]);clause.update(id='SPACE_NEW',checks=[{'path':path,'op':'equals','value':'above'}]);self.ir['contract'].append(clause)
  avir,report=storyboard_to_avir(self.ir,self.base);self.assertEqual(avir['timeline']['spatial_relations'][-1]['predicate'],'above');self.assertEqual(next(c for c in avir['contract'] if c['id']=='SPACE_NEW')['checks'][0]['path'],path)
 def test_handoff_retains_transform_origin(self):
  director=json.loads((self.base/'director.json').read_text());n=director['timeline']['spatial_nodes'][0];n['frame']['transforms']=[{'at_ms':0,'origin':[0,0,0],'basis':[[1,0,0],[0,1,0],[0,0,1]]}];inputs=[('director',director,{'uri':'director.json','sha256':'0'*64})]
  req=requirements('storyboard',inputs);self.assertTrue(any(r['source_paths']==['/timeline/spatial_nodes/0/frame/transforms/0/origin/0'] for r in req));self.assertIn('timeline',briefing('storyboard',inputs,{})['inputs'][0]['coordinates'])
 def test_panel_uses_current_composition(self):
  original=copy.deepcopy(self.ir['timeline']['composition_tracks'][0]);late=copy.deepcopy(original);late.update(id='COMP_MID',start_ms=1500);late['framing']='此刻偏重手与信封';self.ir['timeline']['composition_tracks'][0]['end_ms']=1500;self.ir['timeline']['composition_tracks'].insert(1,late)
  rows=image_briefs('storyboard',self.ir);p=next(r for r in rows if r['id']=='P2');self.assertEqual(p['composition']['framing'],'此刻偏重手与信封');self.assertEqual(p['events'],[]);self.assertNotIn('actions',p['state_evaluation'])
 def test_later_track_key_does_not_invalidate_previous_panel(self):
  before={r['id']:r['spatial_dependency']['value'] for r in image_briefs('storyboard',self.ir)};tr=next(x for x in self.ir['timeline']['motion_tracks'] if x['id']=='HAND_EV_GRASP');tr['keyframes'][-1]['value']['description']+='；腕部保持'
  after={r['id']:r['spatial_dependency']['value'] for r in image_briefs('storyboard',self.ir)};self.assertEqual(before['P7'],after['P7']);self.assertEqual(before['P1'],after['P1'])
 def test_current_key_changes_only_consuming_panel(self):
  before={r['id']:r['spatial_dependency']['value'] for r in image_briefs('storyboard',self.ir)};tr=next(x for x in self.ir['timeline']['motion_tracks'] if x['id']=='HAND_EV_GRASP');tr['keyframes'][0]['value']['description']+='；右手指腹初触纸面'
  after={r['id']:r['spatial_dependency']['value'] for r in image_briefs('storyboard',self.ir)};self.assertNotEqual(before['P7'],after['P7']);self.assertEqual(before['P1'],after['P1']);self.assertEqual(before['P8'],after['P8'])
 def test_pinned_old_adapter_uses_legacy_branch(self):
  spec=importlib.util.spec_from_file_location('v51_pinned_example',ROOT/'scripts/run_v5_example.py');example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'example';example.run_example(out,'v51');k=V5Kernel(out/'project');k.project['adapter_version']='1.1.0';k.write('project.json',k.project);lock=(k.root/'modules.lock.json').read_bytes();k.revise('target',target='agnes-video-2.5');result=k.compile();self.assertNotEqual(result['status'],'BLOCKED');self.assertEqual(k.project['adapter_version'],'1.1.0');self.assertEqual((k.root/'modules.lock.json').read_bytes(),lock)
 def test_storyboard_input_unchanged(self):
  original=encoded(self.ir);storyboard_to_avir(self.ir,self.base);self.assertEqual(encoded(self.ir),original)
 def test_bundled_workflow_revision_and_resume(self):
  spec=importlib.util.spec_from_file_location('v52_example',ROOT/'scripts/run_v5_example.py');example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'example';result=example.run_example(out,'v52');self.assertEqual(result['status'],'DELIVERED');k=V5Kernel(out/'project');self.assertEqual(k.run()['status'],'DELIVERED');self.assertTrue(k.validate(True)['valid'])
   with self.assertRaisesRegex(ValueError,'one shot/action/node/track'):k.revise('storyboard',node_id='N_A',track_id='HAND_EV_GRASP')
   jobs=k.image_jobs(7);self.assertEqual(len(jobs),8);self.assertTrue(all(k.dependencies_valid(j['dependencies']) for j in jobs))
   k.revise('storyboard',track_id='HAND_EV_GRASP');task=k.run()['task'];self.assertEqual(task['scope']['shot_ids'],['S3']);self.assertEqual(task['scope']['track_ids'],['HAND_EV_GRASP'])
   resumed=V5Kernel(out/'project');self.assertEqual(resumed.run()['task']['task_id'],task['task_id']);self.assertFalse(k.validate()['video_generated'])
if __name__=='__main__':unittest.main()
