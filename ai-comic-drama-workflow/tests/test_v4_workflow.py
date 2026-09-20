"""Synthetic contract fixtures, never evidence of native generation or human review."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from ai_comic_drama_workflow.v4 import V4Kernel
from ai_comic_drama_workflow.v4_contracts import PHASES, output, model_policy
from ai_comic_drama_workflow.utils import sha256_file


def shot():
    return {'shot_id': 'SHOT_001', 'segment_id': 'SEG_001', 'scene_id': 'ROOM', 'duration_s': 4,
        'purpose': '交接信封', 'initial_state': '沈持有信封', 'end_state': '陆持有信封',
        'continuity': {'kind': 'scene_change', 'reason': '开场'}, 'required_asset_ids': ['SHEN', 'LU', 'ROOM', 'LETTER'],
        'characters': [{'entity_id': e, 'identity_asset_id': e,
            'positions': [{'time_s': 0, 'position': [x, 0, 0], 'facing': '对方', 'gaze': '信封', 'pose': '站立'},
                          {'time_s': 4, 'position': [x, 0, 0], 'facing': '对方', 'gaze': '对方', 'pose': '站立'}],
            'actions': [{'start_s': 0, 'end_s': 4, 'phase': 'key', 'description': '递出' if e == 'SHEN' else '接过', 'target_id': 'LETTER', 'prop_state': '信封交接'}],
            'emotions': [{'start_s': 0, 'end_s': 4, 'emotion': '谨慎', 'intensity': 0.5, 'expression': '抿嘴', 'trigger': '信封递近'}]} for e, x in [('SHEN', -1), ('LU', 1)]],
        'camera': [{'start_s': 0, 'end_s': 4, 'framing': '双人中景', 'position': [0, -4, 1.5], 'movement': '固定', 'focus': '信封', 'axis': '人物连线南侧'}],
        'sound': [{'start_s': 0, 'end_s': 4, 'speaker_id': 'SHEN', 'dialogue': '给你。', 'ambience': '安静书房', 'sfx': '纸声', 'music_intent': '无'}],
        'lighting': '日光', 'environment': '书房', 'negative_constraints': ['不新增人物'],
        'key_moments': [{'time_s': 2, 'name': '递交信封_关键点', 'description': '两人共同接触信封'}]}


def data_for(kernel, number):
    source = kernel.store.read(PHASES[0]['folder'] + '/sources.json')['sources'][0]['source_id']
    data = {'content': '测试场景：两个原创成年人在书房交接信封。', 'source_refs': [source], 'inferences': [], 'reuse': 'created'}
    if number == 1:
        data.update(entities=[{'entity_id': 'SHEN', 'name': '沈'}, {'entity_id': 'LU', 'name': '陆'}], unresolved=[])
    if number == 6:
        data['segments'] = [{'segment_id': 'SEG_001', 'target_duration_s': 15, 'source_text': '交接信封'}]
    if number == 7:
        data['shots'] = [shot()]
    if number == 8:
        data['assets'] = [{'asset_id': key, 'name': name, 'kind': kind, 'entity_ids': [key] if kind == 'role' else [],
                           'version_label': '常服_正面' if kind == 'role' else '日景', 'prompt': name + ' 测试素材',
                           'continuity': ['保持外观'], 'forbidden_inheritance': ['背景']} for key, name, kind in
                          [('SHEN', '沈知微', 'role'), ('LU', '陆沉', 'role'), ('ROOM', '书房', 'scene'), ('LETTER', '信封', 'prop'), ('STYLE', '画风', 'style')]]
    if number == 9:
        data['shots'] = [shot()]
        data['scenes'] = [{'scene_id': 'ROOM', 'origin': '房间中心', 'axes': 'X左右Y前后Z向上', 'units': '米',
                           'bounds': {'min': [-3, -3, 0], 'max': [3, 3, 3]}, 'fixed_elements': ['北墙书架'],
                           'entrances': ['南门'], 'blocking': '两人东西相对', 'axis_rules': '相机位于南侧'}]
    if number == 10:
        data['review'] = {'passed': True, 'checked_shot_ids': ['SHOT_001'], 'limitations': ['synthetic test, no actual creative acceptance']}
    return data


def result_for(kernel, task):
    result = {'task_id': task['task_id'], 'context_fingerprint': task['context_fingerprint'],
              'execution': {**task['model_policy'], 'agent_id': 'synthetic-agent', 'dispatch_evidence': 'synthetic test only'},
              'findings': [], 'qa': {'passed': True, 'visual_findings': ['synthetic fixture, not real image review']}}
    if task['task_kind'] == 'creative':
        result['data'] = data_for(kernel, task['phase'])
    else:
        path = kernel.store.path('runtime/fixture.png')
        Image.new('RGB', (32, 32), '#345678').save(path)
        result['media'] = {'provider': 'provided', 'call_evidence': 'synthetic user-import fixture',
                           'output_path': str(path), 'sha256': sha256_file(path),
                           'input_hash': task['job']['input_hash'], 'bindings': task['job']['bindings']}
    return result


def start(root, kind='novel'):
    kernel = V4Kernel.initialize(root, ['两个原创成年人在书房交接信封。'], input_type=kind)
    kernel.configure_host([model_policy(1), model_policy(9)], 'available', 'synthetic inventory')
    return kernel


def advance(kernel, stop=None, choices=None):
    choices = {'style': '高规格2D动漫', 'canvas': '16:9', 'rights': 'authorized', 'identity_approval': 'approve', **(choices or {})}
    for _ in range(80):
        status = kernel.status()
        if stop and stop(status):
            return status
        if status['status'] == 'awaiting_agent_result':
            kernel.submit(result_for(kernel, status['task']))
        elif status['status'] == 'awaiting_choice':
            request = status['decision']
            value = choices.get(request['key'], request['options'][0])
            kernel.resume({'request_id': request['request_id'], 'value': value})
        else:
            return status
    raise AssertionError('Unexpected loop')


class V4Tests(unittest.TestCase):
    def test_six_shots_finish_all_director_and_review_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            shots = [deepcopy(shot()) for _ in range(6)]
            for i, s in enumerate(shots):
                s['shot_id'] = f'SHOT_{i + 1:03d}'
            seen = {7: [], 9: [], 10: []}
            for _ in range(80):
                status = kernel.status()
                if status['status'] == 'awaiting_choice':
                    request = status['decision']
                    values = {'style': '高规格2D动漫', 'canvas': '16:9', 'rights': 'authorized', 'identity_approval': 'approve'}
                    kernel.resume({'request_id': request['request_id'], 'value': values.get(request['key'], request['options'][0])})
                elif status['status'] == 'awaiting_agent_result':
                    task = status['task']
                    result = result_for(kernel, task)
                    n = task['phase']
                    if task['task_kind'] == 'creative' and n in (7, 9, 10):
                        ids = task['batch']['expected_shot_ids']
                        if n == 7:
                            start_at = len(task['batch']['completed_shot_ids'])
                            batch = shots[start_at:start_at + 5]
                            result['data']['shots'] = batch
                            result['batch_complete'] = start_at + len(batch) == 6
                        elif n == 9:
                            result['data']['shots'] = [s for s in shots if s['shot_id'] in ids]
                        else:
                            result['data']['review']['checked_shot_ids'] = ids
                        seen[n].append(len(result['data'].get('shots', ids or [])))
                    kernel.submit(result)
                else:
                    break
            self.assertEqual('complete', kernel.status()['status'], kernel.validate(True))
            self.assertEqual({7: [5, 1], 9: [5, 1], 10: [5, 1]}, seen)
            self.assertEqual(6, len(kernel.store.read(PHASES[9]['folder'] + '/prompt-package.json')['prompts']))

    def test_copy_destination_cannot_be_inside_original(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            with self.assertRaisesRegex(ValueError, 'separate'):
                V4Kernel.copy_project(kernel.store.root, kernel.store.root / 'nested')
            self.assertFalse(kernel.store.path('nested').exists())

    def test_unfinished_legacy_project_copies_verified_original_sources(self):
        from ai_comic_drama_workflow.kernel import WorkflowKernel as LegacyKernel
        with tempfile.TemporaryDirectory() as directory:
            legacy = LegacyKernel.initialize(Path(directory) / 'old', ['原始小说，尚未生成剧本。'])
            copied = V4Kernel.copy_project(legacy.store.root, Path(directory) / 'new')
            records = copied.store.read(PHASES[0]['folder'] + '/sources.json')['sources']
            self.assertEqual(1, len(records))
            self.assertIn('原始小说', copied.store.path(records[0]['text_path']).read_text())
            self.assertEqual({}, copied.state['approvals'])

    def test_changed_image_run_invalidates_downstream_and_old_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            advance(kernel)
            path = kernel.store.path(kernel.state['media']['SHEN']['path'])
            Image.new('RGB', (32, 32), '#aa2233').save(path)
            status = kernel.run()
            self.assertNotIn('SHEN', kernel.state['approvals'])
            self.assertEqual('invalidated', kernel.state['phase_status']['9'])
            self.assertNotEqual('complete', status['status'])

    def test_identity_revision_requires_new_approval_even_same_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            advance(kernel)
            before = kernel.state['media']['SHEN']
            kernel.revise(8, asset_id='SHEN')
            status = advance(kernel, lambda s: s.get('decision', {}).get('key') == 'identity_approval')
            self.assertEqual('SHEN', status['decision']['scope'])
            after = kernel.state['media']['SHEN']
            self.assertEqual(before['sha256'], after['sha256'])
            self.assertGreater(after['revision'], before['revision'])

    def test_context_cannot_be_relabelled_after_input_change(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            task = kernel.status()['task']
            result = result_for(kernel, task)
            source = kernel.store.read(PHASES[0]['folder'] + '/sources.json')['sources'][0]['path']
            kernel.store.path(source).write_text('changed story')
            result['context_fingerprint'] = kernel.fingerprint(1)
            with self.assertRaisesRegex(ValueError, 'Stale'):
                kernel.submit(result)

    def test_named_file_normalization_and_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            status = advance(kernel, lambda s: s.get('task', {}).get('phase') == 8)
            result = result_for(kernel, status['task'])
            result['data']['assets'][0]['name'] = '角色/甲'
            result['data']['assets'][1]['name'] = '角色:甲'
            kernel.submit(result)
            advance(kernel)
            first, second = kernel.state['media']['SHEN'], kernel.state['media']['LU']
            self.assertNotEqual(first['filename'], second['filename'])
            self.assertNotIn('/', first['filename'])
            self.assertIn('角色_甲', first['filename'])

    def test_scoped_asset_revision_rejects_unrelated_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            advance(kernel)
            status = kernel.revise(8, asset_id='SHEN')
            result = result_for(kernel, status['task'])
            result['data']['assets'][1]['name'] = '改掉无关角色'
            with self.assertRaisesRegex(ValueError, 'unrelated'):
                kernel.submit(result)

    def test_image_import_write_failure_rolls_back_entire_submission(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            status = advance(kernel, lambda s: s.get('task', {}).get('task_kind') == 'image')
            state_before = deepcopy(kernel.state)
            result = result_for(kernel, status['task'])
            original = kernel.commit
            def fail_after_copy(path, *args, **kwargs):
                if '/image-records/' in path:
                    raise OSError('synthetic disk failure')
                return original(path, *args, **kwargs)
            with patch.object(kernel, 'commit', side_effect=fail_after_copy), self.assertRaises(OSError):
                kernel.submit(result)
            self.assertEqual(state_before, kernel.state)
            self.assertEqual([], list(kernel.store.path(PHASES[7]['folder'] + '/images').glob('*')))

    def test_prefilled_choices_do_not_ask_again(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = V4Kernel.initialize(Path(directory) / 'p', ['test'], style='高规格2D动漫', canvas='16:9', rights='authorized', image_budget=10, segment_seconds=20)
            kernel.configure_host([model_policy(1), model_policy(9)], 'available', 'synthetic inventory')
            status = advance(kernel, lambda s: 'decision' in s)
            self.assertEqual('identity_approval', status['decision']['key'])
            self.assertEqual(20, kernel.store.read('project.json')['segment_target_s'])

    def test_larger_shot_plan_is_transactional_and_batched(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            status = advance(kernel, lambda s: s.get('task', {}).get('phase') == 7)
            result = result_for(kernel, status['task'])
            result['data']['shots'] = [deepcopy(shot()) for _ in range(6)]
            for i, s in enumerate(result['data']['shots']):
                s['shot_id'] = f'SHOT_{i + 1:03d}'
            with self.assertRaisesRegex(ValueError, 'five'):
                kernel.submit(result)
            last = result['data']['shots'].pop()
            result['batch_complete'] = False
            status = kernel.submit(result)
            self.assertFalse(kernel.store.exists(output(7)))
            self.assertEqual(5, len(status['task']['batch']['completed_shot_ids']))
            result = result_for(kernel, status['task'])
            result['data']['shots'] = [last]
            result['batch_complete'] = True
            kernel.submit(result)
            self.assertEqual(6, len(kernel.store.read(output(7))['data']['shots']))

    def test_uncertain_call_pauses_without_repeat_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            status = advance(kernel, lambda s: s.get('task', {}).get('task_kind') == 'image')
            count = kernel.state['image_dispatches']
            result = result_for(kernel, status['task'])
            result.update(status='uncertain', failure_evidence='response not observed')
            status = kernel.submit(result)
            self.assertEqual('uncertain_result', status['decision']['key'])
            self.assertEqual(count, kernel.state['image_dispatches'])

    def test_technical_retry_fourth_failure_escalates(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            for i in range(4):
                result = result_for(kernel, kernel.status()['task'])
                result.update(status='failed', failure_evidence='synthetic transient failure')
                status = kernel.submit(result)
                self.assertEqual('awaiting_choice' if i == 3 else 'awaiting_agent_result', status['status'])
            self.assertEqual('retry_exhausted', status['decision']['key'])

    def test_missing_reference_mapping_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            status = advance(kernel, lambda s: s.get('task', {}).get('phase') == 9 and s['task']['task_kind'] == 'image')
            result = result_for(kernel, status['task'])
            result['media']['bindings'] = []
            with self.assertRaisesRegex(ValueError, 'bindings'):
                kernel.submit(result)
            self.assertNotIn('SHOT_001:moment:1', kernel.state['media'])

    def test_v4_copy_keeps_old_tree_and_rejects_old_approvals(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'old')
            advance(kernel)
            before = {p.relative_to(kernel.store.root).as_posix(): sha256_file(p) for p in kernel.store.root.rglob('*') if p.is_file()}
            copied = V4Kernel.copy_project(kernel.store.root, Path(directory) / 'new')
            self.assertEqual({}, copied.state['approvals'])
            self.assertEqual('pending', copied.state['phase_status']['9'])
            self.assertTrue(copied.store.path('.history/migrations/project.json').is_file())
            self.assertEqual(before, {p.relative_to(kernel.store.root).as_posix(): sha256_file(p) for p in kernel.store.root.rglob('*') if p.is_file()})
            copied.configure_host([model_policy(1), model_policy(9)], 'available', 'synthetic inventory')
            advance(copied)
            self.assertTrue(copied.validate(True)['valid'], copied.validate(True))

    def test_wrong_scene_and_changed_dialogue_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            status = advance(kernel, lambda s: s.get('task', {}).get('phase') == 9)
            result = result_for(kernel, status['task'])
            result['data']['shots'][0]['scene_id'] = 'missing'
            with self.assertRaisesRegex(ValueError, 'Unknown scene'):
                kernel.submit(result)
            result = result_for(kernel, status['task'])
            result['data']['shots'][0]['sound'][0]['dialogue'] = '更换台词'
            with self.assertRaisesRegex(ValueError, 'silently change'):
                kernel.submit(result)

    def test_legacy_status_does_not_write_files(self):
        from ai_comic_drama_workflow.kernel import WorkflowKernel as LegacyKernel
        with tempfile.TemporaryDirectory() as directory:
            legacy = LegacyKernel.initialize(Path(directory) / 'old', ['test'])
            before = {p.relative_to(legacy.store.root).as_posix(): sha256_file(p) for p in legacy.store.root.rglob('*') if p.is_file()}
            kernel = V4Kernel(legacy.store.root)
            self.assertTrue(kernel.run()['legacy_read_only'])
            with self.assertRaisesRegex(ValueError, 'read-only'):
                kernel.export(draft=True)
            self.assertEqual(before, {p.relative_to(legacy.store.root).as_posix(): sha256_file(p) for p in legacy.store.root.rglob('*') if p.is_file()})

    def test_complete_named_dual_package_and_deterministic_export(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            status = advance(kernel)
            self.assertEqual('complete', status['status'], kernel.validate(True))
            self.assertEqual(10, len(list(kernel.store.path('stages').iterdir())))
            self.assertTrue(kernel.validate(True)['valid'])
            package = kernel.store.read(PHASES[9]['folder'] + '/prompt-package.json')
            refs = package['prompts'][0]['references']
            self.assertEqual(['@image_role_1', '@image_role_2', '@image_board_1'], [r['alias'] for r in refs])
            self.assertIn('沈知微_常服_正面_v001', refs[0]['filename'])
            self.assertEqual(2, len(kernel.state['media']['SHOT_001:moment:1']['input_bindings']))
            first = kernel.export()
            second = kernel.export()
            self.assertEqual(first['sha256'], second['sha256'])

    def test_model_and_time_failures_leave_formal_tree_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            task = kernel.status()['task']
            result = result_for(kernel, task)
            result['execution']['model'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'Wrong model'):
                kernel.submit(result)
            self.assertFalse(kernel.store.exists(output(1)))
            status = advance(kernel, lambda s: s.get('task', {}).get('phase') == 7)
            result = result_for(kernel, status['task'])
            result['data']['shots'][0]['characters'][0]['positions'][1]['time_s'] = 10
            with self.assertRaises(ValueError):
                kernel.submit(result)
            self.assertFalse(kernel.store.exists(output(7)))

    def test_only_necessary_gates_and_no_external_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            gates = []
            while kernel.status()['status'] in ('awaiting_choice', 'awaiting_agent_result'):
                status = kernel.status()
                if 'decision' in status:
                    request = status['decision']
                    gates.append(request['key'])
                    values = {'style': '高规格2D动漫', 'canvas': '16:9', 'rights': 'authorized', 'identity_approval': 'approve'}
                    kernel.resume({'request_id': request['request_id'], 'value': values.get(request['key'], request['options'][0])})
                else:
                    task = status['task']
                    self.assertEqual(model_policy(task['phase']), task['model_policy'])
                    self.assertFalse(any('blender' in r for r in task['loaded_resources']))
                    kernel.submit(result_for(kernel, task))
            self.assertEqual(['style', 'canvas', 'rights', 'image_budget', 'identity_approval', 'identity_approval'], gates)

    def test_changed_image_blocks_export(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            advance(kernel)
            path = kernel.store.path(kernel.state['media']['SHEN']['path'])
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Formal export blocked'):
                kernel.export()

    def test_unavailable_images_requires_explicit_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            status = advance(kernel, lambda s: s.get('task', {}).get('phase') == 8)
            state = kernel.state
            state['image_capability'] = 'unavailable'
            kernel.save_state(state)
            kernel.revise(8)
            status = advance(kernel, lambda s: s.get('decision', {}).get('key') == 'image_unavailable')
            self.assertEqual('image_unavailable', status['decision']['key'])
            kernel.resume({'request_id': status['decision']['request_id'], 'value': 'draft-only'})
            advance(kernel)
            self.assertFalse(kernel.validate(True)['valid'])
            self.assertTrue(kernel.export(draft=True)['draft'])

    def test_input_routes_and_scoped_revision_preserve_unrelated_media(self):
        for kind in ('novel', 'screenplay', 'storyboard', 'text'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                kernel = start(Path(directory) / 'p', kind)
                records = kernel.store.read(PHASES[0]['folder'] + '/sources.json')['sources']
                self.assertEqual(kind, records[0]['kind'])
        with tempfile.TemporaryDirectory() as directory:
            kernel = start(Path(directory) / 'p')
            advance(kernel)
            original = deepcopy(kernel.state['media'])
            kernel.revise(9, shot_id='SHOT_001')
            advance(kernel)
            self.assertEqual(original, kernel.state['media'])

if __name__ == '__main__':
    unittest.main()
