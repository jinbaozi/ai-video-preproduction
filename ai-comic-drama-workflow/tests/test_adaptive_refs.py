"""Reference bookkeeping unit fixtures; these do not claim actual Blender/media review."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ai_comic_drama_workflow.adaptive_refs import index, for_panel, binding_valid
from ai_comic_drama_workflow.v5_adapters import digest
from ai_comic_drama_workflow.v5_modules import digest_file, read
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.adaptive_control import POLICY


class AdaptiveReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'control').mkdir()
        (self.root/'control/package-manifest.json').write_text('{}')
        # Arbitrary bytes exercise accepted-record references, not renderer validation.
        (self.root/'proxy.png').write_bytes(b'unit-reference-bytes')
        self.control={'status':'READY','uri':'control',
            'package_manifest_sha256':digest_file(self.root/'control/package-manifest.json'),
            'adaptive':{'shots':[{'shot_id':'S1','level':3,'required_assets':['proxy_keyframes']},
                                 {'shot_id':'S2','level':1,'required_assets':['identity_anchor']}]},
            'materials':{'status':'CONTROL_MATERIALS_VERIFIED','renders':{'S1':[{'frames':[
                {'at_ms':1000,'path':'proxy.png','sha256':digest_file(self.root/'proxy.png')}]}]}}}
        self.control['materials_sha256']=digest(self.control['materials'])
        self.brief={'shot_id':'S1','spatial_dependency':{'at_ms':1000}}

    def test_exact_scoped_proxy_is_an_image_host_input_not_identity(self):
        refs=for_panel(self.root,self.control,self.brief)
        self.assertEqual(len(refs),1);self.assertIsNone(refs[0]['entity_id'])
        self.assertIn('not identity',refs[0]['purpose']);self.assertTrue(refs[0]['key'].startswith('CONTROL_'))
        self.assertTrue(binding_valid(self.root,self.control,refs[0]))
        self.assertEqual(for_panel(self.root,self.control,{'shot_id':'S2'}),[])

    def test_nearest_frame_and_other_shot_cannot_substitute(self):
        for brief in ({'shot_id':'S1','spatial_dependency':{'at_ms':1001}}, {'shot_id':'S3'}):
            with self.assertRaises(ValueError):for_panel(self.root,self.control,brief)

    def test_changed_materials_or_frame_invalidates_old_binding(self):
        ref=for_panel(self.root,self.control,self.brief)[0]
        (self.root/'proxy.png').write_bytes(b'changed')
        self.assertFalse(binding_valid(self.root,self.control,ref))
        self.control['materials']['renders']['S1'][0]['frames'][0]['sha256']=digest_file(self.root/'proxy.png')
        with self.assertRaisesRegex(ValueError,'materials changed'):index(self.root,self.control)

    def test_package_change_rejects_old_reference(self):
        (self.root/'control/package-manifest.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError,'package changed'):index(self.root,self.control)

    def test_ambiguous_same_moment_frames_block(self):
        (self.root/'other.png').write_bytes(b'different')
        self.control['materials']['renders']['S1'][0]['frames'].append(
            {'at_ms':1000,'path':'other.png','sha256':digest_file(self.root/'other.png')})
        self.control['materials_sha256']=digest(self.control['materials'])
        with self.assertRaisesRegex(ValueError,'Conflicting'):for_panel(self.root,self.control,self.brief)

    def test_scoped_reference_path_escape_is_rejected(self):
        self.control['materials']['renders']['S1'][0]['frames'][0]['path']='../outside.png'
        self.control['materials_sha256']=digest(self.control['materials'])
        with self.assertRaisesRegex(ValueError,'escapes'):index(self.root,self.control)

    def test_input_binding_checks_reject_omitted_proxy_before_media_probe(self):
        project=self.root/'project';k=V5Kernel.initialize(project,['unit'],control_policy=POLICY)
        media={'path':str(self.root/'proxy.png'),'provider':'provided','call_evidence':{'source':'unit'},
               'sha256':digest_file(self.root/'proxy.png'),'input_bindings':[]}
        ref=for_panel(self.root,self.control,self.brief)[0]
        job={'stage':7,'key':'BOARD_P1','fingerprint':'unit','references':[ref]}
        with patch.object(k,'image_jobs',return_value=[job]),patch.object(k,'prompt_valid',return_value=True),patch.object(k,'check_image_host'):
            with self.assertRaisesRegex(ValueError,'references do not match'):
                k.accept_media({'job':job,'prompt':{}},{'media':media})

    def test_auto_path_rejects_unconsumed_native_video_controls(self):
        k=V5Kernel.initialize(self.root/'project',['unit'],control_policy=POLICY)
        k.adaptive_config_check({'adaptive':{'policy':POLICY},'controls':[{'channel':'keyframe_input'}]})
        for channel in ('clay_video_reference','camera_trajectory','first_frame','image_reference'):
            with self.assertRaisesRegex(ValueError,'explicit joint compiler'):
                k.adaptive_config_check({'adaptive':{'policy':POLICY},'controls':[{'channel':channel}]})

    def test_image_jobs_wires_geometry_before_appearance_references(self):
        import shutil
        k=V5Kernel.initialize(self.root/'project',['fixture'],control_policy=POLICY)
        shutil.copytree(self.root/'control',k.root/'control')
        shutil.copyfile(self.root/'proxy.png',k.root/'proxy.png')
        state=k.state;state['control']=self.control;k.save(state)
        brief={'id':'P1','kind':'board','shot_id':'S1','source_pointer':'/shots/0/panels/0',
               'dependency_paths':[], 'spatial_dependency':{'shot_id':'S1','at_ms':1000,'value':{}}}
        ir={'shots':[{'state_start':{},'panels':[{'subject_ids':[]}]}]}
        with patch.object(k,'data',return_value=ir),patch.object(k,'dependency',return_value={}),patch('ai_comic_drama_workflow.v5.image_briefs',return_value=[brief]):
            job=k.image_jobs(7)[0]
            self.assertTrue(job['references'][0]['key'].startswith('CONTROL_'))
            self.assertEqual(job['references'][0]['uri'],'proxy.png')
            old=job['fingerprint']
            state=k.state;state['control']['materials']['renders']['S1'][0]['frames'][0]['at_ms']=1001
            state['control']['materials_sha256']=digest(state['control']['materials']);k.save(state)
            with self.assertRaisesRegex(ValueError,'exact geometry'):k.image_jobs(7)
