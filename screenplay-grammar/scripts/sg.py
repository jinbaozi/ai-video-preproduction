#!/usr/bin/env python3
"""Offline screenplay authoring support. Creative prose is supplied by the current Agent."""
import argparse
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from screenplay_protocol import (ROOT,encoded,digest,file_hash,read,pointer,within,overlap,
    content_hash,validate,schema_errors,make_handoff,review_valid)


def route(project):
    task=project['task'];styles=read(ROOT/'registries/styles.json')['styles']
    request=task['style_request']
    for writer in read(ROOT/'registries/writers.json')['writers']:
        if request in (writer['name'],writer['english_name']):request=writer['profile']
    if request and request not in {x['id'] for x in styles}:raise ValueError('Unknown style/writer; no silent fallback: '+request)
    accepted=[];rejected=[]
    for style in styles:
        conflict=set(task['forbidden_techniques'])&set(style['techniques'])
        if conflict:rejected.append({'id':style['id'],'reason':'forbidden techniques: '+','.join(sorted(conflict))});continue
        if request and style['id']!=request:continue
        matches=sorted(set(task['tags'])&set(style['tags']))
        accepted.append({'id':style['id'],'score':len(matches),'matches':matches,'techniques':style['techniques']})
    if not accepted:raise ValueError('No style satisfies constraints')
    accepted.sort(key=lambda s:(-s['score'],s['id']!='character_causal',s['id']))
    return {'selected':accepted[0],'alternatives':accepted[1:],'rejected':rejected,
            'overlays':project['culture']['overlays'],'basis':'Deterministic tag heuristic, not measured writing quality'}


def initialize(project_id,title,brief,output):
    return dict(schema='script-ir/1.0',project_id=project_id,revision=1,title=title,language='zh-CN',status='DRAFT',
        task={'operation':'story' if output=='story' else 'create','output':output,'tags':[],'style_request':None,'forbidden_techniques':[]},
        sources=[{'id':'USER','kind':'user','uri':'inline:user','locator':'request','excerpt':brief,'sha256':None,'verification':'provided'}],source_refs=['USER'],
        canon={'ref':None,'facts':[],'proposals':[]},characters=[],propositions=[],
        narrative={'premise':'','ending':'','initial_knowledge':[],'events':[],'reveal_order':[],'promises':[]},scenes=[],
        culture={'mode':'invented','overlays':[],'claims':[]},timing={'target_seconds':None,'estimated_range_seconds':None,'measured_seconds':None,'evidence':None},
        contract={'scope':brief,'deliverables':[output],'clauses':[],'checks':[]},locks=[],
        rewrite_scope={'level':'structure','allowed_paths':['/scenes','/narrative','/characters','/propositions'],'preserve_paths':[],'allow_new_events':True},
        review={'status':'NOT_RUN','content_sha256':None,'reviewer':None,'findings':[]},open_issues=['Agent must author the requested prose and complete the production contract.'])


def apply_patch(project,patch,base=None):
    errors=validate(project,base)+schema_errors(patch,'patch')
    if errors:raise ValueError('; '.join(errors))
    if patch['base_sha256']!=content_hash(project):raise ValueError('Patch base differs')
    scope=project['rewrite_scope'];level=scope['level']
    if level=='diagnose':raise ValueError('Diagnose is read-only')
    result=deepcopy(project);paths=[]
    protected=[x['path'] for x in project['locks']]+scope['preserve_paths']
    for change in patch['changes']:
        path=change['path']
        if any(overlap(path,p) for p in paths):raise ValueError('Overlapping patch paths')
        paths.append(path)
        if not any(within(path,r) for r in ('/scenes','/narrative','/characters','/propositions','/culture')):raise ValueError('Protected project metadata: '+path)
        if not any(within(path,a) for a in scope['allowed_paths']):raise ValueError('Outside authorized paths: '+path)
        if any(overlap(path,p) for p in protected):raise ValueError('Patch touches locked or preserved content: '+path)
        if level=='line' and not (path.startswith('/scenes/') and path.endswith('/text')):raise ValueError('Line edits replace block text only')
        if level=='scene' and not path.startswith('/scenes/'):raise ValueError('Scene edits stay in authorized scenes')
        pointer(result,path) # Replace only; absent paths and append syntax are rejected.
        parent,key=path.rsplit('/',1);target=pointer(result,parent)
        if isinstance(target,list):target[int(key)]=deepcopy(change['value'])
        else:target[key.replace('~1','/').replace('~0','~')]=deepcopy(change['value'])
    if not scope['allow_new_events'] and result['narrative']['events']!=project['narrative']['events']:raise ValueError('Event changes not authorized')
    result['revision']+=1;result['status']='DRAFT'
    result['review']={'status':'NOT_RUN','content_sha256':None,'reviewer':None,'findings':[]}
    errors=validate(result,base)
    if errors:raise ValueError('; '.join(errors))
    return result


def diff(left,right,path=''):
    if type(left)!=type(right):return [{'path':path,'before':left,'after':right}]
    if isinstance(left,dict):
        rows=[]
        for key in sorted(left.keys()|right.keys()):
            p=path+'/'+key.replace('~','~0').replace('/','~1')
            if key not in left or key not in right:rows.append({'path':p,'before':left.get(key),'after':right.get(key)})
            else:rows+=diff(left[key],right[key],p)
        return rows
    if isinstance(left,list):
        if len(left)!=len(right):return [{'path':path,'before':left,'after':right}]
        return [row for i,(a,b) in enumerate(zip(left,right)) for row in diff(a,b,path+'/'+str(i))]
    return [] if left==right else [{'path':path,'before':left,'after':right}]


def render(project):
    names={c['id']:c['name'] for c in project['characters']}
    md=['# '+project['title'],''];fountain=['Title: '+project['title'],''];mapping=[];dialogue=[]
    story=project['task']['output']=='story'
    for si,scene in enumerate(project['scenes']):
        md+=['## '+scene['heading'],'']
        if not story:fountain+=['.'+scene['heading'],'']
        for bi,b in enumerate(scene['blocks']):
            speaker=names.get(b['speaker'],b['speaker'] or '')
            label={'narration':'旁白','inner_voice':'内心声','sound':'声音','text':'画面文字'}.get(b['kind'])
            line=(speaker+'：“'+b['text']+'”') if b['kind']=='dialogue' else (f'【{label}'+('·'+speaker if speaker else '')+'】'+b['text'] if label else b['text'])
            start=len(md)+1;md+=line.splitlines()+['']
            row={'block_id':b['id'],'source_refs':b['source_refs'],'script_path':f'/scenes/{si}/blocks/{bi}','markdown_lines':[start,len(md)-1]}
            if not story:
                fs=len(fountain)+1
                if b['kind']=='dialogue':fountain+=['@'+speaker,*b['text'].splitlines(),'']
                else:fountain+=['!'+line.replace('\n','\n!'),'']
                row['fountain_lines']=[fs,len(fountain)-1]
            mapping.append(row)
            if b['kind'] in ('dialogue','narration','inner_voice'):
                dialogue.append({'id':b['id'],'scene_id':scene['id'],'speaker':b['speaker'],'kind':b['kind'],'text':b['text'],'source_refs':b['source_refs']})
    return '\n'.join(md)+'\n','\n'.join(fountain)+'\n',mapping,dialogue


def compile_project(project,base,out):
    errors=validate(project,base)
    if errors:raise ValueError('; '.join(errors))
    out=Path(out).resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):raise ValueError('Output must be a new or empty directory')
    # Check all paths before writing; compilation snapshots dependencies without changing authority.
    p=deepcopy(project);copies={}
    for source in p['sources']:
        if source['sha256'] and '://' not in source['uri']:
            path=(Path(base)/source['uri']).resolve();name='sources/'+source['sha256']+'-'+path.name
            copies[name]=path.read_bytes();source['uri']=name
    if p['canon']['ref']:
        ref=p['canon']['ref'];path=(Path(base)/ref['uri']).resolve();name='sources/'+ref['sha256']+'-canon.json'
        copies[name]=path.read_bytes();ref['uri']=name
    md,fountain,mapping,dialogue=render(p);story=p['task']['output']=='story'
    name='story.md' if story else 'screenplay.md'
    snapshot=encoded(p);handoff=make_handoff(p,'script-ir.json',digest(p))
    final_errors=validate(p,final=True)
    report={'status':'STATIC_VALID','delivery':'READY' if not final_errors else 'DRAFT','semantic_review':'REVIEW_ATTESTED' if review_valid(p) else 'NOT_RUN','final_issues':final_errors,'media':'NOT_RUN','professional_blind_review':'NOT_RUN'}
    files={**copies,name:md.encode(),'script-ir.json':snapshot,
        'narrative-ir.json':encoded({'schema':'narrative-ir/1.0','read_only':True,'script_sha256':digest(p),'narrative':p['narrative'],'characters':p['characters'],'propositions':p['propositions']}),
        'dialogue.json':encoded(dialogue),'source-map.json':encoded(mapping),'production-contract.json':encoded(p['contract']),
        'production-contract.md':('\n'.join(['# 制作合同',p['contract']['scope']]+[f"- {c['id']} [{c['priority']}] {c['requirement']}\n  来源：{', '.join(c['source_refs'])}；正文：{', '.join(c['paths'])}；实现：{c['realization']}；步骤：{' → '.join(c['steps'])}；验收：{', '.join(c['check_ids'])}" for c in p['contract']['clauses']])+'\n').encode(),
        'checks.json':encoded(report),'director-handoff.json':encoded(handoff)}
    if not story:files['screenplay.fountain']=fountain.encode()
    manifest={'schema':'screenplay-compile/1.0','input_content_sha256':content_hash(project),'project_id':p['project_id'],'revision':p['revision'],
        'status':report['delivery'],'submitted':False,'media':'NOT_RUN','files':{k:{'sha256':__import__('hashlib').sha256(v).hexdigest(),'bytes':len(v)} for k,v in sorted(files.items())},
        'representation_changes':[] if story else ['Fountain subset: narrative, knowledge, locks and contracts remain in JSON; no arbitrary round-trip import.']}
    files['compile-manifest.json']=encoded(manifest);out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.screenplay-') as tmp:
        staged=Path(tmp)/'bundle';staged.mkdir()
        for name,data in files.items():
            target=staged/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        if out.exists():out.rmdir()
        staged.rename(out)
    return manifest


def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(encoded(value))


def relocate_references(project,base):
    result=deepcopy(project)
    for source in result['sources']:
        if source['sha256'] and '://' not in source['uri']:
            source['uri']=str((Path(base)/source['uri']).resolve())
    if result['canon']['ref']:
        ref=result['canon']['ref'];ref['uri']=str((Path(base)/ref['uri']).resolve())
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('init');q.add_argument('--project-id',required=True);q.add_argument('--title',required=True);q.add_argument('--brief',required=True);q.add_argument('--output',choices=['screenplay','story'],default='screenplay');q.add_argument('--out',required=True)
    for name in ('route','validate','compile','apply','diff'):
        q=sub.add_parser(name);q.add_argument('input')
        if name=='validate':q.add_argument('--final',action='store_true')
        if name in ('apply','diff'):q.add_argument('other')
        if name in ('compile','apply'):q.add_argument('--out',required=True)
    a=p.parse_args()
    try:
        if a.command=='init':
            value=initialize(a.project_id,a.title,a.brief,a.output);errors=validate(value)
            if errors:raise ValueError('; '.join(errors))
            write_new(a.out,value);result={'status':'DRAFT','out':a.out}
        else:
            project=read(a.input);base=Path(a.input).resolve().parent
            if a.command=='validate':
                errors=validate(project,base,a.final);result={'status':'INVALID' if errors else 'STATIC_VALID','errors':errors,'semantic_review':'REVIEW_ATTESTED' if not errors and review_valid(project) else 'NOT_RUN'}
            elif a.command=='route':result=route(project)
            elif a.command=='diff':result={'changes':diff(project,read(a.other))}
            elif a.command=='apply':
                value=relocate_references(apply_patch(project,read(a.other),base),base);write_new(a.out,value);result={'status':'DRAFT','revision':value['revision'],'out':a.out}
            else:result=compile_project(project,base,a.out)
        print(encoded(result).decode());return 2 if result.get('status')=='INVALID' else 0
    except (ValueError,OSError,KeyError,IndexError,TypeError) as e:
        print(encoded({'status':'ERROR','error':str(e)}).decode(),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
