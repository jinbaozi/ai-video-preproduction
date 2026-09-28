"""Opt-in/new-start routing and hard gates; mocks isolate dispatch, not media QA."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ai_comic_drama_workflow.adaptive_control import POLICY, assess
from ai_comic_drama_workflow.lean import start
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import ROOT, read


class AdaptiveWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'project'
        self.sb=read(ROOT/'examples/v52/cafe/storyboard.json')

    def kernel(self, delivery='full'):
        return V5Kernel.initialize(self.root,['Synthetic routing fixture'],delivery=delivery,
                                  workflow_profile='lean',control_policy=POLICY)

    def test_start_pins_policy_but_old_init_has_no_silent_upgrade(self):
        start(self.root,['idea']);self.assertEqual(read(self.root/'project.json')['control_policy'],POLICY)
        old=V5Kernel.initialize(self.root.parent/'old',['idea'])
        self.assertNotIn('control_policy',old.project)

    def test_audited_start_receives_the_same_policy(self):
        with patch('ai_comic_drama_workflow.v6_runtime.V6Runtime.initialize') as init:
            init.return_value.run.return_value={'status':'RUNNING'}
            start(self.root,['idea'],profile='audited')
            self.assertEqual(init.call_args.kwargs['control_policy'],POLICY)

    def test_frozen_policy_cannot_be_removed_from_candidate(self):
        k=self.kernel()
        for config in ({},{'adaptive':{}},{'adaptive':{'policy':'other'}}):
            with self.assertRaises(ValueError):k.adaptive_config_check(config)

    def test_missing_control_cannot_bypass_direct_compile(self):
        k=self.kernel()
        with patch.object(k,'valid',return_value=True),patch.object(k,'data',return_value=self.sb):
            gate=k.adaptive_delivery_gate();self.assertEqual(gate['status'],'BLOCKED')
            self.assertIn('not accepted',gate['reason'])
            with patch.object(k,'modules',side_effect=AssertionError('must not compile')):
                self.assertEqual(k.compile()['status'],'BLOCKED')

    def test_task_gets_plan_without_new_stage_or_report_file(self):
        k=self.kernel();state=k.state
        state['artifacts']['storyboard']={'sha256':'a'*64};k.save(state)
        with patch.object(k,'data',return_value=self.sb),patch.object(k,'dependency',return_value={}),patch.object(k,'task',return_value='control') as task:
            self.assertEqual(k.control_step(),'control')
            self.assertEqual(task.call_args.args[:4],('control','control',6,'video-prompt-compiler'))
            self.assertEqual(task.call_args.kwargs['extra']['adaptive_control']['policy'],POLICY)
        self.assertFalse((k.root/'adaptive-plan.json').exists())

    def test_unknown_camera_returns_native_repair_not_lower_tier(self):
        k=self.kernel();state=k.state;state['artifacts']['storyboard']={'sha256':'a'*64};k.save(state)
        sb=copy.deepcopy(self.sb);sb['timeline']['camera_operations'][0]['operation']='unknown'
        with patch.object(k,'data',return_value=sb):
            response=k.control_step()
            self.assertEqual(response['status'],'BLOCKED');self.assertEqual(response['repair_owner'],'storyboard')

    def test_revision_does_not_reuse_old_ready_record(self):
        k=self.kernel();state=k.state;state['artifacts']['storyboard']={'sha256':'b'*64}
        state['control']={'status':'READY','storyboard_sha256':'a'*64,'policy':POLICY};k.save(state)
        with patch.object(k,'data',return_value=self.sb),patch.object(k,'dependency',return_value={}),patch.object(k,'task',return_value='new') as task:
            self.assertEqual(k.control_step(),'new');task.assert_called_once()

    def test_legacy_trigger_preserved_only_for_legacy_project(self):
        k=V5Kernel.initialize(self.root,['idea']);self.assertTrue(k.control_applicable(self.sb))
        self.assertIsNone(k.adaptive_plan(self.sb));self.assertIsNone(k.adaptive_delivery_gate())

    def test_control_gate_failure_is_in_final_audit(self):
        k=self.kernel()
        with patch.object(k,'adaptive_delivery_gate',return_value={'status':'BLOCKED','reason':'missing current render'}):
            errors=[];k.audit_delivery_errors(errors)
            self.assertIn('missing current render',errors)

    def test_deleting_project_policy_does_not_enable_legacy_bypass(self):
        k=self.kernel();project=read(k.root/'project.json');del project['control_policy']
        k.write('project.json',project)
        altered=V5Kernel(k.root)
        with self.assertRaisesRegex(ValueError,'policy'):altered.require_v5()

    def test_explicit_control_repair_keeps_sources_and_reissues_control(self):
        k=self.kernel();state=k.state
        state['control']={'status':'READY','policy':POLICY,'storyboard_sha256':'a'*64}
        state['artifacts']['storyboard']={'sha256':'a'*64};k.save(state)
        with patch.object(k,'status',return_value={'status':'RUNNING'}),patch.object(k,'data',return_value=self.sb):
            k.revise('control',shot_id='S1')
            self.assertEqual(k.state['control']['status'],'INVALIDATED')
            with patch.object(k,'dependency',return_value={}),patch.object(k,'task',return_value='repair'):
                self.assertEqual(k.control_step(),'repair')
        self.assertTrue(list((k.root/'history').glob('control-*.json')))

    def test_unknown_policy_not_accepted(self):
        with self.assertRaises(ValueError):V5Kernel.initialize(self.root,['idea'],control_policy='skip-checks')

    def test_shared_routing_bytes_match_locked_source(self):
        k=self.kernel();canonical=k.modules('video-prompt-compiler')/'scripts/adaptive_control.py'
        self.assertEqual(canonical.read_bytes(),(ROOT/'src/ai_comic_drama_workflow/adaptive_control.py').read_bytes())
        self.assertEqual(canonical.read_bytes(),(k.modules('image-prompt-optimizer')/'scripts/adaptive_control.py').read_bytes())


class AdaptiveIntegrationTests(unittest.TestCase):
    def test_full_native_text_fixture_remains_planned_not_generated(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts'))
        from run_v5_example import run_example
        with tempfile.TemporaryDirectory() as temp:
            result=run_example(Path(temp)/'fixture','v52','lean',control_policy=POLICY)
            self.assertEqual(result['status'],'DELIVERED')
            k=V5Kernel(Path(temp)/'fixture/project')
            self.assertEqual(k.state['control']['policy'],POLICY)
            self.assertEqual(k.state['control']['materials']['status'],'PLANNED_NOT_RENDERED')
            self.assertEqual(k.state['media'],{})
            self.assertTrue(k.validate(True)['valid'])
            self.assertFalse(k.status()['video_complete'])

    def test_actual_audited_start_pins_native_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'project'
            result=start(root,['Synthetic idea, no actual agent execution'],profile='audited')
            self.assertEqual(read(root/'project.json')['orchestration_protocol'],'6.0')
            self.assertEqual(read(root/'state.json')['control_policy'],POLICY)
            self.assertEqual(result['review_policy'],'independent-per-stage')

    def test_explicit_floor_and_its_freeze(self):
        with tempfile.TemporaryDirectory() as temp:
            k=V5Kernel.initialize(Path(temp)/'project',['fixture'],control_policy=POLICY,control_minimum=4)
            sb=read(ROOT/'examples/v52/cafe/storyboard.json')
            self.assertTrue(all(row['level']==4 for row in k.adaptive_plan(sb)['shots']))
            with patch.object(k,'data',return_value=sb):
                with self.assertRaisesRegex(ValueError,'minimum'):
                    k.adaptive_config_check({'adaptive':{'policy':POLICY},'controls':[]})
            changed=read(k.root/'project.json');changed['control_minimum']=0;k.write('project.json',changed)
            with self.assertRaisesRegex(ValueError,'policy'):V5Kernel(k.root).require_v5()
