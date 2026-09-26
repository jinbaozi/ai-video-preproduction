import json
from pathlib import Path

root = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
out = root / 'runtime/v6/candidates/TASK_0560d46ecc764c68ee9a590e/1'
canon_uri = str(root / 'runtime/v6/candidates/TASK_0e0c8a4ca94c8ffdbb7e14ae/1/canon.json')
director_uri = str(root / 'runtime/v6/candidates/TASK_b1e7ff7ce83d7a32bfa09935/3/director-ir.json')

def asset(id, kind, name, design, locks, materials, state):
    return dict(id=id, entity_id=id, name=name, kind=kind, origin='existing',
                source_refs=['CANON','DIRECTOR','ART_DESIGN'], design=design,
                identity_locks=locks, material_ids=materials, initial_state=state,
                state_rules=[], graphic_text=None)

def check(id, gate, scope, method, predicate, evidence, owner):
    return dict(id=id, gate=gate, scope=scope, method=method, predicate=predicate,
                evidence_required=evidence, owner=owner, blocking=True)

def clause(id, requirement, paths, checks, instruction, sources=None, channel='prompt'):
    return dict(id=id, requirement=requirement, priority='hard',
                source_refs=sources or ['CANON','DIRECTOR'], paths=paths, shot_ids=['S1'],
                check_ids=checks, change_policy='explicit_revision',
                execution=dict(channel=channel, instruction=instruction, reference_ids=[]))

def planned_ref(id, asset_id, role, inherit, exclude):
    return dict(id=id, asset_id=asset_id, role=role, file=None, sha256=None,
                status='planned', inherit=inherit, exclude=exclude,
                rights='尚无文件或授权观察；待宿主取得并核验真实素材', source_refs=['ART_DESIGN'])

art = {
 'schema_version':'1.0', 'project_id':'LETTER_DEMO', 'revision':1,
 'canon':{'uri':canon_uri,'revision':'1'},
 'director':{'uri':director_uri,'sha256':'262e23f487752f69bf6ec031f6e0d7851a2205df482ee5d4cf91755f0bf0c98b','project_id':'LETTER_DEMO','revision':3},
 'sources':[
  {'id':'USER','kind':'user','uri':str(root/'sources/SRC_69a71adcfaca/source.txt'),'locator':'原始一句话雨夜交信文本','claim':'雨夜；甲将一封未拆的信交给乙；乙确认封口完整后收进背包。','verification':'read'},
  {'id':'CANON','kind':'canon','uri':canon_uri,'locator':'/content /entities /event_order /source_requirements /unspecified','claim':'稳定人物、道具和场景ID；一封未拆信与三事件顺序；地点、年代、外观、室内外未定。','verification':'read'},
  {'id':'DIRECTOR','kind':'director','uri':director_uri,'locator':'/scenes/0 /shots/0 /timeline/actions /contract','claim':'固定双人中近景、世界坐标预演、手部交接与封口和背包开口可见性；导演时序与动作只读。','verification':'read'},
  {'id':'ART_DESIGN','kind':'design','uri':'design://TASK_0560d46ecc764c68ee9a590e/scene-painter-v1','locator':'本 ArtIR 的色材、简化环境、服化与道具外观建议','claim':'中性低干扰美术方案；不声明具体地点、年代、职业、关系、信件内容或已生成媒体。','verification':'inference'}
 ],
 'brief':{'world_mode':'contemporary','medium':'live_action','tags':['观察','雨夜'],
          'forbidden_styles':[],'locked_style':'contemporary_observation','secondary':None},
 'world':{
  'thesis':'以无地点标识的雨夜背景退让，让观众辨认甲乙之间同一封未拆信的交接、完整封口及入包结果。',
  'era':'年代未指定；当代观察仅为这版中性美术语法，不登记为剧情年代。',
  'region':'地点和室内外未指定；不出现可指认城市、建筑、房间或地标。',
  'social_logic':'甲乙身份、关系和交信动机未给；衣装与背包仅服务同一动作链，不暗示职业或阶层。',
  'shape_language':'只保留两人可交接的空隙、信的封口边缘和乙可触及的背包开口；后景用低频雨夜层次，不添门窗、桌椅或标志。',
  'palette':[
   {'id':'NIGHT','color':'低饱和深灰蓝','role':'无地点标识的雨夜后景，低对比但可辨雨势'},
   {'id':'PEOPLE','color':'相互可分的中性灰阶','role':'甲乙衣装与背景分离，不用色彩编码身份或情绪'},
   {'id':'LETTER','color':'中性偏浅纸色','role':'一封信及封口边缘在手部行动区可读'},
   {'id':'BAG','color':'低反光中深灰','role':'背包开口与浅色信形成明度区别'}
  ],
  'materials':[
   {'id':'MAT_CLOTH','base':'未定材质的服装面料','craft':'简洁剪裁与真实袖口','finish':'低反光、纹理频率低','wear':'不凭空添加损伤；仅保持本镜一致'},
   {'id':'MAT_PAPER','base':'纸质信件外层','craft':'连续纸面与完整封口折线','finish':'哑光中性浅色','wear':'未拆、封口完整；无可读文字、印章或破损'},
   {'id':'MAT_BAG','base':'可弯折的背包面料','craft':'开口和包腔结构可容纳同一封信','finish':'中深灰、低反光','wear':'不增加品牌、标记或无来源磨损'},
   {'id':'MAT_RAIN','base':'雨水','craft':'后景雨迹或水线层','finish':'低对比、局部可见','wear':'不预设人物、纸张或包身被雨淋湿'}
  ],
  'color_script':[{'shot_ids':['S1'],'palette_ids':['NIGHT','PEOPLE','LETTER','BAG'],
                   'change_reason':'单镜连续；夜色保持恒定，封口和入包证据靠局部明度与材质分离，不作无来源色彩转场。'}]
 },
 'assets':[
  asset('CHAR_JIA','character','甲','中性、无年代和职业标识的外观建议；袖口不遮握信的右手。',['沿用 CHAR_JIA 身份；不发明年龄、性别、关系或表情','本镜衣装外观连续；不遮甲右手与信纸边接触'],['MAT_CLOTH'],{'appearance':'unapproved_stable_design'}),
  asset('CHAR_YI','character','乙','中性、无年代和职业标识的外观建议；袖口和发丝不遮右手验封、左手在背包开口的动作。',['沿用 CHAR_YI 身份；不发明年龄、性别、关系或动机','本镜衣装连续；右手、左手、眼部按导演可见范围保持清楚'],['MAT_CLOTH'],{'appearance':'unapproved_stable_design'}),
  asset('PROP_LETTER','prop','同一封未拆信','单件哑光浅纸色信件；封口折线完整且能被乙检查，外观无字、印章或特殊来历线索。',['全程只有 PROP_LETTER 这一封信','封口在交接、确认、入包过程中保持未拆且完整','不得增加文字、印章、撕裂或信件内容；控制权和位置变化只读 DirectorIR 时间线'],['MAT_PAPER'],{'seal':'intact_unopened','identity':'single_letter'}),
  asset('PROP_BACKPACK','prop','乙的背包','乙身上的同一背包；开口能由左手撑持，包腔可容纳同一封信，开口边缘与信形成明度差。',['始终为 PROP_BACKPACK，归乙使用','不增加品牌、图案或来源未给的独特形制；收存动作以 DirectorIR 为准'],['MAT_BAG'],{'identity':'same_backpack','access':'reachable'}),
  asset('ENV_RAIN_NIGHT','set','雨夜环境','无具体地点标识的低频雨夜后景；雨的可见线索与导演雨声计划兼容，不推定室内或室外。',['雨夜事实稳定','地点、室内外、年代均未指定；不可加入门窗、街牌或地标作为事实'],['MAT_RAIN'],{'weather':'rain','time':'night'})
 ],
 'set':{
  'scene_id':'SC_RAIN_NIGHT','location_entity_id':'ENV_RAIN_NIGHT',
  'coordinate_system':'right-handed:X-right,Y-depth,Z-up;meters',
  'origin':'沿用 DirectorIR 的甲乙交接中心作为预演原点；数值只表示可留空的设计包络，不是实测场景。',
  'bounds':{'min_m':[-1.5,-0.5,0],'max_m':[1.5,0.5,2]},
  'layout':[],'counts':[],
  'functional_zones':[{'id':'HAND_BAG_CLEARANCE','min_m':[-0.45,-0.3,0.6],'max_m':[0.95,0.3,1.45],
                       'purpose':'交信、验封和乙背包开口共用的无固定陈设操作区；人物与道具轨迹以导演时间线为准。'}],
  'practical_lights':[],
  'atmosphere':'雨夜有可辨雨迹或雨层；背景不指认地点与室内外。柔和基础照度支持甲乙手部、封口及包口可读，画内灯具位置尚未定义；不把纸、衣、包自动做成湿透。'
 },
 'events':[],
 'shots':[{
  'id':'S1','director_pointer':'/shots/0','source_refs':['CANON','DIRECTOR','ART_DESIGN'],
  'visible_assets':['CHAR_JIA','CHAR_YI','PROP_LETTER','PROP_BACKPACK','ENV_RAIN_NIGHT'],
  'required_references':[],
  'composition_support':{
   'focal_asset':'PROP_LETTER',
   'background':'后景仅保留不指认地点的雨夜层次；无牌匾、门窗、桌椅或高频反光线穿过人物面部与手部。',
   'separation':'浅纸色信与甲乙手部、深色背包开口持续分离；封口完整的折线在确认段可读。',
   'negative_space':'两人之间的交接区域、乙验封手边与背包开口周围不放陈设；不改变导演固定双人中近景。',
   'occlusion':'在导演交接、封口确认、入包关键时间点，袖口、发丝、雨迹和包边不遮挡同一封信、完整封口、乙双手及包口。'
  },
  'performance_support':[
   {'entity_id':'CHAR_JIA','required_parts':['hands'],'wardrobe_makeup':'甲的右袖口避开握信纸边；不规定未给的脸、年龄或妆容。','background':'手后保留低频暗部，双手接触点不被雨迹遮挡。'},
   {'entity_id':'CHAR_YI','required_parts':['face','eyes','hands'],'wardrobe_makeup':'乙的发丝和领口不遮眼部；右袖口露出验封手势，左袖口不盖住背包开口。','background':'乙面部与包口后方维持安静层次，不靠额外物件解释心理。'}
  ],
  'relative_relations':[
   {'subject_asset':'CHAR_JIA','relation':'world_left_of','object_asset':'CHAR_YI','criterion':'沿用 DirectorIR 世界 X 轴的甲乙站位；不要由屏幕左右反推世界坐标。'},
   {'subject_asset':'PROP_BACKPACK','relation':'near','object_asset':'CHAR_YI','criterion':'乙携带同一背包且包口在左手可及范围；动态接触和信的控制权由 DirectorIR 定义。'}
  ]
 }],
 'references':[
  planned_ref('REF_JIA','CHAR_JIA','identity',['仅待核身份与当次衣装轮廓'],['背景、无关道具、未经批准的年龄职业设定']),
  planned_ref('REF_YI','CHAR_YI','identity',['仅待核身份与当次衣装轮廓'],['背景、无关道具、未经批准的关系动机']),
  planned_ref('REF_LETTER','PROP_LETTER','prop',['唯一信件外观、完整封口和纸边'],['文字、印章、信内内容、第二封信']),
  planned_ref('REF_BAG','PROP_BACKPACK','prop',['乙的同一背包及可收信的开口'],['品牌、无关物件、未经批准的持有人变更'])
 ],
 'contract':{
  'id':'ART_RAIN_NIGHT','version':1,
  'scope':'SC_RAIN_NIGHT 单镜文字美术候选；Canon 与 DirectorIR 只读。未绑定真实图片、未生成视频。',
  'deliverables':['原生 ArtIR 1.0','离线美术交接与逐镜补充','来源、条款和待审媒体 QA'],
  'clauses':[
   clause('A_RAIN','保留雨夜；不指认具体地点、年代或室内外状态。',['/world/era','/world/region','/set/atmosphere','/assets/4','/shots/0/composition_support/background'],['C_INPUT','C_DESIGN','C_MEDIA','C_FINAL'],'将雨夜与无地点标识后景作为美术补充；实际画面审雨夜可辨且未引入无来源地点。'),
   clause('A_SINGLE_LETTER','只使用 PROP_LETTER 这一封未拆且封口完整的信；交接、验封和收存保持同一外观。',['/assets/2','/world/materials/1','/shots/0/composition_support/separation'],['C_DESIGN','C_MEDIA','C_FINAL'],'给信件唯一资产ID与完整封口边缘；下游与导演时间线逐点核对身份、接触和控制权。'),
   clause('A_ORDER','交信完成后乙确认完整封口，确认后才收进同一个 PROP_BACKPACK；美术不重排导演动作。',['/assets/2/identity_locks','/assets/3','/shots/0/composition_support/occlusion'],['C_MAP','C_MEDIA','C_FINAL'],'宿主合并只读 DirectorIR /timeline/actions 的 ACT_EXTEND→ACT_GRIP→ACT_RELEASE→ACT_CONFIRM_SEAL→ACT_STOW；本美术包只保障对应证据可见。'),
   clause('A_ENDING','同一封信收进乙背包即结束；不添加信件内容、人物动机、对白或后续情节。',['/assets/2/design','/assets/3/design','/shots/0/composition_support'],['C_MEDIA','C_FINAL'],'合并导演末态后检查信入包并停在来源终点；不给画面增添故事线索。'),
   clause('A_EVENTS','三项来源事件各有可见美术证据：接触与交接、完整封口、包口及入包；不新增事件。',['/shots/0/composition_support','/shots/0/performance_support','/set/functional_zones'],['C_DESIGN','C_MAP','C_MEDIA'],'按导演三事件与五个动作节点留出无遮挡物理区域；不把美术状态说明改写为人物表演。'),
   clause('A_REVEAL','观众先见交接，再见封口完整，最后见同一封信收入包内；雨夜后景不得抢先暗示信件内容或后续。',['/shots/0/composition_support/background','/shots/0/composition_support/occlusion','/world/color_script'],['C_MAP','C_MEDIA','C_FINAL'],'逐节点观察同一封信、封口和包口；美术可读性随导演时间线检查，保持单镜夜色连续。'),
   clause('A_ASSET_LOCKS','甲乙身份与衣装、唯一信件、同一背包和雨夜后景连续；真实参考取得后才可绑定并审图。',['/shots/0','/assets/0','/assets/1','/assets/2','/assets/3','/assets/4','/references'],['C_INPUT','C_DESIGN','C_MAP','C_MEDIA'],'以稳定ID制作资产卡；参考仍为 planned，宿主补入真实文件、哈希、用途及权利后再做视觉审核。',sources=['CANON','DIRECTOR','ART_DESIGN'])
  ],
  'checks':[
   check('C_INPUT','G0','project','static','输入 Canon/DirectorIR/任务与模块哈希、稳定ID及未指定项记录一致。','本候选 source-integrity 与 module-receipt 证据。','art_planner'),
   check('C_DESIGN','G1','project','static','美术色材、空场拓扑和资产可读性不改导演镜头或原文事实。','ArtIR 字段审阅与导演只读绑定。','art_director'),
   check('C_MAP','G2','project','static','每条硬要求有源、ArtIR 字段、执行渠道和后续可观察检查。','合同覆盖表及 V5/V6 handoff 映射。','host_reviewer'),
   check('C_MEDIA','G3','S1','frame_review','实际镜头可辨雨夜、唯一未拆信、完整封口、包口与先后动作，且没有新地点或剧情。','真实 Take 文件/哈希，关键时间码及具名逐帧观察；当前 NOT_RUN。','visual_reviewer'),
   check('C_FINAL','G4','project','playback','完整播放后只得到雨夜交信、验封和收存；同一封信入包即终点。','最终文件/哈希及完整播放记录；当前 NOT_RUN。','final_reviewer')
  ],
  'execution':{'mode':'plan_only','authorization_ref':None,'budget_amount':0,'currency':'CNY','max_attempts_per_job':1,
               'stop_conditions':['仅交付文字与静态候选；生成媒体需独立执行任务','G3/G4 未完成前不声明实际画面通过']}
 }
}
(out/'art-ir.json').write_text(json.dumps(art,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
