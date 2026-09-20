"""Small, explicit role handoffs; native IR remains the content authority."""
from copy import deepcopy
from .v5_adapters import assert_check, digest, pointer


def requirements(kind, inputs):
    result = []
    if kind not in ('art', 'storyboard'):
        return result
    for slot, value, record in inputs:
        if slot != 'director' and not slot.startswith('art:'):
            continue
        for clause in value['contract']['clauses']:
            if clause['priority'] != 'hard':
                continue
            paths = clause['paths']
            result.append({'id': slot + ':' + clause['id'], 'owner': slot,
                'statement': clause['requirement'], 'source_paths': paths,
                'source_fingerprint': digest([pointer(value, p) for p in paths]),
                'allowed_channels': clause.get('allowed_channels', [clause.get('execution', {}).get('channel', 'prompt')]),
                'source_values': [deepcopy(pointer(value, p)) for p in paths]})
        if kind == 'storyboard' and value.get('timeline'):
            from .v51_detail_runtime import leaves
            for path, detail in leaves(value['timeline'], '/timeline'):
                if (len(path.split('/'))>4 and path.split('/')[4]=='origin') or path.startswith('/timeline/semantic_review/'):
                    continue
                result.append({'id': slot + ':DETAIL_' + digest(path)[:20], 'owner': slot,
                    'statement': 'Preserve established temporal detail ' + path,
                    'source_paths': [path], 'source_fingerprint': digest([detail]),
                    'allowed_channels': ['prompt', 'post', 'reference', 'review'],
                    'source_values': [deepcopy(detail)], 'preservation_only': True})
        for i, check in enumerate(record.get('locks', [])):
            result.append({'id': slot + ':LOCK_' + str(i), 'owner': slot,
                'statement': 'Preserve explicitly locked field ' + check['path'],
                'source_paths': [check['path']], 'source_fingerprint': digest([pointer(value, check['path'])]),
                'allowed_channels': ['prompt', 'parameter', 'reference', 'post', 'review'],
                'source_values': [deepcopy(pointer(value, check['path']))]})
    return result


def briefing(kind, inputs, scope):
    selected = []
    for slot, value, record in inputs:
        if slot == 'director':
            fields = ('intent', 'entities', 'scenes', 'format', 'shots', 'timeline')
            basis = {'source': 'X-right,Y-depth,Z-up', 'storyboard': 'x-right,y-up,z-depth',
                     'position_transform': '[x,y,z] -> [x,z,y]',
                     'note': 'Only positions share this declared world basis; do not apply to screen positions or anatomical left/right. Camera angles need separate semantic review.'}
            if value.get('schema_version')=='1.2':
                basis['timeline']='The 1.2 timeline already uses x-right,y-up,z-depth; copy its declared frames intact. The position transform applies only to legacy static fields.'
        elif slot.startswith('art:'):
            fields = ('world', 'set', 'assets', 'shots', 'references')
            basis = {'source': value['set'].get('coordinate_system'), 'per_scene': value['set']['scene_id']}
        else:
            fields = ('content', 'entities', 'locks')
            basis = None
        selected.append({'slot': slot, 'native_uri': record['uri'], 'native_sha256': record['sha256'],
                         'fields': {key: {'pointer': '/' + key, 'value': deepcopy(value[key])}
                                    for key in fields if key in value}, 'coordinates': basis})
    return {'kind': kind, 'scope': scope or {}, 'inputs': selected,
            'required_handoffs': requirements(kind, inputs),
            'semantic_action': 'Current Agent records target assertions and rationale; unresolved interpretation is a conflict, never silently guessed.'}


def validate_handoff(kind, value, required, review):
    review = review or []
    if len({r['requirement_id'] for r in review}) != len(review):
        raise ValueError('Duplicate handoff requirement')
    by_id = {r['requirement_id']: r for r in review}
    clauses = {c['id']: c for c in value.get('contract', [])} if kind == 'storyboard' else {}
    for req in required:
        mapped = by_id.get(req['id'])
        if not mapped or mapped.get('source_fingerprint') != req['source_fingerprint']:
            raise ValueError('Missing or stale ownership handoff: ' + req['id'])
        if not mapped.get('reason') or not mapped.get('target_checks'):
            raise ValueError('Handoff needs explicit target checks and mapping reason: ' + req['id'])
        if not all(assert_check(value, c) for c in mapped['target_checks']):
            raise ValueError('Handoff target assertion failed: ' + req['id'])
        if req.get('preservation_only'):
            if not all(c['op'] == 'equals' and c.get('value') == req['source_values'][0] for c in mapped['target_checks']):
                raise ValueError('Detailed handoff needs an exact preserved field; semantic redesign requires a new upstream revision: ' + req['id'])
            continue
        if kind == 'storyboard':
            clause = clauses.get(mapped.get('target_clause'))
            if not clause or clause['strength'] != 'hard':
                raise ValueError('Hard upstream requirement needs a native hard StoryboardIR clause: ' + req['id'])
            allowed = [{'natural_language':'prompt','lexical':'prompt','native':'parameter'}.get(c,c) for c in req['allowed_channels']]
            if clause['channel'] not in allowed:
                raise ValueError('Handoff changes the required execution channel: ' + req['id'])
    return deepcopy(review)
