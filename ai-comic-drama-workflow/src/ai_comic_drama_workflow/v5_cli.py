"""V6 orchestration commands and the explicit legacy V5 command surface."""
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
    init.add_argument('--orchestration',choices=['codex','current-agent'],default='codex')
    init.add_argument('--no-run',action='store_true')
    for name in ('agent-event','agent-message','agent-result','agent-review','agent-reconcile','agent-cancel','image-begin','image-result'):
        sub=commands.add_parser(name);sub.add_argument('project');sub.add_argument('--file',required=True)
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
    c=commands.add_parser('migrate-v6');c.add_argument('project');c.add_argument('--destination',required=True)
    commands.add_parser('doctor')
    graph_command=commands.add_parser('graph');graph_command.add_argument('--format',choices=['mermaid','json'],default='mermaid')
    prod=commands.add_parser('production');prod.add_argument('project')
    prod_commands=prod.add_subparsers(dest='production_command',required=True)
    for name in ('plan','execute','recover-execution','receive-take','freeze','select','review-take',
                 'check-adjacent','assemble','review-sequence','post-obligation','deliver','status'):
        sub=prod_commands.add_parser(name)
        if name=='plan':
            sub.add_argument('--compile',required=True);sub.add_argument('--request',required=True)
            sub.add_argument('--manifest-sha',required=True);sub.add_argument('--attachments',required=True)
            sub.add_argument('--max-attempts',type=int);sub.add_argument('--project-cap',type=int,default=9)
            sub.add_argument('--budget-authorization')
        if name=='execute':sub.add_argument('--job',required=True);sub.add_argument('--out',required=True)
        if name=='recover-execution':sub.add_argument('--record',required=True);sub.add_argument('--out')
        if name=='receive-take':
            sub.add_argument('--job',required=True);sub.add_argument('--file',required=True);sub.add_argument('--probe',required=True)
            sub.add_argument('--execution-evidence')
        if name=='freeze':
            sub.add_argument('--shots',required=True);sub.add_argument('--shot-ranges',required=True)
            sub.add_argument('--plan',required=True);sub.add_argument('--spec',required=True)
            sub.add_argument('--obligations')
        if name=='select':sub.add_argument('--shot',required=True);sub.add_argument('--take',required=True)
        if name=='review-take':
            sub.add_argument('--plan',required=True);sub.add_argument('--observations',required=True)
            sub.add_argument('--shot',required=True);sub.add_argument('--take')
        if name=='check-adjacent':sub.add_argument('--plan',required=True);sub.add_argument('--observations',required=True);sub.add_argument('--left',required=True);sub.add_argument('--right',required=True)
        if name=='assemble':sub.add_argument('--edl',required=True);sub.add_argument('--out',required=True);sub.add_argument('--spec',required=True)
        if name=='review-sequence':sub.add_argument('--plan',required=True);sub.add_argument('--observations',required=True)
        if name=='post-obligation':sub.add_argument('--id',required=True);sub.add_argument('--evidence',required=True)
    a=p.parse_args(argv)
    try:
        if a.command=='graph':
            from .v6_graph import graph_to_mermaid, load_graph
            graph=load_graph()
            diagram=graph_to_mermaid(graph)
            if a.format=='mermaid':
                print(diagram,end='')
                return 0
            r={'workflow_id':graph['workflow_id'],'schema_version':graph['schema_version'],
               'nodes':graph['nodes'],'mermaid':diagram}
        elif a.command=='doctor':
            from .v6_graph import load_graph
            graph=load_graph()
            r={'workflow':graph['workflow_id'],'execution_mode':graph['execution_mode'],'python':'3.12+',
               'stage_count':len(graph['nodes']),
               'image_gen':'host-only; capability requires actual tool evidence','modules':default_lock(ROOT)}
        elif a.command=='init':
            if a.orchestration=='codex':
                from .v6_runtime import V6Runtime
                k=V6Runtime.initialize(a.project,a.inputs,project_id=a.project_id,delivery=a.delivery,
                                       target=a.target,mode=a.mode,production_target=a.production_target)
            else:
                k=V5Kernel.initialize(a.project,a.inputs,project_id=a.project_id,delivery=a.delivery,
                                      target=a.target,mode=a.mode,production_target=a.production_target)
            r=k.status() if a.no_run else k.run()
        elif a.command=='migrate-v6':
            from .v6_runtime import V6Runtime
            r=V6Runtime.migrate(a.project,a.destination).status()
        elif a.command=='copy-project':r=V5Kernel.copy_project(a.project,a.destination).status()
        elif a.command=='production':r=_production(a)
        else:
            project=read(Path(a.project)/'project.json')
            is_v6=project.get('orchestration_protocol')=='6.0'
            if is_v6:
                from .v6_runtime import V6Runtime
                k=V6Runtime(a.project)
            else:k=V5Kernel(a.project)
            if a.command.startswith('agent-') or a.command in ('image-begin','image-result'):
                if not is_v6:raise ValueError('Host and agent commands require a V6 project')
                payload=read(Path(a.file))
                fields={
                    'agent-event':{'receipt'},'agent-message':{'message'},
                    'agent-result':{'candidate'},'agent-review':{'review'},
                    'agent-reconcile':{'task_id','observation'},
                    'agent-cancel':{'task_id','ack_message_id'},
                    'image-begin':{'task_id'},'image-result':{'candidate'},
                }[a.command] | {'command_id','expected_revision'}
                if not isinstance(payload,dict) or set(payload)!=fields:
                    raise ValueError('Command wrapper fields differ from the V6 command contract')
                common={'command_id':payload['command_id'],'expected_revision':payload['expected_revision']}
                if a.command=='agent-event':r=k.agent_event(payload['receipt'],**common)
                elif a.command=='agent-message':r=k.agent_message(payload['message'],**common)
                elif a.command=='agent-result':r=k.agent_result(payload['candidate'],**common)
                elif a.command=='agent-review':r=k.agent_review(payload['review'],**common)
                elif a.command=='agent-reconcile':r=k.agent_reconcile(payload['task_id'],payload['observation'],**common)
                elif a.command=='agent-cancel':r=k.agent_cancel(payload['task_id'],payload['ack_message_id'],**common)
                elif a.command=='image-begin':r=k.image_begin(payload['task_id'],**common)
                else:r=k.image_result(payload['candidate'],**common)
            elif is_v6 and a.command not in ('run','status','validate','export'):
                r=k.v5_command(a)
            elif a.command in ('run','status'):r=getattr(k,a.command)()
            elif a.command=='compile':r=k.compile(a.mapping)
            elif a.command=='import-observation':r=k.import_observation(a.bundle)
            elif a.command=='import-compiled':r=k.import_compiled(a.package)
            elif a.command=='validate':r=k.validate(a.final)
            elif a.command=='export':r=k.export(a.draft)
            elif a.command=='submit':r=k.submit(a.result)
            elif a.command=='resume':r=k.resume(a.decision)
            elif a.command=='request-decision':r=k.request_decision(a.proposal)
            elif a.command=='host':
                info=read(Path(a.capabilities));r=k.host(info['image_capability'],info['evidence'],info.get('video_capabilities'),info.get('image_tools'))
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
    project=read(Path(a.project)/'project.json')
    if project.get('orchestration_protocol')=='6.0':
        from .v6_runtime import V6Runtime
        from .v6_production_runtime import V6ProductionRuntime
        return _production_v6(a,V6ProductionRuntime(V6Runtime(a.project)))
    k=V5Kernel(a.project)
    ledger=ProductionLedger(k)
    command=a.production_command
    if command=='status':
        return {'jobs':ledger.jobs(),'executions':ledger.records(),'takes':ledger.takes(),
                'blockers':ledger.video_delivery_blockers(),'production_target':k.production_target()}
    if command=='plan':
        compiled=read(Path(a.compile));request=next(r for r in compiled['requests'] if r['id']==a.request)
        budget={'max_attempts':a.max_attempts if a.max_attempts is not None else (1 if ledger.strict else 3),
                'project_cap':a.project_cap}
        if a.budget_authorization:budget['authorization']=a.budget_authorization
        return ledger.plan_job(request,a.manifest_sha,read(Path(a.attachments)),request['scope'].get('shot_ids',[]),
                               budget,compile_path=a.compile if ledger.strict else None)
    if command=='execute':
        from .executors.agnes_http import AgnesHttpTransport
        return AgnesApiExecutor(ledger,AgnesHttpTransport()).execute(a.job,a.out)
    if command=='recover-execution':
        from .executors.agnes_http import AgnesHttpTransport
        executor=AgnesApiExecutor(ledger,AgnesHttpTransport())
        record=ledger._load('executions/'+a.record+'.json')
        if record.get('task_id'):
            if not a.out:raise ValueError('--out is required to recover a submitted execution')
            return executor.finish(a.record,a.out)
        return executor.recover(a.record)
    if command=='receive-take':
        evidence=read(Path(a.execution_evidence)) if a.execution_evidence else None
        return ManualExecutor(ledger).receive(a.job,a.file,read(Path(a.probe)),execution_evidence=evidence)
    if command=='freeze':
        source=read(Path(a.plan));contract=source['contract'] if isinstance(source,dict) else source
        plan=freeze_plan(contract)
        if ledger.strict and not a.shot_ranges:
            raise ValueError('Protocol 6.0 needs --shot-ranges')
        return ledger.freeze_delivery_manifest(read(Path(a.shots)),plan,
                                               read(Path(a.obligations)) if a.obligations else [],
                                               read(Path(a.spec)),
                                               shot_ranges=read(Path(a.shot_ranges)) if a.shot_ranges else None)
    if command=='select':return ledger.select_take(a.shot,a.take)
    if command=='review-take':
        source=read(Path(a.plan));plan=freeze_plan(source['contract'] if isinstance(source,dict) else source)
        decision=shot_decision(plan,read(Path(a.observations)),a.shot,plan['sha256'])
        decision['id']='ACC_'+a.shot
        if ledger.strict:
            if not a.take:raise ValueError('Protocol 6.0 needs --take for shot review')
            decision['take_ids']={a.shot:a.take}
        return ledger.save_acceptance(decision)
    if command=='check-adjacent':
        source=read(Path(a.plan));plan=freeze_plan(source['contract'] if isinstance(source,dict) else source)
        decision=adjacent_decision(plan,read(Path(a.observations)),a.left,a.right,plan['sha256'])
        decision['id']='ACC_'+a.left+'_'+a.right
        return ledger.save_acceptance(decision)
    if command=='assemble':
        edl=read(Path(a.edl));spec=read(Path(a.spec));validate_edl(edl)
        result=assemble_ffmpeg(edl,a.out,spec)
        if result['status']!='CHECKED':return result
        clocks=timelines(spec.get('project',[]),spec.get('media',[]),spec.get('post',[]))
        record={'id':'ASM_'+result.get('output_sha256','pending')[:12],**clocks,'edl':edl,'tool':'ffmpeg','status':result['status'],'probe':result.get('probe')}
        ledger.save_assembly(record,output_path=a.out)
        return {**result,'handoff':{'jianying':export_jianying(edl,str(Path(a.out).with_suffix(''))+'-jianying'),'hypit':export_hypit(edl,str(Path(a.out).with_suffix(''))+'-hypit')}}
    if command=='review-sequence':
        source=read(Path(a.plan));plan=freeze_plan(source['contract'] if isinstance(source,dict) else source)
        decision=decide(plan,read(Path(a.observations)),frozen_sha256=plan['sha256'])
        decision.update(id='ACC_SEQUENCE',level='sequence')
        return ledger.save_acceptance(decision)
    if command=='post-obligation':return ledger.save_post_obligation(a.id,read(Path(a.evidence)))
    if command=='deliver':return ledger.mark_video_delivered()
    raise ValueError('Unknown production command')


def _production_v6(a, runtime):
    from .acceptance import adjacent_decision, decide, freeze_plan, shot_decision
    command=a.production_command
    if command=='status':return runtime.status()
    if command=='plan':
        compiled=read(Path(a.compile));request=next(r for r in compiled['requests'] if r['id']==a.request)
        budget={'max_attempts':a.max_attempts if a.max_attempts is not None else 1,
                'project_cap':a.project_cap}
        if a.budget_authorization:budget['authorization']=a.budget_authorization
        return runtime.plan_job(request,a.manifest_sha,read(Path(a.attachments)),
                                request['scope'].get('shot_ids',[]),budget,compile_path=a.compile)
    if command=='freeze':
        source=read(Path(a.plan));contract=source['contract'] if isinstance(source,dict) else source
        return runtime.freeze_delivery(read(Path(a.shots)),freeze_plan(contract),
                                       read(Path(a.obligations)) if a.obligations else [],
                                       read(Path(a.spec)),shot_ranges=read(Path(a.shot_ranges)))
    if command=='execute':return runtime.execute(a.job,a.out)
    if command=='recover-execution':return runtime.recover_execution(a.record,a.out)
    if command=='receive-take':
        if not a.execution_evidence:raise ValueError('Protocol 6.0 needs --execution-evidence')
        return runtime.receive_take(a.job,a.file,read(Path(a.probe)),
                                    read(Path(a.execution_evidence)))
    if command=='review-take':
        if not a.take:raise ValueError('Protocol 6.0 needs --take for shot review')
        source=read(Path(a.plan));plan=freeze_plan(source['contract'] if isinstance(source,dict) else source)
        decision=shot_decision(plan,read(Path(a.observations)),a.shot,plan['sha256'])
        decision.update(id='ACC_'+a.shot,take_ids={a.shot:a.take})
        return runtime.review_take(decision)
    if command=='select':return runtime.select_take(a.shot,a.take)
    if command=='check-adjacent':
        source=read(Path(a.plan));plan=freeze_plan(source['contract'] if isinstance(source,dict) else source)
        decision=adjacent_decision(plan,read(Path(a.observations)),a.left,a.right,plan['sha256'])
        decision['id']='ACC_'+a.left+'_'+a.right
        return runtime.check_adjacent(decision)
    if command=='assemble':return runtime.assemble(read(Path(a.edl)),a.out,read(Path(a.spec)))
    if command=='post-obligation':return runtime.post_obligation(a.id,read(Path(a.evidence)))
    if command=='review-sequence':
        source=read(Path(a.plan));plan=freeze_plan(source['contract'] if isinstance(source,dict) else source)
        decision=decide(plan,read(Path(a.observations)),frozen_sha256=plan['sha256'])
        decision.update(id='ACC_SEQUENCE',level='sequence')
        return runtime.review_sequence(decision)
    if command=='deliver':return runtime.deliver()
    raise ValueError('Unknown production command')


if __name__=='__main__':raise SystemExit(main())
