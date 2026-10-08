"""Synthetic coverage fixtures; not automatic artistic judgement."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from ai_comic_drama_workflow import stage_quality as q
from ai_comic_drama_workflow.lean import start, step
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import read, digest_file
from ai_comic_drama_workflow.v5_adapters import digest
from tests.test_craft_routing import context, save
from tests.test_v5_workflow import result_for, screenplay
from tests.test_minimal_core import core_result


def fixture_quality(kind, artifact, sha):
    """TEST ONLY: bind synthetic coverage findings, never create production approvals."""
    from ai_comic_drama_workflow.craft_router import pointer
    def strings(v,p):
        if isinstance(v,dict):
            for k,x in v.items():yield from strings(x,p+'/'+k.replace('~','~0').replace('/','~1'))
        elif isinstance(v,list):
            for i,x in enumerate(v):yield from strings(x,p+'/'+str(i))
        elif isinstance(v,str) and v.strip():yield p,v
    rows=[]
    for scope in q.scopes(kind,artifact):
        path,text=max((item for item in strings(pointer(artifact,scope) if scope else artifact,scope) if not any(part in {'id','source_refs','sha256','schema','schema_version','style_id'} for part in item[0].split('/'))),key=lambda item:len(item[1]))
        for check in q.CHECKS[kind]:
            rows.append(dict(scope=scope,check=check,status='PASS',finding='SYNTHETIC coverage only, not artistic or media assessment.',evidence=[dict(pointer=path,quote=text)]))
    return dict(policy=q.POLICY,artifact_sha256=sha,findings=rows)


class QualityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.script={'narrative':{'events':[{'description':'先备好早餐；误以为迟到，决定不吃，拿包去玄关换鞋。'},{'description':'在玄关拿到手机，看到周六日期后才意识到休息，回到已备早餐。'}]}}
        self.sha=digest(self.script);self.review=fixture_quality('screenplay',self.script,self.sha)
    def validate(self):q.validate('screenplay',self.script,self.review,self.sha)
    def test_valid_bound_coverage(self):self.validate()
    def test_missing_resource_origin(self):
        self.review['findings']=[r for r in self.review['findings'] if r['check']!='resource_origin']
        with self.assertRaisesRegex(ValueError,'Missing scoped'):self.validate()
    def test_host_detected_breakfast_gap_blocks(self):
        self.review['findings'][3].update(status='FAIL',finding='早餐来源未交代。')
        with self.assertRaisesRegex(ValueError,'Failed quality'):self.validate()
    def test_changed_hash(self):
        with self.assertRaisesRegex(ValueError,'stale'):q.validate('screenplay',self.script,self.review,'new')
    def test_invented_quote(self):
        self.review['findings'][0]['evidence'][0]['quote']='不存在的对白'
        with self.assertRaisesRegex(ValueError,'absent'):self.validate()
    def test_other_event_evidence(self):
        self.review['findings'][0]['evidence']=self.review['findings'][-1]['evidence']
        with self.assertRaisesRegex(ValueError,'own event'):self.validate()
    def test_id_is_not_substantive_evidence(self):
        self.script['narrative']['events'][0]['id']='E1'
        self.review['findings'][0]['evidence']=[{'pointer':'/narrative/events/0/id','quote':'E1'}]
        with self.assertRaisesRegex(ValueError,'substantive'):self.validate()
    def test_duplicate(self):
        self.review['findings'][-1]=deepcopy(self.review['findings'][0])
        with self.assertRaisesRegex(ValueError,'duplicate'):self.validate()
    def test_prompt_completeness_no_word_quota(self):
        a={'prompt':'右肩后方看手机屏幕；右手握持；晨光；单一静止时刻。'};r=fixture_quality('image-prompt',a,digest(a))
        q.validate('image-prompt',a,r,digest(a));r['findings'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):q.validate('image-prompt',a,r,digest(a))
    def test_contracts(self):
        for kind in q.CHECKS:self.assertIn('checks',q.contract(kind))


class StudioStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        start(self.root/'p',['成年人物先备早餐，误以为工作日，在手机看到周六后才返回用餐。'],delivery='text-only');self.k=V5Kernel(self.root/'p')
    def canon(self,k=None):
        k=k or self.k;t=k.run()['task'];src=k.state['sources'][0]
        a=dict(project_id='PROJECT',content=k.path(src['uri']).read_text(),source_refs=[src['id']],entities=[{'id':'A'},{'id':'B'}],locks=[])
        p=save(self.root/('canon-'+k.root.name+'.json'),a)
        extra={'craft_context':context(k)} if k.project.get('craft_policy')!='off' else {}
        k.submit(core_result(result_for(t,artifact=str(p),artifact_sha256=digest_file(p),**extra)));return k.run()['task']
    def test_routes_registered_practitioner_not_yet_adopted(self):
        t=self.canon();self.assertTrue(t['craft']['practitioner']['name']);self.assertEqual(t['quality_contract']['policy'],q.POLICY)
        report=self.k.status()['stage_report'];self.assertEqual(report['active']['status'],'SELECTED_NOT_ADOPTED');self.assertEqual(report['active']['practitioner'],t['craft']['practitioner']);self.assertEqual(len(report['stages']),1)
    def test_missing_quality_blocks_native(self):
        t=self.canon();p=save(self.root/'script.json',screenplay(self.k));r=core_result(result_for(t,artifact=str(p),artifact_sha256=digest_file(p)))
        before=self.k.state['completed_tasks'].copy()
        with self.assertRaisesRegex(ValueError,'quality_review'):self.k.submit(r)
        self.assertEqual(before,self.k.state['completed_tasks']);self.assertNotIn('screenplay',self.k.state['artifacts'])
    def test_off_keeps_quality_old_projects_unchanged(self):
        start(self.root/'off',['测试'],craft_routing='off',delivery='text-only');cfg=read(self.root/'off/project.json')
        self.assertEqual(cfg['craft_policy'],'off');self.assertEqual(cfg['quality_policy'],q.POLICY)
        old=V5Kernel.initialize(self.root/'old',['已有项目'],delivery='text-only',craft_policy='off');before=(old.root/'project.json').read_bytes();step(old.root)
        self.assertEqual(before,(old.root/'project.json').read_bytes());self.assertNotIn('quality_policy',old.project)
    def test_receipt_binding_idempotency_and_tamper(self):
        start(self.root/'off',['原创测试'],craft_routing='off',delivery='text-only');k=V5Kernel(self.root/'off');t=self.canon(k)
        a=screenplay(k);a['project_id']=k.project['project_id'];a['sources'][0]['excerpt']=k.path(k.state['sources'][0]['uri']).read_text();a['review']['content_sha256']=k.screenplay_protocol().content_hash(a);p=save(self.root/'s.json',a);review=fixture_quality('screenplay',a,digest_file(p));review.pop('artifact_sha256')
        r=core_result(result_for(t,artifact=str(p),artifact_sha256=digest_file(p),quality_review=review))
        self.assertEqual(k.submit(r)['status'],'ACCEPTED');self.assertEqual(k.submit(r)['status'],'ALREADY_ACCEPTED');self.assertTrue(k.valid('screenplay'))
        self.assertEqual(k.status()['stage_report']['stages'][-1]['quality_evidence'],'ACCEPTED_HOST_DECLARED')
        proof=k.path(k.state['artifacts']['screenplay']['quality_proof']['uri']);proof.write_text('{}');self.assertFalse(k.valid('screenplay'))
        self.assertEqual(k.status()['stage_report']['stages'][-1]['native_status'],'STALE_OR_UNREVIEWED')


class StudioDeliveryIntegrationTests(unittest.TestCase):
    def test_native_studio_routes_adopts_and_refuses_changed_compile_proof(self):
        import sys
        from ai_comic_drama_workflow.v5_modules import ROOT
        sys.path.insert(0,str(ROOT/'scripts'))
        from run_v5_example import run_example
        from ai_comic_drama_workflow import workspace
        with tempfile.TemporaryDirectory() as tmp:
            response=run_example(Path(tmp)/'demo','v52',studio=True)
            self.assertEqual(response['status'],'DELIVERED')
            self.assertEqual(response['progress']['status'],'DELIVERED')
            k=V5Kernel(Path(tmp)/'demo/project');report=k.status()['stage_report']
            owners={r['kind']:r for r in report['stages']}
            for kind in ('screenplay','director','art','storyboard','compile-review'):
                self.assertEqual(owners[kind]['method_evidence'],'ACCEPTED_HOST_DECLARED')
                self.assertEqual(owners[kind]['quality_evidence'],'ACCEPTED_HOST_DECLARED')
            self.assertFalse(k.status()['video_complete'])
            record=k.state['compile_review'];proof=k.path(record['quality_proof']['uri']);saved=read(proof)
            saved['quality_review']['findings'][0]['finding']='changed after acceptance'
            save(proof,saved)
            self.assertFalse(q.compile_proof_valid(k))
            self.assertNotEqual(workspace.progress(k)['stages'][7]['status'],'已完成')
            self.assertFalse(k.validate(True)['valid'])
            self.assertEqual(k.status()['status'],'BLOCKED')
            self.assertFalse(k.status()['preproduction_complete'])
