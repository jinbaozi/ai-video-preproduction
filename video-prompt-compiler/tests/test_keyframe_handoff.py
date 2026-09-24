from pathlib import Path
import shutil
import unittest
import test_shot_control as fixtures
from shot_control.common import read, write
from shot_control.control_plan import build
from shot_control.keyframes import check_request


class KeyframeHandoffTests(unittest.TestCase):
    setUp = fixtures.ShotControlTests.setUp
    artifact = fixtures.ShotControlTests.artifact
    manifest = fixtures.ShotControlTests.manifest

    def test_source_bound_identity_scene_and_edit_base_are_required(self):
        import spatial_runtime as spatial
        controls=[]
        for ident, requirement, pointer in [('ID_B','REQ_CAST','/entities'),('SCENE','ART_CAFE','/scenes/0/description')]:
            controls.append({'id':'C_'+ident,'requirement_id':requirement,'source_pointers':[pointer],'shot_ids':['S2'],
                             'channel':'image_reference','artifact_ids':[ident],'hardness':'hard','fallback_policy':'block','purpose':'supplement'})
        config={'schema':'shot-control-config/0.2','lenses':{s['id']:self.lens for s in self.ir['shots']},'controls':controls}
        controls.append({'id':'C_BASE','requirement_id':'REQ_FACE','source_pointers':['/shots/1/camera/shot_size'],'shot_ids':['S2'],
                         'channel':'first_frame','artifact_ids':['BASE'],'hardness':'hard','fallback_policy':'block','purpose':'supplement'})
        identity=self.artifact(config,controls[0],'ID_B',role='identity',content=100)
        scene=self.artifact(config,controls[1],'SCENE',role='scene',content=200)
        base=self.artifact(config,controls[2],'BASE',role='clean_keyframe',content=50)
        base['review'].update(result='FAIL',checks=['Wrong eyeline; explicit edit required'])
        self.ir['assets']=[];self.ir['bindings']=[]
        for a,target,role in [(identity,'B','identity'),(scene,'CAFE','scene')]:
            self.ir['assets'].append({'id':a['id'],'kind':'image','filename':a['path'],'path':a['path'],'sha256':a['sha256'],
                                      'public_url':None,'inspection':'observed','source_refs':['DESIGN']})
            self.ir['bindings'].append({'id':'BIND_'+a['id'],'asset_id':a['id'],'target_id':target,'shot_ids':['S2'],
                                        'roles':[role],'negative_roles':[],'source_refs':['DESIGN']})
        self.ir['timeline']['semantic_review']['input_sha256']=spatial.content_hash(self.ir)
        source=Path(self.tmp.name)/'source.json';write(source,self.ir)
        shutil.copyfile(self.source.parent/'cafe.source.txt',source.parent/'cafe.source.txt')
        build(source,self.out,config);manifest=self.manifest(identity,scene,base)
        request=next(r for r in read(self.out/'keyframe-requests.json') if r['shot_id']=='S2' and r['at_ms']==4000)
        request.update(master_anchors=['ID_B','SCENE'],generation_mode='generate')
        result=check_request(request,self.out,manifest)
        self.assertEqual(result['reasons'],[])
        from shot_control.common import digest
        from shot_control.package import recipe
        from copy import deepcopy
        original=deepcopy(identity)
        for start,end in [(9000,10000),(5000,4000)]:
            identity['uses'][0].update(start_ms=start,end_ms=end,
                recipe_sha256=recipe(self.ir,config,controls[0],'S2','identity',start,end))
            identity['review']['uses_sha256']=digest(identity['uses']);self.manifest(identity,scene,base)
            self.assertIn('ANCHOR_TIME_SCOPE:ID_B',check_request(request,self.out,manifest)['reasons'])
        identity=original;self.manifest(identity,scene,base)
        request['master_anchors']=['SCENE']
        self.assertIn('IDENTITY_MASTER_REQUIRED:B',check_request(request,self.out,manifest)['reasons'])
        request['master_anchors']=['ID_B']
        self.assertIn('SCENE_MASTER_REQUIRED:CAFE',check_request(request,self.out,manifest)['reasons'])
        request.update(master_anchors=['ID_B','SCENE'],generation_mode='edit',base_asset_id='ID_B')
        request['edit_delta']={'schema':'edit-delta/0.1','keyframe_id':request['id'],'source':request['source'],
          'base_asset_sha256':identity['sha256'],'master_anchor_ids':['ID_B','SCENE'],
          'allow_changes':['/B/head/gaze'],'preserve':['/B/identity','/scene'],'acceptance':['Synthetic handoff only']}
        self.assertEqual(check_request(request,self.out,manifest)['reasons'],[])
        request['edit_delta']['base_asset_sha256']='0'*64
        self.assertIn('EDIT_DELTA_BINDING_MISMATCH',check_request(request,self.out,manifest)['reasons'])
        request.update(base_asset_id='BASE')
        request['edit_delta']['base_asset_sha256']=base['sha256']
        self.assertEqual(check_request(request,self.out,manifest)['reasons'],[])
        base['review']['uses_sha256']='0'*64;self.manifest(identity,scene,base)
        self.assertIn('ANCHOR_REVIEW_REQUIRED:BASE',check_request(request,self.out,manifest)['reasons'])
        base['review']=None;self.manifest(identity,scene,base)
        self.assertIn('ANCHOR_REVIEW_REQUIRED:BASE',check_request(request,self.out,manifest)['reasons'])
        request['edit_delta']=None
        self.assertIn('EDIT_BASE_AND_DELTA_REQUIRED',check_request(request,self.out,manifest)['reasons'])
        identity['review']['result']='FAIL';self.manifest(identity,scene,base)
        self.assertIn('ANCHOR_REVIEW_REQUIRED:ID_B',check_request(request,self.out,manifest)['reasons'])


if __name__=='__main__':unittest.main()
