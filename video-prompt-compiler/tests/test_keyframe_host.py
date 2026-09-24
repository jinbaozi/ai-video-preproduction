"""Full native source and actual PNGs; host/visual claims here are synthetic fixtures."""
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import unittest

import test_shot_control as fixtures
from shot_control.common import read, sha, write
from shot_control.control_plan import build
from shot_control.keyframe_host import stage, receive, verify_stage, verify_received


class KeyframeHostTests(unittest.TestCase):
    setUp = fixtures.ShotControlTests.setUp
    artifact = fixtures.ShotControlTests.artifact
    manifest = fixtures.ShotControlTests.manifest

    def prepare(self, edit=False):
        import spatial_runtime as spatial
        root = Path(self.tmp.name)
        controls = []
        for ident, req, pointer, channel in [('ID_B','REQ_CAST','/entities','image_reference'),
                ('SCENE','ART_CAFE','/scenes/0/description','image_reference'),
                ('K','REQ_FACE','/shots/1/camera/shot_size','first_frame')]:
            controls.append({'id':'C_'+ident, 'requirement_id':req, 'source_pointers':[pointer], 'shot_ids':['S2'],
                             'channel':channel, 'artifact_ids':[ident], 'hardness':'hard', 'fallback_policy':'block', 'purpose':'supplement'})
        config = {'schema':'shot-control-config/0.2', 'lenses':{s['id']:self.lens for s in self.ir['shots']}, 'controls':controls}
        identity = self.artifact(config, controls[0], 'ID_B', role='identity', content=50)
        scene = self.artifact(config, controls[1], 'SCENE', role='scene', content=100)
        base = self.artifact(config, controls[2], 'K', content=200)
        base['review']['result'] = 'FAIL'
        self.ir['assets'] = []; self.ir['bindings'] = []
        for a, target, role in [(identity,'B','identity'), (scene,'CAFE','scene')]:
            self.ir['assets'].append({'id':a['id'], 'kind':'image', 'filename':a['path'], 'path':a['path'],
                'sha256':a['sha256'], 'public_url':None, 'inspection':'observed', 'source_refs':['DESIGN']})
            self.ir['bindings'].append({'id':'B_'+a['id'], 'asset_id':a['id'], 'target_id':target, 'shot_ids':['S2'],
                                       'roles':[role], 'negative_roles':[], 'source_refs':['DESIGN']})
        self.ir['timeline']['semantic_review']['input_sha256'] = spatial.content_hash(self.ir)
        write(root/'source.json', self.ir)
        shutil.copyfile(self.source.parent/'cafe.source.txt', root/'cafe.source.txt')
        build(root/'source.json', self.out, config)
        manifest = self.manifest(identity, scene, base)
        request = next(r for r in read(self.out/'keyframe-requests.json') if r['shot_id']=='S2' and r['at_ms']==4000)
        request.update(master_anchors=['ID_B','SCENE'], generation_mode='generate')
        if edit:
            request.update(generation_mode='edit', base_asset_id='K', edit_delta={'schema':'edit-delta/0.1',
                'keyframe_id':request['id'], 'source':request['source'], 'base_asset_sha256':base['sha256'],
                'master_anchor_ids':['ID_B','SCENE'], 'allow_changes':['/B/gaze'], 'preserve':['/B/identity'],
                'acceptance':['Changed eyeline only']})
        write(root/'request.json', request); (root/'prompt.txt').write_text('Synthetic host test only.\n', encoding='utf-8')
        self.staged = root/'stage'
        stage(self.out, root/'request.json', manifest, root/'prompt.txt', 'K', self.staged)
        self.media = root/'actual.png'
        subprocess.run(['ffmpeg','-v','error','-i',str(root/'K.png'),'-vf','scale=320:180','-frames:v','1',str(self.media)], check=True)
        frozen = read(self.staged/'stage.json')
        self.host = {'schema':'keyframe-host-result/0.1', 'stage_sha256':sha(self.staged/'stage-manifest.json'),
            'prompt_sha256':frozen['prompt_sha256'], 'input_sha256':[i['sha256'] for i in frozen['inputs']],
            'output_filename':self.media.name, 'output_sha256':sha(self.media), 'host':'synthetic test',
            'model':None, 'execution_id':None, 'evidence':'No image model was executed', 'recording_mode':'synthetic_test'}
        self.host_path = root/'host.json'; write(self.host_path, self.host)
        self.review = {'schema':'keyframe-image-review/0.1', 'stage_sha256':self.host['stage_sha256'],
            'sha256':sha(self.media), 'reviewer':'synthetic fixture', 'checks':[{'criterion':c, 'result':'PASS',
            'evidence':'Synthetic positive assertion; no quality claim'} for c in dict.fromkeys(request['acceptance']+(request.get('edit_delta') or {}).get('acceptance',[]))]}
        self.review_path = root/'review.json'; write(self.review_path, self.review)

    def test_pending_receive_is_portable_and_never_invents_review_or_upload(self):
        self.prepare()
        root = Path(self.tmp.name); out = root/'received'
        receive(self.staged, self.media, self.host_path, out)
        artifact = read(out/'artifact-manifest.json')['artifacts'][-1]
        self.assertIsNone(artifact['review']); self.assertIsNone(artifact['binding'])
        self.assertEqual(artifact['uses'][0]['start_ms'],4000)
        self.assertEqual(artifact['uses'][0]['end_ms'],4000)
        self.assertEqual(read(out/'receipt.json')['media']['width'],320)
        # Copy is self-contained and source edits cannot silently alter it.
        moved = root/'moved'; shutil.move(out,moved); shutil.rmtree(self.staged); shutil.rmtree(self.out)
        self.assertEqual(verify_received(moved)['visual_review'],'NOT_RUN')

    def test_order_and_output_hash_mismatch_leave_no_half_package(self):
        self.prepare(edit=True)
        frozen = verify_stage(self.staged)
        self.assertEqual([i['asset_id'] for i in frozen['inputs']],['K','ID_B','SCENE'])
        for key, value in [('input_sha256',list(reversed(self.host['input_sha256']))),('output_sha256','0'*64),('stage_sha256','0'*64)]:
            bad = {**self.host,key:value}; write(self.host_path,bad)
            out = Path(self.tmp.name)/('bad-'+key)
            with self.assertRaises(ValueError): receive(self.staged,self.media,self.host_path,out)
            self.assertFalse(out.exists())
        with self.assertRaisesRegex(ValueError,'inside'): receive(self.staged,self.media,self.host_path,self.staged/'nested')

    def test_every_criterion_required_and_fail_unknown_pass_remain_distinct(self):
        self.prepare(edit=True)
        original = deepcopy(self.review)
        for result in ['FAIL','UNDETERMINED','PASS']:
            self.review = deepcopy(original); self.review['checks'][-1]['result']=result
            write(self.review_path,self.review); out=Path(self.tmp.name)/result
            receive(self.staged,self.media,self.host_path,out,self.review_path)
            self.assertEqual(verify_received(out)['visual_review'],result)
            a=read(out/'artifact-manifest.json')['artifacts'][-1]
            self.assertIsNone(a['binding'])
            if result=='UNDETERMINED': self.assertIsNone(a['review'])
            else: self.assertEqual(a['review']['result'],result)
        self.review['checks'].pop(); write(self.review_path,self.review)
        with self.assertRaisesRegex(ValueError,'every frozen'): receive(self.staged,self.media,self.host_path,Path(self.tmp.name)/'missing',self.review_path)

    def test_resealed_output_review_and_input_tampering_is_rejected(self):
        self.prepare()
        out=Path(self.tmp.name)/'received';receive(self.staged,self.media,self.host_path,out)
        a=read(out/'artifact-manifest.json');a['artifacts'][-1]['binding']={'sha256':sha(self.media),'url':'https://example.com/x','receipt':'invented'}
        write(out/'artifact-manifest.json',a)
        seal=read(out/'received-manifest.json');seal['files']['artifact-manifest.json']=sha(out/'artifact-manifest.json');write(out/'received-manifest.json',seal)
        with self.assertRaisesRegex(ValueError,'derivation differs'):verify_received(out)
        (self.staged/'prompt.txt').write_text('Changed after freeze')
        with self.assertRaisesRegex(ValueError,'differs'):verify_stage(self.staged)

    def test_wrong_image_aspect_cannot_be_promoted_by_pass_assertions(self):
        self.prepare()
        shutil.copyfile(Path(self.tmp.name)/'K.png',self.media)
        self.host['output_sha256']=sha(self.media);write(self.host_path,self.host)
        self.review['sha256']=sha(self.media);write(self.review_path,self.review)
        out=Path(self.tmp.name)/'aspect';receive(self.staged,self.media,self.host_path,out,self.review_path)
        self.assertEqual(verify_received(out)['visual_review'],'FAIL')
        self.assertIn('OUTPUT_ASPECT_MISMATCH',read(out/'receipt.json')['technical_issues'])


if __name__=='__main__':unittest.main()
