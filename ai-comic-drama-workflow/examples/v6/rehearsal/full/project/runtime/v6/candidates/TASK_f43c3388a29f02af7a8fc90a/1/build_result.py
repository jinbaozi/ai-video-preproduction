import hashlib, json, subprocess, sys
from pathlib import Path
from ai_comic_drama_workflow.v5_handoff import validate_handoff

ROOT = Path('/private/tmp/ai-video-v6-full-demo/project')
OUT = ROOT/'runtime/v6/candidates/TASK_f43c3388a29f02af7a8fc90a/1'
EVID = OUT/'evidence'
TASK = json.loads((ROOT/'runtime/tasks/TASK_f43c3388a29f02af7a8fc90a.json').read_text())
ART = OUT/'art-ir.json'
art = json.loads(ART.read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
write = lambda p,x: Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
uri = lambda p: Path(p).relative_to(ROOT).as_posix()

# Lock proof is a byte comparison, not an interpretation claim.
reads=[]
for item in TASK['module']['required_reads']:
    actual=sha(item['path'])
    if actual != item['sha256']: raise RuntimeError('locked read changed: '+item['relative'])
    reads.append(dict(path=item['path'],sha256=actual))
inputs=[]
for item in TASK['inputs']:
    actual=sha(item['uri'])
    if actual != item['sha256']: raise RuntimeError('frozen native input changed: '+item['slot'])
    inputs.append(dict(slot=item['slot'],uri=item['uri'],sha256=actual))
module_receipt=dict(name=TASK['module']['name'],version=TASK['module']['version'],
                    skill_sha256=TASK['module']['skill_sha256'],reads=reads)
write(EVID/'module-receipt.json',dict(status='PASS',module_receipt=module_receipt,inputs=inputs,
    v6_inputs=[dict(slot=i['slot'],uri=i['uri'],sha256=i['sha256']) for i in json.loads((ROOT/'runtime/v6/state.json').read_text())['tasks']['TASK_f43c3388a29f02af7a8fc90a']['envelope']['inputs']]))

# Fresh locked native validator, capturing its exact status.
script=ROOT/'runtime/modules'/TASK['module']['sha256']/TASK['module']['name']/'scripts/art_compile.py'
command=[sys.executable,str(script),'validate',str(ART)]
proc=subprocess.run(command,capture_output=True,text=True)
if proc.returncode: raise RuntimeError('native validator failed: '+proc.stderr+proc.stdout)
report=json.loads(proc.stdout)
write(EVID/'native-validator.json',dict(command=command,exit_code=proc.returncode,stdout=report,
    stderr=proc.stderr,artifact_uri=uri(ART),artifact_sha256=sha(ART)))

# The frozen DirectorIR 1.2 expresses actions in timeline/actions, while the locked Art
# validator only permits ArtIR.events pointers into /shots/N/phases/K. Do not forge a phase.
director=json.loads(Path(TASK['inputs'][0]['uri']).read_text())
phase_counts={s['id']:len(s['phases']) for s in director['shots']}
write(EVID/'phase-pointer-limit.json',dict(status='OPEN_CONTRACT_LIMIT',owner='director',
    finding='DirectorIR 1.2 的动作位于 /timeline/actions；锁定 Art 校验器要求 ArtIR.events 指向 /shots/N/phases/K，而三个镜头的 phases 均为空。故本 ArtIR 不伪造事件指针，保留逐镜美术支持与冻结导演时间线的语义映射。',
    director_uri=TASK['inputs'][0]['uri'],director_sha256=sha(TASK['inputs'][0]['uri']),
    art_events=len(art['events']),director_phase_counts=phase_counts,
    director_actions=[dict(id=a['id'],semantic_id=a['semantic_id'],start_ms=a['start_ms'],end_ms=a['end_ms']) for a in director['timeline']['actions']],
    media_review='NOT_RUN'))

spec={r['id']:r for r in TASK['handoff']['required_handoffs']}
mapping={
 'director:REQ_RAIN_NIGHT':(
    '雨夜写入世界、美术环境和逐镜背景，地点及室内外仍开放。','ART_WORLD',[
        dict(op='contains',path='/world/thesis',value='雨夜'),
        dict(op='contains',path='/set/atmosphere',value='具体室内外')]),
 'director:REQ_SAME_UNOPENED_LETTER':(
    '同一 PROP_LETTER 资产绑定三个镜头，封口持续完整且验封不拆。','ART_CONTINUITY',[
        dict(op='contains',path='/assets/2/identity_locks/0',value='同一实体 PROP_LETTER'),
        dict(op='contains',path='/shots/1/composition_support/occlusion',value='未拆信')]),
 'director:REQ_EVENT_ORDER':(
    '逐镜美术支持与冻结导演的三个有序 timeline/actions 对齐；Art 不重写动作时间线。','ART_MAPPING',[
        dict(op='equals',path='/shots/0/id',value='S_HANDOFF'),
        dict(op='equals',path='/shots/1/id',value='S_SEAL'),
        dict(op='equals',path='/shots/2/id',value='S_STOW'),
        dict(op='contains',path='/shots/1/composition_support/negative_space',value='不提前显示入包')]),
 'director:REQ_ENDING':(
    '终镜美术支持明确8500毫秒后信在包内且终帧不外露；动作终态仍以冻结导演时间线为准。','ART_STOW',[
        dict(op='contains',path='/shots/2/composition_support/background',value='8500毫秒后信完全在背包内'),
        dict(op='contains',path='/shots/2/composition_support/occlusion',value='终帧只见乙手退出与背包口')]),
 'director:REQ_SCRIPT_EVENTS':(
    '三个原生事件 ID 分别锚入对应镜头美术遮挡约束，角色认知与动作起讫仍由DirectorIR持有。','ART_MAPPING',[
        dict(op='contains',path='/shots/0/composition_support/occlusion',value='EVT_HANDOFF'),
        dict(op='contains',path='/shots/1/composition_support/occlusion',value='EVT_SEAL_CHECK'),
        dict(op='contains',path='/shots/2/composition_support/occlusion',value='EVT_STOW')]),
 'director:REQ_REVEAL_ORDER':(
    '交接镜不提前展示验封/入包，验封镜不提前展示入包，最后镜才呈现收存结果。','ART_MAPPING',[
        dict(op='contains',path='/shots/0/composition_support/negative_space',value='不提前展示验封或入包结果'),
        dict(op='contains',path='/shots/1/composition_support/negative_space',value='不提前显示入包'),
        dict(op='contains',path='/shots/2/composition_support/negative_space',value='只在验封之后出现')])
}
handoff=[]
for key,requirement in spec.items():
    reason,target_clause,checks=mapping[key]
    handoff.append(dict(requirement_id=key,source_fingerprint=requirement['source_fingerprint'],
        reason=reason,target_checks=checks,target_clause=target_clause))
validated=validate_handoff('art',art,TASK['handoff']['required_handoffs'],handoff)
write(EVID/'handoff-v5.json',dict(status='PASS',scope='static target assertions and source fingerprints',
    note='六条原生V5映射独立于V6两条artifact lineage。ArtIR.events为空的阶段指针限制另列证据，不以静态检查冒充实际媒体/语义审核。',
    mappings=validated))

# Independent V6 lineage evidence: current raw candidate bytes and their native bindings.
VENVELOPE=json.loads((ROOT/'runtime/v6/state.json').read_text())['tasks'][TASK['task_id']]['envelope']
upstream={i['slot']:i for i in VENVELOPE['inputs']}
assert sha(ROOT/upstream['canon:project:project:Canon']['uri']) == upstream['canon:project:project:Canon']['sha256']
assert sha(ROOT/upstream['director:project:project:DirectorIR']['uri']) == upstream['director:project:project:DirectorIR']['sha256']
write(EVID/'handoff-v6-canon.json',dict(requirement_id=VENVELOPE['handoffs'][0]['requirement_id'],
    input=upstream['canon:project:project:Canon'],native_binding=art['canon'],
    retained_entity_ids=[a['entity_id'] for a in art['assets']],
    checks=['Rain-night source fact retained','same unopened letter retained','event order preserved in shot support']))
write(EVID/'handoff-v6-director.json',dict(requirement_id=VENVELOPE['handoffs'][1]['requirement_id'],
    input=upstream['director:project:project:DirectorIR'],native_binding=art['director'],
    shot_ids=[s['id'] for s in art['shots']],director_phase_counts=phase_counts,
    checks=['Three frozen shot pointers match','8500/9000 ms stow state expressed without exposed letter','No invented ArtIR event phase pointer']))

artifact_sha=sha(ART)
base='runtime/v6/candidates/'+TASK['task_id']+'/1/'
checks=[
    dict(id='module_receipt',status='PASS',finding='四份锁定资源和两份V5原生输入已逐字节核对。',evidence=[base+'evidence/module-receipt.json']),
    dict(id='native_validator',status='PASS',finding='锁定 art_compile.py 新鲜校验返回 '+report['status']+'；仅为静态检查。phase 指针限制单列，媒体未审。',evidence=[base+'evidence/native-validator.json',base+'evidence/phase-pointer-limit.json']),
    dict(id='handoff',status='PASS',finding='六条V5目标断言通过且V6两条来源 lineage 独立绑定；phase 指针限制须独立语义审核。',evidence=[base+'evidence/handoff-v5.json',base+'evidence/handoff-v6-canon.json',base+'evidence/handoff-v6-director.json',base+'evidence/phase-pointer-limit.json'])
]
role=dict(schema='role-result/5.1',task_id=TASK['task_id'],context_fingerprint=TASK['context_fingerprint'],
    artifact=str(ART),artifact_sha256=artifact_sha,module_receipt=module_receipt,
    checks=checks,handoff=handoff,complete=True,conflicts=[],
    unresolved=['Director owner: frozen DirectorIR 1.2 has no /shots/N/phases/K, so locked ArtIR.events cannot encode the three existing /timeline/actions. Shot-level Art support and V5 target assertions preserve their meaning; independent reviewer must decide whether this is adequate for downstream continuity.'],
    validator=report)
write(OUT/'role-result.json',role)

v6_handoffs=[]
for specrow,proof in zip(VENVELOPE['handoffs'],['handoff-v6-canon.json','handoff-v6-director.json']):
    row=dict(specrow)
    row['evidence']=[base+'evidence/'+proof,base+'evidence/handoff-v5.json']
    v6_handoffs.append(row)
candidate=dict(schema='candidate-result/6.0',task_id=TASK['task_id'],batch=1,
    agent_id='/root/host_bridge/full_rehearsal/v6_f35d6d105d97b99707b9c9e7',
    input_digest=VENVELOPE['input_digest'],result_uri=base+'role-result.json',result_sha256=sha(OUT/'role-result.json'),
    artifacts=[dict(slot=VENVELOPE['expected_artifacts'][0]['slot'],kind='ArtIR',uri=base+'art-ir.json',sha256=artifact_sha)],
    module_receipts=[VENVELOPE['module']],checks=[dict(id=c['id'],status=c['status'],evidence=c['evidence']) for c in checks],
    handoffs=v6_handoffs,unresolved=role['unresolved'])
write(OUT/'candidate-result.json',candidate)
print(json.dumps(dict(art_sha256=artifact_sha,validator_status=report['status'],candidate_uri=base+'candidate-result.json',candidate_sha256=sha(OUT/'candidate-result.json'),asset_ids=[a['id'] for a in art['assets']],phase_counts=phase_counts),ensure_ascii=False))

# A later hard-requirement audit found a native state-after contradiction. Keep the
# preliminary PASS hash for provenance, then reproduce the blocked metadata.
audit_path=EVID/'hard-requirement-audit.json'
if audit_path.is_file():
    audit=json.loads(audit_path.read_text())
    preliminary_sha=sha(OUT/'candidate-result.json')
    if preliminary_sha != audit['prior_candidate_sha256']:
        raise RuntimeError('Preliminary candidate no longer matches the recorded audit baseline')
    role=json.loads((OUT/'role-result.json').read_text())
    for item in role['checks']:
        if item['id']=='handoff':
            item['status']='FAIL'
            item['finding']='六条V5语法目标断言通过，但硬终态在Art原生状态演算中仍为背包待收纳；当前Director无可引用phase，故语义交接未满足。'
            item['evidence'].append(base+'evidence/hard-requirement-audit.json')
    role['complete']=False
    write(OUT/'role-result.json',role)
    candidate=json.loads((OUT/'candidate-result.json').read_text())
    for item in candidate['checks']:
        if item['id']=='handoff':
            item['status']='FAIL'
            item['evidence'].append(base+'evidence/hard-requirement-audit.json')
    candidate['result_sha256']=sha(OUT/'role-result.json')
    write(OUT/'candidate-result.json',candidate)
    print(json.dumps(dict(revision_decision=audit['revision_decision'],current_candidate_sha256=sha(OUT/'candidate-result.json')),ensure_ascii=False))
