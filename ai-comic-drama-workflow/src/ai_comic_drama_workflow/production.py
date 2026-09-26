"""Append-only production ledger. Compile artifacts stay unchanged."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import zipfile

from .acceptance import verify_plan
from .assembly import _probe, validate_edl
from .transactions import transaction
from .v5_modules import digest_file, read
from .v5_protocol import validate_protocol

REMEDIES = ('换执行通道', '补资产', '调整允许变化的镜头设计', '交由后期完成')
EXECUTION_TRANSITIONS = {
    'SUBMITTING': {'SUBMITTED', 'SUCCEEDED', 'FAILED', 'UNKNOWN'},
    'SUBMITTED': {'SUCCEEDED', 'FAILED', 'UNKNOWN'},
    'UNKNOWN': {'SUBMITTED', 'SUCCEEDED', 'FAILED'},
    'SUCCEEDED': set(), 'FAILED': set(),
}


def _sha(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def channel_registry(skill_root):
    skill_root = Path(skill_root)
    archive = skill_root / 'assets' / 'bundled-skills' / 'video-prompt-compiler.skill'
    lock = read(skill_root / 'modules.lock.json')['modules']['video-prompt-compiler']
    if not archive.is_file() or digest_file(archive) != lock['sha256']:
        raise ValueError('Locked video channel module is missing or changed')
    with zipfile.ZipFile(archive) as bundle:
        raw = bundle.read('video-prompt-compiler/registries/control-capabilities.json')
    return json.loads(raw)


def normalize_video_capabilities(items, registry=None, skill_root=None):
    """Register only channels that already exist in the control registry."""
    if registry is None:
        registry = channel_registry(skill_root or Path(__file__).resolve().parents[2])
    known = {(r['model'], r['mode'], r['surface']): r for r in registry['routes']}
    if not isinstance(items, list):
        raise ValueError('video_capabilities must be a list')
    recorded = []
    for item in items:
        key = (item.get('model'), item.get('mode'), item.get('surface', 'API'))
        route = known.get(key)
        if route is None:
            raise ValueError('Unregistered video channel: ' + str(key))
        recorded.append({
            'model': route['model'], 'mode': route['mode'], 'surface': route['surface'],
            'channels': list(route['channels']),
            'probe_passed': bool(route.get('probe_passed')),
            'quality_validated': bool(route.get('quality_validated')),
            'evidence': item.get('evidence'),
        })
    return recorded


def _verify_frozen_post_audio(spec):
    tracks = spec.get('post_audio', [])
    if not isinstance(tracks, list):
        raise ValueError('Frozen post audio must be a list')
    for track in tracks:
        if (not isinstance(track, dict) or set(track) not in ({'source', 'sha256', 'start_ms'},
                {'source', 'sha256', 'start_ms', 'gain'}) or
            not isinstance(track.get('source'), str) or not track['source'] or
            type(track.get('start_ms')) is not int or track['start_ms'] < 0 or
            type(track.get('gain', 1)) not in (int, float) or track.get('gain', 1) < 0):
            raise ValueError('Frozen post audio track fields are invalid')
        source = Path(track['source'])
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != track.get('sha256'):
            raise ValueError('Frozen post audio track bytes differ from its hash')


class ProductionLedger:
    def __init__(self, kernel):
        self.kernel = kernel
        self.root = Path(kernel.root) / 'runtime' / 'production'

    @property
    def strict(self):
        return self.kernel.project.get('orchestration_protocol') == '6.0'

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def _path(self, relative):
        return self.kernel.path('runtime/production/' + relative)

    def _write(self, relative, value, protocol):
        with transaction(self.kernel.root):
            if protocol:
                validate_protocol(protocol, value, self.kernel.skill_root)
            path = self._path(relative)
            if path.exists():
                raise ValueError('Production records are append-only: ' + relative)
            self.kernel.write('runtime/production/' + relative, value)
        return value

    def _load(self, relative):
        return read(self._path(relative))

    def jobs(self):
        folder = self.root / 'jobs'
        if not folder.is_dir():
            return []
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('*.json'))]

    def records(self, job_id=None):
        folder = self.root / 'executions'
        if not folder.is_dir():
            return []
        rows = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('*.json'))]
        return [r for r in rows if job_id is None or r['job_id'] == job_id]

    def takes(self):
        folder = self.root / 'takes'
        if not folder.is_dir():
            return []
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('*.json'))]

    def plan_job(self, request, compile_sha256, attachments, shot_ids, budget, *, compile_path=None):
        if self.strict and self._path('delivery-manifest.json').exists():
            raise ValueError('Cannot add an execution job after delivery scope is frozen')
        payload = request['payload_draft']
        if request.get('submitted') is not False:
            raise ValueError('Refusing to plan from a compile artifact that claims submission')
        if not isinstance(payload, dict) or not payload:
            raise ValueError('Compiled request has no executable payload draft')
        if self.strict and (request.get('status') != 'COMPILED_DRAFT' or request.get('reasons') != []):
            raise ValueError('Protocol 6.0 execution requires a compiled request without blockers')
        if not isinstance(shot_ids, list) or (self.strict and not shot_ids) or len(set(shot_ids)) != len(shot_ids):
            raise ValueError('Job needs a unique, nonempty shot scope')
        declared = request.get('scope', {}).get('shot_ids')
        if declared is not None and declared != shot_ids:
            raise ValueError('Job shot scope differs from compiled request')
        scope = request.get('scope') or {}
        if self.strict and (set(scope) != {'shot_ids', 'start_ms', 'end_ms'} or
                            not isinstance(scope['start_ms'], int) or not isinstance(scope['end_ms'], int) or
                            scope['start_ms'] < 0 or scope['end_ms'] <= scope['start_ms']):
            raise ValueError('Protocol 6.0 needs a frozen compiled request time scope')
        if not isinstance(attachments, list) or any(not isinstance(a, dict) or not a.get('sha256') or not a.get('url') for a in attachments):
            raise ValueError('Attachments require URL and frozen byte hash')
        if self.strict and attachments != request.get('attachment_index', []):
            raise ValueError('Attachments differ from frozen compiled request')
        if budget['max_attempts'] < 1 or budget['project_cap'] < 1:
            raise ValueError('Execution budget must be positive')
        authorization_sha256 = None
        if self.strict and budget['max_attempts'] > 1:
            authorization = budget.get('authorization')
            source = Path(authorization).resolve() if isinstance(authorization, str) and authorization else None
            if source is None or not source.is_file():
                raise ValueError('More than one generation attempt needs recorded budget authorization')
            approval = read(source)
            if (not isinstance(approval, dict) or set(approval) != {'decision', 'request_id', 'max_attempts', 'project_cap', 'actor', 'evidence'} or
                approval['decision'] != 'APPROVED' or approval['request_id'] != request['id'] or
                type(approval['max_attempts']) is not int or type(approval['project_cap']) is not int or
                approval['max_attempts'] < budget['max_attempts'] or approval['project_cap'] < budget['project_cap'] or
                not isinstance(approval['actor'], str) or not approval['actor'] or
                not isinstance(approval['evidence'], str) or not approval['evidence']):
                raise ValueError('Budget authorization does not approve this request and limit')
            authorization_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        compile_verified = False
        compile_uri = None
        if compile_path is not None:
            source = Path(compile_path).resolve()
            if not source.is_file():
                raise ValueError('Compiled manifest is missing')
            frozen_bytes = source.read_bytes()
            if hashlib.sha256(frozen_bytes).hexdigest() != compile_sha256:
                raise ValueError('Compiled manifest differs from frozen hash')
            try:
                compiled = json.loads(frozen_bytes)
            except json.JSONDecodeError as exc:
                raise ValueError('Compiled manifest is not JSON') from exc
            if not isinstance(compiled, dict) or not isinstance(compiled.get('requests'), list) or request not in compiled['requests']:
                raise ValueError('Execution request is not an exact member of the frozen compiled manifest')
            if self.strict and (compiled.get('status') != 'COMPILED_DRAFT' or compiled.get('submitted') is not False):
                raise ValueError('Protocol 6.0 execution needs an unsubmitted, fully compiled manifest')
            compile_verified = True
            compile_uri = str(source)
        elif self.strict:
            raise ValueError('Protocol 6.0 requires the frozen compiled manifest file')
        route = 'MANUAL'
        if payload.get('model') and payload.get('mode'):
            route = next((r['entry'] for r in channel_registry(self.kernel.skill_root)['routes']
                          if r['model'] == payload['model'] and r['mode'] == payload['mode'] and r['surface'] == 'API'), None)
            if route is None:
                raise ValueError('Execution route is not registered')
        job_id = 'JOB_' + _sha({'compile': compile_sha256, 'request': request['id'], 'payload': payload,
                                'attachments': attachments, 'shot_ids': shot_ids})[:16]
        job = {
            'schema_version': 'v5-generation-job/1.0', 'id': job_id, 'request_id': request['id'],
            'compile_sha256': compile_sha256, 'request_sha256': _sha(request),
            'payload_sha256': _sha(payload), 'payload': payload,
            'attachments': attachments, 'shot_ids': list(shot_ids), 'state': 'FROZEN',
            'scope': scope,
            'budget': {'max_attempts': budget['max_attempts'], 'project_cap': budget['project_cap'],
                       **({'authorization': str(Path(budget['authorization']).resolve()),
                           'authorization_sha256': authorization_sha256} if authorization_sha256 else {})},
            'compile_uri': compile_uri, 'compile_verified': compile_verified, 'route': route,
        }
        return self._write('jobs/' + job_id + '.json', job, 'generation-job')

    def _budget_block(self, job):
        attempts = [r for r in self.records(job['id']) if r['state'] in ('SUBMITTED', 'SUCCEEDED', 'FAILED', 'UNKNOWN', 'SUBMITTING')]
        calls = [r for r in self.records() if r['automatic'] and r['state'] != 'FROZEN']
        if len(attempts) >= job['budget']['max_attempts'] or len(calls) >= job['budget']['project_cap']:
            return {'status': 'BLOCKED_BUDGET', 'remedies': list(REMEDIES), 'job_id': job['id']}
        return None

    def begin_submit(self, job_id, automatic=True, authorized=False):
        with transaction(self.kernel.root):
            job = self._load('jobs/' + job_id + '.json')
            self._verify_job(job)
            if self.strict and not job['compile_verified']:
                raise ValueError('Frozen compiled manifest was not verified')
            if automatic and job['route'] == 'MANUAL':
                raise ValueError('Job has no registered automatic execution route')
            current = self.records(job_id)
            if any(r['state'] in ('UNKNOWN', 'SUBMITTED', 'SUBMITTING') for r in current):
                raise ValueError('Unresolved execution must be reconciled before another attempt')
            if authorized and self.strict:
                raise ValueError('Authorization does not override an unresolved execution')
            blocked = self._budget_block(job)
            if blocked:
                return blocked
            record_id = 'EXE_' + _sha({'job': job_id, 'n': len(current)})[:16]
            record = {'schema_version': 'v5-execution-record/1.0', 'id': record_id,
                      'job_id': job_id, 'state': 'SUBMITTING', 'task_id': None,
                      'automatic': automatic, 'version': 0, 'created_at': self._now()}
            self._write('executions/' + record_id + '.json', record, 'execution-record')
            self._write('execution-events/' + record_id + '/0000.json',
                        {'record_id': record_id, 'version': 0, 'from': None, 'to': 'SUBMITTING',
                         'at': record['created_at'], 'record_sha256': _sha(record), 'record': record}, None)
            return record

    def _replace_state(self, record_id, state, **extra):
        with transaction(self.kernel.root):
            old = self._load('executions/' + record_id + '.json')
            if state not in EXECUTION_TRANSITIONS.get(old['state'], set()):
                raise ValueError('Illegal execution transition: ' + old['state'] + ' -> ' + state)
            record = dict(old)
            record.update(extra)
            record['state'] = state
            record['version'] = old['version'] + 1
            record['updated_at'] = self._now()
            if state != 'UNKNOWN':
                record.pop('reason', None)
                record.pop('resubmit', None)
            if state != 'FAILED':
                record.pop('error', None)
            validate_protocol('execution-record', record, self.kernel.skill_root)
            event = {'record_id': record_id, 'version': record['version'], 'from': old['state'],
                     'to': state, 'at': record['updated_at'], 'previous_sha256': _sha(old),
                     'record_sha256': _sha(record), 'record': record}
            relative = 'execution-events/' + record_id + '/' + f"{record['version']:04d}.json"
            self._write(relative, event, None)
            self.kernel.write('runtime/production/executions/' + record_id + '.json', record)
            return record

    def mark_submitted(self, record_id, task_id):
        if not task_id:
            raise ValueError('task_id is required')
        return self._replace_state(record_id, 'SUBMITTED', task_id=task_id)

    def register_external_execution(self, record_id, evidence):
        with transaction(self.kernel.root):
            record = self._load('executions/' + record_id + '.json')
            if record['automatic'] or record['state'] != 'SUBMITTING':
                raise ValueError('External execution receipt requires a pending manual record')
            job = self._load('jobs/' + record['job_id'] + '.json')
            required = {'channel', 'external_task_id', 'request_id', 'payload_sha256',
                        'attachment_sha256s', 'proof_uri', 'proof_sha256'}
            if not isinstance(evidence, dict) or set(evidence) != required:
                raise ValueError('External execution receipt fields are incomplete or unknown')
            if not evidence['channel'] or not evidence['external_task_id'] or evidence['request_id'] != job['request_id'] or evidence['payload_sha256'] != job['payload_sha256']:
                raise ValueError('External execution receipt does not match frozen job')
            if evidence['attachment_sha256s'] != [item['sha256'] for item in job['attachments']]:
                raise ValueError('External execution attachment bytes do not match frozen job')
            proof = Path(evidence['proof_uri'])
            if not proof.is_file() or hashlib.sha256(proof.read_bytes()).hexdigest() != evidence['proof_sha256']:
                raise ValueError('External execution proof bytes differ from hash')
            self._write('external-executions/' + record_id + '.json', evidence, None)
            return self.mark_submitted(record_id, evidence['external_task_id'])

    def mark_failed(self, record_id, error):
        if not error:
            raise ValueError('Failure evidence is required')
        return self._replace_state(record_id, 'FAILED', error=error)

    def mark_unknown(self, record_id, reason):
        return self._replace_state(record_id, 'UNKNOWN', reason=reason, resubmit=False)

    def save_take(self, job_id, record_id, file_path, probe, automatic):
        with transaction(self.kernel.root):
            job = self._load('jobs/' + job_id + '.json')
            self._verify_job(job)
            record = self._load('executions/' + record_id + '.json')
            if record['job_id'] != job_id or record['automatic'] != automatic:
                raise ValueError('Take execution identity does not match its job')
            if record['state'] not in ('SUBMITTED', 'SUBMITTING', 'UNKNOWN'):
                raise ValueError('Execution cannot receive a take in state ' + record['state'])
            if automatic and record['state'] == 'SUBMITTING':
                raise ValueError('Automatic take needs a submitted task ID')
            data = Path(file_path).read_bytes()
            if not data:
                raise ValueError('Take file is empty')
            digest = hashlib.sha256(data).hexdigest()
            if probe.get('sha256') not in (None, digest):
                raise ValueError('Take probe hash differs from media bytes')
            actual = _probe(file_path) if self.strict else None
            if actual is not None:
                for key in ('width', 'height', 'fps', 'duration_ms'):
                    if key in probe and actual[key] != probe[key]:
                        raise ValueError('Take declared probe differs from local probe: ' + key)
            take_id = 'TAKE_' + _sha({'job': job_id, 'record': record_id, 'file': digest})[:16]
            uri = 'runtime/production/media/' + take_id + Path(file_path).suffix
            take = {'schema_version': 'v5-take/1.0', 'id': take_id, 'job_id': job_id,
                    'record_id': record_id, 'sha256': digest, 'uri': uri,
                    'automatic': automatic, 'probe': actual or probe,
                    'probe_verified': actual is not None, 'accepted': False}
            self._write('takes/' + take_id + '.json', take, 'take')
            self.kernel.write(uri, data)
            self._replace_state(record_id, 'SUCCEEDED', take_id=take_id)
            return take

    def _verify_job(self, job):
        validate_protocol('generation-job', job, self.kernel.skill_root)
        if self.strict and job['budget']['max_attempts'] > 1:
            approval_path = Path(job['budget'].get('authorization', ''))
            if (not approval_path.is_file() or hashlib.sha256(approval_path.read_bytes()).hexdigest() !=
                    job['budget'].get('authorization_sha256')):
                raise ValueError('Budget authorization evidence bytes changed')
            approval = read(approval_path)
            if (approval.get('decision') != 'APPROVED' or approval.get('request_id') != job['request_id'] or
                approval.get('max_attempts', 0) < job['budget']['max_attempts'] or
                approval.get('project_cap', 0) < job['budget']['project_cap']):
                raise ValueError('Budget authorization no longer matches frozen job')
        if _sha(job['payload']) != job['payload_sha256']:
            raise ValueError('Frozen execution payload differs from its hash')
        if job.get('compile_verified'):
            source = Path(job['compile_uri'])
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != job['compile_sha256']:
                raise ValueError('Frozen compiled manifest has changed')
            compiled = read(source)
            if not isinstance(compiled.get('requests'), list) or not any(_sha(item) == job['request_sha256'] and
                    item.get('id') == job['request_id'] and item.get('payload_draft') == job['payload'] and
                    item.get('attachment_index', []) == job['attachments'] and item.get('scope', {}) == job['scope']
                    for item in compiled['requests']):
                raise ValueError('Frozen compiled request does not match execution job')
        return True

    def freeze_delivery_manifest(self, shot_ids, plan, obligations=(), output_spec=None, *, shot_ranges=None):
        verify_plan(plan, plan['sha256'])
        if not isinstance(shot_ids, list) or not shot_ids or len(set(shot_ids)) != len(shot_ids):
            raise ValueError('Delivery needs an ordered set of unique shots')
        if any(set(item['shot_ids']) - set(shot_ids) for item in plan['items']):
            raise ValueError('Acceptance plan references shots outside frozen delivery scope')
        for shot in shot_ids:
            if not any(item['hard'] and (not item['shot_ids'] or shot in item['shot_ids']) for item in plan['items']):
                raise ValueError('Frozen shot has no hard acceptance check: ' + shot)
        if self.strict:
            if not isinstance(shot_ranges, dict) or set(shot_ranges) != set(shot_ids):
                raise ValueError('Every frozen shot needs its project time range')
            previous_end = 0
            jobs = self.jobs()
            for shot in shot_ids:
                span = shot_ranges[shot]
                if (not isinstance(span, dict) or set(span) != {'start_ms', 'end_ms'} or
                    not isinstance(span['start_ms'], int) or not isinstance(span['end_ms'], int) or
                    span['start_ms'] != previous_end or span['end_ms'] <= span['start_ms']):
                    raise ValueError('Frozen shot ranges must be positive and contiguous in project time')
                if not any(shot in job['shot_ids'] and job['scope']['start_ms'] <= span['start_ms'] and
                           job['scope']['end_ms'] >= span['end_ms'] for job in jobs):
                    raise ValueError('Frozen shot time range is outside every compiled execution request')
                previous_end = span['end_ms']
        if any(not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'] or
               row.get('kind') not in ('audio', 'subtitle', 'graphics', 'color', 'other') or
               (self.strict and set(row) != {'id', 'kind'}) for row in obligations):
            raise ValueError('Post obligations need an ID and supported kind')
        if len({row['id'] for row in obligations}) != len(obligations):
            raise ValueError('Duplicate post obligation IDs')
        if self.strict and (not isinstance(output_spec, dict) or any(key not in output_spec for key in ('width', 'height', 'fps'))):
            raise ValueError('Video delivery needs frozen width, height and frame rate')
        if self.strict and (any(not isinstance(output_spec[key], (int, float)) or output_spec[key] <= 0 for key in ('width', 'height', 'fps')) or
                            not isinstance(output_spec.get('preserve_native_audio'), bool)):
            raise ValueError('Video delivery needs numeric size/frame rate and explicit native audio policy')
        if self.strict:
            _verify_frozen_post_audio(output_spec)
        if self.strict and any(item['hard'] and not item['checks'] for item in plan['items']):
            raise ValueError('Hard acceptance clauses need executable checks')
        manifest = {'schema': 'video-delivery-manifest/1.0', 'shot_ids': shot_ids,
                    'plan_sha256': plan['sha256'], 'obligations': list(obligations),
                    'output_spec': output_spec or {}, 'shot_ranges': shot_ranges or {},
                    'job_ids': [job['id'] for job in self.jobs() if set(job['shot_ids']) <= set(shot_ids)]}
        manifest['sha256'] = _sha({k: v for k, v in manifest.items() if k != 'sha256'})
        with transaction(self.kernel.root):
            self._write('acceptance-plans/' + plan['sha256'] + '.json', plan, None)
            return self._write('delivery-manifest.json', manifest, None)

    def select_take(self, shot_id, take_id):
        with transaction(self.kernel.root):
            self.validate_selection(shot_id, take_id)
            take = self._load('takes/' + take_id + '.json')
            row = {'shot_id': shot_id, 'take_id': take_id, 'take_sha256': take['sha256'],
                   'selected_at': self._now()}
            return self._write('selections/' + shot_id + '.json', row, None)

    def validate_selection(self, shot_id, take_id):
        manifest = self._load('delivery-manifest.json')
        self._verify_manifest(manifest)
        if shot_id not in manifest['shot_ids']:
            raise ValueError('Shot is outside frozen delivery scope')
        take = self._load('takes/' + take_id + '.json')
        job = self._load('jobs/' + take['job_id'] + '.json')
        if shot_id not in job['shot_ids']:
            raise ValueError('Take job does not cover selected shot')
        self._verify_take(take)
        folder = self.root / 'acceptance'
        reviews = [read(path) for path in folder.glob('*.json')] if folder.is_dir() else []
        if not any(row.get('level') == 'shot' and row.get('shot_id') == shot_id and
                   row.get('take_ids') == {shot_id: take_id} and row.get('status') == 'PASS'
                   for row in reviews):
            raise ValueError('Selected Take must first pass its shot review')
        return take

    def save_post_obligation(self, obligation_id, evidence):
        manifest = self._load('delivery-manifest.json')
        self._verify_manifest(manifest)
        if obligation_id not in {row['id'] for row in manifest['obligations']} or not isinstance(evidence, dict) or evidence.get('status') != 'PASS':
            raise ValueError('Post obligation needs a frozen ID and evidence')
        source = Path(evidence.get('uri', ''))
        if not source.is_file() or evidence.get('sha256') != hashlib.sha256(source.read_bytes()).hexdigest():
            raise ValueError('Post obligation evidence file differs from registered bytes')
        return self._write('post-obligations/' + obligation_id + '.json',
                           {'id': obligation_id, 'evidence': evidence, 'at': self._now()}, None)

    def _verify_manifest(self, manifest):
        if (not isinstance(manifest, dict) or set(manifest) != {'schema', 'shot_ids', 'plan_sha256',
                'obligations', 'output_spec', 'shot_ranges', 'job_ids', 'sha256'} or
            manifest.get('schema') != 'video-delivery-manifest/1.0' or
            manifest.get('sha256') != _sha({k: v for k, v in manifest.items() if k != 'sha256'})):
            raise ValueError('Frozen delivery manifest content differs from hash')
        if (not isinstance(manifest.get('shot_ids'), list) or not manifest['shot_ids'] or
            any(not isinstance(shot, str) or not shot for shot in manifest['shot_ids']) or
            len(set(manifest['shot_ids'])) != len(manifest['shot_ids'])):
            raise ValueError('Frozen delivery shot order is invalid')
        if self.strict:
            spec = manifest.get('output_spec')
            if (not isinstance(spec, dict) or
                not all(type(spec.get(key)) in (int, float) and spec[key] > 0 for key in ('width', 'height', 'fps')) or
                not isinstance(spec.get('preserve_native_audio'), bool)):
                raise ValueError('Frozen output specification is invalid')
            _verify_frozen_post_audio(spec)
            obligations = manifest.get('obligations')
            if (not isinstance(obligations, list) or any(not isinstance(item, dict) or
                    set(item) != {'id', 'kind'} or not isinstance(item['id'], str) or not item['id'] or
                    item['kind'] not in ('audio', 'subtitle', 'graphics', 'color', 'other')
                    for item in obligations) or
                len({item['id'] for item in obligations}) != len(obligations)):
                raise ValueError('Frozen post obligation catalogue is invalid')
            job_ids = manifest.get('job_ids')
            if (not isinstance(job_ids, list) or not job_ids or
                any(not isinstance(job, str) or not job for job in job_ids) or
                len(set(job_ids)) != len(job_ids)):
                raise ValueError('Frozen delivery job catalogue is invalid')
            jobs = [self._load('jobs/' + job_id + '.json') for job_id in job_ids]
            for job in jobs:
                self._verify_job(job)
                if not set(job['shot_ids']) <= set(manifest['shot_ids']):
                    raise ValueError('Frozen job exceeds delivery shot scope')
            ranges = manifest.get('shot_ranges')
            if not isinstance(ranges, dict) or set(ranges) != set(manifest['shot_ids']):
                raise ValueError('Frozen delivery time coverage is incomplete')
            previous_end = 0
            for shot in manifest['shot_ids']:
                span = ranges[shot]
                if (not isinstance(span, dict) or set(span) != {'start_ms', 'end_ms'} or
                    type(span['start_ms']) is not int or type(span['end_ms']) is not int or
                    span['start_ms'] != previous_end or span['end_ms'] <= span['start_ms']):
                    raise ValueError('Frozen delivery time ranges are not contiguous')
                if not any(shot in job['shot_ids'] and job['scope']['start_ms'] <= span['start_ms'] and
                           job['scope']['end_ms'] >= span['end_ms'] for job in jobs):
                    raise ValueError('Frozen shot range has no matching execution job')
                previous_end = span['end_ms']
        plan = self._load('acceptance-plans/' + manifest['plan_sha256'] + '.json')
        verify_plan(plan, manifest['plan_sha256'])
        if any(set(item['shot_ids']) - set(manifest['shot_ids']) for item in plan['items']):
            raise ValueError('Frozen acceptance plan has a shot outside delivery')
        return plan

    def _verify_take(self, take):
        validate_protocol('take', take, self.kernel.skill_root)
        path = self.kernel.path(take['uri'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != take['sha256']:
            raise ValueError('Registered take bytes differ from frozen hash')
        record = self._load('executions/' + take['record_id'] + '.json')
        if record['job_id'] != take['job_id'] or record['state'] != 'SUCCEEDED' or record.get('take_id') != take['id']:
            raise ValueError('Take has no successful matching execution')
        if self.strict:
            actual = _probe(path)
            if actual != take['probe']:
                raise ValueError('Take local probe differs from registered probe')
        return True

    def note_continuity(self, take_id, end_state):
        self._verify_take(self._load('takes/' + take_id + '.json'))
        payload = {'take_id': take_id, 'end_state': end_state, 'writes_canon': False}
        return self._write('continuity/' + take_id + '.json', payload, None)

    def normalize_acceptance(self, decision):
        decision = dict(decision)
        decision.setdefault('schema_version', 'v5-acceptance/1.0')
        if self.strict:
            manifest = self._load('delivery-manifest.json')
            plan = self._verify_manifest(manifest)
            if decision.get('plan_sha256') != manifest['plan_sha256']:
                raise ValueError('Acceptance uses an outdated plan')
            level = decision.get('level')
            shots = manifest['shot_ids']
            if level == 'shot':
                target = decision.get('shot_id')
                if target not in shots:
                    raise ValueError('Shot acceptance outside frozen delivery scope')
                covered = [target]
            elif level == 'adjacent':
                left, right = decision.get('left'), decision.get('right')
                if (left, right) not in list(zip(shots, shots[1:])):
                    raise ValueError('Adjacent acceptance does not match delivery order')
                covered = [left, right]
            elif level == 'sequence':
                covered = shots
                assemblies = list((self.root / 'assembly').glob('*.json')) if (self.root / 'assembly').is_dir() else []
                if len(assemblies) != 1:
                    raise ValueError('Sequence acceptance needs exactly one frozen assembly')
                assembly = read(assemblies[0])
                decision.setdefault('assembly_id', assembly['id'])
                decision.setdefault('output_sha256', assembly['output_sha256'])
                if decision['assembly_id'] != assembly['id'] or decision['output_sha256'] != assembly['output_sha256']:
                    raise ValueError('Sequence acceptance is for a different output')
            else:
                raise ValueError('Invalid acceptance level')
            expected = {item['id']: item for item in plan['items']
                        if level == 'sequence' or not item['shot_ids'] or set(item['shot_ids']) & set(covered)}
            if not expected:
                raise ValueError('Acceptance scope has no frozen checks')
            items = decision.get('items')
            if not isinstance(items, list) or len(items) != len(expected) or {i.get('id') for i in items} != set(expected):
                raise ValueError('Acceptance items do not cover the frozen plan exactly')
            if any(item.get('result') not in ('PASS', 'FAIL', 'UNDETERMINED') or
                   item.get('hard') != expected[item['id']]['hard'] for item in items):
                raise ValueError('Acceptance result or hard gate differs from frozen plan')
            if decision.get('status') == 'PASS' and (any(i['result'] != 'PASS' for i in items) or
                                                       any(not i.get('evidence') for i in items)):
                raise ValueError('Passing acceptance requires passing checks and evidence')
            if level == 'shot':
                bound = decision.get('take_ids')
                if not isinstance(bound, dict) or set(bound) != {target}:
                    raise ValueError('Shot review must identify the Take under review')
                take = self._load('takes/' + bound[target] + '.json')
                job = self._load('jobs/' + take['job_id'] + '.json')
                if target not in job['shot_ids']:
                    raise ValueError('Shot review Take is outside its compiled job scope')
                self._verify_take(take)
            else:
                selected = {shot: self._load('selections/' + shot + '.json')['take_id'] for shot in covered}
                if decision.get('take_ids') not in (None, selected):
                    raise ValueError('Acceptance references a non-selected take')
                decision['take_ids'] = selected
                for take_id in selected.values():
                    self._verify_take(self._load('takes/' + take_id + '.json'))
        validate_protocol('acceptance', decision, self.kernel.skill_root)
        return decision

    def save_acceptance(self, decision):
        normalized = self.normalize_acceptance(decision)
        return self._write('acceptance/' + normalized['id'] + '.json', normalized, 'acceptance')

    def save_assembly(self, record, *, output_path=None):
        record = dict(record)
        record.setdefault('schema_version', 'v5-assembly/1.0')
        if self.strict:
            manifest = self._load('delivery-manifest.json')
            self._verify_manifest(manifest)
            edl = record.get('edl')
            validate_edl(edl)
            if [row.get('shot_id') for row in edl] != manifest['shot_ids']:
                raise ValueError('Assembly EDL does not cover frozen shots in order')
            frame = 0
            for row in edl:
                selected = self._load('selections/' + row['shot_id'] + '.json')
                if row['take_id'] != selected['take_id']:
                    raise ValueError('Assembly EDL uses a non-selected take')
                take = self._load('takes/' + row['take_id'] + '.json')
                self._verify_take(take)
                if Path(row['source']).resolve() != self.kernel.path(take['uri']):
                    raise ValueError('Assembly EDL source is not registered media')
                if row['record_in_frame'] != frame:
                    raise ValueError('Assembly EDL has a gap or overlap')
                if row['fps'] != take['probe']['fps']:
                    raise ValueError('Assembly EDL frame rate differs from take')
                span = manifest['shot_ranges'][row['shot_id']]
                if row['src_out_frame'] - row['src_in_frame'] != round((span['end_ms'] - span['start_ms']) * row['fps'] / 1000):
                    raise ValueError('Assembly EDL duration differs from frozen shot time range')
                if row['src_out_frame'] > round(take['probe']['duration_ms'] * row['fps'] / 1000):
                    raise ValueError('Assembly EDL extends beyond source media')
                frame += row['src_out_frame'] - row['src_in_frame']
            if record.get('status') != 'CHECKED' or output_path is None:
                raise ValueError('Checked assembly needs a real output file')
            source = Path(output_path)
            data = source.read_bytes()
            if not data:
                raise ValueError('Assembly output is empty')
            digest = hashlib.sha256(data).hexdigest()
            if record.get('output_sha256') not in (None, digest):
                raise ValueError('Assembly output differs from recorded hash')
            observed = _probe(source)
            if record.get('probe') not in (None, observed):
                raise ValueError('Assembly output differs from recorded probe')
            spec = manifest['output_spec']
            for key in ('width', 'height', 'fps'):
                if key in spec and observed[key] != spec[key]:
                    raise ValueError('Assembly output differs from frozen specification: ' + key)
            if observed.get('frames') != frame:
                raise ValueError('Assembly output decoded frame count differs from EDL')
            if spec.get('preserve_native_audio') and any(self._load('takes/' + row['take_id'] + '.json')['probe'].get('audio_streams', 0) for row in edl) and not observed.get('audio_streams', 0):
                raise ValueError('Assembly silently dropped native audio')
            record['output_sha256'] = digest
            record['output_uri'] = 'runtime/production/outputs/' + record['id'] + source.suffix
            record['probe'] = observed
            with transaction(self.kernel.root):
                self._write('assembly/' + record['id'] + '.json', record, 'assembly')
                self.kernel.write(record['output_uri'], data)
                return record
        return self._write('assembly/' + record['id'] + '.json', record, 'assembly')

    def validate_production_integrity(self):
        errors = []
        for job in self.jobs():
            try:
                self._verify_job(job)
            except (ValueError, OSError, KeyError) as exc:
                errors.append('Job integrity: ' + job.get('id', '?') + ': ' + str(exc))
        for record in self.records():
            try:
                validate_protocol('execution-record', record, self.kernel.skill_root)
                events = sorted((self.root / 'execution-events' / record['id']).glob('*.json'))
                if len(events) != record['version'] + 1:
                    raise ValueError('Execution event history is incomplete')
                previous = None
                previous_digest = None
                for index, path in enumerate(events):
                    event = read(path)
                    if event['version'] != index or event['from'] != previous:
                        raise ValueError('Execution event order differs from state history')
                    if index and event['to'] not in EXECUTION_TRANSITIONS[previous]:
                        raise ValueError('Execution event has illegal transition')
                    if event['record_sha256'] != _sha(event['record']) or event['record']['state'] != event['to']:
                        raise ValueError('Execution event snapshot differs from its hash')
                    if index and event.get('previous_sha256') != previous_digest:
                        raise ValueError('Execution event hash chain is broken')
                    previous_digest = event['record_sha256']
                    previous = event['to']
                if previous != record['state'] or previous_digest != _sha(record):
                    raise ValueError('Execution snapshot differs from event history')
                if self.strict and not record['automatic'] and record['state'] in ('SUBMITTED', 'SUCCEEDED'):
                    receipt = self._load('external-executions/' + record['id'] + '.json')
                    job = self._load('jobs/' + record['job_id'] + '.json')
                    proof = Path(receipt['proof_uri'])
                    if (receipt['external_task_id'] != record['task_id'] or
                        receipt['request_id'] != job['request_id'] or
                        receipt['payload_sha256'] != job['payload_sha256'] or
                        receipt['attachment_sha256s'] != [item['sha256'] for item in job['attachments']] or
                        hashlib.sha256(proof.read_bytes()).hexdigest() != receipt['proof_sha256']):
                        raise ValueError('External execution proof differs from frozen job')
            except (ValueError, OSError, KeyError, IndexError) as exc:
                errors.append('Execution integrity: ' + record.get('id', '?') + ': ' + str(exc))
        for take in self.takes():
            try:
                self._verify_take(take)
            except (ValueError, OSError, KeyError) as exc:
                errors.append('Take integrity: ' + take.get('id', '?') + ': ' + str(exc))
        return errors

    def video_delivery_blockers(self, *, include_whole=True):
        if self.strict:
            return self._strict_video_delivery_blockers(include_whole=include_whole)
        decisions = []
        folder = self.root / 'acceptance'
        if folder.is_dir():
            decisions = [json.loads(p.read_text(encoding='utf-8')) for p in folder.glob('*.json')]
        levels = {d['level']: d for d in decisions}
        errors = []
        for level in ('shot', 'adjacent', 'sequence'):
            row = levels.get(level)
            if not row or row['status'] != 'PASS':
                errors.append('Acceptance not passed: ' + level)
            elif any(i['result'] == 'UNDETERMINED' for i in row['items']):
                errors.append('Undetermined acceptance: ' + level)
        assemblies = list((self.root / 'assembly').glob('*.json')) if (self.root / 'assembly').is_dir() else []
        if not assemblies:
            errors.append('Assembly missing')
        else:
            latest = json.loads(assemblies[-1].read_text(encoding='utf-8'))
            if latest['status'] != 'CHECKED':
                errors.append('Assembly not checked')
        return errors

    def _strict_video_delivery_blockers(self, *, include_whole=True):
        errors = self.validate_production_integrity()
        try:
            manifest = self._load('delivery-manifest.json')
            plan = self._verify_manifest(manifest)
        except (ValueError, OSError, KeyError) as exc:
            return errors + ['Frozen delivery manifest: ' + str(exc)]
        shots = manifest['shot_ids']
        selected = {}
        for shot in shots:
            try:
                row = self._load('selections/' + shot + '.json')
                take = self._load('takes/' + row['take_id'] + '.json')
                self._verify_take(take)
                if row['shot_id'] != shot or row['take_sha256'] != take['sha256'] or shot not in self._load('jobs/' + take['job_id'] + '.json')['shot_ids']:
                    raise ValueError('Selection is not bound to this shot and take')
                selected[shot] = take['id']
            except (ValueError, OSError, KeyError) as exc:
                errors.append('Selected take missing or invalid for ' + shot + ': ' + str(exc))
        decision_folder = self.root / 'acceptance'
        decisions = [read(path) for path in decision_folder.glob('*.json')] if decision_folder.is_dir() else []
        if not include_whole:
            decisions = [row for row in decisions if row.get('level') != 'sequence']
        expected_keys = [('shot', shot) for shot in shots] + [('adjacent', left, right) for left, right in zip(shots, shots[1:])]
        if include_whole:
            expected_keys.append(('sequence',))
        def key(row):
            if row.get('level') == 'shot': return ('shot', row.get('shot_id'))
            if row.get('level') == 'adjacent': return ('adjacent', row.get('left'), row.get('right'))
            if row.get('level') == 'sequence': return ('sequence',)
            return ('invalid', row.get('level'))
        keys = [key(row) for row in decisions]
        if sorted(map(str, keys)) != sorted(map(str, expected_keys)):
            errors.append('Acceptance does not cover every shot, adjacent pair and sequence exactly once')
        assemblies = [read(path) for path in (self.root / 'assembly').glob('*.json')] if (self.root / 'assembly').is_dir() else []
        if len(assemblies) != 1:
            errors.append('Exactly one checked assembly is required')
        assembly = assemblies[0] if len(assemblies) == 1 else None
        if assembly:
            try:
                validate_protocol('assembly', assembly, self.kernel.skill_root)
                validate_edl(assembly['edl'])
                if assembly['status'] != 'CHECKED' or [row['shot_id'] for row in assembly['edl']] != shots:
                    raise ValueError('Assembly scope or status differs from frozen delivery')
                frame = 0
                for edl_row in assembly['edl']:
                    span = manifest['shot_ranges'][edl_row['shot_id']]
                    if edl_row['record_in_frame'] != frame or edl_row['src_out_frame'] - edl_row['src_in_frame'] != round((span['end_ms'] - span['start_ms']) * edl_row['fps'] / 1000):
                        raise ValueError('Assembly EDL time coverage differs from frozen shot ranges')
                    take = self._load('takes/' + edl_row['take_id'] + '.json')
                    if Path(edl_row['source']).resolve() != self.kernel.path(take['uri']) or edl_row['fps'] != take['probe']['fps']:
                        raise ValueError('Assembly EDL source or frame rate differs from selected take')
                    frame += edl_row['src_out_frame'] - edl_row['src_in_frame']
                path = self.kernel.path(assembly['output_uri'])
                if hashlib.sha256(path.read_bytes()).hexdigest() != assembly['output_sha256'] or _probe(path) != assembly['probe']:
                    raise ValueError('Assembly output bytes or media probe changed')
                if assembly['probe'].get('frames') != sum(row['src_out_frame'] - row['src_in_frame'] for row in assembly['edl']):
                    raise ValueError('Assembly output frame count differs from EDL')
                for row in assembly['edl']:
                    if selected.get(row['shot_id']) != row['take_id']:
                        raise ValueError('Assembly uses a non-selected take')
                if manifest['output_spec'].get('preserve_native_audio') and any(self._load('takes/' + row['take_id'] + '.json')['probe'].get('audio_streams', 0) for row in assembly['edl']) and not assembly['probe'].get('audio_streams', 0):
                    raise ValueError('Assembly lacks required native audio')
            except (ValueError, OSError, KeyError) as exc:
                errors.append('Assembly invalid: ' + str(exc))
        for row in decisions:
            try:
                validate_protocol('acceptance', row, self.kernel.skill_root)
                if row['level'] not in ('shot', 'adjacent', 'sequence'):
                    raise ValueError('Unknown acceptance level')
                covered = [row['shot_id']] if row['level'] == 'shot' else [row['left'], row['right']] if row['level'] == 'adjacent' else shots
                expected_items = {item['id'] for item in plan['items'] if row['level'] == 'sequence' or not item['shot_ids'] or set(item['shot_ids']) & set(covered)}
                if row['status'] != 'PASS' or row['plan_sha256'] != plan['sha256'] or {item['id'] for item in row['items']} != expected_items:
                    raise ValueError('Decision failed or plan coverage differs')
                if len(row['items']) != len(expected_items):
                    raise ValueError('Decision duplicates a frozen check')
                if any(item['result'] != 'PASS' or not item.get('evidence') for item in row['items']):
                    raise ValueError('Decision has unresolved checks or missing evidence')
                if row.get('take_ids') != {shot: selected[shot] for shot in covered}:
                    raise ValueError('Decision references outdated or unselected take')
                if row['level'] == 'sequence' and (not assembly or row.get('assembly_id') != assembly['id'] or row.get('output_sha256') != assembly['output_sha256']):
                    raise ValueError('Sequence review is not bound to final output')
            except (ValueError, OSError, KeyError) as exc:
                errors.append('Acceptance invalid: ' + row.get('id', '?') + ': ' + str(exc))
        for obligation in manifest['obligations']:
            try:
                evidence = self._load('post-obligations/' + obligation['id'] + '.json')['evidence']
                path = Path(evidence['uri'])
                if evidence['status'] != 'PASS' or hashlib.sha256(path.read_bytes()).hexdigest() != evidence['sha256']:
                    raise ValueError('Evidence bytes or status differ')
            except (ValueError, OSError, KeyError) as exc:
                errors.append('Post obligation unfinished: ' + obligation['id'] + ': ' + str(exc))
        return errors

    def mark_video_delivered(self):
        if self.kernel.production_target() != 'video':
            raise ValueError('Project production_target is not video')
        errors = self.video_delivery_blockers()
        if errors:
            return {'status': 'BLOCKED', 'errors': errors}
        if self.strict:
            transition = getattr(self.kernel, 'transition_video_delivered', None)
            if transition is None:
                raise ValueError('Protocol 6.0 requires central VIDEO_DELIVERED transition')
            manifest = self._load('delivery-manifest.json')
            return transition({'delivery_manifest_sha256': manifest['sha256'],
                               'production_integrity': 'PASS'})
        state = self.kernel.state
        state['status'] = 'VIDEO_DELIVERED'
        self.kernel.save(state)
        return {'status': 'VIDEO_DELIVERED'}
