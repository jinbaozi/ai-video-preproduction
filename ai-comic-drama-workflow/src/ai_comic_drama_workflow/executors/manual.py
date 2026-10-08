"""Record a human upload/download without calling it automatic."""
import hashlib
from pathlib import Path

from ..transactions import transaction


class ManualExecutor:
    def __init__(self, ledger):
        self.ledger = ledger

    def receive(self, job_id, file_path, probe, *, execution_evidence=None, record_id=None):
        data = Path(file_path).read_bytes()
        if hashlib.sha256(data).hexdigest() != probe.get('sha256', hashlib.sha256(data).hexdigest()):
            raise ValueError('Manual file hash does not match the declared probe')
        if self.ledger.strict and execution_evidence is None and record_id is None:
            raise ValueError('Protocol 6.0 needs external execution evidence')
        with transaction(self.ledger.kernel.root):
            if record_id is None:
                if self.ledger._path('studio-policy.json').exists():
                    raise ValueError('Studio external execution must reserve a record before generation')
                record = self.ledger.begin_submit(job_id, automatic=False)
            else:
                from ..studio import _id
                record = self.ledger._load('executions/' + _id(record_id) + '.json')
                if record['job_id'] != job_id or record['automatic'] or record['state'] != 'SUBMITTED':
                    raise ValueError('Recovered manual Take needs its original submitted execution')
                if self.ledger.strict:
                    self.ledger._verify_external_execution(record)
            if record.get('status') == 'BLOCKED_BUDGET':
                return record
            if self.ledger.strict and record_id is None:
                self.ledger.register_external_execution(record['id'], execution_evidence)
            take = self.ledger.save_take(job_id, record['id'], file_path, probe, automatic=False)
            return {'status': 'SUCCEEDED', 'automatic': False, 'take': take}
