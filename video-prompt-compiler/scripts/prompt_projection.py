"""Project validated AVIR 1.2 detail into a chronological model prompt.

The spatial renderer remains the complete audit view. This module only changes
presentation and records exactly which source fields reach the prompt text.
"""
from collections import defaultdict
from hashlib import sha256


EXECUTED = {'direct_output', 'equivalent_conversion', 'emitted'}
EVENT_ORDER = {
    'action_groups': 0,
    'composition_tracks': 1,
    'spatial_relations': 2,
    'actions': 3,
    'performances': 4,
    'camera_operations': 5,
    'motion_tracks': 6,
    'audio_events': 7,
    'extensions': 8,
}


def _seconds(ms):
    return f'{ms / 1000:g}'


def _text_hash(value):
    return sha256(value.encode('utf-8')).hexdigest()


def _leaves(detail, ir, path):
    try:
        value = detail.pointer(ir, path)
    except (KeyError, IndexError, TypeError):
        return []
    return [p for p, _ in detail.leaves(value, path)]


def _visible_entities(ir, shot_id, at_ms, detail):
    nodes = detail.nodes(ir)
    visible = set()
    for track in ir['timeline']['composition_tracks']:
        if shot_id not in track['shot_ids'] or not (track['start_ms'] <= at_ms <= track['end_ms']):
            continue
        for subject in track['subjects']:
            if subject['presence'] == 'outside':
                continue
            node = nodes[subject['node_id']]
            while node and not node['entity_id'] and node['parent_id']:
                node = nodes[node['parent_id']]
            if node and node['entity_id']:
                visible.add(node['entity_id'])
    return visible


def _event_position(ir, path, detail):
    parts = path.strip('/').split('/')
    if len(parts) < 3 or parts[0] != 'timeline':
        return None
    collection, number = parts[1:3]
    if collection not in ir['timeline'] or not number.isdigit():
        return None
    item = ir['timeline'][collection][int(number)]
    if collection == 'spatial_relations':
        at_ms = detail.scope_bounds(item['scope'])[0]
    elif collection == 'action_groups':
        children = [a for a in ir['timeline']['actions'] if a['parent_id'] == item['id']]
        at_ms = min((a['start_ms'] for a in children), default=0)
    else:
        at_ms = item.get('start_ms', 0)
    return collection, item, at_ms


def _lean_eligible(channel_coverage):
    eligible, referents = set(), {}
    for item in channel_coverage or []:
        if item.get('channel') == 'prompt':
            continue
        if not (item.get('capability_basis') and item.get('asset_duty') and item.get('binding_verified') and item.get('result_check')):
            continue
        if not item.get('referent'):
            continue
        eligible.add(item['source_path'])
        referents[item['source_path']] = item['referent']
    return eligible, referents


def render(ir, bindings, target, mode, detail, audit_blocks, audit_coverage,
           start_ms=0, end_ms=None, layout=None, projection_profile='full', channel_coverage=None):
    """Return prompt, field-span coverage, prompt trace and unresolved gaps."""
    end_ms = ir['output']['duration_ms'] if end_ms is None else end_ms
    shots = [(i, shot, *detail.bounds(ir)[shot['id']]) for i, shot in enumerate(ir['shots'])
             if detail.overlap(detail.bounds(ir)[shot['id']], (start_ms, end_ms))]
    active_shots = {shot['id'] for _, shot, _, _ in shots}
    visible_people = set()
    for _, shot, a, b in shots:
        for track in ir['timeline']['composition_tracks']:
            if shot['id'] in track['shot_ids'] and detail.overlap((a, b), (track['start_ms'], track['end_ms'])):
                visible_people.update(_visible_entities(ir, shot['id'], max(a, track['start_ms'], start_ms), detail))
    if projection_profile not in ('full', 'lean'):
        raise ValueError('projection_profile must be full or lean')
    eligible, referents = _lean_eligible(channel_coverage) if projection_profile == 'lean' else (set(), {})
    rows_by_block = defaultdict(list)
    required = set()
    for row in audit_coverage:
        if row['channel'] == 'prompt' and row['disposition'] in EXECUTED:
            if row['source_path'] not in eligible:
                required.add(row['source_path'])
            if row['block'] is not None:
                rows_by_block[row['block']].append(row['source_path'])

    chunks = []

    def add(text, paths=(), object_id=None, shot_id=None, rule='PROMPT.PROJECT.1.3'):
        if not text:
            return None
        paths = list(dict.fromkeys(paths))
        if projection_profile == 'lean' and paths and set(paths) <= eligible:
            text = '；'.join(dict.fromkeys(referents[p] for p in paths))
        chunks.append({'text': text, 'paths': paths, 'object_id': object_id,
                       'shot_id': shot_id, 'rule': rule})
        return len(chunks) - 1

    def asset_for(binding):
        return (next((a for a in bindings if a['id'] == binding['asset_id']), None) or
                next((a for a in ir['assets'] if a['id'] == binding['asset_id']),
                     {'filename': 'UNRESOLVED'}))

    h3 = layout == 'h3_fields' or (layout is None and target == 'minimax-h3')
    if h3 and mode == 'reference':
        references = []
        ref_paths = []
        for i, binding in enumerate(ir['bindings']):
            if not set(binding['shot_ids']) & active_shots:
                continue
            asset = asset_for(binding)
            references.append(f"{asset['filename']}：{binding['target_id']} 的{'、'.join(binding['roles'])}；不继承{'、'.join(binding['negative_roles']) or '其他维度'}。")
            ref_paths += _leaves(detail, ir, f'/bindings/{i}/roles') + _leaves(detail, ir, f'/bindings/{i}/negative_roles')
            ref_paths += [f'/bindings/{i}/target_id']
            for j, source in enumerate(ir['assets']):
                if source['id'] == binding['asset_id']:
                    ref_paths.append(f'/assets/{j}/filename')
        add('subject_definitions:\n' + ('\n'.join(references) or '无已绑定参考。'), ref_paths)
        add(f"summary: {_seconds(end_ms-start_ms)}秒；{ir['output']['aspect_ratio']}；按既定镜头顺序制作。",
            ['/output/aspect_ratio'])
        add('retention_analysis: 仅按上述素材职责继承，不扩大到禁止维度。')
        body_prefix = 'detailed_description:'
    else:
        body_prefix = 'integrated_multimodal_description:' if h3 else None

    add((body_prefix + '\n' if body_prefix else '') +
        f"制作规格：{_seconds(end_ms-start_ms)}秒，{ir['output']['aspect_ratio']}。以下时间均从当前片段0秒开始。",
        ['/output/duration_ms', '/output/aspect_ratio'] if start_ms == 0 and end_ms == ir['output']['duration_ms'] else
        ['/output/aspect_ratio'])
    if not (h3 and mode == 'reference'):
        for i, binding in enumerate(ir['bindings']):
            if not set(binding['shot_ids']) & active_shots:
                continue
            asset = asset_for(binding)
            paths = [f'/bindings/{i}/target_id']
            paths += _leaves(detail, ir, f'/bindings/{i}/roles')
            paths += _leaves(detail, ir, f'/bindings/{i}/negative_roles')
            for j, source in enumerate(ir['assets']):
                if source['id'] == binding['asset_id']:
                    paths.append(f'/assets/{j}/filename')
            reference = (f"关键帧制作来源记录 {asset['filename']}（未作为本请求附件提供）" if asset.get('consumer') == 'image_host' else f"参考 {asset['filename']}")
            add(f"{reference}：用于 {binding['target_id']} 的{'、'.join(binding['roles'])}；禁止继承{'、'.join(binding['negative_roles']) or '未指定额外维度'}。",
                paths, binding['id'])

    # Node definitions are emitted once as spatial anchors, not repeated after
    # every state sample or action. They retain the original renderer's detail.
    for index, block in enumerate(audit_blocks):
        if block['channel'] == 'prompt' and block['path'].startswith('/timeline/spatial_nodes/'):
            add(block['text'], rows_by_block[index], block['id'])

    global_clauses = []
    shot_clauses = defaultdict(list)
    for i, clause in enumerate(ir['contract']):
        if clause['channel'] == 'post':
            continue
        scope = set()
        for check in clause['checks']:
            parts = check['path'].strip('/').split('/')
            if len(parts) >= 2 and parts[0] == 'shots' and parts[1].isdigit():
                scope.add(ir['shots'][int(parts[1])]['id'])
            elif len(parts) >= 3 and parts[0] == 'timeline' and parts[2].isdigit():
                item = ir['timeline'][parts[1]][int(parts[2])]
                scope.update(item.get('shot_ids', [item['shot_id']] if 'shot_id' in item else []))
            elif len(parts) >= 2 and parts[0] == 'bindings' and parts[1].isdigit():
                scope.update(ir['bindings'][int(parts[1])]['shot_ids'])
        if scope and not scope & active_shots:
            continue
        entry = (i, clause)
        if len(scope) == 1:
            shot_clauses[next(iter(scope))].append(entry)
        else:
            global_clauses.append(entry)
    def add_clause(i, clause, shot_id=None):
        paths = [f'/contract/{i}/requirement'] + [check['path'] for check in clause['checks']]
        add('保持与禁止变化：' + clause['requirement'], paths, clause['id'], shot_id)
    for i, clause in global_clauses:
        add_clause(i, clause)

    events = defaultdict(list)
    h3_sound = []
    h3_music = []
    for index, block in enumerate(audit_blocks):
        if block['channel'] != 'prompt' or block['path'].startswith(('/timeline/spatial_nodes/', '/timeline/state_samples/')):
            continue
        position = _event_position(ir, block['path'], detail)
        if position is None:
            continue
        collection, item, at_ms = position
        if collection not in EVENT_ORDER:
            continue
        if h3 and collection == 'audio_events' and item['kind'] in ('ambience', 'sfx'):
            h3_sound.append((block['text'], rows_by_block[index], block['id']))
            continue
        if h3 and collection == 'audio_events' and item['kind'] == 'music' and item['placement'] != 'environment':
            h3_music.append((block['text'], rows_by_block[index], block['id']))
            continue
        chosen = next((shot['id'] for _, shot, a, b in shots if
                       (a <= at_ms < b or (at_ms == b == end_ms)) and
                       (not item.get('shot_ids') or shot['id'] in item['shot_ids'])), None)
        if chosen is None:
            chosen = next((shot['id'] for _, shot, a, b in shots if
                           detail.overlap((a, b), (item.get('start_ms', at_ms), item.get('end_ms', at_ms + 1))) and
                           (not item.get('shot_ids') or shot['id'] in item['shot_ids'])), None)
        if chosen:
            events[chosen].append((max(at_ms, start_ms), EVENT_ORDER[collection], index, block))

    # A post-produced on-screen line still needs visual lip movements at its
    # original time. Its audio remains in post_production, not native sound.
    for i, audio in enumerate(ir['timeline']['audio_events']):
        if audio['route'] != 'post' or audio['placement'] != 'on_screen' or not audio['lip_sync']:
            continue
        if not detail.overlap((audio['start_ms'], audio['end_ms']), (start_ms, end_ms)):
            continue
        shot_id = next((s['id'] for _, s, a, b in shots if a <= audio['start_ms'] < b), None)
        if shot_id:
            events[shot_id].append((audio['start_ms'], 7, len(audit_blocks) + i,
                {'post_visual': audio, 'audio_index': i}))
    for i, sample in enumerate(ir['timeline']['state_samples']):
        if sample['shot_id'] in active_shots and start_ms <= sample['at_ms'] <= end_ms:
            events[sample['shot_id']].append((sample['at_ms'], -1, len(audit_blocks) + len(ir['timeline']['audio_events']) + i,
                                              {'state_sample': sample, 'sample_index': i}))

    scenes_seen = set()
    entities_seen = set()
    style_seen = {}
    state_seen = {}
    for shot_number, shot, shot_start, shot_end in shots:
        local_start = max(shot_start, start_ms) - start_ms
        local_end = min(shot_end, end_ms) - start_ms
        if h3:
            title = f"[Shot {shot_number+1}] At {_seconds(local_start)}s, duration {_seconds(local_end-local_start)}s"
        elif layout == 'kling_multi_shot_plan':
            title = f"Shot {shot_number+1} ({_seconds(local_end-local_start)}s): {shot['id']}，片段{_seconds(local_start)}–{_seconds(local_end)}秒"
        else:
            title = f"【镜头 {shot['id']}｜{_seconds(local_start)}–{_seconds(local_end)}秒】"
        paths = [f'/shots/{shot_number}/start_ms', f'/shots/{shot_number}/end_ms']
        rows = [title]
        scene_index = next(i for i, s in enumerate(ir['scenes']) if s['id'] == shot['scene_id'])
        scene = ir['scenes'][scene_index]
        if scene['id'] not in scenes_seen:
            rows += ['场景：' + scene['description'], '光线：' + detail.legacy.readable(scene['lighting'])]
            paths += _leaves(detail, ir, f'/scenes/{scene_index}/description')
            paths += _leaves(detail, ir, f'/scenes/{scene_index}/lighting')
            scenes_seen.add(scene['id'])
        visible = set()
        for track in ir['timeline']['composition_tracks']:
            if shot['id'] in track['shot_ids'] and detail.overlap(
                    (track['start_ms'], track['end_ms']), (max(shot_start, start_ms), min(shot_end, end_ms))):
                visible.update(_visible_entities(ir, shot['id'], max(shot_start, start_ms, track['start_ms']), detail))
        visible.update(entity['id'] for entity in ir['entities'] if entity['kind'] in ('prop', 'environment')
                       and any(entity['id'] in sample['entities'] and sample['shot_id'] == shot['id']
                               for sample in ir['timeline']['state_samples']))
        for entity_index, entity in enumerate(ir['entities']):
            if entity['id'] in visible and entity['id'] not in entities_seen:
                rows.append(f"{entity['label']}：{entity['appearance']}；保持{'、'.join(entity['locks']) or '既定外观'}。")
                for field in ('label', 'appearance', 'locks'):
                    paths += _leaves(detail, ir, f'/entities/{entity_index}/{field}')
                entities_seen.add(entity['id'])
        rows.append('切换：' + detail.legacy.readable(shot['transition']) +
                    ('；' + shot['transition_reason'] if shot['transition_reason'] else ''))
        rows.append('镜头透视：' + shot['camera']['lens_intent'])
        paths += _leaves(detail, ir, f'/shots/{shot_number}/transition')
        paths += _leaves(detail, ir, f'/shots/{shot_number}/transition_reason')
        paths += _leaves(detail, ir, f'/shots/{shot_number}/camera/lens_intent')
        style_key = detail.digest(shot['style'])
        if style_key not in style_seen:
            rows.append('风格：' + '；'.join(shot['style']))
            paths += _leaves(detail, ir, f'/shots/{shot_number}/style')
        else:
            chunks[style_seen[style_key]]['paths'] += _leaves(detail, ir, f'/shots/{shot_number}/style')
        shot_block = add('\n'.join(rows), paths, shot['id'], shot['id'])
        if style_key not in style_seen:
            style_seen[style_key] = shot_block

        grouped = defaultdict(list)
        for at_ms, priority, index, block in events[shot['id']]:
            grouped[at_ms].append((priority, index, block))
        for at_ms in sorted(grouped):
            before_group = len(chunks)
            add(f"{_seconds(at_ms-start_ms)}秒起：", shot_id=shot['id'], rule='PROMPT.BEAT.1.3')
            for _, index, block in sorted(grouped[at_ms], key=lambda row: (row[0], row[1])):
                if 'state_sample' in block:
                    sample, sample_index = block['state_sample'], block['sample_index']
                    visible_at = _visible_entities(ir, shot['id'], sample['at_ms'], detail)
                    changed, state_paths, updates = [], [], []
                    for entity_id, state in sample['entities'].items():
                        if entity_id not in visible_at:
                            continue
                        name = next(e['label'] for e in ir['entities'] if e['id'] == entity_id)
                        fields = []
                        for field, value in state.items():
                            path = f'/timeline/state_samples/{sample_index}/entities/{entity_id}/{field}'
                            fingerprint = detail.digest(value)
                            prior = state_seen.get((entity_id, field))
                            if prior and prior[0] == fingerprint:
                                chunks[prior[1]]['paths'] += _leaves(detail, ir, path)
                                continue
                            fields.append(detail.legacy.LABELS.get(field, field) + '：' + detail.legacy.readable(value))
                            state_paths += _leaves(detail, ir, path)
                            updates.append((entity_id, field, fingerprint))
                        if fields:
                            changed.append(name + '：' + '；'.join(fields))
                    if changed:
                        state_block = add(f"{_seconds(sample['at_ms']-start_ms)}秒状态：" + '\n'.join(changed),
                                          state_paths, sample['id'], shot['id'], 'PROMPT.STATE.DELTA.1.3')
                        for entity_id, field, fingerprint in updates:
                            state_seen[(entity_id, field)] = (fingerprint, state_block)
                elif 'post_visual' in block:
                    audio = block['post_visual']
                    speaker = next((e['label'] for e in ir['entities'] if e['id'] == audio['speaker_id']), audio['speaker_id'])
                    text = (f"{_seconds(audio['start_ms']-start_ms)}–{_seconds(audio['end_ms']-start_ms)}秒，"
                            f"{speaker}按原文说话人：“{audio['text']}”表演口型与停顿；声音由后期制作。")
                    i = block['audio_index']
                    paths = [f'/timeline/audio_events/{i}/{field}' for field in ('text', 'speaker_id', 'lip_sync', 'start_ms', 'end_ms')]
                    add(text, paths, audio['id'], shot['id'], 'PROMPT.POST.LIPS.1.3')
                else:
                    add(block['text'], rows_by_block[index], block['id'], shot['id'])
            if len(chunks) == before_group + 1:
                chunks.pop()
        for i, clause in shot_clauses[shot['id']]:
            add_clause(i, clause, shot['id'])

    if h3:
        sound = '\n'.join(text for text, _, _ in h3_sound)
        add('overall_soundscape: ' + (sound or '声音由独立音轨制作；不要求本次生成原生声音。'),
            [p for _, paths, _ in h3_sound for p in paths])
        music = '\n'.join(text for text, _, _ in h3_music)
        add('non_diegetic_music: ' + (music or 'N/A'),
            [p for _, paths, _ in h3_music for p in paths])

    prompt_parts = []
    coverage = []
    trace = []
    mapped = set()
    offset = 0
    for number, chunk in enumerate(chunks):
        if prompt_parts:
            offset += 2
        text = chunk['text']
        prompt_parts.append(text)
        start, end = offset, offset + len(text)
        trace.append({'block': number, 'text': text, 'ir_paths': list(dict.fromkeys(chunk['paths'])),
                      'source_refs': [], 'source_namespace': 'avir', 'rule': chunk['rule']})
        for path in dict.fromkeys(chunk['paths']):
            if path in mapped:
                continue
            try:
                source = detail.pointer(ir, path)
            except (KeyError, IndexError, TypeError):
                continue
            coverage.append({'source_path': path, 'source_sha256': detail.digest(source),
                             'object_id': chunk['object_id'], 'disposition': 'equivalent_conversion',
                             'channel': 'prompt', 'block': number, 'start_char': start, 'end_char': end,
                             'text_sha256': _text_hash(text), 'rule': chunk['rule']})
            mapped.add(path)
        offset = end
    prompt = '\n\n'.join(prompt_parts)
    def required_in_prompt(path):
        if path.startswith('/timeline/state_samples/'):
            return False
        parts = path.strip('/').split('/')
        if len(parts) >= 3 and parts[0] == 'entities' and parts[1].isdigit():
            entity = ir['entities'][int(parts[1])]
            if entity['kind'] == 'person' and entity['id'] not in visible_people:
                return False
        return True

    gaps = sorted(path for path in required - mapped if required_in_prompt(path))
    return prompt, coverage, trace, gaps


def verify(ir, prompt, coverage, detail, channel_owners=None):
    """Check source and exact prompt spans; semantic equivalence is Agent-reviewed."""
    errors = []
    for row in coverage:
        try:
            if detail.digest(detail.pointer(ir, row['source_path'])) != row['source_sha256']:
                raise ValueError('source changed')
            text = prompt[row['start_char']:row['end_char']]
            if not text or _text_hash(text) != row['text_sha256']:
                raise ValueError('prompt span changed')
        except (KeyError, IndexError, TypeError, ValueError):
            errors.append(detail.issue('E_PROMPT_COVERAGE', row['source_path'],
                                       '正文片段或来源指纹变化，需重编译并复核'))
    for item in channel_owners or []:
        if not (item.get('capability_basis') and item.get('asset_duty') and item.get('binding_verified') and item.get('result_check')):
            errors.append(detail.issue('E_PROMPT_COVERAGE', item.get('source_path', ''),
                                       '通道承担缺少能力依据、素材职责、已核验绑定或结果检查'))
    return errors
