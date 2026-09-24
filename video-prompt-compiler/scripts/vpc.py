#!/usr/bin/env python3
"""Local compiler CLI; deliberately contains no upload or generation transport."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from vpc_core import ROOT, VERSION, canonical_count, compile_ir, digest, encoded, profile, read, validate


def emit(path, value):
    Path(path).write_bytes(encoded(value))


def runtime_files():
    paths=[ROOT/'SKILL.md',ROOT/'requirements.txt']
    for folder in ('scripts','schemas','registries','templates'):
        paths += [p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    return {str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def prepare(out):
    out=Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('输出目录非空；为修订选择新目录，避免混入旧提示词。')
    out.mkdir(parents=True,exist_ok=True)
    return out


def run_compile(ir, target, mode, base, out):
    cap=profile(target)
    artifact, context=compile_ir(ir,cap,mode,base)
    out=prepare(out)
    delivery=None
    emit(out/'avir.json',ir)
    emit(out/'capability-snapshot.json',cap)
    if artifact is None:
        emit(out/'diagnostics.json',{'status':'INVALID','diagnostics':context,'submitted':False})
        return {'status':'INVALID','diagnostics':context},2
    emit(out/'artifact.json',artifact)
    if ir.get('schema') in ('avir/1.1','avir/1.2'):
        emit(out/'detail-coverage.json', artifact['detail_coverage'])
        if ir['schema']=='avir/1.2':
            emit(out/'prompt-coverage.json', artifact['prompt_coverage'])
            emit(out/'prompt-review.json', artifact['prompt_review'])
        emit(out/'segment-proposals.json', artifact['segment_proposals'])
        if ir['schema']=='avir/1.2':
            import spatial_runtime as spatial
            from prompt_projection import render as render_prompt
            from prompt_projection import verify as verify_prompt
            from segment_delivery import build as build_delivery
            emit(out/'spatial-checks.json', artifact['spatial_checks'])
            segments=spatial.segment_plan(ir)
            for segment in segments:
                start,end=segment['project_start_ms'],segment['project_end_ms']
                blocks,coverage=spatial.render(ir,start,end)
                segment['prompt'],segment['prompt_coverage'],_,gaps=render_prompt(
                    ir,artifact['asset_bindings'],'unbound',mode,spatial,blocks,coverage,start,end)
                if gaps:
                    segment['status']='BLOCKED'
                    segment['reasons'] += ['PROMPT_COVERAGE:'+path for path in gaps]
            layout=read(ROOT/'templates/backends.json')['projection_v12'][cap['template']]['layout']
            delivery,prompt_files=build_delivery(ir,cap,mode,artifact,spatial,render_prompt,verify_prompt,
                                                 canonical_count,layout)
            emit(out/'segment-delivery.json',delivery)
            for name,content in prompt_files.items():
                (out/name).write_text(content,encoding='utf-8')
        else:
            from detail_runtime import segment_plan
            segments=segment_plan(ir)
        emit(out/'segment-plan.json', segments)
        emit(out/'production-specification.json', ir)
    emit(out/'context-ir.json',context)
    emit(out/'constraint-coverage.json',artifact['coverage'])
    emit(out/'loss-report.json',artifact['losses'])
    emit(out/'post-production.json',artifact['post_production'])
    (out/'prompt.txt').write_text(artifact['prompt']+'\n',encoding='utf-8')
    lines=[f"# {ir['project_id']} 制作合同 · revision {ir['revision']}",
           f"目标：{target} / {mode}；编译状态：{artifact['status']}；提交：否；媒体验收：NOT_RUN。",
           '合同是可审阅的制作规格，不是法律合同。',f"创作意图：{ir['intent']}"]
    for c in ir['contract']:
        lines += [f"\n## {c['id']} · {c['level']}",c['requirement'],
                  f"来源：{', '.join(c['source_refs'])}",
                  '字段：'+', '.join(x['path'] for x in c['checks']),
                  f"执行：{c['channel']} → {c['execution']}",
                  f"验收：{c['acceptance']['method']}；{c['acceptance']['criterion']}",
                  f"不支持时：{c['on_unsupported']}；真实验收：NOT_RUN"]
    lines += ['\n## 来源记录']+[f"- {s['id']}：{s['kind']} / {s['verification']}；{s['uri']}；{s['locator']}；{s['claim']}" for s in ir['sources']]
    (out/'production-contract.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    manifest={'compiler':f'video-prompt-compiler@{VERSION}','avir_schema':ir['schema'],'target':target,'mode':mode,
              'adapter_version':cap['version'],'rulepack':read(ROOT/'registries/rules.json')['version'],
              'templates':read(ROOT/'templates/backends.json')['version'],'retrieval_snapshot':read(ROOT/'registries/sources.json')['version'],
              'optimizer':'rules-only','input_hash':digest(ir),'artifact_hash':digest(artifact),
              'asset_base':str(Path(base).resolve()),'runtime_files':runtime_files(),
              'files':{p.name:sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}}
    manifest['build_id']=digest({k:v for k,v in manifest.items() if k!='asset_base'})
    emit(out/'compile-manifest.json',manifest)
    result={'status':artifact['status'],'target':target,'out':str(out.resolve()),'canonical_count':artifact['counts']['canonical_count'],
            'diagnostics':artifact['diagnostics'],'submitted':False}
    if delivery is not None:
        result['delivery_status']=delivery['status']
        result['prompt_files']=[str((out/part['prompt_file']).resolve()) for part in delivery['parts']]
    return result,0 if artifact['status']=='COMPILED' else 2


def verify(package):
    package=Path(package)
    m=read(package/'compile-manifest.json')
    failures=[]
    for name,expected in m['files'].items():
        p=package/name
        if Path(name).name!=name or not p.is_file() or sha256(p.read_bytes()).hexdigest()!=expected:
            failures.append(name)
    if digest(read(package/'avir.json'))!=m['input_hash'] or digest(read(package/'artifact.json'))!=m['artifact_hash']:
        failures.append('semantic_hash')
    if read(package/'artifact.json').get('schema')=='compiled-artifact/1.3':
        from prompt_projection import verify as verify_prompt
        import spatial_runtime as spatial
        ir,artifact=read(package/'avir.json'),read(package/'artifact.json')
        if (package/'prompt.txt').read_text(encoding='utf-8')!=artifact['prompt']+'\n':
            failures.append('prompt.txt')
        if read(package/'prompt-coverage.json')!=artifact['prompt_coverage']:
            failures.append('prompt-coverage.json')
        if read(package/'prompt-review.json')!=artifact['prompt_review']:
            failures.append('prompt-review.json')
        if sha256(artifact['prompt'].encode('utf-8')).hexdigest()!=artifact['prompt_review']['prompt_sha256']:
            failures.append('prompt_review_hash')
        if '\n\n'.join(row['text'] for row in artifact['trace'])!=artifact['prompt']:
            failures.append('trace')
        if verify_prompt(ir,artifact['prompt'],artifact['prompt_coverage'],spatial):
            failures.append('prompt_coverage')
        if (package/'segment-delivery.json').is_file():
            from prompt_projection import render as render_prompt
            from segment_delivery import build as build_delivery
            cap=read(package/'capability-snapshot.json')
            layout=read(ROOT/'templates/backends.json')['projection_v12'][cap['template']]['layout']
            expected,files=build_delivery(ir,cap,m['mode'],artifact,spatial,render_prompt,verify_prompt,
                                          canonical_count,layout)
            if read(package/'segment-delivery.json')!=expected:
                failures.append('segment-delivery.json')
            for name,content in files.items():
                if not (package/name).is_file() or (package/name).read_text(encoding='utf-8')!=content:
                    failures.append(name)
    if digest({k:v for k,v in m.items() if k not in ('asset_base','build_id')})!=m['build_id']:
        failures.append('build_id')
    if failures:
        raise ValueError('E_PACKAGE_CHANGED: '+', '.join(failures))
    return m


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('profiles',help='列出精确目标ID与已实现边界')
    p=sub.add_parser('validate');p.add_argument('input')
    p=sub.add_parser('compile');p.add_argument('input');p.add_argument('--target',required=True);p.add_argument('--mode',choices=['text','keyframe','reference','edit','extend'],default='text');p.add_argument('--out',required=True)
    p=sub.add_parser('route');p.add_argument('input');p.add_argument('--mode',default='text')
    p=sub.add_parser('batch');p.add_argument('input',help='NDJSON: input,target,mode；相对路径基于批文件');p.add_argument('--out',required=True)
    for name in ('verify','explain','replay'):
        p=sub.add_parser(name);p.add_argument('package')
        if name=='replay':p.add_argument('--out',required=True)
    args=parser.parse_args()
    try:
        code=0
        if args.command=='profiles':
            result=read(ROOT/'registries/capabilities.json')
        elif args.command=='validate':
            path=Path(args.input).resolve();errors=validate(read(path),path.parent)
            code=2 if any(e['severity'] in ('error','blocker') for e in errors) else 0
            result={'status':'INVALID' if any(e['severity']=='error' for e in errors) else 'BLOCKED' if code else 'VALID','diagnostics':errors}
        elif args.command=='compile':
            path=Path(args.input).resolve()
            result,code=run_compile(read(path),args.target,args.mode,path.parent,args.out)
        elif args.command=='route':
            path=Path(args.input).resolve();ir=read(path)
            result={'selection':'USER_DECISION_OR_HOST_POLICY','quality_ranking':None,'candidates':[]}
            for cap in read(ROOT/'registries/capabilities.json')['profiles']:
                artifact,details=compile_ir(ir,cap,args.mode,path.parent)
                result['candidates'].append({'target':cap['id'],'status':artifact['status'] if artifact else 'INVALID','diagnostics':artifact['diagnostics'] if artifact else details})
        elif args.command=='batch':
            path=Path(args.input).resolve();out=prepare(args.out);rows=[]
            for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
                if not line.strip():continue
                try:
                    job=json.loads(line)
                    if set(job)-{'input','target','mode'}:raise ValueError('未知批字段')
                    source=Path(job['input']);source=source if source.is_absolute() else path.parent/source
                    row,exit_code=run_compile(read(source),job['target'],job.get('mode','text'),source.parent,out/f'job-{n:04d}')
                    code=max(code,exit_code)
                except (OSError,ValueError,KeyError) as e:
                    row={'status':'INVALID','line':n,'message':str(e)};code=2
                rows.append(row)
            result={'jobs':rows,'submitted':False};emit(out/'batch-result.json',result)
        else:
            package=Path(args.package);manifest=verify(package)
            if args.command=='verify':result={'status':'VERIFIED','build_id':manifest['build_id']}
            elif args.command=='explain':result=read(package/'artifact.json')['trace']
            else:
                if manifest['runtime_files']!=runtime_files():raise ValueError('E_BUILD_DRIFT: 使用与manifest匹配的完整Skill构建包重放，不能混用新规则或新适配器。')
                result,code=run_compile(read(package/'avir.json'),manifest['target'],manifest['mode'],manifest['asset_base'],args.out)
                if read(Path(args.out)/'compile-manifest.json')['artifact_hash']!=manifest['artifact_hash']:
                    raise ValueError('E_REPLAY_CHANGED: 参考素材或编译结果发生变化。')
        print(json.dumps(result,ensure_ascii=False,indent=2));return code
    except (OSError,ValueError,KeyError,TypeError) as e:
        print(json.dumps({'status':'ERROR','message':str(e)},ensure_ascii=False),file=sys.stderr);return 1


if __name__=='__main__':
    raise SystemExit(main())
