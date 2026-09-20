"""Explicit StoryboardIR -> AVIR lowering and source-bound role briefs."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path

VERSION = '1.2.0'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def pointer(value, path):
    if path == '':
        return value
    if not path.startswith('/'):
        raise ValueError('Expected JSON Pointer')
    for part in path[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def assert_check(value, check):
    try:
        actual = pointer(value, check['path'])
        return (check['op'] == 'exists' or
                check['op'] == 'equals' and actual == check['value'] or
                check['op'] == 'contains' and check['value'] in actual)
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def role_brief(role, artifacts, scope=None):
    """A briefing references authority; it is not a fabricated downstream IR."""
    return {'schema': 'role-brief/1.0', 'role': role, 'scope': scope or {},
            'inputs': deepcopy(artifacts), 'ownership': {
                'canon': 'source facts, stable IDs, user decisions and asset registry',
                'screenplay': 'story causality, character choices, knowledge, reveal constraints, dialogue and outcomes',
                'director': 'audiovisual realization of screenplay constraints, blocking and explicitly locked shot/performance fields',
                'art': 'world, set topology, costume, material and practical light sources',
                'storyboard': 'unlocked shot/panel/timing details and continuity',
                'compiler': 'loss-aware model adaptation; no semantic invention'},
            'instructions': ['Read the referenced native files and their schemas.',
                             'Reuse IDs and declared locks; report owner conflicts by field.',
                             'Keep source facts, observations and design additions distinct.']}


def image_briefs(kind, ir):
    if kind == 'storyboard' and ir.get('schema_version') == 'storyboard-ir/1.2':
        from .v52_adapters import image_briefs as spatial_briefs
        return spatial_briefs(ir)
    if kind == 'storyboard' and ir.get('schema_version') == 'storyboard-ir/1.1':
        from .v51_adapters import image_briefs as detailed_briefs
        return detailed_briefs(ir)
    if kind == 'art':
        return [{'id': a['id'], 'entity_id': a.get('entity_id'), 'kind': a['kind'],
                 'name': a['name'], 'design': a['design'], 'locks': a['identity_locks'],
                 'world': ir['world'], 'set': ir['set'] if a['kind']=='set' else None,
                 'references': [r for r in ir['references'] if r['asset_id'] == a['id']],
                 'source_pointer': f'/assets/{i}', 'source_hash': digest(ir),
                 'dependency_paths': [f'/assets/{i}', '/world'] + (['/set'] if a['kind']=='set' else []) +
                     [f'/references/{j}' for j,r in enumerate(ir['references']) if r['asset_id']==a['id']],
                 'allowed_change': 'prompt expression only; preserve approved design'}
                for i, a in enumerate(ir['assets'])]
    if kind == 'storyboard':
        return [{'id': p['id'], 'shot_id': s['id'], 'scene_id': s['scene_id'], 'kind': 'board',
                 'frame': p['frame'], 'moment': p['moment'], 'must_show': p['must_show'],
                 'camera': s['camera'], 'composition': s['composition'],
                 'state_start': s['state_start'], 'events': s['events'],
                 'bindings': [b for b in ir['bindings'] if s['id'] in b['shot_ids']],
                 'source_pointer': f'/shots/{i}/panels/{j}', 'source_hash': digest(ir),
                 'dependency_paths': [f'/shots/{i}/panels/{j}'] +
                     [f'/shots/{i}/{field}' for field in ('camera','composition','state_start','events')] +
                     [f'/bindings/{n}' for n,b in enumerate(ir['bindings']) if s['id'] in b['shot_ids']],
                 'allowed_change': 'depict only this moment; do not compress the action into one still'}
                for i, s in enumerate(ir['shots']) for j, p in enumerate(s['panels'])]
    raise ValueError('Image briefs require art or storyboard')


def storyboard_to_avir(ir, base, overrides=None):
    if ir.get('schema_version') == 'storyboard-ir/1.2':
        from .v52_adapters import storyboard_to_avir as spatial_conversion
        return spatial_conversion(ir, base, overrides, storyboard_to_avir)
    if ir.get('schema_version') == 'storyboard-ir/1.1':
        from .v51_adapters import storyboard_to_avir as detailed_conversion
        return detailed_conversion(ir, base, overrides, storyboard_to_avir)
    if ir.get('schema_version') != 'storyboard-ir/1.0':
        raise ValueError('Expected StoryboardIR 1.0, not compiler-handoff.json')
    source = deepcopy(ir)
    # JSON object insertion order must not change state-array indices or the
    # strings lowered from structured composition/lighting/event data.
    ir = json.loads(encoded(ir))
    base = Path(base).resolve()
    paths, losses, rounding = {}, [], {}
    fps = Decimal(ir['delivery']['fps'])

    def ms(frame):
        exact = Decimal(frame) * 1000 / fps
        result = int(exact.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        rounding[str(frame)] = {'milliseconds': result, 'error_ms': float(Decimal(result) - exact)}
        return result

    def bind(source_path, target_path):
        paths[source_path] = target_path

    def lost(path, reason, hard=True):
        losses.append({'path': path, 'reason': reason, 'severity': 'error' if hard else 'notice'})

    result = dict(schema='avir/1.0', project_id=ir['project_id'], revision=ir['revision'],
                  tenant_id='local', intent=ir['intent'], sources=[], entities=[], scenes=[],
                  assets=[], bindings=[], output={'duration_ms': ms(ir['delivery']['total_frames']),
                      'aspect_ratio': ir['delivery']['aspect_ratio'], 'resolution': ir['delivery']['resolution']},
                  shots=[], audio={'utterances': [], 'cues': []}, contract=[],
                  policy={'allow_semantic_invention': False, 'max_canonical_units': None, 'context_ir': 'rules'},
                  expansions=[])
    bind('/delivery', '/output')
    for a, b in [('total_frames', 'duration_ms'), ('aspect_ratio', 'aspect_ratio'), ('resolution', 'resolution')]:
        bind('/delivery/' + a, '/output/' + b)
    for s in ir['sources']:
        uri = s['uri']
        if '://' not in uri:
            uri = str((base / uri).resolve())
        result['sources'].append({'id': s['id'], 'kind': {'script': 'user', 'observation': 'observed'}.get(s['kind'], s['kind']),
            'uri': uri, 'locator': s['locator'], 'claim': s['excerpt'],
            'verification': s['verification'], 'sha256': s['file_sha256']})
    allowed_source = {'user', 'observed', 'canon', 'director', 'art', 'official', 'community', 'design', 'optimizer'}
    for s in result['sources']:
        if s['kind'] not in allowed_source:
            s['kind'] = 'design' if s['verification'] == 'inference' else 'canon'
    for i, entity in enumerate(ir['entities']):
        if entity['kind'] == 'voice':
            lost(f'/entities/{i}', 'AVIR 1.0 has no voice-only entity. An explicit audio adaptation is required.')
            continue
        result['entities'].append({'id': entity['id'], 'kind': entity['kind'], 'label': entity['name'],
            'appearance': entity['appearance'], 'locks': entity['identity_locks'], 'source_refs': entity['source_refs']})
        for a, b in [('name','label'), ('identity_locks','locks'), ('id','id'), ('kind','kind'), ('appearance','appearance')]:
            bind(f'/entities/{i}/{a}', f'/entities/{len(result["entities"])-1}/{b}')
    bind('/entities', '/entities')
    for i, scene in enumerate(ir['scenes']):
        if scene['coordinates']['axes'] != 'x=world-right,y=up,z=depth':
            lost('/scenes', 'Coordinate basis requires an explicit transformation.')
        result['scenes'].append({k: deepcopy(scene[k]) for k in ('id','description','coordinates','source_refs')})
        result['scenes'][-1]['lighting'] = json.dumps(scene['lighting'], ensure_ascii=False)
        for field in ('id','description','coordinates','lighting'):
            bind(f'/scenes/{i}/{field}',f'/scenes/{i}/{field}')
    for asset in ir['assets']:
        result['assets'].append(dict(id=asset['id'], kind='image', filename=asset['filename'],
            path=str((base / asset['path']).resolve()) if asset['path'] else None,
            sha256=asset['sha256'], public_url=None,
            inspection='observed' if asset['status']=='observed' else 'metadata_only', source_refs=asset['source_refs']))
    for b in ir['bindings']:
        valid_roles = {'identity','wardrobe','scene','style','motion','camera','pacing','voice','music','first_frame','last_frame','source_content'}
        roles = ['source_content' if r=='composition' else r for r in b['roles']]
        exclusions = [r for r in b['exclude'] if r in valid_roles]
        if len(exclusions) != len(b['exclude']):
            lost('/bindings/' + b['id'], 'Free-text exclusions are retained in the original binding and prompt contract.', False)
        result['bindings'].append(dict(id=b['id'], asset_id=b['asset_id'], target_id=b['entity_id'],
            shot_ids=b['shot_ids'], roles=roles, negative_roles=exclusions,
            source_refs=next(a['source_refs'] for a in ir['assets'] if a['id']==b['asset_id'])))
    for i, shot in enumerate(ir['shots']):
        prefix = f'/shots/{i}'
        cam = shot['camera']
        subjects = {s['entity_id']: s for s in shot['composition']['subjects']}
        dst = dict(id=shot['id'], scene_id=shot['scene_id'], start_ms=ms(shot['start_frame']),
            end_ms=ms(shot['end_frame']), purpose=shot['purpose'],
            transition={'scene_change':'scene_change','time_jump':'time_jump'}.get(shot['transition']['type'],'cut'),
            transition_reason=shot['transition']['reason'],
            composition={'framing': shot['composition']['rule'], 'layers': shot['composition']['depth_layers'],
                'screen_positions': json.dumps(shot['composition'],ensure_ascii=False),
                'required_visible': [{'entity_id': s['entity_id'], 'parts': s['visible_parts']} for s in subjects.values()]},
            camera=dict(position=cam['start_m'], look_at=cam['look_at_m'], shot_size=cam['size'],
                angle=f"俯仰意图{cam['pitch_deg']}度，画面旋转{cam['roll_deg']}度；{cam['motivation']}",
                pitch_deg=cam['pitch_deg'], roll_deg=cam['roll_deg'], lens_intent=cam['lens_intent'],
                movement=cam['movement'], trajectory=f"{cam['path']}；起点{cam['start_m']}，终点{cam['end_m']}",
                focus=cam['focus'], axis_side={'negative':'A','positive':'B','on_axis':'on_axis'}.get(cam['axis_side'],'on_axis'),
                axis_change_reason=cam['axis_reason']), relations=[], start_state=[], end_state=[], performance=[],
            style=[ir['style']['medium'], ir['style']['rationale']], source_refs=shot['source_refs'])
        for a,b in [('start_frame','start_ms'), ('end_frame','end_ms'),('purpose','purpose')]:bind(prefix+'/'+a,prefix+'/'+b)
        for a,b in [('size','shot_size'),('start_m','position'),('look_at_m','look_at'),('pitch_deg','pitch_deg'),('roll_deg','roll_deg')]:
            bind(prefix+'/camera/'+a,prefix+'/camera/'+b)
        for relation in shot['relations']:
            if relation['at'] != 'both' or relation['relation'] not in {'world_left_of','world_right_of','world_in_front_of','world_behind','facing','touching'}:
                lost(prefix+'/relations', 'Boundary-specific or unsupported spatial relation needs explicit adaptation.')
            else:
                dst['relations'].append({k:relation[k] for k in ('subject','relation','object')} | {'description':relation['criterion']})
        for before, after in [('state_start','start_state'),('state_end','end_state')]:
            states = shot[before]
            for j,(eid,state) in enumerate(states.items()):
                holding = [prop for prop,v in states.items() if v['holder'] and v['holder'].split('.')[0]==eid]
                dst[after].append(dict(entity_id=eid, position=state['position_m'],
                    pose=state['pose']+f"；状态={state['condition']}；持有人={state['holder']}；接触={state['contacts']}",
                    facing=f"身体yaw={state['yaw_deg']}；头部yaw={state['head_yaw_deg']}；头部pitch={state['head_pitch_deg']}",
                    gaze_target=state['gaze_target'], support=state['support'], holding=holding,
                    visible_parts=subjects.get(eid,{}).get('visible_parts',[])))
                for a,b in [('position_m','position'),('gaze_target','gaze_target'),('support','support')]:
                    bind(prefix+'/'+before+'/'+eid+'/'+a,prefix+'/'+after+'/'+str(j)+'/'+b)
                bind(prefix+'/'+before+'/'+eid+'/holder',prefix+'/'+after+'/'+str(j)+'/pose')
        for group in ('performance','events'):
            for j, event in enumerate(shot[group]):
                k=len(dst['performance'])
                psychology=event.get('psychology')
                if psychology:psychology={key:psychology[key] for key in ('intent','visible_translation','audibility')}
                action=event['action']
                if group=='performance':
                    action+='；'+ '；'.join(key+'：'+str(event[key]) for key in ('face','eyes','hands','body','voice') if event.get(key))
                else:
                    action+=f"；执行部位={event['effector']}；目标={event['target_id']}"
                dst['performance'].append(dict(id=event['id'],start_ms=ms(event['start_frame']),end_ms=ms(event['end_frame']),
                    actor_id=event['actor_id'],trigger=event['trigger'],micro_expression=event.get('micro_expression'),
                    needed_parts=event.get('needed_parts',[]),action=action,feedback=event['feedback'],
                    settle=event.get('settle') or json.dumps(event['changes'],ensure_ascii=False),
                    psychology=psychology,source_refs=event['source_refs']))
                for a,b in [('start_frame','start_ms'),('end_frame','end_ms'),('actor_id','actor_id')]:
                    bind(f'{prefix}/{group}/{j}/{a}',f'{prefix}/performance/{k}/{b}')
        result['shots'].append(dst)
    for i,u in enumerate(ir['audio']['utterances']):
        result['audio']['utterances'].append({k:deepcopy(u[k]) for k in ('id','shot_id','speaker_id','kind','text','language','route')} |
            {'start_ms':ms(u['start_frame']),'end_ms':ms(u['end_frame']),
             'delivery':u['delivery']+f"；发声位置={u['placement']}；口型要求={u['lip_sync']}", 'source_refs':[u['source_id']]})
        for field in ('text','speaker_id','kind','shot_id'):bind(f'/audio/utterances/{i}/{field}',f'/audio/utterances/{i}/{field}')
    for cue in ir['audio']['cues']:
        for shot in ir['shots']:
            start=max(cue['start_frame'],shot['start_frame']);end=min(cue['end_frame'],shot['end_frame'])
            if shot['id'] not in cue['shot_ids'] or start>=end:continue
            result['audio']['cues'].append(dict(id=cue['id']+'_'+shot['id'],shot_id=shot['id'],
                start_ms=ms(start),end_ms=ms(end),kind=cue['kind'],
                description=cue['description']+f"；混音={cue['mix']}；精确同步帧={cue['sync_frame']}",
                sync_event=cue['sync_event'] if cue['sync_event'] in {x['id'] for x in shot['events']+shot['performance']} else None,
                route=cue['route'],source_refs=cue['source_refs']))
    for clause in ir['contract']:
        checks=[]
        for check in clause['checks']:
            if not assert_check(ir,check):
                lost(check['path'],'Source assertion fails before conversion.');continue
            target=paths.get(check['path'])
            override=(overrides or {}).get(check['path'])
            if override:
                if not override.get('reason') or override.get('owner')!=clause['owner']:
                    lost(check['path'],'Explicit mapping must identify its source owner and reason.');continue
                mapped=override['check']
            elif target:
                if check['path'].endswith('/holder'):
                    mapped={'path':target,'op':'contains','value':'持有人='+str(check['value'])}
                elif check['op']=='contains' and check['path'] not in ('/entities','/delivery'):
                    mapped={'path':target,'op':'contains','value':check['value']}
                else:
                    mapped={'path':target,'op':'exists' if check['op']=='exists' else 'equals','value':deepcopy(pointer(result,target))}
            else:
                lost(check['path'],'No verified AVIR assertion mapping; explicit owner-reviewed mapping required.',clause['strength']=='hard');continue
            if not assert_check(result,mapped):lost(check['path'],'Mapped assertion does not hold.');continue
            checks.append(mapped)
        if not checks:continue
        result['contract'].append(dict(id=clause['id'],level=clause['strength'],requirement=clause['statement'],
            source_refs=clause['source_refs'],shot_ids=clause['shot_ids'],checks=checks,
            channel=clause['channel'],execution=clause['execution'],
            acceptance={'method':'media','criterion':'；'.join(a['criterion'] for a in clause['acceptance'])},
            on_unsupported={'block':'block','post':'post'}.get(clause['fallback'],'warn')))
    # Free-text negative inheritance remains in actual copyable contract text.
    for binding in ir['bindings']:
        if binding['exclude'] or 'composition' in binding['roles']:
            idx=next(i for i,b in enumerate(result['bindings']) if b['id']==binding['id'])
            result['contract'].append(dict(id='BIND_'+binding['id'],level='hard',
                requirement=f"参考{binding['asset_id']}只继承{binding['roles']}；禁止继承{binding['exclude']}；画格只是指定瞬间，不代表后续动作。",
                source_refs=result['bindings'][idx]['source_refs'],shot_ids=binding['shot_ids'],
                checks=[{'path':f'/bindings/{idx}/asset_id','op':'equals','value':binding['asset_id']}],
                channel='prompt',execution='按参考维度生成并审查',acceptance={'method':'media','criterion':'参考职责无越界'},on_unsupported='block'))
    report={'adapter':VERSION,'source_hash':digest(source),'target_hash':digest(result),
            'status':'BLOCKED' if any(x['severity']=='error' for x in losses) else 'MAPPED',
            'field_mapping':paths,'rounding':rounding,'overrides':overrides or {},'losses':losses,
            'sidecar':source,'sidecar_scope':['beats','panels','events','upstream locks','handedness','exact audio synchronization'],
            'submitted':False,'media_qa':'NOT_RUN'}
    return result,report
