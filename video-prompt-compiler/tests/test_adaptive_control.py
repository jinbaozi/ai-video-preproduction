"""Adversarial routing and real frozen-package checks; no synthetic media PASS."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from adaptive_control import assess, POLICY
from shot_control.common import read, write, sha
from shot_control.control_plan import build
from shot_control.package import verify_package
from shot_control.adaptive_materials import check


def native():
    """A native-shaped unit fixture, not a semantically approved production source."""
    ir = read(ROOT/'examples/v52/cafe.avir.json')
    ir['shots'] = ir['shots'][:1]
    ir['entities'] = ir['entities'][:2]
    ir['timeline'].update(actions=[],performances=[],spatial_relations=[],state_samples=[])
    ir['timeline']['camera_operations'] = [copy.deepcopy(ir['timeline']['camera_operations'][0])]
    ir['timeline']['composition_tracks'] = [copy.deepcopy(ir['timeline']['composition_tracks'][0])]
    ir['timeline']['composition_tracks'][0]['subjects'] = ir['timeline']['composition_tracks'][0]['subjects'][:2]
    ir['timeline']['motion_tracks'] = [copy.deepcopy(t) for t in ir['timeline']['motion_tracks'][:2]]
    for t in ir['timeline']['motion_tracks']:
        t['action_ids']=[]
    return ir


def contact(ir, start=1000,end=2000):
    action=copy.deepcopy(read(ROOT/'examples/v52/cafe.avir.json')['timeline']['actions'][0])
    action.update(start_ms=start,end_ms=end,target_id='B',changes=[],depends_on=[])
    ir['timeline']['actions'].append(action)
    return action


class AdaptiveRoutingTests(unittest.TestCase):
    def row(self,ir):return assess(ir)['shots'][0]

    def test_static_people_and_numeric_description_changes_do_not_require_white_model(self):
        ir=native();result=self.row(ir)
        self.assertEqual(result['level'],1)
        self.assertEqual(result['required_assets'],['identity_anchor'])
        ir['timeline']['motion_tracks'][0]['keyframes'][2]['value']['description']='fight camera orbit mentioned only as a label'
        self.assertEqual(self.row(ir)['level'],1)

    def test_empty_scene_is_l0_not_a_missing_camera(self):
        ir=native();ir['entities']=[];ir['timeline']['composition_tracks'][0]['subjects']=[]
        self.assertEqual(self.row(ir)['level'],0)
        ir['timeline']['camera_operations']=[]
        self.assertEqual(self.row(ir)['status'],'BLOCKED')

    def test_not_applicable_contact_does_not_count_as_contact(self):
        ir=native();action=contact(ir)
        action['contact']={'status':'not_applicable','text':'No contact'}
        action['path']={'status':'not_applicable','text':'No translation'}
        self.assertEqual(self.row(ir)['level'],1)

    def test_actual_contact_and_custody_override_null_contact(self):
        ir=native();action=contact(ir)
        self.assertEqual(self.row(ir)['level'],3)
        action['contact']={'status':'not_applicable','text':'No contact claimed'}
        action['changes']=[{'field':'controllers','entity_id':'B','before':[],'after':['A.right_hand'],'at_ms':1500}]
        self.assertEqual(self.row(ir)['level'],3)
        self.assertIn(1500,self.row(ir)['critical_times_ms'])

    def test_camera_alone_and_focus_are_l2_without_geometry(self):
        for operation in ('dolly_in','rack_focus','zoom'):
            ir=native();ir['timeline']['camera_operations'][0]['operation']=operation
            row=self.row(ir);self.assertEqual(row['level'],2)
            self.assertNotIn('clay_previs',row['required_assets'])
            self.assertNotIn('proxy_keyframes',row['required_assets'])
        self.assertIn('temporal_focus_review',row['required_assets'])

    def test_unknown_camera_or_contact_is_not_a_low_risk_default(self):
        ir=native();ir['timeline']['camera_operations'][0]['operation']='unknown'
        self.assertEqual(assess(ir)['status'],'BLOCKED')
        ir=native();contact(ir)['contact']={'status':'unknown','text':'Unobserved'}
        self.assertEqual(assess(ir)['status'],'BLOCKED')

    def test_continuous_coupling_requires_l4_not_a_static_frame(self):
        ir=native();contact(ir);ir['timeline']['camera_operations'][0]['operation']='orbit'
        row=self.row(ir);self.assertEqual(row['level'],4)
        self.assertIn('clay_previs',row['required_assets'])
        self.assertNotIn('proxy_keyframes',row['required_assets'])

    def test_sequential_not_overlapping_camera_and_contact_does_not_force_l4(self):
        ir=native();contact(ir,2000,3000)
        ir['timeline']['camera_operations'][0].update(operation='dolly_in',end_ms=1500)
        self.assertEqual(self.row(ir)['level'],3)

    def test_world_motion_tracks_trigger_without_camera_operation_label(self):
        ir=native();track=ir['timeline']['motion_tracks'][0]
        track['keyframes'][0]['transition']='linear';track['keyframes'][1]['value']['value'][0]+=1
        self.assertEqual(self.row(ir)['level'],2)
        contact(ir)
        self.assertEqual(self.row(ir)['level'],3)

    def test_two_moving_actors_and_camera_require_temporal_preview(self):
        ir=native();ir['timeline']['camera_operations'][0]['operation']='tracking'
        for t in ir['timeline']['motion_tracks']:
            t['keyframes'][0]['transition']='linear';t['keyframes'][1]['value']['value'][0]+=1
        self.assertEqual(self.row(ir)['level'],4)

    def test_many_parts_of_one_actor_are_not_many_people(self):
        ir=native();ir['timeline']['camera_operations'][0]['operation']='tracking'
        track=ir['timeline']['motion_tracks'][0]
        track['keyframes'][0]['transition']='linear';track['keyframes'][1]['value']['value'][0]+=1
        second=copy.deepcopy(track);second['id']='PART';ir['timeline']['motion_tracks'].append(second)
        self.assertEqual(self.row(ir)['level'],2)

    def test_explicit_minimum_cannot_lower_inferred_risk_or_accept_boolean(self):
        ir=native();contact(ir)
        self.assertEqual(assess(ir,{'S1':0})['shots'][0]['level'],3)
        for value in (True,False,3.0,-1,5,'3'):
            with self.subTest(value=value),self.assertRaises(ValueError):assess(ir,{'S1':value})
        with self.assertRaises(ValueError):assess(ir,{'missing':4})

    def test_event_only_gaps_do_not_claim_continuous_motion_is_known(self):
        ir=native();contact(ir)
        ir['timeline']['motion_tracks'][0]['keyframes'][0]['transition']='none'
        row=self.row(ir);self.assertEqual(row['level'],3)
        self.assertTrue(row['continuous_motion_gaps']);self.assertEqual(row['status'],'PLANNED')
        ir['timeline']['camera_operations'][0]['operation']='orbit'
        self.assertEqual(self.row(ir)['status'],'BLOCKED')

    def test_no_mutation_or_hidden_file_output(self):
        ir=native();before=copy.deepcopy(ir);a=assess(ir);b=assess(ir)
        self.assertEqual(a,b);self.assertEqual(ir,before)
        self.assertFalse(a['generated']);self.assertEqual(a['media_review'],'NOT_RUN')

    def test_no_cross_shot_upgrade(self):
        ir=native();second=copy.deepcopy(ir['shots'][0]);second.update(id='S2',start_ms=4000,end_ms=8000);ir['shots'].append(second)
        op=copy.deepcopy(ir['timeline']['camera_operations'][0]);op.update(id='C2',shot_ids=['S2'],start_ms=4000,end_ms=8000,operation='orbit');ir['timeline']['camera_operations'].append(op)
        comp=copy.deepcopy(ir['timeline']['composition_tracks'][0]);comp.update(id='COMP2',shot_ids=['S2'],start_ms=4000,end_ms=8000);ir['timeline']['composition_tracks'].append(comp)
        self.assertEqual([r['level'] for r in assess(ir)['shots']],[1,2])

    def test_disjoint_actor_motion_does_not_force_continuous_previs(self):
        ir=native();ir['timeline']['camera_operations'][0]['operation']='tracking'
        for i,t in enumerate(ir['timeline']['motion_tracks']):
            a,b=(0,1000) if i==0 else (2000,3000)
            t.update(start_ms=a,end_ms=b)
            t['keyframes']=copy.deepcopy(t['keyframes'][:2])
            t['keyframes'][0].update(at_ms=a,transition='linear')
            t['keyframes'][1].update(at_ms=b,transition='none')
            t['keyframes'][1]['value']['value'][0]+=1
        self.assertEqual(self.row(ir)['level'],2)

    def test_full_length_tracks_with_disjoint_changed_intervals_stay_l2(self):
        ir=native();ir['timeline']['camera_operations'][0]['operation']='tracking'
        for i,t in enumerate(ir['timeline']['motion_tracks']):
            original=copy.deepcopy(t['keyframes'][0]);t['keyframes']=[]
            for at in (0,1000,2000,3000,4000):
                key=copy.deepcopy(original);key.update(at_ms=at,transition='none' if at==4000 else 'linear')
                if at>=(1000 if i==0 else 3000):key['value']['value'][0]+=1
                t['keyframes'].append(key)
        self.assertEqual(self.row(ir)['level'],2)

    def test_explicit_position_change_cannot_hide_behind_no_path(self):
        ir=native();a=contact(ir)
        for f in ('contact','path'):a[f]={'status':'not_applicable','text':'None'}
        a['changes']=[{'entity_id':'A','field':'position','before':[0,0,0],
                       'after':[1,0,0],'at_ms':1500}]
        self.assertGreaterEqual(self.row(ir)['level'],2)

    def test_unrelated_node_label_is_not_a_shot_dependency(self):
        ir=native();a=self.row(ir)['source_fingerprint']
        ir['timeline']['spatial_nodes'].append({'id':'UNUSED','kind':'root',
            'entity_id':None,'parent_id':None,'label':'unused'})
        self.assertEqual(self.row(ir)['source_fingerprint'],a)

    def test_numeric_alias_nonfinite_duplicate_scope_rejected(self):
        for value in (True,float('inf'),float('nan')):
            ir=native();ir['shots'][0]['end_ms']=value
            with self.assertRaises(ValueError):assess(ir)
        ir=native();ir['shots'].append(copy.deepcopy(ir['shots'][0]))
        with self.assertRaises(ValueError):assess(ir)
        with self.assertRaises(ValueError):assess({})

    def test_contact_and_light_do_not_erase_focus_obligations(self):
        ir=native();contact(ir);op=ir['timeline']['camera_operations'][0];op['operation']='rack_focus'
        light=copy.deepcopy(ir['timeline']['motion_tracks'][0]);light['property']='color';ir['timeline']['motion_tracks'].append(light)
        row=self.row(ir);self.assertEqual(row['level'],3)
        self.assertTrue({'temporal_focus_review','color_review','proxy_keyframes'} <= set(row['required_assets']))

    def test_storyboard_and_avir_route_the_same_native_fixture(self):
        a=assess(read(ROOT/'examples/v52/cafe.avir.json'))
        # Native-shaped paired timing fixture; full native roundtrip is tested in workflow.
        sb=read(ROOT/'examples/v52/cafe.avir.json');sb.pop('schema');sb['schema_version']='storyboard-ir/1.2';sb['delivery']={'fps':24}
        for shot in sb['shots']:
            shot['start_frame']=shot['start_ms']*24/1000;shot['end_frame']=shot['end_ms']*24/1000
        b=assess(sb)
        self.assertEqual([(x['level'],x['required_assets'],x['critical_times_ms']) for x in a['shots']],
                         [(x['level'],x['required_assets'],x['critical_times_ms']) for x in b['shots']])


class AdaptivePackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'package'
        self.config=read(ROOT/'examples/control/cafe-control.json');self.config['adaptive']={'policy':POLICY}
        build(ROOT/'examples/v52/cafe.avir.json',self.out,self.config)

    def reseal(self,name):
        manifest=read(self.out/'package-manifest.json');manifest['files'][name]=sha(self.out/name)
        write(self.out/'package-manifest.json',manifest)

    def test_plan_is_embedded_and_rederived_no_extra_report(self):
        result=verify_package(self.out);self.assertIn('adaptive',result['plan'])
        self.assertFalse((self.out/'adaptive-plan.json').exists())

    def test_resealed_level_or_material_removal_is_rejected(self):
        original=read(self.out/'control-plan.json')
        for key,value in [('level',0),('required_assets',[]),('generated',True)]:
            plan=copy.deepcopy(original)
            if key=='generated':plan['adaptive'][key]=value
            else:plan['adaptive']['shots'][0][key]=value
            write(self.out/'control-plan.json',plan);self.reseal('control-plan.json')
            with self.assertRaisesRegex(ValueError,'Adaptive plan'):verify_package(self.out)

    def test_no_receipts_cannot_turn_plan_into_materials_ready(self):
        result=check(self.out,{'adaptive_evidence':[]},self.root)
        self.assertEqual(result['status'],'BLOCKED')
        self.assertTrue(any('MISSING_PROXY_KEYFRAME' in x for x in result['blockers']))
        self.assertEqual(result['model_execution'],'NOT_RUN')

    def test_fake_previs_manifest_never_accepted_as_render(self):
        fake=self.root/'fake';fake.mkdir();write(fake/'render-manifest.json',{'schema':'fake','files':{}})
        evidence={'adaptive_evidence':[{'shot_id':'S1','kind':'clay_previs','package':'fake','review':{}}]}
        with self.assertRaises(ValueError):check(self.out,evidence,self.root)

    def test_evidence_path_escape_and_unrecognized_fields_rejected(self):
        for entry in ({'shot_id':'S1','kind':'clay_previs','package':'../escape','review':{}},
                      {'shot_id':'S1','kind':'clay_previs','package':'x','review':{},'trusted':True}):
            with self.assertRaises(ValueError):check(self.out,{'adaptive_evidence':[entry]},self.root)

    def test_direct_lower_cannot_bypass_selected_local_materials(self):
        from shot_control.control_lowering import lower
        result=lower(self.out,'agnes-video-2.5','text',self.out/'artifact-manifest.json')
        self.assertEqual(result['status'],'BLOCKED')
        self.assertTrue(any('MISSING_PROXY_KEYFRAME' in x for x in result['reasons']))

    def test_cli_missing_materials_exits_nonzero_and_keeps_blockers(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/control_cli.py'),'material-check',str(self.out),
                          '--evidence','-','--base',str(self.root)],input='{"adaptive_evidence":[]}',text=True,capture_output=True)
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertEqual(json.loads(p.stdout)['status'],'BLOCKED')

    def test_schema_and_manual_check_reject_boolean_minimum(self):
        self.config['adaptive']['minimum_levels']={'S1':True}
        with self.assertRaises(ValueError):build(ROOT/'examples/v52/cafe.avir.json',self.root/'bad',self.config)
        self.assertFalse((self.root/'bad').exists())

    def test_legacy_explicit_control_remains_valid(self):
        del self.config['adaptive']
        build(ROOT/'examples/v52/cafe.avir.json',self.root/'legacy',self.config)
        self.assertNotIn('adaptive',verify_package(self.root/'legacy')['plan'])

    def test_material_verifier_is_not_bypassed_by_declared_pass(self):
        fake=self.root/'fake';fake.mkdir();write(fake/'render-manifest.json',{'schema':'fake','files':{}})
        row={'shot_id':'S1','kind':'clay_previs','package':'fake','review':{'result':'PASS'}}
        with patch('shot_control.previs.verify_render',side_effect=ValueError('REAL_VERIFIER_CALLED')) as verify:
            with self.assertRaisesRegex(ValueError,'REAL_VERIFIER_CALLED'):check(self.out,{'adaptive_evidence':[row]},self.root)
            verify.assert_called_once_with(fake)


class AdaptiveActualRenderTests(unittest.TestCase):
    @unittest.skipUnless(__import__('os').environ.get('BLENDER_EXECUTABLE'), 'Requires actual Blender; never fake render completion')
    def test_actual_render_selected_scope_and_stale_geometry(self):
        import os
        from build_previs_example import fixture
        from shot_control.previs import render
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ir,config=fixture()
            config['adaptive']={'policy':POLICY}
            config['proxy_scene'].update(fps=2,resolution=[320,180])
            shutil.copyfile(ROOT/'examples/v52/cafe.source.txt',root/'cafe.source.txt')
            write(root/'source.json',ir);build(root/'source.json',root/'package',config)
            render(root/'package','S1',root/'render',os.environ['BLENDER_EXECUTABLE'])
            evidence={'adaptive_evidence':[{'shot_id':'S1','kind':'clay_previs','package':'render','review':{
                'reviewer':'synthetic integration-test reviewer; not production quality acceptance',
                'render_manifest_sha256':sha(root/'render/render-manifest.json'),
                'checks':[{'criterion':c,'result':'PASS','observation':'Synthetic test record for '+c+'; geometry-only renderer, no generated video quality claim'}
                          for c in sorted({'layout','camera','scope_limitations','timing'})]}}]}
            result=check(root/'package',evidence,root,{'S1'})
            self.assertEqual(result['status'],'CONTROL_MATERIALS_VERIFIED',result)
            self.assertEqual(result['video_quality'],'NOT_RUN')
            times={f['at_ms'] for f in result['renders']['S1'][0]['frames']}
            required=verify_package(root/'package')['plan']['adaptive']['shots'][0]['critical_times_ms']
            self.assertTrue(set(required)<=times)
            # Partial compilation must not force unselected shots to render.
            self.assertEqual(check(root/'package',evidence,root)['status'],'BLOCKED')
            evidence['adaptive_evidence'][0]['review']['checks'][0]['result']='FAIL'
            self.assertEqual(check(root/'package',evidence,root,{'S1'})['status'],'BLOCKED')
            evidence['adaptive_evidence'][0]['review']['checks'][0]['result']='PASS'
            config['proxy_scene']['objects'][0]['dimensions'][1]+=.1
            build(root/'source.json',root/'changed',config)
            with self.assertRaisesRegex(ValueError,'no longer matches'):
                check(root/'changed',evidence,root,{'S1'})
