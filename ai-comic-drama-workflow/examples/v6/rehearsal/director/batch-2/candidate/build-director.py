"""Build this task's source-bound DirectorIR and screenplay mapping."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

ROOT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
OUT = ROOT / 'runtime/v6/candidates/TASK_b1e7ff7ce83d7a32bfa09935/2'
MODULE = ROOT / 'runtime/modules/0cac239790b608f91542f2902607f91d444ab246be102a4b062448144d08fa64/director-grammar'
CANON = ROOT / 'runtime/v6/candidates/TASK_0e0c8a4ca94c8ffdbb7e14ae/1/canon.json'
SCRIPT = ROOT / 'runtime/v6/candidates/TASK_1b94794070565f70c7f697a7/1/script-ir.json'
HANDOFF = ROOT / 'runtime/v6/candidates/TASK_1b94794070565f70c7f697a7/1/compiled/director-handoff.json'
SOURCE = ROOT / 'sources/SRC_69a71adcfaca/source.txt'

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

screenplay = load_module('screenplay_protocol_for_director', MODULE / 'scripts/screenplay_protocol.py')
detail = load_module('detail_runtime_for_director', MODULE / 'scripts/detail_runtime.py')

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')

def origin(kind, refs, locator):
    return {'kind': kind, 'source_refs': refs, 'locator': locator}

SRC = 'SRC_69a71adcfaca'
DESIGN = 'DIRECTOR_DESIGN'
FACT = [SRC, 'CANON_INPUT', 'SCRIPT_INPUT']
DESIGNED = [SRC, 'SCRIPT_INPUT', DESIGN]
source_origin = origin('source', FACT, 'ScriptIR /scenes/0/blocks 与 Canon /event_order')
design_origin = origin('design', DESIGNED, '导演视听实现；非来源事实或已生成媒体')

def described(text):
    return {'status': 'specified', 'text': text}

def inapplicable(text='原文未指定；本镜无需此项'):
    return {'status': 'not_applicable', 'text': text}

def change(eid, field, before, after, at):
    return {'entity_id': eid, 'field': field, 'before': before, 'after': after, 'at_ms': at}

def depends(aid):
    return {'action_id': aid, 'relation': 'after_end', 'marker': None, 'offset_ms': 0}

def action(aid, start, end, parent, semantic, actor, target, effector, operation, trigger,
           path, speed, support, contact, feedback, settle, dependencies, markers, changes):
    return {'id': aid, 'start_ms': start, 'end_ms': end, 'shot_ids': ['S1'], 'origin': design_origin,
            'parent_id': parent, 'semantic_id': semantic, 'actor_id': actor, 'target_id': target,
            'effector': described(effector), 'operation': operation, 'trigger': trigger,
            'path': described(path), 'speed': described(speed), 'support': described(support),
            'contact': described(contact), 'feedback': feedback, 'settle': settle,
            'depends_on': dependencies, 'markers': markers, 'changes': changes}

def marker(mid, at, meaning):
    return {'id': mid, 'at_ms': at, 'meaning': meaning}

def state(position, pose, gaze, contacts, supports, controllers, visible, condition, facing='面向对方'):
    return {'position': position, 'pose': pose, 'body_facing': facing,
            'head_facing': facing, 'gaze': gaze, 'contacts': contacts, 'supports': supports,
            'controllers': controllers, 'visible_parts': visible, 'condition': condition}

initial = {
    'CHAR_JIA': state([-0.65, 0, 0], '站立；右手持同一封未拆信', '信与乙', [], ['双足着地'], [], ['face','eyes','hands','body'], '身份、外观未提供'),
    'CHAR_YI': state([0.65, 0, 0], '站立；右手准备接信；背包可及', '甲手中的信', [], ['双足着地'], [], ['face','eyes','hands','body'], '身份、外观未提供'),
    'PROP_LETTER': state([-0.2, 1.1, 0], '未拆；封口朝上', '无', ['CHAR_JIA.right_hand'], ['CHAR_JIA.right_hand'], ['CHAR_JIA.right_hand'], ['body','seal'], '同一封信；内容未知；封口完整', '按纸面朝向'),
    'PROP_BACKPACK': state([0.7, 0.75, 0], '乙携带的背包；开口可达', '无', ['CHAR_YI.body'], ['CHAR_YI.body'], [], ['body'], '外观未提供', '随乙身体'),
    'ENV_RAIN_NIGHT': state([0, 0, 0], '雨夜；具体地点与室内外未指定', '无', [], [], [], [], '天气和夜间事实不变', '场景基准'),
}

actions = [
    action('ACT_EXTEND', 500, 1800, 'GROUP_HANDOFF', 'EVT_HANDOFF', 'CHAR_JIA', 'PROP_LETTER',
           'right_hand', '甲把未拆的信从自身一侧送向乙的手边。', '甲开始交信',
           '右前臂向两人之间伸出；信保持封口朝上，不换手。', '平稳前送，接触前减速。',
           '甲双足稳定；右手继续承托信。', '甲右手持续接触并控制同一封信。',
           '信到达乙可接触的位置。', '甲仍控制信，等待乙握住纸边。', [],
           [marker('MARK_REACH', 1800, '信到达交接位置，未释放')],
           [change('PROP_LETTER','position',[-0.2,1.1,0],[0,1.1,0],1800)]),
    action('ACT_GRIP', 2000, 2800, 'GROUP_HANDOFF', 'EVT_HANDOFF', 'CHAR_YI', 'PROP_LETTER',
           'right_hand', '乙右手捏住这封信的另一侧纸边，甲保持接触。', '信停在交接位置',
           '乙右手从身侧到信纸边；避开封口，不拆信。', '先接触，再停稳。',
           '乙双足稳定；信短暂由两人的手共同承托。', '甲右手和乙右手同时接触同一封信；此刻控制权仍在甲。',
           '乙握稳纸边。', '双方手部短暂同框且接触点清楚。', [depends('ACT_EXTEND')],
           [marker('MARK_DUAL_CONTACT', 2500, '两只右手同时接触一封信')],
           [change('CHAR_JIA','pose','站立；右手持同一封未拆信','站立；右手仍持同一封未拆信，乙右手已握住另一侧纸边',2500),
            change('CHAR_YI','pose','站立；右手准备接信；背包可及','站立；右手已握住同一封信的另一侧纸边，等待甲松手',2500),
            change('PROP_LETTER','contacts',['CHAR_JIA.right_hand'],['CHAR_JIA.right_hand','CHAR_YI.right_hand'],2500),
            change('PROP_LETTER','supports',['CHAR_JIA.right_hand'],['CHAR_JIA.right_hand','CHAR_YI.right_hand'],2500)]),
    action('ACT_RELEASE', 2800, 4000, 'GROUP_HANDOFF', 'EVT_HANDOFF', 'CHAR_JIA', 'PROP_LETTER',
           'right_hand', '乙握稳后，甲松开右指并收回手；信由乙右手控制。', '乙已经握住信',
           '甲右指离开纸边；乙右手把信移到自己身前。', '先松手，随后小幅移至乙侧并停稳。',
           '乙右手独自承托，甲双足和乙双足仍稳定。', '甲右手释放；信与乙右手持续接触。',
           '交接完成，信仍未拆。', '甲手离开信；乙持有同一封信。', [depends('ACT_GRIP')],
           [marker('MARK_CUSTODY_YI', 3500, '信的控制权由甲转给乙')],
           [change('CHAR_JIA','pose','站立；右手仍持同一封未拆信，乙右手已握住另一侧纸边','站立；右手已松开并收回，不再持信',3500),
            change('CHAR_YI','pose','站立；右手已握住同一封信的另一侧纸边，等待甲松手','站立；右手独自持有同一封未拆信',3500),
            change('CHAR_YI','gaze','甲手中的信','自己右手中的同一封信',3500),
            change('PROP_LETTER','contacts',['CHAR_JIA.right_hand','CHAR_YI.right_hand'],['CHAR_YI.right_hand'],3500),
            change('PROP_LETTER','supports',['CHAR_JIA.right_hand','CHAR_YI.right_hand'],['CHAR_YI.right_hand'],3500),
            change('PROP_LETTER','controllers',['CHAR_JIA.right_hand'],['CHAR_YI.right_hand'],3500),
            change('PROP_LETTER','position',[0,1.1,0],[0.2,1.1,0],3500)]),
    action('ACT_CONFIRM_SEAL', 4500, 7500, 'GROUP_CONFIRM', 'EVT_SEAL_CHECK', 'CHAR_YI', 'PROP_LETTER',
           'eyes_and_right_hand', '乙使封口朝向自己，目视确认封口完整；信始终未拆。', '乙已收到同一封信',
           '乙右手将信维持在视线内，视线从交接处移到封口；不掀开封口。', '抬至可读位置后停顿，留出看清封口的时间。',
           '乙右手持续承托并控制信，双足稳定。', '乙右手始终接触同一封信；封口不被打开。',
           '封口完整这一事实可见，乙才进入收存。', '乙完成确认，未产生新对白或动机。', [depends('ACT_RELEASE')],
           [marker('MARK_SEAL_VISIBLE', 6000, '封口完整可读且乙正在确认')],
           [change('CHAR_YI','gaze','自己右手中的同一封信','同一封信的封口',5500),
            change('CHAR_YI','pose','站立；右手独自持有同一封未拆信','站立；右手持同一封未拆信，正查看完整封口',6000),
            change('PROP_LETTER','pose','未拆；封口朝上','未拆；封口朝乙且完整可见',6000)]),
    action('ACT_STOW', 8000, 11000, 'GROUP_STOW', 'EVT_STOW', 'CHAR_YI', 'PROP_BACKPACK',
           'right_hand_and_left_hand', '确认后，乙左手保持背包开口可达，右手将同一封信送入背包并松开。', '乙已确认封口完整',
           '乙右手持信从胸前移向自身背包开口；左手只保持开口，不替换信。', '先看开口再平稳放入；入包后停稳并松手。',
           '乙双足稳定；信先由乙右手承托，入包后由背包内部承托。', '信从乙右手接触转为背包内部接触；不再次交给甲。',
           '信进入背包，同一对象未拆。', '乙松手，信留在背包内；镜头到此结束，不呈现后续。', [depends('ACT_CONFIRM_SEAL')],
           [marker('MARK_IN_BAG', 10500, '同一封信完成收存，控制权解除')],
           [change('CHAR_YI','gaze','同一封信的封口','背包开口',8500),
            change('CHAR_YI','pose','站立；右手持同一封未拆信，正查看完整封口','站立；右手持同一封未拆信移向背包开口，左手保持开口',8500),
            change('CHAR_JIA','gaze','信与乙','乙的收存动作与背包开口',8500),
            change('CHAR_YI','pose','站立；右手持同一封未拆信移向背包开口，左手保持开口','站立；右手已松开信，左手在背包开口处；同一封信在包内',10500),
            change('PROP_LETTER','position',[0.2,1.1,0],[0.7,0.75,0],10500),
            change('PROP_LETTER','pose','未拆；封口朝乙且完整可见','同一封未拆信在背包内',10500),
            change('PROP_LETTER','contacts',['CHAR_YI.right_hand'],['PROP_BACKPACK.interior'],10500),
            change('PROP_LETTER','supports',['CHAR_YI.right_hand'],['PROP_BACKPACK.interior'],10500),
            change('PROP_LETTER','controllers',['CHAR_YI.right_hand'],[],10500),
            change('PROP_LETTER','visible_parts',['body','seal'],[],10500)]),
]

def sampled_state(at):
    result = deepcopy(initial)
    for a in actions:
        for c in a['changes']:
            if c['at_ms'] <= at:
                result[c['entity_id']][c['field']] = deepcopy(c['after'])
    return result

def legacy_states(sample):
    values=[]
    for eid, st in sample.items():
        x, y, z = st['position']
        values.append({'entity_id':eid, 'position_m':[x,z,y], 'yaw_deg':0,
                       'pose':st['pose'], 'support':'；'.join(st['supports']) or '不适用',
                       'contact':'；'.join(st['contacts']) or '无接触',
                       'gaze_target':('PROP_LETTER' if eid in ('CHAR_JIA','CHAR_YI') and at_state_is_start(sample) else
                                      'PROP_BACKPACK' if eid=='CHAR_YI' else None)})
    return values

def at_state_is_start(sample):
    return sample['PROP_LETTER']['controllers'] == ['CHAR_JIA.right_hand']

def node(nid, eid, kind, label):
    return {'id':nid,'entity_id':eid,'kind':kind,'label':label,'part':None,'parent_id':None,
            'frame':{'kind':'world','anchor_node_id':None,'unit':'m','transforms':[]},
            'bounds':None,'origin':design_origin}

def key(at, value, transition, description):
    return {'at_ms':at,'value':{'mode':'numeric','value':value,'description':description,'target_node_id':None},
            'transition':transition}

def track(tid, nid, action_ids, keys, path, speed):
    return {'id':tid,'node_id':nid,'property':'position','start_ms':0,'end_ms':12000,'shot_ids':['S1'],
            'action_ids':action_ids,'camera_operation_ids':[],'unit':'m','axis':None,
            'path':path,'speed':speed,'keyframes':keys,'origin':design_origin}

def comp_subject(nid, box, parts, readability, occlusion, description):
    return {'node_id':nid,'box':box,'depth':'midground','visible_parts':parts,
            'readability':readability,'occlusion':occlusion,'presence':'inside','description':description}

def composition(cid, start, end, letter_box, letter_parts, yi_readability, purpose):
    return {'id':cid,'shot_ids':['S1'],'start_ms':start,'end_ms':end,
            'framing':'固定双人中近景，甲乙手部、信和乙的背包开口在同一可读范围',
            'attention_order':['N_JIA','N_LETTER','N_YI','N_BACKPACK'],
            'negative_space':'手部路径周围留出动作余量，不用布景信息遮挡封口',
            'safe_area':'关键手、封口和背包开口避开画幅边缘',
            'depth_layers':'人物与道具同属近中景；雨夜仅作不指定地点的环境线索',
            'subjects':[
                comp_subject('N_JIA',[0.04,0.10,0.36,0.82],['face','eyes','hands','body'],'body','手部交接不遮挡','甲在画面左侧，右手路径可读'),
                comp_subject('N_YI',[0.56,0.10,0.40,0.82],['face','eyes','hands','body'],yi_readability,'双手和视线可读','乙在画面右侧，能够查看封口与背包'),
                comp_subject('N_LETTER',letter_box,letter_parts,'detail' if letter_parts else 'body',
                             '封口检查时无遮挡；收存后由背包遮住' if letter_parts else '背包内部遮住整封信',purpose),
                comp_subject('N_BACKPACK',[0.67,0.62,0.19,0.28],['body','opening'],'body','收存时开口不被前臂完全遮住','同一背包位于乙身体可及处')],
            'origin':design_origin}

def perf(pid, start, end, actor, action_ids, behavior, trigger, feedback, settle, eyes, hands, body, parts, readability):
    return {'id':pid,'start_ms':start,'end_ms':end,'shot_ids':['S1'],'origin':design_origin,
            'action_ids':action_ids,'actor_id':actor,'behavior':behavior,'trigger':trigger,
            'feedback':feedback,'settle':settle,'face':inapplicable('未给情绪，不添加表情剧情'),
            'eyes':described(eyes),'hands':described(hands),'body':described(body),
            'breathing':inapplicable('未指定呼吸变化'),'voice':inapplicable('原文无对白；不发声'),
            'needed_parts':parts,'readability':readability,'psychology':None}

sources=[
    {'id':SRC,'kind':'user','uri':str(SOURCE),'locator':'原始 user-text 全文',
     'claim':SOURCE.read_text(encoding='utf-8').strip(),'verification':'read'},
    {'id':'CANON_INPUT','kind':'canon','uri':str(CANON),'locator':'/content /source_facts /entities /event_order /source_requirements',
     'claim':'雨夜；甲交一封未拆信；乙确认封口完整后收进背包；地点、外观、动机、内容和后续未给。','verification':'read'},
    {'id':'SCRIPT_INPUT','kind':'canon','uri':str(SCRIPT),'locator':'/scenes/0/blocks /narrative /contract',
     'claim':'已接受 ScriptIR 固定交信、确认、收存三事件顺序，无对白或后续。','verification':'read'},
    {'id':DESIGN,'kind':'design','uri':'design://TASK_b1e7ff7ce83d7a32bfa09935/director',
     'locator':'本候选 /shots/0 与 /timeline；单镜、手别、镜头时长和示意坐标均为导演设计意图',
     'claim':'一个固定双人中近景连续呈现三事件；动作关键姿态、坐标和 12 秒预算供下游复核，不作为来源事实或实拍测量。',
     'verification':'inference'},
]

entities=[
    {'id':'CHAR_JIA','name':'甲','kind':'character','description':'交信者；外观、关系和动机均未指定。','source_refs':FACT},
    {'id':'CHAR_YI','name':'乙','kind':'character','description':'收信、确认封口并收存者；外观、关系和动机均未指定。','source_refs':FACT},
    {'id':'PROP_LETTER','name':'同一封信','kind':'prop','description':'交接时未拆，乙确认时封口完整；信件内容、样式和来历未知。','source_refs':FACT},
    {'id':'PROP_BACKPACK','name':'背包','kind':'prop','description':'乙收存同一封信的背包；外观未指定。','source_refs':FACT},
    {'id':'ENV_RAIN_NIGHT','name':'雨夜','kind':'location','description':'下雨的夜间；具体地点及室内外状态未指定。','source_refs':FACT},
]

beats=[
    {'id':'BEAT_HANDOFF','scene_id':'SC_RAIN_NIGHT','change':'甲将同一封未拆信交给乙，乙取得控制权。','source_refs':FACT},
    {'id':'BEAT_CONFIRM','scene_id':'SC_RAIN_NIGHT','change':'乙在收存前目视确认同一封信封口完整，信不拆开。','source_refs':FACT},
    {'id':'BEAT_STOW','scene_id':'SC_RAIN_NIGHT','change':'乙确认后将同一封信收进背包；画面到此结束。','source_refs':FACT},
]

shot={
    'id':'S1','scene_id':'SC_RAIN_NIGHT','beat_id':'BEAT_HANDOFF','source_refs':DESIGNED,
    'purpose':'完整呈现交信、验封和收存的先后及同一封信的控制权变化。',
    'story_order':1,'frames':288,
    'narrative':{'audience_before':[],
                 'audience_after':['甲交给乙同一封未拆信','乙确认该信封口完整','乙随后将这封信收进背包；不呈现后续'],
                 'character_knows':['乙仅在查看封口后确认 PROP_SEAL_INTACT'],
                 'reveal':'交信→封口完整可见→收进背包，顺序与 ScriptIR 一致',
                 'viewpoint':'客观观察三项来源动作，不暗示信件内容或人物动机'},
    'start_state':legacy_states(sampled_state(0)),
    'end_state':legacy_states(sampled_state(12000)),
    'phases':[],
    'composition':{'rule':'固定双人中近景；画面左甲、右乙，信与背包开口在手部行动区域。',
                   'attention_order':['CHAR_JIA','PROP_LETTER','CHAR_YI','PROP_BACKPACK'],
                   'negative_space':'两人手部之间及乙背包开口周围留出可读空隙。',
                   'depth_layers':'甲乙和信构成近中景；雨夜环境只作不指认地点的后景或声音线索。',
                   'safe_area':[0.02,0.02,0.96,0.96],
                   'subjects':[
                       {'entity_id':'CHAR_JIA','box':[0.04,0.10,0.36,0.82],'visible_parts':['face','eyes','hands','body']},
                       {'entity_id':'CHAR_YI','box':[0.56,0.10,0.40,0.82],'visible_parts':['face','eyes','hands','body']},
                       {'entity_id':'PROP_LETTER','box':[0.40,0.42,0.16,0.12],'visible_parts':['body','prop']},
                       {'entity_id':'PROP_BACKPACK','box':[0.67,0.62,0.19,0.28],'visible_parts':['body','prop']} ]},
    'camera':{'movement':'locked','motivation':'保持交接、封口和背包开口在连续时空内可读。',
              'start_m':[0,-2.8,1.2],'end_m':[0,-2.8,1.2],'look_at_m':[0,0,1.0],
              'roll_deg':0,'focal_mm':45,
              'framing_start':'双人中近景，手与信同框，乙背包开口在画面下部',
              'framing_end':'双人中近景，手与信同框，乙背包开口在画面下部',
              'path':'全程固定机位，无推拉摇移；人物和信在画内移动。',
              'speed':'机位全程静止。','focus':'交接手部；验封时封口；收存时背包开口，这些为观看重点而非自动转焦。',
              'precision':'qualitative','axis_side':'negative','axis_transition':None},
    'performance':[],'dialogue':[],
    'sound':{'ambience':'雨夜环境声作为天气线索；不指定具体地点或室内外声学。',
             'cue':'只保留与交接、确认和收存相符的自然动作声；不加对白。',
             'sync':'雨声贯穿；动作声须跟对应接触时刻核对，后期尚未执行。','silence':False},
    'lighting':{'source':'具体实景光源由美术后续确定；此处只记录夜间可读性意图。',
                'direction':'保留手部、封口与背包开口可读；不锁定实际灯位。',
                'quality':'夜间柔和可读，不以黑暗掩盖封口。',
                'color_purpose':'明确夜间氛围；不推定特定地点或色彩来源。'},
    'must_show':[{'entity_id':'PROP_LETTER','part':'prop','reason':'交接与验封必须识别为同一封未拆信'},
                 {'entity_id':'CHAR_YI','part':'hands','reason':'确认与收存的先后需可见'},
                 {'entity_id':'PROP_BACKPACK','part':'prop','reason':'信进入背包的结果可见'}],
    'references':[],'technique_ids':['locked_observation','contact_action'],
    'continuity':{'from_shot':None,'match_entities':[],'transition':'continuous',
                  'reason':'单镜连续呈现三事件，不用省略隐藏交接。',
                  'invariants':['甲乙身份不变','只有一封未拆信','背包始终是乙收存用的同一个道具','事件顺序不变']},
    'acceptance_ids':['Q_RAIN','Q_LETTER','Q_ORDER','Q_FINAL'],
}

timeline={
    'schema':'detail-timeline/1.2',
    'coordinate_system':'x-right,y-up,z-depth; screen and anatomical directions are separate',
    'action_groups':[
        {'id':'GROUP_HANDOFF','parent_id':None,'purpose':'交接一封未拆信并明确控制权从甲至乙',
         'beat_ids':['BEAT_HANDOFF'],'origin':source_origin},
        {'id':'GROUP_CONFIRM','parent_id':None,'purpose':'乙在收存前确认同一封信封口完整',
         'beat_ids':['BEAT_CONFIRM'],'origin':source_origin},
        {'id':'GROUP_STOW','parent_id':None,'purpose':'乙把已确认的同一封信收进背包',
         'beat_ids':['BEAT_STOW'],'origin':source_origin}],
    'actions':actions,
    'performances':[
        perf('PERF_JIA',500,4000,'CHAR_JIA',['ACT_EXTEND','ACT_RELEASE'],
             '甲交信并在乙握稳后松开。','开始交信','乙接住同一封信。','甲手离开信。',
             '看交接位置，不附加心理暗示。','右指夹纸边前送；确认乙握稳后张开并回收。',
             '双足支撑，前臂行动，身体不跨越对方。',['hands','body'],'body'),
        perf('PERF_YI_RECEIVE',2000,4000,'CHAR_YI',['ACT_GRIP'],
             '乙右手接同一封信。','信到达交接位置','甲松手，乙控制信。','乙持信停稳。',
             '先看信与甲的手部接点。','右指捏住未拆信的另一侧纸边，不碰开封口。',
             '站姿稳定，右前臂小幅前伸。',['hands','body'],'body'),
        perf('PERF_YI_SEAL',4500,7500,'CHAR_YI',['ACT_CONFIRM_SEAL'],
             '乙查看封口。','乙已持有信','封口完整可读。','检查完成才进入收存。',
             '视线落到同一封信的封口并停留。','右手使封口面朝乙，不揭开。',
             '信保持在视线和镜头可读范围。',['eyes','hands'],'detail'),
        perf('PERF_YI_STOW',8000,11000,'CHAR_YI',['ACT_STOW'],
             '乙将同一封信收入背包。','已确认封口完整','信进入背包。','乙松手；故事停在收存结果。',
             '从封口转向背包开口。','右手持信入包；左手保持开口，信不换成其他物件。',
             '双足承重，手臂移动；背包留在乙身边。',['hands','body'],'body')],
    'camera_operations':[
        {'id':'CAM_LOCKED','start_ms':0,'end_ms':12000,'shot_ids':['S1'],'origin':design_origin,
         'operation':'locked','start_position':'双人前方同侧示意机位 [0,-2.8,1.2] 米',
         'end_position':'双人前方同侧示意机位 [0,-2.8,1.2] 米',
         'start_framing':'固定双人中近景，信和背包开口在画内',
         'end_framing':'固定双人中近景，信和背包开口在画内',
         'height':'约胸腹高度；数值仅作预演意图','orientation':'面对两人交接轴；无 roll',
         'path':'全程无机位路径；人物和道具在固定画面内行动。',
         'speed':'固定，不推进、不横移、不摇摄、不变焦。',
         'look_at':'两人手部之间，验封与入包靠人物动作进入观看重点。',
         'focus':'保证封口与收存动作可读；不主张精确转焦控制。',
         'axis':'甲至乙为动作轴；机位始终在同一负侧。',
         'sync_action_ids':[], 'precision':'intent'}],
    'audio_events':[
        {'id':'AUD_RAIN','start_ms':0,'end_ms':12000,'shot_ids':['S1'],'origin':source_origin,
         'kind':'ambience','speaker_id':None,'text':'持续雨声，提示雨夜；不暗示具体地点。',
         'placement':'environment','lip_sync':False,'route':'post',
         'delivery':'环境底声；实际场景和声场待后期确定。',
         'mix':'不盖过手部接触与封口检视的可读性。','overlap_reason':None,
         'source_utterance_id':None,'sync':None,'phrases':[]}],
    'state_samples':[{'id':f'STATE_{at}','shot_id':'S1','at_ms':at,
                      'entities':sampled_state(at),'origin':design_origin}
                     for at in (0,2500,4000,7500,10500,12000)],
    'visibility':[], 'segments':[], 'source_time_maps':[], 'extensions':[],
    'semantic_review':{'status':'PENDING','reviewer':None,'input_sha256':None,'findings':[]},
    'spatial_nodes':[node('N_JIA','CHAR_JIA','entity','甲'),node('N_YI','CHAR_YI','entity','乙'),
                     node('N_LETTER','PROP_LETTER','entity','同一封信'),
                     node('N_BACKPACK','PROP_BACKPACK','entity','乙的背包'),
                     node('N_ENV','ENV_RAIN_NIGHT','entity','雨夜环境'),
                     node('N_CAMERA',None,'camera','固定机位')],
    'motion_tracks':[
        track('TRACK_JIA','N_JIA',[],[key(0,[-0.65,0,0],'hold','甲站位的示意地面投影'),
                                   key(12000,[-0.65,0,0],'none','甲整体位置保持；右臂另按动作执行')],
              '甲整体站位不移动；手臂独立行动。','无整体位移。'),
        track('TRACK_YI','N_YI',[],[key(0,[0.65,0,0],'hold','乙站位的示意地面投影'),
                                 key(12000,[0.65,0,0],'none','乙整体位置保持；手臂另按动作执行')],
              '乙整体站位不移动；手臂独立行动。','无整体位移。'),
        track('TRACK_LETTER','N_LETTER',['ACT_EXTEND','ACT_GRIP','ACT_RELEASE','ACT_CONFIRM_SEAL','ACT_STOW'],[
            key(0,[-0.2,1.1,0],'hold','同一封信由甲右手持有'),
            key(500,[-0.2,1.1,0],'linear','甲开始前送'),
            key(1800,[0,1.1,0],'hold','信到达两人之间'),
            key(2500,[0,1.1,0],'hold','双方短暂接触，甲仍控制'),
            key(2800,[0,1.1,0],'linear','乙握稳后甲准备释放'),
            key(3500,[0.2,1.1,0],'hold','信转至乙右手控制'),
            key(7500,[0.2,1.1,0],'hold','封口检查期间停留在乙视线内'),
            key(8000,[0.2,1.1,0],'linear','乙开始向背包开口移动'),
            key(10500,[0.7,0.75,0],'hold','同一封信进入背包'),
            key(12000,[0.7,0.75,0],'none','信保持在背包内，未拆')],
              '甲手→双手交接→乙手停顿验封→乙手送入背包；示意坐标不等于实际执行结果。',
              '交接与入包平稳，封口确认期间停留。'),
        track('TRACK_BACKPACK','N_BACKPACK',[],[key(0,[0.7,0.75,0],'hold','乙携带背包，开口在手可及范围'),
                                             key(12000,[0.7,0.75,0],'none','背包整体位置保持')],
              '背包整体保持乙身侧；开口由乙左手短暂保持。','无整体位移。')],
    'spatial_relations':[
        {'id':'REL_JIA_LEFT_YI','subject_node_id':'N_JIA','object_node_id':'N_YI',
         'predicate':'world_left_of','frame':'world',
         'scope':{'kind':'interval','start_ms':0,'end_ms':12000},'shot_ids':['S1'],
         'criterion':'甲的示意世界 X 坐标始终小于乙；不从画面坐标反推。',
         'distance_m':None,'attachment':None,'origin':design_origin}],
    'composition_tracks':[
        composition('COMP_HANDOFF',0,4000,[0.40,0.42,0.16,0.12],['body','seal'],'body','一封信交接时两只右手可见'),
        composition('COMP_CONFIRM',4000,8000,[0.49,0.39,0.18,0.15],['body','seal'],'detail','封口面朝乙且足够清楚供观众确认'),
        composition('COMP_STOW',8000,10500,[0.58,0.52,0.15,0.13],['body','seal'],'detail','同一封信从乙手向背包开口移动'),
        composition('COMP_END',10500,12000,[0.69,0.70,0.10,0.09],[],'body','信已经入包，由包体遮住；画面不呈现后续')],
}

checks=[
    {'id':'Q_RAIN','gate':'G3','scope':'S1','method':'frame_review','predicate':'实际镜头可辨雨夜环境，不指认原文未给地点。',
     'evidence_required':'真实 Take、哈希、时间码及视听观察；当前 NOT_RUN','owner':'media_reviewer','blocking':True},
    {'id':'Q_LETTER','gate':'G3','scope':'S1','method':'frame_review','predicate':'同一封未拆信在交接、封口确认和入包三段保持身份；接触和控制权切换可见。',
     'evidence_required':'真实 Take、哈希、交接/验封/入包关键帧观察；当前 NOT_RUN','owner':'media_reviewer','blocking':True},
    {'id':'Q_ORDER','gate':'G3','scope':'S1','method':'frame_review','predicate':'乙完成封口确认后才开始把同一封信收入背包；没有对白、人物动机或新增事件。',
     'evidence_required':'真实 Take、哈希、各动作时间码及审片观察；当前 NOT_RUN','owner':'media_reviewer','blocking':True},
    {'id':'Q_FINAL','gate':'G4','scope':'project','method':'playback','predicate':'完整播放后观众只得到雨夜交信、验封、收存三项信息，收存即结束。',
     'evidence_required':'最终文件与完整播放记录；当前 NOT_RUN','owner':'final_reviewer','blocking':True},
]

def clause(cid, requirement, paths, qids):
    return {'id':cid,'requirement':requirement,'priority':'hard','source_refs':FACT,
            'paths':paths,'check_ids':qids,'change_policy':'explicit_revision',
            'allowed_channels':['natural_language','post','review']}

contract={
    'id':'CONTRACT_LETTER_DIRECTOR','version':1,
    'scope':'仅把已接受 Canon/ScriptIR 的雨夜交信、验封、收存落实为可审计视听动作；未给内容保持未指定。',
    'clauses':[
        clause('D_RAIN','雨夜明确保留；不补具体地点或室内外。',
               ['/scenes/0/space','/shots/0/sound/ambience','/shots/0/lighting/color_purpose'],['Q_RAIN','Q_FINAL']),
        clause('D_SINGLE_LETTER','甲交给乙的是一封未拆信，乙验封和入包都使用同一对象。',
               ['/entities/2','/timeline/actions/0','/timeline/actions/1','/timeline/actions/2','/timeline/actions/3','/timeline/actions/4','/shots/0/end_state/2'],['Q_LETTER','Q_FINAL']),
        clause('D_ACTION_ORDER','交信、确认封口、收进背包必须依次发生。',
               ['/beats','/timeline/actions','/shots/0/narrative'],['Q_ORDER','Q_FINAL']),
        clause('D_ENDING','乙将同一封信收入背包即为来源终点，不延伸后续。',
               ['/shots/0/narrative/audience_after/2','/timeline/actions/4/settle','/shots/0/end_state/2'],['Q_ORDER','Q_FINAL']),
        clause('D_EVENTS','三项 ScriptIR 事件各有对应动作与可见反馈，不新增故事事件。',
               ['/beats','/timeline/actions'],['Q_LETTER','Q_ORDER']),
        clause('D_REVEAL_ORDER','观众先见交接，再见封口确认，最后见收入背包。',
               ['/beats','/timeline/actions','/shots/0/narrative/audience_after'],['Q_ORDER','Q_FINAL'])],
    'checks':checks,
    'acceptance':{'rule':'all_blocking_checks_pass','waivers':[]},
    'execution':{'mode':'plan_only','authorization_ref':None,'budget_amount':0,'currency':'CNY',
                 'max_attempts_per_job':1,'stop_conditions':['仅交付文字候选；实际生成需另有任务','G3/G4 未跑前不得宣称媒体通过']},
    'deliverables':['原生 DirectorIR 1.2','编剧交接逐项映射','静态检查证据；真实媒体 QA 待执行']}

ir={
    'schema_version':'1.2','project_id':'LETTER_DEMO','revision':2,'canon_ref':str(CANON),
    'sources':sources,
    'intent':{'task':'narrative','goal':'让观众看清同一封未拆信如何从甲到乙，乙如何先确认封口再收入背包。',
              'tags':['雨夜','动作连续','同一道具'],'style_request':None,'forbidden_techniques':[]},
    'format':{'fps':24,'width':1280,'height':720,'total_frames':288},
    'entities':entities,'assets':[],
    'scenes':[{'id':'SC_RAIN_NIGHT','location_id':'ENV_RAIN_NIGHT',
               'space':'雨夜；具体地点和室内外未指定。甲乙处于可交接距离，乙的背包在其手可及处；站位与道具高度只是导演预演设计。',
               'coordinate_system':'right-handed:X-right,Y-depth,Z-up;meters',
               'axis_start_m':[-0.65,0,0],'axis_end_m':[0.65,0,0],'style_id':'observational'}],
    'beats':beats,'shots':[shot],'contract':contract,'timeline':timeline}

ir['timeline']['semantic_review']={
    'status':'PASS','reviewer':'/root/host_bridge/v6_1ca6ab4732989bfd27b839b0 / current-agent source-bound review',
    'input_sha256':detail.content_hash(ir),
    'findings':[
        '与冻结 Canon、已接受 ScriptIR 逐项对读：只保留雨夜、甲交同一封未拆信、乙确认封口完整、乙随后收入背包。',
        '单镜、12 秒、手别、站位、示意坐标和摄影机属于导演设计；不把它们写成来源事实或实拍测量。',
        '没有新增人物、关系、动机、信件内容、对白、开封行为或收存后的剧情；场地与室内外仍交给美术确定。',
        '关键状态样本覆盖双方握持、乙取得控制、验封完成和信入包；甲乙的姿态随控制权和接触变化，不再保留已过时的持信与待接文字。',
        'G3/G4 真实媒体检查仍 NOT_RUN。']}

write(OUT/'director-ir.json',ir)

handoff=json.loads(HANDOFF.read_text(encoding='utf-8'))
required=handoff['requirements']
checks_by_id={
    'screenplay:REQ_RAIN_NIGHT':('D_RAIN',[{'path':'/scenes/0/space','op':'contains','value':'雨夜；具体地点和室内外未指定'}],
        '场景明确保留雨夜并保持地点、内外未定；声音与夜间可读性见同一硬条款。'),
    'screenplay:REQ_SINGLE_LETTER':('D_SINGLE_LETTER',[{'path':'/entities/2/id','op':'equals','value':'PROP_LETTER'},
        {'path':'/timeline/actions/3/operation','op':'contains','value':'封口完整'},
        {'path':'/timeline/actions/4/operation','op':'contains','value':'同一封信'}],
        '稳定道具 ID 贯穿交接、验封和入包，动作只处理这封未拆信。'),
    'screenplay:REQ_ACTION_ORDER':('D_ACTION_ORDER',[{'path':'/timeline/actions/2/end_ms','op':'equals','value':4000},
        {'path':'/timeline/actions/3/start_ms','op':'equals','value':4500},
        {'path':'/timeline/actions/4/start_ms','op':'equals','value':8000}],
        '控制权交接完成后才验封，验封动作结束后才启动收存；逐项时间和依赖均可查。'),
    'screenplay:NARRATIVE_ending':('D_ENDING',[{'path':'/shots/0/narrative/audience_after/2','op':'equals',
        'value':'乙随后将这封信收进背包；不呈现后续'},
        {'path':'/timeline/actions/4/settle','op':'contains','value':'不呈现后续'}],
        '画面以同一封信收存完成结束，未把来源未写的后续当作剧情。'),
    'screenplay:NARRATIVE_events':('D_EVENTS',[{'path':'/beats/0/id','op':'equals','value':'BEAT_HANDOFF'},
        {'path':'/beats/1/id','op':'equals','value':'BEAT_CONFIRM'},
        {'path':'/beats/2/id','op':'equals','value':'BEAT_STOW'},
        {'path':'/timeline/actions/3/semantic_id','op':'equals','value':'EVT_SEAL_CHECK'}],
        '三事件有各自节拍；交接展开为接触与释放的物理子动作，不形成新剧情事件。'),
    'screenplay:NARRATIVE_reveal_order':('D_REVEAL_ORDER',[{'path':'/shots/0/narrative/audience_after','op':'equals',
        'value':['甲交给乙同一封未拆信','乙确认该信封口完整','乙随后将这封信收进背包；不呈现后续']},
        {'path':'/timeline/actions/4/depends_on/0/action_id','op':'equals','value':'ACT_CONFIRM_SEAL'}],
        '观看顺序与 ScriptIR reveal_order 一致；收存依赖封口确认。'),
}
stamp={'screenplay_sha256':handoff['content_sha256'],
       'director_sha256':screenplay.content_hash(ir),
       'reviewer':'/root/host_bridge/v6_1ca6ab4732989bfd27b839b0 / current-agent screenplay mapping review',
       'findings':['逐项核对六条冻结编剧要求的 ID、源指纹与原生 DirectorIR 字段。',
                   '雨夜、唯一未拆信、交接→验封→收存、结尾边界均落入 hard clause 与目标断言。',
                   '导演新增手别、站位、连续单镜和时长是视听设计；未改编剧因果、知识、对白或结果。',
                   'batch 2 修正交接、验封、入包各检查点的甲乙姿态，镜头终态与信在背包内一致。']}
rows=[]
for req in required:
    clause_id, target_checks, reason=checks_by_id[req['id']]
    rows.append({'requirement_id':req['id'],'source_fingerprint':req['source_fingerprint'],
                 'target_clause':clause_id,'target_checks':target_checks,'reason':reason})
mapping={'schema':'screenplay-director-map/1.0',**stamp,'mappings':rows}
write(OUT/'screenplay-map.json',mapping)

assert detail.content_hash(ir)==ir['timeline']['semantic_review']['input_sha256']
assert not screenplay.validate_mapping(ir,required,mapping,handoff['content_sha256'])
print(json.dumps({'director_ir':str(OUT/'director-ir.json'),
                  'director_sha256':sha256((OUT/'director-ir.json').read_bytes()).hexdigest(),
                  'screenplay_map':str(OUT/'screenplay-map.json'),
                  'semantic_hash':stamp['director_sha256']},ensure_ascii=False))
