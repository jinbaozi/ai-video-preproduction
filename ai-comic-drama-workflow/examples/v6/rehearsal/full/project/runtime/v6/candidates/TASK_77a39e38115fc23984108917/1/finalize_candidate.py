import hashlib
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator


ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
TASK = 'TASK_77a39e38115fc23984108917'
BASE = ROOT / 'runtime/v6/candidates' / TASK / '1'
REL = f'runtime/v6/candidates/{TASK}/1'
ART_URI = 'runtime/v6/candidates/TASK_4de99276d376cc50c61527d6/1/art-ir.json'
TASK_URI = f'runtime/tasks/{TASK}.json'
MODULE_URI = 'runtime/modules/36913615596c143f88fc1226e57e8e9090f8f4b037d0f982dfe2f2828862eef1/image-prompt-optimizer'
MODULE = ROOT / MODULE_URI
REPO = Path('/Users/godxu/101-副业/00-工作流/ai-video-preproduction/ai-comic-drama-workflow')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(name, obj):
    path = BASE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


state = read(ROOT / 'runtime/v6/state.json')
envelope = state['tasks'][TASK]['envelope']
frozen = read(ROOT / TASK_URI)
art = read(ROOT / ART_URI)
contract = read(BASE / 'production-contract.json')
prompt = contract['compilations'][0]['prompt']

inputs = []
for item in envelope['inputs']:
    observed = sha(ROOT / item['uri'])
    assert observed == item['sha256'], item['uri']
    inputs.append(dict(uri=item['uri'], expected_sha256=item['sha256'], observed_sha256=observed))
write('evidence/input-integrity.json', dict(inputs=inputs, status='MATCH'))

resource_reads = []
for item in envelope['resources']:
    observed = sha(ROOT / item['uri'])
    assert observed == item['sha256'], item['uri']
    resource_reads.append(dict(relative=item['uri'].removeprefix(MODULE_URI + '/'),
                               path=str(ROOT / item['uri']), sha256=item['sha256'],
                               observed_sha256=observed))
write('evidence/module-receipt.json',
      dict(module=envelope['module'], required_reads=resource_reads, status='MATCH'))

native_command = [sys.executable, str(MODULE / 'scripts/validate_production_contract.py'),
                  str(BASE / 'production-contract.json')]
proc = subprocess.run(native_command, capture_output=True, text=True)
(BASE / 'evidence/contract-validator-stdout.txt').write_text(proc.stdout, encoding='utf-8')
(BASE / 'evidence/contract-validator-stderr.txt').write_text(proc.stderr, encoding='utf-8')
write('evidence/contract-validator-invocation.json',
      dict(command=native_command, exit_code=proc.returncode,
           stdout_uri=f'{REL}/evidence/contract-validator-stdout.txt',
           stdout_sha256=sha(BASE / 'evidence/contract-validator-stdout.txt'),
           stderr_uri=f'{REL}/evidence/contract-validator-stderr.txt',
           stderr_sha256=sha(BASE / 'evidence/contract-validator-stderr.txt')))
assert proc.returncode == 0, proc.stdout + proc.stderr
native_report = json.loads(proc.stdout)
report_path = write('evidence/contract-validation.json', native_report)
assert native_report['status'] == 'STATIC_VALID', native_report

locks = [
    dict(ref=art['assets'][4]['identity_locks'][0],
         finding='正文锁定 SCENE_HANDOFF 三镜共用同一雨夜、蓝灰色材与环境光方向；该静态场景图本身不声称三镜实拍连续性已通过。'),
    dict(ref=art['assets'][4]['identity_locks'][1],
         finding='正文不标定具体地点、城市、建筑、年代和室内外状态，也不加入能反推这些属性的地标。'),
    dict(ref='/set/atmosphere',
         finding='正文显式保留低频雨幕、交接双手/封口/包口净空，以及同一方位画外柔和环境漫反射。'),
    dict(ref='/set/layout/0 GROUND_1',
         finding='正文使用中性平整、稳定可站立、低反光承托面；未把 ArtIR 设计米值冒充原文测量或图像模型坐标控制。'),
    dict(ref='/references/4 PLAN_ENV_RAIN_NIGHT',
         finding='status=planned 且 file/sha256 均为 null；无真实图像参考文件或已核附件槽位，本张仍为纯文字提示词。'),
]
assert all(x in {row['ref'] for row in locks} for x in art['assets'][4]['identity_locks'])
for row in contract['compilations'][0]['constraint_clauses'].values():
    assert row in prompt, row

contract_sha = sha(BASE / 'production-contract.json')
params = dict(target_model=None, surface='generic', aspect_ratio='16:9',
              requested_pixels=None, reference_files=[])
asset = dict(
    project_id='LETTER_FULL_DEMO', task_id=TASK, asset_id='ENV_RAIN_NIGHT',
    scope_key='ASSET_SCENE_HANDOFF_ENV_RAIN_NIGHT',
    art_source=dict(uri=ART_URI, sha256=sha(ROOT / ART_URI), pointer='/assets/4'),
    reference_plan=dict(id='PLAN_ENV_RAIN_NIGHT', status='planned', file=None,
                        sha256=None, role='scene', use_in_this_prompt='unbound; text-only scene design'),
    prompt=prompt, prompt_document=f'{REL}/prompt.md',
    production_contract=f'{REL}/production-contract.json',
    production_contract_sha256=contract_sha, params=params, static_checks=locks,
    media_status='NOT_RUN', visual_review_status='NOT_RUN',
)
asset_path = write('visual-image-prompt.json', asset)
asset_sha = sha(asset_path)

write('evidence/semantic-audit.json',
      dict(art_source=dict(uri=ART_URI, sha256=sha(ROOT / ART_URI)),
           target_artifact=dict(uri=f'{REL}/visual-image-prompt.json', sha256=asset_sha),
           locks=locks,
           contract=dict(uri=f'{REL}/production-contract.json', sha256=contract_sha,
                         validator_status=native_report['status']),
           prompt_text_matches_contract=asset['prompt'] == prompt,
           reference_file_binding='NONE_PLANNED_ONLY', image_generation='NOT_RUN',
           visual_review='NOT_RUN'))

module_receipt = dict(name='image-prompt-optimizer', version='1.15.7',
                      skill_sha256=sha(MODULE / 'SKILL.md'),
                      reads=[dict(path=row['path'], sha256=row['observed_sha256']) for row in resource_reads])
role = dict(
    schema='role-result/5.1', task_id=TASK,
    context_fingerprint=frozen['context_fingerprint'],
    artifact=str(asset_path), artifact_sha256=asset_sha,
    production_contract=str(BASE / 'production-contract.json'),
    understanding=['源事实为雨夜；蓝灰低频雨幕、承托面与画外漫反射是已接受 ArtIR 的设计。',
                   'PLAN_ENV_RAIN_NIGHT 仍为 planned 文字参考，具体地点与室内外未锁定。'],
    prompt=prompt, params=params,
    quality_check='静态核对同一雨夜、低频雨幕、平整低反光承托面、稳定环境光方向、手/封口/包口净空及无地点和室内外臆断；图像尚未生成或审看。',
    checks=locks,
    validator=dict(status=native_report['status'], report_uri=f'{REL}/evidence/contract-validation.json',
                   report_sha256=sha(report_path)),
    module_receipt=module_receipt, conflicts=[], unresolved=[], complete=True,
)
role_path = write('role-result.json', role)

candidate = dict(
    schema='candidate-result/6.0', task_id=TASK, batch=envelope['batch'],
    agent_id='/root/host_bridge/full_rehearsal/v6_1e8bce88416377cfc2d8315e',
    input_digest=envelope['input_digest'],
    result_uri=f'{REL}/role-result.json', result_sha256=sha(role_path),
    artifacts=[dict(slot=envelope['expected_artifacts'][0]['slot'], kind='VisualImagePrompt',
                    uri=f'{REL}/visual-image-prompt.json', sha256=asset_sha)],
    module_receipts=[envelope['module']],
    checks=[
        dict(id='module_receipt', status='PASS',
             evidence=[f'{REL}/evidence/module-receipt.json', f'{REL}/evidence/input-integrity.json']),
        dict(id='image_prompt_contract', status='PASS',
             evidence=[f'{REL}/evidence/contract-validation.json', f'{REL}/evidence/semantic-audit.json',
                       f'{REL}/evidence/native-preflight.json']),
        dict(id='handoff', status='PASS',
             evidence=[f'{REL}/evidence/semantic-audit.json', f'{REL}/visual-image-prompt.json']),
    ],
    handoffs=[dict(envelope['handoffs'][0], evidence=[f'{REL}/evidence/semantic-audit.json',
                                                  f'{REL}/visual-image-prompt.json'])],
    unresolved=[],
)
candidate_path = write('candidate-result.json', candidate)

role_schema = read(REPO / 'schemas/v5-role-result.schema.json')
candidate_schema = read(REPO / 'schemas/v6-candidate-result.schema.json')
Draft202012Validator(role_schema).validate(role)
Draft202012Validator(candidate_schema).validate(candidate)

sys.path.insert(0, str(REPO / 'src'))
from ai_comic_drama_workflow.v5 import V5Kernel
kernel = V5Kernel(ROOT)
receipt_status = kernel.receipt_audit(frozen, role)
kernel.accept_prompt(frozen, role, kernel.state)
write('evidence/native-preflight.json',
      dict(role_result_schema='SCHEMA_VALID', candidate_result_schema='SCHEMA_VALID',
           module_receipt=receipt_status, v5_accept_prompt='PASS',
           scope='read-only native preflight; no promotion or independent review',
           role_result_sha256=sha(role_path), visual_image_prompt_sha256=asset_sha))

print('candidate', candidate_path, sha(candidate_path))
print('role_result', sha(role_path))
print('artifact', asset_sha)
print('validator', native_report['status'], 'receipt', receipt_status)
