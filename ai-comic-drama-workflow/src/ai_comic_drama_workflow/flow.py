"""Host-mediated Google Flow reference refinement and receipt validation.

This module never signs in, drives a browser, calls an unofficial API, or upscales
pixels locally. The host must execute the frozen action on Flow's official UI,
download the real image, and return evidence. Evidence is a host attestation, not
a cryptographic proof of Google's execution or a guarantee of perfect fidelity.
Dispatch is recorded before the external action; an unknown outcome cannot be
resubmitted. Callers must catch FlowBlockedError *inside* their transaction so a
terminal receipt is retained. Project storage is trusted, as in transactions.py.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlparse

from . import workspace
from .v5_adapters import digest
from .v5_modules import digest_file, read

POLICY = 'google-flow-2k/1.0'
CRITERIA = ('identity', 'composition', 'wardrobe', 'props', 'lighting', 'text')
MIN_LONG_EDGE = 2048
MAX_ATTEMPTS = 3
ASPECT_TOLERANCE = 0.005
_BLOCKERS = {
    'LOGIN_REQUIRED', 'AUTHORIZATION_REQUIRED', 'SUBSCRIPTION_REQUIRED',
    'CAPABILITY_UNAVAILABLE', 'ACCOUNT_MISMATCH', 'DOWNLOAD_UNAVAILABLE',
    'RESOLUTION_UNAVAILABLE', 'QUALITY_FAILED', 'SERVICE_FAILED', 'UNKNOWN',
}
_PRECONDITION_BLOCKERS = {'LOGIN_REQUIRED', 'AUTHORIZATION_REQUIRED', 'SUBSCRIPTION_REQUIRED',
                         'CAPABILITY_UNAVAILABLE', 'ACCOUNT_MISMATCH'}
_EXTENSIONS = {'.png': 'png', '.jpg': 'mjpeg', '.jpeg': 'mjpeg', '.webp': 'webp'}


class FlowBlockedError(ValueError):
    """A truthful, persisted host blocker, rather than an accepted reference."""

    def __init__(self, result):
        self.result = result
        super().__init__(result['reason'])


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or value.strip().lower() in {
        'n/a', 'na', 'unknown', 'none', 'unverified', 'not applicable', 'todo', 'tbd',
    }:
        raise ValueError(label + ' requires actual evidence or an observation')
    return value


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + ' must be an object')
    return value


def validate_configuration(config):
    """Validate and normalize an enabled Flow policy; callers own opt-in/off."""
    config = _object({} if config is None else config, 'flow_refinement')
    if set(config) - {'policy', 'account_hint', 'max_attempts'}:
        raise ValueError('Unknown Flow refinement configuration field')
    if config.get('policy', POLICY) != POLICY:
        raise ValueError('Unknown Flow refinement policy')
    maximum = config.get('max_attempts', 2)
    if type(maximum) is not int or not 1 <= maximum <= MAX_ATTEMPTS:
        raise ValueError(f'Flow max_attempts must be an integer between 1 and {MAX_ATTEMPTS}')
    account = config.get('account_hint')
    if account is not None:
        _text(account, 'Configured Flow account')
    return {'policy': POLICY, 'account_hint': account, 'max_attempts': maximum}


def _config(kernel):
    return validate_configuration(kernel.project.get('flow_refinement'))


def _image(path):
    """Probe and fully decode one real still; dimensions alone are insufficient."""
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in _EXTENSIONS:
        raise ValueError('Flow requires a real PNG, JPEG or WebP file')
    for tool in ('ffprobe', 'ffmpeg'):
        if shutil.which(tool) is None:
            raise ValueError(tool + ' is required to verify Flow image bytes')
    try:
        probe = subprocess.run([
            'ffprobe', '-v', 'error', '-count_frames', '-show_entries',
            'stream=codec_type,codec_name,width,height,nb_read_frames', '-of', 'json', str(path),
        ], capture_output=True, text=True, timeout=60)
        streams = json.loads(probe.stdout).get('streams', [])
        videos = [s for s in streams if s.get('codec_type') == 'video']
        if probe.returncode or len(videos) != 1 or len(streams) != 1:
            raise ValueError('Flow output must contain one still image stream')
        stream = videos[0]
        width, height = stream.get('width'), stream.get('height')
        if (type(width) is not int or type(height) is not int or min(width, height) <= 0 or
                stream.get('codec_name') != _EXTENSIONS[path.suffix.lower()] or
                str(stream.get('nb_read_frames')) != '1'):
            raise ValueError('Flow file is not a decodable single still image')
        decoded = subprocess.run([
            'ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-map', '0:v:0',
            '-frames:v', '1', '-pix_fmt', 'rgba', '-f', 'hash', '-hash', 'sha256', '-',
        ], capture_output=True, text=True, timeout=60)
        match = re.fullmatch(r'SHA256=([0-9a-f]{64})\s*', decoded.stdout)
        if decoded.returncode or not match:
            raise ValueError('Flow image frame decoding failed')
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise ValueError('Flow image probing or decoding failed') from exc
    return {'width': width, 'height': height, 'long_edge': max(width, height),
            'aspect': f'{width}:{height}', 'decoded_sha256': match.group(1)}


def _same_aspect(source, output):
    actual = output['width'] * source['height'] / (output['height'] * source['width'])
    if abs(actual - 1) > ASPECT_TOLERANCE:
        raise ValueError('Flow output changes the reference aspect ratio')


def _original(media):
    if not isinstance(media, dict):
        raise ValueError('Flow refinement needs an accepted media record')
    refined = media.get('flow_refinement')
    original = deepcopy(refined.get('original_media')) if isinstance(refined, dict) else deepcopy(media)
    if not isinstance(original, dict) or 'flow_refinement' in original:
        raise ValueError('Invalid original Flow media provenance')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', str(original.get('key', ''))):
        raise ValueError('Invalid Flow media key')
    if type(original.get('revision')) is not int or original['revision'] < 1:
        raise ValueError('Original media needs an accepted revision')
    review = original.get('visual_review') or {}
    if (original.get('invalidated') or original.get('provider') not in ('image_gen', 'provided') or
            review.get('status') != 'PASS' or review.get('sha256') != original.get('sha256')):
        raise ValueError('Flow input must be a reviewed initial image with original provenance')
    return original


def _base(kernel, media):
    original, config = _original(media), _config(kernel)
    path = kernel.path(original['uri'])
    if digest_file(path) != original.get('sha256'):
        raise ValueError('Original Flow reference bytes changed')
    # Freeze project-relative identity. Moving a recovered project must not
    # create a new external request or forget an UNKNOWN dispatch.
    source = {'uri': original['uri'], 'path': original['uri'], 'sha256': original['sha256'], **_image(path)}
    identity = {'media': original, 'configuration': config, 'source_probe': source}
    action_id = 'FLOW_' + digest(identity)[:24]
    base = {
        'schema': 'flow-refinement-action/1.0', 'action_id': action_id,
        'host_action': 'google-flow-image-to-image', 'service': 'google-flow',
        'official_entry_url': 'https://labs.google/fx/tools/flow',
        'execution_route': 'host-mediated-official-browser', 'begin_required': True,
        'configuration': config, 'source': source, 'original_media': original,
        'prompt': (
            'Use the attached image as the sole visual authority. Recreate it faithfully '
            'with image-to-image: preserve identity, framing, layout, aspect ratio, wardrobe, '
            'props, materials, lighting, colors, and every visible text string. Do not add, '
            'remove, redesign, crop, or silently correct content. Request a downloaded image '
            'whose long edge is at least 2048 pixels. Use a currently available official '
            'Flow export or official Flow upscaling option only. Record the actual native '
            'and final dimensions. If unsupported, blocked, or materially different, report '
            'that outcome; do not claim guaranteed exact reproduction or native 2K.'),
        'output_contract': {
            'kind': 'downloaded-image', 'min_long_edge': MIN_LONG_EDGE,
            'preserve_aspect_ratio': True, 'aspect_tolerance': ASPECT_TOLERANCE,
            'allowed_provenance': ['native', 'official-upscaled'],
            'disallowed': ['screenshot', 'preview', 'source-pass-through', 'local-upscale', 'unofficial-api'],
            'comparison_criteria': list(CRITERIA),
            'comparison_rule': 'Every criterion needs source and output observations; explicit justified NOT_PRESENT is allowed only when absent in both.',
        },
        'receipt_contract': _receipt_contract(),
        'retry_policy': {'max_attempts': config['max_attempts'], 'unknown_outcome': 'RECONCILE_ONLY',
                         'retry_only_after': 'known terminal failure with evidence',
                         'pre_call_blocker': 'BLOCKED until explicit observed resolution via resume_refinement'},
    }
    uri = f'runtime/flow/{action_id}/action.json'
    if kernel.path(uri).exists():
        if read(kernel.path(uri)) != base:
            raise ValueError('Frozen Flow action was changed')
    else:
        kernel.write(uri, base)
    return base, uri


def _receipt_contract():
    return {
        'schema': 'flow-refinement-result/1.0',
        'required': ['action_id', 'attempt', 'status', 'source_sha256', 'submitted'],
        'statuses': ['SUCCEEDED', 'FAILED', 'BLOCKED', 'UNKNOWN'],
        'service': {'name': 'google-flow', 'surface': 'official-browser', 'url': 'actual Flow page URL',
                    'account_hint': 'actual account, required when configured', 'model': 'observed model name'},
        'call_evidence': {'tool': 'host tool name', 'invocation_id': 'actual invocation identifier',
                          'operation': 'image-to-image', 'evidence': 'actual browser/tool evidence',
                          'reference_attachment': {'sha256': 'source hash', 'evidence': 'actual upload/attachment evidence'},
                          'result_id': 'actual Flow image identifier'},
        'output': {'path': 'downloaded local image path', 'sha256': 'actual file hash',
                   'width': 'decoded width', 'height': 'decoded height', 'kind': 'downloaded-image',
                   'download': {'method': 'official-download', 'asset_id': 'Flow image identifier',
                                'evidence': 'actual export/download evidence'}},
        'resolution_provenance': {'kind': 'native or official-upscaled',
                                  'native': {'width': 'actual native width', 'height': 'actual native height',
                                             'evidence': 'observed native export setting/dimensions',
                                             'path': 'pre-upscale downloaded file; required for official-upscaled',
                                             'sha256': 'pre-upscale file hash; required for official-upscaled'},
                                  'upscale': {'service': 'google-flow', 'evidence': 'official upscale evidence; required for official-upscaled'}},
        'visual_comparison': {'status': 'PASS', 'source_sha256': 'source hash', 'output_sha256': 'output hash',
                              'reviewer': 'host reviewer', 'evidence': 'actual side-by-side inspection evidence',
                              'criteria': {name: {'status': 'PASS or NOT_PRESENT',
                                                  'source_observation': 'actual source observation',
                                                  'output_observation': 'actual output observation',
                                                  'source_absent': 'true only for NOT_PRESENT',
                                                  'output_absent': 'true only for NOT_PRESENT',
                                                  'reason': 'required for NOT_PRESENT'} for name in CRITERIA}},
        'failure': {'code': sorted(_BLOCKERS), 'reason': 'observed blocker', 'evidence': 'actual failure evidence'},
    }


def _history(kernel, base):
    prefix = f"runtime/flow/{base['action_id']}"
    rows = []
    for attempt in range(1, base['configuration']['max_attempts'] + 1):
        dispatch_uri = f'{prefix}/dispatch-{attempt:03d}.json'
        receipt_uri = f'{prefix}/receipt-{attempt:03d}.json'
        if not kernel.path(dispatch_uri).exists():
            if kernel.path(receipt_uri).exists():
                raise ValueError('Flow receipt has no dispatch marker')
            continue
        dispatch = read(kernel.path(dispatch_uri))
        if (dispatch.get('action_id') != base['action_id'] or dispatch.get('attempt') != attempt or
                dispatch.get('action_sha256') != digest_file(kernel.path(prefix + '/action.json')) or
                dispatch.get('source_sha256') != base['source']['sha256'] or
                dispatch.get('idempotency_key') != f"{base['action_id']}:{attempt}" or
                dispatch.get('status') != 'DISPATCHED'):
            raise ValueError('Flow dispatch marker changed')
        receipt = read(kernel.path(receipt_uri)) if kernel.path(receipt_uri).exists() else None
        if receipt is not None and (receipt.get('schema') != 'flow-refinement-result/1.0' or
                                    receipt.get('source_sha256') != base['source']['sha256'] or
                                    receipt.get('action_id') != base['action_id'] or receipt.get('attempt') != attempt):
            raise ValueError('Flow receipt identity differs from dispatch')
        rows.append((attempt, dispatch_uri, receipt_uri, receipt))
    if [r[0] for r in rows] != list(range(1, len(rows) + 1)):
        raise ValueError('Flow dispatch history has a gap')
    for attempt, _, receipt_uri, receipt in rows[:-1]:
        if receipt is None or receipt.get('status') not in ('FAILED', 'BLOCKED'):
            raise ValueError('A Flow retry was dispatched before a known terminal failure')
        _block(receipt, base)
        if _requires_resume(receipt):
            resume_uri = f'{prefix}/resume-{attempt:03d}.json'
            if not kernel.path(resume_uri).is_file():
                raise ValueError('A Flow pre-call blocker has no observed resolution')
            resolution = read(kernel.path(resume_uri))
            if (resolution.get('receipt_uri') != receipt_uri or
                    resolution.get('receipt_sha256') != digest_file(kernel.path(receipt_uri))):
                raise ValueError('Flow blocker changed after its resolution was observed')
            _resolution_evidence(base, receipt, resolution.get('evidence'))
    return rows


def _requires_resume(receipt):
    return (receipt.get('status') in ('FAILED', 'BLOCKED') and
            (receipt['status'] == 'BLOCKED' or receipt.get('failure', {}).get('code') in _PRECONDITION_BLOCKERS))


def plan_refinement(kernel, media):
    """Freeze a source-bound host action; repeated planning never executes it."""
    base, uri = _base(kernel, media)
    action = deepcopy(base)
    action.update(action_uri=uri, action_sha256=digest_file(kernel.path(uri)))
    action['source']['path'] = str(kernel.path(base['source']['uri']))
    rows = _history(kernel, base)
    if rows:
        attempt, _, _, receipt = rows[-1]
        if receipt and receipt.get('status') == 'SUCCEEDED':
            promoted_path = kernel.path(f"runtime/flow/{base['action_id']}/promoted.json")
            if not promoted_path.is_file() or not refinement_valid(kernel, read(promoted_path)):
                raise ValueError('Accepted Flow output or provenance changed')
            action.update(status='FLOW_REFINEMENT_ACCEPTED', attempt=attempt)
            return action
        if receipt is None or receipt.get('status') == 'UNKNOWN':
            action.update(status='RECONCILE_ONLY', attempt=attempt,
                          reason='A Flow dispatch may have executed; recover its result without submitting again.')
            return action
        if receipt.get('status') not in ('FAILED', 'BLOCKED'):
            raise ValueError('Invalid Flow attempt outcome')
        _block(receipt, base)
        if _requires_resume(receipt):
            resume_uri = f"runtime/flow/{base['action_id']}/resume-{attempt:03d}.json"
            if not kernel.path(resume_uri).is_file():
                action.update(status='BLOCKED', attempt=attempt, code=receipt['failure']['code'],
                              reason=receipt['failure']['reason'],
                              resume_required=True,
                              resume_instruction='Resolve the observed login, account, subscription, permission, or capability blocker, then submit explicit host observation evidence to resume_refinement.')
                return action
            resolution = read(kernel.path(resume_uri))
            if (resolution.get('receipt_uri') != rows[-1][2] or
                    resolution.get('receipt_sha256') != digest_file(kernel.path(rows[-1][2]))):
                raise ValueError('Flow blocker changed after its resolution was observed')
            _resolution_evidence(base, receipt, resolution.get('evidence'))
    attempt = len(rows) + 1
    action.update(attempt=attempt, idempotency_key=f"{base['action_id']}:{attempt}")
    if attempt > base['configuration']['max_attempts']:
        action.update(status='BLOCKED', code='ATTEMPT_LIMIT', reason='Flow refinement attempt limit reached; explicit revision or repair is required.')
    else:
        action['status'] = 'AWAITING_FLOW_REFINEMENT'
    return action


def begin_refinement(kernel, media):
    """Persist DISPATCHED before the host calls Flow. Safe to call repeatedly."""
    action = plan_refinement(kernel, media)
    if action['status'] != 'AWAITING_FLOW_REFINEMENT':
        return action
    uri = f"runtime/flow/{action['action_id']}/dispatch-{action['attempt']:03d}.json"
    marker = {key: action[key] for key in ('action_id', 'action_sha256', 'attempt', 'idempotency_key')}
    marker.update(schema='flow-dispatch/1.0', status='DISPATCHED', source_sha256=action['source']['sha256'])
    kernel.write(uri, marker)
    return {**action, 'status': 'DISPATCHED', 'dispatch_uri': uri}


def _resolution_evidence(base, receipt, evidence):
    evidence = _object(evidence, 'Flow blocker resolution')
    if (evidence.get('schema') != 'flow-resume-evidence/1.0' or evidence.get('status') != 'RESOLVED' or
            evidence.get('action_id') != base['action_id'] or evidence.get('attempt') != receipt['attempt'] or
            evidence.get('code') != receipt['failure']['code']):
        raise ValueError('Flow resolution must bind the exact observed blocker and attempt')
    _text(evidence.get('observer'), 'Flow resolution observer')
    _text(evidence.get('evidence'), 'Flow resolved precondition evidence')
    _service(base, evidence)
    return evidence


def resume_refinement(kernel, media, evidence):
    """Release a known precondition blocker after observation, without calling Flow."""
    base, _ = _base(kernel, media)
    rows = _history(kernel, base)
    if not rows or not rows[-1][3] or not _requires_resume(rows[-1][3]):
        raise ValueError('Only a known Flow precondition blocker can be resumed; unknown calls require reconciliation')
    attempt, _, receipt_uri, receipt = rows[-1]
    _block(receipt, base)
    evidence = deepcopy(_resolution_evidence(base, receipt, evidence))
    uri = f"runtime/flow/{base['action_id']}/resume-{attempt:03d}.json"
    resolution = {'schema': 'flow-resume-record/1.0', 'receipt_uri': receipt_uri,
                  'receipt_sha256': digest_file(kernel.path(receipt_uri)), 'evidence': evidence}
    if kernel.path(uri).exists() and read(kernel.path(uri)) != resolution:
        raise ValueError('Flow blocker resolution record cannot be replaced')
    kernel.write(uri, resolution)
    return plan_refinement(kernel, media)


def _official_page(value):
    parsed = urlparse(_text(value, 'Flow service URL'))
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443) or
            not (parsed.hostname == 'flow.google' or
                 (parsed.hostname == 'labs.google' and re.match(r'^/fx/(?:[A-Za-z-]+/)?tools/flow(?:/|$)', parsed.path)))):
        raise ValueError('Receipt must identify the official Google Flow browser surface')


def _service(base, result, *, allow_account_mismatch=False):
    service = _object(result.get('service'), 'Flow service')
    if service.get('name') != 'google-flow' or service.get('surface') != 'official-browser':
        raise ValueError('Receipt is not from the official Google Flow browser workflow')
    _official_page(service.get('url'))
    wanted = base['configuration']['account_hint']
    if wanted is not None and service.get('account_hint') != wanted and not allow_account_mismatch:
        raise ValueError('Flow account does not match the configured account')
    return service


def _call(base, result, *, success):
    mismatch = not success and result.get('failure', {}).get('code') == 'ACCOUNT_MISMATCH'
    service = _service(base, result, allow_account_mismatch=mismatch)
    if mismatch:
        _text(service.get('account_hint'), 'Observed mismatched Flow account')
    call = _object(result.get('call_evidence'), 'Flow call evidence')
    for name in ('tool', 'invocation_id', 'evidence'):
        _text(call.get(name), 'Flow call ' + name)
    if call.get('operation') != 'image-to-image':
        raise ValueError('Flow must use image-to-image reference refinement')
    attachment = _object(call.get('reference_attachment'), 'Flow reference attachment')
    if attachment.get('sha256') != base['source']['sha256']:
        raise ValueError('Flow reference attachment is not the frozen source image')
    _text(attachment.get('evidence'), 'Flow reference attachment')
    if success:
        _text(service.get('model'), 'Observed Flow model')
        _text(call.get('result_id'), 'Flow result identity')
    return call


def _comparison(base, result, output_sha):
    comparison = _object(result.get('visual_comparison'), 'Flow visual comparison')
    if (comparison.get('status') != 'PASS' or comparison.get('source_sha256') != base['source']['sha256'] or
            comparison.get('output_sha256') != output_sha):
        raise ValueError('Visual comparison must pass and bind both source and output image hashes')
    _text(comparison.get('reviewer'), 'Flow reviewer')
    _text(comparison.get('evidence'), 'Flow visual inspection')
    criteria = _object(comparison.get('criteria'), 'Flow comparison criteria')
    for name in CRITERIA:
        row = _object(criteria.get(name), 'Flow comparison ' + name)
        if row.get('status') not in ('PASS', 'NOT_PRESENT'):
            raise ValueError('Every Flow comparison criterion must pass: ' + name)
        _text(row.get('source_observation'), name + ' source observation')
        _text(row.get('output_observation'), name + ' output observation')
        if row['status'] == 'NOT_PRESENT':
            if row.get('source_absent') is not True or row.get('output_absent') is not True:
                raise ValueError('NOT_PRESENT needs explicit absence in both images: ' + name)
            _text(row.get('reason'), name + ' absence reason')
    return deepcopy(comparison)


def _resolution(kernel, base, result, output, output_info, folder):
    resolution = _object(result.get('resolution_provenance'), 'Flow resolution provenance')
    native = _object(resolution.get('native'), 'Flow native resolution')
    _text(native.get('evidence'), 'Flow native-resolution evidence')
    if resolution.get('kind') == 'native':
        info = output_info
        native_record = {'uri': output['uri'], 'sha256': output['sha256'], **info}
        if resolution.get('upscale'):
            raise ValueError('Native Flow provenance cannot contain an upscale claim')
    elif resolution.get('kind') == 'official-upscaled':
        upscale = _object(resolution.get('upscale'), 'Flow official upscale')
        if upscale.get('service') != 'google-flow':
            raise ValueError('Only explicitly evidenced official Flow upscaling is accepted')
        _text(upscale.get('evidence'), 'Official Flow upscale evidence')
        path = Path(_text(native.get('path'), 'Pre-upscale image path')).expanduser().resolve()
        native_sha = digest_file(path)
        if native.get('sha256') != native_sha:
            raise ValueError('Pre-upscale native image hash differs')
        info = _image(path)
        _same_aspect(base['source'], info)
        if info['long_edge'] >= output_info['long_edge']:
            raise ValueError('Official-upscaled output must exceed the actual native image resolution')
        if native_sha == base['source']['sha256'] or info['decoded_sha256'] == base['source']['decoded_sha256']:
            raise ValueError('Flow native generation cannot be the unchanged source reference')
        native_uri = workspace.relative(kernel.project, folder + '/native-' + native_sha[:16] + path.suffix.lower())
        native_record = {'uri': native_uri, 'sha256': native_sha, **info}
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != native_sha:
            raise ValueError('Flow native download changed during acceptance')
        output['_native_copy'] = (native_uri, data)
    else:
        raise ValueError('Flow resolution provenance must be native or official-upscaled')
    if (type(native.get('width')) is not int or type(native.get('height')) is not int or
            native['width'] != info['width'] or native['height'] != info['height']):
        raise ValueError('Declared native dimensions differ from actual downloaded image bytes')
    return {'kind': resolution['kind'], 'original_reference': deepcopy(base['source']),
            'native': {**native_record, 'evidence': native['evidence']},
            'downloaded': {k: output[k] for k in ('uri', 'sha256', 'width', 'height', 'long_edge')},
            'derived': resolution['kind'] == 'official-upscaled',
            'upscale': deepcopy(resolution.get('upscale')),
            'native_resolution_claim': 'host-evidenced; not inferred from final dimensions'}


def _block(result, base):
    failure = _object(result.get('failure'), 'Flow failure')
    if failure.get('code') not in _BLOCKERS:
        raise ValueError('Unknown Flow blocker code')
    _text(failure.get('reason'), 'Observed Flow failure')
    _text(failure.get('evidence'), 'Flow failure evidence')
    status, submitted = result['status'], result.get('submitted')
    if status == 'UNKNOWN':
        if submitted is not True:
            raise ValueError('Unknown Flow outcome must conservatively count as submitted')
    elif status == 'FAILED':
        if submitted is not True:
            raise ValueError('FAILED Flow generation needs submitted:true')
        _call(base, result, success=False)
    elif status == 'BLOCKED':
        if submitted is not False:
            raise ValueError('BLOCKED pre-call receipt needs submitted:false; submitted failures use FAILED')
    return {'status': 'BLOCKED', 'code': failure['code'], 'reason': failure['reason'],
            'action_id': base['action_id'], 'attempt': result['attempt'],
            'reconcile_only': status == 'UNKNOWN', 'evidence': failure['evidence']}


def accept_refinement(kernel, media, result):
    """Validate a real host receipt and promote its downloaded image as canonical.

    Identical receipt replay is idempotent. Unknown attempts may be reconciled
    once to a known outcome; any other alteration to an accepted receipt fails.
    """
    result = deepcopy(_object(result, 'Flow result'))
    base, plan_uri = _base(kernel, media)
    if (result.get('schema') != 'flow-refinement-result/1.0' or result.get('action_id') != base['action_id'] or
            result.get('source_sha256') != base['source']['sha256'] or
            type(result.get('attempt')) is not int or result.get('status') not in ('SUCCEEDED', 'FAILED', 'BLOCKED', 'UNKNOWN')):
        raise ValueError('Flow receipt does not bind the frozen action, source, and attempt')
    rows = _history(kernel, base)
    attempt = result['attempt']
    if not 1 <= attempt <= base['configuration']['max_attempts'] or not rows or attempt != rows[-1][0]:
        raise ValueError('Flow receipt needs the current, bounded, previously dispatched attempt')
    _, dispatch_uri, receipt_uri, previous = rows[-1]
    prefix = f"runtime/flow/{base['action_id']}"
    promoted_uri = prefix + '/promoted.json'
    if previous is not None and previous != result:
        if previous.get('status') != 'UNKNOWN' or result['status'] == 'UNKNOWN':
            raise ValueError('A terminal Flow receipt cannot be replaced')
    if previous == result and result['status'] == 'SUCCEEDED':
        promoted = read(kernel.path(promoted_uri))
        if not refinement_valid(kernel, promoted):
            raise ValueError('Previously accepted Flow output or receipt changed')
        return promoted
    if result['status'] != 'SUCCEEDED':
        blocker = _block(result, base)
        if previous is not None and previous != result:
            kernel.write(f'{prefix}/unknown-{attempt:03d}-{digest(previous)[:16]}.json', previous)
        kernel.write(receipt_uri, result)
        raise FlowBlockedError(blocker)
    if result.get('submitted') is not True:
        raise ValueError('Successful Flow refinement needs a submitted generation')
    call = _call(base, result, success=True)
    output = _object(result.get('output'), 'Flow output')
    download = _object(output.get('download'), 'Flow download')
    if (output.get('kind') != 'downloaded-image' or download.get('method') != 'official-download' or
            download.get('asset_id') != call['result_id']):
        raise ValueError('Flow output must be the official downloaded image, never a screenshot or preview')
    _text(download.get('evidence'), 'Flow download evidence')
    path = Path(_text(output.get('path'), 'Flow output path')).expanduser().resolve()
    actual_sha = digest_file(path)
    if output.get('sha256') != actual_sha:
        raise ValueError('Flow output image hash differs')
    info = _image(path)
    if actual_sha == base['source']['sha256'] or info['decoded_sha256'] == base['source']['decoded_sha256']:
        raise ValueError('Flow output cannot pass through the unchanged source reference')
    if info['long_edge'] < MIN_LONG_EDGE:
        raise ValueError('Actual Flow image long edge is below 2048 pixels')
    if any(type(output.get(k)) is not int or output[k] != info[k] for k in ('width', 'height')):
        raise ValueError('Declared Flow dimensions differ from actual decoded image bytes')
    _same_aspect(base['source'], info)
    comparison = _comparison(base, result, actual_sha)
    original = base['original_media']
    revision = original['revision'] + 1
    folder = f"assets/{original['key']}/v{revision:03d}"
    output_uri = workspace.relative(kernel.project, folder + '/flow-' + actual_sha[:16] + path.suffix.lower())
    saved_output = {'uri': output_uri, 'sha256': actual_sha, **info}
    resolution = _resolution(kernel, base, result, saved_output, info, folder)
    native_copy = saved_output.pop('_native_copy', None)
    if native_copy:
        kernel.write(*native_copy)
    # Read before writes and rehash to avoid accepting a changed download.
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != actual_sha:
        raise ValueError('Flow downloaded image changed during acceptance')
    kernel.write(output_uri, data)
    if previous is not None and previous != result:
        kernel.write(f'{prefix}/unknown-{attempt:03d}-{digest(previous)[:16]}.json', previous)
    kernel.write(receipt_uri, result)
    history_files = {}
    for path in kernel.path(prefix).glob('*.json'):
        if path.name.startswith(('dispatch-', 'receipt-', 'resume-', 'unknown-')):
            uri = prefix + '/' + path.name
            history_files[uri] = digest_file(kernel.path(uri))
    promoted = deepcopy(original)
    promoted.update(uri=output_uri, filename=Path(output_uri).name, sha256=actual_sha, revision=revision,
                    provider='google_flow', call_evidence=deepcopy(result['call_evidence']),
                    visual_review={'status': 'PASS', 'sha256': actual_sha,
                                   'findings': [name + ': ' + comparison['criteria'][name]['output_observation'] for name in CRITERIA],
                                   'comparison_sha256': digest(comparison)})
    record = {'schema': 'flow-refinement-record/1.0', 'policy': POLICY,
              'action_id': base['action_id'], 'attempt': attempt, 'original_media': original,
              'source': base['source'], 'output': saved_output, 'resolution_provenance': resolution,
              'visual_comparison': comparison, 'promoted_fields': promoted,
              'history_files': history_files,
              'plan_uri': plan_uri, 'plan_sha256': digest_file(kernel.path(plan_uri)),
              'dispatch_uri': dispatch_uri, 'dispatch_sha256': digest_file(kernel.path(dispatch_uri)),
              'receipt_uri': receipt_uri, 'receipt_sha256': digest_file(kernel.path(receipt_uri))}
    record_uri = prefix + '/record.json'
    kernel.write(record_uri, record)
    promoted['flow_refinement'] = {
        'policy': POLICY, 'action_id': base['action_id'], 'attempt': attempt,
        'record_uri': record_uri, 'record_sha256': digest_file(kernel.path(record_uri)),
        'receipt_uri': receipt_uri, 'receipt_sha256': record['receipt_sha256'],
        'original_media': deepcopy(original), 'resolution_provenance': resolution,
    }
    kernel.write(promoted_uri, promoted)
    return promoted


def refinement_valid(kernel, media):
    """Rehash accepted source, export, native image, plan, dispatch, and receipt."""
    try:
        metadata = _object(media.get('flow_refinement'), 'Flow refinement metadata')
        if metadata.get('policy') != POLICY or media.get('invalidated'):
            return False
        if digest_file(kernel.path(metadata['record_uri'])) != metadata['record_sha256']:
            return False
        record = read(kernel.path(metadata['record_uri']))
        if (record['policy'] != POLICY or metadata['action_id'] != record['action_id'] or
                metadata['attempt'] != record['attempt'] or metadata['original_media'] != record['original_media'] or
                metadata['resolution_provenance'] != record['resolution_provenance'] or
                metadata['receipt_uri'] != record['receipt_uri'] or metadata['receipt_sha256'] != record['receipt_sha256']):
            return False
        for name in ('plan', 'dispatch', 'receipt'):
            if digest_file(kernel.path(record[name + '_uri'])) != record[name + '_sha256']:
                return False
        if any(digest_file(kernel.path(uri)) != sha for uri, sha in record['history_files'].items()):
            return False
        if {k: v for k, v in media.items() if k != 'flow_refinement'} != record['promoted_fields']:
            return False
        for item in (record['source'], record['output'], record['resolution_provenance']['native']):
            if digest_file(kernel.path(item['uri'])) != item['sha256']:
                return False
        plan = read(kernel.path(record['plan_uri']))
        if plan['configuration'] != _config(kernel):
            return False
        receipt = read(kernel.path(record['receipt_uri']))
        if (receipt['status'] != 'SUCCEEDED' or receipt['action_id'] != record['action_id'] or
                receipt['attempt'] != record['attempt'] or receipt['source_sha256'] != record['source']['sha256'] or
                receipt['output']['sha256'] != media['sha256'] or record['source']['sha256'] == media['sha256']):
            return False
        _call(plan, receipt, success=True)
        return _comparison(plan, receipt, media['sha256']) == record['visual_comparison']
    except (KeyError, TypeError, ValueError, OSError):
        return False
