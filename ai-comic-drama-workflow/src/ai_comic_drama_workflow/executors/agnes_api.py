"""Agnes API adapter. Records SUBMITTING before any network call."""
import hashlib
import os
from pathlib import Path

from ..production import channel_registry
from ..transactions import transaction


class AgnesApiExecutor:
    def __init__(self, ledger, transport, key_env='AGNES_API_KEY'):
        self.ledger = ledger
        self.transport = transport
        self.key_env = key_env

    def _route(self, job):
        payload = job['payload']
        registry = channel_registry(self.ledger.kernel.skill_root)
        route = next((r for r in registry['routes']
                      if r['model'] == payload['model'] and r['mode'] == payload['mode'] and r['surface'] == 'API'), None)
        if route is None:
            raise ValueError('Unregistered Agnes route')
        if job.get('route') != route['entry']:
            raise ValueError('Frozen execution route differs from registered Agnes route')
        if self.ledger.strict and getattr(self.transport, 'base', '').rstrip('/') + '/videos' != route['entry']:
            raise ValueError('Transport endpoint differs from frozen execution route')
        if not route.get('probe_passed'):
            # Documented routes may be attempted; quality_validated stays false until an experiment passes.
            pass
        return route

    def preflight(self, job):
        route = self._route(job)
        payload = job['payload']
        if payload['mode'] not in ('text', 'keyframe', 'reference'):
            raise ValueError('Mode is outside the registered route')
        images = [a for a in job['attachments'] if a.get('kind', 'image') == 'image']
        if len(images) > route['max_refs']['image']:
            raise ValueError('Reference count exceeds the registered route')
        for item in job['attachments']:
            body = self.transport.fetch(item['url'])
            digest = hashlib.sha256(body).hexdigest()
            if digest != item['sha256']:
                raise ValueError('Attachment URL bytes do not match the frozen hash')
        return {'status': 'PREFLIGHT_OK', 'route': route['entry']}

    def execute(self, job_id, dest, *, on_started=None):
        key = os.environ.get(self.key_env)
        if not key:
            raise ValueError(self.key_env + ' is required')
        job = self.ledger._load('jobs/' + job_id + '.json')
        self.preflight(job)
        with transaction(self.ledger.kernel.root):
            started = self.ledger.begin_submit(job_id, automatic=True)
            if started.get('status') == 'BLOCKED_BUDGET':
                return started
            if on_started is not None:
                on_started(started)
        try:
            task_id = self.transport.submit(job['payload'], key)
        except Exception as exc:
            self.ledger.mark_unknown(started['id'], 'submit outcome unknown: ' + str(exc))
            return {'status': 'UNKNOWN', 'resubmit': False, 'record_id': started['id']}
        if not task_id:
            self.ledger.mark_unknown(started['id'], 'submit returned no task id')
            return {'status': 'UNKNOWN', 'resubmit': False, 'record_id': started['id']}
        self.ledger.mark_submitted(started['id'], task_id)
        try:
            remote = self.transport.poll(task_id, key, model=job['payload'].get('model'))
            self.transport.download(remote, dest)
        except Exception as exc:
            if str(exc).startswith('Agnes task failed:'):
                self.ledger.mark_failed(started['id'], str(exc))
                return {'status': 'FAILED', 'record_id': started['id']}
            self.ledger.mark_unknown(started['id'], 'submitted task requires recovery: ' + str(exc))
            return {'status': 'UNKNOWN', 'resubmit': False, 'record_id': started['id']}
        probe = self.transport.probe(dest)
        take = self.ledger.save_take(job_id, started['id'], dest, probe, automatic=True)
        return {'status': 'SUCCEEDED', 'take': take, 'record_id': started['id']}

    def finish(self, record_id, dest):
        """Poll an already submitted task. Does not create another video."""
        key = os.environ.get(self.key_env)
        if not key:
            raise ValueError(self.key_env + ' is required')
        record = self.ledger._load('executions/' + record_id + '.json')
        if record['state'] not in ('SUBMITTED', 'UNKNOWN'):
            raise ValueError('Execution is not waiting for a submitted task')
        task_id = record.get('task_id')
        if not task_id:
            raise ValueError('No task id to resume')
        job = self.ledger._load('jobs/' + record['job_id'] + '.json')
        try:
            remote = self.transport.poll(task_id, key, model=job['payload'].get('model'))
            self.transport.download(remote, dest)
        except Exception as exc:
            if str(exc).startswith('Agnes task failed:'):
                self.ledger.mark_failed(record_id, str(exc))
                return {'status': 'FAILED', 'record_id': record_id}
            if record['state'] == 'SUBMITTED':
                self.ledger.mark_unknown(record_id, 'submitted task requires recovery: ' + str(exc))
            return {'status': 'UNKNOWN', 'resubmit': False, 'record_id': record_id}
        probe = self.transport.probe(dest)
        take = self.ledger.save_take(record['job_id'], record_id, dest, probe, automatic=True)
        return {'status': 'SUCCEEDED', 'take': take, 'record_id': record_id}

    def recover(self, record_id):
        record = self.ledger._load('executions/' + record_id + '.json')
        if record['state'] == 'SUBMITTING' and not record.get('task_id'):
            self.ledger.mark_unknown(record_id, 'interrupted before task id')
            return {'status': 'UNKNOWN', 'resubmit': False}
        return {'status': record['state'], 'resubmit': False}
