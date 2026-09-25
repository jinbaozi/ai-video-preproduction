"""Append-only production ledger. Compile artifacts stay unchanged."""
import hashlib
import json
from pathlib import Path

from .v5_modules import read
from .v5_protocol import validate_protocol

REMEDIES = ('换执行通道', '补资产', '调整允许变化的镜头设计', '交由后期完成')


def _sha(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def channel_registry(skill_root):
    skill_root = Path(skill_root)
    candidates = [
        skill_root / 'registries' / 'control-capabilities.json',
        skill_root.parent / 'video-prompt-compiler' / 'registries' / 'control-capabilities.json',
    ]
    for path in candidates:
        if path.is_file():
            return read(path)
    raise ValueError('No registered video channel registry')


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


class ProductionLedger:
    def __init__(self, kernel):
        self.kernel = kernel
        self.root = Path(kernel.root) / 'runtime' / 'production'

    def _write(self, relative, value, protocol):
        validate_protocol(protocol, value, self.kernel.skill_root)
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError('Production records are append-only: ' + relative)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return value

    def _load(self, relative):
        return json.loads((self.root / relative).read_text(encoding='utf-8'))

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

    def plan_job(self, request, compile_sha256, attachments, shot_ids, budget):
        payload = request['payload_draft']
        if request.get('submitted') is not False:
            raise ValueError('Refusing to plan from a compile artifact that claims submission')
        job_id = 'JOB_' + _sha({'compile': compile_sha256, 'request': request['id'], 'payload': payload})[:16]
        job = {
            'schema_version': 'v5-generation-job/1.0', 'id': job_id, 'request_id': request['id'],
            'compile_sha256': compile_sha256, 'payload_sha256': _sha(payload), 'payload': payload,
            'attachments': attachments, 'shot_ids': list(shot_ids), 'state': 'FROZEN',
            'budget': {'max_attempts': budget['max_attempts'], 'project_cap': budget['project_cap']},
        }
        return self._write('jobs/' + job_id + '.json', job, 'generation-job')

    def _budget_block(self, job):
        attempts = [r for r in self.records(job['id']) if r['state'] in ('SUBMITTED', 'SUCCEEDED', 'FAILED', 'UNKNOWN', 'SUBMITTING')]
        calls = [r for r in self.records() if r['automatic'] and r['state'] != 'FROZEN']
        if len(attempts) >= job['budget']['max_attempts'] or len(calls) >= job['budget']['project_cap']:
            return {'status': 'BLOCKED_BUDGET', 'remedies': list(REMEDIES), 'job_id': job['id']}
        return None

    def begin_submit(self, job_id, automatic=True, authorized=False):
        job = self._load('jobs/' + job_id + '.json')
        if any(r['state'] == 'UNKNOWN' for r in self.records(job_id)) and not authorized:
            raise ValueError('UNKNOWN execution must not be resubmitted automatically')
        for record in self.records(job_id):
            if record['state'] == 'SUBMITTING' and not record.get('task_id'):
                self.mark_unknown(record['id'], 'interrupted before task id')
                raise ValueError('UNKNOWN execution must not be resubmitted automatically')
        blocked = self._budget_block(job)
        if blocked:
            return blocked
        record_id = 'EXE_' + _sha({'job': job_id, 'n': len(self.records(job_id))})[:16]
        record = {
            'schema_version': 'v5-execution-record/1.0', 'id': record_id, 'job_id': job_id,
            'state': 'SUBMITTING', 'task_id': None, 'automatic': automatic,
        }
        self._write('executions/' + record_id + '.json', record, 'execution-record')
        return record

    def _replace_state(self, record_id, state, **extra):
        path = self.root / 'executions' / (record_id + '.json')
        record = json.loads(path.read_text(encoding='utf-8'))
        record['state'] = state
        record.update(extra)
        validate_protocol('execution-record', record, self.kernel.skill_root)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return record

    def mark_submitted(self, record_id, task_id):
        if not task_id:
            raise ValueError('task_id is required')
        return self._replace_state(record_id, 'SUBMITTED', task_id=task_id)

    def mark_failed(self, record_id, error):
        return self._replace_state(record_id, 'FAILED', error=error)

    def mark_unknown(self, record_id, reason):
        return self._replace_state(record_id, 'UNKNOWN', reason=reason, resubmit=False)

    def save_take(self, job_id, record_id, file_path, probe, automatic):
        data = Path(file_path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        take_id = 'TAKE_' + digest[:16]
        uri = 'runtime/production/media/' + take_id + Path(file_path).suffix
        dest = Path(self.kernel.root) / uri
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
        take = {
            'schema_version': 'v5-take/1.0', 'id': take_id, 'job_id': job_id, 'record_id': record_id,
            'sha256': digest, 'uri': uri, 'automatic': automatic, 'probe': probe,
            'accepted': False,
        }
        self._write('takes/' + take_id + '.json', take, 'take')
        record = self._replace_state(record_id, 'SUCCEEDED', take_id=take_id)
        if 'error' in record:
            record.pop('error')
            path = self.root / 'executions' / (record_id + '.json')
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return take

    def note_continuity(self, take_id, end_state):
        path = self.root / 'continuity' / (take_id + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {'take_id': take_id, 'end_state': end_state, 'writes_canon': False}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return payload

    def save_acceptance(self, decision):
        decision = dict(decision)
        decision.setdefault('schema_version', 'v5-acceptance/1.0')
        return self._write('acceptance/' + decision['id'] + '.json', decision, 'acceptance')

    def save_assembly(self, record):
        record = dict(record)
        record.setdefault('schema_version', 'v5-assembly/1.0')
        return self._write('assembly/' + record['id'] + '.json', record, 'assembly')

    def video_delivery_blockers(self):
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

    def mark_video_delivered(self):
        if self.kernel.production_target() != 'video':
            raise ValueError('Project production_target is not video')
        errors = self.video_delivery_blockers()
        if errors:
            return {'status': 'BLOCKED', 'errors': errors}
        state = self.kernel.state
        state['status'] = 'VIDEO_DELIVERED'
        self.kernel.save(state)
        return {'status': 'VIDEO_DELIVERED'}
