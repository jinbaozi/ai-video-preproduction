"""Focused regressions against byte-verified upstream modules, not the full suite."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from ai_comic_drama_workflow import acceptance as ac
from ai_comic_drama_workflow import transactions as tx
from ai_comic_drama_workflow import utils


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / 'project.json'
        self.target.write_bytes(b'before')

    def write(self, data=b'after', path=None):
        path = self.target if path is None else path
        tx.before_write(self.root, path)
        utils.atomic_write(path, data)

    def pending(self):
        return list((self.root / 'runtime/transactions').glob('*.pending.json'))

    def journal(self, **changes):
        identifier = 'a' * 32
        value = {'id': identifier, 'created_ns': 1, 'entries': [],
                 'pending_path': f'runtime/transactions/{identifier}.pending.json'}
        value.update(changes)
        path = self.root / f'runtime/transactions/{identifier}.pending.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path, value

    def test_success_commits(self):
        with tx.transaction(self.root):
            self.write()
        self.assertEqual(self.target.read_bytes(), b'after')
        self.assertEqual(self.pending(), [])

    def test_ordinary_failure_restores(self):
        with self.assertRaises(RuntimeError):
            with tx.transaction(self.root):
                self.write()
                raise RuntimeError('operation failure')
        self.assertEqual(self.target.read_bytes(), b'before')
        self.assertEqual(self.pending(), [])

    def test_base_exception_restores(self):
        with self.assertRaises(KeyboardInterrupt):
            with tx.transaction(self.root):
                self.write()
                raise KeyboardInterrupt()
        self.assertEqual(self.target.read_bytes(), b'before')

    def test_noop_transaction(self):
        with tx.transaction(self.root):
            pass
        self.assertEqual(self.pending(), [])

    def test_new_file_removed_on_failure(self):
        target = self.root / 'new' / 'candidate.json'
        with self.assertRaises(RuntimeError):
            with tx.transaction(self.root):
                self.write(b'new', target)
                raise RuntimeError('failure')
        self.assertFalse(target.exists())

    def test_failure_before_new_parent_created(self):
        with self.assertRaisesRegex(RuntimeError, 'before mkdir'):
            with tx.transaction(self.root):
                tx.before_write(self.root, self.root / 'absent' / 'new.json')
                raise RuntimeError('before mkdir')
        self.assertEqual(self.pending(), [])

    def test_repeated_write_uses_original_backup(self):
        with self.assertRaises(RuntimeError):
            with tx.transaction(self.root):
                self.write(b'one')
                self.write(b'two')
                raise RuntimeError('failure')
        self.assertEqual(self.target.read_bytes(), b'before')

    def test_restore_io_failure_retains_journal_then_recovers(self):
        with self.assertRaises(OSError):
            with patch.object(tx, '_restore', side_effect=OSError('injected restore I/O failure')):
                with tx.transaction(self.root):
                    self.write()
                    raise RuntimeError('operation failure')
        self.assertEqual(len(self.pending()), 1, 'failed rollback discarded recovery evidence')
        with tx.transaction(self.root):
            pass
        self.assertEqual(self.target.read_bytes(), b'before')
        self.assertEqual(self.pending(), [])

    def test_cleanup_spoof_cannot_delete_project(self):
        path, _ = self.journal(pending_path='project.json')
        with self.assertRaises(ValueError):
            with tx.transaction(self.root):
                pass
        self.assertTrue(self.target.exists())
        self.assertTrue(path.exists())

    def test_journal_filename_bound_to_identity(self):
        path, value = self.journal()
        other = path.with_name('b' * 32 + '.pending.json')
        path.rename(other)
        with self.assertRaises(ValueError):
            with tx.transaction(self.root):
                pass
        self.assertTrue(other.exists())

    def test_legacy_pending_journal_recovers(self):
        backup = self.root / ('runtime/transactions/' + 'a' * 32 + '/0.backup')
        backup.parent.mkdir(parents=True)
        backup.write_bytes(b'original')
        self.journal(entries=[{'path': 'project.json', 'backup': str(backup.relative_to(self.root))}])
        with tx.transaction(self.root):
            pass
        self.assertEqual(self.target.read_bytes(), b'original')

    def test_cross_transaction_backup_rejected(self):
        backup = self.root / ('runtime/transactions/' + 'b' * 32 + '/0.backup')
        backup.parent.mkdir(parents=True)
        backup.write_bytes(b'wrong transaction')
        self.journal(entries=[{'path': 'project.json', 'backup': str(backup.relative_to(self.root))}])
        with self.assertRaises(ValueError):
            with tx.transaction(self.root):
                pass
        self.assertEqual(self.target.read_bytes(), b'before')

    def test_entire_write_set_validated_before_restore(self):
        path, _ = self.journal(entries=[
            {'path': '../escape', 'backup': None},
            {'path': 'project.json', 'backup': None}])
        with self.assertRaises(ValueError):
            with tx.transaction(self.root):
                pass
        self.assertEqual(self.target.read_bytes(), b'before')
        self.assertTrue(path.exists())

    def test_missing_backup_prevents_other_target_deletion(self):
        missing = 'runtime/transactions/' + 'a' * 32 + '/0.backup'
        self.journal(entries=[{'path': 'another.json', 'backup': missing},
                              {'path': 'project.json', 'backup': None}])
        with self.assertRaises((ValueError, OSError)):
            with tx.transaction(self.root):
                pass
        self.assertEqual(self.target.read_bytes(), b'before')

    def test_symlink_journal_directory_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / 'runtime').mkdir()
            (self.root / 'runtime/transactions').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                with tx.transaction(self.root):
                    self.write()
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_nested_savepoint_rolls_back_only_child(self):
        with tx.transaction(self.root):
            self.write(b'parent')
            with self.assertRaises(RuntimeError):
                with tx.transaction(self.root, savepoint=True):
                    self.write(b'child')
                    raise RuntimeError('child failure')
            self.assertEqual(self.target.read_bytes(), b'parent')
        self.assertEqual(self.target.read_bytes(), b'parent')

    def test_parent_failure_after_successful_child(self):
        with self.assertRaises(RuntimeError):
            with tx.transaction(self.root):
                self.write(b'parent')
                with tx.transaction(self.root, savepoint=True):
                    self.write(b'child')
                raise RuntimeError('parent failure')
        self.assertEqual(self.target.read_bytes(), b'before')

    def test_failed_child_recovery_prevents_parent_commit(self):
        with self.assertRaises(ValueError):
            with tx.transaction(self.root):
                self.write(b'parent')
                try:
                    with patch.object(tx, '_restore', side_effect=OSError('restore failure')):
                        with tx.transaction(self.root, savepoint=True):
                            self.write(b'child')
                            raise RuntimeError('child failure')
                except OSError:
                    pass
        self.assertEqual(len(self.pending()), 2)
        with tx.transaction(self.root):
            pass
        self.assertEqual(self.target.read_bytes(), b'before')

    def test_caught_child_failure_blocks_further_writes(self):
        with self.assertRaises(ValueError):
            with tx.transaction(self.root):
                self.write(b'parent')
                try:
                    with patch.object(tx, '_restore', side_effect=OSError('restore failure')):
                        with tx.transaction(self.root, savepoint=True):
                            self.write(b'child')
                            raise RuntimeError('child failure')
                except OSError:
                    pass
                with self.assertRaises(ValueError):
                    self.write(b'must not commit')

    def test_caught_journal_write_failure_prevents_unlogged_commit(self):
        original = tx.atomic_write
        def fail_journal(path, data):
            if str(path).endswith('.pending.json'):
                raise OSError('journal unavailable')
            return original(path, data)
        with self.assertRaises(ValueError):
            with tx.transaction(self.root):
                try:
                    with patch.object(tx, 'atomic_write', side_effect=fail_journal):
                        self.write(b'first')
                except OSError:
                    pass
                with self.assertRaises(ValueError):
                    self.write(b'unlogged')
        self.assertEqual(self.target.read_bytes(), b'before')

    def test_cleanup_failure_releases_lock_and_retains_recovery(self):
        if not hasattr(tx, '_unlink_durable'):
            self.skipTest('New durable cleanup helper: baseline has no matching hook')
        with self.assertRaises(PermissionError):
            with patch.object(tx, '_unlink_durable', side_effect=PermissionError('cleanup denied')):
                with tx.transaction(self.root):
                    self.write()
        self.assertEqual(len(self.pending()), 1)
        with tx.transaction(self.root):
            pass
        self.assertEqual(self.target.read_bytes(), b'before')

    def test_process_death_recovers(self):
        code = '''import os,sys
from pathlib import Path
from ai_comic_drama_workflow.transactions import transaction,before_write
from ai_comic_drama_workflow.utils import atomic_write
root=Path(sys.argv[1]);target=root/'project.json'
with transaction(root):
 before_write(root,target);atomic_write(target,b'uncommitted');os._exit(23)
'''
        result = subprocess.run([sys.executable, '-c', code, str(self.root)], timeout=10)
        self.assertEqual(result.returncode, 23)
        self.assertEqual(len(self.pending()), 1)
        with tx.transaction(self.root):
            pass
        self.assertEqual(self.target.read_bytes(), b'before')

    def test_nested_process_death_recovers_in_reverse_order(self):
        code = '''import os,sys
from pathlib import Path
from ai_comic_drama_workflow.transactions import transaction,before_write
from ai_comic_drama_workflow.utils import atomic_write
root=Path(sys.argv[1]);target=root/'project.json'
with transaction(root):
 before_write(root,target);atomic_write(target,b'parent')
 with transaction(root,savepoint=True):
  before_write(root,target);atomic_write(target,b'child');os._exit(24)
'''
        result = subprocess.run([sys.executable, '-c', code, str(self.root)], timeout=10)
        self.assertEqual(result.returncode, 24)
        with tx.transaction(self.root):
            pass
        self.assertEqual(self.target.read_bytes(), b'before')

    def test_nested_clock_regression_does_not_reverse_recovery_order(self):
        with tx.transaction(self.root):
            parent = tx._active[str(self.root)][-1]
            with patch.object(tx.time, 'time_ns', return_value=1):
                with tx.transaction(self.root, savepoint=True):
                    child = tx._active[str(self.root)][-1]
                    self.assertGreater(child['created_ns'], parent['created_ns'])

    def test_thread_writers_do_not_lose_updates(self):
        self.target.write_text('0')
        def increment(_):
            for i in range(5):
                with tx.transaction(self.root):
                    self.write(str(int(self.target.read_text()) + 1).encode())
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(increment, range(4)))
        self.assertEqual(self.target.read_text(), '20')

    def test_process_writers_do_not_lose_updates(self):
        self.target.write_text('0')
        code = '''import sys
from pathlib import Path
from ai_comic_drama_workflow.transactions import transaction,before_write
from ai_comic_drama_workflow.utils import atomic_write
root=Path(sys.argv[1]);target=root/'project.json'
for _ in range(5):
 with transaction(root):
  value=int(target.read_text())+1;before_write(root,target);atomic_write(target,str(value).encode())
'''
        workers = [subprocess.Popen([sys.executable, '-c', code, str(self.root)]) for _ in range(3)]
        for worker in workers:
            self.assertEqual(worker.wait(timeout=10), 0)
        self.assertEqual(self.target.read_text(), '15')


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.plan = ac.freeze_plan([{'id': 'focus', 'level': 'hard', 'shot_ids': ['S1'],
                                    'acceptance': 'A then B sharp, no accidental cut', 'checks': []}])
        self.hash = self.plan['sha256']

    def test_empty_plan_cannot_pass(self):
        plan = {'schema': 'acceptance-plan/1.0', 'items': [], 'sha256': ac._sha([])}
        with self.assertRaises(ValueError):
            ac.decide(plan, [], frozen_sha256=plan['sha256'])

    def test_missing_observation_is_incomplete(self):
        self.assertEqual(ac.decide(self.plan, [], frozen_sha256=self.hash)['status'], 'INCOMPLETE')

    def test_hard_failure_is_fail(self):
        self.assertEqual(ac.decide(self.plan, [{'id': 'focus', 'result': 'FAIL'}], frozen_sha256=self.hash)['status'], 'FAIL')

    def test_observation_is_not_media_certification(self):
        result = ac.decide(self.plan, [{'id': 'focus', 'result': 'PASS', 'evidence': 'human review'}], frozen_sha256=self.hash)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['observation_status'], 'OBSERVATIONS_RECORDED')

    def test_legacy_soft_failure_policy_preserved(self):
        plan = ac.freeze_plan([{'id': 'soft', 'level': 'soft'}])
        self.assertEqual(ac.decide(plan, [{'id': 'soft', 'result': 'FAIL'}], frozen_sha256=plan['sha256'])['status'], 'PASS')

    def test_malformed_observation_is_value_error(self):
        with self.assertRaises(ValueError):
            ac.decide(self.plan, ['not an object'], frozen_sha256=self.hash)

    def test_unhashable_observation_id_is_value_error(self):
        with self.assertRaises(ValueError):
            ac.decide(self.plan, [{'id': [], 'result': 'PASS'}], frozen_sha256=self.hash)

    def test_missing_observation_result_is_value_error(self):
        with self.assertRaises(ValueError):
            ac.decide(self.plan, [{'id': 'focus'}], frozen_sha256=self.hash)

    def test_duplicate_observations_rejected(self):
        row = {'id': 'focus', 'result': 'PASS'}
        with self.assertRaises(ValueError):
            ac.decide(self.plan, [row, row], frozen_sha256=self.hash)

    def test_outside_plan_rejected(self):
        with self.assertRaises(ValueError):
            ac.decide(self.plan, [{'id': 'other', 'result': 'PASS'}], frozen_sha256=self.hash)

    def test_changed_plan_hash_rejected(self):
        self.plan['items'][0]['hard'] = False
        with self.assertRaises(ValueError):
            ac.decide(self.plan, [], frozen_sha256=self.hash)

    def test_empty_shot_scope_cannot_pass(self):
        with self.assertRaises(ValueError):
            ac.shot_decision(self.plan, [], 'S2', self.hash)

    def test_invalid_shot_id_rejected(self):
        with self.assertRaises(ValueError):
            ac.shot_decision(self.plan, [], None, self.hash)

    def test_adjacent_requires_both_scopes(self):
        with self.assertRaises(ValueError):
            ac.adjacent_decision(self.plan, [{'id': 'focus', 'result': 'PASS'}], 'S1', 'S2', self.hash)

    def test_empty_sequence_is_blocked(self):
        self.assertTrue(ac.sequence_blocks([]))

    def test_empty_decision_is_blocked(self):
        self.assertTrue(ac.sequence_blocks([{'status': 'PASS', 'items': []}]))

    def test_malformed_decision_is_blocked(self):
        self.assertTrue(ac.sequence_blocks([None]))

    def test_valid_nonempty_sequence_still_allowed(self):
        self.assertEqual(ac.sequence_blocks([{'status': 'PASS', 'items': [{'result': 'PASS'}]}]), [])

    def test_unknown_sequence_is_blocked(self):
        self.assertTrue(ac.sequence_blocks([{'status': 'PASS', 'items': [{'result': 'UNDETERMINED'}]}]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
