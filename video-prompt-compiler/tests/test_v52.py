"""Spatial regression: planned semantics, not rendered-media acceptance."""
import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import spatial_runtime as sp
import vpc_core as core
from upgrade_spatial import upgrade

class SpatialTests(unittest.TestCase):
 def setUp(self):
  self.ir=json.loads((ROOT/'examples/v52/cafe.avir.json').read_text());self.t=self.ir['timeline'];self.base=ROOT/'examples/v52'
 def codes(self):return [e['code'] for e in core.validate(self.ir,self.base)]
 def approve(self):self.t['semantic_review']['input_sha256']=sp.content_hash(self.ir)
 def compile(self):return core.compile_ir(self.ir,core.profile('agnes-video-2.5'),'text',self.base)[0]
 def track(self,id='TEST',node='N_A_RIGHT_HAND',prop='orientation',start=0,end=1000,values=None,mode='relative',transition='none'):
  x=copy.deepcopy(self.t['motion_tracks'][0]);x.update(id=id,node_id=node,property=prop,start_ms=start,end_ms=end,shot_ids=['S1'],action_ids=[],camera_operation_ids=[],unit='relative' if mode=='relative' else 'm',axis=None,path='明确路径与运动目标',speed='先慢后停')
  x['keyframes']=[{'at_ms':at,'value':{'mode':mode,'value':v,'description':'手背朝上并保持，不提前释放','target_node_id':None},'transition':transition if at==start else 'none'} for at,v in zip((start,end),values or (None,None))];self.t['motion_tracks'].append(x);return x
 def relation(self,predicate='above',a='N_A',b='N_B',scope=None,frame='world'):
  x={'id':'TEST_REL','subject_node_id':a,'object_node_id':b,'predicate':predicate,'frame':frame,'scope':scope or {'kind':'point','at_ms':0},'shot_ids':['S1'],'criterion':'保留该关系的明确适用时刻','distance_m':None,'attachment':None,'origin':copy.deepcopy(self.t['spatial_nodes'][0]['origin'])};self.t['spatial_relations'].append(x);return x
 def local(self):
  n=copy.deepcopy(self.t['spatial_nodes'][0]);n.update(id='LOCAL',kind='part',parent_id='N_A',label='A右腕',part='人物自身右腕');pos=sp.position_at(self.ir,'N_A',0);n['frame']={'kind':'local','anchor_node_id':'N_A','unit':'m','transforms':[{'at_ms':0,'origin':pos,'basis':[[1,0,0],[0,1,0],[0,0,1]]}]};self.t['spatial_nodes'].append(n)
  self.track(node='LOCAL',prop='position',mode='numeric',values=([.1,0,0],[.2,0,0]));return n
 def test_full_native_compile(self):
  self.assertEqual(self.codes(),[]);a=self.compile();self.assertEqual(a['status'],'COMPILED');self.assertFalse(a['execution']['submitted']);self.assertEqual(a['schema'],'compiled-artifact/1.3')
 def test_action_not_duplicated_by_motion(self):
  blocks,rows=sp.render(self.ir);self.assertEqual(len([b for b in blocks if b['id']=='EV_REACH']),1);self.assertIn('右手','\n'.join(b['text'] for b in blocks));self.assertNotIn('HAND_EV_REACH','\n'.join(b['text'] for b in blocks))
 def test_deleted_hand_detail_blocks_stale_review(self):
  self.t['spatial_nodes'][-1]['part']='人物自身左手';self.assertEqual(self.compile()['status'],'BLOCKED')
 def test_missing_required_part_rejected(self):
  del self.t['spatial_nodes'][-1]['part'];self.assertIn('E_SCHEMA',self.codes())
 def test_removed_coverage_and_changed_text_detected(self):
  blocks,rows=sp.render(self.ir);self.assertTrue(sp.verify_coverage(self.ir,blocks,rows[1:]));blocks[0]['text']='删掉构图';self.assertTrue(sp.verify_coverage(self.ir,blocks,rows))
 def test_sidecar_only_cannot_satisfy_execution_detail(self):
  blocks,rows=sp.render(self.ir);row=next(r for r in rows if r['source_path'].endswith('/path') and '/motion_tracks/' in r['source_path']);row.update(disposition='not_applicable',channel='review',block=None,text_sha256=None);self.assertIn('E_DETAIL_CHANNEL',[e['code'] for e in sp.verify_coverage(self.ir,blocks,rows)])
 def test_origin_coordinates_have_execution_coverage(self):
  self.local();blocks,rows=sp.render(self.ir);p='/timeline/spatial_nodes/8/frame/transforms/0/origin/0';r=next(x for x in rows if x['source_path']==p);self.assertEqual(r['disposition'],'equivalent_conversion');self.assertIsNotNone(r['block']);self.assertEqual(sp.verify_coverage(self.ir,blocks,rows),[])
 def test_no_automatic_interpolation(self):
  tr=self.track();self.assertEqual(sp.evaluate_track(tr,500)['status'],'NEEDS_KEY_STATE');tr['keyframes'][0]['transition']='hold';self.assertEqual(sp.evaluate_track(tr,500)['status'],'DERIVED_HOLD')
 def test_numeric_linear_position_only(self):
  tr=self.track(node='N_A_RIGHT_HAND',prop='extent',mode='numeric',values=(1,3),transition='linear');self.assertEqual(sp.evaluate_track(tr,500)['value']['value'],2);self.assertNotIn('E_INTERPOLATION',self.codes())
 def test_mixed_numeric_types_rejected_without_crash(self):
  tr=self.track(prop='focus',mode='numeric',values=(1,[0,0,2]),transition='linear');self.assertIn('E_INTERPOLATION',self.codes());self.assertEqual(sp.evaluate_track(tr,500)['status'],'INVALID_VALUES')
 def test_orientation_cannot_infer_pose(self):
  self.track(mode='numeric',values=([1,0,0],[0,1,0]),transition='linear');self.assertIn('E_INTERPOLATION',self.codes())
 def test_rotation_axis_required(self):
  tr=self.track(prop='rotation',mode='numeric',values=(0,45));self.assertIn('E_ROTATION_AXIS',self.codes());tr.update(axis=[0,1,0],unit='degrees');self.assertNotIn('E_ROTATION_AXIS',self.codes())
 def test_conflicting_property_not_array_order(self):
  tr=self.track();self.t['motion_tracks'].append({**copy.deepcopy(tr),'id':'OTHER'});self.assertIn('E_TRACK_CONFLICT',self.codes())
 def test_duplicate_keys_rejected(self):
  tr=self.track();tr['keyframes'][-1]['at_ms']=0;self.assertIn('E_TRACK_KEYS',self.codes())
 def test_parallel_camera_channels(self):
  camera=self.t['camera_operations'][0];camera['operation']='truck';pan=copy.deepcopy(camera);pan.update(id='PAN',operation='pan');focus=copy.deepcopy(camera);focus.update(id='FOCUS',operation='rack_focus',start_ms=2000);self.t['camera_operations'] += [pan,focus];self.assertNotIn('E_CAMERA_CHANNEL',self.codes())
 def test_duplicate_camera_channel_rejected(self):
  camera=self.t['camera_operations'][0];camera['operation']='truck';self.t['camera_operations'].append({**copy.deepcopy(camera),'id':'TRUCK2'});self.assertIn('E_CAMERA_CHANNEL',self.codes())
 def test_local_projection_with_evidence(self):
  self.local();anchor=sp.position_at(self.ir,'N_A',0);self.assertEqual(sp.position_at(self.ir,'LOCAL',0),[anchor[0]+.1,anchor[1],anchor[2]]);self.assertEqual(self.codes(),[])
 def test_missing_same_time_anchor_blocks(self):
  n=self.local();n['frame']['transforms'][0]['at_ms']=500;self.assertIn('B_FRAME_EVIDENCE',self.codes())
 def test_wrong_transform_origin_rejected(self):
  n=self.local();n['frame']['transforms'][0]['origin'][0]+=100;self.assertIn('E_FRAME_ORIGIN',self.codes())
 def test_absent_projection_is_undetermined(self):
  n=self.local();n['frame']['transforms']=[];r=self.relation(a='LOCAL');self.assertIsNone(sp.position_at(self.ir,'LOCAL',0));self.assertEqual(sp.geometry_checks(self.ir)[-1]['status'],'UNDETERMINED')
 def test_endpoint_relation_survives_body(self):
  self.relation(predicate='near',scope={'kind':'point','at_ms':4000})['shot_ids']=['S2'];blocks,_=sp.render(self.ir);self.assertIn('【相对位置与连接｜4秒】','\n'.join(x['text'] for x in blocks));self.assertNotIn('E_SPATIAL_SCOPE',self.codes())
 def test_cut_point_is_not_emitted_twice(self):
  self.relation(predicate='near',scope={'kind':'point','at_ms':4000})['shot_ids']=['S2'];a,_=sp.render(self.ir,0,4000);b,_=sp.render(self.ir,4000,8000);self.assertFalse(any(x['id']=='TEST_REL' for x in a));self.assertEqual(len([x for x in b if x['id']=='TEST_REL']),1)
 def test_screen_world_relation_distinction(self):
  self.relation('screen_left_of');self.assertIn('E_RELATION_FRAME',self.codes())
 def test_attachment_mismatch_detected(self):
  r=self.relation('attached_to');r['attachment']={'subject_part':'右腕','object_part':'手柄','relative_offset':[9,9,9],'release_at_ms':None};self.assertIn('E_GEOMETRY',self.codes())
 def test_contact_not_faked_geometry(self):
  self.relation('touching');self.assertEqual(sp.geometry_checks(self.ir)[-1]['status'],'UNDETERMINED')
 def test_outside_and_partial_box(self):
  subject=self.t['composition_tracks'][0]['subjects'][0];subject.update(box=[-.2,.2,.4,.4],presence='partial');self.assertNotIn('E_SCREEN_BOX',self.codes());subject['presence']='outside';self.assertIn('E_VISIBLE_OUTSIDE',self.codes())
 def test_late_face_visibility_only_active_interval(self):
  c=self.t['composition_tracks'][0];late=copy.deepcopy(c);late.update(id='COMP_LATE',start_ms=500);c['end_ms']=500
  for subject in c['subjects']:subject.update(visible_parts=[],readability='body')
  self.t['composition_tracks'].insert(1,late)
  performances=[p for p in self.t['performances'] if 'S1' in p['shot_ids']]
  for p in performances:p['start_ms']=max(500,p['start_ms'])
  self.assertNotIn('E_DYNAMIC_VISIBILITY',self.codes())
 def test_panel_exact_state_does_not_infer_pose(self):
  state=sp.panel_state(self.ir,'S1',777);self.assertEqual(state['status'],'NEEDS_KEY_POSE');self.assertFalse(state['physical_interpolation'])
 def test_panel_half_open_composition(self):
  c=self.t['composition_tracks'][0];late=copy.deepcopy(c);late.update(id='COMP_LATE',start_ms=500);c['end_ms']=500;self.t['composition_tracks'].insert(1,late);self.assertEqual(sp.panel_state(self.ir,'S1',500)['composition']['id'],'COMP_LATE')
 def test_single_hand_track_scope(self):
  tr=next(t for t in self.t['motion_tracks'] if t['id']=='HAND_EV_GRASP');result=sp.affected(self.ir,track_id=tr['id']);self.assertEqual(result['shot_ids'],['S3']);self.assertNotIn('N_A',result['node_ids'])
 def test_composition_only_node_dependency(self):
  self.t['motion_tracks']=[t for t in self.t['motion_tracks'] if t['node_id']!='N_A'];result=sp.affected(self.ir,node_id='N_A');self.assertIn('S2',result['shot_ids'])
 def test_track_changes_scope(self):
  old=copy.deepcopy(self.ir);self.t['motion_tracks'][-1]['path']+='明确停稳';self.assertEqual(sp.changed_shots(old,self.ir),['S3'])
 def test_old_boundary_position_cannot_be_hidden(self):
  self.ir['shots'][0]['start_state'][0]['position'][0]=999;self.assertIn('E_BOUNDARY_VIEW',self.codes())
 def test_door_cloth_smoke_have_distinct_properties(self):
  for id,prop,label in [('DOOR','rotation','门扇'),('CLOTH','deformation','衣服下摆'),('SMOKE','extent','烟雾范围')]:
   entity=copy.deepcopy(self.ir['entities'][-1]);entity.update(id=id,label=label,appearance=label+'的已有设计状态',locks=[]);self.ir['entities'].append(entity)
   node=copy.deepcopy(self.t['spatial_nodes'][0]);node.update(id='N_'+id,entity_id=id,label=label,kind='entity',part=None,parent_id=None);self.t['spatial_nodes'].append(node);self.track(id=id,node=node['id'],prop=prop)
  self.assertNotIn('E_TRACK_CONFLICT',self.codes());blocks,_=sp.render(self.ir);body='\n'.join(b['text'] for b in blocks)
  for text in ('旋转','形态变化','范围变化'):self.assertIn(text,body)
 def test_upgrade_keeps_original_pending(self):
  original=json.loads((ROOT/'examples/v51/cafe.avir.json').read_text());before=copy.deepcopy(original);draft,report=upgrade(original);self.assertEqual(original,before);self.assertEqual(draft['timeline']['semantic_review']['status'],'PENDING');self.assertTrue(report['missing']);self.assertEqual(draft['schema'],'avir/1.2')
 def test_track_slice_has_local_time_and_requires_phase(self):
  tr=self.track(start=0,end=3000);self.assertNotIn('-1秒',sp.motion_text(self.ir,tr,1000,2000));self.assertIn('待补齐',sp.motion_text(self.ir,tr,1000,2000))
 def test_cli_blocker_nonzero(self):
  n=self.local();n['frame']['transforms'][0]['at_ms']=500
  for src in self.ir['sources']:
   if src.get('uri') and '://' not in src['uri']:src['uri']=str((self.base/src['uri']).resolve())
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'ir.json';p.write_bytes(sp.encoded(self.ir));r=subprocess.run([sys.executable,str(ROOT/'scripts/vpc.py'),'validate',str(p)],capture_output=True,text=True)
   self.assertEqual(r.returncode,2);self.assertEqual(json.loads(r.stdout)['status'],'BLOCKED')
if __name__=='__main__':unittest.main()
