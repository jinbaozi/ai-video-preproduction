"""White-box tests of exact source excerpts; not complete V6 kernel execution.

Repository mode reads methods from the real module via AST. Local mode uses the
pinned excerpts returned by GitHub. Receipt/schema/native-IR checks outside the
transition prefix are deliberately NOT simulated or reported as passed.
"""
import ast
import os
from pathlib import Path
import unittest

ROOT = Path(os.environ['AUDIT_ROOT'])
VARIANT = os.environ.get('AUDIT_VARIANT', 'optimized')
REPO = os.environ.get('AUDIT_REPOSITORY')

MAIN_PATH = {
    'PENDING': {'READY', 'ACCEPTED', 'NOT_APPLICABLE', 'BLOCKED', 'CANCELLED'},
    'READY': {'DISPATCHING', 'BLOCKED', 'STALE', 'CANCELLED'},
    'DISPATCHING': {'RUNNING', 'UNKNOWN', 'FAILED', 'STALE', 'CANCELLED'},
    'RUNNING': {'RESULT_SUBMITTED', 'UNKNOWN', 'FAILED', 'STALE', 'CANCELLED'},
    'RESULT_SUBMITTED': {'VALIDATING', 'FAILED', 'STALE', 'CANCELLED'},
    'VALIDATING': {'REVIEW_REQUIRED', 'ACCEPTED', 'FAILED', 'BLOCKED', 'STALE', 'CANCELLED'},
    'REVIEW_REQUIRED': {'ACCEPTED', 'FAILED', 'BLOCKED', 'STALE', 'CANCELLED'},
    'UNKNOWN': {'RUNNING', 'FAILED', 'CANCELLED'},
    'BLOCKED': {'READY', 'STALE', 'CANCELLED'},
    'FAILED': {'STALE', 'CANCELLED'}, 'ACCEPTED': {'STALE'},
    'NOT_APPLICABLE': {'STALE'}, 'STALE': {'CANCELLED'}, 'CANCELLED': set(),
}


def fail(code, message):
    raise ValueError(code + ': ' + message)


def load_excerpt_class():
    if REPO:
        path = Path(REPO) / 'ai-comic-drama-workflow/src/ai_comic_drama_workflow/v6_kernel.py'
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'V6TaskKernel')
        count = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_active_agent_counts')
        transition = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_transition')
        boundary = next(i for i,n in enumerate(transition.body) if isinstance(n, ast.If)
                        and ast.unparse(n.test) == "new == 'STALE'")
        transition.body = transition.body[:boundary]
        cls.body = [count, transition]
        ast_tree = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
        compiled = compile(ast_tree, str(path), 'exec')
    else:
        text = 'class V6TaskKernel:\n'
        for name in ('v6_active_agent_counts', 'v6_transition_prefix'):
            text += (ROOT / 'excerpts' / f'{name}.{VARIANT}.py').read_text() + '\n'
        compiled = compile(text, '<pinned-v6-source-excerpts>', 'exec')
    namespace = {'MAIN_PATH': MAIN_PATH, '_fail': fail}
    exec(compiled, namespace)
    cls = namespace['V6TaskKernel']
    cls._task = lambda self, state, task_id, batch=None: state['tasks'][task_id]
    return cls


Kernel = load_excerpt_class()


def item(state='RUNNING', kind='professional', review=False):
    return {'state': state, 'version': 1, 'envelope': {'node_id': 'test', 'execution_class': kind,
            'dependencies': []}, 'review_dispatch': {'agent_id': 'reviewer'} if review else None}


class KernelGuardTests(unittest.TestCase):
    def test_unknown_specialist_still_occupies_slot(self):
        self.assertEqual(Kernel._active_agent_counts({'tasks': {'a': item('UNKNOWN')}}), (1, 0))

    def test_unknown_reviewer_still_occupies_slot(self):
        self.assertEqual(Kernel._active_agent_counts({'tasks': {'a': item('UNKNOWN', 'review')}}), (0, 1))

    def test_running_and_dispatching_are_counted(self):
        self.assertEqual(Kernel._active_agent_counts({'tasks': {'a': item(), 'b': item('DISPATCHING')}}), (2, 0))

    def test_independent_review_dispatch_counted(self):
        self.assertEqual(Kernel._active_agent_counts({'tasks': {'a': item('REVIEW_REQUIRED', review=True)}}), (0, 1))

    def test_terminal_tasks_not_counted(self):
        tasks = {name: item(name) for name in ('FAILED', 'CANCELLED', 'ACCEPTED', 'NOT_APPLICABLE')}
        self.assertEqual(Kernel._active_agent_counts({'tasks': tasks}), (0, 0))

    def test_excluding_current_task(self):
        self.assertEqual(Kernel._active_agent_counts({'tasks': {'a': item('UNKNOWN')}}, excluding='a'), (0, 0))

    def call_prefix(self, old, new, dependency='STALE', **changes):
        target = item(old)
        target['envelope']['dependencies'] = [{'task_id': 'upstream'}]
        state = {'tasks': {'target': target, 'upstream': item(dependency)}}
        event = {'task_id': 'target', 'batch': 1, 'object_version': 1,
                 'from_state': old, 'to_state': new, 'error': None}
        event.update(changes)
        return Kernel()._transition(state, {}, event, None, None, None)

    def test_dispatch_rechecks_stale_dependency(self):
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_UNREADY'):
            self.call_prefix('READY', 'DISPATCHING')

    def test_candidate_gate_rechecks_stale_dependency(self):
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_UNREADY'):
            self.call_prefix('RUNNING', 'RESULT_SUBMITTED')

    def test_validation_gate_rechecks_stale_dependency(self):
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_UNREADY'):
            self.call_prefix('RESULT_SUBMITTED', 'VALIDATING')

    def test_review_gate_rechecks_stale_dependency(self):
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_UNREADY'):
            self.call_prefix('VALIDATING', 'REVIEW_REQUIRED')

    def test_acceptance_gate_rechecks_stale_dependency(self):
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_UNREADY'):
            self.call_prefix('REVIEW_REQUIRED', 'ACCEPTED')

    def test_blocked_unblock_rechecks_dependency(self):
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_UNREADY'):
            self.call_prefix('BLOCKED', 'READY')

    def test_accepted_dependency_passes_prefix_only(self):
        self.assertIsNone(self.call_prefix('READY', 'DISPATCHING', 'ACCEPTED'))

    def test_not_applicable_dependency_passes_prefix_only(self):
        self.assertIsNone(self.call_prefix('READY', 'DISPATCHING', 'NOT_APPLICABLE'))

    def test_reconciliation_not_blocked_by_stale_dependency_prefix(self):
        self.assertIsNone(self.call_prefix('UNKNOWN', 'RUNNING'))

    def test_illegal_transition_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ILLEGAL_TRANSITION'):
            self.call_prefix('UNKNOWN', 'READY')

    def test_stale_object_version_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'OBJECT_VERSION'):
            self.call_prefix('READY', 'DISPATCHING', object_version=0)

    def test_unknown_requires_reconciliation_error(self):
        with self.assertRaisesRegex(ValueError, 'ERROR_RECOVERY'):
            self.call_prefix('RUNNING', 'UNKNOWN', error={
                'owner_node': 'test', 'evidence': ['receipt.json'], 'recovery_action': 'RETRY'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
