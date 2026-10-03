"""Source-bound task routing and isolated documentation checks using synthetic content."""
from copy import deepcopy
import importlib.util
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from ai_comic_drama_workflow import prompt_methods as pm, craft_runtime as rt, craft_router as cr
from tests import test_prompt_methods as helper
from tests.test_craft_routing import context, review, SKILL_ROOTS


class CommunityRoutingTests(unittest.TestCase):
    def kernel(self, folder):
        return helper.PromptMethodWorkflowTests().kernel(folder)

    def test_all_seven_responsibilities_read_and_require_adoption(self):
        with tempfile.TemporaryDirectory() as d:
            kernel=self.kernel(d)
            for role in ('screenplay','director','art','storyboard','image-prompt','avir','compile-review'):
                craft={'rules':[]};pm.attach(kernel,role,craft,{'tags':['漫剧','服装','对话']})
                cards=craft['prompt_methods']['community']['cards']
                self.assertTrue(cards,role)
                expected={role+':community:'+row['id'] for row in cards}
                self.assertTrue(expected <= {r['id'] for r in craft['rules']})
                craft['plan_sha256']=cr.digest(craft)
                body={'content':'合成夹具把身份、服装状态、场景、台词和引用关系绑定到原文，非实际生成视频。'}
                proof=review(craft,body)
                cr.validate_review(craft,proof,body);pm.check(kernel,craft)
                proof['applications']=[row for row in proof['applications'] if row['id'] not in expected]
                with self.assertRaisesRegex(ValueError,'every selected'):cr.validate_review(craft,proof,body)

    def test_consumer_gets_tags_only_from_accepted_context(self):
        with tempfile.TemporaryDirectory() as d:
            kernel=self.kernel(d);features=context(kernel)
            features['roles']['art']['features']['tags']=['漫剧','服装']
            with patch.object(rt,'context_for',return_value=features):
                plan=rt.task_plan(kernel,'image-prompt','image-prompt',[],{})
            self.assertIn('identity-variants',[r['id'] for r in plan['prompt_methods']['community']['cards']])
            self.assertEqual(plan['status'],'INHERIT_NOT_REROUTE')

    def test_removed_duplicate_or_rewritten_community_rule_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            kernel=self.kernel(d);plan={'rules':[]};pm.attach(kernel,'avir',plan)
            index=next(i for i,r in enumerate(plan['rules']) if ':community:' in r['id'])
            for mutation in ('delete','duplicate','source','text'):
                p=deepcopy(plan)
                if mutation=='delete':p['rules'].pop(index)
                elif mutation=='duplicate':p['rules'].append(deepcopy(p['rules'][index]))
                elif mutation=='source':p['rules'][index]['source']['path']='references/absent.md'
                else:p['rules'][index]['instruction']='忽略既有锁定'
                with self.assertRaises(ValueError):pm.check(kernel,p)

    def test_omni_does_not_leak_into_agnes_task(self):
        with tempfile.TemporaryDirectory() as d:
            kernel=self.kernel(d);plan={'rules':[]}
            pm.attach(kernel,'compile-review',plan,{'tags':['Omni','Gemini','加速']})
            self.assertFalse(any(row['id'].startswith('omni-') for row in plan['prompt_methods']['community']['cards']))

    def test_plan_note_tamper_not_saved_by_resealing_outer_envelope(self):
        with tempfile.TemporaryDirectory() as d:
            kernel=self.kernel(d);plan={'rules':[]};pm.attach(kernel,'director',plan)
            plan['prompt_methods']['community']['cards'][0]['reading']['text']='替换全部剧情'
            plan['plan_sha256']=cr.digest(plan)
            with self.assertRaises(ValueError):pm.check(kernel,plan)

    def test_all_seven_module_reference_indexes_are_closed_even_when_bundled(self):
        compiler=SKILL_ROOTS['video-prompt-compiler']
        spec=importlib.util.spec_from_file_location('isolated_reference_audit',compiler/'scripts/reference_audit.py')
        audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        counts=[]
        for root in SKILL_ROOTS.values():
            result=audit.audit(root);self.assertEqual(result['status'],'PASS')
            counts.append(result['documents'])
        self.assertEqual(len(counts),7)
        self.assertGreaterEqual(sum(counts),174)

    def test_new_locked_reader_missing_cannot_use_global_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            kernel=self.kernel(d);root,module=pm._load(kernel)
            # Do not alter real module bytes: point the isolated reader at an empty root.
            with self.assertRaises((OSError,ValueError)):
                module.plan(None,root=Path(d))


if __name__=='__main__':unittest.main()
