"""Content-based dependency invalidation and local repair jobs; never rewrite upstream AVIR."""
from copy import deepcopy
from pathlib import Path
import shutil
from .common import read, write, sha, digest, schema_check, confined
from .package import verify_package, recipe

OWNERS = {'clean_keyframe':'image-optimizer','identity':'image-optimizer','appearance':'image-optimizer',
          'style':'production-design','scene':'production-design','clay':'video-compiler','performance':'storyboard','audio':'external-runner','review':'video-compiler'}
MODULES = {'image-optimizer':'image-prompt-optimizer','production-design':'production-design-grammar',
           'video-compiler':'video-prompt-compiler','storyboard':'storyboard-grammar','director':'director-grammar',
           'external-runner':None}


def invalidated_use(manifest, artifact_id, use):
    current = next(a['sha256'] for a in manifest['artifacts'] if a['id']==artifact_id)
    return any(row['artifact_id']==artifact_id and row['artifact_sha256']==current and row['use_sha256']==digest(use) for row in manifest.get('invalidated_uses', []))


def plan_repairs(before_package, after_package, manifest_path, observations=None, media=None):
    before, after = verify_package(before_package), verify_package(after_package)
    if before['ir']['project_id'] != after['ir']['project_id']: raise ValueError('Repair packages belong to different projects')
    manifest_path = Path(manifest_path).resolve()
    manifest = read(manifest_path); schema_check(manifest, 'control-artifacts')
    if len({a['id'] for a in manifest['artifacts']}) != len(manifest['artifacts']): raise ValueError('Duplicate artifact ID')
    if (observations is None) != (media is None): raise ValueError('Observation input and actual video must be supplied together')
    updated = deepcopy(manifest); invalidations = updated.setdefault('invalidated_uses', [])
    tasks, nodes, edges, output_invalidations = [], [], [], []
    old_controls = {c['id']:c for c in before['plan']['controls']}
    new_controls = {c['id']:c for c in after['plan']['controls']}
    old_shots = {s['id']:s for s in before['ir']['shots']}
    new_shots = {s['id']:s for s in after['ir']['shots']}
    def task(owner, issue, source_pointers, scope, targets, observed_output=False):
        acceptance = (['保留当前原生来源及未受影响输入，先核对冻结请求、执行回执与失败媒体',
                       '修复或重试实际执行并保留新旧输出、耗时和回执，不将原输出失败改为通过',
                       '仅有上游设计错误证据时，另交所属模块修订原生来源并重建受影响请求']
                      if observed_output else
                      ['修订由所属模块写回原生来源，再重新 build',
                       '重新生成或审核受影响用途，重新记录配方与文件摘要',
                       '重编受影响请求并验证；保留未受影响资产'])
        acceptance.append('实际生成后重跑冻结基线观察，不用静态通过代替媒体质量')
        value = {'schema':'shot-control-repair-task/0.1', 'project_id':after['ir']['project_id'],
                 'before_source_sha256':before['plan']['source']['sha256'], 'after_source_sha256':after['plan']['source']['sha256'],
                 'owner':owner, 'module':MODULES[owner], 'issue':issue, 'source_pointers':source_pointers,
                 'scope':scope, 'targets':targets, 'status':'OPEN', 'execution':'CURRENT_AGENT_REQUIRED',
                 'acceptance':acceptance}
        value['id'] = 'REPAIR_'+digest(value)[:20]; tasks.append(value)
        return value['id']
    for asset in manifest['artifacts']:
        path = confined(manifest_path.parent, asset['path'])
        file_problem = not path.is_file() or sha(path) != asset['sha256']
        for use in asset['uses']:
            ident = 'asset-use:'+asset['id']+':'+digest(use)
            reasons = []
            old = old_controls.get(use['control_id']); new = new_controls.get(use['control_id'])
            old_shot = old_shots.get(use['shot_id']); new_shot = new_shots.get(use['shot_id'])
            if old is None or old_shot is None or asset['id'] not in old['artifact_ids'] or use['shot_id'] not in old['shot_ids']:
                raise ValueError('Artifact use is not owned by the baseline package')
            if not old_shot['start_ms'] <= use['start_ms'] <= use['end_ms'] <= old_shot['end_ms']:
                raise ValueError('Artifact use is outside baseline shot')
            expected_before = recipe(before['ir'],before['config'],old,use['shot_id'],asset['role'],use['start_ms'],use['end_ms'])
            if expected_before != use['recipe_sha256']: raise ValueError('Baseline artifact recipe is already stale')
            if new is None or new_shot is None or asset['id'] not in new['artifact_ids'] or use['shot_id'] not in new['shot_ids']:
                reasons.append('CONTROL_OR_SHOT_RETIRED'); expected_after = None
            elif not new_shot['start_ms'] <= use['start_ms'] <= use['end_ms'] <= new_shot['end_ms']:
                reasons.append('TIME_SCOPE_CHANGED'); expected_after = None
            else:
                expected_after = recipe(after['ir'],after['config'],new,use['shot_id'],asset['role'],use['start_ms'],use['end_ms'])
                if expected_after != expected_before: reasons.append('DEPENDENCY_CONTENT_CHANGED')
            if file_problem: reasons.append('MISSING_OR_CHANGED_FILE')
            if invalidated_use(manifest,asset['id'],use): reasons.append('PREVIOUSLY_INVALIDATED')
            node = {'id':ident, 'kind':'artifact_use', 'artifact_id':asset['id'], 'use':use,
                    'before_fingerprint':expected_before, 'after_fingerprint':expected_after,
                    'status':'INVALIDATED' if reasons else 'RETAINED', 'reasons':reasons}
            nodes.append(node)
            selectors = list(old['source_pointers'])
            if asset['role'] not in ('identity','appearance','style','scene') or old['channel'] not in ('image_reference','keyframe_input'):
                selectors += ['/shots/'+str(before['ir']['shots'].index(old_shot)), '/timeline', '/entities', '/scenes']
                edges.append({'from':'config:/lenses/'+use['shot_id'], 'to':ident, 'selector':'camera recipe'})
                for field in ('proxy_scene','look_design'):
                    if field in before['config']:
                        edges.append({'from':'config:/'+field,'to':ident,'selector':'shot-scoped '+use['shot_id']+' recipe content'})
            for pointer in sorted(set(selectors)):
                edges.append({'from':'source:'+pointer,'to':ident,'selector':'scoped recipe content'})
            if reasons:
                task_id = task(OWNERS[asset['role']], ', '.join(reasons), old['source_pointers'],
                               {k:use[k] for k in ('shot_id','start_ms','end_ms')}, [ident])
                record = {'artifact_id':asset['id'],'artifact_sha256':asset['sha256'],'use_sha256':digest(use),'reason':', '.join(reasons), 'task_id':task_id}
                if not invalidated_use(updated,asset['id'],use): invalidations.append(record)
    # Requests depend on evaluated content, not the whole source revision checksum.
    def request_content(r):
        return {k:v for k,v in r.items() if k not in ('source','status','generated','visual_review')}
    old_requests = {r['id']:r for r in before['requests']}
    new_requests = {r['id']:r for r in after['requests']}
    for ident in sorted(set(old_requests)|set(new_requests)):
        old, new = old_requests.get(ident), new_requests.get(ident)
        a = digest(request_content(old)) if old else None; b = digest(request_content(new)) if new else None
        changed = a != b; r = new or old
        nodes.append({'id':'keyframe:'+ident,'kind':'keyframe_request','shot_id':r['shot_id'],'at_ms':r['at_ms'],
                      'before_fingerprint':a,'after_fingerprint':b,'status':'INVALIDATED' if changed else 'RETAINED'})
        edges.append({'from':'evaluated-state:'+r['shot_id']+':'+str(r['at_ms']),'to':'keyframe:'+ident,'selector':'camera/pose/composition/anchors'})
        if changed:
            task('image-optimizer','KEYFRAME_CONTENT_CHANGED',r['source_pointers'],
                 {'shot_id':r['shot_id'],'start_ms':r['at_ms'],'end_ms':r['at_ms']},['keyframe:'+ident])
    for sid in sorted(set(old_shots)|set(new_shots)):
        fingerprints = []
        for bundle, shot in ((before,old_shots.get(sid)),(after,new_shots.get(sid))):
            fingerprints.append(recipe(bundle['ir'],bundle['config'],{'source_pointers':[]},sid,'clay',shot['start_ms'],shot['end_ms']) if shot else None)
        dependencies = [n for n in nodes if n['kind']=='artifact_use' and n['use']['shot_id']==sid]
        changed = fingerprints[0] != fingerprints[1] or any(n['status']=='INVALIDATED' for n in dependencies)
        ident = 'planned-shot-output:'+sid
        nodes.append({'id':ident,'kind':'planned_shot_output','shot_id':sid,'before_fingerprint':fingerprints[0],
                      'after_fingerprint':fingerprints[1],'status':'INVALIDATED' if changed else 'RETAINED','generation_status':'NOT_INFERRED'})
        edges += [{'from':n['id'],'to':ident,'selector':'reference input'} for n in dependencies]
        if changed:
            shot = new_shots.get(sid) or old_shots[sid]
            task('video-compiler','SHOT_INPUTS_CHANGED',[],{'shot_id':sid,'start_ms':shot['start_ms'],'end_ms':shot['end_ms']},[ident])
    evaluation = None
    if observations is not None:
        from .media_review import evaluate
        evaluation = evaluate(read(observations),before_package,media)
        for finding in evaluation['findings']:
            if finding['result'] != 'FAIL': continue
            target = 'observed-media:'+evaluation['media_sha256']
            task_id = task(finding['owner'],finding['issue'],finding['source_pointers'],
                           {'start_ms':finding['start_ms'],'end_ms':finding['end_ms']},[target],observed_output=True)
            output_invalidations.append({'media_sha256':evaluation['media_sha256'],'start_ms':finding['start_ms'],
                'end_ms':finding['end_ms'],'reason':finding['issue'],'task_id':task_id,'status':'INVALIDATED'})
        # A failed output does not prove a correct master reference is defective.
    schema_check(updated,'control-artifacts')
    return {'schema':'shot-control-repair-plan/0.1','status':'REPAIR_REQUIRED' if tasks else 'UNCHANGED',
            'source_before':before['plan']['source'],'source_after':after['plan']['source'],
            'graph':{'nodes':nodes,'edges':edges},'tasks':tasks,'output_invalidations':output_invalidations,
            'updated_artifacts':updated,'evaluation':evaluation,'upstream_modified':False,'media_generated':False}


def export(before, after, manifest_path, out, observations=None, media=None):
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())): raise ValueError('Use an empty repair output directory')
    result = plan_repairs(before,after,manifest_path,observations,media)
    out.mkdir(parents=True,exist_ok=True)
    # Copy asset bytes into the new snapshot; preserve the original manifest and files.
    base = Path(manifest_path).resolve().parent
    for asset in result['updated_artifacts']['artifacts']:
        source = confined(base,asset['path']); relative = source.relative_to(base).as_posix(); destination = confined(out/'assets',relative)
        if source.is_file():
            destination.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,destination)
        asset['path'] = 'assets/'+relative
    write(out/'artifact-manifest.json',result['updated_artifacts'])
    write(out/'dependency-graph.json',result['graph'])
    for task in result['tasks']: write(out/'tasks'/(task['id']+'.json'),task)
    write(out/'output-invalidations.json',result['output_invalidations'])
    write(out/'repair-plan.json',result)
    write(out/'repair-manifest.json',{'schema':'shot-control-repair-package/0.1','files':{
        p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}})
    return {'status':result['status'],'out':str(out.resolve()),'tasks':len(result['tasks']),
            'invalidated_uses':len(result['updated_artifacts'].get('invalidated_uses',[])), 'upstream_modified':False}
