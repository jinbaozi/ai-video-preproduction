import hashlib
import json
from pathlib import Path


ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
TASK = 'TASK_77a39e38115fc23984108917'
BASE = ROOT / 'runtime/v6/candidates' / TASK / '1'
REL = f'runtime/v6/candidates/{TASK}/1'
ART_URI = 'runtime/v6/candidates/TASK_4de99276d376cc50c61527d6/1/art-ir.json'
TASK_URI = f'runtime/tasks/{TASK}.json'
MODULE = ROOT / 'runtime/modules/36913615596c143f88fc1226e57e8e9090f8f4b037d0f982dfe2f2828862eef1/image-prompt-optimizer'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, obj):
    path = BASE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


prompt = (
    '为场景资产 ENV_RAIN_NIGHT 制作一张单一静态的雨夜环境参考图，'
    '供 SCENE_HANDOFF 三镜共享同一雨夜、同一蓝灰色材与稳定环境光方向。'
    '低饱和蓝灰夜色铺满低纹理背景；背景雨幕细而低频，不遮蔽将来交接双手、完整封口与包口的画面区域。'
    '下方是一片中性平整、稳定可站立、低反光的承托面，表面只保留克制且物理连贯的微弱湿润反射。'
    '以单一平视视点呈现前中后景，中央留出两人相向站立和右手交信的通行净空，'
    '另留乙右手触及包口的空间；这些位置只是后续摆位净空，本图不画人物、信封或背包。'
    '仅用同一方位的画外柔和环境漫反射，令预留的手、封口和包口区域有可辨的亮度分离；不添加可见灯具。'
    '背景没有高频反光、招牌、品牌、可读文字或新陈设；不标定具体地点、城市、建筑、年代或室内外状态。'
)

source_sha = sha(ROOT / 'sources/SRC_69a71adcfaca/source.txt')
art_sha = sha(ROOT / ART_URI)
task_sha = sha(ROOT / TASK_URI)
planned = json.loads((ROOT / ART_URI).read_text(encoding='utf-8'))['references'][4]

sources = [
    dict(id='USER', kind='user', locator='sources/SRC_69a71adcfaca/source.txt',
         excerpt='雨夜，甲把一封未拆的信交给乙；乙确认封口完整后收进背包。',
         sha256=source_sha, reviewed=True),
    dict(id='ART', kind='document', locator=ART_URI,
         excerpt='ArtIR /assets/4、/world、/set、/references/4：同一雨夜、低频雨幕、蓝灰色材、中性承托面，具体地点及室内外未定。',
         sha256=art_sha, reviewed=True),
    dict(id='TASK', kind='document', locator=TASK_URI,
         excerpt='冻结的 ASSET_SCENE_HANDOFF_ENV_RAIN_NIGHT 任务只允许调整提示词表达，保留场景设计及两条 identity_locks。',
         sha256=task_sha, reviewed=True),
    dict(id='PLATE', kind='assumption', locator='creator composition choice within frozen prompt scope',
         excerpt='以空场景参考图留出后续人物和道具摆位净空；16:9 是未绑定模型时的可修改画幅建议。',
         sha256=None, reviewed=True),
]

frame = dict(
    id='F_RAIN_NIGHT_PLATE', entity_ids=['ENV_RAIN_NIGHT'],
    scene='雨夜低饱和蓝灰背景、细而低频且不遮手/完整封口/包口的雨幕、中性平整且低反光的稳定承托面；地点和室内外未定',
    moment='同一雨夜的单一静态环境时刻；不描绘三镜动作或入包终态',
    composition='单一平视视点，前中后景一致；中央及包口可触及区域留通行和手部动作净空，场景本身不画人物、信封或背包',
    camera=dict(viewpoint='单一平视视点', framing='可供三镜重取景的环境参考图',
                equipment_intent='未指定器材',
                derived_visual_intent='环境空间与净空可辨，背景不争夺手、封口和包口证据',
                focus_depth='平整承托面和净空可辨；雨夜背景柔和后退'),
    performance=[],
    lighting=dict(key='同一方位的画外柔和环境漫反射，预留手/完整封口/包口的可读亮度分离，不设可见实景灯',
                  exposure_intent='后续手、完整封口和包口区域可与深色衣装分离，画面内不设可见灯具'),
    color=dict(palette='低饱和蓝灰夜色；中性低反光承托面，湿润反射克制'),
    quality=dict(realism='写实静态场景资产',
                 detail_budget='只表现雨夜、平整承托和轻微湿润反光；不加地标和高频陈设'),
    continuity=dict(invariants=['同一雨夜、蓝灰环境和环境光方向跨 S_HANDOFF、S_SEAL、S_STOW 连续',
                                '环境光方向与承托面材质在三镜保持一致']),
)

icir = dict(
    locale='zh-CN', intent='为 ENV_RAIN_NIGHT 编译三镜共用的雨夜场景参考图提示词，不确定地点或室内外。',
    mode='text_to_image',
    entities=[dict(id='ENV_RAIN_NIGHT', kind='scene_anchor',
                   description='持续同一雨夜；低饱和蓝灰、低频雨幕和中性平整低反光承托面；具体地点、建筑、年代及室内外未定。',
                   source_ids=['USER', 'ART', 'TASK'])],
    references=[], frames=[frame], relations=[], texts=[],
    output=dict(aspect_ratio='16:9', requested_pixels=None, delivered_pixels=None,
                native_resolution='unknown',
                crop_safe_area='留出双人相向交接、眼神与封口以及乙右手触及包口所需净空；不把该建议当成冻结镜位',
                format=None),
)


def value_at(pointer):
    value = icir
    for part in pointer.lstrip('/').split('/'):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


specs = [
    ('H1', '三镜持续同一雨夜并共享蓝灰环境与光向', '/frames/0/continuity/invariants/0',
     ['USER', 'ART', 'TASK'], '供 SCENE_HANDOFF 三镜共享同一雨夜、同一蓝灰色材与稳定环境光方向'),
    ('H2', '不推出未给出的具体地点、建筑、年代及室内外状态', '/entities/0/description',
     ['ART', 'TASK'], '不标定具体地点、城市、建筑、年代或室内外状态'),
    ('H3', '低频雨幕不能遮蔽交接双手、完整封口和包口的证据区域', '/frames/0/scene',
     ['ART', 'TASK'], '背景雨幕细而低频，不遮蔽将来交接双手、完整封口与包口的画面区域'),
    ('H4', '有中性平整、稳定可站立的低反光承托面', '/frames/0/scene',
     ['ART', 'TASK'], '下方是一片中性平整、稳定可站立、低反光的承托面'),
    ('H5', '同一方位画外环境漫反射使手、封口、包口区域可辨，不发明可见实景灯', '/frames/0/lighting/key',
     ['ART', 'TASK'], '仅用同一方位的画外柔和环境漫反射，令预留的手、封口和包口区域有可辨的亮度分离'),
]

facts = [dict(path='/icir' + pointer, value=value_at(pointer), origin='derived', source_ids=source_ids,
              reason='将冻结 ArtIR 的场景设计与源事实编入单张静态环境参考图')
         for _, _, pointer, source_ids, _ in specs]
facts.append(dict(path='/icir/output/aspect_ratio', value='16:9', origin='assumed', source_ids=['PLATE'],
                  reason='宽幅仅为环境资产构图建议，不是已知模型参数或实际像素'))
constraints = [dict(id=cid, level='hard', requirement=req, path='/icir' + pointer,
                    value=value_at(pointer), source_ids=source_ids)
               for cid, req, pointer, source_ids, _ in specs]

compilation = dict(
    id='OUT_ENV', target='通用自然语言（未指定目标图像模型）', surface='generic',
    adapter_version='generic/1.0', status='READY', prompt=prompt,
    negative_prompt=None, native_params={},
    capability=dict(status='unknown', checked_at=None, source_ids=[],
                    negative_mode='positive_only', allowed_native_params=[]),
    constraint_clauses={cid: clause for cid, _, _, _, clause in specs},
    trace=[dict(operation='preserve', path='/icir/entities/0',
                reason='沿用雨夜源事实与 ArtIR 的环境色材、地点开放约束'),
           dict(operation='derive', path='/icir/frames/0/composition',
                reason='将 ArtIR 通行净空转为单张环境参考图可见构图'),
           dict(operation='add', path='/icir/output/aspect_ratio',
                reason='16:9 仅为便于容纳双人摆位的软建议，未声明已控制模型')],
    warnings=['PLAN_ENV_RAIN_NIGHT 只有 planned 文字计划，没有参考图文件、哈希或附件槽位。',
              '未指定生成模型，也未生成或审看图像；静态合同有效不证明视觉效果。'],
)

execution = [
    dict(id='S1', owner='image-prompt-optimizer creator', action='按锁定 ArtIR 编译场景提示词并校验制作合同',
         depends_on=[], inputs=['ART', 'TASK'],
         outputs=[f'{REL}/prompt.md', f'{REL}/production-contract.json'],
         status='DONE', stop_condition='源事实或场景硬锁冲突则停止该资产提示词交付'),
    dict(id='S2', owner='host image executor', action='在获授权图像入口生成雨夜场景资产',
         depends_on=['S1'], inputs=[f'{REL}/prompt.md'], outputs=['image artifact'],
         status='NOT_RUN', stop_condition='未指定并调用图像模型时不报告生成结果'),
    dict(id='S3', owner='independent visual reviewer', action='审看真实场景图及三镜背景连续性',
         depends_on=['S2'], inputs=['image artifact'], outputs=['visual review'],
         status='NOT_RUN', stop_condition='没有真实图像不评价画面'),
]

acceptance = []
for cid, req, _, _, _ in specs:
    acceptance.extend([
        dict(id='STATIC_' + cid, constraint_ids=[cid], stage='static',
             method='逐条对照冻结 ArtIR、ICIR 与主提示词', expected=req,
             status='PASS', evidence=[ART_URI, f'{REL}/prompt.md']),
        dict(id='VISUAL_' + cid, constraint_ids=[cid], stage='visual',
             method='实际图像生成后人工检查', expected=req,
             status='NOT_RUN', evidence=[]),
    ])

contract = dict(schema_version='1.0', contract_id=TASK + '-ENV_RAIN_NIGHT-b1',
                versions=dict(skill='1.15.7', compiler='agent-icir-1.0',
                              packs=['image-prompt-optimizer/1.15.7']),
                sources=sources, icir=icir, facts=facts, constraints=constraints,
                compilations=[compilation], execution=execution, acceptance=acceptance, unresolved=[])

BASE.mkdir(parents=True, exist_ok=True)
write('production-contract.json', contract)
quality = ('静态核对同一雨夜、低频雨幕、平整低反光承托面、相同环境光方向、手/封口/包口净空及无地点和室内外臆断；'
           'PLAN_ENV_RAIN_NIGHT 未绑定真实图像，生成与视觉审阅均未执行。')
(BASE / 'prompt.md').write_text(
    '# 需求理解与默认假设\n\n'
    '源事实为雨夜交信；环境色材和承托面来自已接受 ArtIR。地点、室内外及真实参考图均未确定。'
    '本张是静态场景资产，16:9 仅是构图建议。\n\n'
    '# 主提示词\n\n' + prompt + '\n\n'
    '# 生成参数\n\n目标模型未指定；使用通用自然语言。建议画幅 16:9；实际像素与参考绑定均未指定。\n\n'
    '# 质量检查\n\n' + quality + '\n', encoding='utf-8')

print('contract', sha(BASE / 'production-contract.json'))
print('prompt', sha(BASE / 'prompt.md'))
print('art', art_sha, 'task', task_sha, 'source', source_sha)
