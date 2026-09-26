"""Codex host boundary for V6 tasks.

This module describes host actions and checks their returned evidence.  It does
not invoke Codex collaboration tools: the active Codex host executes an action
and passes the actual tool result back to the V6 kernel.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .transactions import before_write, transaction
from .utils import atomic_write
from .v6_protocol import (compact_json, envelope_digest, expected_dispatch_id,
                          expected_review_dispatch_id, sha256_json,
                          validate_v6_protocol)


MESSAGE_TYPES = frozenset({'ACK', 'PROGRESS', 'QUESTION', 'BLOCKER', 'HANDOFF', 'RESULT', 'CANCEL_ACK'})
_DISPATCH_STATES = {'RUNNING': ('RUNNING', 'DISPATCH_CONFIRMED'),
                    'UNKNOWN': ('UNKNOWN', 'DISPATCH_UNCERTAIN'),
                    'FAILED': ('FAILED', 'HOST_FAILED')}


def _digest(value: Any) -> str:
    return sha256_json(value)


def _schema(name: str, value: dict) -> None:
    validate_v6_protocol(name, value)


def _task_envelope(envelope: dict, task: dict) -> None:
    _schema('task-envelope', envelope)
    if task.get('envelope') != envelope:
        raise ValueError('Task envelope differs from the frozen task record')
    if task.get('state') not in ('DISPATCHING', 'RUNNING', 'UNKNOWN', 'REVIEW_REQUIRED'):
        raise ValueError('Task is not in a host-dispatch state')


def _dispatch_id(envelope: dict, task: dict) -> str:
    receipt = task.get('receipt')
    if receipt:
        if receipt.get('task_id') != envelope['task_id'] or receipt.get('batch') != envelope['batch']:
            raise ValueError('Stored dispatch receipt belongs to another task or batch')
        return receipt['dispatch_id']
    if task['state'] not in ('DISPATCHING', 'UNKNOWN'):
        raise ValueError('No prior dispatch ID exists for this task')
    return expected_dispatch_id(envelope)


def _task_name(dispatch_id: str) -> str:
    return 'v6_' + _digest(dispatch_id)[:24]


def _spawn_agent_id(result: dict) -> str | None:
    """The live collaboration.spawn_agent tool returns ``task_name``."""
    if not isinstance(result, dict):
        return None
    names = [result[key] for key in ('task_name', 'agent_name') if key in result]
    if len(names) == 0 or any(not isinstance(name, str) for name in names):
        return None
    if any(name != names[0] for name in names):
        return None
    return names[0]


def _candidate_dir(project_root: Path, envelope: dict) -> Path:
    return project_root / 'runtime' / 'v6' / 'candidates' / envelope['task_id'] / str(envelope['batch'])


def _save_tool_result(project_root: str | Path, result: dict) -> tuple[str, str]:
    """Store the exact canonical bytes checked by the kernel, by content hash."""
    if not isinstance(result, dict):
        raise ValueError('Host tool result must be an object')
    raw = compact_json(result)
    checksum = hashlib.sha256(raw).hexdigest()
    relative = f'runtime/v6/host-evidence/{checksum}.json'
    root = Path(project_root).expanduser().resolve()
    target = root / relative
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError('Existing host evidence bytes differ from their content address')
    else:
        before_write(root, target)
        atomic_write(target, raw)
    return relative, checksum


def replay_registered_command(kernel: Any, command_id: str, expected_revision: int,
                              kind: str, payload: dict) -> dict | None:
    """Return an audited no-op for an exact prior CLI submission.

    The first submission remains the only state change.  The original journal
    entry, including its expected revision, must bind the same business input.
    """
    if kind not in ('agent-event', 'agent-message', 'agent-result', 'agent-review',
                    'agent-reconcile', 'agent-cancel'):
        raise ValueError('Unsupported replay command kind')
    state = kernel.snapshot()
    base = Path(kernel.root) / 'runtime' / 'v6'
    commands_path = base / 'commands.json'
    if not commands_path.is_file():
        return None
    commands = json.loads(commands_path.read_text())
    prior = commands.get(command_id)
    if prior is None:
        return None
    events = json.loads((base / 'events.json').read_text())
    if (len(events) != state['revision']
            or (events and 'hash' in events[-1]
                and events[-1]['hash'] != state['last_event_hash'])):
        raise ValueError('REPLAY_RACE: command journal changed during the replay check')
    revision = prior['revision']
    if (type(expected_revision) is not int or revision < 1 or revision > len(events)
            or expected_revision != revision - 1):
        raise ValueError('COMMAND_COLLISION: command revision differs from its original submission')
    entry = events[revision - 1]
    op, saved = entry['op'], entry['payload']
    if (entry['revision'] != revision
            or prior['fingerprint'] != sha256_json({'op': op, 'payload': saved})):
        raise ValueError('COMMAND_COLLISION: command journal does not bind the original operation')
    matched = False
    if kind == 'agent-message':
        matched = op == 'agent_message' and saved == payload
    elif kind == 'agent-event':
        if op == 'review_dispatch':
            matched = saved.get('receipt') == payload
        elif op == 'transition':
            event = saved.get('event') or {}
            matched = event.get('command_id') == command_id and saved.get('receipt') == payload
            if not matched and event.get('to_state') == 'FAILED':
                for uri in event.get('evidence', []):
                    path = Path(kernel.root) / uri
                    if path.is_file() and path.parent == base / 'host-evidence':
                        try:
                            raw = path.read_bytes()
                            if path.name != hashlib.sha256(raw).hexdigest() + '.json':
                                continue
                            proof = json.loads(raw)
                        except (OSError, ValueError):
                            continue
                        if isinstance(proof, dict) and proof.get('failed_dispatch_receipt') == payload:
                            matched = True
                            break
    elif kind == 'agent-result':
        matched = (op == 'transition' and saved.get('candidate') == payload
                   and (saved.get('event') or {}).get('to_state') == 'RESULT_SUBMITTED')
    elif kind == 'agent-review':
        matched = (op == 'transition' and saved.get('review') == payload
                   and (saved.get('event') or {}).get('to_state') == 'ACCEPTED')
    elif kind == 'agent-cancel':
        checksum = hashlib.sha256(compact_json(payload)).hexdigest()
        uri = f'runtime/v6/cancellations/{checksum}.json'
        proof = Path(kernel.root) / uri
        event = saved.get('event') or {}
        matched = (op == 'transition' and event.get('to_state') == 'CANCELLED'
                   and event.get('task_id') == payload.get('task_id')
                   and event.get('reason') == 'CANCEL_REQUESTED'
                   and uri in event.get('evidence', []) and proof.is_file()
                   and proof.read_bytes() == compact_json(payload))
    else:
        if not isinstance(payload, dict) or set(payload) != {'task_id', 'observation'}:
            raise ValueError('COMMAND_COLLISION: reconciliation replay needs task and observation')
        observation = payload['observation']
        checksum = hashlib.sha256(compact_json(observation)).hexdigest()
        uri = f'runtime/v6/host-evidence/{checksum}.json'
        observation_path = Path(kernel.root) / uri
        evidence = ((saved.get('event') or {}).get('evidence', [])
                    if op == 'transition' else saved.get('evidence', [])
                    if op == 'review_dispatch' else [])
        matched = (uri in evidence and observation_path.is_file()
                   and hashlib.sha256(observation_path.read_bytes()).hexdigest() == checksum
                   and json.loads(observation_path.read_text()) == observation
                   and ((op == 'transition' and (saved.get('event') or {}).get('task_id') == payload['task_id']
                         and (saved.get('event') or {}).get('reason') == 'HOST_RECONCILED')
                        or (op == 'review_dispatch' and saved.get('receipt', {}).get('task_id') == payload['task_id'])))
    if not matched:
        raise ValueError('COMMAND_COLLISION: command ID was already used for different content')
    return {'status': 'ALREADY_RECORDED', 'revision': state['revision'],
            'recorded_revision': revision, 'command_id': command_id}


def pending_host_action(envelope: dict, task: dict, *, project_root: str | Path) -> dict:
    """Return a stable action for the host; repeated reads never dispatch.

    DISPATCHING yields a spawn instruction with a required list-agents preflight.
    UNKNOWN yields only a lookup instruction for the original dispatch ID.
    """
    _task_envelope(envelope, task)
    if envelope['execution_class'] not in ('professional', 'review'):
        raise ValueError('This task is not a Codex specialist dispatch')
    dispatch_id = _dispatch_id(envelope, task)
    task_name = _task_name(dispatch_id)
    project_root = Path(project_root).expanduser().resolve()
    if task['state'] == 'UNKNOWN':
        return {'schema': 'codex-host-action/1.0', 'action_id': dispatch_id,
                'dispatch_id': dispatch_id, 'task_id': envelope['task_id'], 'batch': envelope['batch'],
                'task_digest': envelope_digest(envelope), 'tool': 'collaboration.list_agents',
                'task_name': task_name, 'arguments': {},
                'instruction': 'Query the existing agent for this dispatch; do not spawn or resubmit.'}
    if task['state'] != 'DISPATCHING':
        raise ValueError('A running task has no pending dispatch action')
    if task.get('receipt'):
        raise ValueError('Dispatch already has a receipt; reconcile its state')
    candidate_dir = _candidate_dir(project_root, envelope)
    message = (
        'Execute the frozen V6 task below. You are not alone in the codebase; do not revert other agents\' edits. '
        'Project root: ' + str(project_root) + '. Resolve every task URI against this root. '
        'Own only candidate files under ' + str(candidate_dir) + '. Read every item in envelope.inputs, '
        'every listed locked resource, and the relevant Skill before work. If inputs include repair_brief '
        'or repair_failure_1/2, read each cited prior review, fix every recorded defect, and report whether '
        'each old defect is gone. If inputs include upstream_repair, read the bound independent review and '
        'all failed-check evidence, correct the findings owned by this node, and describe the exact changed '
        'fields in the candidate. Do not edit another owner\'s artifacts. '
    )
    if envelope['node_id'] in ('reference_observation', 'compile', 'shot_acceptance',
                               'take_selection', 'adjacent_acceptance', 'whole_acceptance'):
        message += (
            'This graph-only or production-decision node has no native V5 RoleResult. Set '
            'candidate.result_uri and candidate.result_sha256 to null. Do not invent a RoleResult; '
            'submit only the declared graph artifacts, checks, module receipts, handoffs, and evidence. '
        )
    else:
        message += (
            'Copy RoleResult.validator.status exactly from a fresh locked native validator result; '
            'do not infer it from media or visual review status. '
        )
    message += (
        'Record checks and handoffs. '
        'Do not write formal artifacts or '
        'advance workflow state; submit a candidate result for independent review. If this is an independent '
        'review task, review the supplied candidate only and do not create another reviewer.\n\n'
        'Frozen task envelope:\n' + json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2)
    )
    if envelope['node_id'] in ('director', 'art', 'storyboard'):
        message += (
            '\n\nNative handoff reminder: read the frozen runtime/tasks/<task_id>.json '
            'handoff.required_handoffs. The V5 RoleResult.handoff must cover those native '
            'requirements, including screenplay review bindings for a Director task. '
            'candidate.handoffs separately covers the V6 envelope.handoffs; neither list '
            'substitutes for the other.'
        )
    return {'schema': 'codex-host-action/1.0', 'action_id': dispatch_id,
            'dispatch_id': dispatch_id, 'task_id': envelope['task_id'], 'batch': envelope['batch'],
            'task_digest': envelope_digest(envelope), 'tool': 'collaboration.spawn_agent',
            'task_name': task_name,
            'preflight': {'tool': 'collaboration.list_agents', 'match_task_name': task_name},
            'arguments': {'task_name': task_name, 'agent_type': 'worker', 'message': message},
            'candidate_dir': str(candidate_dir)}


def validate_dispatch_receipt(envelope: dict, receipt: dict, *, task: dict | None = None,
                              action: dict | None = None,
                              project_root: str | Path | None = None) -> dict:
    """Check a host tool receipt against the exact frozen task and dispatch."""
    _schema('task-envelope', envelope)
    _schema('dispatch-receipt', receipt)
    if receipt['host'] != 'codex' or receipt['task_id'] != envelope['task_id'] or receipt['batch'] != envelope['batch']:
        raise ValueError('Dispatch receipt host, task, or batch differs')
    if receipt['task_digest'] != envelope_digest(envelope):
        raise ValueError('Dispatch receipt binds a stale or altered envelope')
    if receipt['action_id'] != receipt['dispatch_id']:
        raise ValueError('Dispatch action ID must equal the deterministic dispatch ID')
    if task is not None:
        _task_envelope(envelope, task)
        if receipt['dispatch_id'] != _dispatch_id(envelope, task):
            raise ValueError('Dispatch receipt ID differs from the pending action')
        if task['state'] == 'DISPATCHING' and receipt['host_tool'] not in ('collaboration.spawn_agent', 'collaboration.list_agents'):
            raise ValueError('Initial dispatch requires a spawn or reconciliation tool receipt')
        if task['state'] == 'UNKNOWN' and receipt['host_tool'] != 'collaboration.list_agents':
            raise ValueError('UNKNOWN can only be reconciled from an agent lookup')
    if action is not None:
        if action['task_id'] != receipt['task_id'] or action['batch'] != receipt['batch']:
            raise ValueError('Receipt does not match pending host action')
        if action['dispatch_id'] != receipt['dispatch_id'] or action['task_digest'] != receipt['task_digest']:
            raise ValueError('Receipt does not match pending action identity')
        if action['action_id'] != receipt['action_id']:
            raise ValueError('Receipt does not match pending action ID')
        if action['tool'] != receipt['host_tool']:
            raise ValueError('Receipt was not produced by the pending host tool')
    if receipt['status'] == 'RUNNING' and not receipt['agent_id']:
        raise ValueError('Confirmed dispatch requires the actual agent ID')
    if receipt['agent_id'] and not receipt['agent_id'].endswith('/' + _task_name(receipt['dispatch_id'])):
        raise ValueError('Agent ID is not the deterministic agent for this dispatch')
    if receipt['status'] == 'FAILED' and (not receipt['error'] or
                                          not receipt['error'].get('evidence')):
        raise ValueError('Failed dispatch requires structured error evidence')
    if receipt['status'] == 'RUNNING':
        if project_root is None:
            raise ValueError('Project root is required to verify host tool evidence')
        uri = receipt['tool_result_uri']
        checksum = receipt['tool_result_sha256']
        root = Path(project_root).expanduser().resolve()
        evidence_path = (root / uri).resolve()
        if not evidence_path.is_relative_to(root / 'runtime' / 'v6' / 'host-evidence'):
            raise ValueError('Host tool evidence is outside the protected evidence directory')
        raw = evidence_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError('Host tool evidence bytes changed')
        result = json.loads(raw)
        if receipt['host_tool'] == 'collaboration.spawn_agent':
            if _spawn_agent_id(result) != receipt['agent_id']:
                raise ValueError('Actual spawn result does not name the registered agent')
        else:
            agents = result.get('agents') if isinstance(result, dict) else None
            if not isinstance(agents, list) or sum(isinstance(agent, dict) and
                 agent.get('agent_name') == receipt['agent_id'] for agent in agents) != 1:
                raise ValueError('Actual list_agents result does not uniquely contain the registered agent')
    return receipt


def validate_agent_message(envelope: dict, task: dict, message: dict,
                           *, project_root: str | Path | None = None) -> dict:
    """Bind communication to the dispatched agent; messages do not change state."""
    _task_envelope(envelope, task)
    _schema('agent-message', message)
    if message['type'] not in MESSAGE_TYPES:
        raise ValueError('Unsupported agent message type')
    if message['task_id'] != envelope['task_id'] or message['batch'] != envelope['batch']:
        raise ValueError('Agent message belongs to another task or batch')
    creator = (task.get('receipt') or {}).get('agent_id')
    reviewer = (task.get('review_dispatch') or {}).get('agent_id')
    registered = {agent_id for agent_id in (creator, reviewer) if agent_id}
    if not registered:
        raise ValueError('Agent message has no registered executor')
    if message['sender_id'] == 'kernel':
        if message['recipient_id'] not in registered or message['type'] == 'RESULT':
            raise ValueError('Kernel message must address a registered executor and cannot submit a result')
    elif message['sender_id'] not in registered:
        raise ValueError('Agent message sender differs from registered executors')
    if message['type'] == 'RESULT' and task['state'] == 'REVIEW_REQUIRED' \
            and message['sender_id'] != reviewer:
        raise ValueError('Only the dispatched reviewer may submit a review result')
    participants = {'kernel', *registered}
    if message['recipient_id'] not in participants or message['recipient_id'] == message['sender_id']:
        raise ValueError('Agent message has an unregistered recipient')
    recorded = {item['message_id'] for item in task.get('messages', [])}
    if message['message_id'] in recorded:
        raise ValueError('Agent message ID was already recorded')
    if message['in_reply_to'] is not None and message['in_reply_to'] not in recorded:
        raise ValueError('Agent message replies to an unknown message')
    if message['subject_uri'] is not None:
        if project_root is None:
            raise ValueError('Project root is required to verify message subject bytes')
        root = Path(project_root).expanduser().resolve()
        subject = (root / message['subject_uri']).resolve()
        if not subject.is_relative_to(root) or not subject.is_file():
            raise ValueError('Agent message subject is missing or outside the project')
        raw = subject.read_bytes()
        if hashlib.sha256(raw).hexdigest() != message['subject_sha256']:
            raise ValueError('Agent message subject bytes changed')
        if message['type'] == 'RESULT':
            kind = 'review-record' if task['state'] == 'REVIEW_REQUIRED' else 'candidate-result'
            _schema(kind, json.loads(raw))
    return message


def reconcile_unknown(envelope: dict, task: dict, observation: dict) -> dict:
    """Interpret list_agents after uncertain dispatch or a spawn crash window."""
    _task_envelope(envelope, task)
    if task['state'] not in ('DISPATCHING', 'UNKNOWN', 'REVIEW_REQUIRED'):
        raise ValueError('Only pending or uncertain dispatches can be reconciled')
    review = task['state'] == 'REVIEW_REQUIRED'
    if review and task.get('review_dispatch'):
        raise ValueError('Reviewer dispatch is already registered')
    expected = {'schema', 'source_tool', 'dispatch_id', 'observed_at', 'host_call_id', 'tool_result'}
    if set(observation) != expected or observation['schema'] != 'codex-agent-observation/1.0':
        raise ValueError('Agent observation has an invalid shape')
    if observation['source_tool'] != 'collaboration.list_agents':
        raise ValueError('Agent observation must come from list_agents')
    dispatch_id = expected_review_dispatch_id(envelope) if review else _dispatch_id(envelope, task)
    if observation['dispatch_id'] != dispatch_id:
        raise ValueError('Agent observation refers to another dispatch')
    result = observation['tool_result']
    if not isinstance(result, dict) or not isinstance(result.get('agents'), list):
        raise ValueError('Agent observation is missing the raw list_agents result')
    name = _task_name(dispatch_id)
    matches = [agent for agent in result['agents'] if isinstance(agent, dict)
               and isinstance(agent.get('agent_name'), str)
               and agent['agent_name'].endswith('/' + name)]
    evidence = 'OBS_' + _digest(observation)
    if len(matches) > 1:
        return {'status': 'BLOCKED', 'reason': 'Multiple agents match one dispatch',
                'dispatch_id': dispatch_id, 'evidence': evidence}
    if not matches:
        return {'status': 'UNRESOLVED', 'reason': 'No matching agent was observed; do not dispatch again',
                'dispatch_id': dispatch_id, 'evidence': evidence}
    match = matches[0]
    agent_id = match['agent_name']
    agent_status = match.get('agent_status')
    if not isinstance(agent_status, str) or not agent_status:
        raise ValueError('Observed agent has no status')
    prior = task.get('receipt') or {}
    if not review and prior.get('agent_id') and prior['agent_id'] != agent_id:
        raise ValueError('Observed agent differs from the original dispatch receipt')
    receipt = dict(task.get('receipt') or {})
    receipt.update({'schema': 'dispatch-receipt/6.0', 'task_id': envelope['task_id'],
                    'batch': envelope['batch'], 'host': 'codex',
                    'host_tool': 'collaboration.list_agents',
                    'host_call_id': observation['host_call_id'], 'dispatch_id': dispatch_id,
                    'action_id': dispatch_id,
                    'agent_id': agent_id, 'task_digest': envelope_digest(envelope),
                    'status': 'RUNNING', 'observed_at': observation['observed_at'],
                    'result_uri': receipt.get('result_uri'), 'error': None})
    receipt.setdefault('sent_at', observation['observed_at'])
    return {'status': 'FOUND', 'agent_status': agent_status, 'receipt': receipt,
            'dispatch_id': dispatch_id, 'evidence': evidence,
            'tool_result': result, 'review': review}


def pending_review_action(envelope: dict, task: dict, *, project_root: str | Path) -> dict:
    """Describe an independent reviewer spawn for the current candidate."""
    _schema('task-envelope', envelope)
    if envelope['execution_class'] not in ('professional', 'review'):
        raise ValueError('This task does not require a Codex specialist reviewer')
    if task.get('envelope') != envelope or task.get('state') != 'REVIEW_REQUIRED':
        raise ValueError('Review dispatch requires the current REVIEW_REQUIRED task')
    if not task.get('candidate'):
        raise ValueError('A reviewer cannot inspect a missing candidate')
    if task.get('review_dispatch'):
        raise ValueError('Reviewer already dispatched for this candidate')
    dispatch_id = expected_review_dispatch_id(envelope)
    task_name = _task_name(dispatch_id)
    project_root = Path(project_root).expanduser().resolve()
    review_dir = project_root / 'runtime' / 'v6' / 'reviews' / envelope['task_id'] / str(envelope['batch'])
    message = (
        'Independently review this candidate against the frozen task and every declared check. '
        'You are not alone in the codebase; do not revert others\' edits. Project root: '
        + str(project_root) + '. Resolve task URIs against this root. Own only review files under '
        + str(review_dir) + '. Read the candidate and its referenced evidence; do not change the candidate '
        'or formal project state. Do not create another reviewer. Return a structured V6 review record.\n\n'
        'Frozen task envelope:\n' + json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2)
        + '\nCandidate:\n' + json.dumps(task['candidate'], ensure_ascii=False, sort_keys=True, indent=2)
    )
    return {'schema': 'codex-host-action/1.0', 'action_id': dispatch_id,
            'dispatch_id': dispatch_id, 'task_id': envelope['task_id'], 'batch': envelope['batch'],
            'task_digest': envelope_digest(envelope), 'tool': 'collaboration.spawn_agent',
            'task_name': task_name,
            'preflight': {'tool': 'collaboration.list_agents', 'match_task_name': task_name},
            'arguments': {'task_name': task_name, 'agent_type': 'worker', 'message': message},
            'review_dir': str(review_dir)}


def receipt_from_spawn_result(action: dict, tool_result: dict, *, project_root: str | Path,
                              sent_at: str,
                              observed_at: str, host_call_id: str | None = None,
                              result_uri: str | None = None) -> dict:
    """Build a receipt from the actual collaboration.spawn_agent return value."""
    if action.get('tool') != 'collaboration.spawn_agent':
        raise ValueError('The action is not a spawn_agent call')
    agent_id = _spawn_agent_id(tool_result)
    if not agent_id:
        raise ValueError('spawn_agent did not return one canonical task name')
    if not agent_id.endswith('/' + action['task_name']):
        raise ValueError('spawn_agent returned another task name')
    evidence_uri, evidence_sha256 = _save_tool_result(project_root, tool_result)
    record = {'schema': 'dispatch-receipt/6.0', 'task_id': action['task_id'],
              'batch': action['batch'], 'host': 'codex',
              'host_tool': 'collaboration.spawn_agent', 'host_call_id': host_call_id,
              'dispatch_id': action['dispatch_id'], 'action_id': action['action_id'],
              'tool_result_uri': evidence_uri, 'tool_result_sha256': evidence_sha256,
              'agent_id': agent_id,
              'task_digest': action['task_digest'], 'status': 'RUNNING',
              'sent_at': sent_at, 'observed_at': observed_at,
              'result_uri': result_uri, 'error': None}
    _schema('dispatch-receipt', record)
    return record


def unknown_spawn_receipt(action: dict, *, sent_at: str, observed_at: str,
                          host_call_id: str | None = None) -> dict:
    """Record an uncertain call without inventing an agent ID or retrying."""
    if action.get('tool') != 'collaboration.spawn_agent':
        raise ValueError('The action is not a spawn_agent call')
    record = {'schema': 'dispatch-receipt/6.0', 'task_id': action['task_id'],
              'batch': action['batch'], 'host': 'codex',
              'host_tool': 'collaboration.spawn_agent', 'host_call_id': host_call_id,
              'dispatch_id': action['dispatch_id'], 'action_id': action['action_id'],
              'tool_result_uri': None, 'tool_result_sha256': None, 'agent_id': None,
              'task_digest': action['task_digest'], 'status': 'UNKNOWN',
              'sent_at': sent_at, 'observed_at': observed_at,
              'result_uri': None, 'error': None}
    _schema('dispatch-receipt', record)
    return record


def validate_review_dispatch_receipt(envelope: dict, task: dict, receipt: dict,
                                     *, action: dict | None = None,
                                     project_root: str | Path | None = None) -> dict:
    """Require a distinct, real Codex reviewer for the candidate version."""
    _schema('task-envelope', envelope)
    _schema('dispatch-receipt', receipt)
    if task.get('envelope') != envelope or task.get('state') != 'REVIEW_REQUIRED':
        raise ValueError('Reviewer dispatch is not for the current review task')
    if task.get('review_dispatch'):
        raise ValueError('Reviewer dispatch is already registered')
    if receipt['task_id'] != envelope['task_id'] or receipt['batch'] != envelope['batch']:
        raise ValueError('Reviewer receipt refers to another task or batch')
    if receipt['host'] != 'codex' or receipt['host_tool'] not in ('collaboration.spawn_agent', 'collaboration.list_agents'):
        raise ValueError('Reviewer requires an actual Codex spawn or lookup receipt')
    if receipt['dispatch_id'] != expected_review_dispatch_id(envelope) or receipt['task_digest'] != envelope_digest(envelope):
        raise ValueError('Reviewer receipt does not bind the current frozen task')
    if receipt['action_id'] != receipt['dispatch_id']:
        raise ValueError('Reviewer action ID differs from dispatch ID')
    if receipt['status'] != 'RUNNING' or not receipt['agent_id']:
        raise ValueError('Reviewer must have a confirmed actual agent ID')
    if not receipt['agent_id'].endswith('/' + _task_name(receipt['dispatch_id'])):
        raise ValueError('Reviewer agent ID differs from the dispatched review task')
    creator = (task.get('receipt') or {}).get('agent_id')
    if creator and receipt['agent_id'] == creator:
        raise ValueError('Creator cannot review their own candidate')
    if action is not None and (action['dispatch_id'] != receipt['dispatch_id'] or
                               (receipt['host_tool'] == 'collaboration.spawn_agent' and action['tool'] != receipt['host_tool'])):
        raise ValueError('Reviewer receipt differs from the pending action')
    if project_root is None:
        raise ValueError('Project root is required to verify reviewer tool evidence')
    root = Path(project_root).expanduser().resolve()
    path = (root / receipt['tool_result_uri']).resolve()
    if not path.is_relative_to(root / 'runtime' / 'v6' / 'host-evidence'):
        raise ValueError('Reviewer tool evidence is outside the protected evidence directory')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt['tool_result_sha256']:
        raise ValueError('Reviewer tool evidence bytes changed')
    result = json.loads(raw)
    if receipt['host_tool'] == 'collaboration.spawn_agent':
        if _spawn_agent_id(result) != receipt['agent_id']:
            raise ValueError('Actual reviewer spawn result names another agent')
    else:
        agents = result.get('agents') if isinstance(result, dict) else None
        if not isinstance(agents, list) or sum(isinstance(agent, dict) and
             agent.get('agent_name') == receipt['agent_id'] for agent in agents) != 1:
            raise ValueError('Actual reviewer lookup does not uniquely name the agent')
    return receipt


class CodexHostBridge:
    """Small adapter that submits checked host evidence through V6TaskKernel."""

    def __init__(self, kernel: Any):
        self.kernel = kernel

    def _current(self, task_id: str) -> tuple[dict, dict]:
        state = self.kernel.snapshot()
        try:
            task = state['tasks'][task_id]
        except KeyError as error:
            raise ValueError('Unknown V6 task') from error
        return state, task

    def pending(self, task_id: str) -> dict | None:
        _, task = self._current(task_id)
        if task['state'] == 'REVIEW_REQUIRED':
            return (pending_review_action(task['envelope'], task, project_root=self.kernel.root)
                    if not task.get('review_dispatch') else None)
        if task['state'] in ('DISPATCHING', 'UNKNOWN'):
            return pending_host_action(task['envelope'], task, project_root=self.kernel.root)
        return None

    def register_dispatch(self, receipt: dict, *, command_id: str, expected_revision: int,
                          evidence: list[str] | None = None) -> dict:
        if evidence not in (None, []):
            raise ValueError('Direct dispatch evidence is derived from its receipt; use reconcile for observations')
        replay = replay_registered_command(self.kernel, command_id, expected_revision,
                                           'agent-event', receipt)
        if replay is not None:
            return replay
        state, task = self._current(receipt['task_id'])
        envelope = task['envelope']
        action = pending_host_action(envelope, task, project_root=self.kernel.root)
        validate_dispatch_receipt(envelope, receipt, task=task, action=action,
                                  project_root=self.kernel.root)
        if state['revision'] != expected_revision:
            raise ValueError('Project revision changed before dispatch registration')
        if task['state'] == 'UNKNOWN' and receipt['status'] == 'UNKNOWN':
            raise ValueError('An UNKNOWN dispatch must be reconciled, not re-recorded')
        target, reason = _DISPATCH_STATES[receipt['status']]
        if receipt['host_tool'] == 'collaboration.list_agents' and target == 'RUNNING':
            reason = 'HOST_RECONCILED'
        if target == 'FAILED':
            with transaction(self.kernel.root):
                uri, checksum = _save_tool_result(self.kernel.root, {'failed_dispatch_receipt': receipt})
                failure = receipt['error']
                event = self._event(task, command_id, expected_revision, target, reason,
                                    [uri, 'sha256:' + checksum], receipt['observed_at'],
                                    error={'code': failure['code'], 'owner_node': envelope['node_id'],
                                           'failed_check': failure['failed_check'],
                                           'evidence': failure['evidence'],
                                           'retryable': failure['retryable'],
                                           'recovery_action': failure['recovery_action']})
                return self.kernel.transition(event)
        proof = ['dispatch:' + receipt['dispatch_id']]
        if receipt['host_call_id']:
            proof = [*proof, 'host-call:' + receipt['host_call_id']]
        if receipt['tool_result_sha256']:
            proof = [*proof, 'host-file:' + receipt['tool_result_sha256']]
        uncertainty = ({'code': 'HOST_RESULT_UNKNOWN', 'owner_node': envelope['node_id'],
                        'failed_check': 'dispatch_result', 'evidence': proof,
                        'retryable': False, 'recovery_action': 'RECONCILE'}
                       if target == 'UNKNOWN' else None)
        event = self._event(task, command_id, expected_revision, target, reason,
                            proof, receipt['observed_at'], error=uncertainty)
        return self.kernel.transition(event, receipt=receipt)

    def record_message(self, message: dict, *, command_id: str, expected_revision: int) -> dict:
        replay = replay_registered_command(self.kernel, command_id, expected_revision,
                                           'agent-message', message)
        if replay is not None:
            return replay
        state, task = self._current(message['task_id'])
        if state['revision'] != expected_revision:
            raise ValueError('Project revision changed before message registration')
        validate_agent_message(task['envelope'], task, message, project_root=self.kernel.root)
        return self.kernel.record_message(message, command_id, expected_revision)

    def register_review_dispatch(self, receipt: dict, *, command_id: str,
                                 expected_revision: int,
                                 evidence: list[str] | None = None) -> dict:
        if evidence not in (None, []):
            raise ValueError('Direct reviewer evidence is derived from its receipt; use reconcile for observations')
        replay = replay_registered_command(self.kernel, command_id, expected_revision,
                                           'agent-event', receipt)
        if replay is not None:
            return replay
        state, task = self._current(receipt['task_id'])
        if state['revision'] != expected_revision:
            raise ValueError('Project revision changed before reviewer registration')
        action = pending_review_action(task['envelope'], task, project_root=self.kernel.root)
        validate_review_dispatch_receipt(task['envelope'], task, receipt, action=action,
                                         project_root=self.kernel.root)
        return self.kernel.register_review_dispatch(receipt, command_id, expected_revision,
                                                     evidence=[])

    def reconcile(self, task_id: str, observation: dict, *, command_id: str,
                  expected_revision: int) -> dict:
        replay = replay_registered_command(self.kernel, command_id, expected_revision,
                                           'agent-reconcile',
                                           {'task_id': task_id, 'observation': observation})
        if replay is not None:
            return replay
        state, task = self._current(task_id)
        if state['revision'] != expected_revision:
            raise ValueError('Project revision changed before reconciliation')
        decision = reconcile_unknown(task['envelope'], task, observation)
        if decision['status'] != 'FOUND':
            return decision
        receipt = decision['receipt']
        with transaction(self.kernel.root):
            observation_uri, _ = _save_tool_result(self.kernel.root, observation)
            uri, checksum = _save_tool_result(self.kernel.root, decision['tool_result'])
            receipt['tool_result_uri'] = uri
            receipt['tool_result_sha256'] = checksum
            if decision['review']:
                validate_review_dispatch_receipt(task['envelope'], task, receipt,
                                                 project_root=self.kernel.root)
                return self.kernel.register_review_dispatch(receipt, command_id, expected_revision,
                                                            evidence=[uri, observation_uri])
            validate_dispatch_receipt(task['envelope'], receipt, task=task,
                                      project_root=self.kernel.root)
            event = self._event(task, command_id, expected_revision, 'RUNNING', 'HOST_RECONCILED',
                                [decision['evidence'], observation_uri, 'host-file:' + checksum],
                                observation['observed_at'])
            return self.kernel.transition(event, receipt=receipt)

    @staticmethod
    def _event(task: dict, command_id: str, revision: int, target: str, reason: str,
               evidence: list[str], at: str, error: dict | None = None) -> dict:
        envelope = task['envelope']
        event = {'schema': 'state-event/6.0', 'command_id': command_id,
                'expected_revision': revision, 'task_id': envelope['task_id'],
                'batch': envelope['batch'], 'object_version': task['version'],
                'from_state': task['state'], 'to_state': target, 'reason': reason,
                'check_results': [{'id': 'host-evidence', 'status': ('FAIL' if target == 'FAILED'
                                                                   else 'BLOCKED' if target == 'UNKNOWN'
                                                                   else 'PASS'),
                                   'evidence': evidence}],
                'evidence': evidence, 'affected_outputs': [], 'actor_kind': 'host',
                'actor_id': 'codex', 'at': at}
        if error is not None:
            event['error'] = error
        return event
