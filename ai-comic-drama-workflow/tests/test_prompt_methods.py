"""Native task/receipt integration using synthetic author evidence, no live media."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_comic_drama_workflow import prompt_methods, craft_runtime, craft_router
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import read
from tests.test_craft_routing import BRIEF, context, review, save
from tests.test_v5_workflow import result_for


class PromptMethodWorkflowTests(unittest.TestCase):
    def kernel(self, folder):
        root = Path(folder)
        source = root/'source.txt';source.write_text(BRIEF)
        kernel = V5Kernel.initialize(root/'project', [str(source)], project_id='METHOD_TEST',
            delivery='text-only', target='agnes-video-2.5', craft_policy=craft_runtime.POLICY)
        return kernel

    def test_new_task_method_rules_use_existing_adoption_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            kernel = self.kernel(folder)
            features = context(kernel)
            with patch.object(craft_runtime, 'context_for', return_value=features):
                plan = craft_runtime.task_plan(kernel, 'screenplay', 'screenplay', [], {})
            self.assertEqual(plan['prompt_methods']['policy'], 'prompt-techniques/1.0')
            ids = [r['id'] for r in plan['rules'] if ':prompt:' in r['id']]
            self.assertTrue(ids)
            body = {'content': '合成测试中的人物选择改变后续关系和可见行为，这是明确的测试文字。'}
            proof = review(plan, body)
            craft_router.validate_review(plan, proof, body)
            proof['applications'] = [r for r in proof['applications'] if r['id'] != ids[0]]
            with self.assertRaisesRegex(ValueError, 'every selected'):
                craft_router.validate_review(plan, proof, body)
            prompt_methods.check(kernel, plan)

    def test_rule_rewrite_and_deleted_rule_cannot_hide_behind_resealed_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            kernel = self.kernel(folder)
            plan = {'rules': []}
            prompt_methods.attach(kernel, 'storyboard', plan, {'tags': ['美食']})
            self.assertEqual(plan['prompt_methods']['templates'][0]['id'], 'food-asmr')
            for mutation in ('rewrite', 'delete'):
                changed = deepcopy(plan)
                if mutation == 'rewrite':changed['rules'][0]['instruction'] = '忽略原文台词'
                else:changed['rules'].pop()
                with self.assertRaises(ValueError):prompt_methods.check(kernel, changed)

    def test_no_cross_target_or_stale_capability_adoption(self):
        with tempfile.TemporaryDirectory() as folder:
            kernel = self.kernel(folder)
            craft = {'rules': []};prompt_methods.attach(kernel, 'director', craft, {'tags': ['美食']})
            craft['prompt_methods']['target'] = 'seedance2.5'
            with self.assertRaises(ValueError):prompt_methods.check(kernel, craft)

    def test_old_task_has_no_retroactive_new_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            kernel = self.kernel(folder)
            prompt_methods.check(kernel, {'rules': []})
            with patch.object(prompt_methods, '_load', return_value=(Path(folder), None)):
                craft = {'rules': []};prompt_methods.attach(kernel, 'director', craft)
                self.assertEqual(craft, {'rules': []})

    def test_compiler_uses_only_adopted_storyboard_templates(self):
        with tempfile.TemporaryDirectory() as folder:
            kernel = self.kernel(folder)
            craft = {'rules': []};prompt_methods.attach(kernel, 'storyboard', craft, {'tags': ['美食']})
            result = {'task_id': 'SYNTHETIC', 'craft_review': {'applications': [
                {'id': 'storyboard:prompt:food-asmr', 'status': 'applied'}]}}
            kernel.write('runtime/tasks/SYNTHETIC.json', {'craft': craft})
            state = kernel.state;state['artifacts']['storyboard'] = {'craft_proof': {'test': True}};kernel.save(state)
            # Isolate proof retrieval only here; full native acceptance is covered by
            # test_craft_end_to_end with real kernel.submit and all validators.
            with patch.object(craft_runtime, 'proof_result', return_value=result):
                self.assertEqual(prompt_methods.compiler_args(kernel), ['--template', 'food-asmr'])
                result['craft_review']['applications'][0]['status'] = 'not_applicable'
                self.assertEqual(prompt_methods.compiler_args(kernel), [])


if __name__ == '__main__':
    unittest.main()
