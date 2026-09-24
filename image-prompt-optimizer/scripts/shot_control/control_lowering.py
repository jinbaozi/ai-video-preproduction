"""Static route validation. No uploads, URL probing, submission or quality claims."""
from pathlib import Path
from urllib.parse import urlparse
from .common import read, sha, confined, schema_check, digest
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


def lower(package, target, mode, manifest_path, scope=None):
    package = Path(package).resolve()
    from .package import verify_package, recipe
    from .repair import invalidated_use
    bundle = verify_package(package)
    plan, ir, config = bundle['plan'], bundle['ir'], bundle['config']
    scope = scope or {'start_ms': 0, 'end_ms': ir['output']['duration_ms']}
    if set(scope) != {'start_ms', 'end_ms'} or any(type(v) is not int for v in scope.values()) or not 0 <= scope['start_ms'] < scope['end_ms'] <= ir['output']['duration_ms']:
        raise ValueError('Invalid execution scope')
    active_shots = {s['id'] for s in ir['shots'] if s['start_ms'] < scope['end_ms'] and s['end_ms'] > scope['start_ms']}
    controls = [c for c in plan['controls'] if active_shots.intersection(c['shot_ids'])]
    registry = read(Path(__file__).resolve().parents[2]/'registries/control-capabilities.json')
    route = next((r for r in registry['routes'] if r['model'] == target and r['mode'] == mode), None)
    manifest_path = Path(manifest_path).resolve(); manifest = read(manifest_path)
    schema_check(manifest, 'control-artifacts')
    artifacts = {a['id']: a for a in manifest['artifacts']}
    if len(artifacts) != len(manifest['artifacts']):
        raise ValueError('Duplicate artifact ID')
    reasons, rows, media = [], [], {}
    url_hashes, attachment_index = {}, []
    shots = {x['id']: x for x in ir['shots']}
    if route is None:
        reasons.append('UNRESOLVED_EXACT_ENTRY')
    for c in controls:
        problems = []
        if route is None or c['channel'] not in route['channels']:
            problems.append('UNSUPPORTED_CHANNEL')
        if not c['artifact_ids']:
            problems.append('MISSING_ARTIFACT')
        bindings = []
        needed_shots = set(c['shot_ids']) & active_shots
        bound_shots = set()
        for ident in c['artifact_ids']:
            a = artifacts.get(ident)
            if not a:
                problems.append('MISSING_ARTIFACT:'+ident); continue
            uses = [u for u in a['uses'] if u['control_id'] == c['id']]
            if not uses or any(u['shot_id'] not in c['shot_ids'] for u in uses):
                problems.append('ASSET_SHOT_SCOPE:'+ident); continue
            applicable = []
            for u in uses:
                shot = shots.get(u['shot_id'])
                if shot is None or not shot['start_ms'] <= u['start_ms'] <= u['end_ms'] <= shot['end_ms']:
                    problems.append('ASSET_TIME_SCOPE:'+ident); continue
                if u['shot_id'] not in needed_shots: continue
                a_ms, b_ms = max(shot['start_ms'], scope['start_ms']), min(shot['end_ms'], scope['end_ms'])
                if c['channel'] in ('first_frame', 'last_frame'):
                    at = scope['start_ms'] if c['channel'] == 'first_frame' else scope['end_ms']
                    # Boundary ownership is directional: previous shot cannot own next shot's first frame.
                    owns = shot['start_ms'] <= at < shot['end_ms'] if c['channel'] == 'first_frame' else shot['start_ms'] < at <= shot['end_ms']
                    if not owns:
                        problems.append('INTERNAL_KEYFRAME_REQUIRES_SPLIT:'+c['id']); continue
                    if (u['start_ms'], u['end_ms']) != (at, at):
                        continue
                elif c['channel'] in ('clay_video_reference', 'audio_reference'):
                    if (u['start_ms'], u['end_ms']) != (a_ms, b_ms): continue
                elif not u['start_ms'] <= a_ms <= b_ms <= u['end_ms']:
                    continue
                applicable.append(u)
            if not applicable: continue
            if any(invalidated_use(manifest,ident,u) for u in applicable):
                problems.append('ASSET_USE_INVALIDATED:'+ident); continue
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
            # Revision is provenance; use fingerprints determine applicability.
            for u in applicable:
                if u['recipe_sha256'] != recipe(ir, config, c, u['shot_id'], a['role'], u['start_ms'], u['end_ms']):
                    problems.append('STALE_ASSET_RECIPE:'+ident)
            if review is None or review['uses_sha256'] != digest(a['uses']):
                problems.append('CURRENT_USE_REVIEW_REQUIRED:'+ident)
            url = a['binding']
            if url is None or url['sha256'] != a['sha256'] or urlparse(url['url']).scheme != 'https' or not urlparse(url['url']).netloc:
                problems.append('UNRESOLVED_UPLOAD_BINDING:'+ident)
            else:
                previous = url_hashes.setdefault(url['url'], a['sha256'])
                if previous != a['sha256']:
                    problems.append('URL_CONTENT_CONFLICT:'+ident)
                bindings.append({'artifact_id': ident, 'sha256': a['sha256'], 'url': url['url'],
                                 'receipt': url['receipt'], 'url_accessibility': 'NOT_PROBED', 'uses': applicable})
                bound_shots.update(u['shot_id'] for u in applicable)
        if bound_shots != needed_shots:
            problems.append('NO_VALID_ASSET_FOR_SCOPE')
        rows.append({'control_id': c['id'], 'requirement_id': c['requirement_id'], 'channel': c['channel'],
                     'purpose': 'supplement', 'obligation_type': 'conditioned_media' if c['channel'] == 'clay_video_reference' else 'explicit_trajectory' if c['channel'] == 'camera_trajectory' else 'visual_reference',
                     'status': 'BLOCKED' if problems else 'BOUND', 'bindings': bindings, 'reasons': problems,
                     'submitted': False, 'media_review': 'NOT_RUN'})
        reasons.extend(c['id']+':'+p for p in problems)
    # Quotas apply to unique submitted media, not the number of responsibilities.
    unique_media = {}
    for ident, (a, info) in media.items():
        unique_media.setdefault((a['kind'], a['sha256']), (a, info))
    if route:
        counts = {kind: sum(a['kind'] == kind for a, _ in unique_media.values()) for kind in ('image', 'video', 'audio')}
        for kind, maximum in route['max_refs'].items():
            count = len(unique_media) if kind == 'total' else counts[kind]
            if count > maximum:
                reasons.append('REFERENCE_BUDGET:'+kind)
        for ident, (a, info) in media.items():
            if a['kind'] == 'image':
                if info['width'] is None or not all(256 <= info[d] <= 5760 for d in ('width', 'height')) or info['bytes'] >= 15_000_000:
                    reasons.append('IMAGE_LIMIT:'+ident)
            elif a['kind'] == 'video':
                if info['duration_ms'] is None or not 2000 <= info['duration_ms'] <= 12000 or info['fps'] is None or not 24 <= info['fps'] <= 60 or info['bytes'] >= 50_000_000:
                    reasons.append('VIDEO_LIMIT:'+ident)
            elif info['duration_ms'] is None or not 0 < info['duration_ms'] <= 12000 or info['bytes'] >= 15_000_000:
                reasons.append('AUDIO_LIMIT:'+ident)
        for kind, limit in (('image', 50_000_000), ('audio', 64_000_000)):
            if sum(info['bytes'] for a, info in unique_media.values() if a['kind'] == kind) >= limit:
                reasons.append('TOTAL_BYTES:'+kind)
        audio_duration = sum(info['duration_ms'] or 0 for a, info in unique_media.values() if a['kind'] == 'audio')
        if counts['audio'] and not 2000 <= audio_duration <= 12000:
            reasons.append('TOTAL_AUDIO_DURATION')
    if not controls and mode != 'text':
        reasons.append('NO_CONTROL_ROUTE_SELECTED')
    # Media is supplementary. Native obligations remain explicitly pending the joint compiler.
    obligations = [{'requirement_id': c['id'], 'type': {'prompt': 'prompt', 'parameter': 'native_parameter', 'post': 'post_production'}[c['channel']],
                    'shot_ids': c['shot_ids'] or plan['shot_ids'], 'source_pointers': [x['path'] for x in c['checks']],
                    'status': 'NOT_COMPILED', 'acceptance': c['acceptance']} for c in ir['contract']]
    payload = {'model': target, 'mode': mode}
    slots = {'first_frame': 'first_frame', 'last_frame': 'last_frame', 'image_reference': 'images',
             'clay_video_reference': 'videos', 'audio_reference': 'audios'}
    indexed = {}
    counters = {'images': 0, 'videos': 0, 'audios': 0}
    for row in rows:
        for b in row['bindings']:
            slot = slots.get(row['channel'])
            key = (slot, b['sha256'])
            if key not in indexed:
                if slot in ('first_frame', 'last_frame'):
                    if slot in payload and payload[slot] != b['url']:
                        reasons.append('CONFLICTING_SLOT:'+slot)
                    payload[slot] = b['url']; label = slot
                else:
                    counters[slot] += 1
                    label = '<'+{'images':'Picture', 'videos':'Video', 'audios':'Audio'}[slot]+' '+str(counters[slot])+'>'
                    payload.setdefault(slot, []).append({'url': b['url']} if slot == 'videos' else b['url'])
                item = {'slot': slot, 'label': label, 'sha256': b['sha256'], 'url': b['url'], 'artifact_ids': [], 'control_ids': []}
                indexed[key] = item; attachment_index.append(item)
            item = indexed[key]
            if b['artifact_id'] not in item['artifact_ids']: item['artifact_ids'].append(b['artifact_id'])
            if row['control_id'] not in item['control_ids']: item['control_ids'].append(row['control_id'])
            b['label'] = item['label']; b['submission_url'] = item['url']
    return {'schema': 'control-lowering/0.2', 'status': 'BLOCKED' if reasons else 'BOUND_DRAFT',
            'scope': {**scope, 'shot_ids': sorted(active_shots)}, 'route': route, 'coverage': rows, 'primary_obligations': obligations, 'attachment_index': attachment_index, 'reasons': sorted(set(reasons)),
            'media_fields_draft': None if reasons else payload, 'submitted': False, 'runnable': False,
            'probe_passed': False, 'quality_validated': False, 'execution_receipt': None,
            'note': 'Supplementary media bindings only. Primary prompt/parameter/post obligations are NOT_COMPILED; use the joint compiler before execution. Host must verify URL accessibility.'}
