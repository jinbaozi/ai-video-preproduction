"""Lean orchestration is not independent review or real model execution."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ai_comic_drama_workflow import transactions as tx
from ai_comic_drama_workflow.lean import compact, start, step
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_cli import main
from ai_comic_drama_workflow import v5_modules as modules
from ai_comic_drama_workflow.v5_protocol import validate_protocol


class LeanEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'

    def test_start_keeps_full_delivery_and_native_current_agent(self):
        response = start(self.root, ['成年旅人拾起遗失的信封。'], target='agnes-video-2.5')
        config = modules.read(self.root / 'project.json')
        self.assertEqual(config['workflow_profile'], 'lean')
        self.assertEqual(config['execution_mode'], 'current-agent')
        self.assertEqual(config['delivery'], 'full')
        self.assertNotIn('orchestration_protocol', config)
        self.assertEqual(response['review_policy'], 'current-agent-native-checks')
        self.assertTrue(Path(response['task_file']).is_file())
        task = modules.read(Path(response['task_file']))
        self.assertIn('handoff', task)
        self.assertNotIn('handoff', response['task'])
        self.assertEqual(step(self.root)['task_file'], response['task_file'])

    def test_cli_new_entry_leaves_old_init_default_codex(self):
        with patch('ai_comic_drama_workflow.v6_runtime.V6Runtime.initialize') as initialize:
            initialize.return_value.run.return_value = {'status': 'RUNNING'}
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['init', 'idea', '--project', str(self.root)]), 0)
            initialize.assert_called_once()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['start', 'idea', '--project', str(self.root), '--delivery', 'text-only']), 0)
        self.assertEqual(json.loads(output.getvalue())['workflow_profile'], 'lean')

    def test_audited_start_uses_v6_without_lean_native_flag(self):
        with patch('ai_comic_drama_workflow.v6_runtime.V6Runtime.initialize') as initialize:
            initialize.return_value.run.return_value = {'status': 'RUNNING'}
            value = start(self.root, ['idea'], profile='audited')
            self.assertEqual(value['review_policy'], 'independent-per-stage')
            self.assertNotIn('workflow_profile', initialize.call_args.kwargs)

    def test_v6_cannot_use_step_to_submit_native_result(self):
        self.root.mkdir()
        (self.root / 'project.json').write_text(json.dumps({'orchestration_protocol': '6.0'}))
        with self.assertRaisesRegex(ValueError, 'independent'):
            step(self.root, result='ignored.json')

    def test_lean_schema_cannot_be_marked_codex(self):
        start(self.root, ['idea'])
        config = modules.read(self.root / 'project.json')
        config.update(execution_mode='codex-agents', orchestration_protocol='6.0')
        with self.assertRaises(ValueError):
            validate_protocol('project', config, modules.ROOT)

    def test_blocker_and_only_task_copy_not_hidden(self):
        blocker = {'status': 'BLOCKED', 'decision': {'question': 'Which authorized target?'}, 'unresolved': ['identity']}
        self.assertEqual(compact(blocker), blocker)
        task_only = {'task': {'task_id': 'A', 'handoff': ['must preserve']}}
        self.assertEqual(compact(task_only), task_only)
        start(self.root, ['idea'])
        with patch.object(V5Kernel, 'submit', return_value=blocker), patch.object(V5Kernel, 'run') as run:
            self.assertEqual(step(self.root, result='native.json'), blocker)
            run.assert_not_called()

    def test_accept_then_run_and_video_not_faked(self):
        start(self.root, ['idea'], production_target='video')
        receipt = {'status': 'ACCEPTED', 'task_id': 'A'}
        with patch.object(V5Kernel, 'submit', return_value=receipt), patch.object(V5Kernel, 'run', return_value={'status': 'DELIVERED'}):
            value = step(self.root, result='native.json')
        self.assertEqual(value['receipt'], receipt)
        self.assertTrue(value['preproduction_complete'])
        self.assertFalse(value['video_complete'])
        self.assertIn('No video', value['next_action'])

    def test_identical_write_does_not_create_backups_or_fsync(self):
        kernel = V5Kernel(self.root)
        kernel.write('test.json', {'same': True})
        with patch('ai_comic_drama_workflow.v5.before_write') as before, patch('ai_comic_drama_workflow.v5.atomic_write') as write:
            kernel.write('test.json', {'same': True})
            before.assert_not_called()
            write.assert_not_called()


class ByteCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.name = 'screenplay-grammar'
        self.item = modules.default_lock(modules.ROOT)['modules'][self.name]
        self.archive = self.root / 'module.skill'
        shutil.copyfile(modules.ROOT/'assets/bundled-skills'/(self.name+'.skill'), self.archive)
        modules._verified_module_bytes.cache_clear()

    def test_cache_hit_is_tied_to_actual_archive_bytes(self):
        first = modules.verify_module(self.archive, self.name, self.item)
        second = modules.verify_module(self.archive, self.name, self.item)
        self.assertEqual(first, second)
        self.assertEqual(modules._verified_module_bytes.cache_info().hits, 1)
        first.clear()
        self.assertTrue(modules.verify_module(self.archive, self.name, self.item))
        stat = self.archive.stat()
        data = bytearray(self.archive.read_bytes());data[-1] ^= 1
        self.archive.write_bytes(data)
        os.utime(self.archive, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.assertRaises(ValueError):
            modules.verify_module(self.archive, self.name, self.item)

    def test_wrong_version_is_not_hidden_by_cache(self):
        modules.verify_module(self.archive, self.name, self.item)
        with self.assertRaises(ValueError):
            modules.verify_module(self.archive, self.name, {**self.item, 'version': '999.0'})

    def test_extracted_file_tamper_still_rejected(self):
        kernel = V5Kernel.initialize(self.root/'project', ['idea'], workflow_profile='lean')
        folder = kernel.modules(self.name)
        skill = folder/'SKILL.md';stat = skill.stat()
        data = bytearray(skill.read_bytes());data[-1] ^= 1
        skill.write_bytes(data);os.utime(skill, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.assertRaises(ValueError):
            kernel.modules(self.name)


class TransactionRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.target = self.root/'value.txt';self.target.write_text('original')

    def change(self, value):
        tx.before_write(self.root, self.target)
        self.target.write_text(value)

    def backups(self):
        return list((self.root/'runtime/transactions').rglob('*.backup'))

    def test_commit_cleans_backups(self):
        with tx.transaction(self.root):self.change('new')
        self.assertEqual(self.target.read_text(), 'new')
        self.assertEqual(self.backups(), [])

    def test_rollback_cleans_only_after_restore(self):
        with self.assertRaisesRegex(ValueError, 'planned'):
            with tx.transaction(self.root):
                self.change('new');raise ValueError('planned')
        self.assertEqual(self.target.read_text(), 'original')
        self.assertEqual(self.backups(), [])

    def test_failed_restore_keeps_journal_and_backups_for_recovery(self):
        with patch.object(tx, '_restore', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                with tx.transaction(self.root):
                    self.change('new');raise ValueError('planned')
        self.assertTrue(self.backups())
        self.assertTrue(list((self.root/'runtime/transactions').glob('*.pending.json')))
        with tx.transaction(self.root):pass
        self.assertEqual(self.target.read_text(), 'original')
        self.assertEqual(self.backups(), [])

    def test_nested_commit_cannot_erase_parent_rollback(self):
        with self.assertRaises(ValueError):
            with tx.transaction(self.root):
                self.change('parent')
                with tx.transaction(self.root, savepoint=True):self.change('child')
                self.assertTrue(self.backups())
                raise ValueError('rollback parent')
        self.assertEqual(self.target.read_text(), 'original')
        self.assertEqual(self.backups(), [])

    def test_cleanup_failure_does_not_trigger_duplicate_retry(self):
        with patch.object(tx.shutil, 'rmtree', side_effect=OSError('cleanup unavailable')):
            with tx.transaction(self.root):self.change('committed')
        self.assertEqual(self.target.read_text(), 'committed')
        self.assertTrue(self.backups())
        self.assertFalse(list((self.root/'runtime/transactions').glob('*.pending.json')))


if __name__ == '__main__':unittest.main()
