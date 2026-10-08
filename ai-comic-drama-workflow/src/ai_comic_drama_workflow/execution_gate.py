"""Studio tool-boundary checks and evidence-derived image delivery.

This is an application gate over a trusted project store, not a sandbox. A host
must route its image tools through begin_image; direct out-of-band spending
cannot be prevented by a Python package or a prompt. No automatic visual PASS.
"""
from pathlib import Path
from uuid import uuid4

from .v5_adapters import digest
from .v5_modules import digest_file, read

POLICY = 'studio-execution/1.0'
VISUAL_CHECKS = ('identity', 'composition', 'props', 'space', 'lighting', 'reference_fidelity')
PENDING = {'SUBMITTING', 'SUBMITTED', 'UNKNOWN'}


def enabled(project):
    return project.get('execution_policy') == POLICY


def endpoint(project):
    return project.get('stop_after', 'full')


def required_slots(kernel, stage=5):
    slots = ['canon', 'screenplay', 'director']
    if kernel.valid('director'):
        slots += ['art:' + scene['id'] for scene in kernel.data('director')['scenes']]
    if stage == 7:
        slots.append('storyboard')
    return slots


def receipt_valid(kernel, record):
    """Verify acceptance provenance, never trust an imported 'accepted' label."""
    try:
        proof = record['acceptance_receipt']
        result = read(kernel.path(proof['uri']))
        if digest(result) != proof['sha256'] or kernel.state['completed_tasks'].get(result['task_id']) != proof['sha256']:
            return False
        if 'visual_review' in record:
            media = result.get('media', {})
            if not all(media.get(key) == record.get(key) for key in
                       ('sha256', 'visual_review', 'provider', 'input_bindings', 'call_evidence')):
                return False
            if media.get('provider') == 'image_gen':
                execution = read(kernel.path(record_path(record.get('execution_record_id'))))
                return (execution['state'] == 'ACCEPTED' and execution['candidate_sha256'] == record['sha256']
                        and execution['acceptance_receipt'] == proof
                        and execution['task_id'] == result['task_id'])
            return media.get('provenance_kind') == record.get('provenance_kind')
        if 'kind' in record:
            task = read(kernel.path('runtime/tasks/' + result['task_id'] + '.json'))
            return (task['slot'] == record['slot'] and task['kind'] == record['kind']
                    and result.get('artifact_sha256') == record.get('original_sha256'))
        return (kernel.path(record['uri']).read_text() == result.get('prompt')
                and record.get('params') == result.get('params'))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def upstream_errors(kernel, stage=5):
    errors = []
    for slot in required_slots(kernel, stage):
        record = kernel.state['artifacts'].get(slot, {})
        if not kernel.valid(slot) or record.get('needs_review') or not receipt_valid(kernel, record):
            errors.append('Accepted current native prerequisite required: ' + slot)
    return errors


def check_image_task(kernel, task):
    state = kernel.state
    if task.get('kind') != 'image' or task.get('task_id') != state['active_task']:
        raise ValueError('Generation requires the active native image task')
    if digest(task) != state.get('active_task_sha256'):
        raise ValueError('Image task envelope changed')
    stage = task['job']['stage']
    if stage not in (5, 7) or (endpoint(kernel.project) == 'images' and stage != 5):
        raise ValueError('Image task exceeds the current delivery endpoint')
    errors = upstream_errors(kernel, stage)
    if errors:
        raise ValueError('; '.join(errors))
    if not kernel.dependencies_valid(task['dependencies']):
        raise ValueError('Image task dependencies changed')
    current = next((j for j in kernel.image_jobs(stage) if j['key'] == task['slot']), None)
    if current is None or digest(current) != digest(task['job']):
        raise ValueError('Image job or reference bindings changed')
    prompt = state['prompts'].get(task['slot'])
    if (not prompt or prompt != task['prompt'] or not kernel.prompt_valid(prompt)
            or prompt['input_fingerprint'] != current['fingerprint']
            or not receipt_valid(kernel, prompt)):
        raise ValueError('Accepted current image prompt required')
    for ref in current['references']:
        if not kernel.path(ref['uri']).is_file() or digest_file(kernel.path(ref['uri'])) != ref['sha256']:
            raise ValueError('Image reference bytes changed: ' + ref['key'])
    return current


def record_path(record_id):
    if not isinstance(record_id, str) or not record_id.startswith('IMG_') or len(record_id) != 36:
        raise ValueError('Invalid image execution record ID')
    if any(c not in '0123456789abcdef' for c in record_id[4:]):
        raise ValueError('Invalid image execution record ID')
    return 'runtime/image-executions/' + record_id + '.json'


def records(kernel):
    folder = kernel.path('runtime/image-executions')
    return [read(f) for f in sorted(folder.glob('IMG_*.json'))] if folder.exists() else []


def begin(kernel, task):
    check_image_task(kernel, task)
    host = kernel.state['host']
    if host.get('image_capability') != 'available' or not host.get('image_tools'):
        raise ValueError('Register an available image tool before generation; imports do not need begin-image')
    if any(r['state'] in PENDING for r in records(kernel)):
        raise ValueError('Recover the original unresolved image execution; no new attempt')
    record_id = 'IMG_' + uuid4().hex
    record = {'schema': 'image-execution/1.0', 'id': record_id, 'state': 'SUBMITTING',
              'task_id': task['task_id'], 'key': task['slot'], 'task_sha256': digest(task),
              'job_fingerprint': task['job']['fingerprint'], 'prompt_sha256': task['prompt']['sha256'],
              'provider_task_id': None, 'version': 0}
    kernel.write(record_path(record_id), record)
    kernel.write('runtime/image-events/' + record_id + '/0000.json', record)
    return record


def validate_visual_review(review):
    if not isinstance(review, dict):
        raise ValueError('Visual review must be an object')
    rows = review.get('checks')
    if not isinstance(rows, list):
        raise ValueError('Visual review requires per-check observations, not a blanket PASS')
    seen = set()
    for row in rows:
        key = row.get('check') if isinstance(row, dict) else None
        if key not in VISUAL_CHECKS or key in seen:
            raise ValueError('Unknown or duplicate visual check')
        seen.add(key)
        if not isinstance(row.get('observation'), str) or not row['observation'].strip():
            raise ValueError('Visual check requires an actual observation')
        if row.get('status') == 'NOT_APPLICABLE':
            if key in ('composition', 'space', 'lighting') or not str(row.get('condition') or '').strip():
                raise ValueError('Visual check non-applicability needs a permitted check and reason')
        elif row.get('status') != 'PASS':
            raise ValueError('Failed or unresolved visual check blocks acceptance: ' + key)
    if seen != set(VISUAL_CHECKS):
        raise ValueError('Missing visual checks: ' + ', '.join(sorted(set(VISUAL_CHECKS) - seen)))
    # Existing native lock findings must also have an explicit disposition.
    for row in review.get('findings', []):
        if not isinstance(row, dict) or row.get('status') != 'PASS':
            raise ValueError('Every locked-item visual finding must explicitly PASS')


def check_dimensions(task, width, height):
    """Only enforce explicitly frozen numeric specs, never infer from prose."""
    spec = task['prompt'].get('params', {}).get('expected_image', {})
    if not isinstance(spec, dict) or set(spec) - {'width', 'height', 'aspect_ratio'}:
        raise ValueError('Invalid expected_image specification')
    for name, actual in (('width', width), ('height', height)):
        if name in spec and (type(spec[name]) is not int or spec[name] <= 0 or spec[name] != actual):
            raise ValueError('Image dimensions do not match the frozen ' + name)
    ratio = spec.get('aspect_ratio')
    if ratio is not None:
        if (not isinstance(ratio, list) or len(ratio) != 2
                or any(type(n) is not int or n <= 0 for n in ratio)):
            raise ValueError('aspect_ratio must contain two positive integers')
        if width * ratio[1] != height * ratio[0]:
            raise ValueError('Image aspect ratio does not match the frozen specification')


def dispatch_image(kernel, task_id, invoke):
    """Host adapter entry: reserve -> call once -> receive candidate, NEVER QA.

invoke(dispatch) must call a registered image tool exactly once and return
file/call_evidence and optionally provider_task_id. On exceptions preserve an
UNKNOWN execution; a timeout is not evidence that the provider did not submit.
The host owns authentication, charge authorization and actual tool execution.
"""
    from .transactions import transaction
    if not enabled(kernel.project):
        raise ValueError('Dispatch requires a gated studio project')
    ticket = kernel.begin_image(task_id)
    record = ticket['execution']
    evidence = {'record_id': record['id'], 'task_sha256': record['task_sha256'],
                'provider_task_id': None}
    try:
        result = invoke(ticket['dispatch'])
        if not isinstance(result, dict):
            raise ValueError('Host image adapter must return an object')
        candidate = Path(result.get('file') or '')
        if not candidate.is_file() or not candidate.stat().st_size:
            raise ValueError('Host adapter did not return an actual candidate file')
        call = result.get('call_evidence')
        if not isinstance(call, str) or not any(tool in call for tool in ticket['dispatch']['registered_tools']):
            raise ValueError('Host result must identify the registered tool call')
        provider_id = result.get('provider_task_id')
        if provider_id is not None and (not isinstance(provider_id, str) or not provider_id.strip()):
            raise ValueError('Host provider task ID must be a nonempty string or None')
        evidence.update(state='RECEIVED', file=str(candidate.resolve()),
                        provider_task_id=provider_id,
                        observation='Host adapter returned actual bytes; visual QA NOT_RUN.')
        proof = {'record_id': record['id'], 'call_evidence': call,
                 'provider_task_id': result.get('provider_task_id'), 'candidate_sha256': digest_file(candidate)}
    except Exception as error:
        evidence.update(state='UNKNOWN', observation='Host invocation failed or response is incomplete; submission status is unknown.')
        proof = {'record_id': record['id'], 'exception_type': type(error).__name__,
                 'observation': evidence['observation']}
    with transaction(kernel.root):
        uri = 'runtime/image-events/' + record['id'] + '/host-return.json'
        kernel.write(uri, proof)
        evidence['proof_file'] = str(kernel.path(uri))
        recovered = kernel.recover_image(evidence)
    return {'status': 'CANDIDATE_RECEIVED' if recovered['state'] == 'RECEIVED' else 'BLOCKED_UNKNOWN',
            'execution': recovered, 'visual_review': 'NOT_RUN',
            'instruction': 'Review the actual candidate against the native task. Do not regenerate an UNKNOWN task.'}


def check_media(kernel, task, media):
    check_image_task(kernel, task)
    validate_visual_review(media.get('visual_review', {}))
    if media.get('provider') == 'provided':
        if kernel.state.get('inflight'):
            raise ValueError('Cannot replace an unresolved generation with a provided image')
        if media.get('provenance_kind') not in ('user_provided', 'external_untracked'):
            raise ValueError('Provided images need user_provided or external_untracked provenance')
        return
    record = read(kernel.path(record_path(media.get('execution_record_id'))))
    if (record['task_id'] != task['task_id'] or record['task_sha256'] != digest(task)
            or record['state'] not in ('SUBMITTING', 'SUBMITTED', 'UNKNOWN', 'RECEIVED')):
        raise ValueError('Image result does not match its reserved execution')
    inflight = kernel.state.get('inflight')
    if inflight and inflight.get('record_id') != record['id']:
        raise ValueError('Another image execution is unresolved')
    if record.get('candidate_sha256') and record['candidate_sha256'] != media.get('sha256'):
        raise ValueError('Recovered image bytes differ from the received candidate')


def finish(kernel, task, result, state):
    proof = {'uri': str(kernel.path('runtime/results/' + task['task_id'] + '.json').relative_to(kernel.root)),
             'sha256': digest(result)}
    target = (state['media'] if task['kind'] == 'image' else
              state['prompts'] if task['kind'] == 'image-prompt' else state['artifacts']).get(task['slot'])
    if target is not None:
        target['acceptance_receipt'] = proof
    if task['kind'] == 'image' and result['media']['provider'] == 'image_gen':
        record_id = result['media']['execution_record_id']
        record = read(kernel.path(record_path(record_id)))
        record.update(state='ACCEPTED', candidate_sha256=result['media']['sha256'],
                      acceptance_receipt=proof, version=record['version'] + 1)
        kernel.write(record_path(record_id), record)
        kernel.write(f"runtime/image-events/{record_id}/{record['version']:04d}.json", record)
        target['execution_record_id'] = record_id
    elif task['kind'] == 'image':
        target['provenance_kind'] = result['media']['provenance_kind']


def reconcile(kernel, evidence):
    if not isinstance(evidence, dict):
        raise ValueError('Image recovery needs structured provider evidence, not retry authorization')
    record = read(kernel.path(record_path(evidence.get('record_id'))))
    if evidence.get('task_sha256') != record['task_sha256']:
        raise ValueError('Recovery evidence belongs to another image payload')
    target = evidence.get('state')
    if target not in ('UNKNOWN', 'SUBMITTED', 'FAILED', 'NOT_SUBMITTED', 'RECEIVED'):
        raise ValueError('Unsupported image recovery state')
    proof = Path(evidence.get('proof_file') or '').expanduser()
    if not proof.is_file() or not proof.stat().st_size or not str(evidence.get('observation') or '').strip():
        raise ValueError('Recovery needs a nonempty provider/history proof and actual observation')
    provider_id = evidence.get('provider_task_id')
    if provider_id is not None and (not isinstance(provider_id, str) or not provider_id.strip()):
        raise ValueError('Invalid provider task ID')
    if target == 'SUBMITTED' and not provider_id:
        raise ValueError('SUBMITTED requires the recovered provider task ID')
    if record.get('provider_task_id') and provider_id != record['provider_task_id']:
        raise ValueError('Provider task ID cannot be replaced or erased')
    if target == 'NOT_SUBMITTED' and (provider_id or record['state'] == 'SUBMITTED'):
        raise ValueError('A submitted task cannot be declared NOT_SUBMITTED')
    bound = dict(evidence, proof_sha256=digest_file(proof))
    candidate = None
    if target == 'RECEIVED':
        candidate = Path(evidence.get('file') or '').expanduser()
        if not candidate.is_file() or not candidate.stat().st_size:
            raise ValueError('RECEIVED requires the actual candidate file')
        bound['candidate_sha256'] = digest_file(candidate)
    if record.get('recovery_digest') == digest(bound):
        return record
    if record['state'] not in PENDING:
        raise ValueError('Terminal image execution cannot be reconciled again with different evidence')
    version = record['version'] + 1
    proof_uri = f"runtime/image-events/{record['id']}/proof-{version:04d}"
    kernel.write(proof_uri, proof.read_bytes())
    record.update(state=target, provider_task_id=provider_id, version=version,
                  recovery_digest=digest(bound), proof_uri=proof_uri,
                  proof_sha256=bound['proof_sha256'], observation=evidence['observation'])
    if candidate:
        uri = f"runtime/image-candidates/{record['id']}/{candidate.name}"
        kernel.write(uri, candidate.read_bytes())
        record.update(candidate_uri=uri, candidate_sha256=bound['candidate_sha256'])
    kernel.write(record_path(record['id']), record)
    kernel.write(f"runtime/image-events/{record['id']}/{version:04d}.json", record)
    state = kernel.state
    if (state.get('inflight') or {}).get('record_id') == record['id'] and target not in PENDING:
        state['inflight'] = None
        kernel.save(state)
    return record


def change_scope(kernel, stop_after, reason):
    if not enabled(kernel.project):
        raise ValueError('Scope endpoints require a new gated studio project; old projects are not migrated')
    if stop_after not in ('images', 'full') or not isinstance(reason, str) or not reason.strip():
        raise ValueError('Scope change requires images/full and the actual user request or reason')
    if stop_after == 'images' and kernel.project['delivery'] != 'full':
        raise ValueError('Images endpoint requires full media delivery, not text-only')
    if any(r['state'] in PENDING for r in records(kernel)):
        raise ValueError('Recover unresolved image execution before changing scope')
    from .production import ProductionLedger
    if any(r['state'] in PENDING for r in ProductionLedger(kernel).records()):
        raise ValueError('Recover unresolved video execution before changing scope')
    state = kernel.state
    if endpoint(kernel.project) == stop_after:
        return {'status': 'UNCHANGED', 'stop_after': stop_after}
    event = {'from': endpoint(kernel.project), 'to': stop_after, 'reason': reason,
             'retained_artifacts': {k: v['sha256'] for k, v in state['artifacts'].items()}}
    uri = 'history/scope-' + uuid4().hex + '.json'
    kernel.write(uri, event)
    kernel.project['stop_after'] = state['stop_after'] = stop_after
    # Scope is an execution endpoint, not a change to creative facts. Do not
    # add this request as a new story source and invalidate accepted upstream.
    state.update(active_task=None, active_decision=None, blocked_decision=None, status='RUNNING')
    state.pop('workspace_notice', None)
    kernel.write('project.json', kernel.project)
    kernel.save(state)
    return {'status': 'SCOPE_CHANGED', 'stop_after': stop_after, 'evidence': str(kernel.path(uri)),
            'retained_artifacts': event['retained_artifacts']}


def image_report(kernel):
    """Read current native evidence; never promote arbitrary files in a folder."""
    errors = upstream_errors(kernel)
    state = kernel.state
    for source in state['sources']:
        path = kernel.path(source['uri'])
        if not path.is_file() or digest_file(path) != source['sha256']:
            errors.append('Source missing or changed: ' + source['id'])
    from .v5_modules import verify_module
    for name, item in read(kernel.root / 'modules.lock.json')['modules'].items():
        try:
            verify_module(kernel.path('runtime/module-archives/' + item['sha256'] + '.skill'), name, item)
        except (OSError, ValueError):
            errors.append('Locked module missing or changed: ' + name)
    rows = []
    jobs = []
    if not errors:
        try:
            jobs = kernel.image_jobs(5)
        except (OSError, ValueError, KeyError) as exc:
            errors.append('Image plan unavailable: ' + str(exc))
        if not jobs:
            errors.append('No required image assets; cannot claim image delivery')
    for job in jobs:
        key = job['key']; media = state['media'].get(key); prompt = state['prompts'].get(key)
        problems = []
        if (not prompt or not kernel.prompt_valid(prompt) or not receipt_valid(kernel, prompt)
                or prompt['input_fingerprint'] != job['fingerprint']):
            problems.append('Current accepted prompt missing or stale')
        if (not media or not kernel.media_valid(media) or media['input_fingerprint'] != job['fingerprint']):
            problems.append('Current accepted image missing or stale')
        elif media['role'] == 'identity' and state['approvals'].get(key, {}).get('token') != kernel.approval_token(media):
            problems.append('Identity selection missing')
        if kernel.project.get('flow_refinement') and media and not media.get('flow_refinement'):
            problems.append('Required Flow refinement missing')
        errors += [key + ': ' + message for message in problems]
        rows.append({'key': key, 'status': 'ACCEPTED' if not problems else 'STALE' if media else 'DRAFT',
                     'uri': media['uri'] if media else None, 'sha256': media['sha256'] if media else None,
                     'dimensions': media.get('dimensions') if media else None,
                     'prompt_uri': prompt['uri'] if prompt else None, 'issues': problems})
    if errors and not jobs:
        rows = [{'key': key, 'status': 'STALE', 'uri': media['uri'], 'sha256': media['sha256'],
                 'prompt_uri': None, 'issues': ['Native prerequisites or current image plan unavailable']}
                for key, media in state['media'].items() if media['stage'] == 5]
    executions = records(kernel)
    if state.get('inflight') or any(r['state'] in PENDING for r in executions):
        errors.append('Image execution remains unresolved')
    return {'schema': 'image-delivery-report/1.0', 'status': 'IMAGES_READY' if not errors else 'BLOCKED',
            'valid': not errors, 'scope': 'images', 'errors': errors, 'assets': rows,
            'candidates': [{'record_id': r['id'], 'state': r['state'], 'key': r['key'],
                            'uri': r.get('candidate_uri')} for r in executions if r['state'] != 'ACCEPTED'],
            'preproduction_complete': False, 'video_complete': False,
            'review_basis': 'native receipts + host visual observations; not independent artistic proof'}


def export_images(kernel, draft=False):
    report = image_report(kernel)
    if not report['valid'] and not draft:
        return {'status': 'BLOCKED', 'validation': report}
    status = 'IMAGES_DELIVERED' if report['valid'] else 'DRAFT'
    report['status'] = status
    kernel.write('delivery/image-status.json', report)
    lines = [f"# {kernel.project['project_id']} · {status}",
             '交付范围：图片与实际图片提示词。完整视频前期、音频、视频和实际时间线未由此报告验收。',
             '状态来自当前原生收据与逐项图像观察；候选或过期资产不作为正式素材。']
    for row in report['assets']:
        lines.append(f"- {row['key']} · {row['status']}" +
                     (f" · [图片](../{row['uri']})" if row['uri'] else '') +
                     (f" · [提示词](../{row['prompt_uri']})" if row['prompt_uri'] else ''))
    lines += ['\n未解决：' + error for error in report['errors']]
    kernel.write('delivery/index.md', ('\n\n'.join(lines) + '\n').encode())
    state = kernel.state
    state['status'] = status
    kernel.save(state)
    return {'status': status, 'index': str(kernel.path('delivery/index.md')), 'validation': report,
            'images_complete': report['valid'], 'preproduction_complete': False, 'video_complete': False}
