"""V5 contract tests. Synthetic pixels exercise storage only, never real-media QA."""
import copy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_adapters import digest, encoded, pointer, storyboard_to_avir
from ai_comic_drama_workflow.v5_modules import ROOT, MODULES, digest_file, load_python, read

FIXTURE=ROOT/'examples/v5/cafe'
sys.path.insert(0,str(ROOT/'scripts'))
from screenplay_fixture import screenplay, director_mapping


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encoded(value));return path


def review(task,value):
    if task['kind']=='director' and task['handoff']['required_handoffs']:
        return director_mapping(task,value)
    rows=[]
    for req in task['handoff']['required_handoffs']:
        cid=req['id'].split(':')[-1]
        if task['kind']=='art':
            checks=[{'path':'/set/scene_id','op':'equals','value':'CAFE'}]
            reason='Fixture author reviewed every director requirement; ArtIR preserves the linked scene and does not alter shots, dialogue or custody.'
        else:
            clause=next(c for c in value['contract'] if c['id']==cid)
            checks=clause['checks']
            reason='Fixture author maps the same named requirement to native storyboard assertions; positions use [x,z,y], voice and event order remain explicit.'
        rows.append({'requirement_id':req['id'],'source_fingerprint':req['source_fingerprint'],
                     'target_clause':cid,'target_checks':checks,'reason':reason})
    return rows


def result_for(task,**kw):
    return {'schema':'role-result/5.0','task_id':task['task_id'],'context_fingerprint':task['context_fingerprint'],
            'checks':['SYNTHETIC STATIC TEST: source, assertions and native protocol checked; no actual image/video QA.'],
            'conflicts':[],'unresolved':[],**kw}


def submit_fixture(k,author,task,complete=True):
    kind=task['kind']
    if kind=='screenplay' and k.screenplay_protocol():
        value=screenplay(k)
    elif kind in ('canon','screenplay'):
        value={'project_id':'CAFE_DEMO','revision':1,'content':(FIXTURE/'cafe.source.txt').read_text(),
               'source_refs':[s['id'] for s in k.state['sources']]}
        if kind=='canon':value.update(entities=[{'id':e['id']} for e in read(FIXTURE/'director.json')['entities']],locks=[])
    elif kind=='qa':
        value={'project_id':'CAFE_DEMO','passed':True,'build_id':k.state['build']['build_id'],
               'checks':['Synthetic static fixture acceptance only; no real media was generated or reviewed.']}
    else:value=read(author/(kind+'.json'))
    mapping=review(task,value)
    path=save(author/('submitted-'+kind+'.json'),value)
    result=result_for(task,artifact=str(path),artifact_sha256=digest_file(path),complete=complete,handoff=mapping)
    k.submit(result);return result


def seed_until(k,author,kind):
    for _ in range(12):
        step=k.run()
        if step.get('task',{}).get('kind')==kind:return step['task']
        if 'task' not in step:raise AssertionError(step)
        submit_fixture(k,author,step['task'])
    raise AssertionError('fixture did not reach '+kind)


class V5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.author=self.base/'author';shutil.copytree(FIXTURE,self.author)
        self.k=V5Kernel.initialize(self.base/'project',[str(self.author/'cafe.source.txt')],
            project_id='CAFE_DEMO',delivery='text-only',target='agnes-video-2.5')

    def ready(self):
        task=seed_until(self.k,self.author,'qa');submit_fixture(self.k,self.author,task)
        return self.k.run()

    def test_text_only_end_to_end_and_idempotent_export(self):
        self.assertEqual(self.ready()['status'],'DELIVERED')
        self.assertTrue(self.k.validate(True)['valid']);self.assertEqual(self.k.state['media'],{})
        before=self.k.state['build'];self.assertEqual(self.k.run()['status'],'DELIVERED')
        self.assertEqual(before,self.k.state['build'])
        text=(self.k.path(before['uri'])/'compiled/prompt.txt').read_text()
        self.assertIn('你确定？',text);self.assertIn('B.right_hand',text)
        self.assertFalse(self.k.validate(True)['video_generated'])

    def test_missing_result_schema_and_hash_are_rejected(self):
        task=self.k.run()['task']
        with self.assertRaises(ValueError):self.k.submit({'task_id':task['task_id']})
        path=save(self.author/'bad.json',{})
        with self.assertRaisesRegex(ValueError,'hash differs'):
            self.k.submit(result_for(task,artifact=str(path),artifact_sha256='0'*64))

    def test_duplicate_and_conflicting_submission(self):
        task=self.k.run()['task'];result=submit_fixture(self.k,self.author,task)
        self.assertEqual(self.k.submit(result)['status'],'ALREADY_ACCEPTED')
        with self.assertRaisesRegex(ValueError,'Conflicting duplicate'):self.k.submit({**result,'complete':False})

    def test_partial_result_gets_new_task_id(self):
        task=self.k.run()['task'];submit_fixture(self.k,self.author,task,complete=False)
        follow=self.k.run()['task'];self.assertNotEqual(task['task_id'],follow['task_id'])
        self.assertEqual(follow['kind'],'canon');submit_fixture(self.k,self.author,follow)
        self.assertEqual(self.k.run()['task']['kind'],'screenplay')

    def test_task_envelope_tampering_is_rejected(self):
        task=self.k.run()['task'];path=self.k.path('runtime/tasks/'+task['task_id']+'.json')
        task['scope']={'shot_ids':['invented']};save(path,task)
        with self.assertRaisesRegex(ValueError,'envelope hash'):self.k.submit(result_for(task))

    def test_missing_source_blocks_only_affected_project(self):
        self.k.path(self.k.state['sources'][0]['uri']).write_text('changed')
        self.assertEqual(self.k.run()['status'],'BLOCKED')
        self.assertFalse(self.k.validate()['valid'])

    def test_module_is_pinned_and_cache_tamper_is_rejected(self):
        path=self.k.modules('director-grammar')
        self.assertTrue(path.is_relative_to(self.k.root));self.assertNotEqual(path,ROOT.parent/'director-grammar')
        (path/'SKILL.md').write_text('modified')
        with self.assertRaisesRegex(ValueError,'Cached module'):self.k.modules('director-grammar')

    def test_missing_handoff_and_changed_identity_rejected(self):
        task=seed_until(self.k,self.author,'art');value=read(self.author/'art.json')
        with self.assertRaisesRegex(ValueError,'ownership handoff'):
            self.k.import_artifact('art',self.author/'art.json')
        value['assets'][0]['entity_id']='UNKNOWN'
        path=save(self.author/'identity-conflict.json',value)
        with self.assertRaises(ValueError):self.k.import_artifact('art',path)
        self.assertNotIn('art:CAFE',self.k.state['artifacts'])

    def test_independent_storyboard_requires_reconciliation_and_preserves_raw(self):
        source=self.author/'storyboard.json';raw=source.read_bytes()
        record=self.k.import_artifact('storyboard',source)
        self.assertTrue(record['needs_reconciliation']);self.assertEqual(source.read_bytes(),raw)
        self.assertTrue(any(self.k.path(p).read_bytes()==raw for p in record['files']))
        task=seed_until(self.k,self.author,'storyboard')
        self.assertIn('previous',task);self.assertEqual(task['previous']['original_sha256'],sha256(raw).hexdigest())
        submit_fixture(self.k,self.author,task)
        shutil.rmtree(self.author)
        self.assertTrue(self.k.valid('storyboard'))
        self.assertEqual(self.k.run()['task']['kind'],'qa')

    def test_import_art_auto_infers_scene(self):
        task=seed_until(self.k,self.author,'art');value=read(self.author/'art.json')
        record=self.k.import_artifact('art',self.author/'art.json',handoff=review(task,value))
        self.assertEqual(record['slot'],'art:CAFE');self.assertTrue(self.k.valid('art:CAFE'))

    def test_target_revision_keeps_storyboard_and_art(self):
        self.ready();before={k:r['sha256'] for k,r in self.k.state['artifacts'].items() if k!='qa'}
        self.k.revise('target',target='seedance-2.0')
        self.assertTrue(self.k.valid('storyboard'));self.assertFalse(self.k.valid('qa'))
        self.assertEqual(before,{k:r['sha256'] for k,r in self.k.state['artifacts'].items() if k!='qa'})

    def test_single_shot_scope_and_stable_image_fingerprints(self):
        self.ready();before={j['key']:j['fingerprint'] for j in self.k.image_jobs(7)}
        self.k.revise('storyboard',shot_id='S1');task=self.k.run()['task']
        self.assertEqual(task['scope']['shot_ids'],['S1','S2'])
        value=read(self.author/'storyboard.json');value['revision']+=1;value['shots'][0]['purpose']+='；保留原动作'
        path=save(self.author/'storyboard-rev.json',value)
        self.k.submit(result_for(task,artifact=str(path),artifact_sha256=digest_file(path),handoff=review(task,value)))
        after={j['key']:j['fingerprint'] for j in self.k.image_jobs(7)}
        # Prompt content uses camera/events; purpose-only metadata does not require new images.
        self.assertEqual(before,after)
        self.assertTrue(list((self.k.root/'history').glob('*.json')))

    def test_out_of_scope_shot_revision_rejected(self):
        self.ready();self.k.revise('storyboard',shot_id='S1');task=self.k.run()['task']
        value=read(self.author/'storyboard.json');value['shots'][2]['purpose']+=' changed'
        path=save(self.author/'out-of-scope.json',value)
        with self.assertRaisesRegex(ValueError,'scoped shot'):
            self.k.submit(result_for(task,artifact=str(path),artifact_sha256=digest_file(path),handoff=review(task,value)))

    def test_native_hash_tampering_invalidates_registration(self):
        self.ready();self.k.path(self.k.state['artifacts']['director']['uri']).write_text('{}')
        self.assertFalse(self.k.valid('director'));self.assertFalse(self.k.validate(True)['valid'])

    def test_copy_v4_and_yaml_preserves_original_bytes_and_never_approvals(self):
        for version in ('4.0','yaml'):
            src=self.base/('legacy-'+version);src.mkdir()
            if version=='4.0':save(src/'project.json',{'schema_version':'4.0','project_id':'CAFE_DEMO','workflow_id':'ai-comic-drama-v4','segment_target_s':12})
            else:(src/'project.yaml').write_text('project_id: P001\nstatus: APPROVED\nunknown: keep-me\n')
            (src/'approval.json').write_text('{"status":"approved","unknown":"preserve"}')
            before={str(p.relative_to(src)):digest_file(p) for p in src.rglob('*') if p.is_file()}
            new=V5Kernel.copy_project(src,self.base/('migrated-'+version))
            self.assertEqual(before,{str(p.relative_to(src)):digest_file(p) for p in src.rglob('*') if p.is_file()})
            self.assertEqual(new.state['approvals'],{})
            report=read(new.root/'imports/migration.json')
            self.assertEqual(report['status'],'COPIED_REVIEW_REQUIRED')
            self.assertEqual(set(before.values()),{f['sha256'] for f in report['files']})
            if version=='4.0':self.assertEqual(new.project['legacy_constraints']['max_uploaded_references'],5)
        with self.assertRaises(ValueError):V5Kernel.copy_project(src,src/'nested')

    def test_legacy_cannot_run_or_submit(self):
        legacy=self.base/'old';legacy.mkdir();save(legacy/'project.json',{'schema_version':'4.0'})
        k=V5Kernel(legacy);self.assertEqual(k.status()['status'],'LEGACY_READ_ONLY')
        with self.assertRaises(ValueError):k.run()
        self.assertFalse((legacy/'runtime').exists())

    def test_existing_compilation_import_reuses_prompt_bytes(self):
        self.ready();build=self.k.state['build'];folder=self.k.path(build['uri'])/'compiled'
        prompt=(folder/'prompt.txt').read_bytes()
        self.k.import_compiled(folder)
        self.assertEqual(self.k.run()['status'],'DELIVERED')
        new=self.k.path(self.k.state['build']['uri'])
        self.assertEqual((new/'compiled/prompt.txt').read_bytes(),prompt)
        self.assertTrue(read(new/'mapping.json')['compiled_package_reused'])

    def test_no_host_media_decision_allows_provided_images_and_inflight_recovery(self):
        seed_until(self.k,self.author,'storyboard')
        self.k.project['delivery']='full';self.k.write('project.json',self.k.project)
        prompt=self.k.run()['task'];self.assertEqual(prompt['kind'],'image-prompt')
        self.k.submit(result_for(prompt,prompt='Synthetic test fixture prompt; no real generation.'))
        decision=self.k.run()['decision'];self.assertEqual(decision['key'],'image-capability')
        self.k.resume({'request_id':decision['id'],'value':'provide-media','evidence':'TEST FIXTURE, not a real user approval'})
        task=self.k.run()['task'];self.assertEqual(task['kind'],'image')
        self.k.begin_image(task['task_id'])
        self.assertEqual(V5Kernel(self.k.root).run()['status'],'AWAITING_MEDIA_RESULT')
        with self.assertRaisesRegex(ValueError,'in-flight'):self.k.revise('art',scene_id='CAFE')
        self.k.recover_image('TEST FIXTURE authorized retry only');self.assertIsNone(self.k.state['inflight'])

    def test_real_image_required_for_full_export(self):
        self.ready();self.k.project['delivery']='full';self.k.write('project.json',self.k.project)
        report=self.k.export();self.assertEqual(report['status'],'BLOCKED')
        self.assertTrue(any('Required image' in e for e in report['validation']['errors']))


    def image_task(self):
        seed_until(self.k,self.author,'storyboard')
        self.k.project.update(delivery='full',mode='reference',target='seedance2.0')
        self.k.write('project.json',self.k.project);self.k.host('available','TEST FIXTURE host declaration')
        task=self.k.run()['task']
        self.k.submit(result_for(task,prompt='SYNTHETIC TEST image prompt; no production-media claim.'))
        return self.k.run()['task']

    def pixels(self):
        # Minimal PNG generated only to test the real decoder and byte registration.
        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        path=self.author/'synthetic-test-only.png'
        path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,2,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes([80,120,160])*2)*2))+chunk(b'IEND',b''))
        return path

    def image_result(self,task,path):
        checksum=digest_file(path)
        return result_for(task,media={'path':str(path),'sha256':checksum,'provider':'provided',
            'call_evidence':'SYNTHETIC UNIT TEST INPUT; not real visual-acceptance evidence',
            'input_bindings':[{'key':r['key'],'sha256':r['sha256']} for r in task['job']['references']],
            'visual_review':{'status':'PASS','sha256':checksum,'findings':['TEST ONLY: synthetic PNG byte/decoder exercise. No identity or composition QA claim.']}})

    def test_media_hash_missing_image_and_wrong_bindings_rejected(self):
        task=self.image_task();path=self.pixels();result=self.image_result(task,path)
        result['media']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Media hash'):self.k.submit(result)
        result=self.image_result(task,path);result['media']['input_bindings']=[{'key':'invented','sha256':digest_file(path)}]
        with self.assertRaisesRegex(ValueError,'references'):self.k.submit(result)
        result=self.image_result(task,path);path.unlink()
        with self.assertRaises(OSError):self.k.submit(result)
        self.assertEqual(self.k.state['media'],{})

    def test_image_registration_recovers_once_and_approval_binds_version(self):
        task=self.image_task();path=self.pixels();result=self.image_result(task,path)
        self.k.begin_image(task['task_id']);self.k.submit(result)
        self.assertIsNone(self.k.state['inflight'])
        record=self.k.state['media'][task['slot']];self.assertEqual(record['revision'],1)
        self.assertEqual(self.k.submit(result)['status'],'ALREADY_ACCEPTED')
        request=self.k.run()['decision'];self.assertTrue(request['key'].startswith('identity:'))
        self.k.resume({'request_id':request['id'],'value':'approve','evidence':'SYNTHETIC TEST decision only, never a production user approval'})
        self.k.revise('target',target='agnes-video-2.5',mode='reference')
        self.assertTrue(self.k.media_valid(record));self.assertEqual(self.k.state['approvals'][task['slot']]['token'],self.k.approval_token(record))
        self.assertNotEqual(self.k.run()['task']['slot'],task['slot'])
        self.k.revise('asset',asset_id=task['slot'])
        self.assertFalse(self.k.media_valid(self.k.state['media'][task['slot']]))

    def test_board_media_survives_unconsumed_metadata_change(self):
        self.ready();job=self.k.image_jobs(7)[0]
        prompt={'uri':'prompts/test.txt','sha256':sha256(b'TEST ONLY').hexdigest(),'input_fingerprint':job['fingerprint'],'checks':['TEST ONLY']}
        self.k.write(prompt['uri'],b'TEST ONLY')
        task=self.k.task('image',job['key'],7,'image-prompt-optimizer',job['dependencies'],extra={'job':job,'prompt':prompt})['task']
        self.k.submit(self.image_result(task,self.pixels()))
        self.k.revise('storyboard',shot_id='S1');task=self.k.run()['task']
        value=read(self.author/'storyboard.json');value['shots'][0]['purpose']+='；纯备注修订'
        path=save(self.author/'revised.json',value)
        self.k.submit(result_for(task,artifact=str(path),artifact_sha256=digest_file(path),handoff=review(task,value)))
        self.assertTrue(self.k.media_valid(self.k.state['media'][job['key']]))
        self.assertEqual(self.k.image_jobs(7)[0]['fingerprint'],job['fingerprint'])

    def test_native_media_import_preserves_filename_and_copies_dependencies(self):
        self.ready();path=self.pixels();avir,_=storyboard_to_avir(read(self.author/'storyboard.json'),self.author)
        avir['assets']=[{'id':'REF_A','kind':'image','filename':path.name,'path':str(path),'sha256':digest_file(path),
                        'public_url':None,'inspection':'observed','source_refs':['DESIGN']}]
        avir['bindings']=[{'id':'REF_BIND_A','asset_id':'REF_A','target_id':'A','shot_ids':['S1','S2','S3'],
                          'roles':['identity'],'negative_roles':[],'source_refs':['DESIGN']}]
        source=save(self.author/'independent-avir.json',avir);original=source.read_bytes()
        record=self.k.import_artifact('avir',source)
        imported=self.k.data('avir');asset=imported['assets'][0]
        self.assertEqual(Path(asset['path']).name,path.name)
        self.assertTrue(Path(asset['path']).is_relative_to(self.k.root))
        self.assertEqual(digest_file(asset['path']),digest_file(path));self.assertEqual(source.read_bytes(),original)
        shutil.rmtree(self.author);self.assertTrue(self.k.valid('avir'))

    def test_locked_field_revision_requires_version_bound_decision(self):
        task=self.k.run()['task'];submit_fixture(self.k,self.author,task)
        value=self.k.data('canon');path=save(self.author/'locked-canon.json',value)
        self.k.import_artifact('canon',path,locks=[{'path':'/content','op':'equals','value':value['content']}])
        value['content']+=' 用户批准的补充设计。';changed=save(self.author/'new-canon.json',value)
        with self.assertRaisesRegex(ValueError,'Previously locked'):self.k.import_artifact('canon',changed)
        request=self.k.request_decision({'kind':'creative','question':'TEST: approve this exact locked content revision?',
            'context':{'reason':'SYNTHETIC TEST'},'lock_updates':[{'slot':'canon','index':0,'check':{'path':'/content','op':'equals','value':value['content']}}]})['decision']
        self.k.resume({'request_id':request['id'],'value':'approve','evidence':'SYNTHETIC TEST decision only'})
        self.k.import_artifact('canon',changed);self.assertTrue(self.k.valid('canon'))
        self.assertEqual(len(self.k.state['decisions']),1)

    def test_imported_compilation_followed_by_shot_revision_recompiles(self):
        self.ready();folder=self.k.path(self.k.state['build']['uri'])/'compiled'
        self.k.import_compiled(folder);self.k.run()
        self.k.revise('storyboard',shot_id='S1');task=self.k.run()['task']
        value=read(self.author/'storyboard.json');value['shots'][0]['purpose']+='；新的经审阅镜头说明'
        path=save(self.author/'shot-revision.json',value)
        self.k.submit(result_for(task,artifact=str(path),artifact_sha256=digest_file(path),handoff=review(task,value)))
        qa=self.k.run()['task'];self.assertEqual(qa['kind'],'qa');submit_fixture(self.k,self.author,qa)
        self.assertEqual(self.k.run()['status'],'DELIVERED')
        self.assertFalse(read(self.k.path(self.k.state['build']['uri'])/'mapping.json')['compiled_package_reused'])

    def test_avir_imported_before_upstream_is_reconciled_without_recreation(self):
        avir,_=storyboard_to_avir(read(self.author/'storyboard.json'),self.author)
        path=save(self.author/'early-avir.json',avir);self.k.import_artifact('avir',path)
        self.assertTrue(self.k.state['artifacts']['avir']['needs_reconciliation'])
        self.ready();self.assertTrue(self.k.valid('avir'))
        self.assertFalse(self.k.state['artifacts']['avir']['needs_reconciliation'])

    def test_source_long_text_and_scene_job_keys(self):
        k=V5Kernel.initialize(self.base/'long',['文字'*10000],delivery='text-only')
        self.assertEqual(len(k.state['sources']),1)
        seed_until(self.k,self.author,'storyboard')
        keys=[j['key'] for j in self.k.image_jobs(5)]
        self.assertTrue(all(k.startswith('ASSET_CAFE_') for k in keys));self.assertEqual(len(keys),len(set(keys)))

    def test_explicit_module_update_keeps_old_archive_and_media_bytes(self):
        old=read(self.k.root/'modules.lock.json')
        result=self.k.update_modules(ROOT/'modules.lock.json',ROOT/'assets/bundled-skills')
        self.assertEqual(result['changed'],[])
        self.assertEqual(old,read(self.k.root/'modules.lock.json'))
        self.assertTrue(list((self.k.root/'history').glob('modules-*.json')))

class AdapterTests(unittest.TestCase):
    def setUp(self):self.ir=read(FIXTURE/'storyboard.json')
    def convert(self):return storyboard_to_avir(self.ir,FIXTURE)

    def test_fixed_story_preserves_voice_order_and_handedness(self):
        result,report=self.convert();self.assertEqual(report['status'],'MAPPED')
        self.assertEqual(result['output']['duration_ms'],12000)
        utter=result['audio']['utterances'][0];self.assertEqual(utter['text'],'你确定？');self.assertEqual(utter['speaker_id'],'B')
        self.assertEqual(utter['kind'],self.ir['audio']['utterances'][0]['kind'])
        end=result['shots'][-1]['end_state'];self.assertIn('ENVELOPE',next(s for s in end if s['entity_id']=='B')['holding'])
        self.assertIn('B.right_hand',next(s for s in end if s['entity_id']=='ENVELOPE')['pose'])
        self.assertEqual(len(result['shots'][2]['performance']),len(self.ir['shots'][2]['performance'])+len(self.ir['shots'][2]['events']))

    def test_frame_rounding_shared_boundary_and_no_accumulation(self):
        self.ir['delivery']['fps']=23
        result,report=self.convert()
        self.assertEqual(result['shots'][0]['end_ms'],result['shots'][1]['start_ms'])
        self.assertEqual(result['shots'][-1]['end_ms'],round(288000/23))
        self.assertTrue(all(abs(v['error_ms'])<=0.5 for v in report['rounding'].values()))

    def test_unmappable_hard_field_blocks_not_just_sidecar(self):
        self.ir['contract'][0]['checks']=[{'path':'/shots/0/panels/0/frame','op':'equals','value':self.ir['shots'][0]['panels'][0]['frame']}]
        result,report=self.convert();self.assertEqual(report['status'],'BLOCKED')
        self.assertTrue(any('No verified AVIR' in l['reason'] for l in report['losses']))
        self.assertIn('panels',report['sidecar']['shots'][0])

    def test_failed_source_contract_is_not_repaired_silently(self):
        self.ir['contract'][0]['checks'][0]['value']=1
        self.assertEqual(self.convert()[1]['status'],'BLOCKED')

    def test_coordinate_basis_and_boundary_relations_block_ambiguous_conversion(self):
        self.ir['scenes'][0]['coordinates']['axes']='ambiguous'
        self.assertEqual(self.convert()[1]['status'],'BLOCKED')
        self.ir=read(FIXTURE/'storyboard.json');self.ir['shots'][0]['relations'][0]['at']='start'
        self.assertEqual(self.convert()[1]['status'],'BLOCKED')

    def test_explicit_mapping_requires_source_owner_and_assertion(self):
        c=self.ir['contract'][0];p='/shots/0/panels/0/frame';c['checks']=[{'path':p,'op':'equals','value':0}]
        override={p:{'owner':'wrong','reason':'bad','check':{'path':'/shots/0/start_ms','op':'equals','value':0}}}
        self.assertEqual(storyboard_to_avir(self.ir,FIXTURE,override)[1]['status'],'BLOCKED')
        override[p]['owner']=c['owner'];override[p]['reason']='The first panel at frame zero is exactly the shot start, mapped to zero ms; its still-image purpose remains in the source package.'
        self.assertEqual(storyboard_to_avir(self.ir,FIXTURE,override)[1]['status'],'MAPPED')

    def test_native_storyboard_handoff_file_is_not_accepted_as_avir(self):
        with self.assertRaises(ValueError):storyboard_to_avir({'schema':'compiler-handoff/1.0'},FIXTURE)


if __name__=='__main__':unittest.main()
