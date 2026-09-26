#!/usr/bin/env python3
"""Build the frozen DirectorIR candidate from the read-only upstream snapshots."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
OUT = ROOT / 'runtime/v6/candidates/TASK_eb6702e9e268b2ba339b0fcf/2'
MODULE = ROOT / 'runtime/modules/0cac239790b608f91542f2902607f91d444ab246be102a4b062448144d08fa64/director-grammar'
CANON_PATH = ROOT / 'runtime/v6/candidates/TASK_5ae2734678bb041b76474d34/1/canon.json'
SCRIPT_PATH = ROOT / 'runtime/v6/candidates/TASK_20dbe9991f545d5fe05e55e7/2/script-ir.json'
TASK_PATH = ROOT / 'runtime/tasks/TASK_eb6702e9e268b2ba339b0fcf.json'
SOURCE_PATH = ROOT / 'sources/SRC_69a71adcfaca/source.txt'
HANDOFF_PATH = ROOT / 'runtime/v6/candidates/TASK_20dbe9991f545d5fe05e55e7/2/compiled/director-handoff.json'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()

def digest(value):
    return sha256(encoded(value)).hexdigest()

def save(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))
    return path

def pointer(value, path):
    for key in path.strip('/').split('/') if path else []:
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value

canon, script, task, handoff = map(read, (CANON_PATH, SCRIPT_PATH, TASK_PATH, HANDOFF_PATH))
assert canon['content'] == SOURCE_PATH.read_text(encoding='utf-8').strip()
assert script['narrative']['reveal_order'] == [x['id'] for x in canon['event_order']]
assert [b['id'] for b in script['scenes'][0]['blocks']] == ['B_HANDOFF', 'B_SEAL_CHECK', 'B_STOW']

src = 'SRC_69a71adcfaca'
design = 'DESIGN_D1'
script_ref = 'SCRIPT_V16'
canon_ref = 'CANON_V12'
refs = [src, canon_ref, script_ref, design]
design_origin = {'kind': 'design', 'source_refs': [design, script_ref], 'locator': '三镜机位、动作细节与计划时长；仅为本次导演设计'}
source_origin = {'kind': 'source', 'source_refs': [src, canon_ref, script_ref], 'locator': '同一封信及三段动作顺序'}

def part(text, status='specified'):
    return {'status': status, 'text': text}

def entity_state(eid, stage):
    if eid == 'CHAR_JIA':
        return {'position': [-0.6, 0, 0], 'pose': '站定，朝乙方向递信' if stage == 0 else '站定，递信手已放开',
                'body_facing': '朝乙，具体角度为设计意图', 'head_facing': '朝乙与信的交接处', 'gaze': 'PROP_LETTER',
                'contacts': ['PROP_LETTER'] if stage == 0 else [], 'supports': ['自身站立支撑'],
                'controllers': ['PROP_LETTER'] if stage == 0 else [], 'visible_parts': [], 'condition': '身份与外观未指定'}
    if eid == 'CHAR_YI':
        pose = ['面向甲，准备接信', '接住信并持稳', '接住信并持稳', '将信送入背包后手离包口'][stage]
        return {'position': [0.6, 0, 0], 'pose': pose, 'body_facing': '朝甲，具体角度为设计意图',
                'head_facing': '随信封观察方向微调', 'gaze': 'PROP_LETTER',
                'contacts': [] if stage == 0 else ['PROP_LETTER'] if stage in (1, 2) else [],
                'supports': ['自身站立支撑'], 'controllers': [], 'visible_parts': [],
                'condition': '尚未确认封口' if stage in (0, 1) else '已确认同一封信封口完整'}
    if eid == 'PROP_LETTER':
        positions = [[-0.35, 0.9, 0], [0.3, 0.9, 0], [0.3, 0.9, 0], [0.72, 0.45, 0]]
        contact = ['CHAR_JIA.right_hand', 'CHAR_YI.right_hand', 'CHAR_YI.right_hand', 'PROP_BACKPACK.interior'][stage]
        return {'position': positions[stage], 'pose': '同一封未拆的信，封口保持完整',
                'body_facing': '封口朝可被乙查看的一侧', 'head_facing': '不适用', 'gaze': '不适用',
                'contacts': [contact], 'supports': [contact], 'controllers': [contact] if stage < 3 else [],
                'visible_parts': [], 'condition': '未拆；封口完整；仍为同一封信'}
    if eid == 'PROP_BACKPACK':
        return {'position': [0.75, 0.4, 0], 'pose': '位于乙可触及范围；样式和放置方式由美术确定',
                'body_facing': '未规定', 'head_facing': '不适用', 'gaze': '不适用',
                'contacts': [], 'supports': ['稳定承托；具体场景拓扑由美术确定'], 'controllers': [],
                'visible_parts': [], 'condition': '收纳同一封信' if stage == 3 else '待收纳信'}
    return {'position': [0, 0, 0], 'pose': '雨夜环境；具体地点与室内外状态未指定',
            'body_facing': '不适用', 'head_facing': '不适用', 'gaze': '不适用',
            'contacts': [], 'supports': [], 'controllers': [], 'visible_parts': [], 'condition': '雨夜持续'}

entity_ids = ['CHAR_JIA', 'CHAR_YI', 'PROP_LETTER', 'PROP_BACKPACK', 'ENV_RAIN_NIGHT']
states = [{eid: entity_state(eid, stage) for eid in entity_ids} for stage in range(4)]

def old_view(stage):
    result = []
    for eid in entity_ids:
        st = states[stage][eid]
        result.append({'entity_id': eid, 'position_m': [st['position'][0], st['position'][2], st['position'][1]],
                       'yaw_deg': 0, 'pose': st['pose'], 'support': '；'.join(st['supports']) or '不适用',
                       'contact': '；'.join(st['contacts']) or '无接触',
                       'gaze_target': 'PROP_LETTER' if eid in ('CHAR_JIA', 'CHAR_YI') else None})
    return result

def subject(eid, box, parts, depth='midground', readability='body'):
    return {'node_id': 'N_' + eid, 'box': box, 'depth': depth, 'visible_parts': parts,
            'readability': readability, 'occlusion': '关键部位保持无遮挡', 'presence': 'inside',
            'description': '仅是画面位置设计；外观和场景材质未指定'}

shots = []
shot_defs = [
    ('S_HANDOFF', 'B_HANDOFF', '甲把一封未拆的信交给乙', '甲的手、乙的接手与同一封信可见',
     [subject('CHAR_JIA', [0.08, 0.14, 0.34, 0.72], ['body', 'hands']),
      subject('CHAR_YI', [0.58, 0.14, 0.34, 0.72], ['body', 'hands']),
      subject('PROP_LETTER', [0.43, 0.50, 0.15, 0.14], ['prop'], 'foreground', 'detail')],
     [0, -3, 1.3], '二人手与信同框的中景', ['交接前尚未确认', '甲交给乙一封未拆的信'],
     ['甲与乙之间的同一封信', '乙接稳信后甲松手'], [1, 3], 'EVENT_HANDOFF'),
    ('S_SEAL', 'B_SEAL_CHECK', '乙查看同一封信并确认封口完整', '乙视线与完整封口同框；不能出现拆信',
     [subject('CHAR_YI', [0.53, 0.08, 0.37, 0.74], ['face', 'eyes', 'hands'], 'midground', 'detail'),
      subject('PROP_LETTER', [0.24, 0.49, 0.34, 0.23], ['prop'], 'foreground', 'detail')],
     [0.25, -1.8, 1.25], '乙眼神和封口均可辨的近景', ['乙已接稳同一封未拆的信'],
     ['乙已确认封口完整，信仍未拆'], [2, 3], 'EVENT_SEAL_CHECK'),
    ('S_STOW', 'B_STOW', '确认后乙把同一封信收进背包', '信从乙手中进入背包；终态在包内',
     [subject('CHAR_YI', [0.18, 0.10, 0.52, 0.79], ['body', 'hands']),
      subject('PROP_LETTER', [0.53, 0.48, 0.17, 0.12], ['prop'], 'foreground', 'detail'),
      subject('PROP_BACKPACK', [0.55, 0.55, 0.32, 0.34], ['prop'], 'foreground', 'detail')],
     [0.2, -2.1, 1.25], '乙手、信和背包口同框的中近景', ['乙已确认封口完整'],
     ['同一封未拆的信已经收进背包'], [2, 3], 'EVENT_STOW'),
]
for i, (sid, bid, purpose, rule, subs, camera_pos, framing, before, after, attention, action_id) in enumerate(shot_defs):
    first, last = i * 3000, (i + 1) * 3000
    entities_in_frame = [s['node_id'][2:] for s in subs]
    shots.append({
        'id': sid, 'scene_id': 'SCENE_HANDOFF', 'beat_id': bid, 'source_refs': refs,
        'purpose': purpose, 'story_order': i + 1, 'frames': 72,
        'narrative': {'audience_before': before, 'audience_after': after,
                      'character_knows': ['乙尚未确认封口'] if i == 0 else ['乙已确认封口完整'] if i == 2 else ['乙在本镜确认封口完整'],
                      'reveal': None, 'viewpoint': '客观观察；只呈现当前事件，不提前呈现后续结果'},
        'start_state': old_view(i), 'end_state': old_view(i + 1), 'phases': [],
        'composition': {'rule': rule, 'attention_order': entities_in_frame,
                        'negative_space': '给手、信及背包口留出动作空间',
                        'depth_layers': '关键手与信在前；人物关系在中；雨夜氛围在后',
                        'safe_area': [0.04, 0.04, 0.92, 0.92],
                        'subjects': [{'entity_id': s['node_id'][2:], 'box': s['box'], 'visible_parts': s['visible_parts']} for s in subs]},
        'camera': {'movement': 'locked', 'motivation': '让当前剧情证据在动作期间可见',
                   'start_m': camera_pos, 'end_m': camera_pos, 'look_at_m': [0, 0, 1],
                   'roll_deg': 0, 'focal_mm': 40, 'framing_start': framing, 'framing_end': framing,
                   'path': '在交接轴同一侧固定观察；镜间切换不改变世界左右关系',
                   'speed': '全程固定；数值仅为机位设计意图', 'focus': '当前动作证据清楚可辨',
                   'precision': 'qualitative', 'axis_side': 'negative', 'axis_transition': None},
        'performance': [], 'dialogue': [],
        'sound': {'ambience': '雨夜持续雨声', 'cue': '本镜不增加对白或剧情性声源',
                  'sync': '雨声跨镜连续；动作音如需后期处理须与真实接触同步', 'silence': False},
        'lighting': {'source': '雨夜可读的既有环境光；具体光源由美术确定',
                     'direction': '保持跨镜一致，方向由美术确定', 'quality': '手部与信封封口可辨',
                     'color_purpose': '保持夜晚气氛，不借色彩虚构信件内容'},
        'must_show': [{'entity_id': s['node_id'][2:], 'part': 'prop' if 'prop' in s['visible_parts'] else 'hands' if 'hands' in s['visible_parts'] else 'eyes',
                       'reason': rule} for s in subs],
        'references': [], 'technique_ids': ['locked_observation', 'contact_action'],
        'continuity': {'from_shot': None if i == 0 else shots[-1]['id'],
                       'match_entities': [] if i == 0 else ['CHAR_JIA', 'CHAR_YI', 'PROP_LETTER', 'PROP_BACKPACK'],
                       'transition': 'continuous', 'reason': '同一场连续事件，镜间无省略',
                       'invariants': ['同一封信始终未拆且封口完整', '角色身份和道具外观跨镜连续', '交接轴不跳轴']},
        'acceptance_ids': ['G3_' + sid],
    })

# The shot summary describes its settled frame; the timed tracks below retain
# the exposed letter while it travels from hand to backpack.
stow_shot = shots[2]
stow_shot['camera']['framing_end'] = '乙手退出包口，信已完全在包内；终帧只见乙与背包口'
stow_shot['composition']['rule'] = '前段信与手、背包口同框；8500毫秒信完全入包后不再可见，终帧呈现收存结果'
stow_shot['composition']['attention_order'] = ['CHAR_YI', 'PROP_BACKPACK']
stow_shot['composition']['depth_layers'] = '终帧乙手与背包口可见；信在包内，不作为外露前景'
stow_shot['composition']['negative_space'] = '给乙手退出包口留出动作空间'
stow_shot['composition']['subjects'] = [s for s in stow_shot['composition']['subjects'] if s['entity_id'] != 'PROP_LETTER']

timeline = {'schema': 'detail-timeline/1.2',
            'coordinate_system': 'x-right,y-up,z-depth; screen and anatomical directions are separate',
            'action_groups': [], 'actions': [], 'performances': [], 'camera_operations': [],
            'audio_events': [], 'state_samples': [], 'visibility': [], 'segments': [],
            'source_time_maps': [], 'extensions': [],
            'semantic_review': {'status': 'PENDING', 'reviewer': None, 'input_sha256': None, 'findings': []},
            'spatial_nodes': [], 'motion_tracks': [], 'spatial_relations': [], 'composition_tracks': []}

for i, (sid, bid, purpose, rule, subs, camera_pos, framing, before, after, attention, action_id) in enumerate(shot_defs):
    first, last = i * 3000, (i + 1) * 3000
    timeline['action_groups'].append({'id': 'GROUP_' + sid, 'parent_id': None, 'purpose': purpose,
                                      'beat_ids': [bid], 'origin': source_origin})
    timeline['state_samples'].extend([
        {'id': 'STATE_' + sid + '_START', 'shot_id': sid, 'at_ms': first, 'entities': deepcopy(states[i]), 'origin': design_origin},
        {'id': 'STATE_' + sid + '_END', 'shot_id': sid, 'at_ms': last, 'entities': deepcopy(states[i + 1]), 'origin': design_origin},
    ])
    timeline['camera_operations'].append({'id': 'CAM_' + sid, 'start_ms': first, 'end_ms': last,
        'shot_ids': [sid], 'origin': design_origin, 'operation': 'locked',
        'start_position': str(camera_pos), 'end_position': str(camera_pos),
        'start_framing': framing, 'end_framing': framing, 'height': '以信与手的可见性为准',
        'orientation': '同侧机位、零滚转；俯仰看向当前关键动作',
        'path': '固定机位，无推拉摇移或变焦', 'speed': '全程固定',
        'look_at': rule, 'focus': rule, 'axis': '同侧交接轴，切镜不跳轴',
        'sync_action_ids': [action_id], 'precision': 'intent'})
    timeline['composition_tracks'].append({'id': 'COMP_' + sid, 'shot_ids': [sid],
        'start_ms': first, 'end_ms': last, 'framing': framing,
        'attention_order': [s['node_id'] for s in subs],
        'negative_space': '手部与信的动作区域留白', 'safe_area': '关键手、信和包口在安全框内',
        'depth_layers': '关键手与信在前，人物关系在中，雨夜氛围在后',
        'subjects': subs, 'origin': design_origin})

for eid in entity_ids:
    timeline['spatial_nodes'].append({'id': 'N_' + eid, 'entity_id': eid, 'kind': 'entity',
        'label': eid, 'part': None, 'parent_id': None,
        'frame': {'kind': 'world', 'anchor_node_id': None, 'unit': 'm', 'transforms': []},
        'bounds': None, 'origin': design_origin})
timeline['spatial_nodes'].append({'id': 'N_CAMERA', 'entity_id': None, 'kind': 'camera',
    'label': '摄影机', 'part': None, 'parent_id': None,
    'frame': {'kind': 'world', 'anchor_node_id': None, 'unit': 'm', 'transforms': []},
    'bounds': None, 'origin': design_origin})

# Once the letter has entered the backpack, the closing frame must show the
# backpack and withdrawing hand, not pretend the letter remains visible.
timeline['state_samples'].insert(5, {'id': 'STATE_S_STOW_SETTLED', 'shot_id': 'S_STOW',
    'at_ms': 8500, 'entities': deepcopy(states[3]), 'origin': design_origin})
stow_comp = timeline['composition_tracks'][2]
stow_comp['end_ms'] = 8500
settled_comp = deepcopy(stow_comp)
settled_comp['id'] = 'COMP_S_STOW_SETTLED'
settled_comp['start_ms'] = 8500
settled_comp['end_ms'] = 9000
settled_comp['framing'] = '乙手退出包口、背包收纳终态可见'
settled_comp['subjects'] = [s for s in settled_comp['subjects'] if s['node_id'] != 'N_PROP_LETTER']
settled_comp['attention_order'] = [s['node_id'] for s in settled_comp['subjects']]
settled_comp['depth_layers'] = '乙手和背包口可见；信已在包内，不再作为画面可见物'
settled_comp['negative_space'] = '给乙手退出包口留出动作空间'
settled_comp['safe_area'] = '乙手和背包口在安全框内；包内信不外露'
timeline['composition_tracks'].append(settled_comp)

action_text = [
    {'actor': 'CHAR_JIA', 'target': 'PROP_LETTER', 'effector': '甲右手，乙右手接应',
     'operation': '甲右手将同一封未拆的信送入乙右手可接触范围；乙接稳后甲松开。',
     'trigger': '雨夜，甲持有未拆的信', 'path': '从甲近侧越过两人之间，到乙手中；信不脱手掉落',
     'speed': '先平稳前送，乙接稳时短暂停顿后甲松手',
     'support': '信先由甲右手承托，双手短暂共持，再由乙右手承托',
     'contact': '交接点双手与信同框；乙接触并取得控制后甲释放',
     'feedback': '乙手对信形成稳定夹持，甲指尖离开；同一封信完整可见',
     'settle': '乙右手独自持有未拆的信，封口未受损'},
    {'actor': 'CHAR_YI', 'target': 'PROP_LETTER', 'effector': '乙眼睛与持信右手',
     'operation': '乙不拆信，将持信手微调至封口朝向视线，目光沿封口查看并确认完整。',
     'trigger': '乙已接稳同一封信', 'path': '信在乙右手控制下微转，封口始终可见',
     'speed': '稳持、短暂停看封口后收束',
     'support': '乙右手始终支撑并控制信，身体站姿保持稳定',
     'contact': '手指不掀开封口，不取出内容',
     'feedback': '观众能看清完整封口与乙的确认视线',
     'settle': '乙已确认封口完整，信仍未拆'},
    {'actor': 'CHAR_YI', 'target': 'PROP_LETTER', 'effector': '乙右手',
     'operation': '确认之后，乙把同一封未拆的信沿背包口送入包内，手退出，信留在包内。',
     'trigger': '乙已经确认封口完整', 'path': '从持信位置到乙可触及的背包口，再进入包内',
     'speed': '先送至包口，保持信完整，再完全放入后松手',
     'support': '入包前乙右手支撑；入包后由背包内部承托',
     'contact': '信经过包口，全程同一封；乙手在信已入包后才释放控制',
     'feedback': '信完全进入背包且不再露在手中',
     'settle': '同一封未拆的信收在背包内'},
]
for i, text in enumerate(action_text):
    first, last = i * 3000, (i + 1) * 3000
    sid = shot_defs[i][0]
    changes = []
    if i == 0:
        fields = [('PROP_LETTER', 'position'), ('PROP_LETTER', 'contacts'), ('PROP_LETTER', 'supports'),
                  ('PROP_LETTER', 'controllers'), ('CHAR_JIA', 'pose'), ('CHAR_JIA', 'contacts'),
                  ('CHAR_JIA', 'controllers'), ('CHAR_YI', 'pose'), ('CHAR_YI', 'contacts')]
    elif i == 1:
        fields = [('CHAR_YI', 'condition')]
    else:
        fields = [('PROP_LETTER', 'position'), ('PROP_LETTER', 'contacts'), ('PROP_LETTER', 'supports'),
                  ('PROP_LETTER', 'controllers'), ('CHAR_YI', 'pose'), ('CHAR_YI', 'contacts'),
                  ('PROP_BACKPACK', 'condition')]
    for eid, field in fields:
        changes.append({'entity_id': eid, 'field': field, 'before': states[i][eid][field],
                        'after': states[i + 1][eid][field], 'at_ms': 8500 if i == 2 else last})
    timeline['actions'].append({'id': shot_defs[i][-1], 'start_ms': first, 'end_ms': last,
        'shot_ids': [sid], 'origin': design_origin, 'parent_id': 'GROUP_' + sid,
        'semantic_id': ['EVT_HANDOFF', 'EVT_SEAL_CHECK', 'EVT_STOW'][i],
        'actor_id': text['actor'], 'target_id': text['target'],
        'effector': part(text['effector']), 'operation': text['operation'], 'trigger': text['trigger'],
        'path': part(text['path']), 'speed': part(text['speed']), 'support': part(text['support']),
        'contact': part(text['contact']), 'feedback': text['feedback'], 'settle': text['settle'],
        'depends_on': [] if i == 0 else [{'action_id': shot_defs[i - 1][-1], 'relation': 'after_end', 'marker': None, 'offset_ms': 0}],
        'markers': [{'id': 'END_' + sid, 'at_ms': last, 'meaning': text['settle']}], 'changes': changes})

timeline['audio_events'].append({'id': 'RAIN_AMBIENCE', 'start_ms': 0, 'end_ms': 9000,
    'shot_ids': [x[0] for x in shot_defs], 'origin': design_origin, 'kind': 'ambience',
    'speaker_id': None, 'source_utterance_id': None, 'text': '连续雨声；无人物对白',
    'placement': 'environment', 'lip_sync': False, 'delivery': '持续且不过度盖住接触动作',
    'mix': '低于动作细节声', 'sync': None, 'phrases': [], 'overlap_reason': None, 'route': 'post'})

checks = [
    {'id': 'G0_INPUT', 'gate': 'G0', 'scope': 'project', 'method': 'static', 'predicate': '冻结 Canon、ScriptIR 和来源哈希保持一致', 'evidence_required': '输入和模块哈希回执', 'owner': 'director', 'blocking': True},
    {'id': 'G1_SEMANTIC', 'gate': 'G1', 'scope': 'project', 'method': 'static', 'predicate': '雨夜、同一封未拆信、事件顺序和终态在原生字段中成立', 'evidence_required': 'DirectorIR 静态校验及当前执行者语义复核', 'owner': 'director', 'blocking': True},
    *[{'id': 'G3_' + s[0], 'gate': 'G3', 'scope': s[0], 'method': 'frame_review', 'predicate': s[3],
       'evidence_required': '实际 Take 的文件哈希、帧号和画面观察', 'owner': 'media_reviewer', 'blocking': True} for s in shot_defs],
    {'id': 'G4_FINAL', 'gate': 'G4', 'scope': 'project', 'method': 'playback',
     'predicate': '完整观看确认交接、验封、入包顺序及同一封信、雨夜成立',
     'evidence_required': '实际成片完整播放与声音记录', 'owner': 'final_reviewer', 'blocking': True},
]

clauses = [
    ('REQ_RAIN_NIGHT', '保留雨夜；不指定具体地点或室内外状态。', ['/scenes/0/space', '/shots/0/sound/ambience', '/timeline/audio_events/0/text'], ['G1_SEMANTIC', 'G4_FINAL']),
    ('REQ_SAME_UNOPENED_LETTER', '三个事件使用同一封未拆的信，验封不拆信。', ['/entities/2', '/timeline/actions/0', '/timeline/actions/1', '/timeline/actions/2', '/timeline/state_samples'], ['G1_SEMANTIC', 'G3_S_SEAL', 'G4_FINAL']),
    ('REQ_EVENT_ORDER', '甲先交信，乙再确认封口，之后才收入背包。', ['/beats', '/shots', '/timeline/actions'], ['G1_SEMANTIC', 'G4_FINAL']),
    ('REQ_ENDING', '结尾同一封未拆的信已经收进背包。', ['/shots/2/end_state', '/shots/2/narrative/audience_after', '/timeline/state_samples/6'], ['G3_S_STOW', 'G4_FINAL']),
    ('REQ_SCRIPT_EVENTS', '保留 EVT_HANDOFF、EVT_SEAL_CHECK、EVT_STOW 的因果与角色认知。', ['/timeline/actions', '/shots/1/narrative', '/shots/2/narrative'], ['G1_SEMANTIC', 'G4_FINAL']),
    ('REQ_REVEAL_ORDER', '只按交接、验封、入包顺序向观众呈现信息。', ['/shots/0', '/shots/1', '/shots/2'], ['G1_SEMANTIC', 'G4_FINAL']),
]
contract = {'id': 'CONTRACT_LETTER_DIRECTOR', 'version': 1,
    'scope': '雨夜同一封信的交接、验封、入包；导演静态实现',
    'deliverables': ['DirectorIR', '上游约束映射', '静态校验回执'],
    'clauses': [{'id': cid, 'requirement': req, 'priority': 'hard', 'source_refs': [src, canon_ref, script_ref],
                 'paths': paths, 'check_ids': ids, 'change_policy': 'explicit_revision',
                 'allowed_channels': ['natural_language', 'review', 'post']} for cid, req, paths, ids in clauses],
    'checks': checks,
    'execution': {'mode': 'plan_only', 'authorization_ref': None, 'max_attempts_per_job': 1,
                  'budget_amount': 0, 'currency': 'CNY',
                  'stop_conditions': ['尚未进入实际视频生成', '任一硬要求缺失则停止下游执行']},
    'acceptance': {'rule': 'all_blocking_checks_pass', 'waivers': []}}

ir = {'schema_version': '1.2', 'project_id': 'LETTER_FULL_DEMO', 'revision': 2,
    'canon_ref': str(CANON_PATH),
    'sources': [
        {'id': src, 'kind': 'user', 'uri': str(SOURCE_PATH), 'locator': '原文全文',
         'claim': canon['content'], 'verification': 'read'},
        {'id': canon_ref, 'kind': 'canon', 'uri': str(CANON_PATH), 'locator': 'content/source_requirements/event_order/entities',
         'claim': '雨夜，同一封未拆信；先交接、后验封、再入包；地点身份外观未指定', 'verification': 'read'},
        {'id': script_ref, 'kind': 'canon', 'uri': str(SCRIPT_PATH), 'locator': 'scenes/narrative/contract',
         'claim': '单场三动作块，无对白；乙在确认封口完整后收入背包', 'verification': 'read'},
        {'id': design, 'kind': 'design', 'uri': 'design://LETTER_FULL_DEMO/director-v2',
         'locator': '本候选 DirectorIR；三镜、9秒、24fps、16:9、站位及机位均为设计意图',
         'claim': '只在原有事件范围内设计动作可读性；地点、室内外、人物外观和背包样式交由相应所有者',
         'verification': 'inference'}],
    'intent': {'task': 'narrative', 'goal': '让观众按交接、完整封口确认、信入背包的顺序看懂同一封信的状态',
               'tags': ['写实', '观察', '克制'], 'style_request': None, 'forbidden_techniques': []},
    'format': {'fps': 24, 'width': 1280, 'height': 720, 'total_frames': 216},
    'entities': [
        {'id': e['id'], 'name': e['name'], 'kind': 'location' if e['kind'] == 'setting' else e['kind'],
         'description': e['description'], 'source_refs': [src, canon_ref]} for e in canon['entities']],
    'assets': [],
    'scenes': [{'id': 'SCENE_HANDOFF', 'location_id': 'ENV_RAIN_NIGHT',
                'space': '雨夜；具体地点与室内外未指定。为交接动作设计甲在画面一侧、乙在另一侧、背包在乙可触及范围，实体绝对尺寸和承托由美术定。',
                'coordinate_system': 'right-handed:X-right,Y-depth,Z-up;meters',
                'axis_start_m': [-0.6, 0, 0], 'axis_end_m': [0.6, 0, 0], 'style_id': 'observational'}],
    'beats': [{'id': bid, 'scene_id': 'SCENE_HANDOFF', 'change': purpose,
               'source_refs': [src, canon_ref, script_ref]} for _, bid, purpose, *_ in shot_defs],
    'shots': shots, 'contract': contract, 'timeline': timeline}

ir['timeline']['semantic_review'] = {
    'status': 'PASS', 'reviewer': 'current-agent / TASK_eb6702e9e268b2ba339b0fcf / batch 2',
    'input_sha256': None,
    'findings': [
        '雨夜、同一封未拆信与交接→验封→入包顺序对照冻结 Canon 和 ScriptIR；没有添加对白、信件内容、人物身份或具体地点。',
        '三镜均为导演视听设计，封口在验封镜可辨；8500毫秒信完全入包，8500至9000毫秒构图不再显示信，9000毫秒终态与包内支撑一致。',
        '九秒、画幅、站位、机位和动作细节均标为设计意图；实际图像与视频未生成，G3/G4 未运行。',
    ]}
content = deepcopy(ir)
content['timeline'].pop('semantic_review')
ir['timeline']['semantic_review']['input_sha256'] = digest(content)
ir_path = save('director-ir.json', ir)

def screenplay_content_hash(value):
    data = deepcopy(value)
    data.pop('review', None)
    data['timeline'].pop('semantic_review', None)
    for source in data.get('sources', []):
        if source.get('sha256') or source.get('file_sha256') or 'shots' in data:
            source.pop('uri', None)
    return digest(data)

mapping_specs = [
    ('screenplay:REQ_RAIN_NIGHT', 'REQ_RAIN_NIGHT', [('/scenes/0/space', 'contains', '雨夜'), ('/shots/0/sound/ambience', 'contains', '雨夜')], '雨夜由场景与声画氛围承载，具体地点保持开放。'),
    ('screenplay:REQ_SAME_UNOPENED_LETTER', 'REQ_SAME_UNOPENED_LETTER', [('/entities/2/description', 'contains', '同一封未拆的信'), ('/timeline/actions/1/operation', 'contains', '不拆信'), ('/timeline/state_samples/6/entities/PROP_LETTER/condition', 'contains', '未拆')], '同一实体 ID 从交接延续至入包，验封过程不拆信。'),
    ('screenplay:REQ_EVENT_ORDER', 'REQ_EVENT_ORDER', [('/timeline/actions/0/semantic_id', 'equals', 'EVT_HANDOFF'), ('/timeline/actions/1/semantic_id', 'equals', 'EVT_SEAL_CHECK'), ('/timeline/actions/2/semantic_id', 'equals', 'EVT_STOW')], '三个动作的开始时间与前件依赖按剧本顺序排列。'),
    ('screenplay:NARRATIVE_ending', 'REQ_ENDING', [('/timeline/state_samples/6/entities/PROP_LETTER/contacts', 'contains', 'PROP_BACKPACK.interior'), ('/shots/2/narrative/audience_after', 'contains', '同一封未拆的信已经收进背包')], '最终关键姿态与观众所得信息均为同一封信入包。'),
    ('screenplay:NARRATIVE_events', 'REQ_SCRIPT_EVENTS', [('/timeline/actions/0/semantic_id', 'equals', 'EVT_HANDOFF'), ('/timeline/actions/1/semantic_id', 'equals', 'EVT_SEAL_CHECK'), ('/timeline/actions/2/semantic_id', 'equals', 'EVT_STOW'), ('/shots/1/narrative/character_knows', 'contains', '乙在本镜确认封口完整')], '每一剧本事件均有独立动作、可见反馈和认知更新。'),
    ('screenplay:NARRATIVE_reveal_order', 'REQ_REVEAL_ORDER', [('/shots/0/story_order', 'equals', 1), ('/shots/1/story_order', 'equals', 2), ('/shots/2/story_order', 'equals', 3)], '镜头和动作顺序均与剧本 reveal_order 对齐。'),
]
required = {r['id']: r for r in task['handoff']['required_handoffs']}
mappings = []
for req_id, clause_id, specs, reason in mapping_specs:
    checks = [{'path': p, 'op': op, 'value': value} for p, op, value in specs]
    for check in checks:
        actual = pointer(ir, check['path'])
        assert actual == check['value'] if check['op'] == 'equals' else check['value'] in actual
    mappings.append({'requirement_id': req_id, 'source_fingerprint': required[req_id]['source_fingerprint'],
                     'target_clause': clause_id, 'target_checks': checks, 'reason': reason})
assert set(required) == {m['requirement_id'] for m in mappings}
save('screenplay-map.json', {'schema': 'screenplay-director-map/1.0',
    'screenplay_sha256': handoff['content_sha256'], 'director_sha256': screenplay_content_hash(ir),
    'reviewer': 'current-agent / TASK_eb6702e9e268b2ba339b0fcf / batch 2',
    'findings': ['逐项对照冻结 Canon、ScriptIR 与六条编剧交接；原生硬条款覆盖导演实现路径。'],
    'mappings': mappings})
print(ir_path)
