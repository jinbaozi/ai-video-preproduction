from pathlib import Path
import unittest
import subprocess
import test_shot_control as fixtures
from shot_control.common import read, write, sha, digest
from shot_control.control_plan import build
from shot_control.control_lowering import lower
from shot_control.repair import plan_repairs, export


class ControlRepairTests(unittest.TestCase):
    setUp = fixtures.ShotControlTests.setUp
    configured = fixtures.ShotControlTests.configured
    artifact = fixtures.ShotControlTests.artifact
    manifest = fixtures.ShotControlTests.manifest

    def changed_lens(self, config):
        changed=read(self.out/'control-config.json');changed['lenses']['S2']['vertical_fov_deg']=70
        out=Path(self.tmp.name)/'changed';build(self.source,out,changed)
        return out

    def test_camera_change_invalidates_only_affected_shot_assets_and_jobs(self):
        c={'id':'C','requirement_id':'REQ_CAST','shot_ids':['S1','S2'],'source_pointers':['/entities'],
           'channel':'first_frame','artifact_ids':['A1','A2'],'hardness':'hard','fallback_policy':'block','purpose':'supplement'}
        config={'schema':'shot-control-config/0.2','lenses':{s['id']:self.lens for s in self.ir['shots']},'controls':[c]}
        build(self.source,self.out,config)
        a=self.artifact(config,{**c,'shot_ids':['S1']},'A1',content=100)
        b=self.artifact(config,{**c,'shot_ids':['S2']},'A2',content=200)
        manifest=self.manifest(a,b);before_bytes=manifest.read_bytes()
        changed=self.changed_lens(config);destination=Path(self.tmp.name)/'repair'
        result=export(self.out,changed,manifest,destination)
        self.assertEqual(result['status'],'REPAIR_REQUIRED')
        self.assertEqual(manifest.read_bytes(),before_bytes)
        plan=read(destination/'repair-plan.json')
        uses={n['artifact_id']:n for n in plan['graph']['nodes'] if n['kind']=='artifact_use'}
        self.assertEqual(uses['A1']['status'],'RETAINED');self.assertEqual(uses['A2']['status'],'INVALIDATED')
        shots={n['shot_id']:n['status'] for n in plan['graph']['nodes'] if n['kind']=='planned_shot_output'}
        self.assertEqual(shots,{'S1':'RETAINED','S2':'INVALIDATED','S3':'RETAINED'})
        self.assertTrue(list((destination/'tasks').glob('*.json')))
        new_manifest=destination/'artifact-manifest.json'
        self.assertEqual(lower(changed,'agnes-video-2.5','keyframe',new_manifest,{'start_ms':0,'end_ms':4000})['status'],'BOUND_DRAFT')
        failed=lower(changed,'agnes-video-2.5','keyframe',new_manifest,{'start_ms':4000,'end_ms':8000})
        self.assertIn('C:ASSET_USE_INVALIDATED:A2',failed['reasons'])
        self.assertEqual(sha(destination/'assets/A1.png'),a['sha256'])
        self.assertFalse(plan['upstream_modified'])

    def test_identity_master_survives_camera_revision(self):
        config,c=self.configured('image_reference');a=self.artifact(config,c,role='identity')
        manifest=self.manifest(a);changed=self.changed_lens(config)
        result=plan_repairs(self.out,changed,manifest)
        use=next(n for n in result['graph']['nodes'] if n['kind']=='artifact_use')
        self.assertEqual(use['status'],'RETAINED')
        self.assertEqual(result['updated_artifacts']['invalidated_uses'],[])
        self.assertTrue(any(t['owner']=='image-optimizer' for t in result['tasks']))

    def test_failed_observed_output_creates_scoped_jobs_without_discarding_master(self):
        from shot_control.package import verify_package
        config,c=self.configured('image_reference');a=self.artifact(config,c,role='identity');manifest=self.manifest(a)
        baseline=verify_package(self.out)['evaluation'];video=Path(self.tmp.name)/'observed.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=320x180:r=24:d=12','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
        observations=Path(self.tmp.name)/'observations.json'
        write(observations,{'schema':'control-media-review/0.2','media_sha256':sha(video),'reviewer':'synthetic failure fixture',
              'evaluation_plan_sha256':digest(baseline),'observed_points':[],'events':[],
              'findings':[{'dimension':'camera','start_ms':4000,'end_ms':8000,'result':'FAIL','issue':'No planned composition in synthetic video',
                           'owner':'video-compiler','source_pointers':['/shots/1/camera']}]})
        result=plan_repairs(self.out,self.out,manifest,observations,video)
        self.assertEqual(result['status'],'REPAIR_REQUIRED');self.assertEqual(len(result['tasks']),1)
        self.assertEqual(result['tasks'][0]['scope'],{'start_ms':4000,'end_ms':8000})
        self.assertEqual(result['output_invalidations'][0]['media_sha256'],sha(video))
        self.assertEqual(result['updated_artifacts']['invalidated_uses'],[])
        self.assertEqual(result['evaluation']['status'],'OBSERVATIONS_RECORDED')

    def test_unchanged_package_creates_no_repair_jobs(self):
        config,c=self.configured('image_reference');manifest=self.manifest(self.artifact(config,c,role='identity'))
        result=plan_repairs(self.out,self.out,manifest)
        self.assertEqual(result['status'],'UNCHANGED');self.assertEqual(result['tasks'],[])
        self.assertTrue(all(n['status']=='RETAINED' for n in result['graph']['nodes']))

    def test_regenerated_reviewed_content_retires_only_old_invalidation(self):
        config,c=self.configured();old=self.artifact(config,c,content=100);new=self.artifact(config,c,content=200)
        manifest=self.manifest(new);data=read(manifest)
        data['invalidated_uses']=[{'artifact_id':'K1','artifact_sha256':old['sha256'],'use_sha256':digest(old['uses'][0]),'reason':'Old content defect','task_id':'OLD'}]
        write(manifest,data)
        self.assertEqual(lower(self.out,'agnes-video-2.5','keyframe',manifest,{'start_ms':4000,'end_ms':8000})['status'],'BOUND_DRAFT')

    def test_preexisting_invalidation_cannot_be_erased_by_repair(self):
        config,c=self.configured();a=self.artifact(config,c);manifest=self.manifest(a)
        data=read(manifest);data['invalidated_uses']=[{'artifact_id':'K1','artifact_sha256':a['sha256'],'use_sha256':digest(a['uses'][0]),'reason':'Observed defect','task_id':'OLD'}]
        write(manifest,data)
        result=plan_repairs(self.out,self.out,manifest)
        self.assertEqual(result['updated_artifacts']['invalidated_uses'],data['invalidated_uses'])
        self.assertEqual(result['status'],'REPAIR_REQUIRED')
        media=lower(self.out,'agnes-video-2.5','keyframe',manifest,{'start_ms':4000,'end_ms':8000})
        self.assertIn('C1:ASSET_USE_INVALIDATED:K1',media['reasons'])


if __name__=='__main__':unittest.main()
