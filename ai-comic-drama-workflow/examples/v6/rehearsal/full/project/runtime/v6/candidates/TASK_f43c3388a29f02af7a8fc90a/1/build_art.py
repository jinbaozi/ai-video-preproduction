import json
from pathlib import Path

ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
OUT = ROOT / 'runtime/v6/candidates/TASK_f43c3388a29f02af7a8fc90a/1'
TASK = json.loads((ROOT/'runtime/tasks/TASK_f43c3388a29f02af7a8fc90a.json').read_text())
CANON = TASK['inputs'][1]['uri']
DIRECTOR = TASK['inputs'][0]['uri']
S = ['S_HANDOFF', 'S_SEAL', 'S_STOW']

def asset(aid, kind, name, design, locks, materials, initial, refs, entity=None, origin='existing'):
    return dict(id=aid, entity_id=aid if entity is None and origin=='existing' else entity,
        name=name, kind=kind, origin=origin, source_refs=refs, design=design,
        identity_locks=locks, material_ids=materials, initial_state=initial,
        state_rules=[], graphic_text=None)

def ref(aid, role, inherit, exclude):
    return dict(id='PLAN_'+aid, asset_id=aid, role=role, file=None, sha256=None,
        status='planned', inherit=inherit, exclude=exclude,
        rights='尚未制作或登记图像；实际文件、字节哈希和使用权待宿主核验，当前仅为文字参考计划。',
        source_refs=['DESIGN_ART'])

def shot(sid, idx, visible, focal, bg, sep, space, occ, support):
    return dict(id=sid, director_pointer='/shots/'+str(idx),
        source_refs=['CANON','DIRECTOR','DESIGN_ART'], visible_assets=visible,
        required_references=[], composition_support=dict(focal_asset=focal,background=bg,
        separation=sep,negative_space=space,occlusion=occ),
        performance_support=support,relative_relations=[])

def perf(eid, parts, wardrobe, bg):
    return dict(entity_id=eid,required_parts=parts,wardrobe_makeup=wardrobe,background=bg)

def check(cid,gate,scope,method,predicate,evidence,owner):
    return dict(id=cid,gate=gate,scope=scope,method=method,predicate=predicate,
        evidence_required=evidence,owner=owner,blocking=True)

def clause(cid, requirement, source_refs, paths, shot_ids, check_ids, channel='prompt'):
    return dict(id=cid,requirement=requirement,priority='hard',source_refs=source_refs,
        paths=paths,shot_ids=shot_ids,check_ids=check_ids,change_policy='explicit_revision',
        execution=dict(channel=channel,
            instruction='按对应ArtIR字段制作美术交接；由宿主与冻结DirectorIR合并并对实际画面核验，不改镜头、表演、台词或事件时序。',
            reference_ids=[]))

art = dict(
    schema_version='1.0',project_id='LETTER_FULL_DEMO',revision=1,
    canon=dict(uri='/private/tmp/ai-video-v6-full-demo/project/runtime/v6/candidates/TASK_5ae2734678bb041b76474d34/1/canon.json',revision='1'),
    director=dict(uri=DIRECTOR,sha256=TASK['inputs'][0]['sha256'],project_id='LETTER_FULL_DEMO',revision=2),
    sources=[
        dict(id='CANON',kind='canon',uri=CANON,locator='/content,/entities,/event_order,/source_requirements,/unspecified',
             claim='源事实只有雨夜、甲交一封未拆的信给乙、乙验封后将同一封信收进背包；人物外观、地点和室内外未给出。',verification='read'),
        dict(id='DIRECTOR',kind='director',uri=DIRECTOR,locator='/scenes/0,/shots/0-2,/timeline/actions,/timeline/state_samples',
             claim='冻结三镜、动作时点和终态；甲乙交接、验封、入包的机位与行为只读继承。',verification='read'),
        dict(id='DESIGN_ART',kind='design',uri='local:LETTER_FULL_DEMO/art/SCENE_HANDOFF/revision-1',locator='/world,/assets,/set,/shots,/references',
             claim='色材、无标识衣装、平整承托面、低干扰背景与参考计划均为本次美术设计提案，不是原文事实、已批准角色身份或已存在图像。',verification='inference')
    ],
    brief=dict(world_mode='contemporary',medium='live_action',tags=['观察','日常','雨夜'],forbidden_styles=[],locked_style='contemporary_observation',secondary=None),
    world=dict(
        thesis='在地点和室内外仍开放的雨夜，以低干扰色材让交接的双手、同一封完整封口以及入包终态可读。',
        era='原文未指定年代；当代观察语法仅为本次视觉设计提案，不据此补写人物身世或剧情。',
        region='原文未指定地域及具体地点；不加入可辨识城市、建筑、招牌或年代地标。',
        social_logic='不从衣装、信或背包推断二人关系、动机或信件内容；视觉物件仅服务已锁定动作。',
        shape_language='单一平整承托面、二人相向站立的通行净空和乙可触及的背包位置；不放妨碍手与包口的陈设。',
        palette=[
            dict(id='BG_NIGHT',color='低饱和蓝灰',role='雨夜环境后退，提供人物与动作的低频背景'),
            dict(id='WARDROBE_DARK',color='深石墨灰与深蓝灰',role='两人服装低对比区分，手和信不被暗纹吞没'),
            dict(id='LETTER_NEUTRAL',color='中性偏暖纸色',role='未拆信及封口与深色袖口、背包口分离')
        ],
        materials=[
            dict(id='MAT_CLOTH',base='无标识深色织物',craft='平织与收口袖型',finish='低反光哑面',wear='无指定旧化、品牌与身份标记；雨夜湿痕仅在实际可见且不遮手时使用'),
            dict(id='MAT_PAPER',base='普通纸质信封',craft='折叠封口保持闭合',finish='中性哑面纸纹',wear='无拆封、破口、涂写或可读文字；三镜为同一封，封口始终完整'),
            dict(id='MAT_BAG',base='深色无标识织物',craft='有可开启包口与足够容纳一封信的内腔',finish='低反光哑面',wear='不添加来源不明的贴章、文字或明显损坏；包口形制三镜不变'),
            dict(id='MAT_GROUND',base='中性稳定承托面',craft='平整可站立',finish='低反光',wear='无可识别场所线索；雨夜反光不淹没接触证据')
        ],
        color_script=[
            dict(shot_ids=['S_HANDOFF'],palette_ids=['BG_NIGHT','WARDROBE_DARK','LETTER_NEUTRAL'],change_reason='甲乙双手与同一封信的接触需要从雨夜背景分离'),
            dict(shot_ids=['S_SEAL'],palette_ids=['BG_NIGHT','WARDROBE_DARK','LETTER_NEUTRAL'],change_reason='乙的眼神、右手与完整封口同框可辨，不暗示拆封'),
            dict(shot_ids=['S_STOW'],palette_ids=['BG_NIGHT','WARDROBE_DARK','LETTER_NEUTRAL'],change_reason='前段辨认信进入包口；8500毫秒后信在包内不再外露，终帧由乙手与背包口承载结果')
        ]
    ),
    assets=[
        asset('CHAR_JIA','character','甲','Canon只给代称和交信行为。美术提案为无标识深石墨灰哑面外层、袖口收紧，使右手递信接触可见；脸、年龄、性别和职业未由本卡决定。',
              ['同一人物与同一服装外观跨三镜连续；脸部身份仍由Canon或后续已核参考锁定','右手及袖口不遮住交接的信封'],['MAT_CLOTH'],{'wardrobe':'深石墨灰无标识外层（设计提案）'},['CANON','DIRECTOR','DESIGN_ART']),
        asset('CHAR_YI','character','乙','Canon只给代称、验封与入包行为。美术提案为无标识深蓝灰哑面外层、无遮挡眼部与可活动右袖；脸、年龄、性别和职业未由本卡决定。',
              ['同一人物与同一服装外观跨三镜连续；脸部身份仍由Canon或后续已核参考锁定','眼部、右手与包口接触面不被衣袖或头饰遮挡'],['MAT_CLOTH'],{'wardrobe':'深蓝灰无标识外层（设计提案）'},['CANON','DIRECTOR','DESIGN_ART']),
        asset('PROP_LETTER','prop','同一封未拆的信','同一封纸质信封；外观提案为中性偏暖哑面、无可读文字的闭合折叠封口。甲右手交给乙右手，乙仅查看完整封口，随后放入背包；具体信件内容与来历未定。',
              ['同一实体 PROP_LETTER 跨交接、验封、入包三镜连续','封口从头至尾完整且未拆；不露出内页','8500毫秒后完全在背包内，9000毫秒终帧不外露'],['MAT_PAPER'],{'condition':'同一封未拆、封口完整'},['CANON','DIRECTOR','DESIGN_ART']),
        asset('PROP_BACKPACK','prop','背包','乙收信所用背包；美术提案为深色无标识软质织物包，包口能让同一封信顺利进入并由内腔承托，具体背法与品牌不定义。',
              ['同一实体 PROP_BACKPACK 外观与包口位置连续','包口可被乙右手触及；信完整入包后留在内腔且不外露'],['MAT_BAG'],{'condition':'待收纳同一封信'},['CANON','DIRECTOR','DESIGN_ART']),
        asset('ENV_RAIN_NIGHT','set','雨夜环境','雨夜为源事实；本次只设计低频雨幕、蓝灰夜色和供两人稳定站立的中性平整承托面，具体地点、建筑、地理区域及室内外仍开放。',
              ['三个镜头持续为同一雨夜','不得从背景推断未给出的具体地点或室内外状态'],['MAT_GROUND'],{'condition':'雨夜持续'},['CANON','DIRECTOR','DESIGN_ART']),
    ],
    set=dict(scene_id='SCENE_HANDOFF',location_entity_id='ENV_RAIN_NIGHT',coordinate_system='right-handed:X-right,Y-depth,Z-up;meters',
             origin='以冻结DirectorIR的两人交接中点在承托面上的投影为设计原点；以下米值仅为美术搭建范围，不是原文测量。',
             bounds=dict(min_m=[-2,-2,0],max_m=[2,2,2.5]),
             layout=[dict(id='GROUND_1',asset_id='ENV_RAIN_NIGHT',position_m=[0,0,0],size_m=[4,4,0.02],yaw_deg=0,
                          role='甲乙站立与背包稳定承托的中性连续面；不确定具体地点')],
             counts=[dict(asset_id='ENV_RAIN_NIGHT',count=1)],functional_zones=[],practical_lights=[],
             atmosphere='雨夜持续，背景雨幕低频且不遮挡手、封口与包口；具体室内外和可辨建筑不定。光源以同一方位的画外环境漫反射为待实现设计提案，三镜保持手与封口可读。'),
    events=[],
    shots=[
        shot('S_HANDOFF',0,['CHAR_JIA','CHAR_YI','PROP_LETTER','ENV_RAIN_NIGHT'],'PROP_LETTER',
             '雨夜蓝灰背景低频，不加地标或高亮陈设；延续Director的中景与交接轴。',
             '中性纸色与深色袖口分离，交接时同一封未拆信和两人的手均可辨。',
             '双手相遇与信的运动路径留净空，不摆放新道具；本镜不提前展示验封或入包结果。',
             '按Director /timeline/actions/0 的 EVT_HANDOFF：乙右手接稳后甲右手松开；不以袖口、雨幕或布景遮挡接触和控制权转移。',
             [perf('CHAR_JIA',['hands'],'深石墨灰袖口收紧，露出交信右手；不设计未给出的面容。','手与信后方低纹理'),
              perf('CHAR_YI',['hands'],'深蓝灰右袖不吞手，接信处可见。','接手位置后方低纹理')]),
        shot('S_SEAL',1,['CHAR_YI','PROP_LETTER','ENV_RAIN_NIGHT'],'PROP_LETTER',
             '乙脸后无高频反光；封口完整可视，不增加可读文字或拆开的信纸。',
             '中性纸封口与深色袖口分离，乙眼神和持信右手同时清楚。',
             '依Director近景留出乙视线到封口的净空；不提前显示入包。',
             '按Director /timeline/actions/1 的 EVT_SEAL_CHECK：乙只微调同一封未拆信查看完整封口；衣领、发丝与手指不遮住眼神或封口，也不掀开封口。',
             [perf('CHAR_YI',['face','eyes','hands'],'眼部无遮挡，右袖露出握信手；脸部身份未由美术擅定。','脸和封口背后低频、低反光')]),
        shot('S_STOW',2,['CHAR_YI','PROP_LETTER','PROP_BACKPACK','ENV_RAIN_NIGHT'],'PROP_BACKPACK',
             '前段在乙右手、同一封信和包口后保持低频雨夜背景；8500毫秒后信完全在背包内，9000毫秒终帧不外露。',
             '深色包口边缘与乙手分离，入包前信的中性纸色可辨；入包后不让纸色继续作为前景。',
             '包口前留右手送入和退出的净空；收存结果只在验封之后出现。',
             '按Director /timeline/actions/2 的 EVT_STOW：乙右手把信穿过包口并由包内承托；8500毫秒后信在包内不再可见，终帧只见乙手退出与背包口，无外露信件。',
             [perf('CHAR_YI',['hands'],'右袖不遮住包口接触，手退出路径清楚。','乙手与包口后方低反光')])
    ],
    references=[
        ref('CHAR_JIA','identity',['同一人物外观与灰色衣装的连续性'],['来源未给出的年龄、性别、关系或场所背景']),
        ref('CHAR_YI','identity',['同一人物外观与深蓝灰衣装的连续性'],['来源未给出的年龄、性别、关系或场所背景']),
        ref('PROP_LETTER','prop',['同一封未拆信及完整封口'],['信件内容、可读文字、拆封状态']),
        ref('PROP_BACKPACK','prop',['可触及包口与可容信内腔'],['品牌、归属、未给出的贴章或文字']),
        ref('ENV_RAIN_NIGHT','scene',['雨夜低频背景和跨镜环境连续性'],['具体地点、可辨城市、建筑及室内外断言'])
    ]
)
art['contract']=dict(
    id='ART_SCENE_HANDOFF',version=1,scope='SCENE_HANDOFF 三镜场景的静态美术合同；实际媒体未生成或审看',
    deliverables=['ArtIR','场景与资产设计','逐镜美术支持','计划参考与验收条件'],
    clauses=[
        clause('ART_WORLD','保持雨夜且不确立具体地点、年代、室内外或人物关系。',['CANON','DIRECTOR','DESIGN_ART'],['/world','/set','/assets/4'],[],['G0INPUT','G1DESIGN','G4FINAL']),
        clause('ART_CONTINUITY','同一甲乙、同一未拆信和同一背包的外观跨镜连续；信封始终完整，人物脸部身份未由此美术提案擅定。',['CANON','DIRECTOR','DESIGN_ART'],['/assets/0','/assets/1','/assets/2','/assets/3'],[],['G1DESIGN','G4FINAL']),
        clause('ART_HANDOFF','按冻结导演第1镜交接，同一封信从甲右手到乙右手，双手及接触清楚。',['CANON','DIRECTOR'],['/shots/0','/assets/0','/assets/1','/assets/2','/assets/4'],['S_HANDOFF'],['G3_HANDOFF']),
        clause('ART_SEAL','按冻结导演第2镜验封，乙眼神、右手和完整封口可辨，不拆信。',['CANON','DIRECTOR'],['/shots/1','/assets/1','/assets/2','/assets/4'],['S_SEAL'],['G3_SEAL']),
        clause('ART_STOW','按冻结导演第3镜，验封后信进入背包；8500毫秒后完全在包内，终帧无外露信件。',['CANON','DIRECTOR'],['/shots/2','/assets/1','/assets/2','/assets/3','/assets/4'],['S_STOW'],['G3_STOW']),
        clause('ART_MAPPING','逐镜美术支持只约束材质、环境、服化与可读性；动作、机位、信息顺序沿用冻结DirectorIR。',['DIRECTOR','DESIGN_ART'],['/shots','/director','/references'],[],['G2MAP','G4FINAL'])
    ],
    checks=[
        check('G0INPUT','G0','project','static','源事实、设计补充及导演绑定哈希可分辨。','冻结Canon/Director文件与原生校验结果','art_planner'),
        check('G1DESIGN','G1','project','static','资产、场景与色材无来源不明的身份或地点断言。','ArtIR来源/锁定项审阅记录','art_director'),
        check('G2MAP','G2','project','static','各镜可见资产、导演动作和硬要求均可追踪。','ArtIR合同覆盖及V5/V6交接映射','host_reviewer'),
        check('G3_HANDOFF','G3','S_HANDOFF','frame_review','交接时双手与同一封未拆的信接触可辨，甲在乙接稳后松开。','实际镜头、哈希与具名逐帧观察','visual_reviewer'),
        check('G3_SEAL','G3','S_SEAL','frame_review','乙眼神和完整封口可辨且无拆封。','实际镜头、哈希与具名逐帧观察','visual_reviewer'),
        check('G3_STOW','G3','S_STOW','frame_review','入包过程可辨，8500毫秒后信不外露，终帧信在包内。','实际镜头、哈希与8500/9000毫秒具名观察','visual_reviewer'),
        check('G4FINAL','G4','project','playback','三镜美术连续、雨夜持续、同一信封完整且结尾入包。','最终媒体及完整具名审核记录','final_reviewer')
    ],
    execution=dict(mode='plan_only',authorization_ref=None,budget_amount=0,currency='CNY',max_attempts_per_job=2,
                   stop_conditions=['没有真实媒体和授权时只交付静态计划','真实参考、图像或视频未登记前不得声称视觉验收通过'])
)
(OUT/'art-ir.json').write_text(json.dumps(art,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
