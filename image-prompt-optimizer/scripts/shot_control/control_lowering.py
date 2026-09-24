"""Static route validation. No uploads, URL probing, submission or quality claims."""
from pathlib import Path
from urllib.parse import urlparse
from .common import read, sha, confined, schema_check, pointer
from .media_probe import probe

CHANNELS = {'first_frame': 'image', 'last_frame': 'image', 'image_reference': 'image',
            'clay_video_reference': 'video', 'audio_reference': 'audio'}


def validate_delta(delta):
    schema_check(delta, 'edit-delta')
    changed, preserved = delta['allow_changes'], delta['preserve']
    def conflicts(a, b):
        return a == b or a.startswith(b+'/') or b.startswith(a+'/')
    if any(conflicts(a, b) for a in changed for b in preserved):
        raise ValueError('Edit change overlaps a preserved property')
    if len(set(changed)) != len(changed) or len(set(preserved)) != len(preserved):
        raise ValueError('Duplicate edit property')
    return {'status': 'STATIC_VALID', 'generated': False, 'visual_review': 'NOT_RUN'}


def lower(package, target, mode, manifest_path):
    package = Path(package).resolve()
    plan = read(package/'control-plan.json')
    schema_check(plan, 'shot-control')
    source = confined(package, plan['source']['path'])
    if sha(source) != plan['source']['sha256']:
        raise ValueError('Source changed; regenerate controls')
    ir = read(source)
    controls = plan['controls']
    for c in controls:
        for p in c['source_pointers']:
            pointer(ir, p)
    registry = read(Path(__file__).resolve().parents[2]/'registries/control-capabilities.json')
    route = next((r for r in registry['routes'] if r['model'] == target and r['mode'] == mode), None)
    manifest_path = Path(manifest_path).resolve(); manifest = read(manifest_path)
    schema_check(manifest, 'control-artifacts')
    artifacts = {a['id']: a for a in manifest['artifacts']}
    if len(artifacts) != len(manifest['artifacts']):
        raise ValueError('Duplicate artifact ID')
    reasons, rows, media = [], [], {}
    if route is None:
        reasons.append('UNRESOLVED_EXACT_ENTRY')
    for c in controls:
        problems = []
        if route is None or c['channel'] not in route['channels']:
            problems.append('UNSUPPORTED_CHANNEL')
        if not c['artifact_ids']:
            problems.append('MISSING_ARTIFACT')
        bindings = []
        for ident in c['artifact_ids']:
            a = artifacts.get(ident)
            if not a:
                problems.append('MISSING_ARTIFACT:'+ident); continue
            if a['role'] == 'review':
                problems.append('REVIEW_ARTIFACT_FORBIDDEN:'+ident); continue
            kind = CHANNELS.get(c['channel'])
            if kind != a['kind']:
                problems.append('MEDIA_KIND_MISMATCH:'+ident); continue
            if c['channel'] in ('first_frame', 'last_frame') and a['role'] != 'clean_keyframe':
                problems.append('CLEAN_KEYFRAME_REQUIRED:'+ident)
            path = confined(manifest_path.parent, a['path'])
            if not path.is_file() or sha(path) != a['sha256']:
                problems.append('MISSING_OR_CHANGED_FILE:'+ident); continue
            info = probe(path); media[ident] = (a, info)
            if info['detected_kind'] != a['kind']:
                problems.append('DECODED_MEDIA_KIND_MISMATCH:'+ident)
            review = a['review']
            if review is None or review['sha256'] != a['sha256'] or review['result'] != 'PASS' or not review['reviewer'] or not review['checks']:
                problems.append('VISUAL_REVIEW_REQUIRED:'+ident)
            if a['source_sha256'] != plan['source']['sha256']:
                problems.append('STALE_ASSET_SOURCE:'+ident)
            url = a['binding']
            if url is None or url['sha256'] != a['sha256'] or urlparse(url['url']).scheme != 'https' or not urlparse(url['url']).netloc:
                problems.append('UNRESOLVED_UPLOAD_BINDING:'+ident)
            else:
                bindings.append({'artifact_id': ident, 'sha256': a['sha256'], 'url': url['url'],
                                 'receipt': url['receipt'], 'url_accessibility': 'NOT_PROBED'})
        rows.append({'control_id': c['id'], 'requirement_id': c['requirement_id'], 'channel': c['channel'],
                     'status': 'BLOCKED' if problems else 'BOUND', 'bindings': bindings, 'reasons': problems,
                     'submitted': False, 'media_review': 'NOT_RUN'})
        reasons.extend(c['id']+':'+p for p in problems)
    if route:
        counts = {kind: sum(a['kind'] == kind for a, _ in media.values()) for kind in ('image', 'video', 'audio')}
        for kind, maximum in route['max_refs'].items():
            count = len(media) if kind == 'total' else counts[kind]
            if count > maximum:
                reasons.append('REFERENCE_BUDGET:'+kind)
        for ident, (a, info) in media.items():
            if a['kind'] == 'image':
                if info['width'] is None or not all(256 <= info[d] <= 5760 for d in ('width', 'height')) or info['bytes'] >= 15_000_000:
                    reasons.append('IMAGE_LIMIT:'+ident)
            elif a['kind'] == 'video':
                if info['duration_ms'] is None or not 2000 <= info['duration_ms'] <= 12000 or info['fps'] is None or not 24 <= info['fps'] <= 60 or info['bytes'] >= 50_000_000:
                    reasons.append('VIDEO_LIMIT:'+ident)
            elif info['duration_ms'] is None or not 2000 <= info['duration_ms'] <= 12000 or info['bytes'] >= 15_000_000:
                reasons.append('AUDIO_LIMIT:'+ident)
        for kind, limit in (('image', 50_000_000), ('audio', 64_000_000)):
            if sum(info['bytes'] for a, info in media.values() if a['kind'] == kind) >= limit:
                reasons.append('TOTAL_BYTES:'+kind)
        if sum(info['duration_ms'] or 0 for a, info in media.values() if a['kind'] == 'audio') > 12000:
            reasons.append('TOTAL_AUDIO_DURATION')
    if not controls:
        reasons.append('NO_CONTROL_ROUTE_SELECTED')
    # Unrouted hard requirements cannot disappear behind a successful subset.
    covered = {c['requirement_id'] for c in controls}
    for clause in ir['contract']:
        if clause['level'] == 'hard' and clause['id'] not in covered:
            reasons.append('UNROUTED_HARD_REQUIREMENT:'+clause['id'])
    payload = {'model': target, 'mode': mode}
    slots = {'first_frame': 'first_frame', 'last_frame': 'last_frame', 'image_reference': 'images',
             'clay_video_reference': 'videos', 'audio_reference': 'audios'}
    for row in rows:
        for b in row['bindings']:
            slot = slots.get(row['channel'])
            if slot in ('first_frame', 'last_frame'):
                if slot in payload and payload[slot] != b['url']:
                    reasons.append('CONFLICTING_SLOT:'+slot)
                payload[slot] = b['url']
            elif slot:
                value = {'url': b['url']} if slot == 'videos' else b['url']
                if value not in payload.setdefault(slot, []):
                    payload[slot].append(value)
    return {'schema': 'control-lowering/0.1', 'status': 'BLOCKED' if reasons else 'BOUND_DRAFT',
            'route': route, 'coverage': rows, 'reasons': sorted(set(reasons)),
            'media_fields_draft': None if reasons else payload, 'submitted': False, 'runnable': False,
            'probe_passed': False, 'quality_validated': False, 'execution_receipt': None,
            'note': 'Media fields only; merge with separately validated prompt/parameters. Host must verify URL accessibility.'}
