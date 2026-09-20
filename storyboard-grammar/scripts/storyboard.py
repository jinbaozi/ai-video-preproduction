#!/usr/bin/env python3
"""Offline storyboard validation, review documents and versioned handoff. No media transport."""
import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlparse

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'^  version:\s*[\"\']?([^\"\'\n]+)', (ROOT/'SKILL.md').read_text(), re.M).group(1).strip()
MANUAL = [
    '原文事件、潜台词与观众知情顺序：对照原文及导演决定逐镜审阅。',
    '三维碰撞、摄影投影、遮挡、视线和手部接触：检查预演或真实画格。',
    '表情幅度、重心、动作惯性、接动作剪点：查看连续媒体，不能只看首尾帧。',
    '身份、服化道、场景拓扑、光源和道具：逐镜核对实际参考及资产版本。',
    '台词声音归属、口型、停顿、旁白与音乐混音：实听实看并标时间码。',
    '执行入口、模型版本、模式、附件、时长和返回素材：由宿主核验并另存真实回执。',
]


def _detail_support(version=None):
    import importlib.util
    path = Path(__file__).with_name('v52_support.py' if version and version.endswith('1.2') else 'v51_support.py')
    spec = importlib.util.spec_from_file_location('v51_support_' + str(path), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite JSON: ' + x)))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def digest(value):
    return sha256(encoded(value)).hexdigest()


def equal(a, b):
    return encoded(a) == encoded(b)


def pointer(value, path):
    if path == '':
        return value
    if not path.startswith('/') or re.search(r'~(?![01])', path):
        raise KeyError(path)
    for token in path[1:].split('/'):
        token = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token):
                raise KeyError(path)
            value = value[int(token)]
        elif isinstance(value, dict):
            value = value[token]
        else:
            raise KeyError(path)
    return value


def walk(value, path=''):
    if isinstance(value, dict):
        yield path, value
        for k, v in value.items():
            yield from walk(v, path + '/' + k.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk(v, path + '/' + str(i))


def local_path(base, uri):
    parsed = urlparse(uri)
    if parsed.scheme == 'file':
        if parsed.netloc not in ('', 'localhost'):
            return None
        return Path(unquote(parsed.path))
    if parsed.scheme:
        return None
    p = Path(uri)
    return p if p.is_absolute() else Path(base) / p


def schema_errors(value, name):
    schema = read(ROOT / 'schemas' / (name + '.schema.json'))
    return [{'code': 'E_SCHEMA', 'path': '/' + '/'.join(map(str, e.absolute_path)),
             'message': e.message, 'severity': 'error'}
            for e in sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: str(e.absolute_path))]


def assertion(ir, check):
    try:
        actual = pointer(ir, check['path'])
    except (KeyError, IndexError, TypeError):
        return False
    if check['op'] == 'exists':
        return actual is not None
    if check['op'] == 'equals':
        return equal(actual, check['value'])
    if isinstance(actual, list):
        return any(equal(x, check['value']) for x in actual)
    return isinstance(actual, str) and isinstance(check['value'], str) and check['value'] in actual


def style_index():
    return read(ROOT / 'registries/style-index.json')['styles']


def route(query, forbidden=()):
    q = query.casefold()
    rows = []
    for s in style_index():
        matched = [t for t in s['tags'] if t.casefold() in q]
        rows.append({'id': s['id'], 'name': s['name'], 'score': len(matched),
                     'matched_tags': matched, 'eligible': s['id'] not in forbidden})
    rows.sort(key=lambda x: (-x['score'], x['id']))
    eligible = [x for x in rows if x['eligible'] and x['score']]
    return {'method': 'tag_match_suggestion', 'quality_prediction': False,
            'suggested': eligible[0]['id'] if eligible else ('transparent' if 'transparent' not in forbidden else None),
            'candidates': rows, 'decision': 'Agent按导演目的、媒介与画幅选主语法；不自动改写IR。'}


def validate(ir, base):
    if ir.get('schema_version') in ('storyboard-ir/1.1','storyboard-ir/1.2'):
        errors = _detail_support(ir.get('schema_version')).validate_native(ir, ROOT, 'storyboard-ir', base)
        invalid = any(e['severity'] == 'error' for e in errors)
        return dict(schema_version='storyboard-qa/1.0', status='INVALID' if invalid else 'BLOCKED' if any(e['severity']=='blocker' for e in errors) else 'VALID', structure='FAIL' if invalid else 'PASS', diagnostics=errors, media='NOT_RUN', visual='NOT_RUN', execution_ready=False, submitted=False, contract_results=[], manual_checks=MANUAL)
    diagnostics = schema_errors(ir, 'storyboard-ir')
    results = []

    def add(code, path, message, severity='error'):
        diagnostics.append(dict(code=code, path=path, message=message, severity=severity))

    def report():
        structural = any(x['severity'] == 'error' for x in diagnostics)
        blocked = any(x['severity'] == 'blocker' for x in diagnostics)
        return dict(schema_version='storyboard-qa/1.0',
                    status='INVALID' if structural else 'BLOCKED' if blocked else 'VALID',
                    structure='FAIL' if structural else 'PASS', media='NOT_RUN', visual='NOT_RUN',
                    execution_ready=False, submitted=False, diagnostics=diagnostics,
                    contract_results=results, manual_checks=MANUAL)

    if diagnostics:
        return report()
    keys = ('sources', 'upstreams', 'entities', 'scenes', 'assets', 'bindings', 'beats', 'shots', 'contract')
    maps = {k: {x['id']: x for x in ir[k]} for k in keys}
    for k in keys:
        if len(maps[k]) != len(ir[k]):
            add('E_DUPLICATE_ID', '/' + k, '集合内ID重复。')
    sources, entities, scenes, assets, beats, shots = [maps[k] for k in ('sources','entities','scenes','assets','beats','shots')]
    for path, item in walk(ir):
        for ref in item.get('source_refs', []):
            if ref not in sources:
                add('E_SOURCE_REF', path, '未定义来源：' + ref)
    for ref in ir['scope']['source_ids']:
        if ref not in sources:
            add('E_SCOPE_SOURCE', '/scope', '范围来源不存在：' + ref)
    if ir['scope']['shot_ids'] and ir['scope']['shot_ids'] != [x['id'] for x in ir['shots']]:
        add('E_SCOPE_SHOTS', '/scope/shot_ids', '未严格匹配指定镜头范围与顺序。')
    source_lines = {}
    for i, s in enumerate(ir['sources']):
        p = '/sources/' + str(i)
        if sha256(s['excerpt'].encode()).hexdigest() != s['excerpt_sha256']:
            add('E_EXCERPT_HASH', p, '摘录UTF-8哈希不一致。')
        file = local_path(base, s['uri'])
        if s['file_sha256']:
            if file is None:
                add('E_SOURCE_LOCATION', p, '离线文件哈希校验需要本地路径。')
            elif not file.is_file() or sha256(file.read_bytes()).hexdigest() != s['file_sha256']:
                add('E_SOURCE_HASH', p, '来源文件缺失或版本变化。')
            elif s['excerpt'] not in file.read_text(encoding='utf-8'):
                add('E_EXCERPT_CONTENT', p, '摘录不在所绑定的源文件内。')
        for u in s['utterances']:
            a, b = u['span']['start'], u['span']['end']
            if not (0 <= a < b <= len(s['excerpt'])) or s['excerpt'][a:b] != u['text']:
                add('E_SOURCE_SPAN', p, '台词摘录字符区间不匹配。')
            if u['id'] in source_lines:
                add('E_DUPLICATE_UTTERANCE', p, '原文台词ID必须全局唯一。')
            source_lines[u['id']] = (s['id'], u)

    for i, u in enumerate(ir['upstreams']):
        p = '/upstreams/' + str(i)
        file = local_path(base, u['uri'])
        if file is None or not file.is_file():
            add('E_UPSTREAM_FILE', p, '所声明的上游绑定必须可读。')
            continue
        if sha256(file.read_bytes()).hexdigest() != u['sha256']:
            add('E_UPSTREAM_HASH', p, '上游版本变化；更新映射后重编译。')
            continue
        upstream = read(file)
        if not isinstance(upstream, dict):
            add('E_UPSTREAM_SCHEMA', p, '上游应为JSON对象。')
            continue
        if upstream.get('schema_version') != u['schema_version'] or str(upstream.get('revision')) != u['revision']:
            add('E_UPSTREAM_VERSION', p, '上游Schema或revision不一致。')
        if upstream.get('project_id') != u['project_id'] or u['project_id'] != ir['project_id']:
            add('E_UPSTREAM_PROJECT', p, '上游项目ID不一致。')
        if u['kind'] in ('director', 'art') and u['schema_version'] != '1.0':
            add('E_UPSTREAM_UNSUPPORTED', p, '本版仅验证director/art v1.0字段绑定，需显式协商新版本。')
        for lock in u['locks']:
            try:
                okay = equal(pointer(upstream, lock['source_pointer']), lock['source_value']) and equal(pointer(ir, lock['target_pointer']), lock['target_value'])
                if lock['mode'] == 'equal':
                    okay = okay and equal(lock['source_value'], lock['target_value'])
            except (KeyError, IndexError, TypeError):
                okay = False
            if not okay:
                add('E_UPSTREAM_LOCK', p, '锁定字段或显式映射变化：' + lock['target_pointer'])

    styles = {s['id']: s for s in style_index()}
    selected = [ir['style']['primary']] + ir['style']['modifiers']
    if len(set(selected)) != len(selected):
        add('E_STYLE_DUPLICATE', '/style', '主语法与修饰语法重复。')
    for sid in selected:
        if sid not in styles:
            add('E_STYLE_UNKNOWN', '/style', '未知语法：' + sid)
        elif sid in ir['style']['forbidden']:
            add('E_STYLE_FORBIDDEN', '/style', '选择了禁止语法：' + sid)
        elif set(styles[sid]['conflicts']) & set(selected):
            add('E_STYLE_CONFLICT', '/style', '选择的全局语法冲突；先拆局部场景。')
    for i, scene in enumerate(ir['scenes']):
        p = '/scenes/' + str(i)
        if scene['location_id'] not in entities or entities.get(scene['location_id'], {}).get('kind') != 'environment':
            add('E_LOCATION', p, '场景需绑定已定义环境实体。')
        if len(set(scene['entity_ids'])) != len(scene['entity_ids']) or any(x not in entities for x in scene['entity_ids']):
            add('E_SCENE_ENTITY', p, '场景实体重复或不存在。')
        if any(a >= b for a,b in zip(scene['bounds']['min_m'], scene['bounds']['max_m'])):
            add('E_BOUNDS', p, '场景包围盒必须有正体积。')
        a,b = scene['axis']['start_m'], scene['axis']['end_m']
        if math.hypot(a[0]-b[0], a[2]-b[2]) < 1e-8:
            add('E_AXIS_DEGENERATE', p, '水平行动轴两端不能重合。')
    for i, asset in enumerate(ir['assets']):
        p = '/assets/' + str(i)
        if asset['entity_id'] not in entities:
            add('E_ASSET_ENTITY', p, '资产实体不存在。')
        if Path(asset['filename']).name != asset['filename']:
            add('E_ASSET_FILENAME', p, 'filename只保存真实文件名及扩展名。')
        if asset['status'] != 'metadata_only':
            file = local_path(base, asset['path']) if asset['path'] else None
            if file is None or not file.is_file() or file.name != asset['filename']:
                add('E_ASSET_FILE', p, '可用资产必须对应真实本地文件与文件名。')
            elif not asset['sha256'] or sha256(file.read_bytes()).hexdigest() != asset['sha256']:
                add('E_ASSET_HASH', p, '资产哈希缺失或变化。')
    bound = {}
    for i, binding in enumerate(ir['bindings']):
        p = '/bindings/' + str(i)
        asset = assets.get(binding['asset_id'])
        if not asset or binding['entity_id'] != asset['entity_id']:
            add('E_BINDING', p, '参考与实体不匹配。')
            continue
        if binding['required'] and asset['status'] == 'metadata_only':
            add('B_REFERENCE_MISSING', p, '硬参考尚无实际素材：' + asset['filename'], 'blocker')
        if set(binding['roles']) & set(binding['exclude']):
            add('E_BINDING_ROLE', p, '同一参考维度同时继承与排除。')
        for sid in binding['shot_ids']:
            if sid not in shots:
                add('E_BINDING_SHOT', p, '参考镜头不存在。')
            for role in binding['roles']:
                key = (sid, binding['entity_id'], role)
                fingerprint = (asset['id'], asset['revision'], asset['sha256'])
                if key in bound and bound[key] != fingerprint:
                    add('E_ASSET_CONFLICT', p, '同镜同实体同用途绑定冲突版本。')
                bound[key] = fingerprint

    for i, beat in enumerate(ir['beats']):
        if beat['scene_id'] not in scenes:
            add('E_BEAT_SCENE', '/beats/' + str(i), '节拍场景不存在。')
        if not beat['required'] and not beat['exclusion_reason']:
            add('E_BEAT_EXCLUSION', '/beats/' + str(i), '排除节拍需记录原因。')
        if any(d not in beats or d == beat['id'] for d in beat['depends_on']):
            add('E_BEAT_DEPENDENCY', '/beats/' + str(i), '无效节拍前置引用。')
    seen_beats, events, panel_ids, performance_ids = set(), {}, set(), set()
    cursor, previous = 0, None
    ir_schema = read(ROOT / 'schemas/storyboard-ir.schema.json')
    state_validator = Draft202012Validator({'$ref': '#/$defs/states', '$defs': ir_schema['$defs']})

    def check_state(states, scene, path):
        if not state_validator.is_valid(states):
            add('E_STATE_TYPE', path, '事件后的状态字段类型非法。')
            return
        if set(states) != {x for x in scene['entity_ids'] if entities.get(x,{}).get('kind') != 'voice'}:
            add('E_STATE_SET', path, '起止状态需覆盖场景全部物理实体，画外实体也保留。')
        for eid, state in states.items():
            if eid not in entities:
                add('E_ENTITY', path, '状态实体不存在：' + eid)
            if state['gaze_target'] and state['gaze_target'] not in scene['entity_ids']:
                add('E_GAZE', path, '视线对象不在当前场景；画外对象也需登记。')
            if any(v < lo or v > hi for v,lo,hi in zip(state['position_m'],scene['bounds']['min_m'],scene['bounds']['max_m'])):
                add('E_POSITION_BOUNDS', path, '实体位置超出所声明场景。')
            tokens = state['contacts'] + ([state['holder']] if state['holder'] else [])
            for token in tokens:
                if '.' not in token or token.split('.',1)[0] not in scene['entity_ids']:
                    add('E_CONTACT', path, '接触或持物标记应为场景实体ID.部位。')
            if state['holder']:
                holder = state['holder'].split('.',1)[0]
                if entities.get(eid,{}).get('kind') != 'prop' or entities.get(holder,{}).get('kind') not in ('person','animal') or holder == eid:
                    add('E_HOLDER', path, '只有道具可由当前人物或动物持有。')
                if state['holder'] not in state['contacts']:
                    add('E_HOLDER_CONTACT', path, '持有部位必须与道具接触。')

    for i, shot in enumerate(ir['shots']):
        p = '/shots/' + str(i)
        start, end = shot['start_frame'], shot['end_frame']
        if start != cursor or end <= start:
            add('E_TIMELINE', p, '镜头需从0连续覆盖全片，使用左闭右开整数帧。')
        cursor = end
        scene = scenes.get(shot['scene_id'])
        if not scene:
            add('E_SHOT_SCENE', p, '镜头场景不存在。')
            continue
        for bid in shot['beat_ids']:
            beat = beats.get(bid)
            if not beat or beat['scene_id'] != shot['scene_id']:
                add('E_BEAT_REF', p, '节拍不存在或属于其他场景。')
            elif any(d not in seen_beats for d in beat['depends_on']):
                add('E_BEAT_ORDER', p, '前置节拍必须先被表达；同镜按beat_ids排序。')
            seen_beats.add(bid)
        check_state(shot['state_start'], scene, p + '/state_start')
        check_state(shot['state_end'], scene, p + '/state_end')
        subjects = {s['entity_id']: s for s in shot['composition']['subjects']}
        if len(subjects) != len(shot['composition']['subjects']):
            add('E_SUBJECT_DUPLICATE', p, '同一主体的构图声明重复。')
        for eid, sub in subjects.items():
            x,y,w,h = sub['box']
            if eid not in scene['entity_ids'] or w <= 0 or h <= 0 or x+w > 1.000001 or y+h > 1.000001:
                add('E_COMPOSITION', p, '主体引用或归一化画框无效。')
        if any(x not in subjects for x in shot['composition']['attention_order']):
            add('E_ATTENTION', p, '注意力顺序需指向画内主体。')
        cam = shot['camera']
        a,b = scene['axis']['start_m'], scene['axis']['end_m']
        def side(c):
            cross = (b[0]-a[0])*(c[2]-a[2]) - (b[2]-a[2])*(c[0]-a[0])
            return 'on_axis' if abs(cross) < 1e-8 else 'positive' if cross > 0 else 'negative'
        if cam['axis_side'] != side(cam['start_m']):
            add('E_AXIS_SIDE', p, '声明轴侧与世界坐标不一致。')
        crosses = side(cam['start_m']) != side(cam['end_m'])
        if crosses and (cam['axis_strategy'] != 'visible_cross' or not cam['axis_reason']):
            add('E_AXIS_CROSS', p, '镜内过轴需可见路径与动机。')
        if equal(cam['start_m'], cam['look_at_m']):
            add('E_CAMERA_LOOK', p, '观察点不能与机位重合。')
        if cam['precision'] != 'intent':
            add('B_GEOMETRY_EXECUTION', p, '需要绑定实际参考或受控预演后再执行硬几何。', 'blocker')
        if previous and previous['scene_id'] == shot['scene_id']:
            exceptions = {(e['entity_id'],e['field']) for e in shot['transition']['state_exceptions']}
            if exceptions and shot['transition']['type'] not in ('time_jump','subjective'):
                add('E_STATE_EXCEPTION', p, '连续时间不能通过例外跳过动作。')
            for eid, state in shot['state_start'].items():
                old = previous['state_end'].get(eid)
                if old:
                    for k,v in state.items():
                        if not equal(old[k],v) and (eid,k) not in exceptions:
                            add('E_CONTINUITY', p + '/state_start/' + eid + '/' + k, '相邻镜头状态变化缺少动作或明确时空跳转依据。')
            oldside = side(previous['camera']['end_m'])
            newside = side(cam['start_m'])
            if oldside != newside and oldside != 'on_axis' and newside != 'on_axis':
                if cam['axis_strategy'] not in ('reestablish','intentional_disorientation') or not cam['axis_reason']:
                    add('E_AXIS_CUT', p, '切镜过轴需重新建立空间或明确失向表达。')
        elif previous and shot['transition']['type'] not in ('scene_change','subjective','time_jump'):
            add('E_SCENE_TRANSITION', p, '换场需显式时空转场。')

        state = deepcopy(shot['state_start'])
        writes, last_event_end = {}, start
        for ev in shot['events']:
            ep = p + '/events/' + ev['id']
            if ev['id'] in events:
                add('E_EVENT_DUPLICATE', ep, '动作事件ID重复。')
            events[ev['id']] = (shot['id'], ev)
            for dependency in ev['depends_on']:
                prior = events.get(dependency)
                if not prior or dependency == ev['id'] or prior[1]['end_frame'] > ev['start_frame']:
                    add('E_EVENT_DEPENDENCY', ep, '前置事件必须先完成：' + dependency)
            if not start <= ev['start_frame'] < ev['end_frame'] <= end or ev['end_frame'] < last_event_end:
                add('E_EVENT_TIME', ep, '动作需落在镜内并按完成时间排序。')
            last_event_end = ev['end_frame']
            if ev['actor_id'] not in state or (ev['target_id'] and ev['target_id'] not in state):
                add('E_EVENT_ENTITY', ep, '动作主体或目标不在当前世界状态。')
            target = state.get(ev['target_id'])
            hand = ev['actor_id'] + '.' + (ev['effector'] or '')
            if ev['kind'] in ('contact','release','grasp') and (target is None or not ev['effector']):
                add('E_INTERACTION', ep, '接触动作需要目标和身体部位。')
            if target and ev['kind'] == 'grasp' and (hand not in target['contacts'] or target['holder'] is not None):
                add('E_GRASP_PRECONDITION', ep, '拿取前必须接触且原持有人已松手。')
            if target and ev['kind'] == 'release' and target['holder'] != hand:
                add('E_RELEASE_PRECONDITION', ep, '松手人必须是原持有部位。')
            for change in ev['changes']:
                eid, field = change['entity_id'], change['field']
                key = (eid, field)
                if eid not in state or not equal(state[eid][field], change['before']):
                    add('E_EVENT_PRECONDITION', ep, '动作前置状态不成立：' + eid + '.' + field)
                    continue
                if key in writes and writes[key] > ev['start_frame']:
                    add('E_EVENT_OVERLAP', ep, '同一状态字段的动作重叠。')
                writes[key] = ev['end_frame']
                if field == 'holder' and not equal(change['before'], change['after']):
                    valid_release = ev['kind'] == 'release' and eid == ev['target_id'] and change['before'] == hand and change['after'] is None
                    valid_grasp = ev['kind'] == 'grasp' and eid == ev['target_id'] and change['before'] is None and change['after'] == hand
                    if not (valid_release or valid_grasp):
                        add('E_CUSTODY_EVENT', ep, '持物变化必须由原人松手和接触后拿取分别表达。')
                state[eid][field] = deepcopy(change['after'])
            check_state(state, scene, ep)
            after = state.get(ev['target_id'])
            if after and ev['kind'] == 'contact' and hand not in after['contacts']:
                add('E_CONTACT_RESULT', ep, '接触事件未形成所声明部位的接触。')
            if after and ev['kind'] == 'release' and (after['holder'] is not None or hand in after['contacts']):
                add('E_RELEASE_RESULT', ep, '松手后仍声明持有或接触。')
            if after and ev['kind'] == 'release' and after['support'] == hand:
                add('E_RELEASE_SUPPORT', ep, '松手后不能仍把该手记作支撑。')
            if after and ev['kind'] == 'grasp' and after['holder'] != hand:
                add('E_GRASP_RESULT', ep, '拿取结果未交给声明的部位。')
        if not equal(state, shot['state_end']):
            add('E_EVENT_REPLAY', p + '/state_end', '逐事件回放结果与镜尾状态不符。')
        for perf in shot['performance']:
            if perf['id'] in performance_ids:
                add('E_PERFORMANCE_DUPLICATE', p, '表演ID重复。')
            performance_ids.add(perf['id'])
            if not start <= perf['start_frame'] < perf['end_frame'] <= end:
                add('E_PERFORMANCE_TIME', p, '表演时段越界。')
            subject = subjects.get(perf['actor_id'])
            if not subject or not set(perf['needed_parts']) <= set(subject['visible_parts']):
                add('E_PERFORMANCE_VISIBILITY', p, '表演依赖部位未在构图中可见。')
            if perf['micro_expression'] and (cam['size'] not in ('close','extreme_close') or not subject or not {'face','eyes'} <= set(subject['visible_parts'])):
                add('E_MICRO_SCALE', p, '微表情需要可读面部近景；远景改用姿态或拆镜。')
            psych = perf['psychology']
            if psych:
                u = next((x for x in ir['audio']['utterances'] if x['id'] == psych['utterance_id']), None)
                if psych['audibility'] == 'silent' and psych['utterance_id'] is not None:
                    add('E_SILENT_PSYCHOLOGY', p, '静默心理不能绑定发声台词。')
                if psych['audibility'] == 'internal_voice' and (not u or u['kind'] != 'internal_voice' or u['speaker_id'] != perf['actor_id'] or u['shot_id'] != shot['id']):
                    add('E_INNER_VOICE', p, '内心独白需同人物同镜头的有来源声音条目。')
        last_panel = start-1
        for panel in shot['panels']:
            if panel['id'] in panel_ids:
                add('E_PANEL_DUPLICATE', p, '画格ID重复。')
            panel_ids.add(panel['id'])
            if not start <= panel['frame'] < end or panel['frame'] <= last_panel:
                add('E_PANEL_TIME', p, '画格需按可见帧递增，不能落在镜尾排除边界。')
            last_panel = panel['frame']
            if any(x not in subjects for x in panel['subject_ids']):
                add('E_PANEL_SUBJECT', p, '画格主体不在构图内。')
            for ref in panel['event_ids']:
                if ref not in events or events[ref][0] != shot['id'] or panel['frame'] < events[ref][1]['start_frame']:
                    add('E_PANEL_EVENT', p, '画格引用错误或尚未发生的动作。')
        for rel in shot['relations']:
            for key in ('state_start','state_end') if rel['at'] == 'both' else ('state_start',) if rel['at'] == 'start' else ('state_end',):
                astate, bstate = shot[key].get(rel['subject']), shot[key].get(rel['object'])
                if not astate or not bstate:
                    add('E_RELATION_ENTITY', p, '相对关系实体缺失。')
                    continue
                a, b = astate['position_m'], bstate['position_m']
                r = rel['relation']
                okay = {'world_left_of': a[0]<b[0], 'world_right_of': a[0]>b[0], 'above': a[1]>b[1], 'below': a[1]<b[1]}.get(r, True)
                if r == 'near':
                    okay = rel['max_distance_m'] is not None and math.dist(a,b) <= rel['max_distance_m']
                if r in ('screen_left_of','screen_right_of'):
                    sa,sb = subjects.get(rel['subject']),subjects.get(rel['object'])
                    okay = bool(sa and sb and ((sa['box'][0]+sa['box'][2]/2 < sb['box'][0]+sb['box'][2]/2) if r == 'screen_left_of' else (sa['box'][0]+sa['box'][2]/2 > sb['box'][0]+sb['box'][2]/2)))
                if not okay:
                    add('E_RELATION', p, '相对位置断言失败：' + r)
        previous = shot
    if cursor != ir['delivery']['total_frames']:
        add('E_DURATION', '/delivery', '镜头总帧数与交付时长不一致。')
    for beat in ir['beats']:
        if beat['required'] and beat['id'] not in seen_beats:
            add('E_BEAT_COVERAGE', '/beats', '必需节拍未覆盖：' + beat['id'])
    spoken_ids, audio_ids = [], set()
    for u in ir['audio']['utterances']:
        p = '/audio/utterances/' + u['id']
        if u['id'] in audio_ids:
            add('E_AUDIO_DUPLICATE', p, '声音ID重复。')
        audio_ids.add(u['id'])
        source = source_lines.get(u['source_utterance_id'])
        if u['source_id'] not in ir['scope']['source_ids']:
            add('E_DIALOGUE_SCOPE', p, '输出台词超出指定来源范围。')
        if not source or source[0] != u['source_id'] or any(u[k] != source[1][k] for k in ('speaker_id','text','kind')):
            add('E_DIALOGUE_FIDELITY', p, '台词、说话人、声道类型与原文登记不符。')
        spoken_ids.append(u['source_utterance_id'])
        shot = shots.get(u['shot_id'])
        if not shot or not shot['start_frame'] <= u['start_frame'] < u['end_frame'] <= shot['end_frame']:
            add('E_AUDIO_TIME', p, '台词时段需落在所属镜头；跨镜声桥用cue或显式宿主映射。')
        if u['speaker_id'] not in entities or entities[u['speaker_id']]['kind'] not in ('person','animal','voice'):
            add('E_SPEAKER', p, '说话者不存在或不是发声实体。')
        if u['kind'] != 'dialogue' and (u['lip_sync'] or u['placement'] != 'voice_over'):
            add('E_VOICE_ROLE', p, '旁白和内心独白不能要求画内口型。')
        if u['placement'] == 'off_screen' and u['lip_sync']:
            add('E_OFFSCREEN_LIPS', p, '画外对白不要求当前画面口型。')
        if shot and u['placement'] == 'on_screen':
            sub = next((x for x in shot['composition']['subjects'] if x['entity_id'] == u['speaker_id']), None)
            if not sub or (u['lip_sync'] and 'mouth' not in sub['visible_parts']):
                add('E_DIALOGUE_VISIBILITY', p, '画内说话主体或口型部位不可见。')
        duration = (u['end_frame']-u['start_frame'])/ir['delivery']['fps']
        if duration > 0 and len(u['text'])/duration > 7:
            add('W_SPEECH_LOAD', p, '台词负荷偏高；这是粗略排期提示，需朗读或音频实测。', 'warning')
    for i,a in enumerate(ir['audio']['utterances']):
        for b in ir['audio']['utterances'][i+1:]:
            if max(a['start_frame'],b['start_frame']) < min(a['end_frame'],b['end_frame']) and not (a['overlap_reason'] or b['overlap_reason']):
                add('E_DIALOGUE_OVERLAP', '/audio', '重叠台词需明确抢话、声桥或复调依据。')
    excluded = [x['id'] for x in ir['scope']['excluded_utterance_ids']]
    for uid in excluded:
        if uid not in source_lines or uid in spoken_ids:
            add('E_UTTERANCE_EXCLUSION', '/scope', '排除台词不存在或仍被输出。')
    for uid,(sid,_) in source_lines.items():
        if sid in ir['scope']['source_ids'] and uid not in excluded and spoken_ids.count(uid) != 1:
            add('E_DIALOGUE_COVERAGE', '/audio', '范围内台词必须恰好表达一次：' + uid)
    for cue in ir['audio']['cues']:
        p = '/audio/cues/' + cue['id']
        if cue['id'] in audio_ids:
            add('E_AUDIO_DUPLICATE', p, '声音ID重复。')
        audio_ids.add(cue['id'])
        if not 0 <= cue['start_frame'] < cue['end_frame'] <= ir['delivery']['total_frames']:
            add('E_CUE_TIME', p, '声音提示时段越界。')
        covered = [s['id'] for s in ir['shots'] if max(s['start_frame'],cue['start_frame']) < min(s['end_frame'],cue['end_frame'])]
        if cue['shot_ids'] != covered:
            add('E_CUE_SHOTS', p, '声音跨镜范围与时段不一致。')
        if cue['sync_event']:
            event = events.get(cue['sync_event'])
            if not event or cue['sync_frame'] != event[1]['end_frame'] or not cue['start_frame'] <= cue['sync_frame'] < cue['end_frame']:
                add('E_AUDIO_SYNC', p, '动作声音需绑定事件完成帧且在声音时段内。')
        elif cue['sync_frame'] is not None:
            add('E_AUDIO_SYNC', p, '有同步帧却没有同步事件。')
    for c in ir['contract']:
        passed = all(assertion(ir, check) for check in c['checks'])
        if not passed:
            add('E_CONTRACT' if c['strength']=='hard' else 'W_CONTRACT', '/contract/' + c['id'], '合同字段断言未满足。', 'error' if c['strength']=='hard' else 'warning')
        if any(s not in shots for s in c['shot_ids']):
            add('E_CONTRACT_SHOT', '/contract/' + c['id'], '合同镜头引用不存在。')
        if c['strength'] == 'hard' and c['fallback'] == 'warn':
            add('E_HARD_FALLBACK', '/contract/' + c['id'], '硬约束不能自动降级为警告。')
        if any(sources.get(s,{}).get('verification') == 'unverified' for s in c['source_refs']) and c['strength']=='hard':
            add('E_HARD_SOURCE', '/contract/' + c['id'], '硬要求的依据仍未核验。')
        if c['channel'] == 'reference' and not any(b['required'] and (not c['shot_ids'] or set(b['shot_ids']) & set(c['shot_ids'])) for b in ir['bindings']):
            add('B_CONTRACT_REFERENCE', '/contract/' + c['id'], '参考渠道合同尚无必需参考绑定。', 'blocker')
        results.append({'id':c['id'], 'structure':'PASS' if passed else 'FAIL', 'acceptance':[
            {'phase':a['phase'],'status':('PASS' if passed else 'FAIL') if a['phase']=='structure' else 'NOT_RUN',
             'criterion':a['criterion'],'evidence':a['evidence']} for a in c['acceptance']]})
    return report()


def review_markdown(ir):
    names = {e['id']:e['name'] for e in ir['entities']}
    lines = [f"# {ir['project_id']} · 分镜制作说明", ir['intent'],
             f"revision {ir['revision']}；{ir['delivery']['total_frames']}帧 / {ir['delivery']['fps']}fps；{ir['delivery']['aspect_ratio']}。这是静态制作计划。",
             f"风格：{ir['style']['medium']} × {ir['style']['primary']}；{ir['style']['rationale']}"]
    for shot in ir['shots']:
        cam, comp = shot['camera'], shot['composition']
        scene = next(s for s in ir['scenes'] if s['id']==shot['scene_id'])
        lines += [f"\n## {shot['id']} · [{shot['start_frame']}, {shot['end_frame']})帧",
                  f"目的：{shot['purpose']}；视点：{shot['viewpoint']}。观众信息：{shot['audience_before']} → {shot['audience_after']}。",
                  f"场景：{scene['description']}；时间：{scene['time_of_day']}；世界光源：{scene['lighting']['world_source']}。",
                  f"构图：{comp['rule']}；纵深：{comp['depth_layers']}；负空间：{comp['negative_space']}；安全区：{comp['safe_area']}。",
                  f"镜头：{cam['size']}；机位{cam['start_m']} → {cam['end_m']}；看向{cam['look_at_m']}；俯仰{cam['pitch_deg']}° / 滚转{cam['roll_deg']}°；{cam['lens_intent']}。",
                  f"运镜：{cam['movement']}，动机：{cam['motivation']}，路径：{cam['path']}，焦点：{cam['focus']}。坐标与镜头数值为{cam['precision']}，未宣称原生参数。"]
        for sub in comp['subjects']:
            lines.append(f"主体：{names[sub['entity_id']]}，画面{sub['screen_side']} / {sub['depth']}，框{sub['box']}，可见{', '.join(sub['visible_parts'])}；{sub['occlusion']}。")
        for rel in shot['relations']:
            lines.append(f"相对关系：{rel['subject']} {rel['relation']} {rel['object']}；{rel['criterion']}。")
        for eid,s in shot['state_start'].items():
            lines.append(f"起态 {names[eid]}：坐标{s['position_m']}，身体朝向{s['yaw_deg']}°，头部{s['head_yaw_deg']}°/{s['head_pitch_deg']}°，视线{s['gaze_target']}；{s['pose']}；支撑{s['support']}；接触{s['contacts']}；持有人{s['holder']}；状态{s['condition']}。")
        for ev in shot['events']:
            lines.append(f"动作 {ev['id']} [{ev['start_frame']},{ev['end_frame']})：前置{ev['depends_on']}；触发{ev['trigger']} → {ev['action']} → 反馈{ev['feedback']}；状态变化：" + json.dumps(ev['changes'],ensure_ascii=False))
        for perf in shot['performance']:
            details = '；'.join(f'{label}：{perf[key]}' for key,label in [('face','面部'),('eyes','眼神'),('micro_expression','微表情'),('hands','手部'),('body','身体'),('voice','声音')] if perf[key])
            lines.append(f"表演 {names[perf['actor_id']]} [{perf['start_frame']},{perf['end_frame']})：{perf['trigger']} → {details}；动作{perf['action']}；对手反馈{perf['feedback']}；收束{perf['settle']}。")
            if perf['psychology']:
                psy = perf['psychology']
                lines.append(f"心理指导（{psy['audibility']}）：{psy['intent']} → 可见化：{psy['visible_translation']}。")
        for u in ir['audio']['utterances']:
            if u['shot_id']==shot['id']:
                lines.append(f"{u['kind']} / {u['placement']} [{u['start_frame']},{u['end_frame']})：{names[u['speaker_id']]}：“{u['text']}” {u['delivery']}；口型{u['lip_sync']}；执行{u['route']}。")
        for cue in ir['audio']['cues']:
            if shot['id'] in cue['shot_ids']:
                lines.append(f"声音 {cue['kind']} [{cue['start_frame']},{cue['end_frame']})：{cue['description']}；同步{cue['sync_event']}@{cue['sync_frame']}；混音{cue['mix']}；执行{cue['route']}。")
        for panel in shot['panels']:
            lines.append(f"画格 {panel['id']} @{panel['frame']}：{panel['moment']}；必须可见：{'；'.join(panel['must_show'])}。")
        for eid,s in shot['state_end'].items():
            lines.append(f"终态 {names[eid]}：{json.dumps(s,ensure_ascii=False)}")
        for binding in ir['bindings']:
            if shot['id'] in binding['shot_ids']:
                asset = next(a for a in ir['assets'] if a['id']==binding['asset_id'])
                lines.append(f"参考：{asset['filename']} / {asset['id']} / revision {asset['revision']} / {asset['status']}；用途{binding['roles']}；禁止继承{binding['exclude']}；附件槽位由后端确定。")
        lines.append(f"剪接：{shot['transition']['type']}；{shot['transition']['reason']}；匹配点：{shot['transition']['match']}；来源：{shot['source_refs']}。")
    return '\n\n'.join(lines)+'\n'


def panel_state(shot, frame):
    """Evaluate completed events only; interpolation inside actions is not claimed."""
    state = deepcopy(shot['state_start'])
    for event in shot['events']:
        if event['end_frame'] <= frame:
            for change in event['changes']:
                state[change['entity_id']][change['field']] = deepcopy(change['after'])
    return {'completed_state': state,
            'active_event_ids': [e['id'] for e in shot['events'] if e['start_frame'] <= frame < e['end_frame']],
            'interpolated': False}


def compile_package(ir, base, out):
    if ir.get('schema_version') in ('storyboard-ir/1.1','storyboard-ir/1.2'):
        from types import SimpleNamespace
        return _detail_support(ir.get('schema_version')).storyboard_package(SimpleNamespace(**globals()), ir, base, out)
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('输出目录非空，请使用新的修订目录。')
    qa = validate(ir, base)
    out.mkdir(parents=True,exist_ok=True)
    def emit(name,value):
        (out/name).write_bytes(encoded(value))
    emit('qa.report.json',qa)
    if qa['status'] == 'INVALID':
        return qa
    input_hash = digest(ir)
    emit('storyboard.ir.json',ir)
    (out/'storyboard.md').write_text(review_markdown(ir),encoding='utf-8')
    emit('production-contract.json',dict(schema_version='storyboard-contract/1.0',project_id=ir['project_id'],input_hash=input_hash,requirements=ir['contract']))
    contract_text = [f"# {ir['project_id']} · 制作合同", '制作规格与验收约定；实际媒体、声音和人工验收尚未执行。']
    for c in ir['contract']:
        contract_text += [f"\n## {c['id']} · {c['strength']} · {c['owner']}",c['statement'],
                         f"来源：{c['source_refs']}；镜头：{c['shot_ids']}；字段断言：{json.dumps(c['checks'],ensure_ascii=False)}",
                         f"执行：{c['channel']} → {c['execution']}；不支持时：{c['fallback']}"]
        contract_text += [f"验收 {a['phase']}：{a['criterion']}；所需证据：{a['evidence']}" for a in c['acceptance']]
    (out/'production-contract.md').write_text('\n\n'.join(contract_text)+'\n',encoding='utf-8')
    selected = [ir['style']['primary']]+ir['style']['modifiers']
    cards = [read(ROOT / next(s['file'] for s in style_index() if s['id']==sid)) for sid in selected]
    emit('style-decision.json',dict(selection=ir['style'],cards=cards,quality_prediction=False))
    emit('panel-briefs.json',{'status':'PLANNED','generated':False,'panels':[
        dict(**p,shot_id=s['id'],scene_id=s['scene_id'],camera=s['camera'],composition=s['composition'],state_evaluation=panel_state(s,p['frame']),
             references=[b for b in ir['bindings'] if s['id'] in b['shot_ids']]) for s in ir['shots'] for p in s['panels']]})
    emit('animatic.plan.json',{'status':'PLAN_ONLY','fps':ir['delivery']['fps'],'total_frames':ir['delivery']['total_frames'],
                             'shots':[{'id':s['id'],'start_frame':s['start_frame'],'end_frame':s['end_frame'],'panels':s['panels'],'transition':s['transition']} for s in ir['shots']],
                             'audio':ir['audio'],'takes':[],'edit_segments':[]})
    handoff = dict(schema_version='storyboard-handoff/1.0',project_id=ir['project_id'],revision=ir['revision'],
                   status='BLOCKED' if qa['status']=='BLOCKED' else 'PLANNED',input_hash=input_hash,
                   ir_file='storyboard.ir.json',asset_base=str(Path(base).resolve()),upstreams=ir['upstreams'],
                   shots=[dict(id=s['id'],scene_id=s['scene_id'],start_frame=s['start_frame'],end_frame=s['end_frame'],
                               panel_ids=[p['id'] for p in s['panels']],requirement_ids=[c['id'] for c in ir['contract'] if not c['shot_ids'] or s['id'] in c['shot_ids']]) for s in ir['shots']],
                   timebase=ir['delivery'],source_ids=[s['id'] for s in ir['sources']],execution_ready=False,submitted=False,visual_qa='NOT_RUN',
                   target=dict(protocol='avir/1.0',adapter='host_explicit_mapping',negotiation='REQUIRED',
                               preserve=['原始IR与哈希','完整事件及画格','台词原文与归属','合同与上游所有权','整数帧转毫秒的舍入记录']))
    if schema_errors(handoff,'handoff'):
        raise ValueError('内部交接Schema验证失败。')
    emit('compiler-handoff.json',handoff)
    emit('loss.report.json',{'status':'BACKEND_UNRESOLVED','ir_fields_retained':True,
                            'losses':[{'code':'L_AVIR_MAPPING','status':'PENDING','message':'AVIR 1.0无独立节拍、画格和状态事件字段；宿主保留本交接包为sidecar并记录字段映射，不能静默丢失。'},
                                      {'code':'L_NATIVE_CONTROL','status':'PENDING','message':'几何、口型、时长、引用槽位与声音执行须由具体入口证明。'}]})
    deps = [ROOT/'SKILL.md',ROOT/'requirements.txt']
    for folder in ('scripts','schemas','registries','references'):
        deps += [p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    deps += [ROOT/next(s['file'] for s in style_index() if s['id']==sid) for sid in selected]
    runtime = {str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in sorted(set(deps))}
    manifest = {'compiler':'storyboard-grammar@'+VERSION,'input_hash':input_hash,'runtime_files':runtime,
                'files':{p.name:sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}}
    manifest['build_id'] = digest(manifest)
    emit('compile-manifest.json',manifest)
    return qa


def verify(package):
    package=Path(package)
    m=read(package/'compile-manifest.json')
    if digest({k:v for k,v in m.items() if k!='build_id'}) != m['build_id']:
        raise ValueError('E_MANIFEST_HASH: 清单已变化。')
    actual={p.name for p in package.iterdir() if p.is_file() and p.name!='compile-manifest.json'}
    if actual != set(m['files']):
        raise ValueError('E_PACKAGE_MEMBERS: 文件集合变化。')
    for name,h in m['files'].items():
        p=package/name
        if Path(name).name!=name or p.is_symlink() or not p.is_file() or sha256(p.read_bytes()).hexdigest()!=h:
            raise ValueError('E_PACKAGE_HASH: '+name)
    if digest(read(package/'storyboard.ir.json'))!=m['input_hash']:
        raise ValueError('E_INPUT_HASH')
    if read(package/'storyboard.ir.json').get('schema_version') in ('storyboard-ir/1.1','storyboard-ir/1.2'):
        report = validate(read(package/'storyboard.ir.json'), package)
        if report['status'] == 'INVALID': raise ValueError('E_PACKAGE_SCHEMA: ' + str(report['diagnostics']))
        return {'status':'VERIFIED','build_id':m['build_id'],'files':len(m['files']),'media':'NOT_RUN'}
    for name,schema in [('compiler-handoff.json','handoff'),('qa.report.json','qa-report'),('production-contract.json','production-contract')]:
        if schema_errors(read(package/name),schema):
            raise ValueError('E_PACKAGE_SCHEMA: '+name)
    return {'status':'VERIFIED','build_id':m['build_id'],'files':len(m['files']),'media':'NOT_RUN'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('route');p.add_argument('query');p.add_argument('--forbid',action='append',default=[])
    for name in ('inspect','compile'):
        p=sub.add_parser(name);p.add_argument('input')
        if name=='compile':p.add_argument('--out',required=True)
    p=sub.add_parser('verify');p.add_argument('package')
    args=parser.parse_args()
    try:
        if args.command=='route':result=route(args.query,args.forbid)
        elif args.command=='verify':result=verify(args.package)
        else:
            p=Path(args.input).resolve();ir=read(p)
            result=validate(ir,p.parent) if args.command=='inspect' else compile_package(ir,p.parent,args.out)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 2 if result.get('status') in ('INVALID','BLOCKED') else 0
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        print(json.dumps({'status':'ERROR','message':str(e),'submitted':False},ensure_ascii=False))
        return 2


if __name__=='__main__':
    sys.exit(main())
