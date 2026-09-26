"""Codex-hosted V6 orchestration over the existing pinned V5 content runtime.

The V5 kernel remains the native-IR validator and artifact importer.  This
gateway is the only supported mutating entry for projects marked protocol 6.0.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

from .transactions import transaction
from .v5 import V5Kernel
from .v5_adapters import digest as native_digest, storyboard_to_avir
from .v5_handoff import requirements as native_handoff_requirements, validate_handoff
from .v5_modules import ROOT, read, digest_file
from .v5_protocol import validate_protocol as validate_v5
from .v6_protocol import (compact_json, envelope_input_digest, envelope_digest,
                          candidate_digest, expected_dispatch_id, sha256_json,
                          validate_v6_protocol)
from .v6_runtime_fingerprint import (RUNTIME_CODE_FILES, runtime_code_hashes,
                                     runtime_resources_changed)
from .v6_graph import load_graph, stage_by_id, stage_applicability
from .v6_stage_adapter import graph_envelope_fields, predecessor_task_ids, slot_for


_TERMINAL = {'ACCEPTED', 'NOT_APPLICABLE', 'CANCELLED', 'STALE', 'FAILED', 'BLOCKED'}
_V5_TO_NODE = {
    'canon': 'canon', 'screenplay': 'screenplay', 'director': 'director',
    'art': 'art', 'storyboard': 'storyboard', 'control': 'control',
    'avir': 'compile', 'compile-review': 'compile_review', 'qa': 'preproduction_qa',
}


class V6CheckFailure(ValueError):
    def __init__(self, check_id: str, code: str, cause: Exception):
        self.failed_check = check_id
        self.code = code
        super().__init__(str(cause))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


class V6Runtime:
    def __init__(self, project: str | Path, *, skill_root: Path = ROOT):
        self.root = Path(project).expanduser().resolve()
        self.skill_root = Path(skill_root).resolve()
        self.v5 = V5Kernel(self.root, self.skill_root)
        if self.v5.project.get('orchestration_protocol') != '6.0':
            raise ValueError('Project does not use V6 orchestration; use the V5 entry')
        self.v5._v6_gateway = True
        from .v6_kernel import V6TaskKernel
        self.kernel = V6TaskKernel(self.root, schema_root=self.skill_root)
        self.graph = load_graph(module_lock=read(self.root/'modules.lock.json'))

    @property
    def project(self) -> dict:
        return self.v5.project

    def path(self, relative: str) -> Path:
        return self.v5.path(relative)

    def write(self, relative: str, value: object) -> str:
        return self.v5.write(relative, value)

    def _runtime_code_resources(self, node_id: str) -> list[dict]:
        if node_id not in ('control', 'compile', 'compile_review'):
            return []
        source_root = Path(getattr(self, '_runtime_code_root', Path(__file__).resolve().parent))
        hashes = runtime_code_hashes(source_root)
        resources = []
        for name in RUNTIME_CODE_FILES:
            checksum = hashes[name]
            uri = f'runtime/v6/runtime-resources/{checksum}/{name}'
            path = self.path(uri)
            if path.is_file():
                if digest_file(path) != checksum:
                    raise ValueError('Content-addressed runtime resource changed: '+uri)
            else:
                self.write(uri, (source_root/name).read_bytes())
            resources.append({'uri': uri, 'sha256': checksum})
        return resources

    def _runtime_code_changed(self, envelope: dict) -> bool:
        return runtime_resources_changed(
            envelope['node_id'], envelope['resources'],
            Path(getattr(self, '_runtime_code_root', Path(__file__).resolve().parent)))

    def _archive_project_evidence(self) -> str:
        """Keep exact project-manifest bytes before an authorized native mutation."""
        source = self.root/'project.json'
        raw = source.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        relative = f'runtime/v6/evidence/project-json/{checksum}.json'
        target = self.path(relative)
        if target.is_file():
            if digest_file(target) != checksum:
                raise ValueError('Archived project evidence path has different bytes')
        else:
            self.write(relative, raw)
        return relative

    def production_target(self) -> str:
        return self.v5.production_target()

    @classmethod
    def initialize(cls, project: str | Path, inputs: list[str], **kwargs) -> 'V6Runtime':
        skill_root = Path(kwargs.get('skill_root', ROOT)).resolve()
        kernel = V5Kernel.initialize(project, inputs, **kwargs)
        kernel.project['orchestration_protocol'] = '6.0'
        kernel.project['execution_mode'] = 'codex-agents'
        validate_v5('project', kernel.project, skill_root)
        with transaction(kernel.root):
            kernel.write('project.json', kernel.project)
        return cls(kernel.root, skill_root=skill_root)

    @classmethod
    def migrate(cls, source: str | Path, destination: str | Path,
                *, skill_root: Path = ROOT) -> 'V6Runtime':
        old = Path(source).expanduser().resolve()
        if read(old/'project.json').get('orchestration_protocol') == '6.0':
            raise ValueError('Source already uses V6; copy it without rewriting its audit history')
        copied = V5Kernel.copy_project(old, destination, skill_root=skill_root)
        copied.project['orchestration_protocol'] = '6.0'
        copied.project['execution_mode'] = 'codex-agents'
        validate_v5('project', copied.project, skill_root)
        with transaction(copied.root):
            copied.write('project.json', copied.project)
        return cls(copied.root, skill_root=skill_root)

    def _task_record(self, task_id: str) -> tuple[dict, dict]:
        snapshot = self.kernel.snapshot()
        try:
            return snapshot, snapshot['tasks'][task_id]
        except KeyError as exc:
            raise ValueError('Unknown V6 task: ' + task_id) from exc

    def _replayed_submission(self, command_id: str, task_id: str, expected_revision: int, *,
                             reason: str, field: str | None = None,
                             value: dict | None = None,
                             failure_reason: str | None = None) -> dict | None:
        """Recognize a committed host command before checking its old revision.

        The journal stores the original payload, so an ID reused with changed
        content cannot be mistaken for a harmless retry after a lost response.
        """
        snapshot = self.kernel.snapshot()
        events_path = self.root/'runtime/v6/events.json'
        if not events_path.is_file():
            return None
        for item in read(events_path):
            payload = item['payload']
            event = payload.get('event') if isinstance(payload, dict) else None
            if not isinstance(event, dict):
                continue
            if failure_reason is not None and event.get('command_id') == command_id+'-failed':
                if (event.get('task_id') != task_id or event.get('reason') != failure_reason
                        or event.get('expected_revision') != expected_revision):
                    raise ValueError('Command ID was already used with different content')
                evidence = event.get('evidence') or []
                details = read(self.path(evidence[0])) if evidence else {}
                if details.get('submission_digest') != _hash(value):
                    raise ValueError('Command ID was already used with different content')
                return {'status': 'ALREADY_RECORDED', 'task_id': task_id,
                        'state': snapshot['tasks'][task_id]['state'],
                        'recovery_action': event['error']['recovery_action'],
                        'revision': snapshot['revision']}
            if event.get('command_id') != command_id:
                continue
            if (event.get('task_id') != task_id or event.get('reason') != reason
                    or event.get('expected_revision') != expected_revision
                    or (field is not None and payload.get(field) != value)):
                raise ValueError('Command ID was already used with different content')
            return {'status': 'ALREADY_RECORDED', 'task_id': task_id,
                    'state': snapshot['tasks'][task_id]['state'],
                    'revision': snapshot['revision']}
        return None

    def _event(self, record: dict, to_state: str, reason: str, *, command_id: str,
               checks: list[dict] | None = None, evidence: list[str] | None = None,
               actor_kind: str = 'kernel', actor_id: str = 'v6-runtime',
               affected_outputs: list[str] | None = None) -> dict:
        snapshot = self.kernel.snapshot()
        envelope = record['envelope']
        return {'schema': 'state-event/6.0', 'command_id': command_id,
                'expected_revision': snapshot['revision'], 'task_id': envelope['task_id'],
                'batch': envelope['batch'], 'object_version': record['version'],
                'from_state': record['state'], 'to_state': to_state, 'reason': reason,
                'check_results': checks or [], 'evidence': evidence or [],
                'affected_outputs': affected_outputs or [], 'actor_kind': actor_kind,
                'actor_id': actor_id, 'at': _utc()}

    def _node(self, task: dict) -> str:
        if task['kind'] in ('image', 'image-prompt'):
            return ('visual_' if task['stage'] == 5 else 'board_') + ('media' if task['kind'] == 'image' else 'prompts')
        return _V5_TO_NODE[task['kind']]

    @staticmethod
    def _project_scope() -> dict:
        return {'kind': 'project', 'ids': []}

    def _scope_for_task(self, task: dict) -> dict:
        node = stage_by_id(self.graph, self._node(task))
        kind = node['scope']
        if kind == 'project':
            return self._project_scope()
        if kind == 'scene':
            ids = list((task.get('scope') or {}).get('scene_ids') or [])
        elif kind in ('asset', 'panel'):
            ids = [task['slot']]
        else:
            raise ValueError('V5 task cannot infer graph scope: '+kind)
        if len(ids) != 1:
            raise ValueError('V5 task scope must identify exactly one '+kind)
        return {'kind': kind, 'ids': ids}

    def _scopes(self, node_id: str) -> list[dict]:
        node = stage_by_id(self.graph, node_id)
        if node['scope'] == 'project':
            return [self._project_scope()]
        if node_id == 'art':
            if not self.v5.valid('director'):
                raise ValueError('DirectorIR is required before expanding art scenes')
            return [{'kind': 'scene', 'ids': [item['id']]} for item in self.v5.data('director')['scenes']]
        if node_id in ('visual_prompts', 'visual_media'):
            jobs = self.v5.image_jobs(5)
            if not jobs:
                return [{'kind': 'asset', 'ids': ['ALL']}]
            return [{'kind': 'asset', 'ids': [item['key']]} for item in jobs]
        if node_id in ('board_prompts', 'board_media'):
            jobs = self.v5.image_jobs(7)
            if not jobs:
                return [{'kind': 'panel', 'ids': ['ALL']}]
            return [{'kind': 'panel', 'ids': [item['key']]} for item in jobs]
        if self.production_target() != 'video':
            return [{'kind': node['scope'], 'ids': ['NO_VIDEO']}]
        raise ValueError('Production stage scope requires a frozen production catalogue: '+node_id)

    def _scope_catalogue(self, node_id: str) -> dict[str, list[dict]]:
        node = stage_by_id(self.graph, node_id)
        return {name: self._scopes(name) for name in [node_id, *node['depends_on']]}

    def _scope_links(self, node_id: str, scope: dict) -> dict[str, list[dict]]:
        if node_id == 'visual_prompts':
            key = scope['ids'][0]
            if key == 'ALL':
                return {'art': self._scopes('art')}
            job = next(item for item in self.v5.image_jobs(5) if item['key'] == key)
            scenes = list(dict.fromkeys(dep['slot'][4:] for dep in job['dependencies']
                                        if dep['slot'].startswith('art:')))
            if not scenes:
                raise ValueError('Visual asset must bind at least one ArtIR scene')
            return {'art': [{'kind': 'scene', 'ids': [scene]} for scene in scenes]}
        if node_id in ('board_prompts', 'board_media'):
            dependency = 'visual_prompts' if node_id == 'board_prompts' else 'visual_media'
            # The asset set is frozen by the upstream ArtIR image-job catalogue.
            return {dependency: self._scopes(dependency)}
        if self.production_target() != 'video':
            if node_id == 'take_recovery':
                return {'video_execution': self._scopes('video_execution')}
            if node_id == 'shot_acceptance':
                return {'take_recovery': self._scopes('take_recovery')}
        return {}

    def _materialize_skips_before(self, target_node_id: str) -> None:
        context = self.kernel._applicability_context()
        for node in self.graph['nodes']:
            if node['id'] == target_node_id:
                return
            if node['applicability']['kind'] == 'always':
                continue
            applicability = stage_applicability(node, context, evidence_ref='project.json')
            if applicability['status'] != 'NOT_APPLICABLE':
                continue
            evidence = ['project.json']
            if (applicability['reason_code'] == 'NO_APPLICABLE_ASSETS'
                    and node['id'] in ('visual_prompts', 'visual_media',
                                       'board_prompts', 'board_media')):
                if node['id'].startswith('visual_'):
                    evidence.extend(item['uri'] for slot, item in self.v5.state['artifacts'].items()
                                    if slot.startswith('art:') and self.v5.valid(slot))
                else:
                    evidence.append(self.v5.state['artifacts']['storyboard']['uri'])
            for scope in self._scopes(node['id']):
                if any(row['envelope']['scope'] == scope and row['state'] == 'NOT_APPLICABLE'
                       for row in self._stage_rows(node['id'])):
                    continue
                task_id = self._skip_task_id(node['id'], scope, context)
                envelope = self.create_graph_task(node['id'], scope, task_id)
                record = self.kernel.snapshot()['tasks'][envelope['task_id']]
                self.kernel.transition(self._event(record, 'NOT_APPLICABLE', applicability['reason_code'],
                                                   command_id='skip-'+task_id,
                                                   evidence=evidence,
                                                   affected_outputs=applicability['affected_outputs']))

    def _skip_task_id(self, node_id: str, scope: dict, context: dict) -> str:
        snapshot = self.kernel.snapshot()
        predecessors = predecessor_task_ids(self.graph, node_id, scope, snapshot['tasks'],
                                             self._scope_catalogue(node_id),
                                             self._scope_links(node_id, scope))
        return 'V6_skip_'+_hash({'node': node_id, 'scope': scope, 'context': context,
                                'predecessors': [(task_id, snapshot['tasks'][task_id]['version'])
                                                 for task_id in predecessors],
                                'project_sha256': digest_file(self.root/'project.json'),
                                'modules': digest_file(self.root/'modules.lock.json')})[:24]

    def _handoffs(self, node_id: str, scope: dict, predecessor_ids: list[str]) -> list[dict]:
        node = stage_by_id(self.graph, node_id)
        if not node['handoff_required']:
            return []
        rows = self.kernel.snapshot()['tasks']
        target_slot = slot_for(node_id, scope, node['output_types'][0])
        bindings = []
        for predecessor in predecessor_ids:
            row = rows[predecessor]
            if row['state'] == 'NOT_APPLICABLE':
                continue
            for item in row['envelope']['expected_artifacts']:
                bindings.append({'requirement_id': 'UP_'+_hash({'source': predecessor,
                    'slot': item['slot'], 'target': target_slot})[:24],
                    'source_slot': item['slot'], 'source_version': row['version'],
                    'target_slot': target_slot, 'target_pointer': '', 'channel': 'artifact'})
        if not bindings:
            raise ValueError('Specialist stage needs an accepted source artifact for handoff')
        return bindings

    def create_graph_task(self, node_id: str, scope: dict, task_id: str, *, batch: int = 1,
                          required_scopes: dict | None = None, scope_links: dict | None = None,
                          frozen_task: dict | None = None, extra_inputs: list[dict] | None = None,
                          handoff_bindings: list[dict] | None = None) -> dict:
        """Create one evidence-bound task from graph metadata and frozen predecessor scopes."""
        node = stage_by_id(self.graph, node_id)
        catalogue = required_scopes or self._scope_catalogue(node_id)
        links = scope_links if scope_links is not None else self._scope_links(node_id, scope)
        snapshot = self.kernel.snapshot()
        predecessor_ids = predecessor_task_ids(self.graph, node_id, scope, snapshot['tasks'], catalogue, links)
        bindings = handoff_bindings if handoff_bindings is not None else self._handoffs(node_id, scope, predecessor_ids)
        fields = graph_envelope_fields(self.graph, node_id, scope, task_id, batch,
                                       snapshot['tasks'], catalogue, links, bindings)
        inputs = []
        for predecessor in predecessor_ids:
            row = snapshot['tasks'][predecessor]
            if row['state'] == 'NOT_APPLICABLE':
                continue
            for artifact in row['envelope']['expected_artifacts']:
                registered = snapshot['artifacts'].get(artifact['slot'])
                if not registered or registered['task_id'] != predecessor:
                    raise ValueError('Accepted predecessor output is absent from artifact index')
                inputs.append({'slot': artifact['slot'], 'uri': registered['uri'],
                               'sha256': registered['sha256'], 'version': row['version']})
        if frozen_task is not None:
            task_file = self.root/'runtime/tasks'/(frozen_task['task_id']+'.json')
            inputs.append({'slot': 'frozen_task', 'uri': str(task_file.relative_to(self.root)),
                           'sha256': digest_file(task_file), 'version': 0})
        migration = self.root/'imports/migration.json'
        if migration.is_file():
            inputs.append({'slot': 'migration_report', 'uri': 'imports/migration.json',
                           'sha256': digest_file(migration), 'version': 0})
        inputs.extend(extra_inputs or [])
        if len({item['slot'] for item in inputs}) != len(inputs):
            raise ValueError('Graph envelope inputs have duplicate slots')
        module = None
        resources = []
        if node['locked_skill']:
            lock = read(self.root/'modules.lock.json')['modules'][node['locked_skill']]
            module = {'name': node['locked_skill'], 'version': lock['version'], 'sha256': lock['sha256']}
            task_module = (frozen_task or {}).get('module') or {}
            reads = (task_module.get('required_reads') or []) if task_module.get('name') == node['locked_skill'] else self.v5.required_reads(node['locked_skill'], kind=node_id)
            resources = [{'uri': str(Path(item['path']).resolve().relative_to(self.root)),
                          'sha256': item['sha256']} for item in reads]
            required_scripts = ({'reference_observation': ['scripts/observe_video.py'],
                                 'compile': ['scripts/vpc.py', 'scripts/vpc_core.py']}
                                .get(node_id, []))
            for relative in required_scripts:
                path = self.v5.modules(node['locked_skill'])/relative
                if not path.is_file():
                    raise ValueError('Locked Skill lacks a required execution script: '+relative)
                resource = {'uri': str(path.relative_to(self.root)), 'sha256': digest_file(path)}
                if resource not in resources:
                    resources.append(resource)
        resources.extend(self._runtime_code_resources(node_id))
        envelope = {'schema': 'task-envelope/6.0', 'project_id': self.project['project_id'],
                    'node_id': node_id, 'task_id': task_id, 'batch': batch,
                    **fields, 'input_revision': snapshot['revision'], 'inputs': inputs,
                    'input_digest': '', 'module': module, 'resources': resources}
        envelope['input_digest'] = envelope_input_digest(envelope)
        self.kernel.create_task(envelope, command_id='create-'+task_id+'-'+str(batch),
                                expected_revision=snapshot['revision'])
        return envelope

    def _envelope(self, task: dict, *, extra_inputs: list[dict] | None = None) -> dict:
        node_id = self._node(task)
        previous = self.kernel.snapshot()['tasks'].get(task['task_id'])
        if previous is not None and previous['state'] not in ('FAILED', 'BLOCKED', 'STALE'):
            raise ValueError('V6 task already exists and is not retryable: '+task['task_id'])
        batch = (previous['envelope']['batch'] + 1) if previous else 1
        return self.create_graph_task(node_id, self._scope_for_task(task), task['task_id'],
                                      batch=batch, frozen_task=task,
                                      extra_inputs=extra_inputs)

    def _ancestor_nodes(self, node_id: str) -> set[str]:
        nodes = {item['id']: item for item in self.graph['nodes']}
        if node_id not in nodes:
            raise ValueError('Unknown graph node: '+node_id)
        found: set[str] = set()
        pending = list(nodes[node_id]['depends_on'])
        while pending:
            current = pending.pop()
            if current in found:
                continue
            found.add(current)
            pending.extend(nodes[current]['depends_on'])
        return found

    def _task_dependency_closure(self, task_id: str) -> set[str]:
        rows = self.kernel.snapshot()['tasks']
        found: set[str] = set()
        pending = [task_id]
        while pending:
            current = pending.pop()
            if current in found:
                continue
            found.add(current)
            row = rows.get(current)
            if row is not None:
                pending.extend(item['task_id'] for item in row['envelope']['dependencies'])
        found.discard(task_id)
        return found

    def _revise_review_owner(self, node_id: str, row: dict) -> None:
        """Invalidate precisely the V5-owned source instance named by review."""
        scope = row['envelope']['scope']
        if node_id == 'art':
            if scope['kind'] != 'scene' or len(scope['ids']) != 1:
                raise ValueError('Art upstream repair requires one frozen scene scope')
            self.v5.revise('art', scene_id=scope['ids'][0])
        elif node_id in ('canon', 'screenplay', 'director', 'storyboard'):
            self.v5.revise(node_id)
        elif node_id == 'control':
            state = self.v5.state
            control = state.get('control') or {}
            if control.get('status') != 'READY':
                raise ValueError('Control upstream repair has no accepted native control package')
            control['status'] = 'INVALIDATED'
            state['control'] = control
            state.update(active_task=None, build=None, status='RUNNING')
            self.v5.save(state)
        elif node_id in ('visual_prompts', 'board_prompts'):
            native_path = self.path('runtime/tasks/'+row['envelope']['task_id']+'.json')
            native = read(native_path)
            if native.get('kind') != 'image-prompt':
                raise ValueError('Image prompt owner task is not bound to a native image-prompt task')
            state = self.v5.state
            state['prompts'].pop(native['slot'], None)
            state.update(active_task=None, build=None, status='RUNNING')
            self.v5.save(state)
        else:
            raise ValueError('Review owner has no supported native revision route: '+node_id)

    def _route_upstream_review_failure(self, row: dict) -> dict | None:
        """Return a review failure to its verified upstream specialist exactly once."""
        if row['state'] != 'FAILED' or row.get('review_dispatch') is None:
            return None
        source = row['envelope']
        event_rows = read(self.path('runtime/v6/events.json'))
        event = next((item['payload']['event'] for item in reversed(event_rows)
                      if (item.get('payload') or {}).get('event', {}).get('task_id') == source['task_id']
                      and item['payload']['event'].get('batch') == source['batch']
                      and item['payload']['event'].get('to_state') == 'FAILED'
                      and item['payload']['event'].get('reason') == 'REVIEW_FAILED'), None)
        if event is None:
            return None
        if len(event.get('evidence', [])) != 1:
            raise ValueError('Review failure event must bind one immutable failure record')
        failure_uri = event['evidence'][0]
        failure_path = self.path(failure_uri)
        failure = read(failure_path)
        owner = failure.get('reviewer_failure_owner')
        source_node = source['node_id']
        if owner in (None, source_node):
            return None
        ancestors = self._ancestor_nodes(source_node)
        node_specs = {item['id']: item for item in self.graph['nodes']}
        if owner not in ancestors or node_specs.get(owner, {}).get('executor_kind') != 'specialist':
            return {'status': 'REPAIR_REQUIRED', 'task_id': source['task_id'],
                    'node_id': source_node, 'failure_evidence': failure_uri,
                    'reason': 'Reviewer named a non-ancestor or non-specialist owner'}
        frozen_candidate_digest = (failure.get('candidate_digest') or
                                   candidate_digest(row.get('candidate') or {}))
        route_key = {'source_task_id': source['task_id'], 'source_batch': source['batch'],
                     'owner_node_id': owner, 'candidate_digest': frozen_candidate_digest}
        route_id = 'UPR_'+sha256_json(route_key)[:24]
        route_uri = f'runtime/v6/upstream-repair/{route_id}.json'
        if self.path(route_uri).is_file():
            return None

        review_uri = failure.get('review_record_uri')
        review_sha = failure.get('review_record_sha256')
        if not review_uri or not review_sha:
            # Early V6 rehearsals kept the exact review as a RESULT message
            # and hash-bound file but did not copy it into the failure record.
            # Recover only that original message; never synthesize a review.
            recorded = [message for message in row.get('messages', [])
                        if message.get('type') == 'RESULT'
                        and message.get('sender_id') == row['review_dispatch']['agent_id']
                        and message.get('subject_uri')
                        and '/reviews/' in message['subject_uri']]
            if len(recorded) == 1:
                review_uri = recorded[0]['subject_uri']
                review_sha = recorded[0]['subject_sha256']
        if not review_uri or not review_sha or not self.path(review_uri).is_file():
            return {'status': 'REPAIR_REQUIRED', 'task_id': source['task_id'],
                    'node_id': source_node, 'failure_evidence': failure_uri,
                    'reason': 'Independent review record is not durably bound'}
        review_path = self.path(review_uri)
        if digest_file(review_path) != review_sha:
            raise ValueError('Independent review bytes changed before upstream routing')
        review = read(review_path)
        if (review.get('task_id') != source['task_id'] or review.get('batch') != source['batch']
                or review.get('candidate_digest') != frozen_candidate_digest
                or _hash(review) != failure.get('submission_digest')
                or review.get('failure_owner') != owner
                or review.get('reviewer_agent_id') != row['review_dispatch']['agent_id']
                or review.get('reviewer_dispatch_id') != row['review_dispatch']['dispatch_id']
                or review.get('reviewer_agent_id') == (row.get('receipt') or {}).get('agent_id')):
            raise ValueError('Independent review identity or source candidate changed before routing')
        failed_checks = [{'id': item['id'], 'evidence': item['evidence']}
                         for item in review['checks'] if item['status'] == 'FAIL']
        if not failed_checks:
            raise ValueError('Upstream review route has no failed checks')
        for check in failed_checks:
            for uri in check['evidence']:
                path = self.path(uri)
                if not path.is_file():
                    raise ValueError('Review check evidence disappeared: '+uri)

        closure = self._task_dependency_closure(source['task_id'])
        owner_tasks = [item for task_id, item in self.kernel.snapshot()['tasks'].items()
                       if task_id in closure and item['envelope']['node_id'] == owner
                       and item['state'] == 'ACCEPTED']
        if len(owner_tasks) != 1:
            return {'status': 'REPAIR_REQUIRED', 'task_id': source['task_id'],
                    'node_id': source_node, 'failure_evidence': failure_uri,
                    'reason': 'Review owner does not resolve to exactly one accepted upstream task',
                    'owner_task_candidates': [item['envelope']['task_id'] for item in owner_tasks]}
        owner_row = owner_tasks[0]
        try:
            with transaction(self.root):
                self._revise_review_owner(owner, owner_row)
                # Stale the reviewed owner and its accepted descendants before asking
                # the native V5 scheduler for a new task.
                self._stale_changed_inputs()
                native_result = self.v5.run()
                native_task = native_result.get('task')
                if native_task is None or self._node(native_task) != owner:
                    raise ValueError('Native scheduler did not return the assigned review owner')
                brief = {'schema': 'upstream-repair-brief/6.0', 'route_id': route_id,
                         'project_id': self.project['project_id'],
                         'source_task_id': source['task_id'], 'source_batch': source['batch'],
                         'source_node_id': source_node,
                         'candidate_digest': frozen_candidate_digest,
                         'owner_node_id': owner, 'owner_task_id': native_task['task_id'],
                         'review': {'uri': review_uri, 'sha256': review_sha,
                                    'reviewer_agent_id': review['reviewer_agent_id'],
                                    'reviewer_dispatch_id': review['reviewer_dispatch_id']},
                         'failed_checks': failed_checks,
                         'instruction': 'Resolve every failed review check against its evidence in this new owner task. Preserve the frozen unaffected inputs, state the correction and its target fields in the candidate, and return unresolved if the check cannot be corrected from the supplied source.'}
                validate_v6_protocol('upstream-repair-brief', brief, self.skill_root)
                self.write(route_uri, brief)
                extra = [{'slot': 'upstream_repair', 'uri': route_uri,
                          'sha256': digest_file(self.path(route_uri)), 'version': source['batch']}]
                envelope = self._envelope(native_task, extra_inputs=extra)
                record = self.kernel.snapshot()['tasks'][native_task['task_id']]
                self.kernel.transition(self._event(record, 'READY', 'DEPENDENCIES_SATISFIED',
                                                   command_id='ready-'+native_task['task_id']+'-'+str(envelope['batch']),
                                                   evidence=[route_uri]))
                record = self.kernel.snapshot()['tasks'][native_task['task_id']]
                self.kernel.transition(self._event(record, 'DISPATCHING', 'DISPATCH_REQUESTED',
                                                   command_id='dispatch-'+native_task['task_id']+'-'+str(envelope['batch']),
                                                   evidence=[route_uri]))
        except (ValueError, OSError) as error:
            return {'status': 'REPAIR_REQUIRED', 'task_id': source['task_id'],
                    'node_id': source_node, 'failure_evidence': failure_uri,
                    'reason': str(error), 'revision': self.kernel.snapshot()['revision']}
        return self.run()

    def _active(self) -> list[dict]:
        return [row for row in self.kernel.snapshot()['tasks'].values() if row['state'] not in _TERMINAL]

    def _stage_rows(self, node_id: str) -> list[dict]:
        return [row for row in self.kernel.snapshot()['tasks'].values()
                if row['envelope']['node_id'] == node_id and row['state'] != 'STALE']

    def _reconcile_native_active_task(self, node_id: str, active: list[dict]) -> None:
        """Move V5's serial pointer off a V6 task that has formally failed."""
        state = self.v5.state
        native_active = state.get('active_task')
        active_ids = {row['envelope']['task_id'] for row in active}
        if native_active is None or native_active in active_ids:
            return
        rows = self.kernel.snapshot()['tasks']
        failed = rows.get(native_active)
        if (failed is None or failed['state'] not in ('FAILED', 'BLOCKED', 'STALE', 'CANCELLED')
                or failed['envelope']['node_id'] != node_id or len(active) != 1):
            raise ValueError('Native active task is outside the frozen V6 '+node_id+' task set')
        next_row = active[0]
        native_path = self.path('runtime/tasks/'+next_row['envelope']['task_id']+'.json')
        if not native_path.is_file():
            raise ValueError('Active V6 task has no frozen native task')
        native = read(native_path)
        if native['task_id'] != next_row['envelope']['task_id'] or self._node(native) != node_id:
            raise ValueError('Active V6 task does not match native recovery scope')
        state['active_task'] = native['task_id']
        state['active_task_sha256'] = native_digest(native)
        state['status'] = 'AWAITING_CURRENT_AGENT'
        with transaction(self.root):
            self.v5.save(state)

    def _queue_parallel_art(self) -> None:
        """Freeze one more independent scene while another ArtIR task is live."""
        active = self._active()
        if (not active or any(row['envelope']['node_id'] != 'art' for row in active)
                or len(active) >= 2 or not self.v5.valid('director')):
            return
        self._reconcile_native_active_task('art', active)
        scopes = self._scopes('art')
        if len(scopes) < 2:
            return
        existing = {tuple(row['envelope']['scope']['ids'])
                    for row in self._stage_rows('art')}
        for scope in scopes:
            if tuple(scope['ids']) in existing or self.v5.valid('art:'+scope['ids'][0]):
                continue
            # Exact graph predecessors are checked before touching the V5
            # single-task pointer. Every mutation then shares one transaction.
            predecessor_task_ids(self.graph, 'art', scope,
                                 self.kernel.snapshot()['tasks'],
                                 self._scope_catalogue('art'))
            with transaction(self.root):
                scene_id = scope['ids'][0]
                native = self.v5.task('art', 'art:'+scene_id, 4,
                                      'production-design-grammar',
                                      self.v5.role_dependencies('art',
                                                                {'scene_ids': [scene_id]}),
                                      {'scene_ids': [scene_id]})['task']
                envelope = self._envelope(native)
                row = self.kernel.snapshot()['tasks'][native['task_id']]
                self.kernel.transition(self._event(row, 'READY', 'DEPENDENCIES_SATISFIED',
                                                   command_id='ready-'+native['task_id']+'-'+str(envelope['batch']),
                                                   evidence=[f'runtime/tasks/{native["task_id"]}.json']))
                row = self.kernel.snapshot()['tasks'][native['task_id']]
                self.kernel.transition(self._event(row, 'DISPATCHING', 'DISPATCH_REQUESTED',
                                                   command_id='dispatch-'+native['task_id']+'-'+str(envelope['batch']),
                                                   evidence=[f'runtime/tasks/{native["task_id"]}.json']))
            return

    def _queue_parallel_prompts(self) -> None:
        """Freeze one more independent image prompt while a peer is live."""
        active = self._active()
        if not active or len(active) >= 2:
            return
        nodes = {row['envelope']['node_id'] for row in active}
        if len(nodes) != 1 or not nodes <= {'visual_prompts', 'board_prompts'}:
            return
        node_id = next(iter(nodes))
        self._reconcile_native_active_task(node_id, active)
        stage = 5 if node_id == 'visual_prompts' else 7
        jobs = self.v5.image_jobs(stage)
        if len(jobs) < 2:
            return
        existing = {tuple(row['envelope']['scope']['ids'])
                    for row in self._stage_rows(node_id)}
        state = self.v5.state
        for job in jobs:
            scope = {'kind': 'asset' if stage == 5 else 'panel', 'ids': [job['key']]}
            prompt = state['prompts'].get(job['key'])
            if (tuple(scope['ids']) in existing or
                    prompt and prompt['input_fingerprint'] == job['fingerprint']
                    and self.v5.prompt_valid(prompt)):
                continue
            predecessor_task_ids(self.graph, node_id, scope,
                                 self.kernel.snapshot()['tasks'],
                                 self._scope_catalogue(node_id),
                                 self._scope_links(node_id, scope))
            with transaction(self.root):
                native = self.v5.task('image-prompt', job['key'], stage,
                                      'image-prompt-optimizer', job['dependencies'],
                                      extra={'job': job})['task']
                envelope = self._envelope(native)
                row = self.kernel.snapshot()['tasks'][native['task_id']]
                self.kernel.transition(self._event(row, 'READY', 'DEPENDENCIES_SATISFIED',
                                                   command_id='ready-'+native['task_id']+'-'+str(envelope['batch']),
                                                   evidence=[f'runtime/tasks/{native["task_id"]}.json']))
                row = self.kernel.snapshot()['tasks'][native['task_id']]
                self.kernel.transition(self._event(row, 'DISPATCHING', 'DISPATCH_REQUESTED',
                                                   command_id='dispatch-'+native['task_id']+'-'+str(envelope['batch']),
                                                   evidence=[f'runtime/tasks/{native["task_id"]}.json']))
            return

    def _restore_parallel_native_task(self, record: dict) -> None:
        """Select the reviewed frozen task for one serial V5 promotion."""
        node_id = record['envelope']['node_id']
        if node_id not in ('art', 'visual_prompts', 'board_prompts'):
            return
        task_id = record['envelope']['task_id']
        frozen = next((item for item in record['envelope']['inputs']
                       if item['slot'] == 'frozen_task'), None)
        if frozen is None or frozen['uri'] != f'runtime/tasks/{task_id}.json':
            raise ValueError('Parallel task has no matching frozen native envelope')
        path = self.path(frozen['uri'])
        if digest_file(path) != frozen['sha256']:
            raise ValueError('Frozen parallel task bytes changed before promotion')
        task = read(path)
        scope_id = record['envelope']['scope']['ids'][0]
        matching = (task['kind'] == 'art' and task['scope'].get('scene_ids') == [scope_id]
                    if node_id == 'art' else
                    task['kind'] == 'image-prompt' and task['slot'] == scope_id
                    and task['stage'] == (5 if node_id == 'visual_prompts' else 7))
        if task['task_id'] != task_id or not matching:
            raise ValueError('Frozen native task differs from reviewed V6 scope')
        live_peers = {row['envelope']['task_id'] for row in self._active()
                      if row['envelope']['node_id'] == node_id}
        state = self.v5.state
        if state.get('active_task') not in (None, *live_peers):
            raise ValueError('Cannot replace an unrelated native active task')
        state['active_task'] = task_id
        state['active_task_sha256'] = native_digest(task)
        state['status'] = 'AWAITING_CURRENT_AGENT'
        self.v5.save(state)

    def _ensure_sources(self) -> dict | None:
        sources = self.v5.state['sources']
        if not sources:
            raise ValueError('V6 requires at least one registered source')
        accepted = [row for row in self._stage_rows('sources') if row['state'] == 'ACCEPTED']
        if accepted:
            if len(accepted) != 1:
                raise ValueError('V6 source registry has ambiguous accepted versions')
            row = accepted[0]
            registered = read(self.path(row['candidate']['artifacts'][0]['uri']))['sources']
            if registered != sources:
                return {'status': 'BLOCKED', 'reason': 'Source registry differs from accepted source version',
                        'revision': self.kernel.snapshot()['revision']}
            changed = any(not self.path(item['uri']).is_file() or
                          digest_file(self.path(item['uri'])) != item['sha256']
                          for item in sources)
            if not changed:
                return None
            self.kernel.transition(self._event(row, 'STALE', 'INPUT_CHANGED',
                                               command_id='source-changed-'+str(row['version']),
                                               evidence=['state.json']))
            self._stale_descendants()
            return {'status': 'BLOCKED', 'reason': 'Source file missing or changed',
                    'revision': self.kernel.snapshot()['revision']}
        if any(row['envelope']['node_id'] == 'sources' for row in self.kernel.snapshot()['tasks'].values()):
            return {'status': 'BLOCKED', 'reason': 'Source registry requires an explicit revised version',
                    'revision': self.kernel.snapshot()['revision']}
        for source in sources:
            if digest_file(self.path(source['uri'])) != source['sha256']:
                raise ValueError('Source file missing or changed: '+source['id'])
        task_id = 'V6_sources_'+_hash([(item['id'], item['sha256']) for item in sources])[:20]
        inputs = [{'slot': item['id'], 'uri': item['uri'], 'sha256': item['sha256'], 'version': 0}
                  for item in sources]
        inputs.append({'slot': 'source_index', 'uri': 'runtime/v6/source-index.json',
                       'sha256': digest_file(self.path('runtime/v6/source-index.json')),
                       'version': 0})
        envelope = self.create_graph_task('sources', self._project_scope(), task_id, extra_inputs=inputs)
        uri = f'runtime/v6/candidates/{task_id}/1/source-registry.json'
        self.write(uri, {'schema_version': '6.0', 'sources': sources})
        artifact = {'slot': envelope['expected_artifacts'][0]['slot'], 'kind': 'SourceRegistry',
                    'uri': uri, 'sha256': digest_file(self.path(uri))}
        checks = [{'id': 'source_integrity', 'status': 'PASS',
                   'evidence': [uri, *[item['uri'] for item in sources]]}]
        candidate = {'schema': 'candidate-result/6.0', 'task_id': task_id, 'batch': 1,
                     'agent_id': 'kernel', 'input_digest': envelope['input_digest'],
                     'result_uri': None, 'result_sha256': None,
                     'artifacts': [artifact], 'module_receipts': [], 'checks': checks,
                     'handoffs': [], 'unresolved': []}
        record = self.kernel.snapshot()['tasks'][task_id]
        self.kernel.transition(self._event(record, 'ACCEPTED', 'SYSTEM_VALIDATED',
                                           command_id='accept-'+task_id,
                                           checks=checks, evidence=[uri]), candidate=candidate)
        return None

    def _refresh_source_index(self) -> None:
        value = {'schema': 'source-index/6.0',
                 'sources': [{'id': item['id'], 'uri': item['uri'], 'sha256': item['sha256']}
                             for item in self.v5.state['sources']]}
        uri = 'runtime/v6/source-index.json'
        path = self.path(uri)
        if path.is_file() and read(path) == value:
            return
        with transaction(self.root):
            self.write(uri, value)

    def _stale_descendants(self) -> None:
        for node in self.graph['nodes']:
            for row in self._stage_rows(node['id']):
                if row['state'] not in ('READY', 'DISPATCHING', 'RUNNING',
                                        'RESULT_SUBMITTED', 'VALIDATING',
                                        'REVIEW_REQUIRED', 'ACCEPTED', 'NOT_APPLICABLE',
                                        'FAILED', 'BLOCKED'):
                    continue
                snapshot = self.kernel.snapshot()
                if any(snapshot['tasks'][item['task_id']]['state'] == 'STALE'
                       for item in row['envelope']['dependencies']):
                    self.kernel.transition(self._event(row, 'STALE', 'DEPENDENCY_STALE',
                                                       command_id='dependency-stale-'+row['envelope']['task_id']+'-'+str(row['version']),
                                                       evidence=['runtime/v6/state.json']))

    def _stale_changed_inputs(self) -> list[str]:
        changed = []
        for node in self.graph['nodes']:
            for row in self._stage_rows(node['id']):
                if row['state'] not in ('READY', 'DISPATCHING', 'RUNNING',
                                        'RESULT_SUBMITTED', 'VALIDATING',
                                        'REVIEW_REQUIRED', 'ACCEPTED', 'NOT_APPLICABLE'):
                    continue
                if (not self._runtime_code_changed(row['envelope'])
                        and not self.kernel._input_changed(
                            row['envelope'], accepted=row['state'] == 'ACCEPTED')):
                    continue
                task_id = row['envelope']['task_id']
                with transaction(self.root):
                    if row['state'] == 'ACCEPTED':
                        node_id = row['envelope']['node_id']
                        slot = ('art:' + row['envelope']['scope']['ids'][0]
                                if node_id == 'art' else
                                {'canon': 'canon', 'screenplay': 'screenplay',
                                 'director': 'director', 'storyboard': 'storyboard',
                                 'preproduction_qa': 'qa'}.get(node_id))
                        if slot:
                            native_state = self.v5.state
                            if slot in native_state['artifacts']:
                                native_state['artifacts'][slot]['invalidated'] = True
                                self.v5.save(native_state)
                        elif node_id == 'control':
                            native_state = self.v5.state
                            if native_state.get('control', {}).get('status') == 'READY':
                                native_state['control']['status'] = 'INVALIDATED'
                                self.v5.save(native_state)
                    self.kernel.transition(self._event(row, 'STALE', 'INPUT_CHANGED',
                                                       command_id='input-stale-'+task_id+'-'+str(row['version']),
                                                       evidence=['runtime/v6/state.json']))
                changed.append(task_id)
        if changed:
            self._stale_descendants()
        return changed

    def _sync_native_invalidations(self) -> None:
        """Keep legacy stage selection behind V6's authoritative stale states."""
        snapshot = self.kernel.snapshot()
        state = self.v5.state
        changed = False
        slots = {'canon': 'canon', 'screenplay': 'screenplay',
                 'director': 'director', 'storyboard': 'storyboard',
                 'preproduction_qa': 'qa'}
        rows = list(snapshot['tasks'].values())
        for row in rows:
            if (row['state'] in ('FAILED', 'BLOCKED', 'STALE', 'CANCELLED')
                    and row['envelope']['node_id'] in ('control', 'compile', 'compile_review')
                    and state.get('active_task') == row['envelope']['task_id']):
                state['active_task'] = None
                state['active_task_sha256'] = None
                changed = True
            if row['state'] != 'STALE':
                continue
            envelope = row['envelope']
            node = envelope['node_id']
            slot = ('art:' + envelope['scope']['ids'][0]
                    if node == 'art' else slots.get(node))
            if slot is None or slot not in state['artifacts']:
                continue
            if any(other['state'] == 'ACCEPTED'
                   and other['envelope']['node_id'] == node
                   and other['envelope']['scope'] == envelope['scope'] for other in rows):
                continue
            if not state['artifacts'][slot].get('invalidated'):
                state['artifacts'][slot]['invalidated'] = True
                changed = True
        if changed:
            with transaction(self.root):
                self.v5.save(state)

    def _ensure_reference_observation(self) -> None:
        rows = self._stage_rows('reference_observation')
        if rows and rows[-1]['state'] != 'FAILED':
            return
        node_id = 'reference_observation'
        node = stage_by_id(self.graph, node_id)
        context = self.kernel._applicability_context()
        applies = stage_applicability(node, context, evidence_ref='project.json')['status'] == 'APPLICABLE'
        task_id = 'V6_observation_'+_hash({'sources': self.v5.source_fingerprint_inputs()})[:20]
        previous = self.kernel.snapshot()['tasks'].get(task_id)
        if previous and previous['state'] == 'FAILED':
            if previous['envelope']['batch'] >= 3 or any(
                    count >= 2 for count in previous['failure_counts'].values()):
                return
        batch = previous['envelope']['batch']+1 if previous else 1
        envelope = self.create_graph_task(node_id, self._project_scope(), task_id, batch=batch)
        record = self.kernel.snapshot()['tasks'][task_id]
        if not applies:
            self.kernel.transition(self._event(record, 'NOT_APPLICABLE', node['skip']['reason_code'],
                                               command_id='skip-'+task_id+'-'+str(batch),
                                               evidence=['project.json'],
                                               affected_outputs=node['skip']['affected_outputs']))
            return
        self.kernel.transition(self._event(record, 'READY', 'DEPENDENCIES_SATISFIED',
                                           command_id='ready-'+task_id+'-'+str(batch),
                                           evidence=['project.json']))
        record = self.kernel.snapshot()['tasks'][task_id]
        self.kernel.transition(self._event(record, 'DISPATCHING', 'DISPATCH_REQUESTED',
                                           command_id='dispatch-'+task_id+'-'+str(batch),
                                           evidence=['project.json']))

    def _ensure_compile_task(self) -> None:
        build = self.v5.state.get('build') or {}
        if not build.get('build_id') or not build.get('files'):
            raise ValueError('Frozen V5 compilation is required before V6 compile review')
        for uri, checksum in build['files'].items():
            if digest_file(self.path(uri)) != checksum:
                raise ValueError('Compiled input changed before V6 dispatch: '+uri)
        task_id = 'V6_compile_'+_hash({'build': build['build_id'],
                                      'files': build['files']})[:20]
        previous = self.kernel.snapshot()['tasks'].get(task_id)
        if previous and previous['state'] not in ('FAILED', 'BLOCKED'):
            return
        if previous and previous['state'] == 'FAILED':
            if previous['envelope']['batch'] >= 3 or any(
                    count >= 2 for count in previous['failure_counts'].values()):
                return
        batch = previous['envelope']['batch']+1 if previous else 1
        brief_uri = f'runtime/v6/task-briefs/{task_id}.json'
        brief = {'node_id': 'compile', 'build_id': build['build_id'],
                 'build_uri': build['uri'], 'files': build['files'],
                 'instruction': 'Inspect the locked compiler and the frozen compiled package. Copy the exact AVIR and compile manifest into the candidate directory, report every graph check and source handoff; do not change the compiled creative content.'}
        route = self._latest_compile_semantic_failure()
        if route and route['record']['build_id'] != build['build_id']:
            brief['compile_semantic_failure'] = route['uri']
            brief['instruction'] += (' Resolve the hash-bound compile_semantic_failure record against its cited frozen build and evidence; '
                                     'the new output must pass a fresh independent compiler review.')
        extra = []
        extra.extend({'slot': 'build_'+str(index), 'uri': uri, 'sha256': checksum, 'version': 0}
                     for index, (uri, checksum) in enumerate(sorted(build['files'].items()), 1))
        if route and route['record']['build_id'] != build['build_id']:
            extra.append({'slot': 'compile_semantic_failure', 'uri': route['uri'],
                          'sha256': route['sha256'], 'version': route['record']['source_batch']})
        with transaction(self.root):
            self.write(brief_uri, brief)
            extra.insert(0, {'slot': 'compile_brief', 'uri': brief_uri,
                             'sha256': digest_file(self.path(brief_uri)), 'version': 0})
            self.create_graph_task('compile', self._project_scope(), task_id,
                                   batch=batch, extra_inputs=extra)
            record = self.kernel.snapshot()['tasks'][task_id]
            self.kernel.transition(self._event(record, 'READY', 'DEPENDENCIES_SATISFIED',
                                               command_id='ready-'+task_id+'-'+str(batch),
                                               evidence=[brief_uri]))
            record = self.kernel.snapshot()['tasks'][task_id]
            self.kernel.transition(self._event(record, 'DISPATCHING', 'DISPATCH_REQUESTED',
                                               command_id='dispatch-'+task_id+'-'+str(batch),
                                               evidence=[brief_uri]))

    def _verified_compile_semantic_failure(self, row: dict | None = None) -> dict | None:
        """Normalize a historical compiler failure only after its journal and byte chain verify."""
        events_path = self.path('runtime/v6/events.json')
        if not events_path.is_file():
            return None
        events = read(events_path)
        task_id = (row or {}).get('envelope', {}).get('task_id')
        failures = []
        for item in events:
            payload = item.get('payload') or {}
            event = payload.get('event') or {}
            if (event.get('to_state') != 'FAILED'
                    or event.get('reason') != 'VALIDATION_FAILED'
                    or (task_id is not None and event.get('task_id') != task_id)):
                continue
            if task_id is None and not any(
                    (prior.get('payload') or {}).get('task_id') == event.get('task_id')
                    and (prior.get('payload') or {}).get('node_id') == 'compile_review'
                    and (prior.get('payload') or {}).get('batch') == event.get('batch')
                    for prior in events if prior.get('op') == 'create_task'):
                continue
            failures.append(item)
        for item in reversed(failures):
            event = item['payload']['event']
            if len(event.get('evidence', [])) != 1:
                continue
            failure_uri = event['evidence'][0]
            failure_path = self.path(failure_uri)
            failure = read(failure_path)
            if (failure_path.parent != self.path(
                    f"runtime/v6/failures/{event['task_id']}/{event['batch']}")
                    or failure_path.name != _hash(failure)+'.json'):
                raise ValueError('Compile semantic failure record is not content-addressed')
            if failure.get('failed_check') != 'compile_semantics':
                continue
            check = next((entry for entry in event.get('check_results', [])
                          if entry.get('id') == 'compile_semantics'), None)
            if check is None or check.get('status') != 'FAIL':
                raise ValueError('Compile semantic route lacks the exact failed check event')
            task_id, batch = event['task_id'], event['batch']
            envelope_item = next((entry for entry in reversed(events)
                if entry.get('op') == 'create_task'
                and (entry.get('payload') or {}).get('task_id') == task_id
                and (entry.get('payload') or {}).get('batch') == batch), None)
            if envelope_item is None:
                raise ValueError('Compile semantic route has no frozen task envelope in the journal')
            envelope = envelope_item['payload']
            validate_v6_protocol('task-envelope', envelope, self.skill_root)
            if envelope['node_id'] != 'compile_review':
                continue

            candidate_uri = f'runtime/v6/candidates/{task_id}/{batch}/candidate-result.json'
            candidate_path = self.path(candidate_uri)
            candidate = read(candidate_path)
            validate_v6_protocol('candidate-result', candidate, self.skill_root)
            if (candidate.get('task_id') != task_id or candidate.get('batch') != batch
                    or candidate.get('input_digest') != envelope['input_digest']
                    or candidate_digest(candidate) != failure.get('candidate_digest')
                    or _hash(candidate) != failure.get('submission_digest')):
                raise ValueError('Compile semantic route candidate differs from the original submission')
            dispatch = next((entry.get('payload', {}).get('receipt') for entry in events
                if entry.get('op') == 'transition'
                and (entry.get('payload') or {}).get('event', {}).get('task_id') == task_id
                and entry['payload']['event'].get('batch') == batch
                and entry['payload']['event'].get('reason') == 'DISPATCH_CONFIRMED'), None)
            if not dispatch:
                raise ValueError('Compile semantic route has no original dispatch receipt')
            validate_v6_protocol('dispatch-receipt', dispatch, self.skill_root)
            self.kernel._verify_receipt(envelope, dispatch)
            if (dispatch.get('status') != 'RUNNING'
                    or dispatch.get('agent_id') != candidate['agent_id']):
                raise ValueError('Compile semantic route execution identity is not the frozen dispatch')

            result_uri = candidate['result_uri']
            result_path = self.path(result_uri)
            if digest_file(result_path) != candidate['result_sha256']:
                raise ValueError('Compile semantic route RoleResult bytes changed')
            result = read(result_path)
            validate_v5('role-result', result, self.skill_root)
            native_path = self.path('runtime/tasks/'+task_id+'.json')
            native_task = read(native_path)
            if (result.get('task_id') != task_id
                    or result.get('context_fingerprint') != native_task.get('context_fingerprint')
                    or native_task.get('kind') != 'compile-review'):
                raise ValueError('Compile semantic route RoleResult names a different native task')
            frozen_build = native_task.get('build') or {}
            build_id = frozen_build.get('build_id')
            semantic = result.get('semantic_review') or {}
            if (not build_id or semantic.get('build_id') != build_id
                    or semantic.get('equivalent') is not False
                    or semantic.get('failure_owner') != 'compile'
                    or not isinstance(semantic.get('finding_code'), str)
                    or not semantic['finding_code'].startswith('AVIR_')):
                raise ValueError('Compile semantic route lacks a structured current-build owner finding')
            for uri, checksum in (frozen_build.get('files') or {}).items():
                if digest_file(self.path(uri)) != checksum:
                    raise ValueError('Failed compile-review source build changed: '+uri)

            artifact_path = Path(result.get('artifact') or '').expanduser().resolve()
            if not artifact_path.is_relative_to(self.root) or not artifact_path.is_file():
                raise ValueError('Compile review artifact is not inside the project')
            artifact_uri = artifact_path.relative_to(self.root).as_posix()
            matching = [entry for entry in candidate.get('artifacts', [])
                        if entry.get('kind') == 'CompileReview' and entry.get('uri') == artifact_uri]
            if len(matching) != 1:
                raise ValueError('Compile semantic route artifact is not uniquely declared by the candidate')
            artifact_sha = digest_file(artifact_path)
            if (artifact_sha != result.get('artifact_sha256')
                    or matching[0].get('sha256') != artifact_sha):
                raise ValueError('Compile semantic route artifact hash differs across its bindings')
            artifact = read(artifact_path)
            if (artifact.get('build_id') != build_id or artifact.get('equivalent') is not False
                    or artifact.get('failure_owner_node') != 'compile'
                    or artifact.get('finding_code') != semantic['finding_code']
                    or not str(artifact.get('finding') or '').strip()
                    or (semantic.get('finding') is not None
                        and artifact.get('finding') != semantic['finding'])):
                raise ValueError('Compile semantic route artifact disagrees with its RoleResult')

            body = {'schema': 'compile-semantic-failure/6.0',
                    'project_id': self.project['project_id'],
                    'source_task_id': task_id, 'source_batch': batch,
                    'source_agent_id': candidate['agent_id'],
                    'candidate_digest': candidate_digest(candidate),
                    'result': {'uri': result_uri, 'sha256': candidate['result_sha256']},
                    'build_id': build_id,
                    'review_artifact': {'uri': artifact_uri, 'sha256': artifact_sha},
                    'failure_owner_node': 'compile', 'finding_code': semantic['finding_code'],
                    'finding': artifact['finding']}
            body['route_id'] = 'CSF_'+sha256_json(body)[:24]
            validate_v6_protocol('compile-semantic-failure', body, self.skill_root)
            uri = f"runtime/v6/compile-semantic-failures/{body['route_id']}.json"
            path = self.path(uri)
            if path.is_file():
                if read(path) != body:
                    raise ValueError('Compile semantic route ID already contains different content')
            else:
                with transaction(self.root):
                    self.write(uri, body)
            return {'uri': uri, 'sha256': digest_file(path), 'record': body}
        return None

    def _latest_compile_semantic_failure(self) -> dict | None:
        return self._verified_compile_semantic_failure()

    def _ensure_preproduction_delivery(self) -> None:
        if any(row['state'] == 'ACCEPTED' for row in self._stage_rows('preproduction_delivery')):
            return
        native = self.v5.validate(final=True)
        if not native['valid']:
            raise ValueError('Native preproduction validation failed: '+'; '.join(native['errors']))
        task_id = 'V6_preproduction_'+_hash({
            'build': (self.v5.state.get('build') or {}).get('build_id'),
            'qa': self.v5.state['artifacts']['qa']['sha256']})[:20]
        with transaction(self.root):
            envelope = self.create_graph_task('preproduction_delivery', self._project_scope(), task_id)
            delivered = self.v5.export()
            if delivered.get('status') != 'DELIVERED':
                raise ValueError('Native preproduction export did not pass validation')
            uri = f'runtime/v6/candidates/{task_id}/1/delivery-index.json'
            self.write(uri, self.path('delivery/index.json').read_bytes())
            checks = [{'id': 'preproduction_final', 'status': 'PASS',
                       'evidence': [uri, 'delivery/index.json']}]
            candidate = {'schema': 'candidate-result/6.0', 'task_id': task_id,
                         'batch': 1, 'agent_id': 'kernel',
                         'input_digest': envelope['input_digest'],
                         'result_uri': None, 'result_sha256': None,
                         'artifacts': [{'slot': envelope['expected_artifacts'][0]['slot'],
                                        'kind': 'PreproductionDelivery', 'uri': uri,
                                        'sha256': digest_file(self.path(uri))}],
                         'module_receipts': [], 'checks': checks,
                         'handoffs': [], 'unresolved': []}
            record = self.kernel.snapshot()['tasks'][task_id]
            self.kernel.transition(self._event(record, 'ACCEPTED', 'SYSTEM_VALIDATED',
                                               command_id='accept-'+task_id,
                                               checks=checks,
                                               evidence=[uri, 'delivery/index.json']),
                                   candidate=candidate)

    def _finish_non_video(self) -> None:
        if self.production_target() == 'video':
            return
        self._materialize_skips_before('video_delivery')
        node = stage_by_id(self.graph, 'video_delivery')
        if any(row['state'] == 'NOT_APPLICABLE' for row in self._stage_rows('video_delivery')):
            return
        scope = self._project_scope()
        task_id = self._skip_task_id('video_delivery', scope,
                                     self.kernel._applicability_context())
        self.create_graph_task('video_delivery', scope, task_id)
        record = self.kernel.snapshot()['tasks'][task_id]
        self.kernel.transition(self._event(record, 'NOT_APPLICABLE', node['skip']['reason_code'],
                                           command_id='skip-'+task_id,
                                           evidence=['project.json'],
                                           affected_outputs=node['skip']['affected_outputs']))

    def _targeted_repair(self, failed: dict) -> dict:
        """Freeze repeated failures as new input before a final specialist batch."""
        envelope = failed['envelope']
        task_id = envelope['task_id']
        batch = envelope['batch'] + 1
        repeated = {key for key, count in failed['failure_counts'].items() if count >= 2}
        if (failed['state'] != 'FAILED' or batch != 3
                or envelope['execution_class'] != 'professional' or len(repeated) != 1):
            raise ValueError('Targeted repair requires one repeated specialist check after batch two')
        check_id = next(iter(repeated))
        history = {item['envelope']['batch']: item for item in failed['history']
                   if isinstance(item, dict) and isinstance(item.get('envelope'), dict)}
        history[envelope['batch']] = failed
        failures = []
        for entry in read(self.path('runtime/v6/events.json')):
            event = (entry.get('payload') or {}).get('event') or {}
            if (event.get('task_id') != task_id or event.get('to_state') != 'FAILED'
                    or (event.get('error') or {}).get('failed_check') != check_id):
                continue
            evidence = event.get('evidence') or []
            if len(evidence) != 1 or not self.path(evidence[0]).is_file():
                raise ValueError('Repeated failure lacks its original evidence file')
            detail = read(self.path(evidence[0]))
            review_evidence = list(detail.get('check_evidence') or [])
            previous = history.get(event['batch'])
            if previous is not None:
                for message in previous.get('messages', []):
                    if message.get('type') == 'RESULT' and message.get('batch') == event['batch']:
                        review_evidence.extend(uri for uri in message.get('evidence', [])
                                               if '/reviews/' in uri)
            review_evidence = list(dict.fromkeys(review_evidence))
            if any(not self.path(uri).is_file() for uri in review_evidence):
                raise ValueError('Independent review evidence changed before repair')
            failures.append({'batch': event['batch'], 'code': event['error']['code'],
                             'failure_uri': evidence[0],
                             'failure_sha256': digest_file(self.path(evidence[0])),
                             'review_evidence': [{'uri': uri, 'sha256': digest_file(self.path(uri))}
                                                 for uri in review_evidence]})
        if len(failures) < 2 or [item['batch'] for item in failures[-2:]] != [1, 2]:
            raise ValueError('Targeted repair needs both failed batch records')
        failures = failures[-2:]
        brief = {'schema': 'repair-brief/6.0', 'task_id': task_id,
                 'node_id': envelope['node_id'], 'next_batch': batch,
                 'failed_check': check_id, 'failures': failures,
                 'instruction': 'Read both failure and review evidence files. Correct every cited issue in a new candidate while preserving the frozen source and upstream contracts.'}
        validate_v6_protocol('repair-brief', brief, self.skill_root)
        uri = f'runtime/v6/repair/{task_id}/{batch}/repair-brief.json'
        snapshot = self.kernel.snapshot()
        if snapshot['tasks'][task_id]['version'] != failed['version']:
            raise ValueError('Task changed before targeted repair was prepared')
        dependency_slots = {item['slot'] for dep in envelope['dependencies']
                            for item in snapshot['tasks'][dep['task_id']]['envelope']['expected_artifacts']}
        extra = [item for item in envelope['inputs']
                 if item['slot'] not in dependency_slots
                 and item['slot'] not in ('frozen_task', 'migration_report')]
        extra = [item for item in extra if not item['slot'].startswith('repair_')]
        with transaction(self.root):
            self.write(uri, brief)
            extra.append({'slot': 'repair_brief', 'uri': uri,
                          'sha256': digest_file(self.path(uri)), 'version': batch})
            for index, item in enumerate(failures, 1):
                extra.append({'slot': f'repair_failure_{index}',
                              'uri': item['failure_uri'],
                              'sha256': item['failure_sha256'], 'version': item['batch']})
            native_task_path = self.path(f'runtime/tasks/{task_id}.json')
            native_task = read(native_task_path) if native_task_path.is_file() else None
            self.create_graph_task(envelope['node_id'], envelope['scope'], task_id,
                                   batch=batch, frozen_task=native_task,
                                   extra_inputs=extra)
            record = self.kernel.snapshot()['tasks'][task_id]
            self.kernel.transition(self._event(record, 'READY', 'DEPENDENCIES_SATISFIED',
                                               command_id=f'ready-{task_id}-{batch}',
                                               evidence=[uri]))
            record = self.kernel.snapshot()['tasks'][task_id]
            self.kernel.transition(self._event(record, 'DISPATCHING', 'DISPATCH_REQUESTED',
                                               command_id=f'dispatch-{task_id}-{batch}',
                                               evidence=[uri]))
        return self.run()

    def run(self) -> dict:
        from .v6_codex_host import CodexHostBridge
        self.kernel.recover()
        self._refresh_source_index()
        self._sync_native_invalidations()
        changed = self._stale_changed_inputs()
        if changed:
            self._sync_native_invalidations()
            return {'status': 'BLOCKED', 'reason': 'Frozen task input changed',
                    'stale_tasks': changed, 'revision': self.kernel.snapshot()['revision']}
        source_block = self._ensure_sources()
        if source_block is not None:
            return source_block
        self._ensure_reference_observation()
        self._queue_parallel_art()
        self._queue_parallel_prompts()
        active = self._active()
        if active:
            actions = []
            for task in active:
                if task['envelope']['execution_class'] == 'external_image' and task['state'] in (
                        'DISPATCHING', 'RUNNING', 'UNKNOWN'):
                    from .v6_media_host import pending_image_action
                    frozen = read(self.root/'runtime/tasks'/(task['envelope']['task_id']+'.json'))
                    actions.append(pending_image_action(task['envelope'], frozen, self.root))
                elif task['state'] in ('DISPATCHING', 'UNKNOWN', 'REVIEW_REQUIRED'):
                    action = CodexHostBridge(self.kernel).pending(task['envelope']['task_id'])
                    if action is not None:
                        actions.append(action)
            return {'status': 'AWAITING_HOST' if actions else 'AWAITING_RESULT',
                    'revision': self.kernel.snapshot()['revision'], 'actions': actions,
                    'tasks': [{'task_id': item['envelope']['task_id'], 'node_id': item['envelope']['node_id'],
                               'state': item['state']} for item in active]}
        compile_failure = self._latest_compile_semantic_failure()
        if compile_failure is not None:
            build = self.v5.state.get('build') or {}
            if (build.get('build_id') == compile_failure['record']['build_id']
                    and build.get('input_fingerprint') == self.v5.build_fingerprint()):
                return {'status': 'REPAIR_REQUIRED',
                        'task_id': compile_failure['record']['source_task_id'],
                        'node_id': 'compile_review', 'owner_node_id': 'compile',
                        'failed_check': 'compile_semantics',
                        'failure_route': compile_failure['uri'],
                        'failure_route_sha256': compile_failure['sha256'],
                        'recovery_action': 'REVISE',
                        'revision': self.kernel.snapshot()['revision']}
        for row in self.kernel.snapshot()['tasks'].values():
            if row['state'] not in ('FAILED', 'BLOCKED'):
                continue
            routed = self._route_upstream_review_failure(row)
            if routed is not None:
                return routed
            later = [item for item in self.kernel.snapshot()['tasks'].values()
                     if item['envelope']['node_id'] == row['envelope']['node_id']
                     and item['envelope']['scope'] == row['envelope']['scope']
                     and item['envelope']['input_revision'] > row['envelope']['input_revision']
                     and item['state'] in ('ACCEPTED', 'NOT_APPLICABLE')]
            if later:
                continue
            repeated = any(count >= 2 for count in row['failure_counts'].values())
            if repeated and row['state'] == 'FAILED' and row['envelope']['batch'] < 3 \
                    and row['envelope']['execution_class'] == 'professional':
                return self._targeted_repair(row)
            if row['state'] == 'BLOCKED' or repeated or row['envelope']['batch'] >= 3:
                return {'status': 'REPAIR_REQUIRED', 'task_id': row['envelope']['task_id'],
                        'node_id': row['envelope']['node_id'],
                        'failed_checks': [key for key, count in row['failure_counts'].items() if count],
                        'recovery_action': 'REVISE' if row['envelope']['batch'] < 3 else 'ABORT',
                        'revision': self.kernel.snapshot()['revision']}
        if self.v5.valid('qa'):
            native = self.v5.validate(final=True)
            if not native['valid']:
                return {'status': 'BLOCKED', 'validation': native,
                        'revision': self.kernel.snapshot()['revision']}
            self._ensure_preproduction_delivery()
            self._finish_non_video()
            return {'status': 'PREPRODUCTION_DELIVERED' if self.production_target() == 'video' else 'DELIVERED',
                    'revision': self.kernel.snapshot()['revision'],
                    'delivery_index': str(self.path('delivery/index.md'))}
        with transaction(self.root):
            result = self.v5.run()
            task = result.get('task')
            if task is None:
                return result
            self._materialize_skips_before(self._node(task))
            if self._node(task) == 'compile_review' and not any(
                    row['state'] == 'ACCEPTED' for row in self._stage_rows('compile')):
                self._ensure_compile_task()
            else:
                envelope = self._envelope(task)
                record = self.kernel.snapshot()['tasks'][task['task_id']]
                self.kernel.transition(self._event(record, 'READY', 'DEPENDENCIES_SATISFIED',
                                                   command_id='ready-'+task['task_id']+'-'+str(envelope['batch']),
                                                   evidence=[task_file_ref(self.root, task)]))
                record = self.kernel.snapshot()['tasks'][task['task_id']]
                self.kernel.transition(self._event(record, 'DISPATCHING', 'DISPATCH_REQUESTED',
                                                   command_id='dispatch-'+task['task_id']+'-'+str(envelope['batch']),
                                                   evidence=[task_file_ref(self.root, task)]))
        return self.run()

    def image_begin(self, task_id: str, *, command_id: str, expected_revision: int) -> dict:
        """Record the original host action and V5 in-flight marker before a tool call."""
        from .v6_media_host import pending_image_action, store_image_action
        replay = self._replayed_submission(command_id, task_id, expected_revision,
                                           reason='HOST_EXECUTION_STARTED')
        if replay is not None:
            return replay
        snapshot, record = self._task_record(task_id)
        if snapshot['revision'] != expected_revision or record['state'] != 'DISPATCHING':
            raise ValueError('Image host start is stale or task is not dispatching')
        if record['envelope']['execution_class'] != 'external_image':
            raise ValueError('Image host start requires an image task')
        frozen = read(self.root/'runtime/tasks'/(task_id+'.json'))
        action = pending_image_action(record['envelope'], frozen, self.root)
        if action['kind'] == 'RECONCILE_ONLY':
            raise ValueError('Image call is already in flight; reconcile its original action')
        with transaction(self.root):
            uri, _ = store_image_action(self.root, action)
            self.v5.begin_image(task_id)
            self.kernel.transition(self._event(record, 'RUNNING', 'HOST_EXECUTION_STARTED',
                                               command_id=command_id, evidence=[uri],
                                               actor_kind='host', actor_id='image_host'))
        return {'status': 'RUNNING', 'action': action, 'action_evidence': uri,
                'revision': self.kernel.snapshot()['revision']}

    def image_result(self, candidate: dict, *, command_id: str, expected_revision: int) -> dict:
        """Accept copied image bytes only after host, native and graph checks agree."""
        from .v6_media_host import validate_media_result
        replay = self._replayed_submission(command_id, candidate['task_id'], expected_revision,
                                           reason='HOST_RESULT_RECEIVED',
                                           field='candidate', value=candidate)
        if replay is not None:
            return replay
        snapshot, record = self._task_record(candidate['task_id'])
        if snapshot['revision'] != expected_revision or record['state'] != 'RUNNING':
            raise ValueError('Image result is stale or task is not running')
        envelope = record['envelope']
        if envelope['execution_class'] != 'external_image':
            raise ValueError('Image result requires an external image task')
        frozen = read(self.root/'runtime/tasks'/(candidate['task_id']+'.json'))
        validate_media_result(self.root, envelope, frozen, candidate, skill_root=self.skill_root)
        evidence = [candidate['host_record_uri'], candidate['result_uri']]
        with transaction(self.root):
            self.kernel.submit_candidate(self._event(record, 'RESULT_SUBMITTED',
                                                     'HOST_RESULT_RECEIVED', command_id=command_id,
                                                     evidence=evidence, actor_kind='host',
                                                     actor_id='image_host'), candidate)
            record = self.kernel.snapshot()['tasks'][candidate['task_id']]
            self.kernel.transition(self._event(record, 'VALIDATING', 'VALIDATION_STARTED',
                                               command_id=command_id+'-validate', evidence=evidence))
            native = self.v5.submit(str(self.root/candidate['result_uri']))
            if native.get('status') not in ('ACCEPTED', 'ALREADY_ACCEPTED') or native.get('task_id') != candidate['task_id']:
                raise ValueError('Native image import did not pass its completion gate')
            record = self.kernel.snapshot()['tasks'][candidate['task_id']]
            self.kernel.complete_host_task(self._event(record, 'ACCEPTED', 'HOST_EXECUTION_CONFIRMED',
                                                       command_id=command_id+'-accept',
                                                       checks=candidate['checks'], evidence=evidence), candidate)
        return self.run()

    def agent_event(self, receipt: dict, *, command_id: str, expected_revision: int) -> dict:
        from .v6_codex_host import CodexHostBridge, replay_registered_command
        replay = replay_registered_command(self.kernel, command_id, expected_revision,
                                           'agent-event', receipt)
        if replay is not None:
            return replay
        bridge = CodexHostBridge(self.kernel)
        snapshot, record = self._task_record(receipt['task_id'])
        if snapshot['revision'] != expected_revision:
            raise ValueError('Stale host event revision')
        if record['state'] == 'REVIEW_REQUIRED':
            return bridge.register_review_dispatch(receipt, command_id=command_id,
                                                   expected_revision=expected_revision)
        return bridge.register_dispatch(receipt, command_id=command_id,
                                        expected_revision=expected_revision)

    def agent_message(self, message: dict, *, command_id: str, expected_revision: int) -> dict:
        from .v6_codex_host import CodexHostBridge, replay_registered_command
        replay = replay_registered_command(self.kernel, command_id, expected_revision,
                                           'agent-message', message)
        if replay is not None:
            return replay
        return CodexHostBridge(self.kernel).record_message(message, command_id=command_id,
                                                             expected_revision=expected_revision)

    def agent_cancel(self, task_id: str, ack_message_id: str | None, *,
                     command_id: str, expected_revision: int) -> dict:
        from .v6_codex_host import replay_registered_command
        payload = {'task_id': task_id, 'ack_message_id': ack_message_id}
        replay = replay_registered_command(self.kernel, command_id, expected_revision,
                                           'agent-cancel', payload)
        if replay is not None:
            return replay
        snapshot, record = self._task_record(task_id)
        if snapshot['revision'] != expected_revision:
            raise ValueError('Cancellation uses an old project revision')
        if record['state'] not in ('READY', 'DISPATCHING', 'RUNNING', 'REVIEW_REQUIRED'):
            raise ValueError('Task cannot be cancelled from its current state')
        receipt = record.get('review_dispatch') or record.get('receipt')
        if receipt is None:
            if ack_message_id is not None:
                raise ValueError('Undispatched task cannot claim an agent acknowledgement')
        else:
            acknowledgements = [item for item in record['messages']
                                if item['message_id'] == ack_message_id
                                and item['type'] == 'CANCEL_ACK'
                                and item['sender_id'] == receipt['agent_id']
                                and item['recipient_id'] == 'kernel'
                                and item['evidence']]
            if len(acknowledgements) != 1:
                raise ValueError('Cancellation requires the current agent CANCEL_ACK with evidence')
        checksum = hashlib.sha256(compact_json(payload)).hexdigest()
        uri = f'runtime/v6/cancellations/{checksum}.json'
        with transaction(self.root):
            self.write(uri, compact_json(payload))
            event = self._event(record, 'CANCELLED', 'CANCEL_REQUESTED',
                                command_id=command_id, evidence=[uri],
                                actor_kind='host', actor_id='codex-host')
            self.kernel.transition(event)
        return {'status': 'CANCELLED', 'task_id': task_id,
                'revision': self.kernel.snapshot()['revision'], 'evidence': uri}

    def agent_result(self, candidate: dict, *, command_id: str, expected_revision: int) -> dict:
        replay = self._replayed_submission(command_id, candidate['task_id'], expected_revision,
                                           reason='RESULT_RECEIVED',
                                           field='candidate', value=candidate,
                                           failure_reason='VALIDATION_FAILED')
        if replay is not None:
            return replay
        snapshot, record = self._task_record(candidate['task_id'])
        if snapshot['revision'] != expected_revision or record['state'] != 'RUNNING':
            raise ValueError('Candidate is stale or task is not running')
        try:
            with transaction(self.root):
                event = self._event(record, 'RESULT_SUBMITTED', 'RESULT_RECEIVED', command_id=command_id,
                                    evidence=[candidate['result_uri']] if candidate['result_uri'] else [],
                                    actor_kind='host', actor_id=candidate['agent_id'])
                self.kernel.submit_candidate(event, candidate)
                record = self.kernel.snapshot()['tasks'][candidate['task_id']]
                self.kernel.transition(self._event(record, 'VALIDATING', 'VALIDATION_STARTED',
                                                   command_id=command_id+'-validate'))
                record = self.kernel.snapshot()['tasks'][candidate['task_id']]
                if record['envelope']['node_id'] in ('reference_observation', 'compile'):
                    self._validate_graph_only_candidate(record)
                elif record['envelope']['node_id'] in ('shot_acceptance', 'take_selection',
                                                       'adjacent_acceptance', 'whole_acceptance'):
                    from .v6_production_runtime import V6ProductionRuntime
                    V6ProductionRuntime(self).validate_candidate(record['envelope'], candidate)
                else:
                    self._validate_v5_candidate(record)
                node = stage_by_id(self.graph, record['envelope']['node_id'])
                target = 'ACCEPTED' if node['review'] == 'none' else 'REVIEW_REQUIRED'
                if target == 'ACCEPTED':
                    if record['envelope']['node_id'] in ('shot_acceptance', 'take_selection',
                                                         'adjacent_acceptance', 'whole_acceptance'):
                        V6ProductionRuntime(self).promote_candidate(record['envelope'], candidate)
                    else:
                        result = self.v5.submit(str(self.root/candidate['result_uri']))
                        if result.get('status') not in ('ACCEPTED', 'ALREADY_ACCEPTED') or result.get('task_id') != candidate['task_id']:
                            raise ValueError('Native task was not accepted after validation')
                self.kernel.transition(self._event(record, target, 'VALIDATION_PASSED',
                                                   command_id=command_id+'-validation',
                                                   checks=candidate['checks'],
                                                   evidence=[candidate['result_uri']] if candidate['result_uri'] else []))
        except (ValueError, OSError) as error:
            return self._record_failure(candidate['task_id'], error, command_id=command_id,
                                        candidate=candidate, reason='VALIDATION_FAILED')
        return self.run()

    def _record_failure(self, task_id: str, error: Exception, *, command_id: str,
                        candidate: dict | None = None, review: dict | None = None,
                        reason: str) -> dict:
        snapshot, record = self._task_record(task_id)
        if record['state'] not in ('RUNNING', 'RESULT_SUBMITTED', 'VALIDATING', 'REVIEW_REQUIRED'):
            raise error
        declared = [item['id'] for item in record['envelope']['validators']]
        reported = (review or candidate or {}).get('checks') or []
        failed = getattr(error, 'failed_check', None)
        if failed not in declared:
            failed = next((item['id'] for item in reported if item.get('status') == 'FAIL'
                           and item.get('id') in declared), declared[0])
        count = record['failure_counts'].get(failed, 0) + 1
        action = ('ABORT' if record['envelope']['batch'] >= 3 else
                  'REVISE' if count >= 2 else 'RETRY')
        details = {'task_id': task_id, 'batch': record['envelope']['batch'],
                   'node_id': record['envelope']['node_id'], 'failed_check': failed,
                   'code': getattr(error, 'code', type(error).__name__.upper()),
                   'message': str(error),
                   'candidate_digest': (candidate_digest(candidate) if candidate else
                                        (review or {}).get('candidate_digest')),
                   'submission_digest': _hash(candidate if candidate is not None else review),
                   'reviewer_failure_owner': (review or {}).get('failure_owner'),
                   'check_evidence': next((item.get('evidence', []) for item in reported
                                           if item.get('id') == failed), [])}
        review_uri = (f"runtime/v6/reviews/{task_id}/{record['envelope']['batch']}/review-failure.json"
                      if review is not None else None)
        with transaction(self.root):
            if review is not None:
                self.write(review_uri, review)
                details['review_record_uri'] = review_uri
                details['review_record_sha256'] = digest_file(self.path(review_uri))
            uri = ('runtime/v6/failures/'+task_id+'/'+str(record['envelope']['batch'])+'/'
                   +_hash(details)+'.json')
            self.write(uri, details)
            checks = [{'id': item, 'status': 'FAIL' if item == failed else 'BLOCKED',
                       'evidence': [uri]} for item in declared]
            event = self._event(record, 'FAILED', reason,
                                command_id=command_id+'-failed', checks=checks,
                                evidence=[uri])
            event['error'] = {'code': details['code'], 'owner_node': record['envelope']['node_id'],
                              'failed_check': failed, 'evidence': [uri],
                              'retryable': action == 'RETRY', 'recovery_action': action}
            self.kernel.transition(event)
        if action == 'RETRY' and record['envelope']['node_id'] not in ('reference_observation', 'compile'):
            return self.run()
        if (review is not None and review.get('failure_owner')
                not in (None, record['envelope']['node_id'])):
            return self.run()
        if action == 'REVISE' and record['envelope']['execution_class'] == 'professional':
            return self.run()
        return {'status': 'REPAIR_REQUIRED' if action != 'RETRY' else 'RETRY_REQUIRED',
                'task_id': task_id, 'node_id': record['envelope']['node_id'],
                'failed_check': failed, 'failure_evidence': uri,
                'recovery_action': action, 'revision': self.kernel.snapshot()['revision']}

    def _validate_v5_candidate(self, record: dict) -> None:
        candidate = record['candidate']
        if candidate['result_uri'] is None:
            raise ValueError('V5 promotion requires a frozen RoleResult file')
        path = self.root/candidate['result_uri']
        if not path.resolve().is_relative_to(self.root) or digest_file(path) != candidate['result_sha256']:
            raise ValueError('Candidate RoleResult bytes changed')
        result = read(path)
        validate_v5('role-result', result, self.skill_root)
        task_id = record['envelope']['task_id']
        native_task = read(self.root/'runtime/tasks'/(task_id+'.json'))
        if result['task_id'] != task_id or result['context_fingerprint'] != native_task['context_fingerprint']:
            raise ValueError('Candidate RoleResult binds a different task context')
        if result.get('conflicts') or result.get('unresolved') or candidate['unresolved']:
            raise ValueError('Unresolved native result cannot enter review or acceptance')
        declared = {self.root/item['uri'] for item in candidate['artifacts']}
        if result.get('artifact'):
            if Path(result['artifact']).resolve() not in {item.resolve() for item in declared}:
                raise ValueError('Native artifact is absent from candidate manifest')
            if digest_file(Path(result['artifact'])) != result.get('artifact_sha256'):
                raise ValueError('Native artifact bytes changed')
        if result.get('manifest'):
            if not Path(result['manifest']).is_file() or digest_file(Path(result['manifest'])) != result.get('manifest_sha256'):
                raise ValueError('Native manifest bytes changed')
        # Run the read-only native acceptance checks before spending an
        # independent review. A syntactically valid ScriptIR may still bind an
        # old Canon, which the native importer would otherwise reject only
        # after the reviewer has finished.
        try:
            self.v5.receipt_audit(native_task, result)
        except ValueError as error:
            raise V6CheckFailure('module_receipt', 'MODULE_RECEIPT_INVALID', error) from error
        if native_task['kind'] == 'image-prompt':
            try:
                self.v5.accept_prompt(native_task, result, self.v5.state)
            except ValueError as error:
                raise V6CheckFailure('image_prompt_contract', 'PROMPT_CONTRACT_INVALID', error) from error
            # Prompt outputs are plain UTF-8 text. Treating this artifact as
            # JSON (as native IR artifacts are) rejects valid optimizer output.
            return
        if native_task['kind'] == 'control':
            try:
                packs = [item for item in candidate['artifacts'] if item['kind'] == 'ShotControlPack']
                if len(packs) != 1:
                    raise ValueError('Control candidate needs exactly one ShotControlPack manifest')
                manifest = self.root/packs[0]['uri']
                config = Path(result.get('config') or '').resolve()
                candidate_dir = self.root/f"runtime/v6/candidates/{task_id}/{record['envelope']['batch']}"
                if (not config.is_file() or not config.is_relative_to(candidate_dir)
                        or config.read_bytes() != (manifest.parent/'control-config.json').read_bytes()):
                    raise ValueError('Control config is missing, outside this candidate or differs from package')
                avir, report = storyboard_to_avir(self.v5.data('storyboard'), self.root)
                if report['status'] != 'MAPPED':
                    raise ValueError('Current StoryboardIR cannot be fully mapped to AVIR')
                if report.get('semantic_review') != 'INHERITED_DETERMINISTICALLY':
                    raise ValueError('Current StoryboardIR semantic review is not bound to imported bytes')
                if read(manifest.parent/'production-specification.json') != avir:
                    raise ValueError('Control package AVIR differs from current StoryboardIR conversion')
                fresh = self.kernel._verify_control_package(packs[0]['uri'])
                if (result.get('validator') or {}).get('status') != fresh['status']:
                    raise ValueError('Control RoleResult validator differs from fresh locked verification')
                frames = read(manifest.parent/'review/frames.json')
                if not frames or any(frame['camera']['status'] == 'UNDETERMINED'
                                     for frame in frames):
                    raise ValueError('Control package has undetermined camera projection frames')
            except (ValueError, OSError, KeyError) as error:
                raise V6CheckFailure('control_verify', 'CONTROL_PACKAGE_INVALID', error) from error
        if result.get('artifact'):
            artifact_path = Path(result['artifact']).resolve()
            check_id = ('canon_contract' if native_task['kind'] == 'canon' else
                        'preproduction_final' if native_task['kind'] == 'qa' else 'native_validator')
            artifact_value = read(artifact_path)
            if (native_task['kind'] in ('director', 'storyboard', 'avir')
                    and isinstance(artifact_value.get('timeline'), dict)
                    and isinstance(artifact_value['timeline'].get('semantic_review'), dict)):
                from .v51_detail_runtime import semantic_status
                if artifact_value['timeline']['semantic_review'].get('status') == 'PASS' \
                        and not semantic_status(artifact_value):
                    raise V6CheckFailure('native_validator', 'SEMANTIC_REVIEW_STALE',
                                         ValueError('Native semantic review does not bind current content'))
            try:
                self.v5.check_content(native_task['kind'], artifact_value, artifact_path)
            except ValueError as error:
                raise V6CheckFailure(check_id, 'NATIVE_CONTENT_INVALID', error) from error
            if native_task['kind'] in ('director', 'screenplay', 'art', 'storyboard', 'avir'):
                try:
                    self.v5.check_validator(native_task['kind'], artifact_path, result)
                except ValueError as error:
                    raise V6CheckFailure('native_validator', 'NATIVE_VALIDATOR_MISMATCH', error) from error
            if native_task['kind'] in ('director', 'art', 'storyboard'):
                protocol = self.v5.screenplay_protocol() if native_task['kind'] == 'director' else None
                required = native_handoff_requirements(native_task['kind'],
                    self.v5.handoff_inputs(native_task['dependencies']), protocol)
                screenplay = ((self.v5.data('screenplay'), protocol)
                              if protocol and self.v5.valid('screenplay') else None)
                try:
                    validate_handoff(native_task['kind'], read(artifact_path), required,
                                     result.get('handoff'), screenplay)
                except ValueError as error:
                    raise V6CheckFailure('handoff', 'NATIVE_HANDOFF_INVALID', error) from error

    def _validate_graph_only_candidate(self, record: dict) -> None:
        envelope, candidate = record['envelope'], record['candidate']
        if candidate['result_uri'] is not None:
            raise ValueError('Graph-only candidate must not claim a native RoleResult')
        node_id = envelope['node_id']
        artifacts = {item['kind']: item for item in candidate['artifacts']}
        if node_id == 'compile':
            build = self.v5.state.get('build') or {}
            if not build or build.get('input_fingerprint') != self.v5.build_fingerprint():
                raise ValueError('Current native build is absent or stale')
            files = build.get('files') or {}
            avir_uri = build['uri']+'/avir.json'
            manifest_uri = build['uri']+'/compiled/compile-manifest.json'
            if any(not self.path(uri).is_file() or digest_file(self.path(uri)) != checksum
                   for uri, checksum in files.items()):
                raise ValueError('Compiled native package bytes changed')
            if (set(artifacts) != {'AVIR', 'CompilePackage'}
                    or artifacts['AVIR']['sha256'] != files.get(avir_uri)
                    or artifacts['CompilePackage']['sha256'] != files.get(manifest_uri)
                    or read(self.path(artifacts['AVIR']['uri'])) != read(self.path(avir_uri))
                    or read(self.path(artifacts['CompilePackage']['uri'])) != read(self.path(manifest_uri))):
                raise ValueError('Compile candidate differs from frozen native AVIR or manifest')
            manifest = read(self.path(manifest_uri))
            if manifest.get('build_id') != build['build_id']:
                raise ValueError('Compile candidate binds a different build ID')
            compiler = self.v5.modules('video-prompt-compiler')
            completed = subprocess.run([sys.executable, str(compiler/'scripts/vpc.py'),
                                        'verify', str(self.path(build['uri']+'/compiled'))],
                                       capture_output=True, text=True)
            if completed.returncode:
                raise ValueError('Frozen compiled package verification failed: '+completed.stderr+completed.stdout)
        elif node_id == 'reference_observation':
            if set(artifacts) != {'ObservationRegister'}:
                raise ValueError('Reference observation must provide one register artifact')
            register = read(self.path(artifacts['ObservationRegister']['uri']))
            validate_v6_protocol('observation-register', register, self.skill_root)
            expected = {item['id']: item for item in self.v5.state['sources']
                        if Path(item['uri']).suffix.lower() in ('.mp4', '.mov', '.mkv',
                            '.webm', '.m4v', '.avi')}
            if ({item['source_id'] for item in register['bundles']} != set(expected)
                    or len(register['bundles']) != len(expected)):
                raise ValueError('Observation register does not cover every video source exactly')
            for item in register['bundles']:
                bundle = self.path(item['directory'])
                candidate_dir = self.path(envelope['expected_artifacts'][0]['uri_prefix'])
                if not bundle.is_dir() or not bundle.is_relative_to(candidate_dir):
                    raise ValueError('Observation bundle must remain inside the candidate directory')
                observation, review = bundle/'observation.json', bundle/'review.json'
                if (digest_file(observation) != item['observation_sha256']
                        or digest_file(review) != item['review_sha256']):
                    raise ValueError('Observation manifest or review bytes changed')
                manifest = read(observation)
                if any(Path(frame.get('file') or '').name != frame.get('file')
                       for frame in manifest.get('frames') or []):
                    raise ValueError('Observation frame names must remain inside their bundle')
                if (manifest.get('source_sha256') != expected[item['source_id']]['sha256']
                        or Path(manifest.get('source') or '').resolve() != self.path(expected[item['source_id']]['uri'])
                        or not manifest.get('frames') or not all(
                            (bundle/frame['file']).is_file() and
                            digest_file(bundle/frame['file']) == frame['sha256']
                            for frame in manifest['frames'])):
                    raise ValueError('Observation frames or source binding changed')
                from .v51_observe_video import record_review
                with tempfile.TemporaryDirectory() as temporary:
                    cloned = Path(temporary)/'bundle'
                    shutil.copytree(bundle, cloned)
                    normalized = record_review(cloned, cloned/'review.json')
                    if digest_file(cloned/'review.json') != item['review_sha256']:
                        raise ValueError('Observation review must be finalized before submission')
                    if normalized['visual_review'] != 'SAMPLED_FRAMES_REVIEWED':
                        raise ValueError('Reference frames have no complete sampled-frame review')
        else:
            raise ValueError('Task is not a graph-only candidate')

    def _promote_graph_only_candidate(self, record: dict) -> None:
        self._validate_graph_only_candidate(record)
        if record['envelope']['node_id'] != 'reference_observation':
            return
        candidate = record['candidate']
        artifact = next(item for item in candidate['artifacts'] if item['kind'] == 'ObservationRegister')
        for item in read(self.path(artifact['uri']))['bundles']:
            result = self.v5.import_observation(self.path(item['directory']))
            if result.get('status') != 'REGISTERED':
                raise ValueError('Native reference observation import failed')

    def agent_review(self, review: dict, *, command_id: str, expected_revision: int) -> dict:
        replay = self._replayed_submission(command_id, review['task_id'], expected_revision,
                                           reason='REVIEW_PASSED', field='review', value=review,
                                           failure_reason='REVIEW_FAILED')
        if replay is not None:
            return replay
        snapshot, record = self._task_record(review['task_id'])
        if snapshot['revision'] != expected_revision or record['state'] != 'REVIEW_REQUIRED':
            raise ValueError('Review is stale or task is not awaiting review')
        validate_v6_protocol('review-record', review, self.skill_root)
        receipt = record.get('review_dispatch') or {}
        if (review['batch'] != record['envelope']['batch']
                or review['candidate_digest'] != candidate_digest(record['candidate'])
                or review['reviewer_agent_id'] != receipt.get('agent_id')
                or review['reviewer_dispatch_id'] != receipt.get('dispatch_id')
                or review['reviewer_agent_id'] == (record.get('receipt') or {}).get('agent_id')):
            raise ValueError('Review identity or candidate binding differs from current dispatch')
        self.kernel._require_origin_result(record, review['reviewer_agent_id'], review)
        self.kernel._check_ids(review['checks'], record['envelope']['validators'], 'id', 'REVIEW_COVERAGE')
        if any(item['status'] == 'FAIL' for item in review['checks']):
            if review['failure_owner'] is None:
                raise ValueError('Failed review must identify a responsible node')
            owner = review['failure_owner']
            if owner != record['envelope']['node_id']:
                node_specs = {item['id']: item for item in self.graph['nodes']}
                if (owner not in self._ancestor_nodes(record['envelope']['node_id'])
                        or node_specs.get(owner, {}).get('executor_kind') != 'specialist'):
                    raise ValueError('Review failure owner must be the current node or an upstream specialist')
            return self._record_failure(review['task_id'], ValueError('Independent review failed'),
                                        command_id=command_id, review=review,
                                        reason='REVIEW_FAILED')
        if review['failure_owner'] is not None:
            raise ValueError('Passing review cannot assign a failure owner')
        try:
            with transaction(self.root):
                if record['envelope']['node_id'] in ('reference_observation', 'compile'):
                    self._promote_graph_only_candidate(record)
                else:
                    self._validate_v5_candidate(record)
                    self._restore_parallel_native_task(record)
                    path = self.root/record['candidate']['result_uri']
                    imported = self.v5.submit(str(path))
                    if imported.get('status') not in ('ACCEPTED', 'ALREADY_ACCEPTED') or imported.get('task_id') != review['task_id']:
                        raise ValueError('Native task did not pass its completion gate')
                refreshed = self.kernel.snapshot()['tasks'][review['task_id']]
                self.kernel.record_review(self._event(refreshed, 'ACCEPTED', 'REVIEW_PASSED',
                                                      command_id=command_id, checks=review['checks'],
                                                      evidence=[item['uri'] for item in record['candidate']['artifacts']]), review)
                if record['candidate']['result_uri']:
                    native_result = read(self.path(record['candidate']['result_uri']))
                    if native_result.get('reused'):
                        native_task = read(self.path('runtime/tasks/'+review['task_id']+'.json'))
                        state = self.v5.state
                        if native_task['kind'] == 'image-prompt':
                            state['prompts'][native_task['slot']]['audit'] = 'audited'
                        elif native_task['slot'] in state['artifacts']:
                            state['artifacts'][native_task['slot']].pop('needs_review', None)
                            state['artifacts'][native_task['slot']]['audit'] = 'audited'
                        self.v5.save(state)
        except (ValueError, OSError) as error:
            return self._record_failure(review['task_id'], error, command_id=command_id,
                                        review=review, reason='REVIEW_FAILED')
        return self.run()

    def agent_reconcile(self, task_id: str, observation: dict, *, command_id: str,
                        expected_revision: int) -> dict:
        from .v6_codex_host import CodexHostBridge, replay_registered_command
        replay = replay_registered_command(self.kernel, command_id, expected_revision,
                                           'agent-reconcile', {'task_id': task_id,
                                                               'observation': observation})
        if replay is not None:
            return replay
        return CodexHostBridge(self.kernel).reconcile(task_id, observation,
                                                       command_id=command_id,
                                                       expected_revision=expected_revision)

    def status(self) -> dict:
        base = self.v5.status()
        snapshot = self.kernel.snapshot()
        active = [row for row in snapshot['tasks'].values() if row['state'] not in _TERMINAL]
        waiting_host = {'DISPATCHING', 'UNKNOWN', 'REVIEW_REQUIRED'}
        project_scope = self._project_scope()

        def latest_stage(node_id: str) -> dict | None:
            rows = [row for row in snapshot['tasks'].values()
                    if row['envelope']['node_id'] == node_id
                    and row['envelope']['scope'] == project_scope]
            return max(rows, key=lambda row: (row['envelope']['input_revision'],
                                                row['envelope']['batch'])) if rows else None

        preproduction = latest_stage('preproduction_delivery')
        video = latest_stage('video_delivery')
        preproduction_accepted = bool(preproduction and preproduction['state'] == 'ACCEPTED')
        video_accepted = bool(video and video['state'] == 'ACCEPTED')
        target = self.production_target()
        native_status = base.get('status')
        native_preproduction_complete = (
            native_status in ('PREPRODUCTION_DELIVERED', 'VIDEO_DELIVERED')
            if target == 'video' else native_status == 'DELIVERED')
        native_video_complete = target == 'video' and native_status == 'VIDEO_DELIVERED'
        delivery_consistent = (preproduction_accepted == native_preproduction_complete
                               and video_accepted == native_video_complete)
        preproduction_complete = preproduction_accepted and native_preproduction_complete
        video_complete = video_accepted and native_video_complete
        if any(row['state'] == 'UNKNOWN' for row in active):
            status = 'RECONCILE_REQUIRED'
        elif any(row['state'] in waiting_host for row in active):
            status = 'AWAITING_HOST'
        elif active:
            status = 'AWAITING_RESULT'
        elif delivery_consistent and video_complete:
            status = 'VIDEO_DELIVERED'
        elif delivery_consistent and preproduction_complete:
            status = 'PREPRODUCTION_DELIVERED' if target == 'video' else 'DELIVERED'
        elif not delivery_consistent:
            status = 'BLOCKED'
        elif any(row['state'] in ('STALE', 'FAILED', 'BLOCKED') for row in snapshot['tasks'].values()):
            status = 'BLOCKED'
        else:
            status = base['status']
        return {**base, 'status': status, 'execution_mode': 'codex-agents',
                'orchestration_protocol': '6.0', 'v6_revision': snapshot['revision'],
                'preproduction_complete': preproduction_complete,
                'video_complete': video_complete,
                'v6_tasks': {task_id: {'node_id': row['envelope']['node_id'], 'state': row['state']}
                             for task_id, row in snapshot['tasks'].items()}}

    def validate(self, final: bool = False) -> dict:
        native = self.v5.validate(final)
        snapshot = self.kernel.snapshot()
        errors = list(native['errors'])
        if final:
            for node in self.graph['nodes']:
                try:
                    if node['id'] in ('video_freeze', 'video_execution', 'take_recovery',
                                      'shot_acceptance', 'take_selection', 'adjacent_acceptance',
                                      'assembly', 'whole_acceptance', 'video_delivery') and self.production_target() == 'video':
                        from .v6_production_runtime import V6ProductionRuntime
                        scopes = V6ProductionRuntime(self)._catalogue(node['id'])[node['id']]
                    else:
                        scopes = self._scopes(node['id'])
                    required = {(scope['kind'], tuple(scope['ids'])) for scope in scopes}
                    rows = [row for row in snapshot['tasks'].values()
                            if row['envelope']['node_id'] == node['id'] and row['state'] != 'STALE']
                    actual = {(row['envelope']['scope']['kind'], tuple(row['envelope']['scope']['ids']))
                              for row in rows}
                    if not required or actual != required:
                        raise ValueError('scope coverage differs from current frozen inputs')
                    for scope in required:
                        matches = [row for row in rows if (row['envelope']['scope']['kind'],
                                   tuple(row['envelope']['scope']['ids'])) == scope]
                        latest = max(matches, key=lambda row: (row['envelope']['input_revision'],
                                                                 row['envelope']['batch']))
                        if latest['state'] not in ('ACCEPTED', 'NOT_APPLICABLE'):
                            raise ValueError('latest task is '+latest['state'])
                        applies, _ = self.kernel._stage_applies(latest['envelope'])
                        if (latest['state'] == 'ACCEPTED') != applies:
                            raise ValueError('completion state differs from graph applicability')
                        if latest['state'] == 'ACCEPTED':
                            if self.kernel._input_changed(latest['envelope'], accepted=True):
                                raise ValueError('accepted task has stale input, module or native review')
                except (ValueError, OSError, KeyError) as exc:
                    errors.append('V6 stage incomplete: '+node['id']+' ('+str(exc)+')')
        return {**native, 'valid': not errors, 'errors': errors,
                'orchestration_protocol': '6.0', 'v6_revision': snapshot['revision']}

    def transition_video_delivered(self, evidence: dict) -> dict:
        """Commit final graph evidence and native VIDEO_DELIVERED in one transaction."""
        from .production import ProductionLedger
        from .v6_production_runtime import V6ProductionRuntime
        if self.production_target() != 'video' or set(evidence) != {
                'delivery_manifest_sha256', 'production_integrity'} or evidence['production_integrity'] != 'PASS':
            raise ValueError('Video delivery evidence differs from the frozen production target')
        with transaction(self.root):
            ledger = ProductionLedger(self)
            blockers = ledger.video_delivery_blockers()
            if blockers:
                return {'status': 'BLOCKED', 'errors': blockers}
            manifest_uri = 'runtime/production/delivery-manifest.json'
            manifest = read(self.path(manifest_uri))
            if manifest['sha256'] != evidence['delivery_manifest_sha256']:
                raise ValueError('Video delivery evidence binds a different frozen manifest')
            rows = self._stage_rows('video_delivery')
            accepted = [row for row in rows if row['state'] == 'ACCEPTED']
            if accepted:
                if self.v5.state['status'] != 'VIDEO_DELIVERED':
                    raise ValueError('Video graph and native delivery state disagree')
                return {'status': 'VIDEO_DELIVERED'}
            scope = self._project_scope()
            task_id = 'V6_video_delivery_'+_hash({'manifest': manifest['sha256']})[:20]
            envelope = self.create_graph_task('video_delivery', scope, task_id,
                required_scopes=V6ProductionRuntime(self)._catalogue('video_delivery'),
                extra_inputs=[{'slot': 'delivery_manifest', 'uri': manifest_uri,
                               'sha256': digest_file(self.path(manifest_uri)), 'version': 0}])
            uri = f'runtime/v6/candidates/{task_id}/1/video-delivery.json'
            self.write(uri, {'schema': 'video-delivery/6.0',
                             'delivery_manifest_sha256': manifest['sha256'],
                             'production_integrity': 'PASS'})
            checks = [{'id': 'video_final', 'status': 'PASS',
                       'evidence': [manifest_uri, uri]}]
            candidate = {'schema': 'candidate-result/6.0', 'task_id': task_id,
                         'batch': 1, 'agent_id': 'kernel',
                         'input_digest': envelope['input_digest'],
                         'result_uri': None, 'result_sha256': None,
                         'artifacts': [{'slot': envelope['expected_artifacts'][0]['slot'],
                                        'kind': 'VideoDelivery', 'uri': uri,
                                        'sha256': digest_file(self.path(uri))}],
                         'module_receipts': [], 'checks': checks,
                         'handoffs': [], 'unresolved': []}
            record = self.kernel.snapshot()['tasks'][task_id]
            self.kernel.transition(self._event(record, 'ACCEPTED', 'SYSTEM_VALIDATED',
                                               command_id='accept-'+task_id,
                                               checks=checks, evidence=[manifest_uri, uri]),
                                   candidate=candidate)
            final = self.validate(final=True)
            if not final['valid']:
                raise ValueError('V6 video graph completion failed: '+'; '.join(final['errors']))
            state = self.v5.state
            state['status'] = 'VIDEO_DELIVERED'
            self.v5.save(state)
            return {'status': 'VIDEO_DELIVERED', 'task_id': task_id,
                    'revision': self.kernel.snapshot()['revision']}

    def export(self, draft: bool = False) -> dict:
        report = self.validate(final=True)
        if not report['valid'] and not draft:
            return {'status': 'BLOCKED', 'validation': report}
        if draft:
            return self.v5.export(draft=True)
        if not any(row['state'] == 'ACCEPTED' for row in self._stage_rows('preproduction_delivery')):
            return {'status': 'BLOCKED', 'reason': 'Preproduction delivery graph task is not accepted'}
        return {'status': self.v5.state['status'], 'index': str(self.path('delivery/index.md')),
                'validation': report}

    def v5_command(self, args) -> dict:
        """Allow only native input/capability changes through the V6 gateway.

        Candidate import, direct submit and compilation would bypass V6 review.
        """
        name = args.command
        if name in {'submit', 'import-artifact', 'import-compiled', 'compile',
                    'begin-image', 'recover-image', 'import-observation'}:
            raise ValueError(name + ' requires a V6 candidate, review or host recovery event')
        if self._active():
            raise ValueError('Resolve, cancel or reconcile the active V6 task before changing native inputs')
        if name == 'host':
            with transaction(self.root):
                self._archive_project_evidence()
                info = read(Path(args.capabilities))
                return self.v5.host(info['image_capability'], info['evidence'],
                                    info.get('video_capabilities'), info.get('image_tools'))
        if name == 'request-decision':
            return self.v5.request_decision(args.proposal)
        if name == 'resume':
            with transaction(self.root):
                self._archive_project_evidence()
                result = self.v5.resume(args.decision)
                stale = self._stale_changed_inputs()
                return {**result, 'v6_stale_tasks': stale}
        if name == 'revise':
            with transaction(self.root):
                self._archive_project_evidence()
                result = self.v5.revise(args.kind, shot_id=args.shot_id, action_id=args.action_id,
                                        node_id=args.node_id, track_id=args.track_id,
                                        scene_id=args.scene_id, asset_id=args.asset_id,
                                        target=args.target, mode=args.mode)
                stale = self._stale_changed_inputs()
                return {**result, 'v6_stale_tasks': stale}
        if name == 'add':
            with transaction(self.root):
                self._archive_project_evidence()
                result = self.v5.add(args.inputs)
                stale = self._stale_changed_inputs()
                return {**result, 'v6_stale_tasks': stale}
        if name == 'update-modules':
            with transaction(self.root):
                self._archive_project_evidence()
                result = self.v5.update_modules(args.lock, args.archives)
                stale = self._stale_changed_inputs()
                return {**result, 'v6_stale_tasks': stale}
        raise ValueError('Unsupported V6 command: ' + name)


def task_file_ref(root: Path, task: dict) -> str:
    return str(root/'runtime/tasks'/(task['task_id']+'.json'))
