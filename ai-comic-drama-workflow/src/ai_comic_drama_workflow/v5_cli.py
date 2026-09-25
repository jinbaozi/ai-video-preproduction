"""Current-agent V5 command surface; legacy projects are read-only."""
import argparse
import json
from pathlib import Path
from .v5 import V5Kernel
from .v5_modules import ROOT, read, default_lock


def main(argv=None):
    p=argparse.ArgumentParser(prog='ai-comic-drama')
    commands=p.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init');init.add_argument('inputs',nargs='+');init.add_argument('--project',required=True)
    init.add_argument('--project-id',default='PROJECT');init.add_argument('--delivery',choices=['full','text-only'],default='full')
    init.add_argument('--target');init.add_argument('--mode',choices=['text','reference','keyframe','edit','extend'],default=None)
    init.add_argument('--production-target',choices=['none','video'],default='none')
    init.add_argument('--no-run',action='store_true')
    for command in ('run','status','validate','export','submit','resume','request-decision','host','revise','add','import-artifact','import-compiled','compile','begin-image','update-modules','recover-image','import-observation'):
        c=commands.add_parser(command);c.add_argument('project')
        if command=='validate':c.add_argument('--final',action='store_true')
        if command=='export':c.add_argument('--draft',action='store_true')
        if command in ('submit','resume','host'):
            c.add_argument('--'+{'submit':'result','resume':'decision','host':'capabilities'}[command],required=True)
        if command=='revise':
            c.add_argument('kind');c.add_argument('--shot-id');c.add_argument('--action-id');c.add_argument('--node-id');c.add_argument('--track-id');c.add_argument('--scene-id');c.add_argument('--asset-id');c.add_argument('--target');c.add_argument('--mode')
        if command=='add':c.add_argument('inputs',nargs='+')
        if command=='import-artifact':
            c.add_argument('kind');c.add_argument('input');c.add_argument('--scene-id');c.add_argument('--locks');c.add_argument('--handoff')
        if command=='import-observation':c.add_argument('bundle')
        if command=='import-compiled':c.add_argument('package')
        if command=='compile':c.add_argument('--mapping')
        if command=='request-decision':c.add_argument('--proposal',required=True)
        if command=='begin-image':c.add_argument('--task-id',required=True)
        if command=='update-modules':c.add_argument('--lock',required=True);c.add_argument('--archives',required=True)
        if command=='recover-image':c.add_argument('--evidence',required=True)
    c=commands.add_parser('copy-project');c.add_argument('project');c.add_argument('--destination',required=True)
    commands.add_parser('doctor')
    prod=commands.add_parser('production');prod.add_argument('project')
    prod_commands=prod.add_subparsers(dest='production_command',required=True)
    for name in ('plan','execute','receive-take','review-take','check-adjacent','assemble','status'):
        sub=prod_commands.add_parser(name)
        if name=='plan':
            sub.add_argument('--compile',required=True);sub.add_argument('--request',required=True)
            sub.add_argument('--manifest-sha',required=True);sub.add_argument('--attachments',required=True)
            sub.add_argument('--max-attempts',type=int,default=3);sub.add_argument('--project-cap',type=int,default=9)
        if name=='execute':sub.add_argument('--job',required=True);sub.add_argument('--out',required=True)
        if name=='receive-take':
            sub.add_argument('--job',required=True);sub.add_argument('--file',required=True);sub.add_argument('--probe',required=True)
        if name=='review-take':sub.add_argument('--plan',required=True);sub.add_argument('--observations',required=True);sub.add_argument('--shot',required=True)
        if name=='check-adjacent':sub.add_argument('--plan',required=True);sub.add_argument('--observations',required=True);sub.add_argument('--left',required=True);sub.add_argument('--right',required=True)
        if name=='assemble':sub.add_argument('--edl',required=True);sub.add_argument('--out',required=True);sub.add_argument('--spec',required=True)
    a=p.parse_args(argv)
    try:
        if a.command=='doctor':
            r={'workflow':'V5','execution_mode':'current-agent','python':'3.12+',
               'image_gen':'host-only; capability requires actual tool evidence','modules':default_lock(ROOT)}
        elif a.command=='init':
            k=V5Kernel.initialize(a.project,a.inputs,project_id=a.project_id,delivery=a.delivery,target=a.target,mode=a.mode,production_target=a.production_target)
            r=k.status() if a.no_run else k.run()
        elif a.command=='copy-project':r=V5Kernel.copy_project(a.project,a.destination).status()
        elif a.command=='production':r=_production(a)
        else:
            k=V5Kernel(a.project)
            if a.command in ('run','status'):r=getattr(k,a.command)()
            elif a.command=='compile':r=k.compile(a.mapping)
            elif a.command=='import-observation':r=k.import_observation(a.bundle)
            elif a.command=='import-compiled':r=k.import_compiled(a.package)
            elif a.command=='validate':r=k.validate(a.final)
            elif a.command=='export':r=k.export(a.draft)
            elif a.command=='submit':r=k.submit(a.result)
            elif a.command=='resume':r=k.resume(a.decision)
            elif a.command=='request-decision':r=k.request_decision(a.proposal)
            elif a.command=='host':
                info=read(Path(a.capabilities));r=k.host(info['image_capability'],info['evidence'],info.get('video_capabilities'))
            elif a.command=='revise':r=k.revise(a.kind,shot_id=a.shot_id,action_id=a.action_id,node_id=a.node_id,track_id=a.track_id,scene_id=a.scene_id,asset_id=a.asset_id,target=a.target,mode=a.mode)
            elif a.command=='add':r=k.add(a.inputs)
            elif a.command=='import-artifact':
                r=k.import_artifact(a.kind,a.input,scope={'scene_ids':[a.scene_id]} if a.scene_id else None,
                                    locks=read(Path(a.locks))['locks'] if a.locks else None,
                                    handoff=read(Path(a.handoff)) if a.handoff else None)
            elif a.command=='begin-image':r=k.begin_image(a.task_id)
            elif a.command=='update-modules':r=k.update_modules(a.lock,a.archives)
            elif a.command=='recover-image':r=k.recover_image(a.evidence)
        print(json.dumps(r,ensure_ascii=False,indent=2))
        return 2 if r.get('status')=='BLOCKED' or r.get('valid') is False else 0
    except (ValueError,OSError,KeyError,IndexError,StopIteration) as e:
        print(json.dumps({'status':'ERROR','error':str(e)},ensure_ascii=False));return 1


def _production(a):
    from .acceptance import adjacent_decision, decide, freeze_plan, shot_decision
    from .assembly import assemble_ffmpeg, export_hypit, export_jianying, timelines, validate_edl
    from .executors.agnes_api import AgnesApiExecutor
    from .executors.manual import ManualExecutor
    from .production import ProductionLedger
    k=V5Kernel(a.project)
    ledger=ProductionLedger(k)
    command=a.production_command
    if command=='status':
        return {'jobs':ledger.jobs(),'executions':ledger.records(),'takes':ledger.takes(),
                'blockers':ledger.video_delivery_blockers(),'production_target':k.production_target()}
    if command=='plan':
        compiled=read(Path(a.compile));request=next(r for r in compiled['requests'] if r['id']==a.request)
        return ledger.plan_job(request,a.manifest_sha,read(Path(a.attachments)),request['scope'].get('shot_ids',[]),
                               {'max_attempts':a.max_attempts,'project_cap':a.project_cap})
    if command=='execute':
        from .executors.agnes_http import AgnesHttpTransport
        return AgnesApiExecutor(ledger,AgnesHttpTransport()).execute(a.job,a.out)
    if command=='receive-take':
        return ManualExecutor(ledger).receive(a.job,a.file,read(Path(a.probe)))
    if command=='review-take':
        plan=freeze_plan(read(Path(a.plan))['contract'])
        decision=shot_decision(plan,read(Path(a.observations)),a.shot,plan['sha256'])
        decision['id']='ACC_'+a.shot
        return ledger.save_acceptance(decision)
    if command=='check-adjacent':
        plan=freeze_plan(read(Path(a.plan))['contract'])
        decision=adjacent_decision(plan,read(Path(a.observations)),a.left,a.right,plan['sha256'])
        decision['id']='ACC_'+a.left+'_'+a.right
        return ledger.save_acceptance(decision)
    if command=='assemble':
        edl=read(Path(a.edl));spec=read(Path(a.spec));validate_edl(edl)
        result=assemble_ffmpeg(edl,a.out,spec)
        clocks=timelines(spec.get('project',[]),spec.get('media',[]),spec.get('post',[]))
        record={'id':'ASM_'+result.get('output_sha256','pending')[:12],**clocks,'edl':edl,'tool':'ffmpeg','status':result['status'],'probe':result.get('probe')}
        if result['status']=='CHECKED':ledger.save_assembly(record)
        return {**result,'handoff':{'jianying':export_jianying(edl,str(Path(a.out).with_suffix(''))+'-jianying'),'hypit':export_hypit(edl,str(Path(a.out).with_suffix(''))+'-hypit')}}
    raise ValueError('Unknown production command')


if __name__=='__main__':raise SystemExit(main())
