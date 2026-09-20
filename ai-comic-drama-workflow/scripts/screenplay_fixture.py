"""Bind the pre-authored cafe screenplay for offline examples/tests, not a writing engine."""
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def screenplay(kernel):
    from ai_comic_drama_workflow.v5_modules import read
    core=kernel.screenplay_protocol();value=read(ROOT/'examples/v5/cafe/screenplay.json')
    old=value['sources'][0]['id'];source=kernel.state['sources'][0]
    def replace(obj):
        if isinstance(obj,dict):
            for k,v in obj.items():
                if k=='source_refs':obj[k]=[source['id'] if x==old else x for x in v]
                else:replace(v)
        elif isinstance(obj,list):
            for v in obj:replace(v)
    replace(value);value['sources'][0].update(id=source['id'],uri=str(kernel.path(source['uri'])),sha256=source['sha256'])
    canon=kernel.state['artifacts']['canon'];value['canon']['ref']={'uri':str(kernel.path(canon['uri'])),'sha256':canon['sha256']}
    value['review']['content_sha256']=core.content_hash(value)
    return value


def director_mapping(task,director):
    # Load the owned protocol from the selected director module, never a sibling checkout.
    from ai_comic_drama_workflow.v5_modules import load_python,read
    core=load_python(task['module']['path'],'screenplay_protocol.py')
    source=next(i for i in task['inputs'] if i['slot']=='screenplay');script=read(source['uri'])
    if script.get('schema')!='script-ir/1.0':return []
    authored={r['requirement_id']:r for r in read(ROOT/'examples/v5/cafe/screenplay-mapping.json')}
    rows=[]
    for req in task['handoff']['required_handoffs']:
        spec=deepcopy(authored[req['id']])
        if director.get('timeline'):
            spec['paths']=['/timeline/actions' if p=='/shots/2/phases' else p for p in spec['paths']]
        if director.get('timeline') and req['id']=='screenplay:DIALOGUE_LINE':
            index=next(i for i,a in enumerate(director['timeline']['audio_events']) if a['id']=='D_B')
            spec['paths']=[f'/timeline/audio_events/{index}/text',f'/timeline/audio_events/{index}/speaker_id']
        clause=next(c for c in director['contract']['clauses'] if c['id']==spec['target_clause'])
        # Extend this fixture's actual native clause to cover its reviewed realizations.
        for path in spec['paths']:
            if path not in clause['paths']:clause['paths'].append(path)
        rows.append(dict(requirement_id=req['id'],source_fingerprint=req['source_fingerprint'],target_clause=spec['target_clause'],
                         target_checks=[{'path':p,'op':'equals','value':deepcopy(core.pointer(director,p))} for p in spec['paths']],reason=spec['reason']))
    if director.get('timeline'):
        support=load_python(task['module']['path'],'v52_support.py' if director['schema_version']=='1.2' else 'v51_support.py')
        director['timeline']['semantic_review']['input_sha256']=support.detail.content_hash(director)
    stamp=dict(screenplay_sha256=core.content_hash(script),director_sha256=core.content_hash(director),
               reviewer='authored-cafe-fixture / static test',findings=['固定咖啡馆样例与原文对读；仅测试协议，不代表真实媒体通过。'])
    return [dict(**row,review=stamp) for row in rows]
