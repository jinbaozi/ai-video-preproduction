from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from vpc_core import canonical_count, compile_ir, context_view, digest, profile, read, schema_errors, validate
from vpc import run_compile, verify


class CompilerTests(unittest.TestCase):
    def setUp(self):
        self.ir=read(ROOT/'examples/teahouse.avir.json')
        self.base=ROOT/'examples'
        self.tmp=tempfile.TemporaryDirectory(prefix='vpc-test-')
        self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)

    def compile(self,target='agnes-video-2.5',mode='text'):
        return compile_ir(self.ir,profile(target),mode,self.base)[0]

    def codes(self):
        return {x['code'] for x in validate(self.ir,self.base)}

    def test_strict_schema_rejects_unknown_fields(self):
        self.ir['output']['fps']=60
        self.assertIn('E_SCHEMA',self.codes())

    def test_all_verified_targets_preserve_post_dialogue_and_contract(self):
        for target in ('seedance2.0','seedance2.5','agnes-video-2.5','agnes-video-2.5-flash','kling-v3','kling-v3-omni','minimax-h3','veo3.1'):
            with self.subTest(target=target):
                a=self.compile(target)
                self.assertEqual(a['status'],'COMPILED')
                self.assertIn('林岚：“你终于来了。”',a['prompt'])
                self.assertIn('4.5–6.8秒',a['prompt'])
                self.assertIn('口型',a['prompt'])
                self.assertEqual(a['counts']['native_count'],None)
                self.assertFalse(a['execution']['submitted'])
                self.assertEqual({c['id'] for c in self.ir['contract']},{c['id'] for c in a['coverage']})
                self.assertTrue(all(c['realization']=='NOT_RUN' for c in a['coverage']))
                for c in self.ir['contract']:
                    if c['channel']!='post':self.assertIn(c['requirement'],a['prompt'])
                self.assertFalse(schema_errors(a,'compile-artifact'))

    def test_agnes_lifts_seconds_and_forbids_diffusion_params(self):
        a=self.compile()
        self.assertEqual(a['payload_draft']['seconds'],'8')
        self.assertEqual(a['payload_draft']['size'],'720P')
        self.assertNotIn('duration',a['payload_draft'])
        self.assertNotIn('fps',a['payload_draft'])

    def test_native_audio_respects_evidence(self):
        self.ir=read(ROOT/'examples/native-dialogue.avir.json')
        self.assertEqual(self.compile('kling-v3')['status'],'COMPILED')
        a=self.compile()
        self.assertEqual(a['status'],'BLOCKED')
        self.assertIn('E_AUDIO_UNVERIFIED',{d['code'] for d in a['diagnostics']})

    def test_terminal_spatial_relationship(self):
        self.ir['shots'][1]['end_state'][0]['position'][0]=1.5
        self.assertIn('E_SPATIAL',self.codes())

    def test_continuity_ownership_and_axis(self):
        self.ir['shots'][1]['start_state'][0]['holding']=['CUP']
        self.ir['shots'][1]['camera']['axis_side']='B'
        self.assertTrue({'E_CONTINUITY','E_AXIS','E_CONSTRAINT'}<=self.codes())
        self.ir['shots'][0]['start_state'][1]['holding']=['CUP']
        self.assertIn('E_OWNERSHIP',self.codes())

    def test_invisible_micro_expression(self):
        self.ir['shots'][1]['camera']['shot_size']='wide'
        self.assertIn('E_MICRO_VISIBILITY',self.codes())
        self.ir['shots'][1]['start_state'][0]['visible_parts']=['back']
        self.assertIn('E_PERFORMANCE_VISIBILITY',self.codes())

    def test_timeline_and_audio_boundary(self):
        self.ir['shots'][1]['start_ms']=3900
        self.ir['audio']['utterances'][0]['end_ms']=8200
        self.assertTrue({'E_TIMELINE','E_AUDIO_TIME'}<=self.codes())

    def test_sources_hard_contract_and_unknown_pointer(self):
        self.ir['contract'][0]['source_refs']=['UNDEFINED']
        self.ir['contract'][1]['checks'][0]['path']='/absent'
        self.ir['contract'][2]['on_unsupported']='warn'
        self.assertTrue({'E_SOURCE','E_CONSTRAINT','E_HARD_LOSS'}<=self.codes())

    def test_duration_and_flash_resolution_no_silent_coercion(self):
        self.ir['output']['resolution']='1080P'
        a=self.compile('agnes-video-2.5-flash')
        self.assertEqual(a['status'],'BLOCKED')
        self.assertEqual(a['parameters']['size'],'1080P')
        self.assertIsNone(a['payload_draft'])

    def test_unknown_capability_and_edit_are_blocked(self):
        self.assertEqual(self.compile('wan3.0')['status'],'BLOCKED')
        self.assertEqual(self.compile('runway-gen4.5')['status'],'BLOCKED')
        self.assertEqual(self.compile('seedance2.5','edit')['status'],'BLOCKED')
        with self.assertRaises(ValueError):profile('kling')

    def test_budget_never_truncates(self):
        before=self.compile()['prompt']
        self.ir['policy']['max_canonical_units']=5
        a=self.compile()
        self.assertEqual(a['prompt'],before)
        self.assertEqual(a['status'],'BLOCKED')
        self.assertIn('E_BUDGET',{d['code'] for d in a['diagnostics']})

    def test_cpt_is_not_native_token(self):
        self.assertEqual(canonical_count('林岚 Hello_world 42!'),5)

    def test_context_is_pure_and_proposals_are_not_emitted(self):
        self.ir['expansions']=[{'id':'X1','shot_id':'S1','text':'新角色突然进入','origin':'optimizer','invented':True,'disposition':'proposed','source_refs':['DESIGN'],'decision_ref':None}]
        original=digest(self.ir)
        view=context_view(self.ir)
        self.assertEqual(len(view['shots'][0]['style']),2)
        self.assertEqual(digest(self.ir),original)
        self.assertNotIn('新角色突然进入',self.compile()['prompt'])
        self.ir['expansions'][0]['disposition']='accepted'
        self.assertIn('E_INVENTION',self.codes())

    def test_optional_context_fallback(self):
        expected=self.compile()['prompt'];self.ir['policy']['context_ir']='optional'
        a=self.compile();self.assertEqual(a['prompt'],expected)
        self.assertIn('W_OPTIMIZER_FALLBACK',{d['code'] for d in a['diagnostics']})

    def attach(self,count=1,kind='image'):
        # Synthetic bytes exercise binding/hash logic only, never visual QA.
        for n in range(count):
            p=self.out/f'fixture-{n}.png';p.write_bytes(f'test-{n}'.encode())
            aid=f'IMG{n}'
            self.ir['assets'].append({'id':aid,'kind':kind,'filename':p.name,'path':str(p),'sha256':sha256(p.read_bytes()).hexdigest(),'public_url':f'https://assets.example.org/{p.name}','inspection':'observed','source_refs':['BRIEF']})
            self.ir['bindings'].append({'id':f'B{n}','asset_id':aid,'target_id':'LIN','shot_ids':['S1','S2'],'roles':['style'] if n else ['identity'],'negative_roles':['camera','scene'],'source_refs':['BRIEF']})

    def test_binding_numbering_dedup_and_negative_roles(self):
        self.attach()
        duplicate=deepcopy(self.ir['bindings'][0]);duplicate['id']='SECOND';duplicate['roles']=['wardrobe'];self.ir['bindings'].append(duplicate)
        a=self.compile(mode='reference')
        self.assertEqual(a['status'],'COMPILED')
        self.assertEqual(len(a['payload_draft']['images']),1)
        self.assertEqual(a['asset_bindings'][0]['native_slot'],'<Picture 1>')
        self.assertIn('fixture-0.png',a['prompt'])
        self.assertIn('禁止继承 camera、scene',a['prompt'])
        self.ir['bindings'][0]['negative_roles'].append('identity')
        self.assertIn('E_ROLE_CONFLICT',self.codes())

    def test_missing_and_changed_reference(self):
        self.ir=read(ROOT/'examples/missing-reference.avir.json')
        self.assertEqual(self.compile(mode='reference')['status'],'BLOCKED')
        self.ir=read(ROOT/'examples/teahouse.avir.json');self.attach()
        Path(self.ir['assets'][0]['path']).write_bytes(b'changed')
        self.assertIn('E_ASSET_HASH',{d['code'] for d in self.compile(mode='reference')['diagnostics']})

    def test_keyframe_mode_exclusive(self):
        self.attach();self.ir['bindings'][0]['roles']=['first_frame']
        a=self.compile(mode='keyframe')
        self.assertIn('first_frame',a['payload_draft'])
        self.assertNotIn('images',a['payload_draft'])
        self.assertEqual(self.compile(mode='reference')['status'],'BLOCKED')
        self.assertEqual(self.compile(mode='text')['status'],'BLOCKED')

    def test_agnes_video_object_and_flash_rejection(self):
        self.attach(kind='video');self.ir['bindings'][0]['roles']=['motion']
        a=self.compile(mode='reference')
        self.assertIsInstance(a['payload_draft']['videos'][0],dict)
        self.assertEqual(self.compile('agnes-video-2.5-flash','reference')['status'],'BLOCKED')

    def test_hard_scope_and_reference_authority(self):
        self.attach(2)
        self.ir['bindings'][1]['roles']=['identity']
        self.assertIn('E_REF_AUTHORITY',self.codes())

    def test_reference_limit_square_resolution_and_internal_voice(self):
        self.attach(6)
        for b,role in zip(self.ir['bindings'],['identity','style','wardrobe','pacing','motion','voice']):b['roles']=[role]
        self.assertIn('E_REF_LIMIT',{d['code'] for d in self.compile('agnes-video-2.5-flash','reference')['diagnostics']})
        self.ir=read(ROOT/'examples/teahouse.avir.json');self.ir['output']['resolution']='1K'
        self.assertIn('E_AGNES_SQUARE',{d['code'] for d in self.compile()['diagnostics']})
        self.ir['shots'][0]['performance'][0]['psychology']['audibility']='internal_voice'
        self.assertIn('E_INTERNAL_VOICE',self.codes())

    def test_source_content_hash_and_expansion_trace(self):
        self.ir['sources'][0]['sha256']='0'*64
        self.assertIn('E_SOURCE_HASH',self.codes())
        self.ir=read(ROOT/'examples/teahouse.avir.json')
        self.ir['policy']['allow_semantic_invention']=True
        self.ir['expansions']=[{'id':'X1','shot_id':'S1','text':'光线在白瓷杯沿呈现柔和反射','origin':'optimizer','invented':True,'disposition':'accepted','source_refs':['DESIGN'],'decision_ref':'DESIGN'}]
        a=self.compile()
        row=next(t for t in a['trace'] if '光线在白瓷杯沿' in t['text'])
        self.assertIn('/expansions/0',row['ir_paths'])
        self.assertIn('DESIGN',row['source_refs'])

    def test_manifest_replay_and_mutation_detection(self):
        out=self.out/'a';out2=self.out/'b'
        run_compile(self.ir,'agnes-video-2.5','text',self.base,out)
        m=verify(out)
        run_compile(self.ir,'agnes-video-2.5','text',self.base,out2)
        self.assertEqual(m['artifact_hash'],verify(out2)['artifact_hash'])
        with self.assertRaises(ValueError):run_compile(self.ir,'agnes-video-2.5','text',self.base,out)
        (out/'prompt.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError,'E_PACKAGE_CHANGED'):verify(out)

    def test_batch_keeps_valid_jobs_after_failure(self):
        job=self.out/'jobs.ndjson'
        job.write_text('\n'.join(json.dumps({'input':str(self.base/'teahouse.avir.json'),'target':x}) for x in ('missing','agnes-video-2.5')))
        result=subprocess.run([sys.executable,str(ROOT/'scripts/vpc.py'),'batch',str(job),'--out',str(self.out/'batch')],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        data=json.loads(result.stdout)
        self.assertEqual(data['jobs'][1]['status'],'COMPILED')


if __name__=='__main__':unittest.main()
