"""Record a human upload/download without calling it automatic."""
import hashlib
from pathlib import Path

from ..transactions import transaction


class ManualExecutor:
    def __init__(self, ledger):
        self.ledger = ledger

    def receive(self, job_id, file_path, probe, *, execution_evidence=None):
        data = Path(file_path).read_bytes()
        if hashlib.sha256(data).hexdigest() != probe.get('sha256', hashlib.sha256(data).hexdigest()):
            raise ValueError('Manual file hash does not match the declared probe')
        if self.ledger.strict and execution_evidence is None:
            raise ValueError('Protocol 6.0 needs external execution evidence')
        with transaction(self.ledger.kernel.root):
            record = self.ledger.begin_submit(job_id, automatic=False)
            if record.get('status') == 'BLOCKED_BUDGET':
                return record
            if self.ledger.strict:
                self.ledger.register_external_execution(record['id'], execution_evidence)
            take = self.ledger.save_take(job_id, record['id'], file_path, probe, automatic=False)
            return {'status': 'SUCCEEDED', 'automatic': False, 'take': take}
