"""Full native build → scoped media lowering → unified prompt/payload → re-verification."""
from pathlib import Path
from copy import deepcopy
import unittest
import shutil
import test_shot_control as fixtures
from shot_control.common import read, write, sha
from shot_control.control_plan import build
from shot_control.control_lowering import lower
from shot_control.joint_compile import compile_package, export, verify_export, scope_for_shots


class JointControlTests(unittest.TestCase):
    setUp = fixtures.ShotControlTests.setUp
    build = fixtures.ShotControlTests.build
    configured = fixtures.ShotControlTests.configured
    artifact = fixtures.ShotControlTests.artifact
    manifest = fixtures.ShotControlTests.manifest

    def test_text_request_has_native_parameters_and_typed_obligations(self):
        self.build()
        result = compile_package(self.out, 'agnes-video-2.5', 'text', self.manifest())
        self.assertEqual(result['status'], 'COMPILED_DRAFT', result['reasons'])
        self.assertTrue(result['complete_project_scope'])
        self.assertEqual(len(result['requests']), 1)
        request = result['requests'][0]
        self.assertEqual(request['payload_draft']['seconds'], '12')
        self.assertEqual(request['payload_draft']['prompt'], request['prompt'])
        rows = {r['requirement_id']: r for r in request['primary_obligations']}
        self.assertEqual(rows['REQ_DURATION']['type'], 'native_parameter')
        self.assertEqual(rows['REQ_CAST']['status'], 'EMITTED')
        self.assertEqual(rows['REQ_LINE']['status'], 'POST_TASK_PLANNED')
        self.assertTrue(request['post_tasks']); self.assertFalse(request['runnable'])
        self.assertEqual(rows['REQ_DURATION']['media_acceptance'], 'NOT_RUN')

    def test_internal_keyframe_cannot_become_whole_project_first_frame(self):
        config, c = self.configured(); manifest = self.manifest(self.artifact(config, c))
        media = lower(self.out, 'agnes-video-2.5', 'keyframe', manifest)
        self.assertEqual(media['status'], 'BLOCKED')
        self.assertTrue(any('INTERNAL_KEYFRAME' in r for r in media['reasons']))
        result = compile_package(self.out, 'agnes-video-2.5', 'keyframe', manifest, ['S2'])
        self.assertEqual(result['status'], 'COMPILED_DRAFT', result['reasons'])
        self.assertFalse(result['complete_project_scope'])
        request = result['requests'][0]
        self.assertEqual(request['scope'], {'start_ms':4000, 'end_ms':8000, 'shot_ids':['S2']})
        self.assertEqual(request['payload_draft']['seconds'], '4')
        self.assertEqual(request['payload_draft']['first_frame'], 'https://example.com/K1.png')
        duration = next(r for r in request['primary_obligations'] if r['requirement_id']=='REQ_DURATION')
        self.assertEqual(duration['evidence'][0]['status'], 'ASSEMBLY_REQUIRED')

    def test_keyframe_boundaries_split_without_dropping_uncovered_parts(self):
        config, c = self.configured(); manifest = self.manifest(self.artifact(config, c))
        result = compile_package(self.out, 'agnes-video-2.5', 'keyframe', manifest)
        self.assertEqual([(r['scope']['start_ms'],r['scope']['end_ms']) for r in result['requests']], [(0,4000),(4000,8000),(8000,12000)])
        self.assertEqual([r['status'] for r in result['requests']], ['BLOCKED','COMPILED_DRAFT','BLOCKED'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_references_payload_and_prompt_share_deduplicated_index(self):
        config, c = self.configured('image_reference', ['A1','A2'])
        a = self.artifact(config, c, 'A1', 'style', 128)
        b = self.artifact(config, c, 'A2', 'style', 128)
        result = compile_package(self.out, 'agnes-video-2.5', 'reference', self.manifest(a,b))
        self.assertEqual(result['status'], 'COMPILED_DRAFT', result['reasons'])
        request = result['requests'][0]
        self.assertEqual(len(request['attachment_index']), 1)
        self.assertEqual(request['payload_draft']['images'], ['https://example.com/A1.png'])
        self.assertIn('<Picture 1>（A1.png）', request['prompt'])
        self.assertIn('<Picture 1>（A2.png）', request['prompt'])
        self.assertNotIn('<Picture 2>', request['prompt'])
        self.assertEqual(request['attachment_index'][0]['artifact_ids'], ['A1','A2'])

    def test_cross_request_url_hash_collision_is_blocked(self):
        controls = []
        for i, sid in enumerate(('S1','S2'), 1):
            controls.append({'id': 'C'+str(i), 'requirement_id':'REQ_CAST','shot_ids':[sid],
                'source_pointers':['/entities'],'channel':'first_frame','artifact_ids':['A'+str(i)],
                'hardness':'hard','fallback_policy':'block','purpose':'supplement'})
        config = {'schema':'shot-control-config/0.2','lenses':{s['id']:self.lens for s in self.ir['shots']},'controls':controls}
        build(self.source,self.out,config)
        a = self.artifact(config,controls[0],'A1',content=100,url='https://example.com/reused.png')
        b = self.artifact(config,controls[1],'A2',content=200,url='https://example.com/reused.png')
        result = compile_package(self.out,'agnes-video-2.5','keyframe',self.manifest(a,b),['S1','S2'])
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(len(result['requests']),2)
        self.assertTrue(all(r['payload_draft'] is None and 'CROSS_REQUEST_URL_CONTENT_CONFLICT' in r['reasons'] for r in result['requests']))

    def test_shared_control_can_select_different_keyframes_per_shot(self):
        c = {'id':'C','requirement_id':'REQ_CAST','shot_ids':['S1','S2'],'source_pointers':['/entities'],
             'channel':'first_frame','artifact_ids':['A1','A2'],'hardness':'hard','fallback_policy':'block','purpose':'supplement'}
        config = {'schema':'shot-control-config/0.2','lenses':{s['id']:self.lens for s in self.ir['shots']},'controls':[c]}
        build(self.source,self.out,config)
        a = self.artifact(config,{**c,'shot_ids':['S1']},'A1',content=100)
        b = self.artifact(config,{**c,'shot_ids':['S2']},'A2',content=200)
        result = compile_package(self.out,'agnes-video-2.5','keyframe',self.manifest(a,b),['S1','S2'])
        self.assertEqual(result['status'],'COMPILED_DRAFT',result['reasons'])
        self.assertEqual([r['payload_draft']['first_frame'] for r in result['requests']],['https://example.com/A1.png','https://example.com/A2.png'])

    def test_native_asset_identity_and_responsibility_share_the_submission_index(self):
        import spatial_runtime as spatial
        c={'id':'C','requirement_id':'REQ_CAST','shot_ids':['S2'],'source_pointers':['/entities'],
           'channel':'image_reference','artifact_ids':['PORTRAIT'],'hardness':'hard','fallback_policy':'block','purpose':'supplement'}
        config={'schema':'shot-control-config/0.2','lenses':{s['id']:self.lens for s in self.ir['shots']},'controls':[c]}
        asset=self.artifact(config,c,'PORTRAIT',role='identity')
        self.ir['assets']=[{'id':'PORTRAIT','kind':'image','filename':'PORTRAIT.png','path':'PORTRAIT.png',
                           'sha256':asset['sha256'],'public_url':None,'inspection':'observed','source_refs':['DESIGN']}]
        self.ir['bindings']=[{'id':'BIND_A','asset_id':'PORTRAIT','target_id':'A','shot_ids':['S2'],
                            'roles':['identity'],'negative_roles':['wardrobe','scene'],'source_refs':['DESIGN']}]
        self.ir['timeline']['semantic_review']['input_sha256']=spatial.content_hash(self.ir)
        source=Path(self.tmp.name)/'source.json';write(source,self.ir)
        shutil.copyfile(self.source.parent/'cafe.source.txt',source.parent/'cafe.source.txt')
        build(source,self.out,config)
        result=compile_package(self.out,'agnes-video-2.5','reference',self.manifest(asset))
        self.assertEqual(result['status'],'COMPILED_DRAFT',result['reasons'])
        prompt=result['requests'][0]['prompt']
        self.assertIn('PORTRAIT.png',prompt);self.assertIn('<Picture 1>',prompt)
        self.assertIn('wardrobe',prompt);self.assertIn('scene',prompt)
        # Same bytes with a different identifier do not silently replace an upstream binding.
        c['artifact_ids']=['ALIAS'];asset['id']='ALIAS'
        second=Path(self.tmp.name)/'unmapped';build(source,second,config)
        blocked=compile_package(second,'agnes-video-2.5','reference',self.manifest(asset))
        self.assertTrue(any('UNMAPPED_SOURCE_ASSET:PORTRAIT' in r for r in blocked['reasons']))

    def test_export_verifies_payload_bytes_against_sources(self):
        self.build(); out=Path(self.tmp.name)/'joint'
        export(self.out,'agnes-video-2.5-flash','text',self.manifest(),out)
        self.assertEqual(verify_export(out)['status'],'VERIFIED')
        request=read(out/'REQUEST_001.json'); request['payload_draft']['seconds']='5'
        write(out/'REQUEST_001.json',request)
        receipt=read(out/'compile-manifest.json');receipt['files']['REQUEST_001.json']=sha(out/'REQUEST_001.json')
        write(out/'compile-manifest.json',receipt)
        with self.assertRaisesRegex(ValueError,'differs'):verify_export(out)

    def test_noncontiguous_selection_is_not_silently_edited(self):
        with self.assertRaisesRegex(ValueError,'contiguous'):scope_for_shots(self.ir,['S1','S3'])
        with self.assertRaisesRegex(ValueError,'Duplicate'):scope_for_shots(self.ir,['S2','S2'])
        with self.assertRaisesRegex(ValueError,'Unknown'):scope_for_shots(self.ir,['FAKE'])

    def test_export_rejects_resealed_boolean_numeric_aliases(self):
        self.build(); out=Path(self.tmp.name)/'joint'
        export(self.out,'agnes-video-2.5','text',self.manifest(),out)
        originals={name:read(out/name) for name in ('REQUEST_001.json','joint-compile.json','compile-manifest.json')}
        self.assertEqual(verify_export(out)['status'],'VERIFIED')
        cases=[('REQUEST_001.json',('submitted',),0),
               ('REQUEST_001.json',('runnable',),0),
               ('REQUEST_001.json',('scope','start_ms'),False),
               ('joint-compile.json',('complete_project_scope',),1),
               ('joint-compile.json',('submitted',),0),
               ('joint-compile.json',('scope','start_ms'),False),
               ('joint-compile.json',('requests',0,'runnable'),0)]
        for name,keys,value in cases:
            with self.subTest(file=name,field=keys):
                for filename,original in originals.items():write(out/filename,original)
                changed=deepcopy(originals[name]); target=changed
                for key in keys[:-1]:target=target[key]
                target[keys[-1]]=value;write(out/name,changed)
                manifest=read(out/'compile-manifest.json');manifest['files'][name]=sha(out/name)
                write(out/'compile-manifest.json',manifest)
                with self.assertRaisesRegex(ValueError,'differs'):verify_export(out)
        # Numeric representation changes remain legal; original boolean states stay booleans.
        for filename,original in originals.items():write(out/filename,original)
        manifest=read(out/'compile-manifest.json')
        for name in ('REQUEST_001.json','joint-compile.json'):
            changed=read(out/name);changed['scope']['start_ms']=0.0
            write(out/name,changed);manifest['files'][name]=sha(out/name)
        write(out/'compile-manifest.json',manifest)
        self.assertEqual(verify_export(out)['status'],'VERIFIED')


if __name__ == '__main__': unittest.main()
