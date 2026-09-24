import copy
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_previs_example import fixture
from shot_control.common import read, write, digest
from shot_control.control_plan import build
from shot_control.package import verify_package, recipe
from shot_control.previs import derive, render, verify_render, validate_geometry
from shot_control.control_lowering import lower


class PrevisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.ir,self.config=fixture()
        self.config['proxy_scene']['fps']=2; self.config['proxy_scene']['resolution']=[320,180]
        shutil.copyfile(ROOT/'examples/v52/cafe.source.txt',self.root/'cafe.source.txt')

    def package(self):
        write(self.root/'source.json',self.ir)
        build(self.root/'source.json',self.root/'package',self.config)
        return self.root/'package'

    def test_native_source_timing_geometry_and_missing_interpolation(self):
        package=self.package(); bundle=verify_package(package); plan=derive(bundle,'S1')
        self.assertEqual(len(plan['video_samples']),8)
        self.assertEqual(plan['samples'][plan['event_samples'][-1]]['at_ms'],4000)
        self.assertEqual(plan['samples'][plan['video_samples'][-1]]['at_ms'],3500)
        self.assertEqual(plan['fidelity'],'EXPLICIT_GEOMETRY_ONLY')
        self.assertEqual(plan['geometry']['basis'],'authored_proxy')
        broken=copy.deepcopy(bundle)
        track=next(t for t in broken['ir']['timeline']['motion_tracks'] if t['id']=='POS_S1_ENVELOPE')
        track['keyframes'][0]['transition']='none'
        with self.assertRaisesRegex(ValueError,'Unknown position'): derive(broken,'S1')
        with self.assertRaisesRegex(ValueError,'Explicit proxy'): derive(bundle,'S2')

    def test_geometry_is_not_another_motion_authority(self):
        geometry=self.config['proxy_scene']; geometry['objects'][0]['trajectory']=[[0,0,0],[1,0,0]]
        with self.assertRaises(ValueError): validate_geometry(self.ir,geometry)
        del geometry['objects'][0]['trajectory']; geometry['objects'][0]['node_id']='MISSING'
        with self.assertRaisesRegex(ValueError,'Unknown'): validate_geometry(self.ir,geometry)

    def test_unresolved_orientation_and_incorrect_aspect_block(self):
        bundle=verify_package(self.package())
        bundle['config']['proxy_scene']['objects'][0]['orientation']='node_direction'
        with self.assertRaisesRegex(ValueError,'Unknown world orientation'): derive(bundle,'S1')
        bundle['config']['proxy_scene']['objects'][0]['orientation']='world_axes'
        bundle['config']['proxy_scene']['resolution']=[180,320]
        with self.assertRaisesRegex(ValueError,'aspect'): derive(bundle,'S1')

    def test_geometry_change_invalidates_clay_but_preserves_master(self):
        c=self.config['controls'][0]
        clay=recipe(self.ir,self.config,c,'S1','clay',0,4000)
        master_control={**c,'channel':'image_reference'}
        master=recipe(self.ir,self.config,master_control,'S1','identity',0,4000)
        other=recipe(self.ir,self.config,c,'S2','clay',4000,8000)
        self.config['proxy_scene']['objects'][0]['dimensions'][1]+=.1
        self.assertNotEqual(recipe(self.ir,self.config,c,'S1','clay',0,4000),clay)
        self.assertEqual(recipe(self.ir,self.config,master_control,'S1','identity',0,4000),master)
        self.assertEqual(recipe(self.ir,self.config,c,'S2','clay',4000,8000),other)

    @unittest.skipUnless(os.environ.get('BLENDER_EXECUTABLE'),'Requires explicit local Blender integration runtime')
    def test_actual_blender_reopened_scene_render_and_pending_handoff(self):
        # Exercise portrait, off-centre crop and roll through Blender's real projection.
        self.ir['output']['aspect_ratio']='9:16'
        for lens in self.config['lenses'].values():lens.update(aspect=9/16)
        self.config['lenses']['S1'].update(crop=[.1,.2,.8,.8])
        next(c for c in self.ir['contract'] if c['id']=='REQ_DURATION')['checks'][0]['value']['aspect_ratio']='9:16'
        self.config['proxy_scene']['resolution']=[180,320]
        self.ir['shots'][0]['camera']['roll_deg']=12
        self.config['proxy_scene']['objects'].append({'id':'TEST_LINK','shape':'bone','node_id':'N_A','end_node_id':'N_B',
            'shot_ids':['S1'],'radius':.015,'evidence':'Synthetic link for endpoint verification, not anatomy'})
        direction=copy.deepcopy(next(t for t in self.ir['timeline']['motion_tracks'] if t['id']=='POS_S1_A'))
        direction.update(id='TEST_DIRECTION',property='orientation',unit='unitless')
        for k in direction['keyframes']: k['value'].update(value=[1,0,0],description='Synthetic numeric orientation')
        self.ir['timeline']['motion_tracks'].append(direction)
        self.config['proxy_scene']['objects'][0]['orientation']='node_direction'
        package=self.package(); out=self.root/'render'
        result=render(package,'S1',out,os.environ['BLENDER_EXECUTABLE'])
        self.assertEqual(result['status'],'RENDERED_LOCAL')
        self.assertLess(result['projection_check']['max_normalized_projection_error'],1e-5)
        self.assertEqual(verify_render(out)['status'],'VERIFIED_LOCAL_RENDER')
        self.assertEqual(read(out/'blender-readback.json')['renderer']['readback'],'REOPENED_BLEND')
        manifest=read(out/'artifact-manifest.json')
        self.assertIsNone(manifest['artifacts'][0]['review'])
        lowered=lower(package,'agnes-video-2.5','reference',out/'artifact-manifest.json',{'start_ms':0,'end_ms':4000})
        self.assertEqual(lowered['status'],'BLOCKED')
        self.assertTrue(any('VISUAL_REVIEW_REQUIRED' in s for s in lowered['reasons']))
        with (out/'clay.mp4').open('ab') as f:f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):verify_render(out)


if __name__=='__main__':unittest.main()
