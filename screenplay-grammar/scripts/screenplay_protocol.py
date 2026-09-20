"""Screenplay protocol 1.0. Distributed identically to the director; no sibling imports."""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]

def encoded(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()

def digest(value):return sha256(encoded(value)).hexdigest()
def file_hash(path):return sha256(Path(path).read_bytes()).hexdigest()
def read(path):
    def pairs(rows):
        result={}
        for k,v in rows:
            if k in result:raise ValueError('Duplicate JSON key: '+k)
            result[k]=v
        return result
    def number(value):
        result=float(value)
        if not math.isfinite(result):raise ValueError('Non-finite number: '+value)
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_float=number,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Non-finite number: '+v)))

def pointer(value,path):
    if path=='':return value
    if not path.startswith('/'):raise ValueError('Expected JSON Pointer')
    for key in path[1:].split('/'):
        key=key.replace('~1','/').replace('~0','~')
        if isinstance(value,list):
            if not key.isdigit() or (len(key)>1 and key[0]=='0'):raise ValueError('Invalid array index')
            value=value[int(key)]
        else:value=value[key]
    return value

def within(path,parent):return path==parent or path.startswith(parent+'/')
def overlap(a,b):return within(a,b) or within(b,a)

def content_hash(value):
    data=deepcopy(value);data.pop('review',None)
    if isinstance(data.get('timeline'),dict):data['timeline'].pop('semantic_review',None)
    for source in data.get('sources',[]):
        if source.get('sha256') or source.get('file_sha256') or 'shots' in data:source.pop('uri',None)
    # Canon byte hash remains authoritative through relocation; the URI is transport only.
    if data.get('canon',{}).get('ref'):data['canon']['ref'].pop('uri',None)
    return digest(data)

def schema_errors(value,name):
    directory=ROOT/'schemas'
    if not (directory/'project.schema.json').exists():directory=directory/'screenplay'
    schema=read(directory/(name+'.schema.json'))
    return [f'/{"/".join(map(str,e.absolute_path))}: {e.message}' for e in
            sorted(Draft202012Validator(schema).iter_errors(value),key=lambda e:str(e.absolute_path))]

def assert_check(value,check):
    try:
        actual=pointer(value,check['path'])
        return (check['op']=='exists' or check['op']=='equals' and actual==check.get('value') or
                check['op']=='contains' and check.get('value') in actual)
    except (KeyError,IndexError,ValueError,TypeError):return False

def review_valid(project):
    r=project['review']
    return r['status']=='PASS' and r['content_sha256']==content_hash(project) and bool(r['reviewer'] and r['findings'])

def validate(project,base=None,final=False):
    errors=schema_errors(project,'project')
    if errors:return errors
    def err(message):errors.append(message)
    def unique(rows,label):
        ids=[x['id'] for x in rows]
        if len(ids)!=len(set(ids)):err('Duplicate IDs: '+label)
        return {x['id']:x for x in rows}
    sources=unique(project['sources'],'sources');chars=unique(project['characters'],'characters')
    props=unique(project['propositions'],'propositions');scenes=unique(project['scenes'],'scenes')
    events=unique(project['narrative']['events'],'events')
    checks=unique(project['contract']['checks'],'checks');unique(project['contract']['clauses'],'clauses')
    unique(project['canon']['facts'],'canon facts');unique(project['canon']['proposals'],'canon proposals')
    unique(project['culture']['claims'],'culture claims');unique(project['narrative']['promises'],'promises')
    blocks={};block_scene={}
    for scene in project['scenes']:
        for block in scene['blocks']:
            if block['id'] in blocks:err('Duplicate block ID: '+block['id'])
            blocks[block['id']]=block;block_scene[block['id']]=scene['id']
            if block['speaker'] is not None and block['speaker'] not in chars:err('Unknown speaker: '+block['id'])
            if block['kind']=='dialogue' and block['speaker'] is None:err('Dialogue requires speaker: '+block['id'])
            if block['kind']=='inner_voice' and block['speaker'] is None:err('Inner voice requires an owner: '+block['id'])
            if project['task']['output']=='story' and block['kind'] not in ('prose','dialogue','narration','inner_voice','text'):
                err('Story output requires prose-compatible blocks: '+block['id'])
    def refs(value):
        if isinstance(value,dict):
            for ref in value.get('source_refs',[]):
                if ref not in sources:err('Unknown source: '+ref)
            for v in value.values():refs(v)
        elif isinstance(value,list):
            for v in value:refs(v)
    refs(project)
    for source in sources.values():
        uri=source['uri']
        if source['sha256'] and '://' not in uri and base is not None:
            path=Path(base)/uri
            if not path.is_file() or file_hash(path)!=source['sha256']:err('Source missing or changed: '+source['id'])
            elif source['excerpt'] not in path.read_text(encoding='utf-8'):err('Source excerpt differs: '+source['id'])
        if source['verification'] in ('read','provided') and source['kind'] not in ('design',) and not source['sha256']:
            # Inline supplied text is itself retained evidence, not a claimed file inspection.
            if not uri.startswith('inline:'):err('Read/provided source needs file hash or inline text: '+source['id'])
    canon=project['canon']['ref']
    if canon and project['canon']['facts']:err('External Canon owns facts; do not maintain an editable duplicate')
    if canon and base is not None:
        path=Path(base)/canon['uri']
        if not path.is_file() or file_hash(path)!=canon['sha256']:err('Canon missing or changed')
    knowledge={}
    def valid_k(k):
        if k['actor'] not in chars and k['actor']!='AUDIENCE':err('Unknown knowledge actor: '+k['actor'])
        if k['proposition'] not in props:err('Unknown proposition: '+k['proposition'])
    for k in project['narrative']['initial_knowledge']:
        valid_k(k);key=(k['actor'],k['proposition'])
        if key in knowledge:err('Duplicate initial knowledge')
        knowledge[key]=k['state']
    seen=set()
    for event in project['narrative']['events']:
        if event['scene_id'] not in scenes:err('Unknown event scene: '+event['id'])
        for bid in event['block_ids']:
            if bid not in blocks or block_scene.get(bid)!=event['scene_id']:err('Event block outside scene: '+event['id'])
        if any(c not in seen for c in event['causes']):err('Cause missing, future, or cyclic: '+event['id'])
        for k in event['preconditions']:
            valid_k(k)
            if knowledge.get((k['actor'],k['proposition']),'unknown')!=k['state']:err('Knowledge precondition fails: '+event['id'])
        for k in event['updates']:
            valid_k(k);knowledge[(k['actor'],k['proposition'])]=k['state']
        seen.add(event['id'])
    order=project['narrative']['reveal_order']
    if len(order)!=len(set(order)) or any(e not in events for e in order):err('Invalid reveal order')
    for promise in project['narrative']['promises']:
        if promise['setup_event'] not in events or (promise['payoff_event'] and promise['payoff_event'] not in events):err('Unknown promise event')
        if promise['status']=='fulfilled' and not promise['payoff_event']:err('Fulfilled promise needs payoff')
    for claim in project['culture']['claims']:
        if claim['kind']=='historical' and claim['verified']:
            if not any(sources[r]['kind']=='official' and sources[r]['verification']=='read' for r in claim['source_refs'] if r in sources):err('Verified historical claim needs read primary evidence: '+claim['id'])
        if claim['kind']=='historical' and not claim['verified'] and final:err('Unverified historical claim: '+claim['id'])
    for lock in project['locks']:
        try:
            if not any(within(lock['path'],r) for r in ('/scenes','/narrative','/characters','/propositions','/canon','/culture')):err('Invalid lock root')
            if digest(pointer(project,lock['path']))!=lock['sha256']:err('Lock changed: '+lock['path'])
        except (KeyError,IndexError,TypeError,ValueError):err('Invalid lock path: '+lock['path'])
    for path in project['rewrite_scope']['preserve_paths']+project['rewrite_scope']['allowed_paths']:
        try:pointer(project,path)
        except (KeyError,IndexError,TypeError,ValueError):err('Invalid rewrite path: '+path)
    for clause in project['contract']['clauses']:
        for path in clause['paths']:
            try:
                pointer(project,path)
                if not any(within(path,r) for r in ('/scenes','/narrative','/characters','/propositions')):err('Contract must target story content: '+clause['id'])
            except (KeyError,IndexError,ValueError,TypeError):err('Invalid contract path: '+path)
        for cid in clause['check_ids']:
            check=checks.get(cid)
            if check is None:err('Unknown contract check: '+cid)
            elif clause['priority']=='hard' and not check['blocking']:err('Hard clause needs blocking check: '+cid)
    for check in checks.values():
        if check['method']=='static' and not check['assertions']:err('Static check needs assertions: '+check['id'])
        if not all(assert_check(project,a) for a in check['assertions']):err('Contract assertion failed: '+check['id'])
    timing=project['timing'];estimate=timing['estimated_range_seconds']
    if estimate is not None and (len(estimate)!=2 or estimate[0]>estimate[1]):err('Invalid estimated range')
    if timing['measured_seconds'] is not None and not timing['evidence']:err('Measured timing requires evidence')
    if project['review']['status']=='PASS' and not review_valid(project):err('Stale or incomplete semantic review')
    if final:
        if project['status']!='READY' or not project['scenes'] or not project['narrative']['premise']:err('Draft is not a completed deliverable')
        if project['open_issues']:err('Unresolved issues remain')
        if not project['contract']['clauses']:err('Final project needs production contract')
        if not review_valid(project):err('Current semantic review required')
        if any(p['status']=='proposed' for p in project['canon']['proposals']):err('Canon proposals require reconciliation')
    return errors

def requirements(project):
    rows=[]
    for c in project['contract']['clauses']:
        if c['priority']=='hard':rows.append((c['id'],c['requirement'],c['paths'],False))
    for i,lock in enumerate(project['locks']):rows.append(('LOCK_'+str(i),lock['meaning'],[lock['path']],True))
    for si,scene in enumerate(project['scenes']):
        for bi,b in enumerate(scene['blocks']):
            if b['kind']=='dialogue':
                rows.append(('DIALOGUE_'+b['id'],'保留台词原文及说话人 '+b['speaker'],[f'/scenes/{si}/blocks/{bi}/text',f'/scenes/{si}/blocks/{bi}/speaker'],True))
    for key in ('ending','events','reveal_order'):
        if project['narrative'][key]:rows.append(('NARRATIVE_'+key,'保留叙事语义 '+key,['/narrative/'+key],False))
    return [dict(id='screenplay:'+cid,owner='screenplay',statement=statement,source_paths=paths,
                 source_fingerprint=digest([pointer(project,p) for p in paths]),
                 source_values=[deepcopy(pointer(project,p)) for p in paths],literal=literal)
            for cid,statement,paths,literal in rows]

FREEDOM=['景别、机位与运镜','在剧情动作与结果内的表演和走位','不改变信息顺序约束的覆盖与剪辑','不改词义和说话归属的声音处理']

def make_handoff(project,uri,checksum):
    return dict(schema='screenplay-handoff/1.0',project_id=project['project_id'],revision=project['revision'],
                script_ref={'uri':str(uri),'sha256':checksum},content_sha256=content_hash(project),
                ready=not validate(project,final=True),requirements=requirements(project),director_freedom=FREEDOM)

def load_handoff(path):
    path=Path(path).resolve();h=read(path);errors=schema_errors(h,'handoff')
    if errors:raise ValueError('; '.join(errors))
    ref=path.parent/h['script_ref']['uri']
    if not ref.is_file() or file_hash(ref)!=h['script_ref']['sha256']:raise ValueError('Screenplay snapshot missing or changed')
    project=read(ref);errors=validate(project,ref.parent,final=True)
    if errors:raise ValueError('; '.join(errors))
    if h!=make_handoff(project,h['script_ref']['uri'],file_hash(ref)):raise ValueError('Stale or modified screenplay handoff')
    return h,project

def validate_mapping(director,required,mapping,screenplay_sha):
    errors=schema_errors(mapping,'director-map')
    if errors:return errors
    if mapping['screenplay_sha256']!=screenplay_sha:errors.append('Stale screenplay binding')
    if mapping['director_sha256']!=content_hash(director):errors.append('Stale director semantic mapping')
    rows=mapping['mappings'];by_id={r['requirement_id']:r for r in rows}
    if len(by_id)!=len(rows) or set(by_id)!={r['id'] for r in required}:errors.append('Missing, extra or duplicate screenplay mappings')
    clauses={c['id']:c for c in director.get('contract',{}).get('clauses',[])}
    for req in required:
        row=by_id.get(req['id'])
        if not row:continue
        if row['source_fingerprint']!=req['source_fingerprint']:errors.append('Stale requirement: '+req['id'])
        clause=clauses.get(row['target_clause'])
        if not clause or clause['priority']!='hard':errors.append('Missing native hard director clause: '+req['id']);continue
        for check in row['target_checks']:
            p=check['path']
            if not any(within(p,r) for r in ('/shots','/beats','/entities','/scenes','/timeline')):errors.append('Mapping must target realization, not a note: '+req['id'])
            if not any(overlap(p,q) for q in clause['paths']):errors.append('Mapping not covered by native clause: '+req['id'])
            if not assert_check(director,check):errors.append('Director changed screenplay realization: '+req['id'])
        if req['literal']:
            for expected in req['source_values']:
                if not any(c['op']=='equals' and c.get('value')==expected for c in row['target_checks']):errors.append('Literal content changed: '+req['id'])
        if req['id'].startswith('screenplay:DIALOGUE_'):
            text,speaker=req['source_values']
            paired=False
            for c in row['target_checks']:
                if c['path'].endswith('/text') and c['op']=='equals' and c.get('value')==text:
                    parent=c['path'].rsplit('/',1)[0]
                    try:
                        utterance=pointer(director,parent)
                        paired=paired or utterance.get('speaker_id')==speaker
                    except (KeyError,IndexError,TypeError,ValueError):pass
            if not paired:errors.append('Dialogue text and speaker must belong to the same utterance: '+req['id'])
    return errors

def check_handoff(director,handoff_path,mapping_path):
    h,project=load_handoff(handoff_path)
    if director['project_id']!=h['project_id']:return ['Different screenplay/director project IDs']
    return validate_mapping(director,h['requirements'],read(mapping_path),h['content_sha256'])
