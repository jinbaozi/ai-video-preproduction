"""Synthetic routing/provenance tests, not LLM, human taste or generated-video evaluation."""
from copy import deepcopy
import json
import atexit
import zipfile
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ai_comic_drama_workflow import craft_router as cr, craft_runtime as rt
from ai_comic_drama_workflow.lean import start
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import ROOT, read, digest_file
from ai_comic_drama_workflow.v5_adapters import encoded, digest

REPO = ROOT.parent
SKILL_ROOTS = {name: REPO/name for name in (*cr.ROLES.values(), 'image-prompt-optimizer', 'video-prompt-compiler')}
if not all(path.is_dir() for path in SKILL_ROOTS.values()):
    _isolated = tempfile.TemporaryDirectory(prefix='craft-bundled-tests-')
    atexit.register(_isolated.cleanup)
    for name in SKILL_ROOTS:
        with zipfile.ZipFile(ROOT/'assets/bundled-skills'/(name+'.skill')) as archive:
            archive.extractall(_isolated.name)
        SKILL_ROOTS[name] = Path(_isolated.name)/name
SKILL_ROOTS['ai-comic-drama-workflow'] = ROOT
BRIEF = '五名陌生人在停业密室搜证，各自隐瞒往事。观众逐渐接近真相；不能提前揭露隐瞒者。'


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))
    return path


def context(kernel):
    src = kernel.state['sources'][0]
    quote = kernel.path(src['uri']).read_text()[:20]
    specs = {
        'screenplay': {'tags': ['人物'], 'goal': '让人物选择及其后果在原文范围内成立。'},
        'director': {'tags': ['关系', '克制'], 'goal': '用可见迟疑和关系距离表现人物信任。', 'task': 'narrative'},
        'art': {'tags': ['当代', '日常'], 'goal': '保留当代室内的材料、生活痕迹和身份。', 'world_mode': 'contemporary', 'medium': 'live_action'},
        'storyboard': {'tags': ['对话', '关系'], 'goal': '交代视点与行动反应，保持空间与道具连续。'},
    }
    return {'source_sha256': rt.source_hash(kernel), 'roles': {
        role: {'features': features, 'evidence': [{'source_id': src['id'], 'quote': quote}]}
        for role, features in specs.items()}}


def review(plan, artifact, pointer='/content'):
    text = cr.pointer(artifact, pointer)
    return {'plan_sha256': plan['plan_sha256'], 'rationale': '合成测试只核对字段、内容与规则的证据绑定，不证明艺术质量。',
            'semantic_review': True, 'applications': [
                {'id': rule['id'], 'status': 'applied', 'reason': '合成测试中的现有正文包含可定位的内容。',
                 'pointer': pointer, 'quote': text[:40], 'value_sha256': cr.digest(text),
                 'check': '合成测试复查这段字符串与指定位置的字节，不进行真实审片。'}
                for rule in plan.get('rules', []) + plan.get('inherited', [])]}


class RoutingTests(unittest.TestCase):
    def route(self, role, query, analysis=None):
        return cr.route(SKILL_ROOTS[cr.ROLES[role]], role, query, analysis)

    def test_unnamed_mystery_routes_methods_and_practitioner(self):
        for role, expected in [('screenplay', 'restricted_mystery'), ('director', 'restrained_suspense'), ('storyboard', 'suspense')]:
            with self.subTest(role=role):
                plan = self.route(role, BRIEF)
                self.assertEqual(plan['primary'], expected)
                self.assertFalse(plan['explicit'])
                self.assertTrue(plan['rules'])
                if role != 'storyboard':
                    self.assertTrue(plan['practitioner']['name'])
                    self.assertTrue(any(r['id'].endswith('practitioner_method') for r in plan['rules']))
                    self.assertEqual(plan['practitioner']['attribution'], 'project_interpretation_not_independently_verified')

    def test_narrative_goal_outranks_cosmetic_tags(self):
        plan = self.route('director', BRIEF + '色彩冷暖转换、焦点从钥匙转向表情。')
        self.assertEqual(plan['primary'], 'restrained_suspense')
        self.assertIn('director:rack_focus', [r['id'] for r in plan['rules']])
        self.assertLessEqual(len(plan['rules']), 6)

    def test_quiet_gesture_is_not_action_movie(self):
        self.assertEqual(self.route('storyboard', '父女重逢，用一个安静动作表达亲情')['primary'], 'transparent')
        self.assertEqual(self.route('director', '父女在厨房安静重逢，沉默中表达亲情')['primary'], 'intimate_subtext')

    def test_teaching_does_not_force_plot(self):
        for role, expected in [('screenplay', 'non_dramatic'), ('director', 'movement_clarity')]:
            self.assertEqual(self.route(role, '太空滑步教学，完整展示步法。不要悬疑和反转。')['primary'], expected)

    def test_product_uses_evidence_not_heroic_spectacle(self):
        self.assertEqual(self.route('director', 'product demonstration, show material and operation without a mystery plot')['primary'], 'product_evidence')

    def test_action_path_is_action(self):
        self.assertEqual(self.route('storyboard', '追逐打斗，必须看清动作路径与接触')['primary'], 'action')

    def test_semantic_host_features_supersede_incidental_keywords(self):
        plan = self.route('director', '主角回忆往事，城市背景。', {'tags': ['关系', '克制'], 'goal': '以父子之间的行为反应表达和解。'})
        self.assertEqual(plan['primary'], 'intimate_subtext')
        self.assertIn('host_semantic', plan['selection_basis'])

    def test_explicit_name_routes_without_name_dump(self):
        plan = self.route('director', '参考李安，克制的父女重逢。')
        self.assertEqual(plan['practitioner']['name'], '李安')
        self.assertTrue(plan['explicit'])
        self.assertTrue(all(r['instruction'] != '李安' for r in plan['rules']))

    def test_negated_name_is_not_selected(self):
        self.assertNotEqual((self.route('director', '英雄登场，但不要参考迈克尔·贝。')['practitioner'] or {}).get('name'), '迈克尔·贝')

    def test_names_in_story_are_not_explicit_style_requests(self):
        self.assertFalse(self.route('director', '两人在影院聊到李安，随后开始调查失踪线索。')['explicit'])

    def test_conflicting_named_profiles_block(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            self.route('director', '参考李安，参考张艺谋。')

    def test_unknown_request_blocks(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            self.route('director', BRIEF, {'requested': 'unknown-master'})

    def test_explicit_reference_cannot_override_task(self):
        with self.assertRaisesRegex(ValueError, 'compatible'):
            self.route('director', '参考李安做步法教学', {'requested': '李安', 'task': 'demonstration'})

    def test_unknown_negative_constraint_blocks(self):
        with self.assertRaisesRegex(ValueError, 'Unknown forbidden'):
            self.route('director', BRIEF, {'forbidden_techniques': ['imaginary_camera']})

    def test_forbidden_profile_cannot_be_explicitly_selected(self):
        with self.assertRaisesRegex(ValueError, 'compatible'):
            self.route('director', BRIEF, {'requested': 'restrained_suspense', 'forbidden_profiles': ['restrained_suspense']})

    def test_art_world_and_medium_are_hard_filters(self):
        plan = self.route('art', '远未来维护中的太空站，工业材料层叠。', {'tags': ['工业', '科幻'], 'goal': '用维修痕迹表现空间功能。', 'world_mode': 'future', 'medium': 'live_action'})
        self.assertEqual(plan['primary'], 'industrial_layers')
        self.assertTrue(any(r['id'].endswith('costume_makeup') for r in plan['rules']))
        self.assertTrue(any(r['id'].endswith('prop_continuity') for r in plan['rules']))

    def test_non_linear_is_not_negation(self):
        _, negative, _, _ = cr.lexical('非线性时间叙事')
        self.assertEqual(negative.strip(), '')

    def test_ambiguous_bootstrap_labels_limitations(self):
        plan = self.route('director', '一个人站着。')
        self.assertTrue(plan['fallback'])
        self.assertIn('requires_host_review', plan['selection_basis'])
        self.assertEqual(plan['media_quality'], 'NOT_RUN')

    def test_empty_and_invalid_feature_inputs_fail(self):
        for query, features in [('', None), (BRIEF, {'task': 'magic'}), (BRIEF, {'tags': 'suspense'}), (BRIEF, {'secret_field': True})]:
            with self.subTest(query=query, features=features), self.assertRaises(ValueError):
                self.route('director', query, features)

    def test_every_source_resolves_to_existing_record(self):
        for role in cr.ROLES:
            plan = self.route(role, BRIEF)
            root = SKILL_ROOTS[cr.ROLES[role]]
            for src in plan['sources']:
                self.assertEqual(digest_file(root/src['path']), src['sha256'])
                if src['locator']:
                    self.assertIsNotNone(cr.pointer(read(root/src['path']), src['locator']))

    def test_source_path_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            cr.source(SKILL_ROOTS['director-grammar'], '../README.md')

    def test_host_semantics_resolve_negative_sentence_ambiguity(self):
        plan = self.route('director', 'Do not ignore suspense in this quiet scene.', {'tags': ['悬疑'], 'goal': '保留悬念，而不是删除悬念。'})
        self.assertEqual(plan['primary'], 'restrained_suspense')

    def test_deterministic_selection(self):
        self.assertEqual(self.route('director', BRIEF), self.route('director', BRIEF))

    def test_studio_and_standalone_entries_keep_professional_routing(self):
        for name in ('ai-comic-drama-workflow', *cr.ROLES.values(), 'image-prompt-optimizer', 'video-prompt-compiler'):
            heading = '## 默认专业方法与质量检查' if name == 'ai-comic-drama-workflow' else '## 默认专业方法路由'
            self.assertIn(heading, (SKILL_ROOTS[name]/'SKILL.md').read_text())
            self.assertTrue((SKILL_ROOTS[name]/'references/craft-routing.md').is_file())


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.plan = cr.route(SKILL_ROOTS['director-grammar'], 'director', '安静的父女重逢，克制地交换目光。')
        self.artifact = {'content': '女儿在门口停住，把雨伞放在墙边；父亲没有说话，只将椅子移开半步，给她留出位置。'}
        self.review = review(self.plan, self.artifact)

    def test_bound_evidence_is_not_visual_pass(self):
        result = cr.validate_review(self.plan, self.review, self.artifact)
        self.assertEqual(result['status'], 'EVIDENCE_BOUND')
        self.assertEqual(result['semantic_assessment'], 'HOST_DECLARED')
        self.assertEqual(result['media_quality'], 'NOT_RUN')

    def test_missing_or_stale_review(self):
        for value in (None, {}, {**self.review, 'plan_sha256': '0'*64}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cr.validate_review(self.plan, value, self.artifact)

    def test_changed_plan_is_rejected(self):
        self.plan['primary'] = 'heroic_reveal'
        with self.assertRaisesRegex(ValueError, 'integrity'):
            cr.validate_review(self.plan, self.review, self.artifact)

    def test_changed_output_hash_is_rejected(self):
        self.artifact['content'] += '她突然瞬移。'
        with self.assertRaisesRegex(ValueError, 'hash'):
            cr.validate_review(self.plan, self.review, self.artifact)

    def test_nonexistent_quote_is_rejected(self):
        self.review['applications'][0]['quote'] = '实际输出中没有的内容'
        with self.assertRaisesRegex(ValueError, 'quote'):
            cr.validate_review(self.plan, self.review, self.artifact)

    def test_native_style_request_is_not_implementation(self):
        self.artifact['task'] = {'style_request': self.plan['primary']}
        bad = review(self.plan, self.artifact, '/task/style_request')
        with self.assertRaisesRegex(ValueError, 'labels'):
            cr.validate_review(self.plan, bad, self.artifact)

    def test_primary_cannot_all_be_waived_using_inherited_evidence(self):
        self.plan['inherited'] = [{'id': 'upstream:rule', 'instruction': '上游规则'}]
        self.plan['plan_sha256'] = cr.digest({k:v for k,v in self.plan.items() if k != 'plan_sha256'})
        candidate = review(self.plan, self.artifact)
        for row in candidate['applications'][:-1]:
            row.update(status='not_applicable', condition='合成用例试图只保留上游规则并跳过主方法。')
        with self.assertRaisesRegex(ValueError, 'primary'):
            cr.validate_review(self.plan, candidate, self.artifact)

    def test_missing_rule_rejected(self):
        self.review['applications'].pop()
        with self.assertRaisesRegex(ValueError, 'every'):
            cr.validate_review(self.plan, self.review, self.artifact)

    def test_duplicate_rule_rejected(self):
        self.review['applications'].append(deepcopy(self.review['applications'][0]))
        with self.assertRaisesRegex(ValueError, 'every'):
            cr.validate_review(self.plan, self.review, self.artifact)

    def test_label_is_not_implementation(self):
        self.artifact['style'] = {'primary': '李安风格的克制亲情'}
        bad = review(self.plan, self.artifact, '/style/primary')
        with self.assertRaisesRegex(ValueError, 'labels'):
            cr.validate_review(self.plan, bad, self.artifact)

    def test_name_only_is_not_implementation(self):
        self.artifact['content'] = '参考' + self.plan['practitioner']['name']
        with self.assertRaisesRegex(ValueError, 'name'):
            cr.validate_review(self.plan, review(self.plan, self.artifact), self.artifact)

    def test_all_not_applicable_is_rejected(self):
        for row in self.review['applications']:
            row.update(status='not_applicable', condition='测试要求所有方法都不适用本段。')
        with self.assertRaisesRegex(ValueError, 'All craft'):
            cr.validate_review(self.plan, self.review, self.artifact)

    def test_not_applicable_needs_scope_condition(self):
        self.review['applications'][0]['status'] = 'not_applicable'
        with self.assertRaisesRegex(ValueError, 'scope'):
            cr.validate_review(self.plan, self.review, self.artifact)

    def test_semantic_review_is_required_but_not_independent(self):
        self.review['semantic_review'] = False
        with self.assertRaisesRegex(ValueError, 'semantic'):
            cr.validate_review(self.plan, self.review, self.artifact)

    def test_root_container_and_negative_array_pointer_fail(self):
        for pointer in ('/', '/missing', '/array/-1'):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                self.review['applications'][0]['pointer'] = pointer
                cr.validate_review(self.plan, self.review, {**self.artifact, 'array': ['x']})


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.kernel = V5Kernel.initialize(self.base/'p', [BRIEF], delivery='text-only', craft_policy=rt.POLICY)

    def canon_result(self):
        task = self.kernel.run()['task']
        artifact = save(self.base/'canon.json', {'project_id': 'PROJECT', 'content': BRIEF,
                'source_refs': [s['id'] for s in self.kernel.state['sources']], 'entities': [], 'locks': []})
        result = {'schema': 'role-result/5.0', 'task_id': task['task_id'], 'context_fingerprint': task['context_fingerprint'],
                  'checks': ['Synthetic source binding only.'], 'conflicts': [], 'unresolved': [],
                  'artifact': str(artifact), 'artifact_sha256': digest_file(artifact), 'craft_context': context(self.kernel)}
        return task, result

    def accept_canon(self):
        task, result = self.canon_result()
        self.assertEqual(self.kernel.submit(result)['status'], 'ACCEPTED')
        self.assertTrue(self.kernel.valid('canon'))
        return task, result

    def test_explicit_lean_start_has_automatic_semantic_task(self):
        output = start(self.base/'new', [BRIEF], delivery='text-only', profile='lean')
        task = read(output['task_file'])
        self.assertEqual(task['project']['craft_policy'], rt.POLICY)
        self.assertEqual(task['craft']['status'], 'SEMANTIC_ANALYSIS_REQUIRED')

    def test_explicit_off_and_old_init_do_not_require_new_evidence(self):
        for name, options in [('old', {}), ('off', {'craft_policy': 'off'})]:
            kernel = V5Kernel.initialize(self.base/name, [BRIEF], **options)
            self.assertNotIn('craft', kernel.run()['task'])

    def test_missing_context_cannot_promote_canon(self):
        _, result = self.canon_result()
        result.pop('craft_context')
        with self.assertRaisesRegex(ValueError, 'craft_context'):
            self.kernel.submit(result)
        self.assertNotIn('canon', self.kernel.state['artifacts'])

    def test_invented_source_quote_cannot_promote(self):
        _, result = self.canon_result()
        result['craft_context']['roles']['art']['evidence'][0]['quote'] = '原文不存在的艺术断言'
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.kernel.submit(result)

    def test_accepted_canon_dispatches_selected_excerpt_not_all_registries(self):
        self.accept_canon()
        task = self.kernel.run()['task']
        self.assertEqual(task['kind'], 'screenplay')
        self.assertEqual(task['craft']['primary'], 'character_causal')
        reads = task['module']['required_reads']
        self.assertTrue(any(r['relative'] == 'craft:selected-methods' for r in reads))
        self.assertFalse(any(r['relative'].endswith('writers.json') for r in reads))
        self.assertEqual(self.kernel.run()['task']['task_id'], task['task_id'])

    def test_missing_adoption_fails_before_native_import(self):
        self.accept_canon()
        task = self.kernel.run()['task']
        artifact = {'task': {'style_request': task['craft']['primary']}, 'content': '这只是用于检查门禁的合成正文，不作为真实制作交付。'}
        path = save(self.base/'candidate.json', artifact)
        with self.assertRaisesRegex(ValueError, 'craft_review'):
            self.kernel.receipt_audit(task, {'artifact': str(path), 'artifact_sha256': digest_file(path)})
        self.assertNotIn('screenplay', self.kernel.state['artifacts'])

    def test_wrong_native_primary_fails(self):
        self.accept_canon()
        task = self.kernel.run()['task']
        artifact = {'task': {'style_request': 'restricted_mystery'}, 'content': '实际可定位的合成正文，但主语法不符合冻结选择。'}
        path = save(self.base/'candidate.json', artifact)
        with self.assertRaisesRegex(ValueError, 'primary grammar'):
            rt.check(self.kernel, task, {'artifact': str(path), 'artifact_sha256': digest_file(path), 'craft_review': review(task['craft'], artifact)})

    def test_changed_source_invalidates_craft_context(self):
        self.accept_canon()
        self.kernel.add(['追加修改：现在只做产品演示。'])
        self.assertFalse(self.kernel.valid('canon'))
        self.assertEqual(self.kernel.run()['task']['kind'], 'canon')

    def test_tampered_accepted_result_invalidates_proof(self):
        self.accept_canon()
        proof = self.kernel.state['artifacts']['canon']['craft_proof']
        self.kernel.path(proof['uri']).write_text('{}')
        self.assertFalse(self.kernel.valid('canon'))

    def test_import_is_not_adoption(self):
        _, result = self.canon_result()
        self.kernel.import_artifact('canon', result['artifact'], trusted=True)
        self.assertFalse(self.kernel.valid('canon'))
        self.assertEqual(self.kernel.run()['task']['kind'], 'canon')

    def test_configuration_cannot_silently_disable_gate(self):
        config = read(self.kernel.root/'project.json')
        config['craft_policy'] = 'off'
        save(self.kernel.root/'project.json', config)
        with self.assertRaisesRegex(ValueError, 'policy'):
            self.kernel.run()

    def test_scene_routes_need_native_scene_evidence_and_continuity(self):
        self.accept_canon()
        artifact = {'scenes': [{'id': 'A', 'space': '当代厨房，旧木桌与自然窗光。'}, {'id': 'B', 'space': '同一厨房，人物转过桌面。'}], 'shots': []}
        features = {'art': {'tags': ['当代', '日常'], 'goal': '保持厨房旧化与自然光源一致。', 'world_mode': 'contemporary', 'medium': 'live_action'},
                    'storyboard': {'tags': ['对话'], 'goal': '用行动反应交代人物相对关系。'}}
        routes = {s['id']: {'continuity_group': 'KITCHEN', 'features': deepcopy(features),
                          'evidence': {'pointer': f'/scenes/{i}/space', 'quote': s['space']}}
                  for i, s in enumerate(artifact['scenes'])}
        self.assertEqual(len(rt.check_scene_routes(self.kernel, artifact, {'craft_scene_routes': routes})), 2)
        routes['B']['features']['art'].update(tags=['图形', '色块'])
        with self.assertRaisesRegex(ValueError, 'continuity group'):
            rt.check_scene_routes(self.kernel, artifact, {'craft_scene_routes': routes})

    def test_mixed_scene_routing_and_scene_evidence_boundary(self):
        self.accept_canon()
        director = {'scenes': [{'id': 'A', 'space': '两个人相对坐下交谈。'}, {'id': 'B', 'space': '两个人在走廊追逐打斗。'}],
                    'shots': [{'id': 'S1', 'scene_id': 'A'}, {'id': 'S2', 'scene_id': 'B'}]}
        routes = {
            'A': {'features': {'storyboard': {'tags': ['对话', '关系'], 'goal': '保持对话行动与反应的清晰关系。'}}},
            'B': {'features': {'storyboard': {'tags': ['动作', '追逐'], 'goal': '让追逐方向和危险结果持续可读。'}}}}
        with patch.object(rt, 'scene_routes_for', return_value=(routes, director)):
            plan = rt.task_plan(self.kernel, 'storyboard', 'storyboard', [], {})
        self.assertEqual(plan['primary'], 'transparent')
        self.assertEqual([p['primary'] for p in plan['scene_profiles']], ['transparent', 'action'])
        artifact = {'style': {'primary': 'transparent'}, 'shots': [
            {'scene_id': 'A', 'content': 'A等待对方回应，B将手放在桌上；这个合成用例描述第一场的可见行动。'},
            {'scene_id': 'B', 'content': 'A向走廊右侧跑去，B沿相同路径跟进；这个合成用例描述第二场的连续追逐。'}]}
        path = save(self.base/'scoped.json', artifact)
        task = {'kind': 'storyboard', 'craft': plan}
        result = {'artifact': str(path), 'artifact_sha256': digest_file(path), 'craft_review': review(plan, artifact, '/shots/0/content')}
        with self.assertRaisesRegex(ValueError, 'another scene'):
            rt.check(self.kernel, task, result)
        for row in result['craft_review']['applications']:
            if row['id'].startswith('scene:B/'):
                text = artifact['shots'][1]['content']
                row.update(pointer='/shots/1/content', quote=text[:40], value_sha256=cr.digest(text))
        rt.check(self.kernel, task, result)

    def test_missing_scene_routes_fail(self):
        self.accept_canon()
        with self.assertRaisesRegex(ValueError, 'every native scene'):
            rt.check_scene_routes(self.kernel, {'scenes': [{'id': 'A'}]}, {})

    def test_image_only_input_uses_declared_observation_not_fake_source_quote(self):
        import base64
        image = self.base/'pixel.png'
        image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWZkAAAAASUVORK5CYII='))
        kernel = V5Kernel.initialize(self.base/'image-only', [str(image)], craft_policy=rt.POLICY)
        task = kernel.run()['task']
        src = kernel.state['sources'][0]
        observed = '合成静态测试像素，仅测试观察记录的来源绑定，不代表真实专业审阅。'
        native = {'project_id': 'PROJECT', 'content': observed, 'source_refs': [src['id']], 'entities': [], 'locks': []}
        path = save(self.base/'observed-canon.json', native)
        ctx = context(self.kernel)
        ctx['source_sha256'] = rt.source_hash(kernel)
        for entry in ctx['roles'].values():
            entry['evidence'] = [{'kind': 'observation', 'source_id': src['id'], 'source_sha256': src['sha256'],
                                  'pointer': '/content', 'quote': observed, 'inspection_ref': 'synthetic-test-record/not-real-media-review'}]
        result = {'schema': 'role-result/5.0', 'task_id': task['task_id'], 'context_fingerprint': task['context_fingerprint'],
                  'checks': ['Synthetic observation binding only.'], 'conflicts': [], 'unresolved': [],
                  'artifact': str(path), 'artifact_sha256': digest_file(path), 'craft_context': ctx}
        kernel.submit(result)
        self.assertTrue(kernel.valid('canon'))
        self.assertEqual(kernel.run()['task']['kind'], 'screenplay')
        bad = deepcopy(ctx)
        bad['roles']['art']['evidence'][0]['source_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'frozen source'):
            rt.check_context(kernel, bad, native)

    def test_audited_start_retains_native_craft_task(self):
        output = start(self.base/'audited', [BRIEF], delivery='text-only', profile='audited')
        native = list((self.base/'audited/runtime/tasks').glob('TASK_*.json'))
        self.assertTrue(native)
        self.assertTrue(any(read(path).get('craft', {}).get('policy') == rt.POLICY for path in native))
        self.assertEqual(output['review_policy'], 'independent-per-stage')


if __name__ == '__main__':
    unittest.main()
