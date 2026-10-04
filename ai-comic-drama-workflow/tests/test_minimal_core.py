"""Minimal host transport tests; synthetic authors, real native acceptance/validators."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ai_comic_drama_workflow import craft_router as cr, craft_runtime as rt, minimal, workspace
from ai_comic_drama_workflow.lean import start, compact
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import ROOT, read, digest_file
from ai_comic_drama_workflow.v5_adapters import digest
from tests.test_craft_routing import context, review, save, SKILL_ROOTS
from tests.test_v5_workflow import FIXTURE, result_for
from tests import test_craft_end_to_end as e2e


def core_result(result, plan=None):
    """Convert a synthetic author fixture, never generate new semantic evidence."""
    value=deepcopy(result)
    value['schema']=minimal.RESULT;value['read_ack']=True
    for key in ('context_fingerprint','artifact_sha256','module_receipt','validator'):
        value.pop(key,None)
    if value.get('craft_context'):value['craft_context'].pop('source_sha256',None)
    if value.get('craft_review'):
        review=value['craft_review'];review.pop('plan_sha256',None)
        groups={}
        rules={r['id']:r for r in (plan or {}).get('rules',[])+(plan or {}).get('inherited',[])}
        for row in review.pop('applications'):
            evidence={k:v for k,v in row.items() if k not in ('id','value_sha256')}
            key=digest([evidence,rules.get(row['id'],{}).get('scope',(plan or {}).get('scope',{}))])
            groups.setdefault(key,{**evidence,'rule_ids':[]})['rule_ids'].append(row['id'])
        review['groups']=list(groups.values())
    return value


class MinimalCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.author=self.root/'author'
        shutil.copytree(FIXTURE,self.author)
        self.kernel=V5Kernel.initialize(self.root/'project',[str(self.author/'cafe.source.txt')],
            project_id='CAFE_DEMO',delivery='text-only',target='agnes-video-2.5',
            workflow_profile='lean',output_policy=workspace.POLICY,craft_policy=rt.POLICY,
            context_policy=minimal.POLICY)

    def canon_result(self):
        task=self.kernel.run()['task']
        artifact={'project_id':'CAFE_DEMO','content':(self.author/'cafe.source.txt').read_text(),
                  'source_refs':[s['id'] for s in self.kernel.state['sources']],
                  'entities':[{'id':e['id']} for e in read(self.author/'director.json')['entities']], 'locks':[]}
        path=save(self.author/'canon.json',artifact)
        result=result_for(task,artifact=str(path),artifact_sha256=digest_file(path),craft_context=context(self.kernel))
        return task,core_result(result)

    def screenplay_task(self):
        _,result=self.canon_result();self.kernel.submit(result)
        return self.kernel.run()['task']

    def test_default_new_lean_has_core_not_new_native_protocol(self):
        response=start(self.root/'default',['成年旅人拾起信封。'],delivery='text-only')
        task=read(Path(response['task_file']))
        self.assertEqual(task['schema'],'task-envelope/5.0')
        self.assertEqual(response['context']['schema'],'core-task/1.0')
        self.assertEqual(response['context']['project']['context_policy'],minimal.POLICY)
        self.assertEqual(response['context']['sources'],task['sources'])
        self.assertEqual(response['context']['handoff'],task['handoff'])
        self.assertNotIn('context_fingerprint',response['context'])

    def test_explicit_audit_retains_old_read_surface(self):
        response=start(self.root/'audit',['idea'],delivery='text-only',context_profile='audit')
        self.assertNotIn('context',response)
        self.assertNotIn('context_policy',read(self.root/'audit/project.json'))
        with self.assertRaises(ValueError):
            start(self.root/'v6',['idea'],profile='audited',context_profile='core')

    def test_frozen_context_policy_cannot_be_removed(self):
        config=read(self.kernel.root/'project.json');config.pop('context_policy')
        save(self.kernel.root/'project.json',config)
        with self.assertRaisesRegex(ValueError,'Frozen'):
            V5Kernel(self.kernel.root).run()

    def test_missing_ack_and_runtime_claims_are_rejected(self):
        _,result=self.canon_result()
        for change in ({'read_ack':False},{'validator':{'status':'VALID'}},{'module_receipt':{}},{'core_audit':{}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.kernel.submit({**result,**change})
        self.assertEqual(self.kernel.state['artifacts'],{})

    def test_bind_current_native_result_and_idempotence(self):
        task,result=self.canon_result()
        self.assertEqual(self.kernel.submit(result)['status'],'ACCEPTED')
        saved=read(self.kernel.path('runtime/results/'+task['task_id']+'.json'))
        self.assertEqual(saved['artifact_sha256'],digest_file(Path(result['artifact'])))
        self.assertEqual(saved['core_audit']['semantic_assessment'],'HOST_DECLARED')
        self.assertEqual(self.kernel.submit(result)['status'],'ALREADY_ACCEPTED')
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            self.kernel.submit({**result,'checks':['different review']})

    def test_conflict_does_not_fabricate_receipts_or_adoption(self):
        task,_=self.canon_result()
        blocked={'schema':minimal.RESULT,'task_id':task['task_id'],'checks':['source requires clarification'],
                 'conflicts':['missing actual identity evidence'],'unresolved':[]}
        self.assertEqual(self.kernel.submit(blocked)['status'],'BLOCKED')
        self.assertFalse(self.kernel.state['artifacts'])
        self.assertEqual(self.kernel.state['active_task'],task['task_id'])

    def test_task_tamper_rejected_even_without_host_hashes(self):
        task,result=self.canon_result()
        path=self.kernel.path('runtime/tasks/'+task['task_id']+'.json')
        task['project']['target']='seedance2.5';save(path,task)
        with self.assertRaisesRegex(ValueError,'Stale|changed'):
            self.kernel.submit(result)

    def test_declared_artifact_hash_mismatch_not_rebound(self):
        _,result=self.canon_result();result['artifact_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'bytes changed'):
            self.kernel.submit(result)

    def test_core_reads_are_actual_and_match_required_manifest(self):
        task=self.screenplay_task();packet=minimal.packet(task)
        actual={r['relative']:Path(r['path']).read_text() for r in task['module']['required_reads']}
        self.assertEqual({r['path']:r['text'] for r in packet['readings']},actual)
        self.assertIn('references/stage-core.md',actual)
        self.assertNotIn('references/detailed-execution.md',actual)

    def test_changed_required_read_rejected(self):
        task=self.screenplay_task();path=Path(task['module']['required_reads'][0]['path'])
        path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'Required read changed'):
            minimal.packet(task)

    def test_every_selected_rule_and_note_survives_projection(self):
        task=self.screenplay_task();view=minimal.packet(task);original=task['craft'];short=view['craft']
        for category in ('rules','inherited'):
            self.assertEqual([(r['id'],r['instruction'],r.get('check'),r.get('scope')) for r in original.get(category,[])],
                             [(r['id'],r['instruction'],r.get('check'),r.get('scope')) for r in short.get(category,[])])
        self.assertEqual(original.get('practitioner'),short.get('practitioner'))
        self.assertEqual(original.get('native_primary_pointer'),short.get('native_primary_pointer'))
        a=original['prompt_methods']['community']['cards'];b=short['prompt_methods']['community']['cards']
        self.assertEqual([(r['id'],r['reading']['text'],r['native_fields']) for r in a],[(r['id'],r['reading']['text'],r['native_fields']) for r in b])
        self.assertEqual(task['handoff'],view['handoff'])
        self.assertEqual(task['inputs'],view['inputs'])

    def test_stale_native_report_never_reused_across_calls(self):
        path=self.author/'director.json'
        self.kernel._capture_native_report=True;self.kernel._submit_origin='submit'
        self.kernel._fresh_native_report=('director',str(path),digest_file(path),{'status':'VALID'})
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'changed during submission'):
            self.kernel.check_validator('director',path,{'validator':{'status':'VALID'}})

    def test_wrong_final_audit_never_accepts_prior_task(self):
        task,result=self.canon_result()
        result['delivery_audit']={'passed':True,'build_id':'fake','checks':['fake observation']}
        with self.assertRaisesRegex(ValueError,'same build'):
            minimal.submit_final(self.kernel,result)
        self.assertEqual(self.kernel.state['active_task'],task['task_id'])
        self.assertEqual(self.kernel.state['artifacts'],{})


class GroupedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.plan=cr.route(SKILL_ROOTS['director-grammar'],'director','父女安静重逢。')
        self.artifact={'content':'父亲把钥匙放在桌面，女儿停在门框处，距离表达迟疑与关系。'}
        self.review=review(self.plan,self.artifact)
        self.grouped=core_result({'craft_review':self.review})['craft_review']

    def test_expanded_evidence_equals_uncompressed_native_evidence(self):
        self.assertEqual(cr.bind_review(self.plan,self.grouped,self.artifact),self.review)

    def test_group_omission_overlap_wildcard_and_mixed_forms_rejected(self):
        variants=[]
        r=deepcopy(self.grouped);r['groups'][0]['rule_ids'].pop();variants.append(r)
        r=deepcopy(self.grouped);r['groups'].append(deepcopy(r['groups'][0]));variants.append(r)
        r=deepcopy(self.grouped);r['groups'][0]['rule_ids']=['*'];variants.append(r)
        r=deepcopy(self.grouped);r['applications']=[];variants.append(r)
        for value in variants:
            with self.subTest(value=value),self.assertRaises(ValueError):cr.bind_review(self.plan,value,self.artifact)

    def test_no_automatic_semantic_pass(self):
        for field in ('rationale','semantic_review'):
            value=deepcopy(self.grouped);value.pop(field)
            with self.assertRaises(ValueError):cr.bind_review(self.plan,value,self.artifact)
        value=deepcopy(self.grouped);value['groups'][0]['status']='unresolved'
        with self.assertRaises(ValueError):cr.bind_review(self.plan,value,self.artifact)

    def test_changed_quote_hash_or_metadata_pointer_rejected(self):
        for fields in ({'quote':'不存在的台词内容'},{'value_sha256':'0'*64},{'pointer':'/style/primary'}):
            value=deepcopy(self.grouped);value['groups'][0].update(fields)
            with self.assertRaises(ValueError):cr.bind_review(self.plan,value,self.artifact)

    def test_different_scopes_cannot_be_collapsed(self):
        plan=deepcopy(self.plan)
        plan['rules'][0]['scope']={'scene_ids':['ONE']}
        plan['plan_sha256']=cr.digest({k:v for k,v in plan.items() if k!='plan_sha256'})
        with self.assertRaisesRegex(ValueError,'Different rule scopes'):
            cr.bind_review(plan,self.grouped,self.artifact)

    def test_each_standalone_creative_skill_binds_groups_via_its_cli(self):
        import subprocess,sys
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            for role,module in cr.ROLES.items():
                root=SKILL_ROOTS[module]
                plan=cr.route(root,role,'当前人物关系场景的专业方法。')
                source=review(plan,self.artifact)
                grouped=core_result({'craft_review':source},plan)['craft_review']
                save(folder/'plan.json',plan);save(folder/'review.json',grouped);save(folder/'native.json',self.artifact)
                p=subprocess.run([sys.executable,str(root/'scripts/craft_router.py'),'--plan',str(folder/'plan.json'),
                    '--review',str(folder/'review.json'),'--artifact',str(folder/'native.json')],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                self.assertEqual(json.loads(p.stdout),source)

    def test_old_review_still_valid(self):
        self.assertEqual(cr.validate_review(self.plan,self.review,self.artifact)['status'],'EVIDENCE_BOUND')

    def test_every_registered_person_and_profile_remains_routable(self):
        self.counts={'profiles':0,'people':0}
        for role,module in cr.ROLES.items():
            root=SKILL_ROOTS[module]
            for card in cr.catalog(root,role):
                with self.subTest(role=role,card=card['id']):
                    features={'requested':card['id'],'tags':[],'goal':'检查已登记方法的按需可达性，不声称艺术质量。'}
                    plan=cr.route(root,role,'测试当前场景的专业方法。',features)
                    self.assertEqual(plan['primary'],card['id'])
                    self.assertEqual(minimal.craft_view(plan)['primary'],card['id'])
                    self.assertTrue(plan['rules']);self.counts['profiles']+=1
                for person in card['practitioners']:
                    plan=cr.route(root,role,'参考'+person['name'],{'requested':person['name'],'tags':[]})
                    self.assertEqual(plan['practitioner']['name'],person['name'])
                    self.assertEqual(minimal.craft_view(plan)['practitioner'],plan['practitioner'])
                    self.counts['people']+=1
        self.assertGreater(self.counts['profiles'],20)
        self.assertGreater(self.counts['people'],40)


class MinimalNativeEndToEndTests(unittest.TestCase):
    def test_core_native_pipeline_and_batched_audit_use_real_gates(self):
        initialize=V5Kernel.initialize;submit=V5Kernel.submit
        calls=[]; kernels=[]
        def init(*args,**kwargs):
            kwargs.update(workflow_profile='lean',output_policy=workspace.POLICY,context_policy=minimal.POLICY)
            kernel=initialize(*args,**kwargs);kernels.append(kernel);return kernel
        def authored(kernel,result):
            if result.get('schema')==minimal.RESULT:return submit(kernel,result)
            task=read(kernel.path('runtime/tasks/'+result['task_id']+'.json'))
            value=core_result(result,task.get('craft'));calls.append(task['kind'])
            if task['kind']=='compile-review':
                value['delivery_audit']={'build_id':task['build']['build_id'],'passed':True,
                    'checks':['SYNTHETIC final fixture finding '+item for item in task['hard_clauses']] or ['SYNTHETIC no hard clauses']}
                before=deepcopy(kernel.state)
                bad=deepcopy(value);bad['delivery_audit']['checks']=['no matching clauses']
                if task['hard_clauses']:
                    with self.assertRaises(ValueError):minimal.submit_final(kernel,bad)
                    self.assertEqual(kernel.state,before)
                from ai_comic_drama_workflow.lean import step
                response=step(kernel.root,result=value)
                receipt=response['receipt']
                self.assertEqual(response['status'],'DELIVERED')
                self.assertFalse(response['video_complete'])
                self.assertIn('final_audit_receipt',receipt)
                replay=step(kernel.root,result=value)
                self.assertEqual(replay['receipt']['status'],'ALREADY_ACCEPTED')
                return receipt
            receipt=submit(kernel,value)
            saved=read(kernel.path('runtime/results/'+result['task_id']+'.json'))
            if task['kind'] in ('screenplay','director','art','storyboard','avir'):
                self.assertEqual(saved['validator']['origin'],'runtime-native-validator')
                self.assertIsNone(getattr(kernel,'_fresh_native_report',None))
            return receipt
        import ai_comic_drama_workflow.v5 as runtime
        native=runtime.native_validate
        with patch.object(V5Kernel,'initialize',side_effect=init),patch.object(V5Kernel,'submit',authored),patch.object(runtime,'native_validate',wraps=native) as validator:
            case=e2e.CraftEndToEndTests('test_native_text_delivery_retains_craft_proofs_without_media_claim')
            result=unittest.TestResult();case.run(result)
            self.assertEqual(result.errors,[]);self.assertEqual(result.failures,[])
            self.assertEqual(validator.call_count,8)  # original + promoted, not a third duplicate
        self.assertEqual(calls,['canon','screenplay','director','art','storyboard','compile-review'])


if __name__=='__main__':unittest.main()
