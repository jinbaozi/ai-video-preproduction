"""Temporal behavior tests: no generated-video claims."""
import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import vpc_core as core
import detail_runtime as dt

class DetailedCompilerTests(unittest.TestCase):
 def setUp(self):self.ir=json.loads((ROOT/'examples/v51/cafe.avir.json').read_text());self.base=ROOT/'examples/v51'
 def errors(self):return core.validate(self.ir,self.base)
 def approve(self):self.ir['timeline']['semantic_review']['input_sha256']=dt.content_hash(self.ir)
 def compile(self):return core.compile_ir(self.ir,core.profile('agnes-video-2.5'),'text',self.base)[0]
 def test_native_compile(self):
  self.assertEqual(self.errors(),[]);a=self.compile();self.assertEqual(a['status'],'COMPILED')
  for id in ('EV_REACH','EV_PLACE','EV_RELEASE','EV_RETRACT','EV_GRASP','EV_LIFT'):self.assertEqual(a['prompt'].count('【动作 '+id+'｜'),1)
  self.assertFalse(a['execution']['submitted'])
 def test_static_style_change_invalidates_review(self):
  self.ir['shots'][0]['style'].append('B提前抢走信封');self.assertEqual(self.compile()['status'],'BLOCKED')
 def test_group_purpose_is_rendered(self):
  self.ir['timeline']['action_groups'][0]['purpose']='保持等待点头，不提前接取';b,c=dt.render(self.ir);self.assertIn('保持等待点头，不提前接取','\n'.join(x['text'] for x in b))
 def test_missing_effector_rejected(self):
  del self.ir['timeline']['actions'][0]['effector'];self.assertIn('E_SCHEMA',[e['code'] for e in self.errors()])
 def test_stale_semantic_review_blocks(self):
  self.ir['timeline']['actions'][0]['operation']='错误地换成左手';self.assertEqual(self.compile()['status'],'BLOCKED')
 def test_deleted_detail_trace_detected(self):
  b,c=dt.render(self.ir);next(x for x in b if x['id']=='EV_REACH')['text']+='错误的左手';self.assertTrue(dt.verify_coverage(self.ir,b,c))
 def test_removed_coverage_detected(self):
  b,c=dt.render(self.ir);self.assertTrue(dt.verify_coverage(self.ir,b,c[1:]))
 def test_dependencies_not_flattened(self):
  self.ir['timeline']['actions'][1]['depends_on'][0]['action_id']='MISSING';self.assertIn('E_DEPENDENCY',[e['code'] for e in self.errors()])
 def test_causal_cycle(self):
  a,b=self.ir['timeline']['actions'][:2];a['depends_on']=[{'action_id':b['id'],'relation':'after_start','marker':None,'offset_ms':0}]
  self.assertIn('E_DEPENDENCY_CYCLE',[e['code'] for e in self.errors()])
 def test_cross_shot_dialogue_once(self):
  a=self.ir['timeline']['audio_events'][0];a.update(start_ms=7500,end_ms=8500,shot_ids=['S2','S3'],placement='off_screen',lip_sync=False)
  self.approve();self.assertEqual(self.errors(),[]);out=self.compile();self.assertEqual(len([r for r in out['post_production'] if r['id']==a['id']]),1)
 def test_offscreen_post_does_not_request_lips(self):
  a=self.ir['timeline']['audio_events'][0];a.update(placement='off_screen',lip_sync=False);self.approve();out=self.compile()
  self.assertNotIn('【后期对白的画内口型',out['prompt'])
 def test_action_middle_sound_anchor(self):
  a=self.ir['timeline']['actions'][1];a['markers'].append({'id':'CONTACT','at_ms':1480,'meaning':'初次接触'})
  cue=next(x for x in self.ir['timeline']['audio_events'] if x['kind']=='sfx');cue['sync']={'action_id':a['id'],'anchor':'marker','marker_id':'CONTACT','offset_ms':0}
  self.assertEqual(self.errors(),[])
 def test_unseen_face_blocks_only_active_interval(self):
  p=next(x for x in self.ir['timeline']['performances'] if x['readability']=='face');v=next(x for x in self.ir['timeline']['visibility'] if x['entity_id']==p['actor_id'] and x['shot_id']==p['shot_ids'][0]);v['start_ms']=p['start_ms']
  self.assertNotIn('E_DYNAMIC_VISIBILITY',[e['code'] for e in self.errors()]);v['start_ms']+=100
  self.assertIn('E_DYNAMIC_VISIBILITY',[e['code'] for e in self.errors()])
 def test_conflicting_state_change(self):
  a=self.ir['timeline']['actions'][1];b=copy.deepcopy(a);b.update(id='CONFLICT',semantic_id='CONFLICT');self.ir['timeline']['actions'].append(b)
  self.assertIn('E_STATE_CONFLICT',[e['code'] for e in self.errors()])
 def test_camera_gap(self):
  self.ir['timeline']['camera_operations'][0]['start_ms']=20;self.assertIn('E_CAMERA_GAP',[e['code'] for e in self.errors()])
 def test_budget_preserves_complete_text(self):
  full=self.compile()['prompt'];self.ir['policy']['max_canonical_units']=10;out=self.compile()
  self.assertEqual(out['status'],'BLOCKED');self.assertEqual(out['prompt'],full);self.assertTrue(out['segment_proposals'])
 def test_missing_key_pose_not_interpolated(self):
  r=dt.panel_state(self.ir,'S1',777);self.assertEqual(r['status'],'NEEDS_KEY_POSE');self.assertFalse(r['interpolated'])
 def test_fraction_time_rounding(self):
  self.assertEqual(dt.ms(30000,'30000/1001'),1001000)
 def test_unknown_execution_extension_blocks(self):
  self.ir['timeline']['extensions'].append({'name':'extra','version':'1','channel':'prompt','instruction':'未知控制','payload':{},'supported':False,'origin':self.ir['timeline']['actions'][0]['origin']})
  self.assertIn('E_EXTENSION_UNSUPPORTED',[e['code'] for e in self.errors()])
 def test_late_shot_dependency_invalidation(self):
  self.ir['timeline']['actions'][-1]['depends_on'].append({'action_id':'EV_REACH','relation':'after_end','marker':None,'offset_ms':0})
  self.assertIn('S3',dt.affected_shots(self.ir,'S1'))
 def test_fixed_camera_allows_independent_focus_pull(self):
  c=copy.deepcopy(self.ir['timeline']['camera_operations'][0]);c.update(id='FOCUS_PULL',operation='rack_focus',start_ms=1000,end_ms=2000,focus='焦点从纸边转到A面部');self.ir['timeline']['camera_operations'].append(c)
  self.assertNotIn('E_CAMERA_CONFLICT',[e['code'] for e in self.errors()])
 def test_single_action_can_have_multiple_state_nodes(self):
  a=next(x for x in self.ir['timeline']['actions'] if any(c['field']=='position' for c in x['changes']));c=next(x for x in a['changes'] if x['field']=='position');first=copy.deepcopy(c)
  first['at_ms']=(a['start_ms']+c['at_ms'])/2;first['after']=[(x+y)/2 for x,y in zip(c['before'],c['after'])];c['before']=copy.deepcopy(first['after']);a['changes'].insert(0,first)
  self.assertNotIn('E_STATE_CONFLICT',[e['code'] for e in self.errors()])
 def test_camera_type_unknown_is_blocked(self):
  self.ir['timeline']['camera_operations'][0]['operation']='unknown';self.approve();self.assertEqual(self.compile()['status'],'BLOCKED')
 def test_segment_requires_explicit_mid_action_pose(self):
  self.ir['timeline']['segments']=[{'id':'PART_A','start_ms':0,'end_ms':777,'shot_ids':['S1'],'status':'accepted','continuous_shot':True,'entry_state':'起始持物','exit_state':'待明确中间姿态','camera_continuity':'机位保持','audio_continuity':'使用全局后期轨','reference_plan':'需要末帧','overlap_ms':0,'cost_impact':'待核验'}]
  result=dt.segment_plan(self.ir)[0];self.assertEqual(result['status'],'BLOCKED');self.assertIn('NEEDS_KEY_POSE:777',result['reasons']);self.assertFalse(result.get('submitted',False))
 def test_static_fields_have_body_coverage(self):
  out=self.compile();paths={x['source_path'] for x in out['detail_coverage'] if x['disposition']=='emitted'}
  self.assertIn('/shots/0/style/0',paths);self.assertIn('/scenes/0/lighting',paths)
 def test_dialogue_speaker_fidelity_is_structural(self):
  self.ir['timeline']['audio_events'][0]['speaker_id']='A';self.assertIn('E_DIALOGUE_FIDELITY',[e['code'] for e in self.errors()])
 def test_legacy_boundary_view_cannot_disagree(self):
  self.ir['shots'][0]['start_state'][0]['position'][0]=99;self.assertIn('E_BOUNDARY_VIEW',[e['code'] for e in self.errors()])
 def test_unrelated_continuous_ambience_does_not_invalidate_every_shot(self):
  self.assertEqual(dt.affected_shots(self.ir,'S3'),['S3'])
 def test_temporal_change_is_part_of_shot_scope(self):
  before=copy.deepcopy(self.ir);self.ir['timeline']['actions'][-1]['end_ms']+=1;self.assertEqual(dt.changed_shots(before,self.ir),['S3'])
if __name__=='__main__':unittest.main()
