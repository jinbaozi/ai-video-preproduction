from pathlib import Path
import hashlib, json

root = Path('/private/tmp/ai-video-v6-full-demo/project')
out = root / 'runtime/v6/candidates/TASK_490d550e3662334847bfacb2/1'
art_rel = 'runtime/v6/candidates/TASK_4de99276d376cc50c61527d6/1/art-ir.json'
art_bytes = (root/art_rel).read_bytes()
art = json.loads(art_bytes)
asset = art['assets'][1]
ref = art['references'][1]
assert asset['id'] == 'CHAR_YI' and ref['id'] == 'PLAN_CHAR_YI'

clauses = {
 'H1': '画面仅一名虚构角色乙',
 'H2': '无标识深蓝灰低反光哑面平织外层',
 'H3': '眼部、右手以及活动自如的右袖与袖口清楚可见，发丝、头饰和袖口均不遮挡眼睛或右手',
 'H4': '不指定面容、年龄、性别、职业或人物关系',
 'H5': '雨夜低饱和蓝灰、低频雨幕与中性平整承托面；不出现可识别城市、建筑或具体室内外线索',
 'H6': '此图确定后作为乙在交接、验封、入包三镜的同一人物与同一衣装外观参考',
 'H7': '无品牌标志、身份标记和可读文字',
}
prompt = ('制作乙的单张2:3竖幅写实角色外观参考图。' + clauses['H1'] + '，平视三分之二身的单一静态时刻，稳立于承托面，双手自然放在身前，衣装轮廓和手的归属可辨。'
          + '乙穿' + clauses['H2'] + '；' + clauses['H3'] + '。'
          + clauses['H5'] + '。同一方向的画外柔和环境漫反射令眼周、右手与深色衣料之间有可读层次，雨幕不遮挡人物。'
          + clauses['H4'] + '；' + clauses['H7'] + '，不添信件内容或其他剧情。'
          + clauses['H6'] + '。')
(out/'prompt.txt').write_text(prompt+'\n',encoding='utf-8')

sources = [
 {'id':'ART1','kind':'document','locator':art_rel+'#/assets/1,/references/1,/world',
  'excerpt':'乙 CHAR_YI 的美术设计、身份锁定、计划参考、雨夜色材；计划参考尚无真实图像。',
  'sha256':hashlib.sha256(art_bytes).hexdigest(),'reviewed':True},
 {'id':'ASSUME1','kind':'assumption','locator':'task-local:CHAR_YI/identity-portrait-framing',
  'excerpt':'2:3竖幅、平视三分之二身和双手静置仅为单张身份与衣装参考的构图选择，不改变上游剧情与镜头。',
  'sha256':None,'reviewed':True},
]
icir = {
 'locale':'zh-CN','intent':'乙 CHAR_YI 的单张静态写实身份与衣装参考提示词；真实图像和参考绑定尚未执行。',
 'mode':'text_to_image',
 'entities':[{'id':'CHAR_YI','kind':'person','description':'乙；深蓝灰无标识哑面外层；面容、年龄、性别、职业与人物关系未锁定。','source_ids':['ART1']}],
 'references':[],
 'frames':[{'id':'F_CHAR_YI','entity_ids':['CHAR_YI'],
            'scene':'雨夜低频背景，中性平整承托面；具体地点和室内外不定。',
            'moment':'乙稳立、双手自然放在身前的单一静态角色外观时刻；无交信、验封或入包动作。',
            'composition':'平视三分之二身；眼部、右手、袖口、衣装轮廓均在可读范围。',
            'camera':{'viewpoint':'平视','framing':'三分之二身，双手入画','derived_visual_intent':'不以透视遮挡眼部或右手'},
            'performance':[{'entity_id':'CHAR_YI','action':'双手自然放在身前，右手可见；稳定站立。','support_contact':'身体由中性平整承托面支撑','gaze':'自然看向画外近处，不指定剧情对象'}],
            'lighting':{'key':'同一方向画外柔和环境漫反射','exposure_intent':'眼周、右手与深色衣料有层次'},
            'color':{'palette':'低饱和蓝灰背景、深蓝灰衣装','protected_colors':['深蓝灰衣装']},
            'quality':{'realism':'写实角色参考','detail_budget':'辨清眼部、右手、袖口和衣料轮廓','preserve_texture':['低反光平织衣料']}}],
 'relations':[], 'texts':[],
 'output':{'aspect_ratio':'2:3','requested_pixels':None,'delivered_pixels':None,'native_resolution':'unknown','crop_safe_area':'眼部、右手与衣装轮廓完整入画','format':None},
}
# 2:3 is a composition proposal only; no pixel dimensions or provider parameter is asserted.
paths = [
 ('H1','画面仅一名乙角色','/icir/frames/0/entity_ids',['ART1']),
 ('H2','保留乙的无标识深蓝灰哑面外层','/icir/entities/0/description',['ART1']),
 ('H3','眼部、右手和右袖无遮挡','/icir/frames/0/composition',['ART1']),
 ('H4','不擅定永久身份信息','/icir/entities/0/description',['ART1']),
 ('H5','雨夜且地点及室内外保持开放','/icir/frames/0/scene',['ART1']),
 ('H6','同一人物与同一衣装跨三镜连续','/icir/frames/0/moment',['ART1']),
 ('H7','不增品牌及画中文字','/icir/frames/0/scene',['ART1']),
]
document = {'icir':icir}
def ptr(path):
 val=document
 for part in path.strip('/').split('/'):
  val=val[int(part)] if isinstance(val,list) else val[part]
 return val
facts=[]; constraints=[]
for hid,req,path,source_ids in paths:
 val=ptr(path)
 facts.append({'path':path,'value':val,'origin':'derived' if hid in ('H6','H7') else 'explicit',
               'source_ids':source_ids,'reason':'从冻结 ArtIR 对乙的资产、雨夜世界与计划参考抽取；跨镜使用为下游目标而非已完成媒体。'})
 constraints.append({'id':hid,'level':'hard','requirement':req,'path':path,'value':val,'source_ids':source_ids})
facts.append({'path':'/icir/output/aspect_ratio','value':'2:3','origin':'assumed','source_ids':['ASSUME1'],'reason':'竖幅角色参考的构图提案；不是用户或 ArtIR 原文指定的接口参数。'})
contract = {
 'schema_version':'1.0','contract_id':'LETTER_FULL_DEMO_CHAR_YI_20260925_B1',
 'versions':{'skill':'1.15.7','compiler':'agent-icir-1.0','packs':['current-contract','character-appearance','structural-realism']},
 'sources':sources,'icir':icir,'facts':facts,'constraints':constraints,
 'compilations':[{'id':'OUT_CHAR_YI','target':'通用自然语言（未选择图像模型）','surface':'generic','adapter_version':'generic/1.0',
                  'status':'READY','prompt':prompt,'negative_prompt':None,'native_params':{},
                  'capability':{'status':'unknown','checked_at':None,'source_ids':[],'negative_mode':'unknown','allowed_native_params':[]},
                  'constraint_clauses':clauses,
                  'trace':[{'operation':'preserve','path':'/icir/entities/0/description','reason':'只锁定 Art 已给乙的衣装；面容和人口属性未由上游确定。'},
                           {'operation':'derive','path':'/icir/frames/0/composition','reason':'单张身份参考选择眼部、右手与衣装同时可见的静态构图，不复述三镜连续动作。'}],
                  'warnings':['PLAN_CHAR_YI 只是文字计划，当前无真实参考文件、图片生成结果或视觉审看。']}],
 'execution':[{'id':'S1','owner':'image-prompt-optimizer-agent','action':'从锁定 ArtIR 编译单张角色参考提示词和静态合同',
               'depends_on':[],'inputs':['ART1'],'outputs':['prompt.txt','production-contract.json'],'status':'DONE',
               'stop_condition':'任何锁定身份或来源冲突须阻断受影响内容'},
              {'id':'S2','owner':'downstream-image-host','action':'在后续受权任务中生成或提供真实图片并绑定文件',
               'depends_on':['S1'],'inputs':['prompt.txt'],'outputs':['real-image-file'],'status':'NOT_RUN',
               'stop_condition':'尚无已核能力、文件和执行证据'},
              {'id':'S3','owner':'independent-visual-reviewer','action':'按锁项审看真实结果并核对身份与衣装',
               'depends_on':['S2'],'inputs':['real-image-file'],'outputs':['visual-review'],'status':'NOT_RUN',
               'stop_condition':'无真实图片时不可宣称视觉通过'}],
 'acceptance':[], 'unresolved':[],
}
for hid,req,_,_ in paths:
 contract['acceptance'].append({'id':'STATIC_'+hid,'constraint_ids':[hid],'stage':'static','method':'检查冻结 ArtIR、ICIR 与提示词正文的相应词句',
                                'expected':req,'status':'NOT_RUN','evidence':[]})
 contract['acceptance'].append({'id':'VISUAL_'+hid,'constraint_ids':[hid],'stage':'visual','method':'取得真实图像后独立审看',
                                'expected':req,'status':'NOT_RUN','evidence':[]})
(out/'production-contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'prompt_sha256':hashlib.sha256((out/'prompt.txt').read_bytes()).hexdigest(),
                  'contract_sha256':hashlib.sha256((out/'production-contract.json').read_bytes()).hexdigest(),
                  'prompt':prompt},ensure_ascii=False,indent=2))
