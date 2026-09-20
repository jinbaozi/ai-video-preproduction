from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import io
import os
import sys
import tarfile
import json
import zipfile
import hashlib

from ai_comic_drama_workflow.editing import execute_edit_plan
from ai_comic_drama_workflow.exporter import build_delivery_archive
from ai_comic_drama_workflow.kernel import WorkflowKernel
from ai_comic_drama_workflow.layout import ASSET_REGISTRY, P09, P13, FINAL_DELIVERY_INDEX, SCENE_SPACE_PLAN
from ai_comic_drama_workflow.references import dual_bindings
from ai_comic_drama_workflow.storage import ProjectStore
from ai_comic_drama_workflow.utils import canonical_json, sha256_file, sha256_bytes
from tests.helpers import drive_to_completion
from tests.test_v2_workflow import advance_until


class DeliveryV3Tests(unittest.TestCase):
    def test_explicit_storyboard_moment_respects_budget_and_time_bounds(self):
        from ai_comic_drama_workflow.pipeline import _key_moments
        shot = {'duration_s': 8, 'storyboard_key_time_s': 4}
        self.assertEqual([{'moment_id': 'key', 'time_s': 4.0,
                           'purpose': 'selected-representative-frame'}], _key_moments(shot))
        for value in (-1, 9, True, float('nan')):
            with self.assertRaises(ValueError):
                _key_moments({**shot, 'storyboard_key_time_s': value})
        self.assertEqual('start', _key_moments({'duration_s': 8})[0]['moment_id'])

    def test_voice_script_uses_contract_speaker_id(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = WorkflowKernel.initialize(Path(directory) / 'project', ['Fictional handoff'], input_type='novel')
            drive_to_completion(kernel, storyboard_durations=[4])
            stage = kernel.graph.get('audio_edit_plan')
            body = kernel.store.read(stage.output)
            body['dialogue_table'] = [{'line_id': 'L', 'speaker_id': 'CHAR-001', 'text': 'Keep it sealed.', 'start_s': 0, 'end_s': 2}]
            kernel._commit_stage_output(stage, body)
            script = kernel.store.path('stages/12-配音字幕与剪辑/derived/voice-script.txt').read_text()
            self.assertIn('CHAR-001: Keep it sealed.', script)
            self.assertNotIn('unknown:', script)

    def test_pruned_views_return_when_transaction_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = WorkflowKernel.initialize(Path(directory) / 'project', ['Fictional handoff'], input_type='novel')
            folder = 'stages/10-分镜级视频提示词/shots'
            kernel.store.write_text(folder + '/old.txt', 'prior derived view')
            with self.assertRaises(RuntimeError):
                with kernel.store.transaction():
                    kernel._replace_text_views(folder, {'new.txt': 'candidate view'})
                    raise RuntimeError('injected interruption')
            self.assertEqual('prior derived view', kernel.store.path(folder + '/old.txt').read_text())
            self.assertFalse(kernel.store.exists(folder + '/new.txt'))

    def dual_fixture(self, root):
        from PIL import Image
        store = ProjectStore(root)
        root.mkdir()
        image = root / 'character.png'
        Image.new('RGB', (64, 64), 'orange').save(image)
        board = root / 'board.png'
        Image.new('RGB', (64, 64), 'blue').save(board)
        store.write_text('approval.json', canonical_json({'valid': True, 'test_only': True}))
        store.write_text(ASSET_REGISTRY, canonical_json({'assets': [{'asset_id': 'A', 'asset_type': 'character-reference',
            'entity_ids': ['C'], 'version': 1, 'media_path': 'character.png', 'sha256': sha256_file(image)}]}))
        shot = {'shot_id': 'S', 'scene_id': 'ROOM', 'character_tracks': [{'character_id': 'C'}]}
        scene = {'scene_id': 'ROOM'}
        store.write_text(SCENE_SPACE_PLAN, canonical_json({'scenes': [scene]}))
        source_hash = sha256_bytes(canonical_json({'scene': scene, 'shot': shot}).encode())
        store.write_text(f'{P09}/storyboard-package.json', canonical_json({'shots': [{'shot_id': 'S',
            'timeline_sha256': sha256_bytes(canonical_json(shot).encode()), 'key_moments': [{'moment_id': 'M', 'time_s': 0}]}]}))
        boards = {'references': [{'reference_id': 'B', 'shot_id': 'S', 'moment_id': 'M', 'time_s': 0,
            'path': 'board.png', 'sha256': sha256_file(board), 'image_role': 'finished_storyboard', 'evaluated_source_hash': source_hash,
            'generation_reference_bindings': [{'reference_id': 'A', 'role': 'character_identity', 'revision': 1, 'sha256': sha256_file(image)}]}]}
        store.write_text(f'{P09}/reference-image-index.json', canonical_json(boards))
        state = {'decisions': {'asset_review_decision': 'approve', 'storyboard_review_decision': 'approve'},
                 'decision_approvals': {'asset_review_decision': 'approval.json', 'storyboard_review_decision': 'approval.json'}}
        return store, shot, state, boards

    def test_board_time_or_scene_changes_cannot_reuse_old_image(self):
        with tempfile.TemporaryDirectory() as directory:
            store, shot, state, boards = self.dual_fixture(Path(directory) / 'project')
            boards['references'][0]['time_s'] = 1
            store.write_text(f'{P09}/reference-image-index.json', canonical_json(boards))
            with self.assertRaisesRegex(ValueError, 'stale'):
                dual_bindings(store, shot, state)

    def test_real_attachment_mapping_and_wrong_character_version(self):
        with tempfile.TemporaryDirectory() as directory:
            store, shot, state, boards = self.dual_fixture(Path(directory) / 'project')
            bindings = dual_bindings(store, shot, state)
            self.assertEqual(['character_identity', 'storyboard_frame'], [b['role'] for b in bindings])
            self.assertEqual([1, 2], [b['slot'] for b in bindings])
            boards['references'][0]['generation_reference_bindings'][0]['revision'] = 2
            store.write_text(f'{P09}/reference-image-index.json', canonical_json(boards))
            with self.assertRaisesRegex(ValueError, 'current character versions'):
                dual_bindings(store, shot, state)

    def test_missing_whitebox_stale_and_named_character_exemption_block(self):
        with tempfile.TemporaryDirectory() as directory:
            store, shot, state, boards = self.dual_fixture(Path(directory) / 'project')
            boards['references'][0]['image_role'] = 'structured_previsualization'
            store.write_text(f'{P09}/reference-image-index.json', canonical_json(boards))
            with self.assertRaisesRegex(ValueError, 'whitebox'):
                dual_bindings(store, shot, state)
            shot['character_tracks'][0]['identity_required'] = False
            with self.assertRaisesRegex(ValueError, 'cannot bypass'):
                dual_bindings(store, shot, state)

    def test_native_dispatch_is_not_a_python_generation_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = WorkflowKernel.initialize(Path(directory) / 'project', ['Fictional handoff'], input_type='novel')
            status = advance_until(kernel, 'asset_generation_or_prompt', choices={'asset_image_strategy': 'codex-native'})
            if status['status'] == 'awaiting_choice':
                request = status['decision_request']
                status = kernel.resume({'request_id': request['request_id'], 'context_fingerprint': request['context_fingerprint'],
                                        'selections': {'image_job_budget': 3}})
            self.assertEqual('awaiting_agent_result', status['status'])
            task = status['task_envelope']
            self.assertEqual('codex-host', task['media_job']['execution_context'])
            self.assertIn('references/codex-imagegen.md', task['loaded_resources'])
            self.assertFalse(kernel.store.exists(ASSET_REGISTRY))

    def test_host_submit_imports_candidates_and_stops_at_confirmed_budget(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            kernel = WorkflowKernel.initialize(Path(directory) / 'project', ['Fictional handoff'], input_type='novel')
            status = advance_until(kernel, 'asset_generation_or_prompt', choices={'asset_image_strategy': 'codex-native'})
            request = status['decision_request']
            status = kernel.resume({'request_id': request['request_id'], 'context_fingerprint': request['context_fingerprint'],
                                    'selections': {'image_job_budget': 3}})
            for index in range(3):
                self.assertEqual('awaiting_agent_result', status['status'])
                task = status['task_envelope']
                image = Path(directory) / f'synthetic-import-{index}.png'
                Image.new('RGB', (32, 32), (index*70, 90, 140)).save(image)
                job = task['media_job']
                status = kernel.submit({'schema_version': '3.0', 'result_id': f'provided-fixture-{index}',
                    'project_id': task['project_id'], 'stage_id': task['stage_id'], 'context_fingerprint': task['context_fingerprint'],
                    'status': 'draft', 'findings': [], 'provenance': [], 'artifact': {
                        'job_id': job['job_id'], 'input_hash': job['input_hash'], 'output_path': str(image),
                        'sha256': sha256_file(image), 'provider': 'provided', 'call_evidence': {'synthetic_test': True},
                        'reference_bindings': job['reference_bindings']}})
                receipt = kernel.store.read(job['receipt_path'])
                self.assertTrue(kernel.store.exists(receipt['media_path']))
                self.assertEqual('pending', receipt['human_approval'])
            self.assertEqual('awaiting_choice', status['status'])
            self.assertEqual(['image_job_budget'], [f['id'] for f in status['decision_request']['fields']])
            self.assertEqual(3, kernel.state['native_image_dispatches'])
            request = status['decision_request']
            status = kernel.resume({'request_id': request['request_id'],
                                    'selections': {'image_job_budget': 60}})
            self.assertEqual('awaiting_agent_result', status['status'])
            self.assertEqual(60, kernel.state['decisions']['image_job_budget'])
            self.assertEqual(4, kernel.state['native_image_dispatches'])

    def test_asset_revision_dispatches_and_checks_reference_bytes(self):
        from PIL import Image
        from ai_comic_drama_workflow.media_bridge import HostMediaRequired, import_candidate
        with tempfile.TemporaryDirectory() as directory:
            kernel = WorkflowKernel.initialize(Path(directory) / 'project', ['Fictional handoff'], input_type='novel')
            advance_until(kernel, 'asset_generation_or_prompt', choices={'asset_image_strategy': 'codex-native'})
            reference = kernel.store.path('identity.png')
            Image.new('RGB', (32, 32), 'orange').save(reference)
            binding = {'reference_id': 'identity-v1', 'role': 'character_identity', 'entity_ids': ['C'],
                       'revision': 1, 'path': 'identity.png', 'sha256': sha256_file(reference),
                       'allowed_inheritance': ['identity'], 'forbidden_inheritance': ['pose'], 'approval_ref': None}
            plan_path = kernel.graph.get('asset_plan').output
            plan = kernel.store.read(plan_path)
            plan['assets'][0]['reference_bindings'] = [binding]
            kernel._commit_stage_output(kernel.graph.get('asset_plan'), plan)
            with self.assertRaises(HostMediaRequired) as caught:
                kernel.pipeline.stage_asset_generation_or_prompt(kernel.project, kernel.state)
            job = caught.exception.job
            self.assertEqual([binding], job['reference_bindings'])
            with self.assertRaisesRegex(ValueError, 'every dispatched binding'):
                import_candidate(kernel.store, job, {'job_id': job['job_id'], 'input_hash': job['input_hash'],
                                                     'provider': 'codex-imagegen', 'reference_bindings': []})
            reference.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Reference missing or changed'):
                kernel.pipeline.stage_asset_generation_or_prompt(kernel.project, kernel.state)

    def test_provided_only_dispatch_does_not_authorize_native_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = WorkflowKernel.initialize(Path(directory) / 'project', ['Fictional handoff'], input_type='novel')
            status = advance_until(kernel, 'asset_generation_or_prompt', choices={'asset_image_strategy': 'use-provided-only'})
            self.assertEqual('awaiting_agent_result', status['status'])
            self.assertEqual(['provided'], status['task_envelope']['media_job']['allowed_providers'])
            self.assertEqual(0, kernel.state.get('native_image_dispatches', 0))

    def test_draft_export_does_not_complete_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = WorkflowKernel.initialize(Path(directory) / 'project', ['Fictional handoff'], input_type='novel')
            before = kernel.run()['status']
            result = build_delivery_archive(kernel.store, draft=True)
            self.assertIn('-DRAFT.zip', result['archive'])
            self.assertEqual(before, kernel.status()['status'])
            with self.assertRaises(ValueError):
                build_delivery_archive(kernel.store)

    def test_revision_draft_has_current_report_and_matching_snapshot_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = WorkflowKernel.initialize(Path(directory) / 'project', ['Fictional handoff'], input_type='novel')
            drive_to_completion(kernel, storyboard_durations=[4, 4])
            kernel.invalidate_from('shot_timeline_specs', shot_id='SHOT-002')
            live_index_hash = sha256_file(kernel.store.path(FINAL_DELIVERY_INDEX))
            result = build_delivery_archive(kernel.store, draft=True)
            self.assertEqual(live_index_hash, sha256_file(kernel.store.path(FINAL_DELIVERY_INDEX)))
            with zipfile.ZipFile(kernel.store.path(result['archive'])) as archive:
                index = json.loads(archive.read(FINAL_DELIVERY_INDEX))
                report = json.loads(archive.read(f'{P13}/final-validation.json'))
                self.assertEqual('draft', index['status'])
                self.assertFalse(report['formal_delivery_approved'])
                self.assertTrue(report['errors'])
                for item in index['artifacts'] + json.loads(archive.read('manifest.json'))['files']:
                    self.assertEqual(item['sha256'], hashlib.sha256(archive.read(item['path'])).hexdigest())
            again = build_delivery_archive(kernel.store, draft=True)
            self.assertEqual(result['sha256'], again['sha256'])

    def test_real_frozen_v2_project_migrates_only_after_choice(self):
        from ai_comic_drama_workflow.utils import PACKAGE_ROOT
        if not (PACKAGE_ROOT / '.git').exists():
            self.skipTest('Frozen git baseline only available in source checkout')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            frozen = base / 'frozen'
            frozen.mkdir()
            archive = subprocess.run(['git', 'archive', 'e98e7ba'], cwd=PACKAGE_ROOT, capture_output=True, check=True).stdout
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(frozen, filter='data')
            project = base / 'project'
            code = "from ai_comic_drama_workflow.kernel import WorkflowKernel; from tests.helpers import drive_to_completion; import sys; k=WorkflowKernel.initialize(sys.argv[1], ['Fictional handoff'], input_type='novel'); drive_to_completion(k, storyboard_durations=[4])"
            subprocess.run([sys.executable, '-c', code, str(project)], cwd=frozen,
                           env={**os.environ, 'PYTHONPATH': str(frozen / 'src') + os.pathsep + str(frozen)}, check=True)
            kernel = WorkflowKernel(project)
            before = sha256_file(project / 'project.json')
            status = kernel.run()
            self.assertEqual('awaiting_choice', status['status'])
            self.assertEqual(before, sha256_file(project / 'project.json'))
            request = status['decision_request']
            kernel.resume({'request_id': request['request_id'], 'context_fingerprint': request['context_fingerprint'],
                           'selections': {'migration_action': 'non-destructive-migrate'}})
            self.assertEqual('3.0', kernel.project['schema_version'])
            self.assertEqual(before, sha256_file(project / '.history/migrations/v2/tree/project.json'))
            self.assertNotIn('asset_review_decision', kernel.state['decisions'])
            self.assertFalse(kernel.store.exists(f'{P09}/storyboard-package.json'))
            drive_to_completion(kernel, storyboard_durations=[4])

    def test_revised_delivery_has_no_self_hash_and_shot_scope_retains_other_shot(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = WorkflowKernel.initialize(Path(directory) / 'project', ['Fictional handoff'], input_type='novel')
            drive_to_completion(kernel, storyboard_durations=[4, 4])
            index = kernel.store.read('stages/09-故事板/shot-timeline-index.json')
            other = index['shots'][1]
            digest = sha256_file(kernel.store.path(other['path']))
            status = kernel.invalidate_from('shot_timeline_specs', shot_id='SHOT-001')
            self.assertEqual(['SHOT-001'], status['task_envelope']['shot_batch']['shot_ids'])
            drive_to_completion(kernel, storyboard_durations=[4, 4])
            self.assertEqual(digest, sha256_file(kernel.store.path(other['path'])))
            delivery = kernel.store.read(FINAL_DELIVERY_INDEX)
            self.assertNotIn(FINAL_DELIVERY_INDEX, [f['path'] for f in delivery['artifacts']])
            for item in delivery['artifacts']:
                self.assertEqual(item['sha256'], sha256_file(kernel.store.path(item['path'])))

    def test_appearance_revision_preserves_locked_space(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = WorkflowKernel.initialize(Path(directory) / 'project', ['Fictional handoff'], input_type='novel')
            drive_to_completion(kernel, storyboard_durations=[4])
            path = 'stages/08-站位与空间/scene-space-plan.json'
            digest = sha256_file(kernel.store.path(path))
            kernel.invalidate_from('asset_plan', asset_id='ASSET-CHAR-001')
            self.assertEqual('complete', kernel.state['stage_status']['spatial_lock_gate'])
            self.assertEqual('complete', kernel.state['stage_status']['shot_timeline_specs'])
            self.assertEqual(digest, sha256_file(kernel.store.path(path)))

    @unittest.skipUnless(shutil.which('ffmpeg'), 'Local FFmpeg required')
    def test_edit_order_trim_dissolve_audio_and_subtitles_are_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(directory)
            media = []
            for shot, color in [('Z', 'red'), ('A', 'blue')]:
                path = store.path(shot + '.mp4')
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color={color}:s=160x90:r=24:d=2',
                                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True)
                media.append({'shot_id': shot, 'path': path.name, 'sha256': sha256_file(path)})
            audio = store.path('voice.wav')
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=500:duration=0.5', str(audio)], check=True)
            plan = {'timeline': [{'shot_id': 'Z', 'in_s': .5, 'duration_s': 1.5},
                {'shot_id': 'A', 'duration_s': 1.5, 'transition_in': {'type': 'dissolve', 'duration_s': .5}}],
                'dialogue_table': [{'line_id': 'L', 'speaker_id': 'C', 'text': 'Test fixture', 'start_s': .2, 'duration_s': .6}]}
            result = execute_edit_plan(store, plan, media, audio_assets=[{'line_id': 'L', 'path': 'voice.wav'}], voice_strategy='tts')
            self.assertEqual(['Z', 'A'], result['shot_order'])
            self.assertAlmostEqual(2.5, result['duration_s'], places=1)
            self.assertEqual(['L'], result['mixed_line_ids'])
            self.assertEqual('muxed', result['subtitle_status'])
            self.assertTrue(any(s['codec_type'] == 'subtitle' for s in result['streams']))
            plan['subtitle_language'] = 'none'
            no_subtitles = execute_edit_plan(store, plan, media)
            self.assertFalse(any(s['codec_type'] == 'subtitle' for s in no_subtitles['streams']))
            plan['dialogue_table'][0]['duration_s'] = .1
            with self.assertRaisesRegex(ValueError, 'Voice exceeds'):
                execute_edit_plan(store, plan, media, audio_assets=[{'line_id': 'L', 'path': 'voice.wav'}], voice_strategy='tts')


if __name__ == '__main__':
    unittest.main()
