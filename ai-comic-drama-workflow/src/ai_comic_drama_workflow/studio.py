"""V2 studio execution facts; native IR, acceptance and scheduling stay authoritative.

The project store is trusted local state, not an authorization service. Evidence
is supplied by the authorized host and bound to bytes here, never invented here.
Money uses integer minor units of one explicitly selected currency.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import math
from pathlib import Path

from .transactions import transaction
from .v5_modules import digest_file, read

BASELINE = 'b195d583f30b3f62e4d76c8ab229fda741b73ff3'
UNRESOLVED = {'SUBMITTING', 'SUBMITTED', 'UNKNOWN'}
RISK_TYPES = {'prop_closeup', 'two_speakers', 'handoff', 'single_closeup', 'camera_motion'}


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(label + ' must be an integer >= ' + str(minimum))
    return value


def _id(value):
    if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9_-]+', value) is None:
        raise ValueError('Invalid native record ID')
    return value


def _proof(path):
    source = Path(path).resolve()
    if not source.is_file() or not source.stat().st_size:
        raise ValueError('Evidence must be a nonempty local file')
    return {'uri': str(source), 'sha256': digest_file(source)}


def _verify_proof(proof):
    if _proof(proof['uri']) != proof:
        raise ValueError('Evidence bytes changed')


def _json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class StudioExecution:
    """Small extension to the existing ledger, using its recoverable transactions."""

    def __init__(self, ledger):
        self.ledger = ledger

    def _load_policy(self):
        path = self.ledger._path('studio-policy.json')
        if not path.exists():
            return None
        value = read(path)
        if value['sha256'] != _json_hash({k: v for k, v in value.items() if k != 'sha256'}):
            raise ValueError('Studio policy changed')
        _verify_proof(value['authorization'])
        for proof in value.get('risk_exclusion_proofs', {}).values():
            _verify_proof(proof)
        return value

    def configure(self, config):
        """Opt in before the first attempt. Never changes an existing project policy."""
        required = {'currency', 'cap_minor', 'max_total_attempts', 'authorization_file', 'quotes', 'canary'}
        if not isinstance(config, dict) or set(config) - {'dialogue', 'risk_exclusions'} != required:
            raise ValueError('Studio configuration fields differ from the contract')
        if not isinstance(config['currency'], str) or re.fullmatch('[A-Z]{3}', config['currency']) is None:
            raise ValueError('Use an explicit three-letter currency')
        _integer(config['cap_minor'], 'cap_minor')
        _integer(config['max_total_attempts'], 'max_total_attempts', 1)
        quotes = config['quotes']
        if not isinstance(quotes, dict) or not quotes:
            raise ValueError('A quote upper bound is required for each planned job')
        for job_id, amount in quotes.items():
            _id(job_id)
            self.ledger._load('jobs/' + job_id + '.json')
            _integer(amount, 'quote')
        canary = config['canary']
        known = {shot for job in self.ledger.jobs() for shot in job['shot_ids']}
        # Cover applicable risks, not invented two-speaker/handoff scenes.
        # A host exclusion binds an explicit scope and real evidence bytes.
        exclusions = config.get('risk_exclusions', {})
        if not isinstance(exclusions, dict) or not set(exclusions) <= RISK_TYPES:
            raise ValueError('Invalid risk exclusions')
        if (not isinstance(canary, dict) or not canary or not set(canary) <= RISK_TYPES or
                not all(isinstance(v, str) for v in canary.values())):
            raise ValueError('Canary needs native shots for applicable risks')
        if not set(canary.values()) <= known:
            raise ValueError('Canary references unplanned native shots')
        if set(exclusions) & set(canary):
            raise ValueError('An applicable risk cannot also be excluded')
        if len(known) >= 5 and set(canary) | set(exclusions) != RISK_TYPES:
            raise ValueError('Every risk needs a canary or an evidence-bound exclusion')
        if len(known) < 5 and set(canary.values()) != known:
            raise ValueError('Small-project canary must cover every native shot')
        exclusion_proofs = {}
        for risk, row in exclusions.items():
            if (not isinstance(row, dict) or set(row) != {'reason', 'shot_ids', 'proof_file'} or
                    not isinstance(row['reason'], str) or not row['reason'].strip() or
                    not isinstance(row['shot_ids'], list) or
                    not all(isinstance(x, str) for x in row['shot_ids']) or
                    set(row['shot_ids']) != known):
                raise ValueError('Risk exclusion needs a reason, all planned shot IDs and proof_file')
            exclusion_proofs[risk] = _proof(row['proof_file'])
        dialogue = config.get('dialogue')
        measurement = None
        if dialogue is not None:
            if not isinstance(dialogue, dict) or set(dialogue) != {'script_file', 'bindings', 'margin_ms'}:
                raise ValueError('Dialogue configuration fields differ from the contract')
            measurement = dialogue_timing(dialogue['script_file'], dialogue['bindings'], margin_ms=dialogue['margin_ms'])
            if measurement['status'] != 'FITS':
                raise ValueError('Measured dialogue needs shorter lines or approved split shots')
            if not set(measurement['shots']) <= known:
                raise ValueError('Dialogue references unplanned native shots')
        with transaction(self.ledger.kernel.root):
            if self.ledger.records():
                raise ValueError('Configure studio before any execution; old projects are not migrated')
            value = {k: v for k, v in config.items() if k != 'authorization_file'}
            value.update(schema='studio-execution/2.0', baseline=BASELINE,
                         authorization=_proof(config['authorization_file']))
            if exclusion_proofs:
                value['risk_exclusion_proofs'] = exclusion_proofs
            if measurement is not None:
                value['dialogue_measurement'] = measurement
            value['sha256'] = _json_hash(value)
            return self.ledger._write('studio-policy.json', value, None)

    def canary_status(self, policy=None):
        policy = policy or self._load_policy()
        if policy is None:
            return {'status': 'NOT_CONFIGURED', 'shots': {}}
        result = {}
        for shot in policy['canary'].values():
            selection = self.ledger._path('selections/' + _id(shot) + '.json')
            try:
                if not selection.is_file():
                    raise ValueError('No accepted selected Take')
                selected = read(selection)
                take = self.ledger.validate_selection(shot, selected['take_id'])
                if selected['take_sha256'] != take['sha256'] or not take.get('probe_verified'):
                    raise ValueError('Take lacks matching verified bytes')
                # Re-normalize the actual review; a filename or stale PASS is insufficient.
                reviews = self.ledger._path('acceptance').glob('*.json')
                matching = [row for row in (read(p) for p in reviews)
                            if row.get('take_ids') == {shot: take['id']}
                            and row.get('level') == 'shot' and row.get('status') == 'PASS']
                if not matching:
                    raise ValueError('No matching native shot review')
                self.ledger.normalize_acceptance(matching[-1])
                result[shot] = {'status': 'ACCEPTED', 'take_id': take['id'], 'sha256': take['sha256']}
            except (ValueError, OSError, KeyError) as exc:
                result[shot] = {'status': 'BLOCKED', 'reason': str(exc)}
        return {'status': 'PASS' if all(r['status'] == 'ACCEPTED' for r in result.values()) else 'BLOCKED',
                'shots': result, 'review_kind': 'native_review_not_independent_by_default'}

    def before_attempt(self, job, record_id):
        """Called inside begin_submit's transaction, before any remote side effect."""
        policy = self._load_policy()
        if policy is None:
            if self.ledger.kernel.project.get('production_policy') == 'studio-production/2.0':
                raise ValueError('Studio execution requires studio-configure before generation')
            return
        if job['id'] not in policy['quotes']:
            raise ValueError('Studio budget has no quote for this job')
        if policy.get('dialogue'):
            config = policy['dialogue']
            bindings = [b for b in config['bindings'] if b['shot_id'] in job['shot_ids']]
            if bindings:
                current = dialogue_timing(config['script_file'], bindings, margin_ms=config['margin_ms'])
                frozen = [r for r in policy['dialogue_measurement']['lines'] if r['shot_id'] in job['shot_ids']]
                if current['status'] != 'FITS' or current['lines'] != frozen:
                    raise ValueError('Dialogue text/speaker/audio changed for this shot; replan affected scope')
                scope = job.get('scope', {})
                if scope and any(r['slot_ms'] > scope['end_ms'] - scope['start_ms'] for r in current['lines']):
                    raise ValueError('Dialogue time slot exceeds the compiled generation request')
        if not set(job['shot_ids']) <= set(policy['canary'].values()):
            if self.canary_status(policy)['status'] != 'PASS':
                raise ValueError('Applicable-risk canary must pass before bulk generation')
        report = self.report(include_canary=False)
        reserve = policy['quotes'][job['id']]
        if report['attempts'] >= policy['max_total_attempts']:
            raise ValueError('Studio attempt budget exhausted')
        if report['committed_minor'] + reserve > policy['cap_minor']:
            raise ValueError('Studio monetary budget exhausted')
        self.ledger._write('costs/reservations/' + _id(record_id) + '.json', {
            'record_id': record_id, 'job_id': job['id'], 'currency': policy['currency'],
            'reserved_minor': reserve, 'policy_sha256': policy['sha256'],
        }, None)

    def settle(self, record_id, amount_minor, receipt_file):
        _id(record_id)
        _integer(amount_minor, 'amount_minor')
        with transaction(self.ledger.kernel.root):
            policy = self._load_policy()
            if policy is None:
                raise ValueError('Studio budget is not configured')
            record = self.ledger._load('executions/' + record_id + '.json')
            if record['state'] in UNRESOLVED:
                raise ValueError('Unresolved execution retains its full reservation')
            self.ledger._load('costs/reservations/' + record_id + '.json')
            # A provider bill may exceed a quote: record the real cost, flag overrun,
            # and block future submissions. Never hide a debt by rejecting its bill.
            value = {'record_id': record_id, 'amount_minor': amount_minor,
                     'currency': policy['currency'], 'receipt': _proof(receipt_file)}
            path = self.ledger._path('costs/settlements/' + record_id + '.json')
            if path.exists():
                if read(path) == value:
                    return value
                raise ValueError('Settlement already exists; conflicting bill requires investigation')
            return self.ledger._write('costs/settlements/' + record_id + '.json', value, None)

    def report(self, include_canary=True):
        policy = self._load_policy()
        if policy is None:
            return {'status': 'NOT_CONFIGURED', 'attempts': len(self.ledger.records())}
        reservations = [read(p) for p in self.ledger._path('costs/reservations').glob('*.json')]
        reserved = settled = 0
        for row in reservations:
            receipt = self.ledger._path('costs/settlements/' + row['record_id'] + '.json')
            if receipt.exists():
                payment = read(receipt)
                _verify_proof(payment['receipt'])
                settled += payment['amount_minor']
            else:
                reserved += row['reserved_minor']
        # Use unique, selected, verified shot ranges, never generated attempt duration.
        accepted_ms = 0
        manifest_path = self.ledger._path('delivery-manifest.json')
        if manifest_path.exists():
            manifest = read(manifest_path)
            for shot, span in manifest.get('shot_ranges', {}).items():
                path = self.ledger._path('selections/' + _id(shot) + '.json')
                if path.exists():
                    selected = read(path)
                    take = self.ledger.validate_selection(shot, selected['take_id'])
                    if take.get('probe_verified') and selected['take_sha256'] == take['sha256']:
                        accepted_ms += span['end_ms'] - span['start_ms']
        total = reserved + settled
        result = {'status': 'OVER_BUDGET' if total > policy['cap_minor'] else 'WITHIN_BUDGET',
                  'currency': policy['currency'], 'attempts': len(self.ledger.records()),
                  'reserved_minor': reserved, 'settled_minor': settled,
                  'committed_minor': total, 'cap_minor': policy['cap_minor'],
                  'accepted_seconds': accepted_ms / 1000,
                  'settled_minor_per_accepted_second': settled * 1000 / accepted_ms if accepted_ms else None,
                  'unsettled_attempts': sum(not self.ledger._path('costs/settlements/' + r['record_id'] + '.json').exists()
                                           for r in reservations),
                  'unresolved': [r['id'] for r in self.ledger.records() if r['state'] in UNRESOLVED]}
        if include_canary:
            result['canary'] = self.canary_status(policy)
        return result

    def reconcile(self, record_id, evidence):
        """Bind a recovered task or confirmed failure to an existing attempt. No submit."""
        _id(record_id)
        required = {'record_id', 'payload_sha256', 'state', 'task_id', 'proof_file', 'observation'}
        if not isinstance(evidence, dict) or set(evidence) != required:
            raise ValueError('Reconciliation evidence fields differ from the contract')
        if evidence['record_id'] != record_id or evidence['state'] not in ('SUBMITTED', 'FAILED'):
            raise ValueError('Reconciliation must identify the existing attempt and an observed state')
        if not isinstance(evidence['observation'], str) or not evidence['observation'].strip():
            raise ValueError('Reconciliation requires a concrete provider observation')
        with transaction(self.ledger.kernel.root):
            record = self.ledger._load('executions/' + record_id + '.json')
            job = self.ledger._load('jobs/' + record['job_id'] + '.json')
            if evidence['payload_sha256'] != job['payload_sha256']:
                raise ValueError('Reconciliation payload differs from the frozen attempt')
            task = evidence['task_id']
            if (task is not None and (not isinstance(task, str) or not task.strip()) or
                    evidence['state'] == 'SUBMITTED' and not task or
                    record.get('task_id') and record['task_id'] != task):
                raise ValueError('Recovered task ID is missing or conflicts with the original')
            value = {k: v for k, v in evidence.items() if k != 'proof_file'}
            value['proof'] = _proof(evidence['proof_file'])
            receipt = 'reconciliation/' + record_id + '/' + _json_hash(value) + '.json'
            if self.ledger._path(receipt).exists():
                return record  # idempotent replay, even after download/acceptance
            if record['state'] not in UNRESOLVED:
                raise ValueError('Execution is already terminal')
            self.ledger._write(receipt, value, None)
            if evidence['state'] == 'FAILED':
                return self.ledger.mark_failed(record_id, evidence['observation'])
            external = 'external-executions/' + record_id + '.json'
            if not record['automatic'] and not self.ledger._path(external).exists():
                self.ledger._write(external, {
                    'channel': 'recovered-external-host', 'external_task_id': task,
                    'request_id': job['request_id'], 'payload_sha256': job['payload_sha256'],
                    'attachment_sha256s': [a['sha256'] for a in job['attachments']],
                    'proof_uri': value['proof']['uri'], 'proof_sha256': value['proof']['sha256'],
                }, None)
            if record['state'] == 'SUBMITTED':
                return record
            return self.ledger.mark_submitted(record_id, task)


def dialogue_timing(script_path, bindings, *, margin_ms=200):
    """Measure real audio and resolve exact native text/speaker JSON pointers.

This reports timing feasibility, not transcription, voice rights or lip-sync PASS.
Bindings are references to native IR, not a second script. The hash is scoped to
each text/speaker value, so an unrelated line change does not stale this evidence.
"""
    from .assembly import _decode
    _integer(margin_ms, 'margin_ms')
    if not isinstance(bindings, list) or not bindings:
        raise ValueError('Dialogue bindings cannot be empty')
    script = read(Path(script_path))

    def resolve(pointer):
        if not isinstance(pointer, str) or not pointer.startswith('/'):
            raise ValueError('Expected a native JSON pointer')
        value = script
        try:
            for part in pointer[1:].split('/'):
                part = part.replace('~1', '/').replace('~0', '~')
                if isinstance(value, list):
                    if not part.isdigit():
                        raise ValueError('Array pointer index must be non-negative')
                    value = value[int(part)]
                else:
                    value = value[part]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError('Native dialogue pointer does not resolve: ' + pointer) from exc
        if not isinstance(value, str) or not value:
            raise ValueError('Dialogue text/speaker pointer must resolve to a nonempty string')
        return value

    rows, totals = [], {}
    seen = set()
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {'shot_id', 'text_pointer', 'speaker_pointer', 'audio_file', 'slot_ms'}:
            raise ValueError('Dialogue binding fields differ from the contract')
        _id(binding['shot_id'])
        key = (binding['shot_id'], binding['text_pointer'])
        if key in seen:
            raise ValueError('Duplicate dialogue binding')
        seen.add(key)
        text, speaker = resolve(binding['text_pointer']), resolve(binding['speaker_pointer'])
        _integer(binding['slot_ms'], 'slot_ms', 1)
        audio = _proof(binding['audio_file'])
        _decode(audio['uri'])
        command = ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries',
                   'stream=duration:format=duration', '-of', 'json', audio['uri']]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('Dialogue probe did not complete') from exc
        if result.returncode or result.stderr.strip():
            raise ValueError('Dialogue probe failed: ' + result.stderr[-1000:])
        probe = json.loads(result.stdout)
        if not probe.get('streams'):
            raise ValueError('Dialogue file has no audio stream')
        seconds = float(probe['streams'][0].get('duration') or probe['format']['duration'])
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('Dialogue duration must be positive and finite')
        duration = round(seconds * 1000)
        if duration <= 0:
            raise ValueError('Dialogue duration must be positive')
        if _proof(audio['uri']) != audio:
            raise ValueError('Dialogue audio changed during measurement')
        row = {'shot_id': binding['shot_id'], 'text_pointer': binding['text_pointer'],
               'speaker_pointer': binding['speaker_pointer'],
               'line_sha256': _json_hash({'text': text, 'speaker': speaker}),
               'audio': audio, 'duration_ms': duration, 'slot_ms': binding['slot_ms']}
        rows.append(row)
        group = totals.setdefault(binding['shot_id'], {'duration_ms': 0, 'slot_ms': binding['slot_ms'], 'lines': 0})
        if group['slot_ms'] != binding['slot_ms']:
            raise ValueError('A shot must have one generation time slot')
        group['duration_ms'] += duration
        group['lines'] += 1
    for group in totals.values():
        group['required_ms'] = group['duration_ms'] + margin_ms * group['lines']
        group['status'] = 'FITS' if group['required_ms'] <= group['slot_ms'] else 'SPLIT_REQUIRED'
    return {'schema': 'dialogue-measurement/2.0', 'lines': rows, 'shots': totals,
            'status': 'FITS' if all(r['status'] == 'FITS' for r in totals.values()) else 'SPLIT_REQUIRED',
            'semantic_review': 'NOT_RUN', 'writes_native_ir': False}
