"""Compile scoped prompts, native parameters and one media index into reviewable requests."""
from pathlib import Path
from copy import deepcopy
from .common import read, write, sha, pointer, schema_check
from .package import verify_package, same_json_value
from .control_lowering import lower
from .asset_usage import OBLIGATION_TYPES


def scope_for_shots(ir, shot_ids=None):
    if not shot_ids:
        return {'start_ms': 0, 'end_ms': ir['output']['duration_ms']}
    if len(set(shot_ids)) != len(shot_ids): raise ValueError('Duplicate selected shot')
    shots = [s for s in ir['shots'] if s['id'] in shot_ids]
    if len(shots) != len(shot_ids): raise ValueError('Unknown selected shot')
    if any(a['end_ms'] != b['start_ms'] for a, b in zip(shots, shots[1:])):
        raise ValueError('Selected shots must be contiguous; no implicit montage')
    return {'start_ms': shots[0]['start_ms'], 'end_ms': shots[-1]['end_ms']}


def partitions(ir, config, cap, scope):
    import spatial_runtime as spatial
    from segment_delivery import _boundary_reasons
    from .control_plan import event_times
    start, end = scope['start_ms'], scope['end_ms']
    limits = cap['duration_ms']
    if not limits['max']: return [], ['DURATION_CAP_UNVERIFIED']
    times, forced = {start, end}, set()
    keyframe_shots = {sid for c in config['controls'] if c['channel'] in ('first_frame', 'last_frame') for sid in c['shot_ids']}
    for shot in ir['shots']:
        times.update(t for t in event_times(ir, shot) if start <= t <= end)
        if shot['id'] in keyframe_shots:
            forced.update(t for t in (shot['start_ms'], shot['end_ms']) if start < t < end)
    best = {start: []}
    for b in sorted(times-{start}):
        options = []
        for a, parts in list(best.items()):
            d = b-a
            if not (limits['min'] or 1) <= d <= limits['max']: continue
            if limits['allowed'] and d not in limits['allowed']: continue
            if limits['step'] and d % limits['step']: continue
            if any(a < cut < b for cut in forced) or _boundary_reasons(ir, spatial, a, b): continue
            options.append(parts+[{'start_ms': a, 'end_ms': b}])
        if options: best[b] = min(options, key=lambda x: (len(x), tuple(-p['end_ms'] for p in x)))
    return best.get(end, []), [] if end in best else ['NO_SAFE_EVENT_PARTITION']


def _source_bindings(ir, config, manifest, media, active_shots):
    """Existing AVIR filenames and responsibilities resolve through the same submitted index."""
    assets = {a['id']: a for a in manifest['artifacts']}
    source_assets = {a['id']: a for a in ir['assets']}
    index = {aid: entry for entry in media['attachment_index'] for aid in entry['artifact_ids']}
    errors, rows = [], []
    for binding in ir['bindings']:
        if not set(binding['shot_ids']) & active_shots: continue
        ident = binding['asset_id']; actual = assets.get(ident); original = source_assets[ident]
        entry = index.get(ident)
        needed = set(binding['shot_ids']) & active_shots
        uses = [c for c in config['controls'] if ident in c['artifact_ids'] and needed.intersection(c['shot_ids'])]
        host_shots = {sid for c in uses if c['channel'] == 'keyframe_input' for sid in c['shot_ids']}
        host_only = bool(uses) and needed <= host_shots and all(c['channel'] == 'keyframe_input' for c in uses)
        if host_only and actual:
            if actual['sha256'] != original['sha256'] or actual['kind'] != original['kind'] or Path(actual['path']).name != original['filename'] or original['inspection'] != 'observed':
                errors.append('SOURCE_ASSET_IDENTITY_MISMATCH:'+ident)
            rows.append({**original, 'consumer':'image_host', 'native_slot':None})
            continue
        if not actual or not entry:
            errors.append('UNMAPPED_SOURCE_ASSET:'+ident); continue
        if actual['sha256'] != original['sha256'] or actual['kind'] != original['kind'] or Path(actual['path']).name != original['filename']:
            errors.append('SOURCE_ASSET_IDENTITY_MISMATCH:'+ident)
        if original['inspection'] != 'observed': errors.append('SOURCE_ASSET_NOT_OBSERVED:'+ident)
        rows.append({**original, 'native_slot': entry['label']})
    return rows, errors


def _obligations(ir, prompt_coverage, parameters, span, active_shots, media):
    paths = {r['source_path'] for r in prompt_coverage}
    rows = []
    parameter_map = {'/output/duration_ms': '/seconds', '/output/aspect_ratio': '/aspect_ratio', '/output/resolution': '/size'}
    for clause in ir['contract']:
        relevant = not clause['shot_ids'] or bool(set(clause['shot_ids']) & active_shots)
        row = {'requirement_id': clause['id'], 'type': OBLIGATION_TYPES[clause['channel']],
               'source_pointers': [c['path'] for c in clause['checks']], 'source_checks': deepcopy(clause['checks']),
               'shot_ids': clause['shot_ids'], 'requirement': clause['requirement'], 'acceptance': clause['acceptance'],
               'static_assertions': 'PASS', 'media_acceptance': 'NOT_RUN', 'evidence': [], 'status': 'OUTSIDE_REQUEST_SCOPE'}
        assertion_results = []
        for check in clause['checks']:
            try:
                actual = pointer(ir, check['path'])
                ok = check['op']=='exists' or (check['op']=='equals' and actual==check['value']) or (check['op']=='contains' and check['value'] in actual)
            except (KeyError, IndexError, TypeError, ValueError):
                ok = False
            assertion_results.append({'source_pointer':check['path'], 'status':'PASS' if ok else 'FAIL'})
        row['assertion_results'] = assertion_results
        row['static_assertions'] = 'PASS' if all(x['status']=='PASS' for x in assertion_results) else 'FAIL'
        if relevant and clause['channel'] == 'prompt':
            covered = [c['path'] for c in clause['checks'] if c['path'] in paths]
            row.update(status='EMITTED' if len(covered) == len(clause['checks']) else 'BLOCKED', evidence=covered)
        elif relevant and clause['channel'] == 'parameter':
            for check in clause['checks']:
                selected = list(parameter_map) if check['path'] == '/output' else [check['path']]
                for path in selected:
                    destination = parameter_map.get(path)
                    if destination is None:
                        row['evidence'].append({'source_pointer': path, 'status': 'UNSUPPORTED_NATIVE_FIELD'}); continue
                    value = pointer(ir, path)
                    partial = path == '/output/duration_ms' and span != {'start_ms': 0, 'end_ms': ir['output']['duration_ms']}
                    row['evidence'].append({'source_pointer': path, 'payload_pointer': destination,
                        'value': parameters.get(destination[1:]), 'status': 'ASSEMBLY_REQUIRED' if partial else 'UNSPECIFIED_SOURCE' if value is None else 'API_FIELD_DRAFT'})
            row['status'] = 'BLOCKED' if any(e['status']=='UNSUPPORTED_NATIVE_FIELD' for e in row['evidence']) else 'CHECKS_MAPPED'
            row['semantic_acceptance'] = 'REQUIRES_REVIEW_OF_REQUIREMENT_TEXT'
        elif relevant and clause['channel'] == 'post':
            row.update(status='POST_TASK_PLANNED', evidence=[clause['execution']])
        elif relevant and clause['channel'] == 'reference':
            index = {aid:item for item in media['attachment_index'] for aid in item['artifact_ids']}
            mapped = True
            for check in clause['checks']:
                keys = check['path'].split('/')[1:]
                if not keys or keys[0] not in ('assets', 'bindings'):
                    row['evidence'].append({'source_pointer':check['path'], 'status':'UNSUPPORTED_REFERENCE_ASSERTION'})
                    mapped = False; continue
                collection = ir[keys[0]]
                try:
                    selected = collection if len(keys)==1 else [pointer(ir, '/'+ '/'.join(keys[:2]))]
                except (KeyError, IndexError, ValueError, TypeError):
                    row['evidence'].append({'source_pointer':check['path'], 'status':'UNSUPPORTED_REFERENCE_ASSERTION'})
                    mapped = False; continue
                if keys[0]=='bindings':
                    selected = [x for x in selected if set(x['shot_ids']) & active_shots]
                if not selected: mapped = False
                for ref in selected:
                    ident = ref['asset_id'] if keys[0]=='bindings' else ref['id']
                    item = index.get(ident)
                    row['evidence'].append({'source_pointer':check['path'], 'artifact_id':ident,
                        'label':item['label'] if item else None, 'sha256':item['sha256'] if item else None,
                        'status':'ATTACHMENT_MAPPED' if item else 'UNMAPPED_REFERENCE'})
                    mapped = mapped and item is not None
            row['status'] = 'REFERENCES_MAPPED' if mapped and media['status']=='BOUND_DRAFT' else 'BLOCKED'
        if relevant and row['static_assertions']=='FAIL' and clause['level']=='hard': row['status']='BLOCKED'
        rows.append(row)
    return rows


def compile_package(package, target, mode, manifest_path, shot_ids=None):
    # This entry belongs to the video compiler; the independent image package validates assets only.
    import spatial_runtime as spatial
    from vpc_core import profile, target_errors, canonical_count
    from prompt_projection import render, verify
    bundle = verify_package(package)
    ir, config = bundle['ir'], bundle['config']
    scope = scope_for_shots(ir, shot_ids)
    cap = profile(target)
    if cap['backend'] != 'agnes_api_draft': raise ValueError('Joint API lowering is not integrated for this exact target')
    manifest = read(manifest_path); schema_check(manifest, 'control-artifacts')
    if len({a['id'] for a in manifest['artifacts']}) != len(manifest['artifacts']): raise ValueError('Duplicate artifact ID')
    parts, reasons = partitions(ir, config, cap, scope)
    if not spatial.semantic_status(ir): reasons.append('SOURCE_SEMANTIC_REVIEW_REQUIRED')
    layout = read(Path(__file__).resolve().parents[2]/'templates/backends.json')['projection_v12'][cap['template']]['layout']
    requests = []
    assets = {a['id']: a for a in manifest['artifacts']}
    clauses = {c['id']: c for c in ir['contract']}
    controls = {c['id']: c for c in bundle['plan']['controls']}
    for number, span in enumerate(parts, 1):
        media = lower(package, target, mode, manifest_path, span)
        errors = list(reasons)+list(media['reasons'])
        if media['route'] and (media['route']['entry'] != cap['entry_point'] or media['route']['model'] != cap['model']):
            errors.append('CAPABILITY_REGISTRY_CONFLICT')
        active = set(media['scope']['shot_ids'])
        bindings, binding_errors = _source_bindings(ir, config, manifest, media, active); errors += binding_errors
        output_view = deepcopy(ir); output_view['output']['duration_ms'] = span['end_ms']-span['start_ms']
        errors += [e['code'] for e in target_errors(output_view, cap, mode) if e['severity'] in ('error','blocker')]
        for a in ir['timeline']['audio_events']:
            if a['start_ms'] < span['end_ms'] and a['end_ms'] > span['start_ms'] and a['route'] == 'native' and cap['native_audio'] is not True:
                errors.append('NATIVE_AUDIO_UNVERIFIED:'+a['id'])
        blocks, audit = spatial.render(ir, span['start_ms'], span['end_ms'])
        errors += [e['code'] for e in spatial.verify_coverage(ir, blocks, audit, span['start_ms'], span['end_ms'])]
        prompt, coverage, trace, gaps = render(ir, bindings, target, mode, spatial, blocks, audit,
                                               span['start_ms'], span['end_ms'], layout=layout)
        errors += ['PROMPT_COVERAGE:'+p for p in gaps]
        errors += ['PROMPT_COVERAGE:'+e['path'] for e in verify(ir, prompt, coverage, spatial)]
        annex = []
        for row in media['coverage']:
            c = controls[row['control_id']]
            for b in row['bindings']:
                a = assets[b['artifact_id']]
                applicable = '；'.join(f"{u['shot_id']} / 项目 {u['start_ms']/1000:g}–{u['end_ms']/1000:g} 秒" +
                    (f"事件采样；参考适用 {u['reference_scope']['start_ms']/1000:g}–{u['reference_scope']['end_ms']/1000:g} 秒" if 'reference_scope' in u else '') for u in b['uses'])
                role = {'identity':'身份','appearance':'造型','style':'美术风格','scene':'场景布局','clean_keyframe':'关键帧构图','clay':'动作及运镜预演','performance':'表演','audio':'声音节奏'}.get(a['role'],a['role'])
                annex.append(f"{b['label']}（{Path(a['path']).name}）：{role}；适用 {applicable}；仅辅助：{clauses[c['requirement_id']]['requirement']}。不得继承未指定的身份、服装、场景或运镜维度。")
        if annex: prompt += '\n\n【本请求附件与职责】\n'+'\n'.join(annex)
        if scope != {'start_ms': 0, 'end_ms': ir['output']['duration_ms']} or len(parts) > 1:
            prompt += f"\n\n本请求仅制作项目 {span['start_ms']/1000:g}–{span['end_ms']/1000:g} 秒。全片时长和其他片段约束用于总装验收，不延长本段。"
        if cap['max_prompt_chars'] and len(prompt) > cap['max_prompt_chars']: errors.append('PROMPT_CHAR_BUDGET')
        if ir['policy']['max_canonical_units'] and canonical_count(prompt) > ir['policy']['max_canonical_units']: errors.append('PROMPT_CANONICAL_BUDGET')
        parameters = {'model': cap['model'], 'mode': mode, 'seconds': str(int((span['end_ms']-span['start_ms'])/1000)),
                      'aspect_ratio': ir['output']['aspect_ratio'], 'n': 1}
        if ir['output']['resolution'] is not None: parameters['size'] = ir['output']['resolution']
        # Flash has one documented resolution; freeze it explicitly instead of depending on a service default.
        elif target == 'agnes-video-2.5-flash': parameters['size'] = '720P'
        obligations = _obligations(ir, coverage, parameters, span, active, media)
        errors += ['UNMAPPED_OBLIGATION:'+r['requirement_id'] for r in obligations if r['status']=='BLOCKED']
        post = [{'id': c['id'], 'owner': 'external-runner', 'instruction': c['execution'], 'requirement': c['requirement'],
                 'source_pointers': [x['path'] for x in c['checks']], 'status': 'PLANNED'} for c in ir['contract']
                if c['channel']=='post' and (not c['shot_ids'] or set(c['shot_ids']) & active)]
        post += [{'id': a['id'], 'owner': 'external-runner', 'audio_event': deepcopy(a), 'status': 'PLANNED'}
                 for a in ir['timeline']['audio_events'] if a['route']=='post' and a['start_ms'] < span['end_ms'] and a['end_ms'] > span['start_ms']]
        payload = {**parameters, **(media['media_fields_draft'] or {}), 'prompt': prompt}
        requests.append({'id': f'REQUEST_{number:03d}', 'scope': media['scope'], 'route': media['route'], 'parameters': parameters,
                         'prompt': prompt, 'prompt_coverage': coverage, 'prompt_trace': trace,
                         'attachment_index': media['attachment_index'], 'control_coverage': media['coverage'],
                         'source_bindings': bindings,
                         'primary_obligations': obligations, 'post_tasks': post,
                         'status': 'BLOCKED' if errors else 'COMPILED_DRAFT', 'reasons': sorted(set(errors)),
                         'payload_draft': None if errors else payload, 'submitted': False, 'runnable': False,
                         'media_acceptance': 'NOT_RUN', 'url_accessibility': 'NOT_PROBED'})
    url_hashes = {}
    for request in requests:
        for item in request['attachment_index']:
            url_hashes.setdefault(item['url'], set()).add(item['sha256'])
    conflicts = {url for url, hashes in url_hashes.items() if len(hashes) > 1}
    for request in requests:
        if any(item['url'] in conflicts for item in request['attachment_index']):
            request['reasons'].append('CROSS_REQUEST_URL_CONTENT_CONFLICT')
            request['status'] = 'BLOCKED'; request['payload_draft'] = None
    reasons += [r['id']+':'+e for r in requests for e in r['reasons']]
    return {'schema': 'joint-control-compile/0.1', 'source_sha256': bundle['plan']['source']['sha256'],
            'package_manifest_sha256': sha(Path(package)/'package-manifest.json'), 'artifacts_sha256': sha(manifest_path),
            'target': target, 'mode': mode, 'capability_snapshot': cap, 'scope': scope,
            'complete_project_scope': scope == {'start_ms': 0, 'end_ms': ir['output']['duration_ms']},
            'status': 'BLOCKED' if reasons else 'COMPILED_DRAFT', 'reasons': sorted(set(reasons)), 'requests': requests,
            'assembly': {'project_duration_ms': ir['output']['duration_ms'], 'selected_duration_ms': scope['end_ms']-scope['start_ms'],
                         'request_order': [r['id'] for r in requests], 'status': 'PLANNED'},
            'submitted': False, 'runnable': False, 'media_acceptance': 'NOT_RUN'}


def export(package, target, mode, manifest_path, out, shot_ids=None):
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())): raise ValueError('Use an empty compile output directory')
    result = compile_package(package, target, mode, manifest_path, shot_ids)
    out.mkdir(parents=True, exist_ok=True)
    write(out/'joint-compile.json', result)
    for request in result['requests']:
        prefix = ('BLOCKED-' if request['status']=='BLOCKED' else '')+request['id']
        (out/(prefix+'.txt')).write_text(request['prompt']+'\n', encoding='utf-8')
        write(out/(prefix+'.json'), request)
    write(out/'compile-manifest.json', {'schema':'joint-control-package/0.1',
          'inputs': {'package': str(Path(package).resolve()), 'target': target, 'mode': mode,
                     'artifacts': str(Path(manifest_path).resolve()), 'shot_ids': shot_ids},
          'files': {p.name: sha(p) for p in out.iterdir() if p.is_file()}})
    return {'status': result['status'], 'out': str(out.resolve()), 'requests': len(result['requests']), 'reasons': result['reasons'], 'submitted': False}


def verify_export(out):
    from .common import confined
    out = Path(out)
    manifest = read(confined(out, 'compile-manifest.json'))
    if set(manifest) != {'schema', 'inputs', 'files'} or manifest['schema'] != 'joint-control-package/0.1':
        raise ValueError('Invalid joint compile manifest')
    inputs = manifest['inputs']
    if set(inputs) != {'package', 'target', 'mode', 'artifacts', 'shot_ids'}: raise ValueError('Invalid joint compile inputs')
    result = compile_package(inputs['package'], inputs['target'], inputs['mode'], inputs['artifacts'], inputs['shot_ids'])
    expected = {'joint-compile.json'}
    request_files = [(('BLOCKED-' if request['status']=='BLOCKED' else '')+request['id'], request)
                     for request in result['requests']]
    for prefix, request in request_files:
        expected.update((prefix+'.json', prefix+'.txt'))
    if set(manifest['files']) != expected:
        raise ValueError('Joint compile file set differs from verified inputs')
    for prefix, request in request_files:
        if not same_json_value(read(confined(out, prefix+'.json')), request) or confined(out, prefix+'.txt').read_text() != request['prompt']+'\n':
            raise ValueError('Joint request differs from verified inputs')
    if not same_json_value(read(confined(out, 'joint-compile.json')), result):
        raise ValueError('Joint compile data differs from verified inputs')
    for name, expected_hash in manifest['files'].items():
        if sha(confined(out, name)) != expected_hash: raise ValueError('Joint compile file changed: '+name)
    return {'status': 'VERIFIED', 'compile_status': result['status'], 'submitted': False, 'media_acceptance': 'NOT_RUN'}
