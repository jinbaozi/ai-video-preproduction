"""Typed AVIR validation, scoped context construction and deterministic lowering."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'^  version:\s*[\"\']?([^\"\'\n]+)', (ROOT/'SKILL.md').read_text(), re.M).group(1).strip()


def _detail_support(version=None):
    import importlib.util
    path = Path(__file__).with_name('v52_support.py' if version and version.endswith('1.2') else 'v51_support.py')
    spec = importlib.util.spec_from_file_location('v51_support_' + str(path), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def digest(value):
    return sha256(encoded(value)).hexdigest()


def issue(code, path, message, severity='error'):
    return dict(code=code, path=path, message=message, severity=severity)


def schema_errors(value, name):
    validator = Draft202012Validator(read(ROOT / 'schemas' / f'{name}.schema.json'))
    return [issue('E_SCHEMA', '/' + '/'.join(map(str, e.absolute_path)), e.message)
            for e in sorted(validator.iter_errors(value), key=lambda e: str(e.absolute_path))]


def pointer(value, path):
    if not path.startswith('/'):
        raise KeyError(path)
    for part in path[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', part):
                raise KeyError(path)
            value = value[int(part)]
        else:
            value = value[part]
    return value


def walk(value, path=''):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from walk(child, path + '/' + key)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk(child, path + '/' + str(i))


def local_path(base, path):
    p = Path(path)
    return p if p.is_absolute() else Path(base) / p


def validate(ir, base):
    if ir.get('schema') in ('avir/1.1','avir/1.2'):
        return _detail_support(ir.get('schema')).validate_native(ir, ROOT, 'avir', base)
    errors = schema_errors(ir, 'avir')
    if errors:
        return errors
    maps = {key: {x['id']: x for x in ir[key]} for key in
            ('sources', 'entities', 'scenes', 'assets', 'bindings', 'shots', 'contract', 'expansions')}
    for key, items in maps.items():
        if len(items) != len(ir[key]):
            errors.append(issue('E_DUPLICATE_ID', '/' + key, '同一集合内 ID 必须唯一。'))
    sources, entities, scenes, assets, shots = [maps[k] for k in ('sources','entities','scenes','assets','shots')]
    for path, item in walk(ir):
        for ref in item.get('source_refs', []):
            if ref not in sources:
                errors.append(issue('E_SOURCE', path, f'来源 {ref} 未定义。'))
    for n, source in enumerate(ir['sources']):
        if source['sha256'] and '://' not in source['uri']:
            p = local_path(base, source['uri'])
            if not p.is_file() or sha256(p.read_bytes()).hexdigest() != source['sha256']:
                errors.append(issue('E_SOURCE_HASH', f'/sources/{n}', '来源文件缺失或内容哈希变化。'))
    last_end, previous = 0, None
    event_ids = set()
    for n, shot in enumerate(ir['shots']):
        path = f'/shots/{n}'
        if shot['scene_id'] not in scenes:
            errors.append(issue('E_SCENE', path, '镜头场景未定义。'))
        if shot['start_ms'] != last_end or shot['end_ms'] <= shot['start_ms']:
            errors.append(issue('E_TIMELINE', path, '镜头需从0连续覆盖时轴，不重叠、不留空，结束晚于开始。'))
        last_end = shot['end_ms']
        states = {}
        for key in ('start_state', 'end_state'):
            states[key] = {x['entity_id']: x for x in shot[key]}
            if len(states[key]) != len(shot[key]):
                errors.append(issue('E_DUPLICATE_STATE', path + '/' + key, '同一实体只能有一个状态。'))
            holders = {}
            for state in shot[key]:
                if state['entity_id'] not in entities or (state['gaze_target'] and state['gaze_target'] not in entities):
                    errors.append(issue('E_ENTITY', path + '/' + key, '状态实体或视线目标未定义。'))
                for prop in state['holding']:
                    if prop not in entities:
                        errors.append(issue('E_PROP', path, f'道具 {prop} 未定义。'))
                    if prop in holders:
                        errors.append(issue('E_OWNERSHIP', path, f'{prop} 有两个独占持有人；交接重叠应在动作阶段描述。'))
                    holders[prop] = state['entity_id']
        if set(states['start_state']) != set(states['end_state']):
            errors.append(issue('E_STATE_SET', path, '入画或出画实体也保留镜头两端世界状态，可见部位可为空。'))
        for visible in shot['composition']['required_visible']:
            a = states['start_state'].get(visible['entity_id'])
            b = states['end_state'].get(visible['entity_id'])
            if not a or not b or not set(visible['parts']) <= (set(a['visible_parts']) & set(b['visible_parts'])):
                errors.append(issue('E_VISIBILITY', path, '关键可见部位必须在起止构图均可见；中段转头另建镜头或调整可见要求。'))
        for event in shot['performance']:
            if event['id'] in event_ids:
                errors.append(issue('E_EVENT_ID', path, '动作事件 ID 必须全局唯一。'))
            event_ids.add(event['id'])
            if not shot['start_ms'] <= event['start_ms'] < event['end_ms'] <= shot['end_ms']:
                errors.append(issue('E_EVENT_TIME', path, '动作时间必须在本镜头内。'))
            actor = states['start_state'].get(event['actor_id'])
            if not actor:
                errors.append(issue('E_ACTOR', path, '动作主体没有空间状态。'))
            elif not set(event['needed_parts']) <= set(actor['visible_parts']):
                errors.append(issue('E_PERFORMANCE_VISIBILITY', path, '动作需要的部位在初态不可见。'))
            if event['micro_expression'] and (shot['camera']['shot_size'] in ('wide','full') or not {'face','eyes'} & set(event['needed_parts'])):
                errors.append(issue('E_MICRO_VISIBILITY', path, '微表情需要可读脸部景别与face/eyes部位；远景用身体行为表达。'))
        for rel in shot['relations']:
            for boundary in ('start_state','end_state'):
                a, b = (states[boundary].get(rel[k]) for k in ('subject','object'))
                if not a or not b:
                    errors.append(issue('E_RELATION', path, '相对关系的两端都必须有空间状态。'))
                    continue
                checks = {'world_left_of': a['position'][0] < b['position'][0],
                          'world_right_of': a['position'][0] > b['position'][0],
                          'world_in_front_of': a['position'][2] < b['position'][2],
                          'world_behind': a['position'][2] > b['position'][2]}
                if rel['relation'] in checks and not checks[rel['relation']]:
                    errors.append(issue('E_SPATIAL', path+'/'+boundary, '镜头不变世界关系与坐标矛盾；若本镜要改变关系，应分段建镜。'))
        if shot['transition'] == 'time_jump' and not shot['transition_reason']:
            errors.append(issue('E_TIME_JUMP', path, '时间跳跃需写明理由。'))
        if previous:
            if previous['scene_id'] == shot['scene_id'] and shot['transition'] != 'time_jump':
                old = {x['entity_id']: x for x in previous['end_state']}
                for eid, current in states['start_state'].items():
                    if eid in old:
                        # Shot scale and angle change visibility, not physical world state.
                        a = {k:v for k,v in old[eid].items() if k != 'visible_parts'}
                        b = {k:v for k,v in current.items() if k != 'visible_parts'}
                        if a != b:
                            errors.append(issue('E_CONTINUITY', path, f'{eid} 物理状态不承接上镜终态。'))
                if previous['camera']['axis_side'] != shot['camera']['axis_side'] and not shot['camera']['axis_change_reason']:
                    errors.append(issue('E_AXIS', path, '摄影机换轴侧需明确轴线重建理由。'))
            elif previous['scene_id'] != shot['scene_id'] and shot['transition'] == 'continuous':
                errors.append(issue('E_SCENE_CONTINUITY', path, '换场不能声明同空间连续镜头。'))
        previous = shot
    if last_end != ir['output']['duration_ms']:
        errors.append(issue('E_DURATION', '/output/duration_ms', '镜头总长与合同总时长不一致。'))
    authority = {}
    for n, binding in enumerate(ir['bindings']):
        path = f'/bindings/{n}'
        if binding['asset_id'] not in assets or binding['target_id'] not in (entities | scenes):
            errors.append(issue('E_BINDING', path, '参考资产或目标主体/场景未定义。'))
        if set(binding['roles']) & set(binding['negative_roles']):
            errors.append(issue('E_ROLE_CONFLICT', path, '同一参考职责不能同时允许与禁止。'))
        for sid in binding['shot_ids']:
            if sid not in shots:
                errors.append(issue('E_BINDING_SHOT', path, '参考镜头未定义。'))
            else:
                target = binding['target_id']
                participants = {s['entity_id'] for s in shots[sid]['start_state']}
                speakers = {a['speaker_id'] for a in ir['audio']['utterances'] if a['shot_id']==sid}
                if target != shots[sid]['scene_id'] and target not in participants | speakers:
                    errors.append(issue('E_BINDING_SCOPE',path,'参考目标不属于关联镜头的人物、说话人或场景。'))
            for role in binding['roles']:
                key = (sid,binding['target_id'],role)
                if key in authority and authority[key] != binding['asset_id']:
                    errors.append(issue('E_REF_AUTHORITY', path, '同镜同目标同维度存在竞争参考；先确定权威来源。'))
                authority[key] = binding['asset_id']
    audio_ids = set()
    for group in ('utterances','cues'):
        for n, cue in enumerate(ir['audio'][group]):
            path = f'/audio/{group}/{n}'
            if cue['id'] in audio_ids:
                errors.append(issue('E_AUDIO_ID', path, '声音事件ID必须唯一。'))
            audio_ids.add(cue['id'])
            shot = shots.get(cue['shot_id'])
            if not shot or not shot['start_ms'] <= cue['start_ms'] < cue['end_ms'] <= shot['end_ms']:
                errors.append(issue('E_AUDIO_TIME', path, '声音须位于关联镜头的时间范围内。'))
            if group == 'utterances':
                if cue['speaker_id'] not in entities:
                    errors.append(issue('E_SPEAKER', path, '说话人/旁白身份未定义。'))
                if cue['kind'] == 'dialogue' and shot and cue['speaker_id'] not in {x['entity_id'] for x in shot['start_state']}:
                    errors.append(issue('E_SPEAKER_SPACE', path, '画内/画外人物台词须有关联空间状态。旁白用narration。'))
                if len(cue['text']) / ((cue['end_ms']-cue['start_ms'])/1000) > 7:
                    errors.append(issue('W_SPEECH_DENSITY', path, '台词时间可能拥挤，需按实际语言和录音核验；不自动删词。','warning'))
            elif cue['sync_event'] and (not shot or cue['sync_event'] not in {e['id'] for e in shot['performance']}):
                errors.append(issue('E_SYNC_EVENT', path, '音效同步事件须来自本镜头。'))
    for n, clause in enumerate(ir['contract']):
        path = f'/contract/{n}'
        if not set(clause['shot_ids']) <= set(shots):
            errors.append(issue('E_CLAUSE_SHOT', path, '条款关联镜头未定义。'))
        if clause['level'] == 'hard' and clause['on_unsupported'] == 'warn':
            errors.append(issue('E_HARD_LOSS', path, '硬要求不能仅警告后丢失；选择block或已约定post。'))
        if clause['level'] == 'hard' and any(sources.get(x,{}).get('verification') == 'unverified' for x in clause['source_refs']):
            errors.append(issue('E_HARD_SOURCE', path, '未核验来源不能成为已确定硬事实。'))
        for check in clause['checks']:
            try:
                actual = pointer(ir, check['path'])
                valid = check['op'] == 'exists' or (check['op'] == 'equals' and actual == check['value']) or (check['op'] == 'contains' and check['value'] in actual)
            except (KeyError,IndexError,TypeError,ValueError):
                valid = False
            if not valid:
                errors.append(issue('E_CONSTRAINT' if clause['level']=='hard' else 'W_CONSTRAINT',path,f"{clause['id']} 的字段断言不成立：{check['path']}",'error' if clause['level']=='hard' else 'warning'))
    for n, expansion in enumerate(ir['expansions']):
        if expansion['shot_id'] not in shots:
            errors.append(issue('E_EXPANSION_SHOT', f'/expansions/{n}', '扩写镜头未定义。'))
        decision = sources.get(expansion['decision_ref'],{})
        if expansion['disposition'] == 'accepted' and (decision.get('kind') not in ('user','canon','director','art','design') or decision.get('verification')=='unverified' or (expansion['invented'] and not ir['policy']['allow_semantic_invention'])):
            errors.append(issue('E_INVENTION', f'/expansions/{n}', '扩写需决策来源；新增语义还须在当前策略内允许。'))
    for shot in ir['shots']:
        for event in shot['performance']:
            if event['psychology'] and event['psychology']['audibility']=='internal_voice' and not any(a['kind']=='internal_voice' and a['speaker_id']==event['actor_id'] and a['shot_id']==shot['id'] for a in ir['audio']['utterances']):
                errors.append(issue('E_INTERNAL_VOICE','/audio/utterances','有声心理活动需要明确的内心独白原文和时间事件。'))
    return errors


def context_view(ir):
    """Lossless scoped projection; never mutates authority or invents scene content."""
    result = []
    for shot in ir['shots']:
        ids = {x['entity_id'] for x in shot['start_state'] + shot['end_state']}
        ids |= {p for x in shot['start_state'] + shot['end_state'] for p in x['holding']}
        ids |= {x['gaze_target'] for x in shot['start_state'] if x['gaze_target']}
        ids |= {x['speaker_id'] for x in ir['audio']['utterances'] if x['shot_id']==shot['id']}
        ids |= {x['target_id'] for x in ir['bindings'] if shot['id'] in x['shot_ids']}
        result.append({'shot_id':shot['id'],'entity_ids':sorted(ids),'scene_id':shot['scene_id'],
                       'binding_ids':[b['id'] for b in ir['bindings'] if shot['id'] in b['shot_ids']],
                       'style':list(dict.fromkeys(shot['style'])),
                       'accepted_expansions':[x for x in ir['expansions'] if x['shot_id']==shot['id'] and x['disposition']=='accepted']})
    return {'schema':'context-ir/1.0','authoritative_ir_hash':digest(ir),'optimizer':'rules-only',
            'is_official_h3_context_ir':False,'shots':result,'proposals':[x for x in ir['expansions'] if x['disposition']=='proposed']}


def canonical_count(text):
    # Every Han codepoint, ASCII word/number and remaining non-space symbol is one unit.
    return len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U000323af]|[A-Za-z0-9_]+|[^\s]', text))


def profile(target):
    profiles = read(ROOT/'registries/capabilities.json')['profiles']
    result = next((x for x in profiles if x['id']==target), None)
    if result is None:
        raise ValueError(f'未知目标 {target}；使用 profiles 查看精确版本，不自动切换模型。')
    errors = schema_errors(result,'capability')
    if errors:
        raise ValueError(str(errors))
    return result


def resolve_assets(ir, cap, mode, base):
    rows, errors = [], []
    by_id = {x['id']:x for x in ir['assets']}
    referenced = list(dict.fromkeys(b['asset_id'] for b in ir['bindings']))
    counts = Counter()
    for aid in referenced:
        a = by_id[aid]
        counts[a['kind']] += 1
        related = [b for b in ir['bindings'] if b['asset_id']==aid]
        roles = set(r for b in related for r in b['roles'])
        slot = 'UNRESOLVED'
        if cap['native_reference_syntax']=='agnes':
            if mode=='reference' and a['kind'] in ('image','audio','video'):
                slot = '<' + {'image':'Picture','audio':'Audio','video':'Video'}[a['kind']] + f' {counts[a["kind"]]}>'
            elif mode=='keyframe' and a['kind']=='image':
                slot = '+'.join(r for r in ('first_frame','last_frame') if r in roles) or 'UNRESOLVED'
        row = {**a,'native_slot':slot,'array_index':counts[a['kind']]-1,'bindings':related,'local_verified':False}
        if a['path']:
            p = local_path(base,a['path'])
            if not p.is_file():
                errors.append(issue('E_ASSET_MISSING',aid,f"文件缺失：{a['filename']}"))
            elif not a['sha256'] or sha256(p.read_bytes()).hexdigest()!=a['sha256']:
                errors.append(issue('E_ASSET_HASH',aid,'参考文件需要匹配的SHA-256。'))
            elif p.name != a['filename']:
                errors.append(issue('E_FILENAME',aid,'真实文件名与登记文件名不一致。'))
            else:
                row['local_verified']=True
        else:
            errors.append(issue('E_ASSET_UNRESOLVED',aid,'尚未绑定可核验本地参考文件；不伪造上传结果。'))
        if a['kind'] != 'document' and a['inspection']!='observed':
            errors.append(issue('E_ASSET_UNSEEN',aid,'先实际查看/听取参考，才能编译其职责为已审参考。'))
        if a['kind']=='document':
            errors.append(issue('E_DOCUMENT_LOWERING',aid,'先抽取带页码/段落的事实到sources；不能直接把文档当视频参考附件。'))
        rows.append(row)
    if mode=='text' and referenced:
        errors.append(issue('E_MODE_MEDIA','/bindings','text模式不可携带参考；显式选择reference或keyframe。'))
    if mode in ('keyframe','reference') and not referenced:
        errors.append(issue('E_MODE_MEDIA','/bindings','此模式缺少必需参考。'))
    if mode=='reference' and any({'first_frame','last_frame'} & set(b['roles']) for b in ir['bindings']):
        errors.append(issue('E_MODE_ROLES','/bindings','首尾帧控制与reference模式不能混写。'))
    if mode=='keyframe':
        for b in ir['bindings']:
            if by_id[b['asset_id']]['kind']!='image' or not set(b['roles']) <= {'first_frame','last_frame'}:
                errors.append(issue('E_KEYFRAME_ROLE','/bindings','keyframe仅接收明确首帧/尾帧图片。'))
        for role in ('first_frame','last_frame'):
            if len({b['asset_id'] for b in ir['bindings'] if role in b['roles']})>1:
                errors.append(issue('E_KEYFRAME_DUPLICATE','/bindings',f'{role}存在多个输入。'))
    if mode=='reference':
        for kind in ('image','audio','video'):
            limit=cap['max_refs'][kind]
            if limit is not None and counts[kind]>limit:
                errors.append(issue('E_REF_LIMIT','/bindings',f'{kind}数量{counts[kind]}超过此入口{limit}。'))
        if cap['max_refs']['total'] is not None and sum(counts.values())>cap['max_refs']['total']:
            errors.append(issue('E_REF_LIMIT','/bindings','总参考数超限。'))
    return rows, errors


def target_errors(ir, cap, mode):
    errors=[]
    if mode not in cap['modes']:
        errors.append(issue('E_MODE','/mode','目标未声明此操作。'))
    if mode in ('edit','extend'):
        errors.append(issue('E_OPERATION_UNIMPLEMENTED','/mode','本版只编译新生成操作；编辑/延长需要输入视频和专属时间契约，不能退化成普通生成。'))
    d, limits=ir['output']['duration_ms'],cap['duration_ms']
    if (limits['min'] is not None and d<limits['min']) or (limits['max'] is not None and d>limits['max']) or (limits['allowed'] and d not in limits['allowed']) or (limits['step'] and d%limits['step']):
        errors.append(issue('E_TARGET_DURATION','/output/duration_ms','超出目标时长；修改分段合同或选择其他目标，不自动截断或改时长。'))
    for key,values in [('resolution',cap['resolutions']),('aspect_ratio',cap['ratios'])]:
        if values and ir['output'][key] is not None and ir['output'][key] not in values:
            errors.append(issue('E_TARGET_'+key.upper(),'/output/'+key,'目标入口不支持此值。'))
    if cap['id']=='veo3.1' and (mode=='reference' or (ir['output']['resolution'] or '').lower() in ('1080p','4k')) and d!=8000:
        errors.append(issue('E_VEO_DURATION','/output/duration_ms','Veo3.1参考图或高分辨率需8秒。'))
    if cap['backend']=='agnes_api_draft' and ir['output']['resolution']=='1K' and ir['output']['aspect_ratio']!='1:1':
        errors.append(issue('E_AGNES_SQUARE','/output','1K为固定1024×1024，无法保留非方形画幅合同。'))
    if cap['backend']=='prompt_plan':
        errors.append(issue('W_TRANSPORT_UNRESOLVED','/target','已编译模型提示词计划；当前渠道载荷、槽位、账户可用性仍待核验。','warning'))
    if cap['evidence_level']=='unverified':
        errors.append(issue('E_CAPABILITY_UNKNOWN','/target','此目标能力尚未取得足够一手证据，仅提供未就绪草案。'))
    return errors


LABELS={'references':'参考素材与职责','subjects':'主体与身份','scene':'场景与光线','space':'三维空间与人物对应',
        'composition':'画面构图','camera':'镜头表达','action':'动作与表演','audio':'台词与声音','style':'视觉细节','constraints':'制作约束'}
PARTS={'face':'面部','eyes':'眼睛','hands':'双手','feet':'双脚','back':'背部','mouth':'嘴部'}
SIZES={'wide':'远景','full':'全景','medium':'中景','close':'近景','detail':'特写'}
RELATIONS={'world_left_of':'在世界坐标左侧于','world_right_of':'在世界坐标右侧于',
           'world_in_front_of':'在世界坐标前方于','world_behind':'在世界坐标后方于','facing':'面向','touching':'接触'}


def compile_ir(ir, cap, mode, base):
    if ir.get('schema') in ('avir/1.1','avir/1.2'):
        from types import SimpleNamespace
        return _detail_support(ir.get('schema')).compile_video(SimpleNamespace(**globals()), ir, cap, mode, base)
    diagnostics=validate(ir,base)
    if any(x['severity']=='error' for x in diagnostics):
        return None, diagnostics
    context=context_view(ir)
    bindings, asset_errors=resolve_assets(ir,cap,mode,base)
    diagnostics += asset_errors + target_errors(ir,cap,mode)
    rows={x['id']:x for x in bindings}
    entities={x['id']:x for x in ir['entities']}
    def name(eid):
        return entities[eid]['label'] if eid in entities else eid
    def parts(items):
        return '、'.join(PARTS.get(x,x) for x in items)
    scenes={x['id']:x for x in ir['scenes']}
    template=read(ROOT/'templates/backends.json')['templates'][cap['template']]
    blocks, trace, post, losses=[],[],[],[]
    def add(text, paths, source_refs, rule='BACKEND.LOWER.V1'):
        blocks.append(text)
        trace.append({'block':len(blocks)-1,'text':text,'ir_paths':paths,'source_refs':source_refs,
                      'source_namespace':'registry' if rule.startswith('TEMPLATE.') else 'avir','rule':rule})
    add(template['guidance'],[],cap['source_refs'],'TEMPLATE.'+cap['template'].upper()+'.V1')
    if cap['backend']=='prompt_plan':
        add(f"制作规格：{ir['output']['duration_ms']/1000:g}秒，{ir['output']['aspect_ratio']}；分辨率意图：{ir['output']['resolution'] or '未指定'}。",['/output'],[], 'PARAMETER.INTENT.V1')
    for n,(shot,view) in enumerate(zip(ir['shots'],context['shots'])):
        sp=f'/shots/{n}'
        sections={k:[] for k in LABELS}
        for bid in view['binding_ids']:
            b=next(x for x in ir['bindings'] if x['id']==bid)
            a=rows[b['asset_id']]
            sections['references'].append(f"{a['filename']}（资产 {a['id']}；槽位 {a['native_slot']}）用于 {b['target_id']} 的 {'、'.join(b['roles'])}；禁止继承 {'、'.join(b['negative_roles']) or '无额外禁止维度'}。")
        for eid in view['entity_ids']:
            if eid in entities:
                e=entities[eid]
                sections['subjects'].append(f"{e['label']}（{eid}）：{e['appearance']}；固定 {'、'.join(e['locks']) or '按既定外观'}。")
        scene=scenes[shot['scene_id']]
        sections['scene']=[scene['description'],scene['lighting']]
        sections['space'].append(f"世界坐标以米为单位，依次为向右、向上、纵深；原点 {scene['coordinates']['origin']}。坐标为布局意图。")
        for label,key in [('起始','start_state'),('结束','end_state')]:
            for st in shot[key]:
                sections['space'].append(f"{label}{name(st['entity_id'])}位于 {st['position']}，{st['pose']}，朝向 {st['facing']}，视线目标 {name(st['gaze_target']) or '未指定'}，支撑 {st['support']}，持有 {'、'.join(name(x) for x in st['holding']) or '无'}，可见 {parts(st['visible_parts']) or '画外'}。")
        sections['space'] += [f"{name(r['subject'])} {RELATIONS[r['relation']]} {name(r['object'])}：{r['description']}" for r in shot['relations']]
        sections['composition']=[shot['composition'][k] for k in ('framing','layers','screen_positions')]
        sections['composition'] += [f"保留{name(v['entity_id'])}的{parts(v['parts'])}可见。" for v in shot['composition']['required_visible']]
        c=shot['camera']
        sections['camera']=[f"机位 {c['position']}，观察点 {c['look_at']}，{SIZES[c['shot_size']]}，{c['angle']}，俯仰意图 {c['pitch_deg']}度，横滚意图 {c['roll_deg']}度；{c['lens_intent']}；{c['movement']}；路径 {c['trajectory']}；焦点 {c['focus']}；位于轴线{c['axis_side']}侧。数值光学与路径为创作意图。"]
        if c['axis_change_reason']:
            sections['camera'].append(c['axis_change_reason'])
        for event in shot['performance']:
            text=f"{event['start_ms']/1000:g}–{event['end_ms']/1000:g}秒，{name(event['actor_id'])}：触发 {event['trigger']}；"
            if event['micro_expression']:
                text+=f"微反应 {event['micro_expression']}；"
            text+=f"动作 {event['action']}；反馈 {event['feedback']}；落定 {event['settle']}。"
            if event['psychology']:
                p=event['psychology']
                text+=f"心理动机 {p['intent']}，用可见行为 {p['visible_translation']} 表现。"
                if p['audibility']=='silent':
                    text+='心理动机不朗读、不转成新增台词。'
            sections['action'].append(text)
        for key in ('utterances','cues'):
            for i,audio in enumerate(ir['audio'][key]):
                if audio['shot_id']!=shot['id']:
                    continue
                if key=='utterances':
                    kind={'dialogue':'对白','narration':'旁白','internal_voice':'内心独白'}[audio['kind']]
                    text=f"{audio['start_ms']/1000:g}–{audio['end_ms']/1000:g}秒，{kind}，{entities[audio['speaker_id']]['label']}：“{audio['text']}”；语言 {audio['language']}；{audio['delivery']}。"
                else:
                    text=f"{audio['start_ms']/1000:g}–{audio['end_ms']/1000:g}秒，{audio['kind']}：{audio['description']}；同步事件 {audio['sync_event'] or '无指定'}。"
                if audio['route']=='post':
                    post.append({'id':audio['id'],'shot_id':shot['id'],'instruction':text,'path':f'/audio/{key}/{i}','status':'PLANNED'})
                    if key=='utterances' and audio['kind']=='dialogue':
                        sections['audio'].append('后期配音的画内表演：'+text+'画面按此原文安排说话口型与停顿，声音由后期合成；不得改成另一句。')
                else:
                    sections['audio'].append(text)
                    if cap['native_audio'] is not True:
                        diagnostics.append(issue('E_AUDIO_UNVERIFIED',f'/audio/{key}/{i}','此入口原生声音控制未充分核验；保留需求，明确后期路线或补证。'))
        sections['style']=view['style']+[x['text'] for x in view['accepted_expansions']]
        for clause in ir['contract']:
            if clause['shot_ids'] and shot['id'] not in clause['shot_ids']:
                continue
            if clause['channel']=='post':
                continue
            # Preserve human-readable hard constraints as well as parameter mapping.
            sections['constraints'].append(clause['requirement'])
        if not sections['audio']:
            sections['audio'].append('本镜头没有分配给生成模型的台词或声音内容；按后期声音清单制作。')
        add(f"镜头 {shot['id']}｜{shot['start_ms']/1000:g}–{shot['end_ms']/1000:g}秒｜{shot['transition']}：{shot['purpose']}"+(f"；{shot['transition_reason']}" if shot['transition_reason'] else ''),[sp],shot['source_refs'])
        for key in template['sections']:
            if not sections[key]:
                continue
            paths=[sp]
            if key in ('space','composition','camera','action','style'):
                fields={'space':['start_state','end_state','relations'],'composition':['composition'],
                        'camera':['camera'],'action':['performance'],'style':['style']}[key]
                paths=[sp+'/'+field for field in fields]
            if key=='subjects': paths += [f'/entities/{i}' for i,e in enumerate(ir['entities']) if e['id'] in view['entity_ids']]
            if key=='scene': paths += [f'/scenes/{i}' for i,s in enumerate(ir['scenes']) if s['id']==shot['scene_id']]
            if key=='references': paths += [f'/bindings/{i}' for i,b in enumerate(ir['bindings']) if b['id'] in view['binding_ids']]
            if key=='audio': paths += [f'/audio/{group}/{i}' for group in ('utterances','cues') for i,a in enumerate(ir['audio'][group]) if a['shot_id']==shot['id'] and (a['route']=='native' or (group=='utterances' and a['kind']=='dialogue'))]
            if key=='style': paths += [f'/expansions/{i}' for i,x in enumerate(ir['expansions']) if x['shot_id']==shot['id'] and x['disposition']=='accepted']
            if key=='constraints': paths += [f'/contract/{i}' for i,c in enumerate(ir['contract']) if c['channel']!='post' and (not c['shot_ids'] or shot['id'] in c['shot_ids'])]
            refs=set(shot['source_refs'])
            for path in paths:
                node=pointer(ir,path)
                for _,item in walk(node):
                    refs.update(item.get('source_refs',[]))
            add(LABELS[key]+'：'+' '.join(sections[key]),paths,sorted(refs))
    for c in ir['contract']:
        if c['channel']=='post':
            post.append({'id':c['id'],'instruction':c['requirement'],'execution':c['execution'],'status':'PLANNED'})
    prompt='\n\n'.join(blocks)
    count=canonical_count(prompt)
    budget=ir['policy']['max_canonical_units']
    if (budget is not None and count>budget) or (cap['max_prompt_chars'] is not None and len(prompt)>cap['max_prompt_chars']):
        diagnostics.append(issue('E_BUDGET','/prompt','已只去除完全重复风格词，仍超预算；保留完整草案，需修订低优先内容或分段。'))
    params=deepcopy(ir['output'])
    payload=None
    if cap['backend']=='agnes_api_draft':
        params={'model':cap['model'],'mode':mode,'seconds':str(ir['output']['duration_ms']//1000),'aspect_ratio':ir['output']['aspect_ratio'],'n':1}
        if ir['output']['resolution']:
            params['size']=ir['output']['resolution']
        media={}
        for row in bindings:
            if not row['public_url'] or urlparse(row['public_url']).scheme not in ('https','http'):
                diagnostics.append(issue('W_UPLOAD_REQUIRED',row['id'],'尚无外部可访问的素材URL；载荷草案暂不生成。','warning'))
                continue
            if mode=='reference' and row['kind'] in ('image','audio','video'):
                key={'image':'images','audio':'audios','video':'videos'}[row['kind']]
                media.setdefault(key,[]).append({'url':row['public_url']} if row['kind']=='video' else row['public_url'])
            elif mode=='keyframe':
                for key in row['native_slot'].split('+'):
                    media[key]=row['public_url']
        if not any(x['severity']=='error' or x['code']=='W_UPLOAD_REQUIRED' for x in diagnostics):
            payload={**params,'prompt':prompt,**media}
    for d in diagnostics:
        if d['severity']=='error':
            losses.append({'code':d['code'],'path':d['path'],'disposition':'blocked','detail':d['message'],'semantic_content_discarded':False})
    coverage=[]
    for c in ir['contract']:
        coverage.append({'id':c['id'],'level':c['level'],'source_refs':c['source_refs'],'ir_paths':[x['path'] for x in c['checks']],
                         'channel':c['channel'],'execution':c['execution'],'acceptance':c['acceptance'],
                         'static_assertions':'FAIL' if any(c['id'] in d['message'] and d['code'] in ('W_CONSTRAINT','E_CONSTRAINT') for d in diagnostics) else 'PASS',
                         'realization':'NOT_RUN','status':'PLANNED' if c['channel']=='post' else 'EMITTED'})
    artifact={'schema':'compiled-artifact/1.0','target':cap['id'],'mode':mode,'status':'BLOCKED' if any(x['severity']=='error' for x in diagnostics) else 'COMPILED','prompt':prompt,'parameters':params,'parameter_semantics':'api_fields' if cap['backend']=='agnes_api_draft' else 'intent_only','payload_draft':payload,'asset_bindings':bindings,'diagnostics':diagnostics,'losses':losses,'trace':trace,'coverage':coverage,'post_production':post,'counts':{'canonical_count':count,'canonical_algorithm':'CPT-v1','native_count':None,'native_tokenizer':None,'chars':len(prompt)},'execution':{'submitted':False,'runnable':False,'media_qa':'NOT_RUN','next_steps':['审阅合同的语义、台词及可见性；静态断言不能证明视频效果。','核验当前入口、账户、模式、素材尺寸时长和上传槽位；按原授权由宿主执行。','保存供应商任务ID与实收媒体；按合同检查画面、声音和连续性。']}}
    if ir['policy']['context_ir']=='optional':
        artifact['diagnostics'].append(issue('W_OPTIMIZER_FALLBACK','/policy/context_ir','外部Context-IR未配置；使用完整有效Core与本地规则视图，不改变硬语义。','warning'))
    failures=schema_errors(artifact,'compile-artifact')
    if failures:
        raise ValueError(str(failures))
    return artifact, context
