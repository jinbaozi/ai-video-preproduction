"""Studio V2 fault injection and local media tests. No paid generation or real speech."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from ai_comic_drama_workflow.assembly import _probe
from ai_comic_drama_workflow.executors.manual import ManualExecutor
from ai_comic_drama_workflow.lean import start, step
from ai_comic_drama_workflow.production import ProductionLedger
from ai_comic_drama_workflow.studio import StudioExecution, dialogue_timing, RISK_TYPES
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_cli import main
from ai_comic_drama_workflow.v5_modules import read


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.kernel = V5Kernel.initialize(self.root/'project', ['原创测试'], delivery='text-only', production_target='video')
        self.ledger = ProductionLedger(self.kernel)
        self.studio = StudioExecution(self.ledger)
        self.proof = self.root/'host-authorization.txt'
        self.proof.write_text('TEST FIXTURE ONLY: not real user authorization or provider evidence')
        self.jobs = [self.job('S' + str(i)) for i in range(1, 7)]

    def job(self, shot, suffix=''):
        request = {'id': 'REQ_' + shot + suffix, 'submitted': False, 'payload_draft': {'prompt': 'test ' + shot + suffix}}
        return self.ledger.plan_job(request, 'test-compile', [], [shot], {'max_attempts': 3, 'project_cap': 20})

    def configure(self, cap=100, attempts=10):
        return self.studio.configure({'currency': 'CNY', 'cap_minor': cap, 'max_total_attempts': attempts,
            'authorization_file': str(self.proof), 'quotes': {j['id']: 40 for j in self.jobs},
            'canary': dict(zip(sorted(RISK_TYPES), ['S1', 'S2', 'S3', 'S4', 'S5']))})

    def begin(self, index=0):
        return self.ledger.begin_submit(self.jobs[index]['id'], automatic=False)

    def evidence(self, record, state='SUBMITTED', task='provider-fixture-1'):
        job = self.ledger._load('jobs/' + record['job_id'] + '.json')
        return {'record_id': record['id'], 'payload_sha256': job['payload_sha256'], 'state': state,
                'task_id': task, 'proof_file': str(self.proof), 'observation': 'SYNTHETIC TEST observation'}

    def test_unknown_cannot_be_bypassed_with_new_job_id(self):
        record = self.begin()
        self.ledger.mark_unknown(record['id'], 'timeout')
        changed = self.job('S1', '_changed')
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            self.ledger.begin_submit(changed['id'], automatic=False)
        self.assertEqual(len(self.ledger.records()), 1)

    def test_manual_attempts_consume_project_count(self):
        first = self.begin()
        self.ledger.mark_failed(first['id'], 'confirmed test failure')
        job = self.ledger.plan_job({'id': 'LIMIT', 'submitted': False, 'payload_draft': {'prompt': 'new'}},
                                   'compile', [], ['S9'], {'max_attempts': 1, 'project_cap': 1})
        self.assertEqual(self.ledger.begin_submit(job['id'], automatic=False)['status'], 'BLOCKED_BUDGET')

    def test_reservation_survives_unknown_and_settlement_is_idempotent(self):
        self.configure()
        record = self.begin()
        self.ledger.mark_unknown(record['id'], 'timeout')
        with self.assertRaisesRegex(ValueError, 'retains'):
            self.studio.settle(record['id'], 0, self.proof)
        self.assertEqual(self.studio.report()['reserved_minor'], 40)
        evidence = self.evidence(record, state='FAILED', task=None)
        self.studio.reconcile(record['id'], evidence)
        self.assertEqual(self.studio.reconcile(record['id'], evidence)['state'], 'FAILED')
        self.assertEqual(self.studio.report()['reserved_minor'], 40)
        self.studio.settle(record['id'], 25, self.proof)
        self.studio.settle(record['id'], 25, self.proof)
        report = self.studio.report()
        self.assertEqual((report['reserved_minor'], report['settled_minor'], report['attempts']), (0, 25, 1))
        self.assertIsNone(report['settled_minor_per_accepted_second'])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.studio.settle(record['id'], 20, self.proof)

    def test_concurrent_reservations_cannot_overspend(self):
        self.configure(cap=50)
        def submit(index):
            try:
                return self.begin(index)['id']
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, [0, 1]))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.studio.report()['committed_minor'], 40)
        self.assertEqual(len(self.ledger.records()), 1)

    def test_attempt_cap_and_real_overrun_block_new_attempt(self):
        self.configure(cap=50, attempts=2)
        record = self.begin()
        self.ledger.mark_failed(record['id'], 'confirmed failure')
        self.studio.settle(record['id'], 80, self.proof)
        self.assertEqual(self.studio.report()['status'], 'OVER_BUDGET')
        with self.assertRaisesRegex(ValueError, 'monetary'):
            self.begin(1)

    def test_global_attempt_cap_includes_failed_and_manual_attempts(self):
        self.configure(cap=500, attempts=1)
        record = self.begin()
        self.ledger.mark_failed(record['id'], 'confirmed failure')
        with self.assertRaisesRegex(ValueError, 'attempt budget'):
            self.begin(1)

    def test_bulk_is_blocked_without_real_selected_canary(self):
        self.configure()
        self.assertEqual(self.studio.canary_status()['status'], 'BLOCKED')
        with self.assertRaisesRegex(ValueError, 'Applicable-risk'):
            self.begin(5)
        self.assertEqual(self.ledger.records(), [])
        self.assertEqual(self.studio.report()['reserved_minor'], 0)

    def risk_config(self):
        return {'currency':'RHC','cap_minor':200,'max_total_attempts':6,
            'authorization_file':str(self.proof),'quotes':{j['id']:20 for j in self.jobs},
            'canary':{'prop_closeup':'S1','single_closeup':'S2'},
            'risk_exclusions':{risk:{'reason':'SYNTHETIC single-person fixed-camera fixture: risk absent.',
                'shot_ids':['S'+str(i) for i in range(1,7)],'proof_file':str(self.proof)}
                for risk in RISK_TYPES-{'prop_closeup','single_closeup'}}}

    def test_single_person_canary_does_not_require_invented_handoff(self):
        self.studio.configure(self.risk_config())
        self.assertEqual(self.studio.canary_status()['status'],'BLOCKED')
        self.assertEqual(self.begin()['state'],'SUBMITTING')
        with self.assertRaisesRegex(ValueError,'Applicable-risk'):self.begin(5)

    def test_missing_risk_reason_or_scope_is_rejected(self):
        config=self.risk_config();config['risk_exclusions']['handoff']['reason']=''
        with self.assertRaisesRegex(ValueError,'Risk exclusion'):self.studio.configure(config)
        config=self.risk_config();config['risk_exclusions']['handoff']['shot_ids']=['S1']
        with self.assertRaisesRegex(ValueError,'Risk exclusion'):self.studio.configure(config)

    def test_changed_risk_evidence_blocks_new_spend(self):
        config=self.risk_config();proof=self.root/'risk-proof.json';proof.write_text('SYNTHETIC risk review')
        for row in config['risk_exclusions'].values():row['proof_file']=str(proof)
        self.studio.configure(config);proof.write_text('changed')
        with self.assertRaisesRegex(ValueError,'Evidence bytes'):self.begin()

    def test_policy_and_proof_bytes_are_rechecked(self):
        self.configure()
        self.proof.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Evidence bytes changed'):
            self.begin()
        self.assertEqual(self.ledger.records(), [])

    def test_configuration_does_not_migrate_existing_attempts(self):
        self.begin()
        with self.assertRaisesRegex(ValueError, 'not migrated'):
            self.configure()

    def test_reservation_and_execution_rollback_together(self):
        self.configure()
        original = self.ledger._write
        def fail(relative, *args):
            if relative.startswith('executions/'):
                raise ValueError('injected write failure')
            return original(relative, *args)
        with patch.object(self.ledger, '_write', side_effect=fail):
            with self.assertRaisesRegex(ValueError, 'injected'):
                self.begin()
        self.assertEqual(self.ledger.records(), [])
        self.assertEqual(self.studio.report()['committed_minor'], 0)

    def test_recovered_manual_take_keeps_original_attempt(self):
        self.configure()
        record = self.begin()
        self.ledger.mark_unknown(record['id'], 'lost submit response')
        evidence = self.evidence(record)
        self.studio.reconcile(record['id'], evidence)
        self.studio.reconcile(record['id'], evidence)
        path = self.root/'fake.bin'
        path.write_bytes(b'TEST ONLY not playable media; non-strict legacy fixture')
        take = ManualExecutor(self.ledger).receive(self.jobs[0]['id'], path, {}, record_id=record['id'])['take']
        self.assertEqual(take['record_id'], record['id'])
        self.assertEqual(len(self.ledger.records()), 1)
        self.assertEqual(self.studio.report()['reserved_minor'], 40)
        self.assertEqual(self.studio.reconcile(record['id'], evidence)['state'], 'SUCCEEDED')

    def test_reconciliation_rejects_wrong_task_payload_and_empty_proof(self):
        record = self.begin()
        self.ledger.mark_submitted(record['id'], 'original')
        self.ledger.mark_unknown(record['id'], 'timeout')
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            self.studio.reconcile(record['id'], self.evidence(record, task='different'))
        evidence = self.evidence(record, task='original')
        evidence['payload_sha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'payload'):
            self.studio.reconcile(record['id'], evidence)
        evidence = self.evidence(record, task='original')
        self.proof.write_text('')
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            self.studio.reconcile(record['id'], evidence)
        self.assertEqual(self.ledger.records()[0]['state'], 'UNKNOWN')

    def test_studio_rejects_retroactive_manual_reservation(self):
        self.configure()
        media = self.root/'fake.bin'
        media.write_bytes(b'test')
        with self.assertRaisesRegex(ValueError, 'before generation'):
            ManualExecutor(self.ledger).receive(self.jobs[0]['id'], media, {})

    def test_cli_failed_take_review_does_not_block_review_of_replacement(self):
        plan=self.root/'plan.json'
        plan.write_text(json.dumps([{'id':'C','level':'hard','checks':['visible'],'shot_ids':['S1']}]))
        observed=self.root/'observations.json'
        identifiers=[]
        for take, verdict in [('TAKE_bad','FAIL'),('TAKE_replacement','PASS')]:
            observed.write_text(json.dumps([{'id':'C','result':verdict,'evidence':'SYNTHETIC review fixture'}]))
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code=main(['production',str(self.kernel.root),'review-take','--shot','S1','--take',take,
                           '--plan',str(plan),'--observations',str(observed)])
            result=json.loads(output.getvalue())
            self.assertEqual(result['status'],verdict)
            self.assertEqual(code,2 if verdict=='FAIL' else 0)
            identifiers.append(result['id'])
        self.assertNotEqual(*identifiers)
        self.assertEqual(len(list(self.ledger._path('acceptance').glob('*.json'))),2)

    def test_cli_configuration_report_and_failed_settlement(self):
        self.configure()
        record = self.begin()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(['production', str(self.kernel.root), 'studio-report'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['reserved_minor'], 40)
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(['production', str(self.kernel.root), 'settle', '--record', record['id'],
                         '--amount-minor', '0', '--receipt', str(self.proof)])
        self.assertEqual(code, 1)


class StudioProfileTests(unittest.TestCase):
    def test_new_default_removes_optional_process_and_keeps_native_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)/'new'
            result = start(project, ['原创对白'], production_target='video')
            config = read(project/'project.json')
            self.assertEqual(result['workflow_profile'], 'studio')
            self.assertEqual(config['craft_policy'], 'craft-routing/1.0')
            self.assertEqual(config['quality_policy'], 'studio-quality/1.0')
            self.assertEqual(config['editing_backend'], 'ffmpeg')
            self.assertFalse(config.get('flow_refinement'))
            self.assertEqual(config['delivery'], 'full')
            self.assertEqual(config['production_policy'], 'studio-production/2.0')
            self.assertIn('craft_context', result['context']['result_instruction'])
            before = (project/'project.json').read_bytes()
            step(project)
            self.assertEqual(before, (project/'project.json').read_bytes())

    def test_legacy_lean_and_explicit_studio_options_remain_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            for profile, options in [('lean', {}), ('studio', {'craft_routing': 'auto',
                    'reference_refinement': 'google-flow-2k', 'editing_backend': 'jianying-headless'})]:
                project = Path(tmp)/profile
                start(project, ['原创对白'], profile=profile, **options)
                config = read(project/'project.json')
                self.assertEqual(config['craft_policy'], 'craft-routing/1.0')
                self.assertEqual(config['editing_backend'], 'jianying-headless')
                self.assertEqual(config['flow_refinement']['policy'], 'google-flow-2k/1.0')


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires ffmpeg')
class StudioMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audio = self.root/'test-tone.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=0.6', str(self.audio)], check=True)
        self.script = self.root/'native-script.json'
        self.script.write_text(json.dumps({'lines': [{'text': '钥匙我留下。', 'speaker': '学徒'},
                                                    {'text': '先把信带上。', 'speaker': '师傅'}]}))
        self.bindings = [{'shot_id': 'S005', 'text_pointer': f'/lines/{i}/text',
                          'speaker_pointer': f'/lines/{i}/speaker', 'audio_file': str(self.audio),
                          'slot_ms': 2000} for i in range(2)]

    def test_real_audio_measurement_sums_two_speakers_and_never_claims_semantics(self):
        report = dialogue_timing(self.script, self.bindings)
        self.assertEqual(report['status'], 'FITS')
        self.assertEqual(report['shots']['S005']['duration_ms'], 1200)
        self.assertEqual(report['semantic_review'], 'NOT_RUN')
        for row in self.bindings:
            row['slot_ms'] = 1000
        self.assertEqual(dialogue_timing(self.script, self.bindings)['status'], 'SPLIT_REQUIRED')

    def test_unrelated_line_change_keeps_first_line_fingerprint(self):
        before = dialogue_timing(self.script, self.bindings)
        data = read(self.script)
        data['lines'][1]['text'] = '改动仅限这句。'
        self.script.write_text(json.dumps(data))
        after = dialogue_timing(self.script, self.bindings)
        self.assertEqual(before['lines'][0], after['lines'][0])
        self.assertNotEqual(before['lines'][1]['line_sha256'], after['lines'][1]['line_sha256'])

    def test_empty_duplicate_or_missing_audio_fails(self):
        for bindings in ([], self.bindings + [self.bindings[0]]):
            with self.assertRaises(ValueError):
                dialogue_timing(self.script, bindings)
        self.audio.unlink()
        with self.assertRaises(ValueError):
            dialogue_timing(self.script, self.bindings)

    def test_same_byte_probe_is_reused_but_never_visual_approval(self):
        from ai_comic_drama_workflow import assembly
        media = self.root/'cache.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=24:d=0.5',str(media)],check=True)
        assembly._PROBE_CACHE.clear()
        original = assembly._decode
        with patch.object(assembly,'_decode',wraps=original) as decode:
            first = _probe(media)
            first['width'] = 999
            second = _probe(media)
            self.assertEqual(decode.call_count,1)
            self.assertEqual(second['width'],64)
            self.assertNotIn('accepted',second)

    def test_dialogue_change_blocks_only_its_bound_shot(self):
        kernel=V5Kernel.initialize(self.root/'project',['fixture'],delivery='text-only')
        ledger=ProductionLedger(kernel);studio=StudioExecution(ledger)
        jobs=[]
        for shot in ('S1','S2'):
            jobs.append(ledger.plan_job({'id':'R'+shot,'submitted':False,'payload_draft':{'prompt':shot}},
                'fixture',[],[shot],{'max_attempts':1,'project_cap':2}))
        proof=self.root/'approval.txt';proof.write_text('SYNTHETIC authorization fixture')
        bindings=[dict(row,shot_id='S'+str(i+1)) for i,row in enumerate(self.bindings)]
        studio.configure({'currency':'CNY','cap_minor':100,'max_total_attempts':2,
            'authorization_file':str(proof),'quotes':{j['id']:10 for j in jobs},
            'canary':{'single_closeup':'S1','two_speakers':'S2'},
            'dialogue':{'script_file':str(self.script),'bindings':bindings,'margin_ms':200}})
        value=read(self.script);value['lines'][1]['text']='只修改第二句。'
        self.script.write_text(json.dumps(value))
        ledger.begin_submit(jobs[0]['id'],automatic=False)
        with self.assertRaisesRegex(ValueError,'changed for this shot'):
            ledger.begin_submit(jobs[1]['id'],automatic=False)
        self.assertEqual(len(ledger.records()),1)
        self.assertEqual(studio.report()['reserved_minor'],10)

    def test_real_media_probe_and_corruption(self):
        media = self.root/'synthetic.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=s=90x160:r=24:d=1', '-i', str(self.audio),
                        '-c:v', 'libx264', '-c:a', 'aac', '-movflags', '+faststart', str(media)], check=True)
        probe = _probe(media)
        self.assertEqual((probe['width'], probe['height'], probe['frames'], probe['audio_streams']), (90,160,24,1))
        data = media.read_bytes()
        media.write_bytes(data[:len(data)//2])
        with self.assertRaisesRegex(ValueError, 'decode'):
            _probe(media)

    def test_full_decode_error_cannot_be_hidden_by_readable_metadata(self):
        error = subprocess.CompletedProcess([], 1, '', 'corrupt decoded frame')
        with patch('ai_comic_drama_workflow.assembly.subprocess.run', return_value=error):
            with self.assertRaisesRegex(ValueError, 'decode'):
                _probe(self.audio)


class StudioNativeCanaryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires ffmpeg')
    def test_five_native_take_reviews_unlock_bulk_and_changed_bytes_close_gate(self):
        from tests.test_v6_production import _strict_kernel, _media
        from ai_comic_drama_workflow.acceptance import freeze_plan, shot_decision
        from ai_comic_drama_workflow.v5_modules import digest_file
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kernel = _strict_kernel(root/'project')
            ledger = ProductionLedger(kernel)
            studio = StudioExecution(ledger)
            requests = [{'id': 'REQ_' + str(i), 'status': 'COMPILED_DRAFT', 'submitted': False, 'reasons': [],
                         'payload_draft': {'prompt': 'SYNTHETIC native gate test'},
                         'scope': {'shot_ids': ['S' + str(i)], 'start_ms': (i-1)*1000, 'end_ms': i*1000}}
                        for i in range(1,7)]
            compiled = root/'compile.json'
            compiled.write_text(json.dumps({'status': 'COMPILED_DRAFT', 'submitted': False, 'requests': requests}))
            jobs = [ledger.plan_job(r, digest_file(compiled), [], r['scope']['shot_ids'],
                                    {'max_attempts': 1, 'project_cap': 6}, compile_path=compiled) for r in requests]
            shots = ['S' + str(i) for i in range(1,7)]
            plan = freeze_plan([{'id': 'C', 'level': 'hard', 'checks': ['visible'], 'shot_ids': []}])
            ledger.freeze_delivery_manifest(shots, plan, [], {'width':64,'height':64,'fps':24,'preserve_native_audio':True},
                shot_ranges={s:{'start_ms':i*1000,'end_ms':(i+1)*1000} for i,s in enumerate(shots)})
            proof = root/'proof.txt'
            proof.write_text('SYNTHETIC local fixture. Not authorization, provider generation or creative review.')
            studio.configure({'currency':'CNY','cap_minor':600,'max_total_attempts':6,'authorization_file':str(proof),
                              'quotes':{j['id']:100 for j in jobs},'canary':dict(zip(sorted(RISK_TYPES),shots[:5]))})
            media = root/'synthetic.mp4'
            _media(media)
            for shot, job in zip(shots[:5], jobs[:5]):
                record = ledger.begin_submit(job['id'],automatic=False)
                studio.reconcile(record['id'], {'record_id':record['id'],'payload_sha256':job['payload_sha256'],
                    'state':'SUBMITTED','task_id':'LOCAL_TEST_'+shot,'proof_file':str(proof),'observation':'Synthetic local generation'})
                take = ManualExecutor(ledger).receive(job['id'],media,_probe(media),record_id=record['id'])['take']
                decision = shot_decision(plan,[{'id':'C','result':'PASS','evidence':'Synthetic gate fixture, not a real creative review'}],shot,plan['sha256'])
                decision.update(id='ACC_'+shot,take_ids={shot:take['id']})
                ledger.save_acceptance(decision)
                ledger.select_take(shot,take['id'])
            self.assertEqual(studio.canary_status()['status'],'PASS')
            self.assertEqual(studio.report()['accepted_seconds'],5)
            record = ledger.begin_submit(jobs[5]['id'],automatic=False)
            self.assertEqual(record['state'],'SUBMITTING')
            kernel.path(take['uri']).write_bytes(b'changed')
            self.assertEqual(studio.canary_status()['status'],'BLOCKED')

    def test_audited_recovery_updates_native_graph_without_second_attempt(self):
        from tests.test_v6_production import StrictProductionTests, _compiled
        from ai_comic_drama_workflow.acceptance import freeze_plan
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            bridge=StrictProductionTests()._bridge(root/'project')
            request={'id':'REQ','status':'COMPILED_DRAFT','submitted':False,'reasons':[],
                     'payload_draft':{'prompt':'SYNTHETIC fixture'},'scope':{'shot_ids':['S1'],'start_ms':0,'end_ms':1000}}
            compiled,digest=_compiled(root,request)
            job=bridge.plan_job(request,digest,[],['S1'],{'max_attempts':1,'project_cap':1},compile_path=compiled)
            plan=freeze_plan([{'id':'C','level':'hard','checks':['visible'],'shot_ids':[]}])
            bridge.freeze_delivery(['S1'],plan,[],{'width':64,'height':64,'fps':24,'preserve_native_audio':True},
                                   shot_ranges={'S1':{'start_ms':0,'end_ms':1000}})
            record=bridge.begin_external(job['id'])
            proof=root/'proof.txt';proof.write_text('SYNTHETIC provider query result')
            evidence={'record_id':record['id'],'payload_sha256':job['payload_sha256'],'state':'SUBMITTED',
                      'task_id':'TEST_TASK','proof_file':str(proof),'observation':'Synthetic submitted task observed'}
            recovered=bridge.reconcile_external(record['id'],evidence)
            self.assertEqual(recovered['state'],'SUBMITTED')
            self.assertEqual(len(bridge.ledger.records()),1)
            nodes=[r for r in bridge.runtime.kernel.snapshot()['tasks'].values() if r['envelope']['node_id']=='video_execution']
            self.assertEqual(len(nodes),1)
            self.assertEqual(nodes[0]['state'],'ACCEPTED')


if __name__ == '__main__':
    unittest.main()
