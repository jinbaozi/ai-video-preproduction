"""Evidence bridge from V6 graph host tasks to the production ledger."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .assembly import _probe
from .production import ProductionLedger
from .v5 import V5Kernel
from .v5_modules import read
from .v5_modules import digest_file
from .transactions import transaction
from .v6_graph import stage_by_id


_HOST_RECORD_PREFIX = {
    'video_execution': 'runtime/production/executions/',
    'take_recovery': 'runtime/production/takes/',
    'assembly': 'runtime/production/assembly/',
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_host_node_candidate(project_root, envelope, candidate):
    """Re-read authoritative execution/media bytes before a host node is accepted.

    The V6 kernel invokes this inside its transaction. Candidate artifacts are
    immutable snapshots; their content must equal the separately recorded
    production ledger. A claimed PASS in a candidate is never used as proof.
    """
    node_id = envelope['node_id']
    prefix = _HOST_RECORD_PREFIX.get(node_id)
    if prefix is None:
        raise ValueError('No production host verifier for ' + node_id)
    root = Path(project_root).resolve()
    kernel = V5Kernel(root)
    ledger = ProductionLedger(kernel)
    if not ledger.strict:
        raise ValueError('Production host verifier requires protocol 6.0')
    uri = candidate.get('host_record_uri')
    if not isinstance(uri, str) or not uri.startswith(prefix) or not uri.endswith('.json'):
        raise ValueError('Host candidate does not name a node-owned production record')
    source = kernel.path(uri)
    if not source.is_file() or candidate.get('host_record_sha256') != _digest(source):
        raise ValueError('Production host record bytes differ from candidate hash')
    record = read(source)
    failures = ledger.validate_production_integrity()
    if failures:
        raise ValueError('Production ledger integrity failed: ' + '; '.join(failures))
    artifact_by_kind = {item['kind']: item for item in candidate['artifacts']}
    if set(artifact_by_kind) != {item['kind'] for item in envelope['expected_artifacts']}:
        raise ValueError('Host candidate artifact kinds differ from graph outputs')
    snapshot_kind = {'video_execution': 'ExecutionRecord', 'take_recovery': 'Take',
                     'assembly': 'AssemblyRecord'}[node_id]
    snapshot = kernel.path(artifact_by_kind[snapshot_kind]['uri'])
    if _digest(snapshot) != _digest(source):
        raise ValueError('Candidate snapshot differs from authoritative production record')
    if node_id == 'video_execution':
        if (record['id'] != envelope['scope']['ids'][0] or
            record['state'] not in ('SUBMITTED', 'SUCCEEDED') or
            not record.get('task_id')):
            raise ValueError('Video execution has no confirmed matching submission')
        job = ledger._load('jobs/' + record['job_id'] + '.json')
        ledger._verify_job(job)
        manifest = ledger._load('delivery-manifest.json')
        ledger._verify_manifest(manifest)
        if not set(job['shot_ids']) <= set(manifest['shot_ids']):
            raise ValueError('Execution job is outside frozen delivery')
    elif node_id == 'take_recovery':
        if record['id'] != envelope['scope']['ids'][0]:
            raise ValueError('Take task scope differs from recovered Take')
        ledger._verify_take(record)
        job = ledger._load('jobs/' + record['job_id'] + '.json')
        if not set(job['shot_ids']) <= set(ledger._load('delivery-manifest.json')['shot_ids']):
            raise ValueError('Recovered Take is outside frozen delivery')
    else:
        if record.get('status') != 'CHECKED':
            raise ValueError('Assembly is not checked')
        output = kernel.path(record['output_uri'])
        if _digest(output) != record['output_sha256'] or _probe(output) != record['probe']:
            raise ValueError('Assembly final media differs from registered bytes or probe')
        pointer = read(kernel.path(artifact_by_kind['FinalMedia']['uri']))
        if pointer != {'output_uri': record['output_uri'], 'output_sha256': record['output_sha256']}:
            raise ValueError('FinalMedia pointer does not bind the checked output')
        failures = ledger.video_delivery_blockers(include_whole=False)
        if failures:
            raise ValueError('Assembly completion gate failed: ' + '; '.join(failures))
    return {'status': 'PASS', 'node_id': node_id, 'record_id': record['id'],
            'record_sha256': candidate['host_record_sha256']}


class V6ProductionRuntime:
    """The only V6 production mutation gateway used by the CLI.

    The production ledger owns media and acceptance bytes; the V6 task kernel
    owns stage state. Both mutations run under the same project transaction.
    External submission and polling happen outside that write lock.
    """

    def __init__(self, runtime):
        if runtime.project.get('orchestration_protocol') != '6.0':
            raise ValueError('V6 production requires protocol 6.0')
        if runtime.production_target() != 'video':
            raise ValueError('Production target must be video')
        self.runtime = runtime
        self.root = runtime.root
        self.ledger = ProductionLedger(runtime)

    @staticmethod
    def _project_scope():
        return {'kind': 'project', 'ids': []}

    @staticmethod
    def _scope(kind, *ids):
        return {'kind': kind, 'ids': list(ids)}

    def _manifest(self):
        manifest = self.ledger._load('delivery-manifest.json')
        self.ledger._verify_manifest(manifest)
        return manifest

    def _catalogue(self, node_id):
        manifest = self._manifest()
        shots = manifest['shot_ids']
        pairs = list(zip(shots, shots[1:]))
        takes = [row for row in self.ledger.takes() if row['job_id'] in manifest['job_ids']]
        scopes = {
            'video_freeze': [self._project_scope()],
            'video_execution': [self._scope('generation_request', row['id']) for row in self.ledger.records()
                                if row['job_id'] in manifest['job_ids']],
            'take_recovery': [self._scope('take', row['id']) for row in takes],
            'shot_acceptance': [self._scope('shot', shot) for shot in shots],
            'take_selection': [self._scope('shot', shot) for shot in shots],
            'adjacent_acceptance': [self._project_scope()],
            'assembly': [self._project_scope()],
            'whole_acceptance': [self._project_scope()],
            'video_delivery': [self._project_scope()],
            'preproduction_delivery': [self._project_scope()],
        }
        node = stage_by_id(self.runtime.graph, node_id)
        return {name: scopes[name] for name in [node_id, *node['depends_on']]}

    def _task_id(self, node_id, scope):
        manifest = self._manifest()
        raw = json_bytes({'manifest': manifest['sha256'], 'node': node_id, 'scope': scope})
        return 'V6P_' + node_id + '_' + hashlib.sha256(raw).hexdigest()[:16]

    def _task_rows(self, node_id, scope):
        return sorted((row for row in self.runtime.kernel.snapshot()['tasks'].values()
                       if row['envelope']['node_id'] == node_id and row['envelope']['scope'] == scope),
                      key=lambda row: (row['envelope']['input_revision'], row['envelope']['batch']))

    def _current_task_id(self, node_id, scope):
        rows = self._task_rows(node_id, scope)
        return rows[-1]['envelope']['task_id'] if rows else self._task_id(node_id, scope)

    def _next_task_id(self, node_id, scope):
        rows = self._task_rows(node_id, scope)
        if not rows:
            return self._task_id(node_id, scope)
        latest = rows[-1]
        if latest['state'] in ('STALE', 'FAILED'):
            return self._task_id(node_id, scope) + '_v' + str(len(rows) + 1)
        return latest['envelope']['task_id']

    def _create(self, node_id, scope, *, links=None, inputs=None, task_id=None):
        task_id = task_id or self._next_task_id(node_id, scope)
        envelope = self.runtime.create_graph_task(node_id, scope, task_id,
                    required_scopes=self._catalogue(node_id), scope_links=links or {},
                    extra_inputs=inputs or [])
        return envelope

    def _transition(self, task_id, to_state, reason, *, evidence=None, checks=None,
                    candidate=None, error=None):
        row = self.runtime.kernel.snapshot()['tasks'][task_id]
        event = self.runtime._event(row, to_state, reason,
                    command_id='prod-'+task_id+'-'+str(row['version'])+'-'+to_state,
                    evidence=evidence or [], checks=checks or [])
        if error is not None:
            event['error'] = error
        if to_state == 'ACCEPTED' and candidate is not None and reason == 'HOST_EXECUTION_CONFIRMED':
            return self.runtime.kernel.complete_host_task(event, candidate)
        return self.runtime.kernel.transition(event, candidate=candidate)

    def _checks(self, envelope, evidence):
        return [{'id': item['id'], 'status': 'PASS', 'evidence': list(evidence)}
                for item in envelope['validators']]

    def _candidate(self, envelope, values, *, creator, evidence, host_record_uri=None):
        prefix = f"runtime/v6/candidates/{envelope['task_id']}/{envelope['batch']}/"
        artifacts = []
        for spec in envelope['expected_artifacts']:
            value = values[spec['kind']]
            uri = prefix + spec['kind'] + '.json'
            self.runtime.write(uri, value)
            artifacts.append({'slot': spec['slot'], 'kind': spec['kind'],
                              'uri': uri, 'sha256': digest_file(self.runtime.path(uri))})
        result = {'schema': 'candidate-result/6.0', 'task_id': envelope['task_id'],
                  'batch': envelope['batch'], 'agent_id': creator,
                  'input_digest': envelope['input_digest'], 'result_uri': None,
                  'result_sha256': None, 'artifacts': artifacts, 'module_receipts': [],
                  'checks': self._checks(envelope, evidence), 'handoffs': [], 'unresolved': []}
        if host_record_uri is not None:
            result['host_record_uri'] = host_record_uri
            result['host_record_sha256'] = digest_file(self.runtime.path(host_record_uri))
        return result

    def _accept_system(self, envelope, values, evidence):
        candidate = self._candidate(envelope, values, creator='kernel', evidence=evidence)
        self._transition(envelope['task_id'], 'ACCEPTED', 'SYSTEM_VALIDATED',
                         evidence=evidence, checks=candidate['checks'], candidate=candidate)
        return {'status': 'ACCEPTED', 'task_id': envelope['task_id'], 'node_id': envelope['node_id']}

    def _host_task(self, node_id, scope, record_uri, values, *, links=None, inputs=None):
        """Record a local host operation through the complete V6 state path."""
        with transaction(self.root):
            task_id = self._next_task_id(node_id, scope)
            rows = self.runtime.kernel.snapshot()['tasks']
            if task_id in rows:
                envelope = rows[task_id]['envelope']
                if rows[task_id]['state'] == 'ACCEPTED':
                    return {'status': 'ACCEPTED', 'task_id': task_id, 'node_id': node_id}
            else:
                envelope = self._create(node_id, scope, links=links, inputs=inputs)
            state = self.runtime.kernel.snapshot()['tasks'][task_id]['state']
            if state == 'PENDING':
                self._transition(task_id, 'READY', 'DEPENDENCIES_SATISFIED')
                state = 'READY'
            if state == 'READY':
                self._transition(task_id, 'DISPATCHING', 'DISPATCH_REQUESTED')
                state = 'DISPATCHING'
            if state == 'UNKNOWN':
                self._transition(task_id, 'RUNNING', 'HOST_RECONCILED', evidence=[record_uri])
                state = 'RUNNING'
            if state == 'DISPATCHING':
                self._transition(task_id, 'RUNNING', 'HOST_EXECUTION_STARTED', evidence=[record_uri])
                state = 'RUNNING'
            if state != 'RUNNING':
                raise ValueError('Host task cannot accept result in state '+state)
            candidate = self._candidate(envelope, values, creator='production_host',
                                        evidence=[record_uri], host_record_uri=record_uri)
            self._transition(task_id, 'RESULT_SUBMITTED', 'HOST_RESULT_RECEIVED',
                             evidence=[record_uri], candidate=candidate)
            self._transition(task_id, 'VALIDATING', 'VALIDATION_STARTED')
            self._transition(task_id, 'ACCEPTED', 'HOST_EXECUTION_CONFIRMED',
                             checks=candidate['checks'], evidence=[record_uri], candidate=candidate)
            return {'status': 'ACCEPTED', 'task_id': task_id, 'node_id': node_id,
                    'record_uri': record_uri}

    def _execution_stage(self, record):
        uri = 'runtime/production/executions/'+record['id']+'.json'
        job_id = record['job_id']
        job_uri = 'runtime/production/jobs/'+job_id+'.json'
        scope = self._scope('generation_request', record['id'])
        inputs = [{'slot': 'frozen_job', 'uri': job_uri,
                   'sha256': digest_file(self.runtime.path(job_uri)), 'version': 0}]
        rows = self._task_rows('video_execution', scope)
        if rows and rows[-1]['state'] == 'STALE':
            if record['state'] != 'SUCCEEDED' or not record.get('task_id'):
                raise ValueError('Recovered execution needs the original provider task ID and Take')
            recovery_uri = ('runtime/production/reconciliations/'+record['id']+'/' +
                            str(record['version'])+'.json')
            recovery = {'record_id': record['id'], 'job_id': job_id,
                        'provider_task_id': record['task_id'], 'record_version': record['version'],
                        'record_sha256': digest_file(self.runtime.path(uri)),
                        'frozen_job_sha256': digest_file(self.runtime.path(job_uri)),
                        'action': 'REVALIDATE_ORIGINAL_CALL'}
            path = self.runtime.path(recovery_uri)
            if path.exists() and read(path) != recovery:
                raise ValueError('Recovery proof differs from the original execution')
            if not path.exists():
                self.runtime.write(recovery_uri, recovery)
            inputs.append({'slot': 'original_call_recovery', 'uri': recovery_uri,
                           'sha256': digest_file(path), 'version': record['version']})
        return self._host_task('video_execution', self._scope('generation_request', record['id']),
                              uri, {'ExecutionRecord': record},
                              inputs=inputs)

    def _prepare_execution(self, record):
        scope = self._scope('generation_request', record['id'])
        job_uri = 'runtime/production/jobs/'+record['job_id']+'.json'
        envelope = self._create('video_execution', scope,
                    inputs=[{'slot': 'frozen_job', 'uri': job_uri,
                             'sha256': digest_file(self.runtime.path(job_uri)), 'version': 0}])
        self._transition(envelope['task_id'], 'READY', 'DEPENDENCIES_SATISFIED')
        self._transition(envelope['task_id'], 'DISPATCHING', 'DISPATCH_REQUESTED')
        return envelope

    def _take_stage(self, take):
        uri = 'runtime/production/takes/'+take['id']+'.json'
        scope = self._scope('take', take['id'])
        job_scope = self._scope('generation_request', take['record_id'])
        return self._host_task('take_recovery', scope, uri, {'Take': take},
                              links={'video_execution': [job_scope]})

    def _queue_review(self, node_id, scope, intent, *, links=None):
        with transaction(self.root):
            task_id = self._next_task_id(node_id, scope)
            uri = 'runtime/v6/production-proposals/'+task_id+'.json'
            path = self.runtime.path(uri)
            if path.exists():
                if read(path) != intent:
                    raise ValueError('A different review intent already exists for this frozen stage')
            else:
                self.runtime.write(uri, intent)
            existing = self.runtime.kernel.snapshot()['tasks'].get(task_id)
            if existing is not None:
                if (existing['envelope']['node_id'] != node_id or
                    not any(item['slot'] == 'production_intent' and item['sha256'] == digest_file(path)
                            for item in existing['envelope']['inputs'])):
                    raise ValueError('Existing review task differs from frozen intent')
                return {'status': 'PENDING_REVIEW' if existing['state'] != 'ACCEPTED' else 'ACCEPTED',
                        'task_id': task_id, 'node_id': node_id,
                        'action': self._pending(task_id)}
            envelope = self._create(node_id, scope, links=links,
                    inputs=[{'slot': 'production_intent', 'uri': uri,
                             'sha256': digest_file(path), 'version': 0}])
            self._transition(task_id, 'READY', 'DEPENDENCIES_SATISFIED')
            self._transition(task_id, 'DISPATCHING', 'DISPATCH_REQUESTED')
            return {'status': 'PENDING_REVIEW', 'task_id': task_id,
                    'node_id': node_id, 'action': self._pending(task_id)}

    def _pending(self, task_id):
        from .v6_codex_host import CodexHostBridge
        action = CodexHostBridge(self.runtime.kernel).pending(task_id)
        if action and action.get('tool') == 'collaboration.spawn_agent':
            action['arguments']['message'] += (
                '\nProduction review evidence contract: Copy the frozen production_intent '
                'JSON without changing it into the one expected candidate artifact. Independently '
                'inspect the current registered Take or output bytes and every frozen check. '
                'Write independent-review.json inside your candidate directory with exactly '
                '{"schema":"production-review/6.0","task_id":TASK_ID,"batch":BATCH,'
                '"reviewer_agent_id":YOUR_AGENT_ID,"decision_sha256":ARTIFACT_SHA256,'
                '"items":[{"id":GRAPH_CHECKER_ID,"status":"PASS",'
                '"evidence":[{"uri":PROJECT_RELATIVE_EVIDENCE,"sha256":SHA256}]}]}. '
                'Each checker item needs at least one separately inspectable evidence file. '
                'Reference independent-review.json in every candidate.checks[*].evidence. '
                'If a check fails, report a blocker; do not claim PASS.')
        return action

    def status(self):
        self.reconcile_execution_state()
        manifest = self.ledger._load('delivery-manifest.json') if self.ledger._path('delivery-manifest.json').is_file() else None
        snapshot = self.runtime.kernel.snapshot()
        actions = []
        for task_id, row in snapshot['tasks'].items():
            if row['envelope']['node_id'] in {'shot_acceptance', 'take_selection',
                    'adjacent_acceptance', 'whole_acceptance'} and row['state'] in ('DISPATCHING', 'UNKNOWN'):
                action = self._pending(task_id)
                if action:
                    actions.append(action)
        return {'jobs': self.ledger.jobs(), 'executions': self.ledger.records(),
                'takes': self.ledger.takes(), 'delivery_manifest': manifest,
                'blockers': self.ledger.video_delivery_blockers() if manifest else ['Delivery is not frozen'],
                'pending_actions': actions,
                'v6_tasks': {key: {'node_id': row['envelope']['node_id'], 'state': row['state']}
                             for key, row in snapshot['tasks'].items()}}

    def plan_job(self, request, compile_sha256, attachments, shot_ids, budget, *, compile_path):
        return self.ledger.plan_job(request, compile_sha256, attachments, shot_ids, budget,
                                    compile_path=compile_path)

    def freeze_delivery(self, shot_ids, plan, obligations, output_spec, *, shot_ranges):
        with transaction(self.root):
            manifest = self.ledger.freeze_delivery_manifest(shot_ids, plan, obligations,
                                                              output_spec, shot_ranges=shot_ranges)
            uri = 'runtime/production/delivery-manifest.json'
            plan_uri = 'runtime/production/acceptance-plans/'+plan['sha256']+'.json'
            envelope = self._create('video_freeze', self._project_scope(),
                    inputs=[{'slot': 'delivery_manifest', 'uri': uri,
                             'sha256': digest_file(self.runtime.path(uri)), 'version': 0},
                            {'slot': 'frozen_acceptance_plan', 'uri': plan_uri,
                             'sha256': digest_file(self.runtime.path(plan_uri)), 'version': 0}])
            values = {'FrozenRequest': {'manifest_sha256': manifest['sha256'],
                                        'job_ids': manifest['job_ids']},
                      'FrozenAcceptancePlan': plan}
            task = self._accept_system(envelope, values, [uri, plan_uri])
            return {**manifest, 'v6_task': task}

    def execute(self, job_id, out=None, transport=None):
        from .executors.agnes_api import AgnesApiExecutor
        from .executors.agnes_http import AgnesHttpTransport
        self._manifest()
        if job_id not in self._manifest()['job_ids']:
            raise ValueError('Execution job is outside frozen delivery')
        if out is None:
            raise ValueError('Output path is needed to recover the submitted media')
        result = AgnesApiExecutor(self.ledger, transport or AgnesHttpTransport()).execute(
                    job_id, out, on_started=self._prepare_execution)
        record_id = result.get('record_id')
        if record_id:
            record = self.ledger._load('executions/'+record_id+'.json')
            if record['state'] in ('SUBMITTED', 'SUCCEEDED'):
                self._execution_stage(record)
            elif record['state'] == 'UNKNOWN':
                self._mark_execution_unknown(record)
            elif record['state'] == 'FAILED':
                self._mark_execution_failed(record)
        if result.get('take'):
            self._take_stage(result['take'])
        return result

    def recover_execution(self, record_id, out=None, transport=None):
        from .executors.agnes_api import AgnesApiExecutor
        from .executors.agnes_http import AgnesHttpTransport
        self.reconcile_execution_state()
        record = self.ledger._load('executions/'+record_id+'.json')
        executor = AgnesApiExecutor(self.ledger, transport or AgnesHttpTransport())
        result = executor.finish(record_id, out) if record.get('task_id') and out else executor.recover(record_id)
        record = self.ledger._load('executions/'+record_id+'.json')
        if record['state'] in ('SUBMITTED', 'SUCCEEDED'):
            self._execution_stage(record)
        elif record['state'] == 'UNKNOWN':
            self._mark_execution_unknown(record)
        elif record['state'] == 'FAILED':
            self._mark_execution_failed(record)
        if result.get('take'):
            self._take_stage(result['take'])
        return result

    def reconcile_execution_state(self):
        """Replay ledger downgrades missed between the media and graph commits."""
        changed = []
        with transaction(self.root):
            for row in list(self.runtime.kernel.snapshot()['tasks'].values()):
                if row['envelope']['node_id'] != 'video_execution' or row['state'] != 'ACCEPTED':
                    continue
                candidate = row['candidate']
                if candidate is None:
                    raise ValueError('Accepted execution lacks its candidate')
                uri = candidate['host_record_uri']
                record_id = row['envelope']['scope']['ids'][0]
                if uri != 'runtime/production/executions/'+record_id+'.json':
                    raise ValueError('Accepted execution record URI differs from task scope')
                accepted_snapshot = next((item for item in candidate['artifacts']
                                          if item['kind'] == 'ExecutionRecord'), None)
                if accepted_snapshot is None:
                    raise ValueError('Accepted execution lacks its frozen record artifact')
                frozen = read(self.runtime.path(accepted_snapshot['uri']))
                if frozen.get('id') != record_id or type(frozen.get('version')) is not int:
                    raise ValueError('Accepted execution snapshot has invalid version')
                folder = self.ledger.root/'execution-events'/record_id
                downgrades = []
                for path in sorted(folder.glob('*.json')):
                    event = read(path)
                    if (type(event.get('version')) is int and event['version'] > frozen['version']
                            and event.get('to') in ('UNKNOWN', 'FAILED')):
                        downgrades.append(str(path.relative_to(self.root)))
                if not downgrades:
                    continue
                self._transition(row['envelope']['task_id'], 'STALE', 'HOST_RECORD_CHANGED',
                                 evidence=[uri, downgrades[0]])
                changed.append(row['envelope']['task_id'])
            if changed:
                self.runtime._stale_descendants()
        return {'status': 'RECONCILED', 'stale_task_ids': changed}

    def _mark_execution_unknown(self, record):
        self.reconcile_execution_state()
        uri = 'runtime/production/executions/'+record['id']+'.json'
        scope = self._scope('generation_request', record['id'])
        with transaction(self.root):
            task_id = self._current_task_id('video_execution', scope)
            rows = self.runtime.kernel.snapshot()['tasks']
            if task_id not in rows:
                self._create('video_execution', scope)
            state = self.runtime.kernel.snapshot()['tasks'][task_id]['state']
            if state == 'PENDING':
                self._transition(task_id, 'READY', 'DEPENDENCIES_SATISFIED')
                self._transition(task_id, 'DISPATCHING', 'DISPATCH_REQUESTED')
                state = 'DISPATCHING'
            if state in ('DISPATCHING', 'RUNNING'):
                self._transition(task_id, 'UNKNOWN', 'DISPATCH_UNCERTAIN', evidence=[uri],
                    error={'code': 'EXECUTION_UNCERTAIN', 'owner_node': 'video_execution',
                           'failed_check': None, 'evidence': [uri], 'retryable': False,
                           'recovery_action': 'RECONCILE'})

    def _mark_execution_failed(self, record):
        self.reconcile_execution_state()
        uri = 'runtime/production/executions/'+record['id']+'.json'
        task_id = self._current_task_id('video_execution',
                                self._scope('generation_request', record['id']))
        state = self.runtime.kernel.snapshot()['tasks'][task_id]['state']
        if state in ('DISPATCHING', 'RUNNING', 'UNKNOWN'):
            self._transition(task_id, 'FAILED', 'HOST_FAILED', evidence=[uri],
                error={'code': 'EXECUTION_FAILED', 'owner_node': 'video_execution',
                       'failed_check': 'execution_provenance', 'evidence': [uri],
                       'retryable': False, 'recovery_action': 'REVISE'})

    def receive_take(self, job_id, file_path, probe=None, execution_evidence=None):
        from .executors.manual import ManualExecutor
        self._manifest()
        if job_id not in self._manifest()['job_ids']:
            raise ValueError('Take job is outside frozen delivery')
        with transaction(self.root):
            result = ManualExecutor(self.ledger).receive(job_id, file_path, probe or {},
                                    execution_evidence=execution_evidence)
            if result.get('status') != 'SUCCEEDED':
                return result
            take = result['take']
            record = self.ledger._load('executions/'+take['record_id']+'.json')
            self._execution_stage(record)
            self._take_stage(take)
            return result

    def review_take(self, decision):
        normalized = self.ledger.normalize_acceptance(decision)
        if normalized['level'] != 'shot':
            raise ValueError('Shot review needs shot-level acceptance')
        shot = normalized['shot_id']
        take_id = normalized['take_ids'][shot]
        return self._queue_review('shot_acceptance', self._scope('shot', shot), normalized,
                                  links={'take_recovery': [self._scope('take', take_id)]})

    def select_take(self, shot_id, take_id):
        self.ledger.validate_selection(shot_id, take_id)
        take = self.ledger._load('takes/'+take_id+'.json')
        intent = {'shot_id': shot_id, 'take_id': take_id, 'take_sha256': take['sha256']}
        return self._queue_review('take_selection', self._scope('shot', shot_id), intent)

    def check_adjacent(self, decision):
        normalized = self.ledger.normalize_acceptance(decision)
        if normalized['level'] != 'adjacent':
            raise ValueError('Adjacent review needs adjacent-level acceptance')
        manifest = self._manifest()
        pairs = list(zip(manifest['shot_ids'], manifest['shot_ids'][1:]))
        pair = (normalized['left'], normalized['right'])
        if pair not in pairs:
            raise ValueError('Adjacent pair is outside frozen sequence')
        with transaction(self.root):
            uri = 'runtime/v6/production-adjacent/'+normalized['left']+'__'+normalized['right']+'.json'
            path = self.runtime.path(uri)
            if path.exists() and read(path) != normalized:
                raise ValueError('Adjacent review proposal differs from existing frozen pair')
            if not path.exists():
                self.runtime.write(uri, normalized)
            missing = [(left, right) for left, right in pairs if not self.runtime.path(
                'runtime/v6/production-adjacent/'+left+'__'+right+'.json').is_file()]
            if missing:
                return {'status': 'COLLECTING_ADJACENT', 'received': list(pair),
                        'remaining': [list(item) for item in missing]}
            return self._queue_adjacent_review(pairs)

    def _queue_adjacent_review(self, pairs):
        manifest = self._manifest()
        decisions = [read(self.runtime.path('runtime/v6/production-adjacent/'+left+'__'+right+'.json'))
                     for left, right in pairs]
        intent = {'manifest_sha256': manifest['sha256'], 'pairs': decisions,
                  'empty_pair_reason': 'EMPTY_PAIR_SET' if not pairs else None}
        return self._queue_review('adjacent_acceptance', self._project_scope(), intent)

    def post_obligation(self, obligation_id, evidence):
        return self.ledger.save_post_obligation(obligation_id, evidence)

    def assemble(self, edl, out, spec):
        from .assembly import assemble_ffmpeg, timelines, validate_edl
        manifest = self._manifest()
        if spec != manifest['output_spec']:
            raise ValueError('Assembly specification differs from frozen delivery specification')
        pairs = list(zip(manifest['shot_ids'], manifest['shot_ids'][1:]))
        rows = [row for row in self.runtime.kernel.snapshot()['tasks'].values()
                if row['envelope']['node_id'] == 'adjacent_acceptance' and row['state'] == 'ACCEPTED']
        if not rows:
            if not pairs:
                return self._queue_adjacent_review([])
            raise ValueError('Adjacent review task must be accepted before assembly')
        validate_edl(edl)
        result = assemble_ffmpeg(edl, out, spec)
        if result['status'] != 'CHECKED':
            return result
        clocks = timelines(spec.get('project', []), spec.get('media', []), spec.get('post', []))
        record = {'id': 'ASM_'+result['output_sha256'][:12], **clocks, 'edl': edl,
                  'tool': 'ffmpeg', 'status': result['status'], 'probe': result['probe'],
                  'output_sha256': result['output_sha256']}
        with transaction(self.root):
            saved = self.ledger.save_assembly(record, output_path=out)
            uri = 'runtime/production/assembly/'+saved['id']+'.json'
            self._host_task('assembly', self._project_scope(), uri,
                            {'AssemblyRecord': saved, 'FinalMedia': {
                                'output_uri': saved['output_uri'],
                                'output_sha256': saved['output_sha256']}})
        return {'status': 'CHECKED', 'assembly': saved, 'output': result}

    def review_sequence(self, decision):
        normalized = self.ledger.normalize_acceptance(decision)
        if normalized['level'] != 'sequence':
            raise ValueError('Whole review needs sequence-level acceptance')
        return self._queue_review('whole_acceptance', self._project_scope(), normalized)

    def validate_candidate(self, envelope, candidate):
        """Read-only production reviewer check called before V6 acceptance."""
        node_id = envelope['node_id']
        kinds = {'shot_acceptance': 'ShotDecision', 'take_selection': 'SelectedTake',
                 'adjacent_acceptance': 'AdjacentDecision', 'whole_acceptance': 'WholeDecision'}
        if node_id not in kinds:
            raise ValueError('No production reviewer validator for '+node_id)
        artifacts = [item for item in candidate['artifacts'] if item['kind'] == kinds[node_id]]
        if len(artifacts) != 1:
            raise ValueError('Production reviewer candidate must contain one decision artifact')
        artifact = artifacts[0]
        path = self.runtime.path(artifact['uri'])
        if digest_file(path) != artifact['sha256']:
            raise ValueError('Production reviewer decision bytes changed')
        review_uri = (f"runtime/v6/candidates/{envelope['task_id']}/{envelope['batch']}/"
                      'independent-review.json')
        review_path = self.runtime.path(review_uri)
        if not review_path.is_file() or any(review_uri not in item['evidence']
                                           for item in candidate['checks']):
            raise ValueError('Independent production review evidence is missing')
        review = read(review_path)
        if (not isinstance(review, dict) or set(review) != {'schema', 'task_id', 'batch',
                'reviewer_agent_id', 'decision_sha256', 'items'} or
            review['schema'] != 'production-review/6.0' or
            review['task_id'] != envelope['task_id'] or review['batch'] != envelope['batch'] or
            review['reviewer_agent_id'] != candidate['agent_id'] or
            review['decision_sha256'] != artifact['sha256'] or
            not isinstance(review['items'], list) or
            {item.get('id') for item in review['items']} != {item['id'] for item in envelope['validators']} or
            len(review['items']) != len(envelope['validators'])):
            raise ValueError('Independent production review does not bind every graph checker')
        for item in review['items']:
            if (set(item) != {'id', 'status', 'evidence'} or item['status'] != 'PASS' or
                not isinstance(item['evidence'], list) or not item['evidence']):
                raise ValueError('Independent production review item is incomplete')
            for proof in item['evidence']:
                if (not isinstance(proof, dict) or set(proof) != {'uri', 'sha256'} or
                    digest_file(self.runtime.path(proof['uri'])) != proof['sha256']):
                    raise ValueError('Independent production review evidence bytes changed')
        value = read(path)
        observed = {(proof['uri'], proof['sha256']) for item in review['items']
                    for proof in item['evidence']}
        intent = next((item for item in envelope['inputs'] if item['slot'] == 'production_intent'), None)
        if intent is None or digest_file(self.runtime.path(intent['uri'])) != intent['sha256'] or value != read(self.runtime.path(intent['uri'])):
            raise ValueError('Reviewer decision differs from frozen production intent')
        if node_id in ('shot_acceptance', 'whole_acceptance'):
            normalized = self.ledger.normalize_acceptance(value)
            if normalized != value or normalized['status'] != 'PASS':
                raise ValueError('Review is not a passing decision against current delivery')
        elif node_id == 'take_selection':
            if set(value) != {'shot_id', 'take_id', 'take_sha256'} or value['shot_id'] != envelope['scope']['ids'][0]:
                raise ValueError('Selected Take candidate has an invalid scope')
            take = self.ledger.validate_selection(value['shot_id'], value['take_id'])
            if value['take_sha256'] != take['sha256']:
                raise ValueError('Selected Take candidate differs from registered media')
        else:
            manifest = self._manifest()
            pairs = list(zip(manifest['shot_ids'], manifest['shot_ids'][1:]))
            if set(value) != {'manifest_sha256', 'pairs', 'empty_pair_reason'} or value['manifest_sha256'] != manifest['sha256'] or len(value['pairs']) != len(pairs):
                raise ValueError('Adjacent review does not bind exact frozen pair set')
            if value['empty_pair_reason'] != ('EMPTY_PAIR_SET' if not pairs else None):
                raise ValueError('Adjacent empty-set reason differs from actual sequence')
            for (left, right), decision in zip(pairs, value['pairs']):
                if decision.get('left') != left or decision.get('right') != right or decision.get('level') != 'adjacent':
                    raise ValueError('Adjacent review misses a frozen ordered pair')
                if self.ledger.normalize_acceptance(decision) != decision or decision['status'] != 'PASS':
                    raise ValueError('Adjacent decision does not pass its frozen checks')
        required_media = []
        if node_id == 'shot_acceptance':
            required_media = [value['take_ids'][value['shot_id']]]
        elif node_id == 'take_selection':
            required_media = [value['take_id']]
        elif node_id == 'adjacent_acceptance':
            required_media = list(dict.fromkeys(take for decision in value['pairs']
                            for take in decision['take_ids'].values()))
        for take_id in required_media:
            take = self.ledger._load('takes/'+take_id+'.json')
            if (take['uri'], take['sha256']) not in observed:
                raise ValueError('Independent review did not inspect the bound Take bytes')
        if node_id == 'whole_acceptance':
            assemblies = list((self.ledger.root/'assembly').glob('*.json'))
            if len(assemblies) != 1:
                raise ValueError('Whole review has no unique assembly')
            assembly = read(assemblies[0])
            if (assembly['output_uri'], assembly['output_sha256']) not in observed:
                raise ValueError('Whole review did not inspect final output bytes')
        return {'status': 'PASS', 'node_id': node_id, 'artifact_uri': artifact['uri'],
                'artifact_sha256': artifact['sha256']}

    def promote_candidate(self, envelope, candidate):
        """Promote only after validate_candidate, in the caller's transaction."""
        self.validate_candidate(envelope, candidate)
        artifact = candidate['artifacts'][0]
        value = read(self.runtime.path(artifact['uri']))
        node_id = envelope['node_id']
        if node_id in ('shot_acceptance', 'whole_acceptance'):
            return self.ledger.save_acceptance(value)
        if node_id == 'take_selection':
            return self.ledger.select_take(value['shot_id'], value['take_id'])
        if node_id == 'adjacent_acceptance':
            with transaction(self.root):
                return [self.ledger.save_acceptance(row) for row in value['pairs']]
        raise ValueError('No production reviewer promotion for '+node_id)

    def deliver(self):
        return self.ledger.mark_video_delivered()


def json_bytes(value):
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')
