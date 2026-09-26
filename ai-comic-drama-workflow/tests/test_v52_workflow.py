"""Native 1.2 handoff and exact-consumption dependencies; no real-media claims."""
import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from ai_comic_drama_workflow.v5_adapters import storyboard_to_avir,image_briefs,digest,encoded,pointer,assert_check
from ai_comic_drama_workflow.v52_spatial_runtime import FIELDS,panel_state,content_hash,semantic_status,position_at
from ai_comic_drama_workflow.v52_adapters import spatial_panel_dependency
from ai_comic_drama_workflow.v5_handoff import requirements,briefing
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import ROOT,digest_file

class SpatialWorkflowTests(unittest.TestCase):
 def setUp(self):self.base=ROOT/'examples/v52/cafe';self.ir=json.loads((self.base/'storyboard.json').read_text())
 def test_exact_spatial_handoff(self):
  self.ir['contract'].append({'id':'ENTITY_AND_SPACE','owner':'storyboard','strength':'hard','statement':'Synthetic entity and spatial preservation test','source_refs':[],'shot_ids':[],'checks':[{'path':'/entities','op':'equals','value':copy.deepcopy(self.ir['entities'])},{'path':'/timeline/schema','op':'equals','value':self.ir['timeline']['schema']}],'channel':'prompt','execution':'test','fallback':'block','acceptance':[{'criterion':'test','phase':'structure','evidence':'test'}]})
  avir,report=storyboard_to_avir(self.ir,self.base);self.assertEqual(report['status'],'MAPPED');self.assertEqual(report['adapter'],'1.2.0')
  for name in FIELDS:self.assertEqual(self.ir['timeline'][name],avir['timeline'][name])
  self.assertEqual(avir['timeline']['audio_events'],self.ir['timeline']['audio_events']);self.assertEqual(avir['timeline']['actions'],self.ir['timeline']['actions'])
  contract=next(c for c in avir['contract'] if c['id']=='ENTITY_AND_SPACE')
  entities=next(c for c in contract['checks'] if c['path']=='/entities')
  self.assertEqual(entities['value'],avir['entities'])
 def test_boundary_visibility_uses_authoritative_timeline_sample(self):
  shot=next(s for s in self.ir['shots'] if s['id']=='S3')
  composition=next(s for s in shot['composition']['subjects'] if s['entity_id']=='ENVELOPE')
  self.assertEqual(composition['visible_parts'],['body'])
  end_ms=max(s['at_ms'] for s in self.ir['timeline']['state_samples'] if s['shot_id']=='S3')
  sample_index=next(i for i,s in enumerate(self.ir['timeline']['state_samples']) if s['shot_id']=='S3' and s['at_ms']==end_ms)
  source_parts=self.ir['timeline']['state_samples'][sample_index]['entities']['ENVELOPE']['visible_parts']
  self.assertEqual(source_parts,[])
  avir,report=storyboard_to_avir(self.ir,self.base)
  target_shot=next(s for s in avir['shots'] if s['id']=='S3')
  target=next(s for s in target_shot['end_state'] if s['entity_id']=='ENVELOPE')
  self.assertEqual(target['visible_parts'],source_parts)
  target_index=target_shot['end_state'].index(target)
  source_path=f'/timeline/state_samples/{sample_index}/entities/ENVELOPE/visible_parts'
  target_path=f'/shots/{avir["shots"].index(target_shot)}/end_state/{target_index}/visible_parts'
  self.assertEqual(report['field_mapping'][source_path],source_path)
  coverage=next(row for row in report['detail_coverage'] if row['source_path']==source_path and row['target_path']==target_path)
  self.assertEqual(coverage['rule'],'STATE_SAMPLE.BOUNDARY_VISIBILITY.1.1')
  self.assertEqual(coverage['source_sha256'],coverage['target_sha256'])
 def test_missing_boundary_visibility_blocks_static_lowering(self):
  shot=next(s for s in self.ir['shots'] if s['id']=='S3')
  end_ms=max(s['at_ms'] for s in self.ir['timeline']['state_samples'] if s['shot_id']=='S3')
  sample=next(s for s in self.ir['timeline']['state_samples'] if s['shot_id']=='S3' and s['at_ms']==end_ms)
  del sample['entities']['ENVELOPE']['visible_parts']
  _,report=storyboard_to_avir(self.ir,self.base)
  self.assertEqual(report['status'],'BLOCKED')
  self.assertTrue(any('authoritative boundary sample' in row['reason'] for row in report['losses']))
 def test_new_relation_enum_and_contract_pointer(self):
  t=self.ir['timeline'];t['spatial_relations'].append({'id':'ABOVE_TEST','subject_node_id':'N_A','object_node_id':'N_B','predicate':'above','frame':'world','scope':{'kind':'point','at_ms':4000},'shot_ids':['S2'],'criterion':'来源明确的端点相对关系','distance_m':None,'attachment':None,'origin':t['spatial_nodes'][0]['origin']})
  path='/timeline/spatial_relations/'+str(len(t['spatial_relations'])-1)+'/predicate';clause=copy.deepcopy(self.ir['contract'][0]);clause.update(id='SPACE_NEW',checks=[{'path':path,'op':'equals','value':'above'}]);self.ir['contract'].append(clause)
  avir,report=storyboard_to_avir(self.ir,self.base);self.assertEqual(avir['timeline']['spatial_relations'][-1]['predicate'],'above');self.assertEqual(next(c for c in avir['contract'] if c['id']=='SPACE_NEW')['checks'][0]['path'],path)
 def test_source_only_and_mixed_contract_paths_are_lowered(self):
  paths=['/scenes/0/time_of_day','/entities/0/identity_locks/0','/beats/1/depends_on/0',
   '/shots/0/panels/1/event_ids/0','/shots/0/panels/1/frame','/shots/0/state_start/A/condition',
   '/shots/0/camera/axis_side','/shots/0/camera/end_m','/timeline/camera_operations/0/operation']
  clause=copy.deepcopy(self.ir['contract'][0]);clause['id']='SOURCE_ONLY_AND_MIXED'
  clause['checks']=[{'path':path,'op':'equals','value':copy.deepcopy(pointer(self.ir,path))} for path in paths]
  self.ir['contract'].append(clause)
  avir,report=storyboard_to_avir(self.ir,self.base)
  self.assertEqual(report['status'],'MAPPED');self.assertEqual(report['losses'],[])
  mapped=next(c for c in avir['contract'] if c['id']==clause['id'])['checks']
  self.assertEqual(len(mapped),len(paths));self.assertTrue(all(assert_check(avir,c) for c in mapped))
  self.assertEqual([c['path'] for c in mapped],[report['field_mapping'][p] for p in paths])
  self.assertTrue(all(not c['path'].startswith(('/beats/','/shots/0/panels/')) for c in mapped))
  self.assertEqual(avir['timeline']['extensions'][-1]['name'],'storyboard-schedule')
  from jsonschema import Draft202012Validator
  with tempfile.TemporaryDirectory() as temporary:
   project=V5Kernel.initialize(Path(temporary)/'project',['原创资料。'],project_id='SCHEMA_TEST',delivery='text-only')
   schema=json.loads((project.modules('video-prompt-compiler')/'schemas/avir-1.2.schema.json').read_text())
  self.assertEqual(list(Draft202012Validator(schema).iter_errors(avir)),[])
  self.ir['contract'][-1]['checks'][0]['value']='incorrect source assertion'
  self.assertEqual(storyboard_to_avir(self.ir,self.base)[1]['status'],'BLOCKED')
 def test_locked_camera_without_position_track_has_source_bound_hold(self):
  self.ir['timeline']['motion_tracks']=[t for t in self.ir['timeline']['motion_tracks'] if t['id']!='CAM_POS_S1']
  self.ir['timeline']['semantic_review']['input_sha256']=content_hash(self.ir)
  avir,report=storyboard_to_avir(self.ir,self.base)
  self.assertEqual(report['status'],'MAPPED');self.assertEqual([x['shot_id'] for x in report['derived_camera_tracks']],['S1'])
  track=next(t for t in avir['timeline']['motion_tracks'] if t['id']=='CAMERA_POSITION_S1')
  self.assertEqual(track['node_id'],'N_CAMERA');self.assertEqual(track['camera_operation_ids'],['CAM_S1'])
  self.assertEqual([k['value']['value'] for k in track['keyframes']],[[0,1.3,-3],[0,1.3,-3]])
  self.assertEqual([k['transition'] for k in track['keyframes']],['hold','none'])
  self.assertIn('/shots/0/camera/start_m',track['origin']['locator'])
  for row in report['detail_coverage']:
   if row['rule']=='CAMERA.LOCKED.HOLD.1.2':
    self.assertEqual(row['source_sha256'],digest(pointer(self.ir,row['source_path'])))
    self.assertEqual(row['target_sha256'],digest(pointer(avir,row['target_path'])))
  self.assertEqual(len([r for r in report['detail_coverage'] if r['rule']=='CAMERA.LOCKED.HOLD.1.2']),4)
  self.assertEqual(position_at(avir,'N_CAMERA',2000),[0,1.3,-3]);self.assertTrue(semantic_status(avir))
 def test_moving_or_unlocked_camera_is_not_inferred(self):
  source=copy.deepcopy(self.ir)
  source['timeline']['motion_tracks']=[t for t in source['timeline']['motion_tracks'] if t['id']!='CAM_POS_S1']
  source['shots'][0]['camera']['end_m']=[0,1.3,-2]
  avir,report=storyboard_to_avir(source,self.base)
  self.assertEqual(report['derived_camera_tracks'],[]);self.assertIsNone(position_at(avir,'N_CAMERA',2000))
  source['shots'][0]['camera']['end_m']=source['shots'][0]['camera']['start_m']
  source['timeline']['camera_operations'][0]['operation']='truck'
  avir,report=storyboard_to_avir(source,self.base)
  self.assertEqual(report['derived_camera_tracks'],[]);self.assertIsNone(position_at(avir,'N_CAMERA',2000))
  source['timeline']['camera_operations'][0]['operation']='locked'
  next(n for n in source['timeline']['spatial_nodes'] if n['id']=='N_CAMERA')['frame'].update(kind='screen',unit='normalized')
  avir,report=storyboard_to_avir(source,self.base)
  self.assertEqual(report['derived_camera_tracks'],[]);self.assertIsNone(position_at(avir,'N_CAMERA',2000))
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
