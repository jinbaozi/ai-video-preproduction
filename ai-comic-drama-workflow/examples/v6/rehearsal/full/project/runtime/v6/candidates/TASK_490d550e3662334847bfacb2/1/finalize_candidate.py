from pathlib import Path
import hashlib, json

root=Path('/private/tmp/ai-video-v6-full-demo/project')
rel='runtime/v6/candidates/TASK_490d550e3662334847bfacb2/1'
out=root/rel
mod=root/'runtime/modules/36913615596c143f88fc1226e57e8e9090f8f4b037d0f982dfe2f2828862eef1/image-prompt-optimizer'
task=json.loads((root/'runtime/tasks/TASK_490d550e3662334847bfacb2.json').read_text())
sha=lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
put=lambda name,data: (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
resources=[
 ('SKILL.md','142ceb296fe2af8152a2d4e0197a00867b16a56d0dd1f4883ae5a467dc3aea68'),
 ('references/current-contract.md','28e679dff03715b08fd5ca1b066eb952b91eaaf74bc44c055118c4b4570a5d1d'),
 ('references/cooperation-v5.md','9cfe4879a072ccdc5eee05467b0cc81bc837224455153a30179bd94f54efbaf2'),
 ('references/intent-compiler.md','ef6e47f0063231d8f72320d1a6e7f573da84011c43153514a1232c1b29656b03'),
 ('references/character-appearance.md','b3cb6fafc16e207b8ee64cfc4d50d797c73eebdd1c8728d5d5e6cff4cd151631'),
 ('templates/production-contract.md','8f156b9ccf183bbeda62260fc5fb94bcb50d4d6e731c51bd2407bca253c0a8d0'),
 ('references/structural-realism.md','333a6cdf6e3060b67aad79566b71e220fde477f8e38762d8181f9559047ef836')]
reads=[]
for name,expected in resources:
 p=mod/name;actual=sha(p);assert actual==expected,(name,actual,expected)
 reads.append({'path':str(p),'sha256':actual})
art=root/'runtime/v6/candidates/TASK_4de99276d376cc50c61527d6/1/art-ir.json'
assert sha(art)=='d077e4315fc85728e26fcdcd92eff9a3efcc727af4fdd47808974160c31eae71'
assert sha(root/'runtime/tasks/TASK_490d550e3662334847bfacb2.json')=='5a27cc1425f46252fc972f1070a79dd6da6045be68eb5dcb141eb29db39829ef'
receipt={'task_id':task['task_id'],'batch':1,'module':{'name':'image-prompt-optimizer','version':'1.15.7','sha256':'36913615596c143f88fc1226e57e8e9090f8f4b037d0f982dfe2f2828862eef1'},
         'frozen_inputs':[{'path':str(art),'sha256':sha(art)},{'path':str(root/'runtime/tasks/TASK_490d550e3662334847bfacb2.json'),'sha256':'5a27cc1425f46252fc972f1070a79dd6da6045be68eb5dcb141eb29db39829ef'}],
         'reads':reads}
put('evidence/read-audit.json',receipt)
contract=out/'production-contract.json';prompt_file=out/'prompt.txt'
prompt=prompt_file.read_text().strip()
validator=json.loads((out/'evidence/native-validator.json').read_text())
assert validator['status']=='STATIC_VALID' and not validator['errors']
locks=task['job']['brief']['locks']
assert len(locks)==2
checks=[
 {'ref':locks[0],'finding':'乙的深蓝灰无标识哑面外层和跨三镜同一人物、同一服装外观已写入提示词；真实脸部身份需待图像形成后由已核参考或后续审核确定。','status':'PASS','evidence':[rel+'/prompt.txt',rel+'/production-contract.json']},
 {'ref':locks[1],'finding':'乙的眼部、右手及可活动右袖在单张身份参考图中无遮挡；实际与包口接触的镜头仍需后续媒体审核，此处未声称已经看见包口。','status':'PASS','evidence':[rel+'/prompt.txt',rel+'/production-contract.json']}
]
contract_evidence={'status':'STATIC_VALID','native_validator_uri':rel+'/evidence/native-validator.json','production_contract_uri':rel+'/production-contract.json',
                   'production_contract_sha256':sha(contract),'prompt_uri':rel+'/prompt.txt','prompt_sha256':sha(prompt_file),
                   'lock_refs':locks,'static_lock_coverage':'PASS','reference_plan':'PLAN_CHAR_YI is planned; no file or sha256 exists','image_generation':'NOT_RUN','visual_review':'NOT_RUN'}
put('evidence/contract-checks.json',contract_evidence)
handoff={'requirement_id':'UP_0af56be83b7ef933e42debd3','source_slot':'art:scene:13x5343454e455f48414e444f4646:ArtIR','source_version':11,
         'source_uri':'runtime/v6/candidates/TASK_4de99276d376cc50c61527d6/1/art-ir.json','source_sha256':sha(art),
         'source_pointers':['/assets/1','/world','/references/1'],
         'target_slot':'visual_prompts:asset:27x41535345545f5343454e455f48414e444f46465f434841525f5949:VisualImagePrompt',
         'target_uri':rel+'/prompt.txt','target_sha256':sha(prompt_file),
         'mapping':{'CHAR_YI':'same-person and wardrobe continuity remains a downstream check',
                    'PLAN_CHAR_YI':'planned text reference only; no invented file or binding',
                    'identity_locks':'both exact lock refs are checked in RoleResult'},
         'status':'STATIC_MAPPED','media_status':'NOT_RUN'}
put('evidence/handoff.json',handoff)
role={
 'schema':'role-result/5.1','task_id':task['task_id'],'context_fingerprint':task['context_fingerprint'],
 'artifact':str(prompt_file),'artifact_sha256':sha(prompt_file),
 'understanding':'乙 CHAR_YI 的单张写实角色身份与衣装提示词；保留雨夜、美术衣装及眼手可见性。面容、年龄、性别、职业、关系和具体地点无来源锁定，PLAN_CHAR_YI 尚无图像文件。',
 'prompt':prompt,
 'params':{'target':'通用自然语言','surface':'generic','native_params':{},'reference_files':[]},
 'quality_check':'锁定制作合同原生校验为 STATIC_VALID，两个 Art 身份锁项已逐项对照提示词；真实图片未生成，像素、人物身份和视觉质量均未审看。',
 'production_contract':str(contract),'validator':{'status':validator['status'],'contract_sha256':sha(contract)},
 'checks':checks,'handoff':[],
 'module_receipt':{'name':'image-prompt-optimizer','version':'1.15.7','skill_sha256':reads[0]['sha256'],'reads':reads},
 'complete':True,'conflicts':[],'unresolved':[]}
put('role-result.json',role)
checks_v6=[
 {'id':'module_receipt','status':'PASS','evidence':[rel+'/evidence/read-audit.json']},
 {'id':'image_prompt_contract','status':'PASS','evidence':[rel+'/evidence/native-validator.json',rel+'/evidence/contract-checks.json',rel+'/production-contract.json']},
 {'id':'handoff','status':'PASS','evidence':[rel+'/evidence/handoff.json']}]
manifest={'schema':'candidate-result/6.0','task_id':task['task_id'],'batch':1,
 'agent_id':'/root/host_bridge/full_rehearsal/v6_a845ef66576a5cddd55a6125',
 'input_digest':'d5213297e7bf126af70ff54a9fb5eb86742ea993e7fddbea7e7d4ade1906361e',
 'result_uri':rel+'/role-result.json','result_sha256':sha(out/'role-result.json'),
 'artifacts':[{'slot':'visual_prompts:asset:27x41535345545f5343454e455f48414e444f46465f434841525f5949:VisualImagePrompt',
               'kind':'VisualImagePrompt','uri':rel+'/prompt.txt','sha256':sha(prompt_file)}],
 'module_receipts':[{'name':'image-prompt-optimizer','version':'1.15.7','sha256':'36913615596c143f88fc1226e57e8e9090f8f4b037d0f982dfe2f2828862eef1'}],
 'checks':checks_v6,
 'handoffs':[{'requirement_id':'UP_0af56be83b7ef933e42debd3','source_slot':'art:scene:13x5343454e455f48414e444f4646:ArtIR','source_version':11,
              'target_slot':'visual_prompts:asset:27x41535345545f5343454e455f48414e444f46465f434841525f5949:VisualImagePrompt',
              'target_pointer':'','channel':'artifact','evidence':[rel+'/evidence/handoff.json']}],
 'unresolved':[]}
put('candidate-result.json',manifest)
print(json.dumps({'candidate_result':str(out/'candidate-result.json'),'sha256':sha(out/'candidate-result.json'),
                  'role_result_sha256':sha(out/'role-result.json'),'prompt_sha256':sha(prompt_file),'contract_sha256':sha(contract),
                  'validator_status':validator['status']},ensure_ascii=False,indent=2))
