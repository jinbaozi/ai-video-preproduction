"""Loss-aware native StoryboardIR 1.1 conversion; temporal fields are copied intact."""
from copy import deepcopy
from fractions import Fraction
from .v51_detail_runtime import digest,leaves,bounds,ms,panel_state,temporal_hash,content_hash,semantic_status,pointer

def storyboard_to_avir(ir,base,overrides,legacy):
 from .v5_adapters import assert_check
 proxy=deepcopy(ir);timeline=proxy.pop('timeline');proxy['schema_version']='storyboard-ir/1.0'
 proxy['delivery']['fps']=float(Fraction(str(proxy['delivery']['fps'])))
 temporal_contracts=[c for c in proxy['contract'] if any(x['path'].startswith('/timeline/') for x in c['checks'])]
 proxy['contract']=[c for c in proxy['contract'] if c not in temporal_contracts]
 voices={e['id'] for e in proxy['entities'] if e['kind']=='voice'}
 for e in proxy['entities']:
  if e['id'] in voices:e['kind']='environment'
 result,report=legacy(proxy,base,overrides)
 for e in result['entities']:
  if e['id'] in voices:e['kind']='voice'
 for source in result['sources']:
  original=next(x for x in ir['sources'] if x['id']==source['id']);source['utterances']=deepcopy(original.get('utterances',[]))
 result['schema']='avir/1.1';result['timeline']=deepcopy(timeline)
 size={'extreme_wide':'wide','extreme_close':'detail','insert':'detail'}
 for shot in result['shots']:
  shot['start_ms'],shot['end_ms']=bounds(ir)[shot['id']]
  shot['camera']['shot_size']=size.get(shot['camera']['shot_size'],shot['camera']['shot_size'])
 result['output']['duration_ms']=ms(ir['delivery']['total_frames'],ir['delivery']['fps'])
 for frame in report['rounding']:
  exact=Fraction(frame)*1000/Fraction(str(ir['delivery']['fps']));rounded=ms(int(frame),ir['delivery']['fps'])
  report['rounding'][frame]={'milliseconds':rounded,'error_ms':float(Fraction(rounded)-exact),'exact_ms':str(exact),'rule':'fraction-boundary-half-up'}
 coverage=[]
 for p,v in leaves(timeline,'/timeline'):
  report['field_mapping'][p]=p
  coverage.append({'source_path':p,'source_sha256':digest(v),'target_path':p,'target_sha256':digest(v),'disposition':'direct','rule':'TEMPORAL.IDENTITY.1.1'})
 for c in temporal_contracts:
  checks=[]
  for check in c['checks']:
   target=report['field_mapping'].get(check['path'])
   if not target or not assert_check(ir,check):
    report['losses'].append({'path':check['path'],'severity':'error','reason':'Missing or failing contract mapping'});continue
   mapped=deepcopy(check);mapped['path']=target
   if not assert_check(result,mapped):report['losses'].append({'path':check['path'],'severity':'error','reason':'Mapped assertion differs'});continue
   checks.append(mapped)
  result['contract'].append({'id':c['id'],'level':c['strength'],'requirement':c['statement'],'source_refs':c['source_refs'],'shot_ids':c['shot_ids'],'checks':checks,'channel':c['channel'],'execution':c['execution'],'acceptance':{'method':'media','criterion':'；'.join(x['criterion'] for x in c['acceptance'])},'on_unsupported':'block' if c['strength']=='hard' else 'warn'})
 if semantic_status(ir) and not any(x['severity']=='error' for x in report['losses']):
  result['timeline']['semantic_review']['input_sha256']=content_hash(result)
 for row in coverage:
  row['target_sha256']=digest(pointer(result,row['target_path']))
  if row['source_sha256']!=row['target_sha256']:row.update(disposition='derived',rule='REVIEW.DETERMINISTIC.REBIND.1.1')
 report.update(adapter='1.1.0',source_hash=digest(ir),target_hash=digest(result),detail_coverage=coverage,sidecar=deepcopy(ir),
  status='BLOCKED' if any(x['severity']=='error' for x in report['losses']) else 'MAPPED',
  semantic_review='INHERITED_DETERMINISTICALLY' if semantic_status(ir) else 'PENDING',
  sidecar_scope=['native beat and panel metadata; temporal execution fields mapped directly'])
 return result,report


def image_briefs(ir):
 result=[]
 for i,s in enumerate(ir['shots']):
  for j,p in enumerate(s['panels']):
   at=ms(p['frame'],ir['delivery']['fps']);state=panel_state(ir,s['id'],at)
   relevant={x['id'] for x in state['actions']}
   paths=[f'/shots/{i}/panels/{j}',f'/shots/{i}/composition']
   for col in ('state_samples','performances','camera_operations','actions','visibility'):
    for k,x in enumerate(ir['timeline'][col]):
     if (x.get('shot_id')==s['id'] and (col!='state_samples' or x['at_ms']==at)) or (s['id'] in x.get('shot_ids',[]) and x['start_ms']<=at<x['end_ms']):paths.append(f'/timeline/{col}/{k}')
   result.append({'id':p['id'],'shot_id':s['id'],'scene_id':s['scene_id'],'kind':'board','frame':p['frame'],'moment':p['moment'],'must_show':p['must_show'],
    'state_evaluation':state,'camera':state['camera'],'performance':state['performance'],'composition':s['composition'],
    'state_start':state['state'],'events':state['actions'],'bindings':[b for b in ir['bindings'] if s['id'] in b['shot_ids']],
    'source_pointer':f'/shots/{i}/panels/{j}','source_hash':digest(ir),'dependency_paths':paths+[f'/bindings/{k}' for k,b in enumerate(ir['bindings']) if s['id'] in b['shot_ids']],
    'allowed_change':'Only this explicit instant. Missing key pose must be designed and reviewed before image generation.'})
 return result
