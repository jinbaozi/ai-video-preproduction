"""New policy defaults preserve old projects and all non-creative permission gates."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_comic_drama_workflow.lean import start
from ai_comic_drama_workflow.production import ProductionLedger
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_cli import main
from ai_comic_drama_workflow.v5_modules import read
from ai_comic_drama_workflow import workspace
from ai_comic_drama_workflow.editing import execute_edit, verify_editing_record


class PipelinePolicies(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'project'

    def kernel(self, **options):
        start(self.root,['Adult traveler finds a letter'],**options)
        return V5Kernel(self.root)

    def media(self,kernel):
        kernel.write('assets/REF/a.png',b'fixture')
        media={'key':'REF','uri':'assets/REF/a.png','sha256':'a'*64,'revision':1,
               'input_fingerprint':'original','role':'identity','stage':5,'entity_id':'ADULT',
               'shot_id':None,'visual_review':{'status':'PASS','findings':['Actually observed fixture'], 'sha256':'a'*64}}
        state=kernel.state;state['media']['REF']=media;state['active_task']=None;kernel.save(state)
        return media

    def test_new_full_defaults_but_old_init_unchanged(self):
        kernel=self.kernel()
        self.assertEqual(kernel.project['creative_policy'],'automatic')
        self.assertEqual(kernel.project['flow_refinement']['policy'],'google-flow-2k/1.0')
        self.assertEqual(kernel.project['editing_backend'],'jianying-headless')
        self.assertTrue(ProductionLedger(kernel).strict)
        old=V5Kernel.initialize(Path(self.temp.name)/'old',['idea'])
        for key in ('creative_policy','flow_refinement','editing_backend','production_policy'):
            self.assertNotIn(key,old.project)
        self.assertFalse(ProductionLedger(old).strict)

    def test_text_only_does_not_require_images(self):
        kernel=self.kernel(delivery='text-only')
        self.assertNotIn('flow_refinement',kernel.project)
        self.assertEqual(kernel.flow_delivery_errors(),[])

    def test_frozen_policy_cannot_be_removed(self):
        kernel=self.kernel()
        config=dict(kernel.project);config.pop('flow_refinement')
        kernel.write('project.json',config)
        with self.assertRaisesRegex(ValueError,'Frozen'):
            V5Kernel(self.root).run()
        with self.assertRaisesRegex(ValueError,'Frozen'):
            ProductionLedger(V5Kernel(self.root))

    def test_account_is_only_local_explicit_configuration(self):
        kernel=self.kernel(flow_account='example@example.org')
        self.assertEqual(kernel.project['flow_refinement']['account_hint'],'example@example.org')

    def test_audited_flow_freezes_real_graph_gates(self):
        self.kernel(profile='audited',reference_refinement='google-flow-2k')
        from ai_comic_drama_workflow.v6_runtime import V6Runtime
        runtime=V6Runtime(self.root)
        nodes={node['id']:node for node in runtime.graph['nodes']}
        self.assertIn('reference_2k',nodes['storyboard']['depends_on'])
        self.assertIn('board_reference_2k',nodes['compile']['depends_on'])
        self.assertEqual(nodes['reference_2k']['checkers'],['flow_2k_provenance','flow_2k_visual_review'])

    def test_automatic_identity_still_waits_for_flow(self):
        kernel=self.kernel();media=self.media(kernel)
        job={'key':'REF','fingerprint':'original','brief':{}}
        with patch.object(kernel,'image_jobs',return_value=[job]),patch.object(kernel,'media_valid',return_value=True),patch('ai_comic_drama_workflow.flow.plan_refinement',return_value={'status':'AWAITING_FLOW_REFINEMENT'}) as plan:
            self.assertEqual(kernel.images_step(5)['status'],'AWAITING_FLOW_REFINEMENT')
            plan.assert_called_once()
        self.assertNotIn('REF',kernel.state['approvals'])

    def test_automatic_identity_is_actual_agent_choice_not_user_claim(self):
        kernel=self.kernel(reference_refinement='off');media=self.media(kernel)
        with patch.object(kernel,'image_jobs',return_value=[{'key':'REF','fingerprint':'original','brief':{}}]),patch.object(kernel,'media_valid',return_value=True):
            self.assertIsNone(kernel.images_step(5))
        approval=kernel.state['approvals']['REF']
        self.assertEqual(approval['actor'],'current-agent')
        self.assertEqual(approval['token'],kernel.approval_token(media))
        self.assertEqual(approval['evidence']['visual_review'],media['visual_review'])

    def test_ask_policy_retains_identity_approval(self):
        kernel=self.kernel(creative_policy='ask',reference_refinement='off');self.media(kernel)
        with patch.object(kernel,'image_jobs',return_value=[{'key':'REF','fingerprint':'original','brief':{}}]),patch.object(kernel,'media_valid',return_value=True):
            self.assertEqual(kernel.images_step(5)['status'],'AWAITING_USER_DECISION')

    def test_creative_choice_auto_but_cost_not_auto(self):
        kernel=self.kernel(delivery='text-only')
        creative={'kind':'creative','question':'Use warm light?','rationale':'Matches the accepted hopeful tone'}
        result=kernel.request_decision(creative)
        self.assertEqual(result['status'],'ACCEPTED');self.assertFalse(result['user_approval'])
        self.assertIsNone(kernel.state['active_decision'])
        result=kernel.request_decision({'kind':'cost','question':'Pay for extra credits?'})
        self.assertEqual(result['status'],'AWAITING_USER_DECISION')

    def test_unsupported_or_empty_automatic_decision_cannot_be_accepted(self):
        kernel=self.kernel(delivery='text-only')
        with self.assertRaisesRegex(ValueError,'rationale'):
            kernel.request_decision({'kind':'creative','question':'Change something?'})
        with self.assertRaisesRegex(ValueError,'concrete'):
            kernel.request_decision({'kind':'authentication','question':'Log in?'})

    def test_compile_cannot_skip_flow(self):
        kernel=self.kernel()
        with patch.object(kernel,'valid',return_value=True),patch.object(kernel,'flow_delivery_errors',return_value=['Flow required']),patch.object(kernel,'adaptive_delivery_gate') as later:
            self.assertEqual(kernel.compile()['status'],'BLOCKED')
            later.assert_not_called()

    def test_explicit_edit_stage_uses_jianying_without_ffmpeg_fallback(self):
        kernel=self.kernel(delivery='text-only')
        with patch('ai_comic_drama_workflow.jianying.assemble_jianying',return_value={'status':'BLOCKED','reason':'Authorization required'}) as edit,patch('ai_comic_drama_workflow.editing.assemble_ffmpeg') as fallback:
            result=execute_edit(kernel,[],self.root/'out.mp4',{})
            self.assertEqual(result['status'],'BLOCKED');edit.assert_called_once();fallback.assert_not_called()

    def test_fake_handoff_cannot_count_as_completed_edit(self):
        kernel=self.kernel(delivery='text-only')
        with self.assertRaisesRegex(ValueError,'has not run'):
            verify_editing_record(kernel,{'tool':'ffmpeg','status':'CHECKED'})
        with self.assertRaisesRegex(ValueError,'pinned'):
            verify_editing_record(kernel,{'tool':'jianying','editing':{'core_commit':'fake'}})

    def test_new_compact_final_edit_path_is_separate_and_old_is_unchanged(self):
        kernel=self.kernel(production_target='video',delivery='text-only')
        self.assertEqual(workspace.relative(kernel.project,'runtime/production/outputs/a.mp4'),'11-edit/outputs/a.mp4')
        self.assertEqual(workspace.relative(kernel.project,'runtime/production/media/a.mp4'),'10-video/media/a.mp4')
        old={'output_policy':workspace.POLICY}
        self.assertEqual(workspace.relative(old,'runtime/production/outputs/a.mp4'),'10-video/outputs/a.mp4')
        self.assertFalse((self.root/'11-edit').exists())

    def test_verified_lean_terminal_transition_does_not_require_v6_graph(self):
        kernel=self.kernel(production_target='video',delivery='text-only')
        ledger=ProductionLedger(kernel)
        with patch.object(ledger,'video_delivery_blockers',return_value=['Missing edit']):
            self.assertEqual(ledger.mark_video_delivered()['status'],'BLOCKED')
        with patch.object(ledger,'video_delivery_blockers',return_value=[]),patch('ai_comic_drama_workflow.production.workspace.update_progress'):
            self.assertEqual(ledger.mark_video_delivered()['status'],'VIDEO_DELIVERED')

    def test_reference_cli_requires_real_result(self):
        kernel=self.kernel()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code=main(['reference',str(self.root),'receive','--media-key','REF'])
        self.assertEqual(code,1);self.assertIn('requires --result',out.getvalue())


class EvidenceIntegration(unittest.TestCase):
    def setUp(self):
        try:
            from tests.test_jianying_adapter import AdapterTests
        except ImportError:
            from test_jianying_adapter import AdapterTests
        self.fixture=AdapterTests(methodName='runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.temp.cleanup)
        self.fixture.edl[0]['shot_id']='S1'
        self.fixture.spec['preserve_native_audio']=True
        self.kernel=V5Kernel.initialize(self.fixture.root/'project',['idea'],delivery='text-only',
            workflow_profile='lean',editing_backend='jianying-headless',production_policy='verified-production/1.0')
        self.result=self.fixture.assemble()
        self.assertEqual(self.result['status'],'CHECKED')
        self.record={'id':'ASM_TEST','tool':'jianying','status':'CHECKED','edl':self.fixture.edl,
            'project_timeline':{'ranges':[],'unit':'project_ms'},
            'media_timeline':{'ranges':[],'unit':'media_frame'},
            'post_timeline':{'ranges':[],'unit':'post_ms'},
            'probe':self.result['probe'],'output_sha256':self.result['output_sha256'],
            'editing':self.result['editing']}
        self.manifest={'output_spec':self.fixture.spec,'shot_ids':['S1'],
            'shot_ranges':{'S1':{'start_ms':0,'end_ms':1000}}}
        self.kernel.write('runtime/production/delivery-manifest.json',self.manifest)

    def test_manifest_cannot_be_reused_for_other_edl_spec_or_output(self):
        with patch('ai_comic_drama_workflow.jianying.probe_media',side_effect=self.fixture.probe):
            verify_editing_record(self.kernel,self.record)
            for field,value in [('output_sha256','f'*64),('edl',[dict(self.fixture.edl[0],src_in_frame=5)])]:
                with self.subTest(field=field),self.assertRaises(ValueError):
                    verify_editing_record(self.kernel,dict(self.record,**{field:value}))
            changed=copy.deepcopy(self.manifest);changed['output_spec']['width']=128
            self.kernel.write('runtime/production/delivery-manifest.json',changed)
            with self.assertRaisesRegex(ValueError,'spec'):
                verify_editing_record(self.kernel,self.record)

    def test_parent_relative_output_artifact_paths_normalize_consistently(self):
        record=copy.deepcopy(self.record)
        for row in record['editing']['files']:
            path=Path(row['path']);row['path']=str(path.parent/'..'/path.parent.name/path.name)
        with patch('ai_comic_drama_workflow.jianying.probe_media',side_effect=self.fixture.probe):
            verify_editing_record(self.kernel,record)

    def test_strict_ledger_saves_canonical_probe_and_owned_editing_snapshot(self):
        ledger=ProductionLedger(self.kernel)
        take={'probe':self.fixture.probe(self.fixture.source),'uri':str(self.fixture.source.relative_to(self.kernel.root)) if self.fixture.source.is_relative_to(self.kernel.root) else 'source.mp4'}
        # Register fixture source within the project, then adapt frozen source paths
        # would alter manifest; use a contained-kernel resolver for this test only.
        real_path=self.kernel.path
        def path(uri):return self.fixture.source if uri=='source.mp4' else real_path(uri)
        def load(uri):
            if uri=='delivery-manifest.json':return self.manifest
            if uri=='selections/S1.json':return {'take_id':'TAKE_1'}
            if uri=='takes/TAKE_1.json':return take
            raise AssertionError(uri)
        with patch.object(ledger,'_load',side_effect=load),patch.object(ledger,'_verify_manifest'),patch.object(ledger,'_verify_take'),patch.object(self.kernel,'path',side_effect=path),patch('ai_comic_drama_workflow.production._probe',return_value=self.result['probe']),patch('ai_comic_drama_workflow.jianying.probe_media',side_effect=self.fixture.probe):
            saved=ledger.save_assembly(self.record,output_path=self.fixture.output)
            self.assertEqual(saved['probe'],self.result['probe'])
            self.assertTrue(all(not Path(row['path']).is_absolute() for row in saved['editing']['files']))
            verify_editing_record(self.kernel,saved)
            victim=self.kernel.path(saved['editing']['files'][0]['path']);victim.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'changed'):
                verify_editing_record(self.kernel,saved)


class RecoveryAndCurrentBuild(unittest.TestCase):
    setUp=PipelinePolicies.setUp
    kernel=PipelinePolicies.kernel
    media=PipelinePolicies.media
    def test_receipt_replay_preserves_accepted_downstream_state(self):
        kernel=self.kernel();media=self.media(kernel);media['flow_refinement']={'fixture':True}
        state=kernel.state;state['media']['REF']=media
        state['build']={'build_id':'accepted-build'};state['compile_review']={'status':'ACCEPTED'}
        state['approvals']={'REF':{'token':'retained'}};state['status']='DELIVERED';kernel.save(state)
        before=kernel.state
        with patch.object(kernel,'media_valid',return_value=True),patch('ai_comic_drama_workflow.flow.accept_refinement',return_value=media),patch('ai_comic_drama_workflow.v5.workspace.update_progress'):
            result=kernel.flow_action('REF',result={'status':'SUCCEEDED'})
        self.assertEqual(result['status'],'ALREADY_ACCEPTED');self.assertEqual(kernel.state,before)

    def test_new_lean_cannot_plan_or_deliver_with_stale_preproduction(self):
        kernel=self.kernel(production_target='video',delivery='text-only');ledger=ProductionLedger(kernel)
        with self.assertRaisesRegex(ValueError,'preproduction'):
            ledger.plan_job({},'not-a-hash',[],[],{},compile_path=self.root/'invented.json')
        self.assertEqual(ledger.mark_video_delivered()['status'],'BLOCKED')
        with patch.object(kernel,'validate',return_value={'valid':True,'errors':[]}):
            with self.assertRaisesRegex(ValueError,'current accepted build'):
                ledger._verify_current_preproduction(self.root/'invented.json')


if __name__=='__main__':unittest.main()
