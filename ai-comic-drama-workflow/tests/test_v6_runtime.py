"""V6 runtime gateway regressions using local text only; no model or media calls."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from contextlib import redirect_stdout
import hashlib
import io
import json
import unittest
from unittest.mock import patch

from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_adapters import digest as native_digest
from ai_comic_drama_workflow.v5_modules import digest_file, read
from ai_comic_drama_workflow.v6_protocol import (candidate_digest,
                                                  envelope_digest,
                                                  envelope_input_digest,
                                                  expected_dispatch_id)
from ai_comic_drama_workflow.v6_runtime_fingerprint import RUNTIME_CODE_FILES
from ai_comic_drama_workflow.v6_runtime import V6CheckFailure, V6Runtime
from ai_comic_drama_workflow.v6_codex_host import receipt_from_spawn_result
from ai_comic_drama_workflow.transactions import transaction
from ai_comic_drama_workflow.v5_cli import main as cli_main


class V6RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def fresh(self, *, production_target: str = 'none') -> V6Runtime:
        return V6Runtime.initialize(
            self.base/'project', ['原创短片：演员在咖啡馆发现一封信。'],
            project_id='RUNTIME_TEST', delivery='text-only',
            production_target=production_target,
        )

    @staticmethod
    def rows(runtime: V6Runtime) -> dict[str, dict]:
        return {row['envelope']['node_id']: row
                for row in runtime.kernel.snapshot()['tasks'].values()}

    def test_first_run_records_source_skip_and_real_dispatch_action(self):
        runtime = self.fresh()
        self.assertEqual(runtime.project['orchestration_protocol'], '6.0')
        first = runtime.run()
        rows = self.rows(runtime)
        self.assertEqual(rows['sources']['state'], 'ACCEPTED')
        self.assertEqual(rows['reference_observation']['state'], 'NOT_APPLICABLE')
        self.assertEqual(rows['canon']['state'], 'DISPATCHING')
        self.assertEqual(first['status'], 'AWAITING_HOST')
        self.assertEqual(len(first['actions']), 1)
        action = first['actions'][0]
        self.assertEqual(action['tool'], 'collaboration.spawn_agent')
        self.assertEqual(action['preflight']['tool'], 'collaboration.list_agents')
        self.assertEqual(action['task_id'], rows['canon']['envelope']['task_id'])
        self.assertEqual(action['batch'], 1)

        canon = rows['canon']['envelope']
        self.assertEqual(canon['schema'], 'task-envelope/6.0')
        self.assertEqual(canon['scope'], {'kind': 'project', 'ids': []})
        self.assertEqual(canon['role'], 'canon')
        self.assertEqual(canon['execution_class'], 'professional')
        self.assertEqual(canon['input_digest'], envelope_input_digest(canon))
        self.assertEqual({item['task_id'] for item in canon['dependencies']},
                         {rows['sources']['envelope']['task_id'],
                          rows['reference_observation']['envelope']['task_id']})
        source_output = rows['sources']['envelope']['expected_artifacts'][0]['slot']
        self.assertIn(source_output, {item['slot'] for item in canon['inputs']})
        self.assertIn('frozen_task', {item['slot'] for item in canon['inputs']})
        self.assertEqual([item['source_slot'] for item in canon['handoffs']], [source_output])
        self.assertEqual(rows['reference_observation']['envelope']['expected_artifacts'][0]['kind'],
                         'ObservationRegister')

        # Reading pending host work is idempotent; only the host can create an agent.
        second = runtime.run()
        self.assertEqual(second['revision'], first['revision'])
        self.assertEqual(second['actions'][0]['dispatch_id'], action['dispatch_id'])
        self.assertEqual(len(runtime.kernel.snapshot()['tasks']), 3)

    def test_status_keeps_current_delivery_complete_when_older_tasks_are_stale(self):
        runtime = self.fresh()
        scope = {'kind': 'project', 'ids': []}
        stale = {'state': 'STALE', 'envelope': {'node_id': 'control', 'scope': scope,
                 'input_revision': 1, 'batch': 1}}
        accepted = {'state': 'ACCEPTED', 'envelope': {'node_id': 'preproduction_delivery',
                    'scope': scope, 'input_revision': 9, 'batch': 1}}
        snapshot = {'revision': 12, 'tasks': {'historical-control': stale,
                                              'current-delivery': accepted}}
        native = {'status': 'DELIVERED', 'preproduction_complete': True,
                  'video_complete': False, 'video_generated': False}
        with patch.object(runtime.kernel, 'snapshot', return_value=snapshot), \
             patch.object(runtime.v5, 'status', return_value=native):
            result = runtime.status()
        self.assertEqual(result['status'], 'DELIVERED')
        self.assertTrue(result['preproduction_complete'])
        self.assertFalse(result['video_complete'])
        self.assertEqual(result['v6_tasks']['historical-control']['state'], 'STALE')

    def test_status_uses_latest_delivery_attempt_and_video_boundary(self):
        runtime = self.fresh()
        scope = {'kind': 'project', 'ids': []}
        old = {'state': 'ACCEPTED', 'envelope': {'node_id': 'preproduction_delivery',
                'scope': scope, 'input_revision': 3, 'batch': 1}}
        latest = {'state': 'STALE', 'envelope': {'node_id': 'preproduction_delivery',
                   'scope': scope, 'input_revision': 4, 'batch': 1}}
        snapshot = {'revision': 8, 'tasks': {'old-delivery': old, 'latest-delivery': latest}}
        native = {'status': 'DELIVERED', 'preproduction_complete': True,
                  'video_complete': False, 'video_generated': False}
        with patch.object(runtime.kernel, 'snapshot', return_value=snapshot), \
             patch.object(runtime.v5, 'status', return_value=native):
            self.assertEqual(runtime.status()['status'], 'BLOCKED')

        video_runtime = V6Runtime.initialize(
            self.base/'video-project', ['原创短片：演员在咖啡馆发现一封信。'],
            project_id='VIDEO_STATUS_TEST', delivery='text-only', production_target='video')
        delivered = {'state': 'ACCEPTED', 'envelope': {'node_id': 'preproduction_delivery',
                    'scope': scope, 'input_revision': 5, 'batch': 1}}
        video_snapshot = {'revision': 10, 'tasks': {'preproduction': delivered}}
        video_native = {'status': 'PREPRODUCTION_DELIVERED', 'preproduction_complete': False,
                        'video_complete': False, 'video_generated': False}
        with patch.object(video_runtime.kernel, 'snapshot', return_value=video_snapshot), \
             patch.object(video_runtime.v5, 'status', return_value=video_native):
            result = video_runtime.status()
        self.assertEqual(result['status'], 'PREPRODUCTION_DELIVERED')
        self.assertTrue(result['preproduction_complete'])
        self.assertFalse(result['video_complete'])

    def test_stale_compile_lineage_invalidates_legacy_review(self):
        runtime = self.fresh()
        state = runtime.v5.state
        state['build'] = {'build_id': 'BUILD_CURRENT', 'input_fingerprint': 'f'*64}
        state['compile_review'] = {'status': 'ACCEPTED', 'build_id': 'BUILD_CURRENT',
                                   'audit': {'source': 'previous accepted review'}}
        runtime.v5.save(state)
        stale = {'state': 'STALE', 'envelope': {
            'task_id': 'OLD_COMPILE_REVIEW', 'node_id': 'compile_review',
            'scope': {'kind': 'project', 'ids': []}, 'input_revision': 5, 'batch': 1,
        }}
        with patch.object(runtime.kernel, 'snapshot', return_value={'tasks': {'old': stale}}):
            runtime._sync_native_invalidations()

        self.assertEqual(runtime.v5.state['compile_review']['status'], 'INVALIDATED')
        archives = list(runtime.path('history').glob('compile-review-invalidated-*.json'))
        self.assertEqual(len(archives), 1)
        self.assertEqual(read(archives[0])['status'], 'ACCEPTED')

    def test_accepted_compile_review_is_not_opened_again_for_the_same_build(self):
        runtime = self.fresh()
        build_id = 'b'*64
        state = runtime.v5.state
        state['build'] = {'build_id': build_id, 'input_fingerprint': 'f'*64,
                          'uri': 'builds/current', 'files': {}}
        state['compile_review'] = {'status': 'INVALIDATED', 'build_id': build_id,
                                   'audit': {'source': 'prior acceptance'}}
        state['active_task'] = 'TASK_duplicate'
        state['active_task_sha256'] = 'a'*64
        runtime.v5.save(state)
        runtime.write('runtime/tasks/TASK_duplicate.json',
                      {'kind': 'compile-review', 'task_id': 'TASK_duplicate'})
        runtime.write('runtime/tasks/TASK_accepted.json',
                      {'kind': 'compile-review', 'task_id': 'TASK_accepted',
                       'build': {'build_id': build_id}})
        accepted = {'state': 'ACCEPTED', 'envelope': {
            'task_id': 'TASK_accepted', 'node_id': 'compile_review',
        }}
        with patch.object(runtime, '_stage_rows', return_value=[accepted]):
            runtime._reconcile_accepted_compile_review()

        restored = runtime.v5.state
        self.assertEqual(restored['compile_review']['status'], 'ACCEPTED')
        self.assertEqual(restored['compile_review']['build_id'], build_id)
        self.assertEqual(restored['compile_review']['audit'], {'source': 'prior acceptance'})
        self.assertIsNone(restored['active_task'])
        self.assertIsNone(runtime.v5.compile_review_step())

        state = runtime.v5.state
        state['compile_review'] = {'status': 'INVALIDATED', 'build_id': build_id}
        state['active_task'] = 'TASK_other'
        runtime.v5.save(state)
        runtime.write('runtime/tasks/TASK_other.json', {'kind': 'qa', 'task_id': 'TASK_other'})
        runtime.write('runtime/tasks/TASK_other_build.json',
                      {'kind': 'compile-review', 'build': {'build_id': 'c'*64}})
        other = {'state': 'ACCEPTED', 'envelope': {
            'task_id': 'TASK_other_build', 'node_id': 'compile_review',
        }}
        with patch.object(runtime, '_stage_rows', return_value=[other]):
            runtime._reconcile_accepted_compile_review()
        kept = runtime.v5.state
        self.assertEqual(kept['compile_review']['status'], 'INVALIDATED')
        self.assertEqual(kept['active_task'], 'TASK_other')

    def test_historical_stale_compile_does_not_invalidate_newer_accepted_review(self):
        runtime = self.fresh()
        state = runtime.v5.state
        state['compile_review'] = {'status': 'ACCEPTED', 'build_id': 'CURRENT_BUILD'}
        runtime.v5.save(state)
        scope = {'kind': 'project', 'ids': []}
        stale = {'state': 'STALE', 'envelope': {
            'task_id': 'OLD_COMPILE_REVIEW', 'node_id': 'compile_review', 'scope': scope,
            'input_revision': 5, 'batch': 1,
        }}
        accepted = {'state': 'ACCEPTED', 'envelope': {
            'task_id': 'CURRENT_COMPILE_REVIEW', 'node_id': 'compile_review', 'scope': scope,
            'input_revision': 10, 'batch': 1,
        }}
        with patch.object(runtime.kernel, 'snapshot',
                           return_value={'tasks': {'old': stale, 'current': accepted}}):
            runtime._sync_native_invalidations()

        self.assertEqual(runtime.v5.state['compile_review']['status'], 'ACCEPTED')
        self.assertFalse(list(runtime.path('history').glob('compile-review-invalidated-*.json')))

    def test_compile_task_retries_after_staleness_with_next_batch(self):
        runtime = self.fresh()
        build_uri = 'runtime/compiled/compile-manifest.json'
        runtime.write(build_uri, b'locked compile manifest')
        state = runtime.v5.state
        state['build'] = {'build_id': 'CURRENT_BUILD', 'uri': 'runtime/compiled',
                          'files': {build_uri: digest_file(runtime.path(build_uri))}}
        runtime.v5.save(state)
        rows = {}
        created = []

        def create_graph_task(node_id, scope, task_id, *, batch, **kwargs):
            created.append((node_id, task_id, batch))
            rows[task_id] = {'envelope': {'task_id': task_id, 'batch': batch},
                             'state': 'PENDING', 'version': 0}
            return {'task_id': task_id}

        with (patch.object(runtime.kernel, 'snapshot',
                           side_effect=lambda: {'revision': 0, 'tasks': rows}),
              patch.object(runtime, 'create_graph_task', side_effect=create_graph_task),
              patch.object(runtime, '_event', return_value={}),
              patch.object(runtime.kernel, 'transition', return_value=None)):
            runtime._ensure_compile_task()
            first_id = created[0][1]
            rows[first_id]['state'] = 'STALE'
            runtime._ensure_compile_task()

        self.assertEqual([item[2] for item in created], [1, 2])
        self.assertEqual(created[0][1], created[1][1])

    def test_skip_identity_changes_when_accepted_predecessor_version_changes(self):
        runtime = self.fresh()
        runtime.run()
        scope = {'kind': 'project', 'ids': []}
        source_id = self.rows(runtime)['sources']['envelope']['task_id']
        context = runtime.kernel._applicability_context()
        with patch('ai_comic_drama_workflow.v6_runtime.predecessor_task_ids',
                   return_value=[source_id]), \
             patch.object(runtime, '_scope_catalogue', return_value={}), \
             patch.object(runtime, '_scope_links', return_value={}):
            old = runtime._skip_task_id('visual_prompts', scope, context)
            changed = runtime.kernel.snapshot()
            changed['tasks'][source_id]['version'] += 1
            with patch.object(runtime.kernel, 'snapshot', return_value=changed):
                new = runtime._skip_task_id('visual_prompts', scope, context)
        self.assertNotEqual(old, new)

    def test_authorized_project_change_archives_mutable_event_evidence(self):
        runtime = self.fresh()
        source = runtime.root/'project.json'
        old_bytes = source.read_bytes()
        old_hash = hashlib.sha256(old_bytes).hexdigest()
        with transaction(runtime.root):
            archived = runtime._archive_project_evidence()
            project = read(source)
            project['target'] = 'seedance2.0'
            runtime.write('project.json', project)
        self.assertEqual(digest_file(runtime.path(archived)), old_hash)
        self.assertEqual(runtime.kernel._file_matches('project.json', old_hash,
                                                       label='historical event evidence'), None)
        self.assertEqual(runtime.kernel._read_store()[0]['schema_version'], '6.0')

    def test_migration_copies_original_evidence_without_fabricating_v6_completion(self):
        old = V5Kernel.initialize(self.base/'old', ['原始故事资料。'],
                                  project_id='MIGRATION_TEST', delivery='text-only')
        note = old.root/'author-note.txt'
        note.write_text('原始创作说明，不是 V6 审阅记录。', encoding='utf-8')
        expected_hash = hashlib.sha256(note.read_bytes()).hexdigest()
        runtime = V6Runtime.migrate(old.root, self.base/'migrated')

        self.assertEqual(read(old.root/'project.json').get('orchestration_protocol'), None)
        self.assertEqual(runtime.project['orchestration_protocol'], '6.0')
        copied = read(runtime.root/'imports/migration.json')
        row = next(item for item in copied['files'] if item['original'] == note.name)
        self.assertEqual(row['sha256'], expected_hash)
        self.assertEqual(digest_file(runtime.root/row['uri']), expected_hash)
        self.assertEqual(copied['status'], 'COPIED_REVIEW_REQUIRED')
        self.assertEqual(runtime.kernel.snapshot()['tasks'], {})
        self.assertEqual(runtime.v5.state['completed_tasks'], {})
        runtime.run()
        canon = self.rows(runtime)['canon']['envelope']
        self.assertIn({'slot': 'migration_report', 'uri': 'imports/migration.json',
                       'sha256': digest_file(runtime.root/'imports/migration.json'), 'version': 0},
                      canon['inputs'])
        (runtime.root/'imports/migration.json').write_text('{}', encoding='utf-8')
        blocked = runtime.run()
        self.assertEqual(blocked['status'], 'BLOCKED')
        self.assertEqual(self.rows(runtime)['canon']['state'], 'STALE')

    def test_accepted_native_task_detects_explicit_v5_invalidation(self):
        runtime = self.fresh()
        runtime.run()
        envelope = self.rows(runtime)['canon']['envelope']
        state = runtime.v5.state
        state['artifacts']['canon'] = {'sha256': 'a' * 64, 'invalidated': False}
        runtime.v5.save(state)
        self.assertFalse(runtime.kernel._input_changed(envelope, accepted=True))
        state = runtime.v5.state
        state['artifacts']['canon']['invalidated'] = True
        runtime.v5.save(state)
        self.assertTrue(runtime.kernel._input_changed(envelope, accepted=True))

    def test_accepted_director_detects_stale_semantic_review_after_snapshot(self):
        runtime = self.fresh()
        value = {'timeline': {'semantic_review': {'status': 'PASS',
                 'reviewer': 'independent', 'findings': ['checked'],
                 'input_sha256': '0' * 64}}}
        uri = 'artifacts/director/current.json'
        runtime.write(uri, value)
        state = runtime.v5.state
        state['artifacts']['director'] = {'uri': uri, 'sha256': digest_file(runtime.path(uri)),
                                          'invalidated': False}
        runtime.v5.save(state)
        with (patch.object(runtime.kernel, '_verify_inputs'),
              patch.object(runtime.kernel, '_verify_module')):
            self.assertTrue(runtime.kernel._input_changed({'node_id': 'director',
                'scope': {'kind': 'project', 'ids': []}}, accepted=True))

    def test_stale_v6_director_invalidates_native_stage_selection(self):
        runtime = self.fresh()
        state = runtime.v5.state
        state['artifacts']['director'] = {'sha256': 'a' * 64, 'invalidated': False}
        runtime.v5.save(state)
        scope = {'kind': 'project', 'ids': []}
        old = {'state': 'STALE', 'envelope': {'node_id': 'director', 'scope': scope}}
        with patch.object(runtime.kernel, 'snapshot', return_value={'tasks': {'old': old}}):
            runtime._sync_native_invalidations()
        self.assertTrue(runtime.v5.state['artifacts']['director']['invalidated'])

    def test_agent_cancel_requires_current_ack_and_replays_exact_command(self):
        runtime = self.fresh()
        action = runtime.run()['actions'][0]
        receipt = receipt_from_spawn_result(
            action, {'task_name': '/root/'+action['task_name']},
            project_root=runtime.root, sent_at='2026-09-25T10:00:00Z',
            observed_at='2026-09-25T10:00:01Z', host_call_id='cancel-dispatch')
        runtime.agent_event(receipt, command_id='cancel-dispatch',
                            expected_revision=runtime.kernel.snapshot()['revision'])
        task_id = action['task_id']
        with self.assertRaisesRegex(ValueError, 'CANCEL_ACK'):
            runtime.agent_cancel(task_id, 'ACK_MISSING', command_id='cancel-premature',
                                 expected_revision=runtime.kernel.snapshot()['revision'])
        ack = {'schema': 'agent-message/6.0', 'message_id': 'CANCEL_ACK_1',
               'task_id': task_id, 'batch': action['batch'],
               'sender_id': receipt['agent_id'], 'recipient_id': 'kernel',
               'in_reply_to': None, 'type': 'CANCEL_ACK',
               'summary': 'Cancelled after upstream revision request',
               'evidence': ['project.json'], 'subject_uri': None,
               'subject_sha256': None, 'at': '2026-09-25T10:00:02Z'}
        runtime.agent_message(ack, command_id='cancel-ack',
                              expected_revision=runtime.kernel.snapshot()['revision'])
        revision = runtime.kernel.snapshot()['revision']
        result = runtime.agent_cancel(task_id, ack['message_id'], command_id='cancel-accepted',
                                      expected_revision=revision)
        self.assertEqual(result['status'], 'CANCELLED')
        self.assertEqual(runtime.kernel.snapshot()['tasks'][task_id]['state'], 'CANCELLED')
        replay = runtime.agent_cancel(task_id, ack['message_id'], command_id='cancel-accepted',
                                      expected_revision=revision)
        self.assertEqual(replay['status'], 'ALREADY_RECORDED')
        with self.assertRaisesRegex(ValueError, 'COMMAND_COLLISION'):
            runtime.agent_cancel(task_id, 'DIFFERENT_ACK', command_id='cancel-accepted',
                                 expected_revision=revision)

    def test_v6_gateway_rejects_legacy_submit_and_import_paths(self):
        runtime = self.fresh()
        for command in ('submit', 'import-artifact', 'import-compiled', 'compile',
                        'begin-image', 'recover-image', 'import-observation'):
            with self.subTest(command=command):
                with self.assertRaisesRegex(ValueError, 'requires a V6 candidate'):
                    runtime.v5_command(SimpleNamespace(command=command))

        # A separately opened V5 kernel must not mutate a marked V6 project.
        direct = V5Kernel(runtime.root)
        with self.assertRaisesRegex(ValueError, 'V6 project mutations require'):
            direct.submit({})
        with self.assertRaisesRegex(ValueError, 'V6 project mutations require'):
            direct.import_artifact('canon', str(runtime.root/'project.json'))
        with self.assertRaisesRegex(ValueError, 'V6 project mutations require'):
            direct.run()
        self.assertEqual(runtime.kernel.snapshot()['tasks'], {})

    def test_cli_image_wrapper_rejects_unknown_fields_before_host_action(self):
        runtime = self.fresh()
        runtime.run()
        task_id = self.rows(runtime)['canon']['envelope']['task_id']
        wrapper = self.base/'image-wrapper.json'
        wrapper.write_text(json.dumps({'command_id': 'CLI_BAD',
                                       'expected_revision': runtime.kernel.snapshot()['revision'],
                                       'task_id': task_id, 'unexpected': True}), encoding='utf-8')
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli_main(['image-begin', str(runtime.root), '--file', str(wrapper)])
        self.assertEqual(code, 1)
        self.assertIn('Command wrapper fields differ', output.getvalue())
        self.assertEqual(self.rows(runtime)['canon']['state'], 'DISPATCHING')

    def test_final_gate_rejects_missing_nodes_and_export(self):
        runtime = self.fresh(production_target='video')
        runtime.run()
        report = runtime.validate(final=True)
        self.assertFalse(report['valid'])
        self.assertTrue(any(item.startswith('V6 stage incomplete: preproduction_delivery')
                            for item in report['errors']))
        self.assertTrue(any(item.startswith('V6 stage incomplete: video_delivery')
                            for item in report['errors']))
        self.assertEqual(runtime.export()['status'], 'BLOCKED')
        self.assertFalse(runtime.status()['preproduction_complete'])
        self.assertFalse(runtime.status()['video_complete'])

    def test_parallel_art_promotion_restores_only_the_reviewed_frozen_task(self):
        runtime = self.fresh()
        records = []
        for scene in ('SCENE_A', 'SCENE_B'):
            task_id = 'ART_'+scene
            uri = f'runtime/tasks/{task_id}.json'
            runtime.write(uri, {'task_id': task_id, 'kind': 'art',
                                'scope': {'scene_ids': [scene]}})
            records.append({'envelope': {
                'node_id': 'art', 'task_id': task_id,
                'scope': {'kind': 'scene', 'ids': [scene]},
                'inputs': [{'slot': 'frozen_task', 'uri': uri,
                            'sha256': digest_file(runtime.path(uri))}],
            }})
        with patch.object(runtime, '_active', return_value=records):
            for first, second in ((0, 1), (1, 0)):
                state = runtime.v5.state
                state['active_task'] = records[second]['envelope']['task_id']
                runtime.v5.save(state)
                runtime._restore_parallel_native_task(records[first])
                task_id = records[first]['envelope']['task_id']
                self.assertEqual(runtime.v5.state['active_task'], task_id)
                self.assertEqual(runtime.v5.state['active_task_sha256'],
                                 native_digest(read(runtime.path(
                                     f'runtime/tasks/{task_id}.json'))))
                state = runtime.v5.state
                state['active_task'] = None
                runtime.v5.save(state)
                runtime._restore_parallel_native_task(records[second])
                self.assertEqual(runtime.v5.state['active_task'],
                                 records[second]['envelope']['task_id'])

            state = runtime.v5.state
            state['active_task'] = 'UNRELATED'
            runtime.v5.save(state)
            with self.assertRaisesRegex(ValueError, 'unrelated native active task'):
                runtime._restore_parallel_native_task(records[0])
            state['active_task'] = None
            runtime.v5.save(state)
            runtime.write('runtime/tasks/ART_SCENE_A.json', {'task_id': 'TAMPERED'})
            with self.assertRaisesRegex(ValueError, 'Frozen parallel task bytes changed'):
                runtime._restore_parallel_native_task(records[0])

    def test_parallel_image_prompt_promotion_checks_scope_and_stage(self):
        runtime = self.fresh()
        for node_id, stage, scope_kind in (('visual_prompts', 5, 'asset'),
                                            ('board_prompts', 7, 'panel')):
            task_id = 'PROMPT_'+str(stage)
            key = 'IMAGE_'+str(stage)
            uri = f'runtime/tasks/{task_id}.json'
            task = {'task_id': task_id, 'kind': 'image-prompt',
                    'slot': key, 'stage': stage}
            runtime.write(uri, task)
            record = {'envelope': {
                'node_id': node_id, 'task_id': task_id,
                'scope': {'kind': scope_kind, 'ids': [key]},
                'inputs': [{'slot': 'frozen_task', 'uri': uri,
                            'sha256': digest_file(runtime.path(uri))}],
            }}
            with patch.object(runtime, '_active', return_value=[record]):
                state = runtime.v5.state
                state['active_task'] = None
                runtime.v5.save(state)
                runtime._restore_parallel_native_task(record)
                self.assertEqual(runtime.v5.state['active_task'], task_id)
                bad = json.loads(json.dumps(record))
                bad['envelope']['scope']['ids'] = ['WRONG']
                with self.assertRaisesRegex(ValueError, 'reviewed V6 scope'):
                    runtime._restore_parallel_native_task(bad)

    def test_parallel_image_prompt_queue_is_bounded_and_scope_specific(self):
        runtime = self.fresh()
        active = {'envelope': {'node_id': 'visual_prompts', 'task_id': 'PROMPT_A',
                               'scope': {'kind': 'asset', 'ids': ['ASSET_A']}}}
        jobs = [{'key': key, 'fingerprint': key, 'dependencies': []}
                for key in ('ASSET_A', 'ASSET_B')]
        next_row = {'envelope': {'node_id': 'visual_prompts', 'task_id': 'PROMPT_B'},
                    'version': 1, 'state': 'PENDING'}
        with (patch.object(runtime, '_active', return_value=[active]),
              patch.object(runtime, '_stage_rows', return_value=[active]),
              patch.object(runtime, '_scope_catalogue', return_value={}),
              patch.object(runtime, '_scope_links', return_value={}),
              patch.object(runtime.v5, 'image_jobs', return_value=jobs),
              patch.object(runtime.v5, 'task', return_value={'task': {'task_id': 'PROMPT_B'}}) as native,
              patch.object(runtime, '_envelope', return_value={'batch': 1}),
              patch.object(runtime.kernel, 'snapshot', return_value={'tasks': {'PROMPT_B': next_row}}),
              patch.object(runtime, '_event', side_effect=lambda row, to_state, *args, **kwargs: to_state),
              patch.object(runtime.kernel, 'transition') as transition,
              patch('ai_comic_drama_workflow.v6_runtime.predecessor_task_ids', return_value=[])):
            runtime._queue_parallel_prompts()
            self.assertEqual(native.call_args.args[:4],
                             ('image-prompt', 'ASSET_B', 5, 'image-prompt-optimizer'))
            self.assertEqual([call.args[0] for call in transition.call_args_list],
                             ['READY', 'DISPATCHING'])

        with (patch.object(runtime, '_active', return_value=[active, active]),
              patch.object(runtime.v5, 'task') as native):
            runtime._queue_parallel_prompts()
            native.assert_not_called()

    def test_changed_source_cannot_leave_old_dispatch_action_usable(self):
        runtime = self.fresh()
        first = runtime.run()
        source = runtime.v5.state['sources'][0]
        (runtime.root/source['uri']).write_text('来源已经改变。', encoding='utf-8')
        after = runtime.run()
        self.assertEqual(after['status'], 'BLOCKED')
        self.assertEqual({row['state'] for row in self.rows(runtime).values()}, {'STALE'})
        self.assertFalse(any(action.get('dispatch_id') == first['actions'][0]['dispatch_id']
                             for action in after.get('actions', [])),
                         'A dispatch tied to old source bytes must not remain actionable')

    def test_failed_result_replay_is_idempotent_and_changed_payload_collides(self):
        runtime = self.fresh()
        action = runtime.run()['actions'][0]
        task_id = action['task_id']
        receipt = receipt_from_spawn_result(
            action, {'task_name': '/root/'+action['task_name']},
            project_root=runtime.root, sent_at='2026-09-25T10:00:00Z',
            observed_at='2026-09-25T10:00:01Z', host_call_id='local-dispatch-1')
        dispatch_revision = runtime.kernel.snapshot()['revision']
        runtime.agent_event(receipt, command_id='runtime-host-1',
                            expected_revision=dispatch_revision)
        self.assertEqual(runtime.agent_event(receipt, command_id='runtime-host-1',
                                            expected_revision=dispatch_revision)['status'],
                         'ALREADY_RECORDED')
        with self.assertRaisesRegex(ValueError, 'COMMAND_COLLISION'):
            runtime.agent_event(receipt, command_id='runtime-host-1',
                                expected_revision=runtime.kernel.snapshot()['revision'])
        candidate = {'task_id': task_id, 'result_uri': None, 'agent_id': receipt['agent_id']}
        before = runtime.kernel.snapshot()['revision']
        first = runtime.agent_result(candidate, command_id='runtime-result-1',
                                     expected_revision=before)
        self.assertGreater(runtime.kernel.snapshot()['revision'], before)
        revision = runtime.kernel.snapshot()['revision']
        repeated = runtime.agent_result(candidate, command_id='runtime-result-1',
                                        expected_revision=before)
        self.assertEqual(repeated['status'], 'ALREADY_RECORDED')
        self.assertEqual(runtime.kernel.snapshot()['revision'], revision)
        self.assertIn(first['status'], ('AWAITING_HOST', 'RETRY_REQUIRED'))
        with self.assertRaisesRegex(ValueError, 'different content'):
            runtime.agent_result(dict(candidate, result_uri='other.json'),
                                 command_id='runtime-result-1', expected_revision=before)
        with self.assertRaisesRegex(ValueError, 'different content'):
            runtime.agent_result(candidate, command_id='runtime-result-1',
                                 expected_revision=revision)

    def test_native_semantics_are_checked_before_independent_review(self):
        runtime = self.fresh()
        runtime.run()
        record = self.rows(runtime)['canon']
        task_id = record['envelope']['task_id']
        native_task = read(runtime.root/'runtime/tasks'/(task_id+'.json'))
        prefix = f'runtime/v6/candidates/{task_id}/1/'
        artifact_uri = prefix+'Canon.json'
        runtime.write(artifact_uri, {'project_id': runtime.project['project_id'],
                                     'revision': 1, 'content': '原创场景',
                                     'source_refs': ['UNKNOWN_SOURCE'],
                                     'entities': [], 'locks': []})
        artifact = runtime.path(artifact_uri)
        result_uri = prefix+'role-result.json'
        runtime.write(result_uri, {
            'schema': 'role-result/5.0', 'task_id': task_id,
            'context_fingerprint': native_task['context_fingerprint'],
            'checks': ['synthetic source review'], 'conflicts': [], 'unresolved': [],
            'artifact': str(artifact), 'artifact_sha256': digest_file(artifact),
        })
        candidate = {'result_uri': result_uri,
                     'result_sha256': digest_file(runtime.path(result_uri)),
                     'artifacts': [{'uri': artifact_uri,
                                    'sha256': digest_file(artifact)}],
                     'unresolved': []}
        with self.assertRaisesRegex(ValueError, 'Unknown narrative source ID'):
            runtime._validate_v5_candidate({**record, 'candidate': candidate})

    def test_image_prompt_contract_is_checked_before_independent_review(self):
        runtime = self.fresh()
        task_id = 'PROMPT_PREFLIGHT'
        runtime.write(f'runtime/tasks/{task_id}.json', {
            'task_id': task_id, 'context_fingerprint': 'f' * 64,
            'kind': 'image-prompt', 'slot': 'ASSET_TEST', 'job': {},
        })
        result_uri = f'runtime/v6/candidates/{task_id}/1/role-result.json'
        runtime.write(result_uri, {'schema': 'role-result/5.0', 'task_id': task_id,
                                   'context_fingerprint': 'f' * 64, 'checks': ['synthetic'],
                                   'conflicts': [], 'unresolved': [], 'prompt': 'synthetic'})
        record = {'envelope': {'task_id': task_id}, 'candidate': {
            'result_uri': result_uri, 'result_sha256': digest_file(runtime.path(result_uri)),
            'artifacts': [], 'unresolved': [],
        }}
        with (patch.object(runtime.v5, 'receipt_audit'),
              patch.object(runtime.v5, 'accept_prompt', side_effect=ValueError('contract missing')) as check):
            with self.assertRaisesRegex(ValueError, 'contract missing'):
                runtime._validate_v5_candidate(record)
            check.assert_called_once()

        prompt_uri = f'runtime/v6/candidates/{task_id}/1/prompt.txt'
        runtime.write(prompt_uri, 'A quiet cafe at dawn.\n'.encode())
        prompt_path = runtime.path(prompt_uri)
        role_result = read(runtime.path(result_uri))
        role_result.update({'artifact': str(prompt_path),
                            'artifact_sha256': digest_file(prompt_path)})
        runtime.write(result_uri, role_result)
        record['candidate'].update({
            'result_sha256': digest_file(runtime.path(result_uri)),
            'artifacts': [{'kind': 'VisualImagePrompt', 'uri': prompt_uri,
                           'sha256': digest_file(prompt_path)}],
        })
        with (patch.object(runtime.v5, 'receipt_audit'),
              patch.object(runtime.v5, 'accept_prompt') as check,
              patch.object(runtime.v5, 'check_content') as json_check):
            runtime._validate_v5_candidate(record)
            check.assert_called_once()
            json_check.assert_not_called()

    def test_failed_parallel_prompt_reconciles_native_serial_pointer(self):
        runtime = self.fresh()
        failed_id, active_id = 'FAILED_PROMPT', 'ACTIVE_PROMPT'
        native = {'task_id': active_id, 'kind': 'image-prompt', 'stage': 5,
                  'context_fingerprint': 'f' * 64, 'slot': 'ASSET_ACTIVE'}
        runtime.write(f'runtime/tasks/{active_id}.json', native)
        rows = {
            failed_id: {'state': 'FAILED', 'envelope': {'task_id': failed_id,
                'node_id': 'visual_prompts'}},
            active_id: {'state': 'RUNNING', 'envelope': {'task_id': active_id,
                'node_id': 'visual_prompts'}},
        }
        state = runtime.v5.state
        state['active_task'] = failed_id
        runtime.v5.save(state)
        with (patch.object(runtime.kernel, 'snapshot', return_value={'tasks': rows}),
              patch.object(runtime.v5, 'save') as save):
            runtime._reconcile_native_active_task('visual_prompts', [rows[active_id]])
        saved = save.call_args.args[0]
        self.assertEqual(saved['active_task'], active_id)
        self.assertEqual(saved['active_task_sha256'], native_digest(native))

    def test_upstream_repair_brief_rejects_unbound_or_extra_fields(self):
        from ai_comic_drama_workflow.v6_protocol import V6ProtocolError, validate_v6_protocol
        brief = {'schema': 'upstream-repair-brief/6.0', 'route_id': 'UPR_'+'a'*24,
                 'project_id': 'RUNTIME_TEST', 'source_task_id': 'COMPILE_TASK',
                 'source_batch': 1, 'source_node_id': 'compile',
                 'candidate_digest': 'b'*64, 'owner_node_id': 'director',
                 'owner_task_id': 'DIRECTOR_TASK',
                 'review': {'uri': 'runtime/v6/reviews/COMPILE_TASK/1/review-failure.json',
                            'sha256': 'c'*64, 'reviewer_agent_id': '/root/reviewer',
                            'reviewer_dispatch_id': 'review-dispatch'},
                 'failed_checks': [{'id': 'compile_semantics',
                                    'evidence': ['runtime/v6/reviews/COMPILE_TASK/1/check.json']}],
                 'instruction': 'Correct the reviewed upstream defect.'}
        validate_v6_protocol('upstream-repair-brief', brief)
        with self.assertRaises(V6ProtocolError):
            validate_v6_protocol('upstream-repair-brief', {**brief, 'unbound': True})

    def test_failed_compile_review_is_routed_with_original_review_evidence(self):
        runtime = self.fresh()
        source_id, owner_id, repaired_id = 'FAILED_COMPILE', 'ACCEPTED_DIRECTOR', 'NEW_DIRECTOR'
        candidate = {'schema': 'candidate-result/6.0', 'task_id': source_id,
                     'batch': 1, 'agent_id': '/root/creator', 'result_uri': None,
                     'result_sha256': None, 'artifacts': [], 'module_receipts': [],
                     'checks': [], 'handoffs': [], 'unresolved': []}
        review_uri = f'runtime/v6/reviews/{source_id}/1/review-record.json'
        check_uri = f'runtime/v6/reviews/{source_id}/1/check.json'
        runtime.write(check_uri, {'finding': 'Director camera coordinates conflict.'})
        review = {'schema': 'review-record/6.0', 'task_id': source_id, 'batch': 1,
                  'reviewer_agent_id': '/root/reviewer',
                  'reviewer_dispatch_id': 'review-dispatch',
                  'candidate_digest': candidate_digest(candidate),
                  'checks': [{'id': 'compile_manifest', 'status': 'FAIL',
                              'evidence': [check_uri]}],
                  'failure_owner': 'director', 'at': '2026-09-25T10:00:00Z'}
        runtime.write(review_uri, review)
        digest = lambda value: hashlib.sha256(json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        failure_uri = f'runtime/v6/failures/{source_id}/1/failure.json'
        runtime.write(failure_uri, {'reviewer_failure_owner': 'director',
            'candidate_digest': candidate_digest(candidate), 'submission_digest': digest(review),
            'review_record_uri': review_uri, 'review_record_sha256': digest_file(runtime.path(review_uri))})
        source = {'state': 'FAILED', 'version': 1,
                  'envelope': {'task_id': source_id, 'batch': 1, 'node_id': 'compile',
                               'dependencies': []}, 'candidate': candidate,
                  'receipt': {'agent_id': '/root/creator'},
                  'review_dispatch': {'agent_id': '/root/reviewer',
                                      'dispatch_id': 'review-dispatch'},
                  'messages': []}
        source['messages'].append({'type': 'RESULT', 'sender_id': '/root/reviewer',
                                   'subject_uri': review_uri,
                                   'subject_sha256': digest_file(runtime.path(review_uri))})
        owner = {'state': 'ACCEPTED', 'envelope': {'task_id': owner_id,
                 'node_id': 'director', 'scope': {'kind': 'project', 'ids': []}}}
        repaired = {'state': 'READY', 'version': 1,
                    'envelope': {'task_id': repaired_id,
                                 'batch': 1, 'node_id': 'director'}}
        rows = {source_id: source, owner_id: owner, repaired_id: repaired}
        runtime.write('runtime/v6/events.json', [{'payload': {'event': {
            'task_id': source_id, 'batch': 1, 'to_state': 'FAILED',
            'reason': 'REVIEW_FAILED', 'evidence': [failure_uri]}}}])
        envelope = {'task_id': repaired_id, 'batch': 1, 'node_id': 'director'}
        native = {'task_id': repaired_id, 'kind': 'director'}
        with (patch.object(runtime.kernel, 'snapshot', return_value={'revision': 10,
                                                                    'tasks': rows}),
              patch.object(runtime.kernel, 'transition'),
              patch.object(runtime, '_task_dependency_closure', return_value={owner_id}),
              patch.object(runtime, '_revise_review_owner') as revise,
              patch.object(runtime, '_stale_changed_inputs', return_value=[]),
              patch.object(runtime.v5, 'run', return_value={'task': native}),
              patch.object(runtime, '_envelope', return_value=envelope) as make_envelope,
              patch.object(runtime, 'run', return_value={'status': 'AWAITING_HOST'})):
            result = runtime._route_upstream_review_failure(source)
        self.assertEqual(result, {'status': 'AWAITING_HOST'})
        revise.assert_called_once_with('director', owner)
        inputs = make_envelope.call_args.kwargs['extra_inputs']
        self.assertEqual(inputs[0]['slot'], 'upstream_repair')
        self.assertEqual(inputs[0]['uri'], 'runtime/v6/upstream-repair/UPR_'
                         +digest({'source_task_id': source_id, 'source_batch': 1,
                                  'owner_node_id': 'director',
                                  'candidate_digest': candidate_digest(candidate)})[:24]+'.json')
        brief = read(runtime.path(inputs[0]['uri']))
        self.assertEqual(brief['owner_task_id'], repaired_id)
        self.assertEqual(brief['review']['sha256'], digest_file(runtime.path(review_uri)))

    def test_compile_runtime_code_is_frozen_and_changes_stale_its_binding(self):
        runtime = self.fresh()
        source_root = self.base/'runtime-source'
        source_root.mkdir()
        for name in RUNTIME_CODE_FILES:
            (source_root/name).write_text('initial:'+name, encoding='utf-8')
        runtime._runtime_code_root = source_root
        with transaction(runtime.root):
            resources = runtime._runtime_code_resources('compile')
        envelope = {'node_id': 'compile', 'resources': resources}
        self.assertFalse(runtime._runtime_code_changed(envelope))
        (source_root/'v51_adapters.py').write_text('corrected adapter', encoding='utf-8')
        self.assertTrue(runtime._runtime_code_changed(envelope))

    def test_compile_route_brief_hash_binds_final_content_and_creation_is_atomic(self):
        runtime = self.fresh()
        build_uri = 'runtime/compiled/compile-manifest.json'
        runtime.write(build_uri, b'locked compile manifest')
        state = runtime.v5.state
        state['build'] = {'build_id': 'CURRENT_BUILD', 'uri': 'runtime/compiled',
                          'files': {build_uri: digest_file(runtime.path(build_uri))}}
        runtime.v5.save(state)
        route_uri = 'runtime/v6/compile-semantic-failures/CSF_fixture.json'
        runtime.write(route_uri, {'schema': 'compile-semantic-failure/6.0'})
        route = {'uri': route_uri, 'sha256': digest_file(runtime.path(route_uri)),
                 'record': {'build_id': 'FAILED_BUILD', 'source_batch': 1}}
        rows = {}

        def create_graph_task(node_id, scope, task_id, *, batch, extra_inputs, **kwargs):
            brief_input = next(item for item in extra_inputs if item['slot'] == 'compile_brief')
            brief_path = runtime.path(brief_input['uri'])
            self.assertEqual(brief_input['sha256'], digest_file(brief_path))
            self.assertEqual(read(brief_path)['compile_semantic_failure'], route_uri)
            runtime.write('runtime/v6/created-during-compile-task.json', {'task_id': task_id})
            rows[task_id] = {'envelope': {'task_id': task_id, 'batch': batch},
                             'state': 'PENDING', 'version': 0}
            return {'task_id': task_id}

        with (patch.object(runtime, '_latest_compile_semantic_failure', return_value=route),
              patch.object(runtime.kernel, 'snapshot',
                           side_effect=lambda: {'revision': 0, 'tasks': rows}),
              patch.object(runtime, 'create_graph_task', side_effect=create_graph_task),
              patch.object(runtime, '_event', return_value={}),
              patch.object(runtime.kernel, 'transition', side_effect=[None, RuntimeError('commit failed')])):
            with self.assertRaisesRegex(RuntimeError, 'commit failed'):
                runtime._ensure_compile_task()

        self.assertFalse(runtime.path('runtime/v6/created-during-compile-task.json').exists())
        brief_dir = runtime.path('runtime/v6/task-briefs')
        self.assertFalse(list(brief_dir.glob('*.json')) if brief_dir.exists() else [])

    def test_compile_semantic_failure_route_requires_bound_owner_and_artifact(self):
        runtime = self.fresh()
        task_id = 'FAILED_COMPILE_REVIEW'
        batch = 1
        context = 'a'*64
        build_id = 'b'*64
        agent_id = '/root/compiler-reviewer'
        prefix = f'runtime/v6/candidates/{task_id}/{batch}/'
        artifact_uri = prefix+'compile-review.json'
        finding = 'AVIR terminal visibility differs from its authoritative timeline boundary.'
        semantic = {'build_id': build_id, 'equivalent': False,
                    'failure_owner': 'compile', 'finding_code': 'AVIR_END_VISIBILITY_CONFLICT',
                    'finding': finding}
        artifact = {'project_id': 'RUNTIME_TEST', 'build_id': build_id,
                    'equivalent': False, 'failure_owner_node': 'compile',
                    'finding_code': semantic['finding_code'], 'finding': finding}
        runtime.write(artifact_uri, artifact)
        module = read(runtime.root/'modules.lock.json')['modules']['video-prompt-compiler']
        envelope = {'schema': 'task-envelope/6.0', 'project_id': 'RUNTIME_TEST',
                    'node_id': 'compile_review', 'task_id': task_id, 'batch': batch,
                    'role': 'compiler_reviewer', 'execution_class': 'review',
                    'scope': {'kind': 'project', 'ids': []}, 'input_revision': 0,
                    'inputs': [], 'input_digest': '',
                    'module': {'name': 'video-prompt-compiler',
                               'version': module['version'], 'sha256': module['sha256']},
                    'resources': [],
                    'expected_artifacts': [{'slot': 'compile_review:project:project:CompileReview',
                                            'kind': 'CompileReview', 'uri_prefix': prefix}],
                    'validators': [{'id': 'module_receipt', 'kind': 'hash'},
                                   {'id': 'compile_semantics', 'kind': 'manual'}],
                    'dependencies': [{'task_id': 'V6_compile_fixture'}], 'handoffs': []}
        envelope['input_digest'] = envelope_input_digest(envelope)
        result_uri = prefix+'role-result.json'
        result = {'schema': 'role-result/5.1', 'task_id': task_id,
                  'context_fingerprint': context, 'checks': [{'id': 'compile_semantics'}],
                  'conflicts': [], 'unresolved': [],
                  'artifact': str(runtime.path(artifact_uri)),
                  'artifact_sha256': digest_file(runtime.path(artifact_uri)),
                  'semantic_review': semantic}
        runtime.write(result_uri, result)
        runtime.write('runtime/tasks/'+task_id+'.json', {
            'task_id': task_id, 'kind': 'compile-review', 'context_fingerprint': context,
            'build': {'build_id': build_id, 'files': {}},
        })
        candidate = {'schema': 'candidate-result/6.0', 'task_id': task_id,
                     'batch': batch, 'agent_id': agent_id,
                     'input_digest': envelope['input_digest'],
                     'result_uri': result_uri, 'result_sha256': digest_file(runtime.path(result_uri)),
                     'artifacts': [{'slot': 'compile-review', 'kind': 'CompileReview',
                                    'uri': artifact_uri,
                                    'sha256': digest_file(runtime.path(artifact_uri))}],
                     'module_receipts': [], 'checks': [], 'handoffs': [], 'unresolved': []}
        runtime.write(prefix+'candidate-result.json', candidate)
        failure = {'failed_check': 'compile_semantics',
            'candidate_digest': candidate_digest(candidate),
            'submission_digest': candidate_digest(candidate)}
        failure_uri = f'runtime/v6/failures/{task_id}/{batch}/{candidate_digest(failure)}.json'
        runtime.write(failure_uri, failure)
        host_uri = 'runtime/v6/host-evidence/'
        runtime.write(host_uri+'raw-placeholder.json', {'task_name': agent_id})
        host_sha = digest_file(runtime.path(host_uri+'raw-placeholder.json'))
        runtime.path(host_uri+'raw-placeholder.json').replace(runtime.path(host_uri+host_sha+'.json'))
        runtime.write(host_uri+host_sha+'.json', {'task_name': agent_id})
        dispatch = {'schema': 'dispatch-receipt/6.0', 'task_id': task_id,
                    'batch': batch, 'host': 'codex',
                    'host_tool': 'collaboration.spawn_agent', 'host_call_id': None,
                    'dispatch_id': expected_dispatch_id(envelope),
                    'action_id': expected_dispatch_id(envelope),
                    'agent_id': agent_id, 'status': 'RUNNING', 'task_digest': envelope_digest(envelope),
                    'sent_at': '2026-09-25T10:00:00Z', 'observed_at': '2026-09-25T10:00:01Z',
                    'result_uri': None, 'error': None,
                    'tool_result_uri': host_uri+host_sha+'.json',
                    'tool_result_sha256': host_sha}
        runtime.write('runtime/v6/events.json', [
            {'op': 'create_task', 'payload': envelope},
            {'op': 'transition', 'payload': {'event': {'task_id': task_id, 'batch': batch,
                'reason': 'DISPATCH_CONFIRMED'}, 'receipt': dispatch}},
            {'op': 'transition', 'payload': {'event': {
                'task_id': task_id, 'batch': batch, 'to_state': 'FAILED',
                'reason': 'VALIDATION_FAILED', 'evidence': [failure_uri],
                'check_results': [{'id': 'compile_semantics', 'status': 'FAIL',
                                   'evidence': [failure_uri]}]}}}])
        row = {'state': 'FAILED', 'envelope': envelope}
        route = runtime._verified_compile_semantic_failure(row)
        self.assertEqual(route['record']['failure_owner_node'], 'compile')
        self.assertEqual(route['record']['build_id'], build_id)
        from ai_comic_drama_workflow.v6_protocol import V6ProtocolError, validate_v6_protocol
        with self.assertRaises(V6ProtocolError):
            validate_v6_protocol('compile-semantic-failure',
                                 {**route['record'], 'unchecked': True})

    def test_control_candidate_binds_config_current_avir_and_locked_verifier(self):
        runtime = self.fresh()
        task_id = 'CONTROL_PREFLIGHT'
        prefix = f'runtime/v6/candidates/{task_id}/1/'
        runtime.write(f'runtime/tasks/{task_id}.json', {
            'task_id': task_id, 'context_fingerprint': 'f' * 64,
            'kind': 'control', 'slot': 'control', 'dependencies': [],
        })
        manifest_uri = prefix+'control-pack/package-manifest.json'
        config_uri = prefix+'control-config.json'
        runtime.write(manifest_uri, {'schema': 'test-only'})
        runtime.write(prefix+'control-pack/control-config.json', {'schema': 'test-only'})
        runtime.write(config_uri, {'schema': 'test-only'})
        runtime.write(prefix+'control-pack/production-specification.json', {'schema': 'avir/1.2'})
        runtime.write(prefix+'control-pack/review/frames.json',
                      [{'camera': {'status': 'PLANNED_PROJECTION'}}])
        result_uri = prefix+'role-result.json'
        runtime.write(result_uri, {
            'schema': 'role-result/5.1', 'task_id': task_id,
            'context_fingerprint': 'f' * 64, 'checks': ['synthetic'],
            'conflicts': [], 'unresolved': [], 'config': str(runtime.path(config_uri)),
            'validator': {'status': 'VERIFIED'},
        })
        record = {'envelope': {'task_id': task_id, 'batch': 1}, 'candidate': {
            'result_uri': result_uri, 'result_sha256': digest_file(runtime.path(result_uri)),
            'artifacts': [{'kind': 'ShotControlPack', 'uri': manifest_uri,
                           'sha256': digest_file(runtime.path(manifest_uri))}],
            'unresolved': [],
        }}
        with (patch.object(runtime.v5, 'receipt_audit'),
              patch.object(runtime.v5, 'data', return_value={}),
              patch('ai_comic_drama_workflow.v6_runtime.storyboard_to_avir',
                    return_value=({'schema': 'avir/1.2'}, {'status': 'MAPPED',
                        'semantic_review': 'INHERITED_DETERMINISTICALLY'})),
              patch.object(runtime.kernel, '_verify_control_package',
                           return_value={'status': 'VERIFIED'}) as verify):
            runtime._validate_v5_candidate(record)
            verify.assert_called_once_with(manifest_uri)
            runtime.write(prefix+'control-pack/production-specification.json',
                          {'schema': 'avir/1.2', 'stale': True})
            with self.assertRaisesRegex(V6CheckFailure, 'differs from current') as raised:
                runtime._validate_v5_candidate(record)
            self.assertEqual(raised.exception.failed_check, 'control_verify')
            runtime.write(prefix+'control-pack/production-specification.json', {'schema': 'avir/1.2'})
            runtime.write(prefix+'control-pack/review/frames.json',
                          [{'camera': {'status': 'UNDETERMINED'}}])
            with self.assertRaisesRegex(V6CheckFailure, 'undetermined camera'):
                runtime._validate_v5_candidate(record)

    def test_director_screenplay_handoff_is_checked_before_independent_review(self):
        runtime = self.fresh()
        task_id = 'DIRECTOR_PREFLIGHT'
        runtime.write(f'runtime/tasks/{task_id}.json', {
            'task_id': task_id, 'context_fingerprint': 'f' * 64,
            'kind': 'director', 'slot': 'director', 'dependencies': [],
        })
        prefix = f'runtime/v6/candidates/{task_id}/1/'
        artifact_uri = prefix+'DirectorIR.json'
        runtime.write(artifact_uri, {'project_id': runtime.project['project_id']})
        artifact = runtime.path(artifact_uri)
        result_uri = prefix+'role-result.json'
        runtime.write(result_uri, {
            'schema': 'role-result/5.0', 'task_id': task_id,
            'context_fingerprint': 'f' * 64, 'checks': ['synthetic'],
            'conflicts': [], 'unresolved': [], 'artifact': str(artifact),
            'artifact_sha256': digest_file(artifact),
            'handoff': [{'review': {'stamp': 'A'}}, {'review': {'stamp': 'B'}}],
        })
        record = {'envelope': {'task_id': task_id}, 'candidate': {
            'result_uri': result_uri, 'result_sha256': digest_file(runtime.path(result_uri)),
            'artifacts': [{'uri': artifact_uri, 'sha256': digest_file(artifact)}],
            'unresolved': [],
        }}
        with (patch.object(runtime.v5, 'receipt_audit'),
              patch.object(runtime.v5, 'check_content'),
              patch.object(runtime.v5, 'check_validator'),
              patch.object(runtime.v5, 'screenplay_protocol', return_value=object()),
              patch.object(runtime.v5, 'valid', return_value=True),
              patch.object(runtime.v5, 'data', return_value={}),
              patch.object(runtime.v5, 'handoff_inputs', return_value=[])):
            with self.assertRaisesRegex(ValueError, 'Inconsistent screenplay review binding') as raised:
                runtime._validate_v5_candidate(record)
            self.assertEqual(raised.exception.failed_check, 'handoff')

    def test_validator_status_mismatch_has_native_check_owner(self):
        runtime = self.fresh()
        task_id = 'STORYBOARD_PREFLIGHT'
        runtime.write(f'runtime/tasks/{task_id}.json', {
            'task_id': task_id, 'context_fingerprint': 'f' * 64,
            'kind': 'storyboard', 'slot': 'storyboard', 'dependencies': [],
        })
        prefix = f'runtime/v6/candidates/{task_id}/1/'
        artifact_uri = prefix+'StoryboardIR.json'
        runtime.write(artifact_uri, {'project_id': runtime.project['project_id']})
        artifact = runtime.path(artifact_uri)
        result_uri = prefix+'role-result.json'
        runtime.write(result_uri, {
            'schema': 'role-result/5.0', 'task_id': task_id,
            'context_fingerprint': 'f' * 64, 'checks': ['synthetic'],
            'conflicts': [], 'unresolved': [], 'artifact': str(artifact),
            'artifact_sha256': digest_file(artifact), 'validator': {'status': 'STATIC_VALID'},
        })
        record = {'envelope': {'task_id': task_id}, 'candidate': {
            'result_uri': result_uri, 'result_sha256': digest_file(runtime.path(result_uri)),
            'artifacts': [{'uri': artifact_uri, 'sha256': digest_file(artifact)}],
            'unresolved': [],
        }}
        with (patch.object(runtime.v5, 'receipt_audit'),
              patch.object(runtime.v5, 'check_content'),
              patch.object(runtime.v5, 'check_validator',
                           side_effect=ValueError('Validator summary does not match a fresh run'))):
            with self.assertRaisesRegex(ValueError, 'Validator summary does not match') as raised:
                runtime._validate_v5_candidate(record)
            self.assertEqual(raised.exception.failed_check, 'native_validator')

    def test_repeated_specialist_failure_creates_evidence_bound_repair_batch(self):
        runtime = self.fresh()
        action = runtime.run()['actions'][0]
        task_id = action['task_id']
        for batch in (1, 2):
            self.assertEqual(action['batch'], batch)
            receipt = receipt_from_spawn_result(
                action, {'task_name': '/root/'+action['task_name']},
                project_root=runtime.root, sent_at='2026-09-25T10:00:00Z',
                observed_at='2026-09-25T10:00:01Z',
                host_call_id=f'repair-dispatch-{batch}')
            runtime.agent_event(receipt, command_id=f'repair-dispatch-{batch}',
                                expected_revision=runtime.kernel.snapshot()['revision'])
            result = runtime.agent_result(
                {'task_id': task_id, 'result_uri': None, 'agent_id': receipt['agent_id']},
                command_id=f'repair-result-{batch}',
                expected_revision=runtime.kernel.snapshot()['revision'])
            action = result['actions'][0]
        self.assertEqual(action['batch'], 3)
        current = self.rows(runtime)['canon']
        self.assertEqual(current['state'], 'DISPATCHING')
        self.assertEqual(current['failure_counts']['source_integrity'], 2)
        slots = {item['slot']: item for item in current['envelope']['inputs']}
        self.assertIn('repair_brief', slots)
        self.assertIn('repair_failure_1', slots)
        self.assertIn('repair_failure_2', slots)
        brief = read(runtime.path(slots['repair_brief']['uri']))
        self.assertEqual([item['batch'] for item in brief['failures']], [1, 2])
        self.assertEqual(brief['failed_check'], 'source_integrity')
        self.assertEqual(runtime.run()['actions'][0]['dispatch_id'], action['dispatch_id'])

    def test_check_failure_records_the_actual_failing_validator(self):
        runtime = self.fresh()
        action = runtime.run()['actions'][0]
        receipt = receipt_from_spawn_result(
            action, {'task_name': '/root/'+action['task_name']},
            project_root=runtime.root, sent_at='2026-09-25T10:00:00Z',
            observed_at='2026-09-25T10:00:01Z', host_call_id='check-owner')
        runtime.agent_event(receipt, command_id='check-owner-dispatch',
                            expected_revision=runtime.kernel.snapshot()['revision'])
        runtime._record_failure(action['task_id'],
            V6CheckFailure('canon_contract', 'NATIVE_CONTENT_INVALID',
                           ValueError('Canon contract failed')),
            command_id='check-owner-result', reason='VALIDATION_FAILED')
        row = self.rows(runtime)['canon']
        self.assertEqual(row['failure_counts'], {'canon_contract': 1})
        failures = [item['payload']['event'] for item in read(runtime.path('runtime/v6/events.json'))
                    if item['op'] == 'transition' and item['payload']['event']['to_state'] == 'FAILED']
        self.assertEqual(failures[-1]['error']['failed_check'], 'canon_contract')


if __name__ == '__main__':
    unittest.main()
