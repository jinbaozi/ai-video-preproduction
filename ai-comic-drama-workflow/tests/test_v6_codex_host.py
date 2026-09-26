"""Codex host dispatch, communication and uncertain-result boundaries."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ai_comic_drama_workflow.v6_codex_host import (
    CodexHostBridge, pending_host_action, pending_review_action,
    receipt_from_spawn_result, unknown_spawn_receipt, reconcile_unknown,
    replay_registered_command,
    validate_agent_message, validate_dispatch_receipt,
    validate_review_dispatch_receipt,
)
from ai_comic_drama_workflow.v6_protocol import envelope_input_digest, sha256_json, validate_v6_protocol


NOW = '2026-09-25T10:00:00Z'


def envelope(execution_class='professional'):
    value = {'schema': 'task-envelope/6.0', 'project_id': 'PROJECT',
             'node_id': 'screenplay', 'task_id': 'Task1', 'batch': 1,
             'role': 'screenwriter', 'execution_class': execution_class,
             'scope': {'kind': 'project', 'ids': []}, 'input_revision': 1,
             'inputs': [], 'input_digest': '0' * 64, 'module': None,
             'resources': [],
             'expected_artifacts': [{'slot': 'screenplay', 'kind': 'screenplay',
                                     'uri_prefix': 'runtime/v6/candidates/Task1/1'}],
             'validators': [], 'dependencies': [], 'handoffs': [],
             'retry_authorization': None}
    value['input_digest'] = envelope_input_digest(value)
    return value


def task(value, state='DISPATCHING'):
    return {'envelope': value, 'state': state, 'version': 3,
            'receipt': None, 'candidate': None, 'review': None,
            'review_dispatch': None, 'messages': []}


def receipt(action, root, *, status='RUNNING'):
    if status == 'UNKNOWN':
        return unknown_spawn_receipt(action, sent_at=NOW, observed_at=NOW, host_call_id='call-1')
    return receipt_from_spawn_result(
        action, {'task_name': '/root/' + action['task_name']},
        project_root=root, sent_at=NOW, observed_at=NOW, host_call_id='call-1')


def message(action, *, kind='ACK', sender=None, reply=None):
    return {'schema': 'agent-message/6.0', 'message_id': 'Message1',
            'task_id': action['task_id'], 'batch': action['batch'],
            'sender_id': sender or '/root/' + action['task_name'],
            'recipient_id': 'kernel', 'in_reply_to': reply, 'type': kind,
            'summary': 'I read the frozen task', 'evidence': [],
            'subject_uri': None, 'subject_sha256': None, 'at': NOW}


class _Kernel:
    def __init__(self, root, value, record):
        self.root = Path(root)
        self.state = {'revision': 4, 'tasks': {value['task_id']: record}}
        self.events = []

    def snapshot(self):
        return deepcopy(self.state)

    def transition(self, event, **kwargs):
        self.events.append((deepcopy(event), deepcopy(kwargs)))
        current = self.state['tasks'][event['task_id']]
        current['state'] = event['to_state']
        current['version'] += 1
        if 'receipt' in kwargs:
            current['receipt'] = kwargs['receipt']
        self.state['revision'] += 1
        return {'status': event['to_state']}

    def register_review_dispatch(self, value, command_id, expected_revision, evidence=None):
        self.state['tasks'][value['task_id']]['review_dispatch'] = value
        self.state['revision'] += 1
        return {'status': 'REVIEW_DISPATCHED'}

    def record_message(self, value, command_id, expected_revision):
        self.state['tasks'][value['task_id']]['messages'].append(value)
        self.state['revision'] += 1
        return {'status': 'RECORDED'}


class CodexHostTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def _journal(self, command_id, op, payload, revision=5):
        base = self.root / 'runtime/v6'
        base.mkdir(parents=True, exist_ok=True)
        (base / 'commands.json').write_text(json.dumps({command_id: {
            'fingerprint': sha256_json({'op': op, 'payload': payload}),
            'revision': revision}}))
        (base / 'events.json').write_text(json.dumps([
            {'revision': index, 'op': 'fixture', 'payload': {}}
            for index in range(1, revision)
        ] + [{'revision': revision, 'op': op, 'payload': payload}]))

    def test_pending_action_is_stable_and_requires_actual_matching_receipt(self):
        value = envelope()
        record = task(value)
        first = pending_host_action(value, record, project_root=self.root)
        second = pending_host_action(value, record, project_root=self.root)
        self.assertEqual(first, second)
        self.assertEqual(first['tool'], 'collaboration.spawn_agent')
        self.assertEqual(first['preflight']['tool'], 'collaboration.list_agents')
        self.assertIn('candidate files under', first['arguments']['message'])
        self.assertIn('RoleResult.validator.status exactly', first['arguments']['message'])
        valid = receipt(first, self.root)
        validate_dispatch_receipt(value, valid, task=record, action=first, project_root=self.root)
        with self.assertRaises(ValueError):
            validate_dispatch_receipt(value, dict(valid, agent_id='/root/other'), task=record,
                                      action=first, project_root=self.root)
        with self.assertRaises(ValueError):
            validate_dispatch_receipt(value, dict(valid, task_digest='0' * 64), task=record,
                                      action=first, project_root=self.root)
        with self.assertRaises(ValueError):
            validate_dispatch_receipt(value, dict(valid, batch=2), task=record,
                                      action=first, project_root=self.root)
        with self.assertRaises(ValueError):
            validate_dispatch_receipt(value, dict(valid, tool_result_sha256='0' * 64), task=record,
                                      action=first, project_root=self.root)
        with self.assertRaises(ValueError):
            receipt_from_spawn_result(first, {'task_name': '/root/other'},
                                      project_root=self.root, sent_at=NOW, observed_at=NOW)

    def test_director_dispatch_names_both_handoff_contracts(self):
        value = envelope()
        value['node_id'] = 'director'
        value['input_digest'] = envelope_input_digest(value)
        action = pending_host_action(value, task(value), project_root=self.root)
        message = action['arguments']['message']
        self.assertIn('RoleResult.handoff', message)
        self.assertIn('candidate.handoffs', message)
        self.assertIn('screenplay review bindings', message)

    def test_graph_only_dispatch_does_not_request_a_native_role_result(self):
        for node_id in ('reference_observation', 'compile', 'shot_acceptance'):
            with self.subTest(node_id=node_id):
                value = envelope()
                value['node_id'] = node_id
                value['input_digest'] = envelope_input_digest(value)
                action = pending_host_action(value, task(value), project_root=self.root)
                prompt = action['arguments']['message']
                self.assertIn('no native V5 RoleResult', prompt)
                self.assertIn('candidate.result_uri and candidate.result_sha256 to null', prompt)
                self.assertNotIn('RoleResult.validator.status exactly', prompt)

    def test_native_dispatch_still_requires_fresh_role_result_validator(self):
        value = envelope()
        action = pending_host_action(value, task(value), project_root=self.root)
        self.assertIn('RoleResult.validator.status exactly', action['arguments']['message'])

    def test_repair_dispatch_requires_reading_every_input_and_prior_failures(self):
        value = envelope()
        value['batch'] = 3
        value['expected_artifacts'][0]['uri_prefix'] = 'runtime/v6/candidates/Task1/3/'
        value['inputs'] = [
            {'slot': slot, 'uri': 'runtime/v6/' + slot + '.json',
             'sha256': '1' * 64, 'version': 2}
            for slot in ('frozen_task', 'repair_brief', 'repair_failure_1', 'repair_failure_2')]
        value['input_digest'] = envelope_input_digest(value)
        action = pending_host_action(value, task(value), project_root=self.root)
        prompt = action['arguments']['message']
        self.assertIn('Read every item in envelope.inputs', prompt)
        self.assertIn('repair_brief', prompt)
        self.assertIn('repair_failure_1/2', prompt)
        self.assertIn('report whether each old defect is gone', prompt)

    def test_unknown_never_returns_spawn_and_reconciles_only_observed_agent(self):
        value = envelope()
        record = task(value)
        action = pending_host_action(value, record, project_root=self.root)
        old = receipt(action, self.root, status='UNKNOWN')
        record.update(state='UNKNOWN', receipt=old)
        pending = pending_host_action(value, record, project_root=self.root)
        self.assertEqual(pending['tool'], 'collaboration.list_agents')
        observation = {'schema': 'codex-agent-observation/1.0',
                       'source_tool': 'collaboration.list_agents',
                       'dispatch_id': action['dispatch_id'], 'observed_at': NOW,
                       'host_call_id': 'lookup-1',
                       'tool_result': {'agents': [{'agent_name': '/root/' + action['task_name'],
                                                   'agent_status': 'running'}]}}
        found = reconcile_unknown(value, record, observation)
        self.assertEqual(found['status'], 'FOUND')
        self.assertEqual(found['receipt']['host_tool'], 'collaboration.list_agents')
        self.assertEqual(found['receipt']['dispatch_id'], old['dispatch_id'])
        missing = deepcopy(observation)
        missing['tool_result'] = {'agents': []}
        self.assertEqual(reconcile_unknown(value, record, missing)['status'], 'UNRESOLVED')
        bad = deepcopy(observation)
        bad['dispatch_id'] = 'wrong'
        with self.assertRaises(ValueError):
            reconcile_unknown(value, record, bad)
        kernel = _Kernel(self.root, value, record)
        bridge = CodexHostBridge(kernel)
        self.assertEqual(bridge.reconcile(value['task_id'], observation, command_id='Command3',
                                          expected_revision=4)['status'], 'RUNNING')
        self.assertEqual(kernel.events[0][0]['reason'], 'HOST_RECONCILED')

    def test_messages_log_authentic_sender_without_advancing_task(self):
        value = envelope()
        record = task(value, 'RUNNING')
        action = pending_host_action(value, task(value), project_root=self.root)
        record['receipt'] = receipt(action, self.root)
        valid = message(action, kind='QUESTION')
        validate_agent_message(value, record, valid)
        with self.assertRaises(ValueError):
            validate_agent_message(value, record, message(action, sender='/root/other'))
        with self.assertRaises(ValueError):
            validate_agent_message(value, record, message(action, reply='unknown'))
        note_uri = 'runtime/v6/messages/host-note.json'
        note = self.root / note_uri
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text('{"frozen_task":"Task1"}')
        host_instruction = dict(valid, message_id='Instruction1', sender_id='kernel',
                                recipient_id=record['receipt']['agent_id'], type='PROGRESS',
                                subject_uri=note_uri,
                                subject_sha256=hashlib.sha256(note.read_bytes()).hexdigest())
        validate_agent_message(value, record, host_instruction, project_root=self.root)
        with self.assertRaises(ValueError):
            validate_agent_message(value, record, dict(host_instruction, type='RESULT'),
                                   project_root=self.root)
        with self.assertRaises(ValueError):
            validate_agent_message(value, record, dict(host_instruction, recipient_id='kernel'),
                                   project_root=self.root)
        kernel = _Kernel(self.root, value, record)
        result = CodexHostBridge(kernel).record_message(valid, command_id='Command1', expected_revision=4)
        self.assertEqual(result['status'], 'RECORDED')
        result = CodexHostBridge(kernel).record_message(host_instruction, command_id='Command2',
                                                        expected_revision=5)
        self.assertEqual(result['status'], 'RECORDED')
        self.assertEqual(kernel.state['tasks'][value['task_id']]['state'], 'RUNNING')

    def test_creator_can_report_after_submit_without_claiming_review_result(self):
        value = envelope()
        record = task(value, 'REVIEW_REQUIRED')
        action = pending_host_action(value, task(value), project_root=self.root)
        record['receipt'] = receipt(action, self.root)
        creator_note = message(action, kind='BLOCKER')
        validate_agent_message(value, record, creator_note)
        forged_result = dict(creator_note, type='RESULT',
                             subject_uri='runtime/v6/reviews/forged.json',
                             subject_sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'Only the dispatched reviewer'):
            validate_agent_message(value, record, forged_result)
        reviewer = '/root/reviewer'
        record['review_dispatch'] = {'agent_id': reviewer}
        validate_agent_message(value, record, dict(creator_note, type='QUESTION'))
        validate_agent_message(value, record, dict(creator_note, sender_id=reviewer,
                                                   message_id='ReviewerAck', type='ACK'))
        with self.assertRaisesRegex(ValueError, 'Only the dispatched reviewer'):
            validate_agent_message(value, record, forged_result)

    def test_result_message_binds_candidate_bytes_before_submission(self):
        value = envelope()
        record = task(value, 'RUNNING')
        action = pending_host_action(value, task(value), project_root=self.root)
        record['receipt'] = receipt(action, self.root)
        candidate = {'schema': 'candidate-result/6.0', 'task_id': value['task_id'],
                     'batch': value['batch'], 'agent_id': record['receipt']['agent_id'],
                     'input_digest': value['input_digest'], 'result_uri': None,
                     'result_sha256': None, 'artifacts': [], 'module_receipts': [],
                     'checks': [], 'handoffs': [], 'unresolved': []}
        uri = 'runtime/v6/candidates/Task1/1/candidate.json'
        path = self.root / uri
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(candidate, ensure_ascii=False).encode()
        path.write_bytes(raw)
        result_message = message(action, kind='RESULT')
        result_message.update(subject_uri=uri, subject_sha256=hashlib.sha256(raw).hexdigest())
        validate_agent_message(value, record, result_message, project_root=self.root)
        with self.assertRaises(ValueError):
            validate_agent_message(value, record, dict(result_message, subject_sha256='0' * 64),
                                   project_root=self.root)
        with self.assertRaises(ValueError):
            validate_agent_message(value, record, message(action, kind='RESULT'),
                                   project_root=self.root)
        record.update(state='REVIEW_REQUIRED', review_dispatch=receipt(
            pending_review_action(value, dict(record, state='REVIEW_REQUIRED', candidate=candidate),
                                  project_root=self.root), self.root))
        with self.assertRaises(ValueError):
            validate_agent_message(value, record, dict(result_message,
                sender_id=record['review_dispatch']['agent_id']), project_root=self.root)

    def test_review_spawn_requires_distinct_agent_and_candidate(self):
        value = envelope()
        creator_task = task(value)
        creator_action = pending_host_action(value, creator_task, project_root=self.root)
        creator_task.update(state='REVIEW_REQUIRED', candidate={'schema': 'candidate-result/6.0'},
                            receipt=receipt(creator_action, self.root))
        reviewer_action = pending_review_action(value, creator_task, project_root=self.root)
        self.assertNotEqual(reviewer_action['dispatch_id'], creator_action['dispatch_id'])
        reviewer_receipt = receipt(reviewer_action, self.root)
        validate_review_dispatch_receipt(value, creator_task, reviewer_receipt, action=reviewer_action,
                                         project_root=self.root)
        with self.assertRaises(ValueError):
            validate_review_dispatch_receipt(value, creator_task,
                                             dict(reviewer_receipt, agent_id=creator_task['receipt']['agent_id']),
                                             action=reviewer_action, project_root=self.root)
        kernel = _Kernel(self.root, value, creator_task)
        bridge = CodexHostBridge(kernel)
        self.assertEqual(bridge.pending(value['task_id'])['tool'], 'collaboration.spawn_agent')
        self.assertEqual(bridge.register_review_dispatch(reviewer_receipt, command_id='Command2',
                                                         expected_revision=4)['status'], 'REVIEW_DISPATCHED')
        self.assertIsNone(bridge.pending(value['task_id']))
        creator_task['candidate'] = None
        with self.assertRaises(ValueError):
            pending_review_action(value, creator_task, project_root=self.root)

    def test_reviewer_spawn_crash_is_reconciled_from_existing_agent(self):
        value = envelope()
        record = task(value)
        creator_action = pending_host_action(value, record, project_root=self.root)
        record.update(state='REVIEW_REQUIRED', candidate={'schema': 'candidate-result/6.0'},
                      receipt=receipt(creator_action, self.root))
        kernel = _Kernel(self.root, value, record)
        bridge = CodexHostBridge(kernel)
        review_action = bridge.pending(value['task_id'])
        observation = {'schema': 'codex-agent-observation/1.0',
                       'source_tool': 'collaboration.list_agents',
                       'dispatch_id': review_action['dispatch_id'],
                       'observed_at': NOW, 'host_call_id': 'lookup-review',
                       'tool_result': {'agents': [{'agent_name': '/root/' + review_action['task_name'],
                                                   'agent_status': 'running'}]}}
        self.assertEqual(bridge.reconcile(value['task_id'], observation, command_id='Command4',
                                          expected_revision=4)['status'], 'REVIEW_DISPATCHED')
        self.assertIsNone(bridge.pending(value['task_id']))

    def test_external_generation_is_not_dispatched_as_a_subagent(self):
        value = envelope('external_video')
        with self.assertRaises(ValueError):
            pending_host_action(value, task(value), project_root=self.root)

    def test_bridge_submits_host_event_with_revision_and_evidence(self):
        value = envelope()
        record = task(value)
        kernel = _Kernel(self.root, value, record)
        bridge = CodexHostBridge(kernel)
        action = bridge.pending(value['task_id'])
        host_receipt = receipt(action, self.root)
        result = bridge.register_dispatch(host_receipt, command_id='Command1', expected_revision=4)
        self.assertEqual(result['status'], 'RUNNING')
        event, attached = kernel.events[0]
        validate_v6_protocol('state-event', event)
        self.assertEqual(event['from_state'], 'DISPATCHING')
        self.assertEqual(event['to_state'], 'RUNNING')
        self.assertEqual(event['object_version'], 3)
        self.assertEqual(attached['receipt']['agent_id'], '/root/' + action['task_name'])
        with self.assertRaises(ValueError):
            bridge.register_dispatch(host_receipt, command_id='Command2', expected_revision=4)

    def test_failed_host_call_has_structured_error_and_no_fake_agent(self):
        value = envelope()
        record = task(value)
        kernel = _Kernel(self.root, value, record)
        bridge = CodexHostBridge(kernel)
        action = bridge.pending(value['task_id'])
        failed = unknown_spawn_receipt(action, sent_at=NOW, observed_at=NOW)
        failed['status'] = 'FAILED'
        failed['error'] = {'code': 'HOST_CALL_FAILED', 'message': 'Tool rejected dispatch',
                           'failed_check': 'host_call', 'evidence': ['host-call:1'],
                           'retryable': True, 'recovery_action': 'RETRY'}
        self.assertEqual(bridge.register_dispatch(failed, command_id='Command5',
                                                  expected_revision=4)['status'], 'FAILED')
        event, attached = kernel.events[0]
        validate_v6_protocol('state-event', event)
        self.assertEqual(event['error']['owner_node'], 'screenplay')
        self.assertEqual(event['check_results'][0]['status'], 'FAIL')
        self.assertEqual(attached, {})

    def test_uncertain_call_requires_reconciliation_and_keeps_original_dispatch(self):
        value = envelope()
        record = task(value)
        kernel = _Kernel(self.root, value, record)
        bridge = CodexHostBridge(kernel)
        action = bridge.pending(value['task_id'])
        uncertain = unknown_spawn_receipt(action, sent_at=NOW, observed_at=NOW,
                                          host_call_id='call-unknown')
        self.assertEqual(bridge.register_dispatch(uncertain, command_id='Command6',
                                                  expected_revision=4)['status'], 'UNKNOWN')
        event, attached = kernel.events[0]
        validate_v6_protocol('state-event', event)
        self.assertEqual(event['error']['recovery_action'], 'RECONCILE')
        self.assertEqual(event['check_results'][0]['status'], 'BLOCKED')
        self.assertIsNone(attached['receipt']['agent_id'])
        self.assertEqual(bridge.pending(value['task_id'])['tool'], 'collaboration.list_agents')

    def test_exact_dispatch_and_message_replay_does_not_repeat_state_changes(self):
        value = envelope()
        kernel = _Kernel(self.root, value, task(value))
        bridge = CodexHostBridge(kernel)
        host_receipt = receipt(bridge.pending(value['task_id']), self.root)
        bridge.register_dispatch(host_receipt, command_id='Dispatch1', expected_revision=4)
        event, attached = kernel.events[0]
        self._journal('Dispatch1', 'transition', {
            'event': event, 'receipt': attached['receipt'], 'candidate': None, 'review': None})
        replay = bridge.register_dispatch(host_receipt, command_id='Dispatch1', expected_revision=4)
        self.assertEqual(replay['status'], 'ALREADY_RECORDED')
        self.assertEqual(kernel.state['revision'], 5)
        with self.assertRaisesRegex(ValueError, 'COMMAND_COLLISION'):
            bridge.register_dispatch(dict(host_receipt, host_call_id='changed'),
                                     command_id='Dispatch1', expected_revision=4)
        with self.assertRaisesRegex(ValueError, 'COMMAND_COLLISION'):
            bridge.register_dispatch(host_receipt, command_id='Dispatch1', expected_revision=5)
        with self.assertRaisesRegex(ValueError, 'evidence is derived'):
            bridge.register_dispatch(host_receipt, command_id='Dispatch1', expected_revision=4,
                                     evidence=['changed'])

        valid = message(bridge.pending(value['task_id']) or {
            'task_id': value['task_id'], 'batch': value['batch'],
            'task_name': host_receipt['agent_id'].rsplit('/', 1)[-1]})
        bridge.record_message(valid, command_id='Message1', expected_revision=5)
        self._journal('Message1', 'agent_message', valid, revision=6)
        self.assertEqual(bridge.record_message(valid, command_id='Message1',
                                               expected_revision=5)['status'], 'ALREADY_RECORDED')
        with self.assertRaisesRegex(ValueError, 'COMMAND_COLLISION'):
            bridge.record_message(dict(valid, summary='changed'), command_id='Message1',
                                  expected_revision=5)

    def test_review_dispatch_and_reconcile_replay_bind_original_evidence(self):
        value = envelope()
        record = task(value)
        creator = receipt(pending_host_action(value, record, project_root=self.root), self.root)
        record.update(state='REVIEW_REQUIRED', candidate={'schema': 'candidate-result/6.0'},
                      receipt=creator)
        kernel = _Kernel(self.root, value, record)
        bridge = CodexHostBridge(kernel)
        reviewer = receipt(bridge.pending(value['task_id']), self.root)
        bridge.register_review_dispatch(reviewer, command_id='ReviewDispatch1', expected_revision=4)
        self._journal('ReviewDispatch1', 'review_dispatch', {'receipt': reviewer, 'evidence': []})
        self.assertEqual(bridge.register_review_dispatch(reviewer, command_id='ReviewDispatch1',
                                                         expected_revision=4)['status'], 'ALREADY_RECORDED')
        with self.assertRaisesRegex(ValueError, 'COMMAND_COLLISION'):
            bridge.register_review_dispatch(dict(reviewer, host_call_id='changed'),
                                            command_id='ReviewDispatch1', expected_revision=4)
        with self.assertRaisesRegex(ValueError, 'evidence is derived'):
            bridge.register_review_dispatch(reviewer, command_id='ReviewDispatch1',
                                            expected_revision=4, evidence=['changed'])

        uncertain = unknown_spawn_receipt(pending_host_action(value, task(value),
                                                               project_root=self.root),
                                          sent_at=NOW, observed_at=NOW)
        other = _Kernel(self.root, value, task(value, 'UNKNOWN'))
        other.state['tasks'][value['task_id']]['receipt'] = uncertain
        other_bridge = CodexHostBridge(other)
        observation = {'schema': 'codex-agent-observation/1.0',
                       'source_tool': 'collaboration.list_agents',
                       'dispatch_id': uncertain['dispatch_id'], 'observed_at': NOW,
                       'host_call_id': 'lookup-replay',
                       'tool_result': {'agents': [{'agent_name': '/root/' +
                           pending_host_action(value, task(value), project_root=self.root)['task_name'],
                           'agent_status': 'running'}]}}
        other_bridge.reconcile(value['task_id'], observation, command_id='Reconcile1',
                               expected_revision=4)
        event, attached = other.events[0]
        self._journal('Reconcile1', 'transition', {
            'event': event, 'receipt': attached['receipt'], 'candidate': None, 'review': None})
        self.assertEqual(other_bridge.reconcile(value['task_id'], observation,
                                                command_id='Reconcile1',
                                                expected_revision=4)['status'], 'ALREADY_RECORDED')
        with self.assertRaisesRegex(ValueError, 'COMMAND_COLLISION'):
            other_bridge.reconcile(value['task_id'], dict(observation, host_call_id='different'),
                                   command_id='Reconcile1', expected_revision=4)
        with self.assertRaisesRegex(ValueError, 'COMMAND_COLLISION'):
            other_bridge.reconcile(value['task_id'], observation,
                                   command_id='Reconcile1', expected_revision=5)

    def test_candidate_and_review_replay_match_full_business_payload(self):
        value = envelope()
        kernel = _Kernel(self.root, value, task(value))
        kernel.state['revision'] = 5
        candidate = {'schema': 'candidate-result/6.0', 'task_id': value['task_id']}
        review = {'schema': 'review-record/6.0', 'task_id': value['task_id']}
        self._journal('Candidate1', 'transition', {
            'event': {'command_id': 'Candidate1', 'to_state': 'RESULT_SUBMITTED'},
            'receipt': None, 'candidate': candidate, 'review': None})
        self.assertEqual(replay_registered_command(kernel, 'Candidate1', 4,
                         'agent-result', candidate)['status'], 'ALREADY_RECORDED')
        with self.assertRaisesRegex(ValueError, 'COMMAND_COLLISION'):
            replay_registered_command(kernel, 'Candidate1', 4, 'agent-result', dict(candidate, batch=2))
        self._journal('Review1', 'transition', {
            'event': {'command_id': 'Review1', 'to_state': 'ACCEPTED'},
            'receipt': None, 'candidate': None, 'review': review})
        self.assertEqual(replay_registered_command(kernel, 'Review1', 4,
                         'agent-review', review)['status'], 'ALREADY_RECORDED')


if __name__ == '__main__':
    unittest.main()
