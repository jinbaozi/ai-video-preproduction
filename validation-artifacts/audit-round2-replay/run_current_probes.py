from support import *
# NEW: legal native reference obligation crashes lower (no simplified source).
case,p,b=fresh('N01_native_reference')
ir=fixture();native=case/'native.png';shutil.copyfile(ASSETS/'p1.png',native)
ir['assets']=[{'id':'NATIVE_REF','kind':'image','filename':'native.png','path':'native.png','sha256':sha(native),'public_url':None,'inspection':'observed','source_refs':['SRC']}]
ir['bindings']=[{'id':'NBIND','asset_id':'NATIVE_REF','target_id':'B','shot_ids':['S1','S2'],'roles':['identity'],'negative_roles':[],'source_refs':['SRC']}]
ir['contract'].append({'id':'REQ_NATIVE_REF','level':'hard','requirement':'Use the provided native identity reference for B','source_refs':['SRC'],'shot_ids':['S1','S2'],
 'checks':[{'path':'/bindings/0/roles','op':'contains','value':'identity'}],'channel':'reference','execution':'Use NATIVE_REF as B identity','acceptance':{'method':'human','criterion':'Preserve B identity'},'on_unsupported':'block'})
shutil.rmtree(p);_,built=make(case,ir=ir,cfg=config([control()]));b=verify_package(p);a=asset(b,b['plan']['controls'][0],'K1');mf=manifest(case,[a])
assert_case('N01_native_reference','new-probe',lambda:lower(p,'agnes-video-2.5','reference',mf),True)

# NEW: URL fragments are not part of the HTTP request target, yet evade raw-string conflict checks.
from urllib.request import Request
cs=[control('C1','K1','REQ_ID_A'),control('C2','K2','REQ_ID_B')]
case,p,b=fresh('N09_url_fragment_alias',cs)
a=asset(b,cs[0],'K1',media='p0.png',url='https://example.com/shared.png#identity-a')
z=asset(b,cs[1],'K2',media='p1.png',url='https://example.com/shared.png#identity-b')
r=bind(case,p,[a,z])
note('N09_url_fragment_alias','new-probe','different hashes for the same HTTP resource must conflict',
     {'lower':r,'http_request_targets':[Request(a['binding']['url']).selector,Request(z['binding']['url']).selector],
      'different_hashes':a['sha256']!=z['sha256']},r['status']=='BLOCKED')
# Queries, unlike fragments, are part of the request target and must not be merged by the audit.
case,p,b=fresh('P15_distinct_query_resources',cs)
a=asset(b,cs[0],'K1',media='p0.png',url='https://example.com/shared.png?v=a')
z=asset(b,cs[1],'K2',media='p1.png',url='https://example.com/shared.png?v=b')
r=bind(case,p,[a,z]);note('P15_distinct_query_resources','positive','different query resources remain distinct',r,r['status']=='BOUND_DRAFT' and len(r['attachment_index'])==2)

# NEW: mislabeled temporal media obtains master-only recipe and survives FOV change.
for role in ['clay','identity']:
    name='N02_temporal_role_'+role;cs=[control('CL','V','REQ_CAMERA','clay_video_reference')]
    case,p,b=fresh(name,cs);a=asset(b,cs[0],'V',role=role,kind='video',media='clay.mp4')
    before=bind(case,p,[a]);cfg=config(cs);cfg['lenses']['S1']['vertical_fov_deg']=75
    shutil.rmtree(case);case,p,_=fresh(name,cs,cfg=cfg);after=bind(case,p,[a])
    note(name,'new-probe','FOV change blocks all temporal channel assets regardless of role',{'before':before,'after':after},after['status']=='BLOCKED')

# NEW: rehashed review HTML / SVG is not source-rederived.
for filename in ['review/index.html','review/blocking-001.svg']:
    name='N03_review_reseal_'+('html' if filename.endswith('html') else 'svg');case,p,b=fresh(name)
    original=(p/filename).read_text();(p/filename).write_text(original.replace('NA','MISLABELED_ACTOR',1))
    reseal(p,filename)
    assert_case(name,'new-probe',lambda p=p:verify_package(p),False)

# NEW: keyframe and lower disagree on known invalid temporal scope.
cs=[control()];case,p,b=fresh('N04_anchor_time_scope',cs);a=asset(b,cs[0],'K1')
a['uses'][0]['start_ms']=9000;a['uses'][0]['end_ms']=10000
# Master recipe is independent of time. Review is legitimately rebound to the tested use.
a['uses'][0]['recipe_sha256']=recipe(b['ir'],b['config'],cs[0],'S1','identity',9000,10000)
a['review']['uses_sha256']=digest(a['uses']);mf=manifest(case,[a]);req=copy.deepcopy(b['requests'][0]);req.update(generation_mode='generate',master_anchors=['K1'])
r=check_request(req,p,mf);lo=lower(p,'agnes-video-2.5','reference',mf)
note('N04_anchor_time_scope','new-probe','both consumers reject out-of-shot uses',{'keyframe':r,'lower':lo},r['status']=='BLOCKED' and lo['status']=='BLOCKED')

# NEW: temporal fingerprints include unrelated entities and future actions.
for mutation in ['unused_entity','future_action']:
    name='N05_false_stale_'+mutation;cs=[control(channel='first_frame')];ir=fixture()
    ir['entities'].append({'id':'UNUSED','kind':'prop','label':'unused prop','appearance':'unused green prop','locks':[],'source_refs':['SRC']})
    case,p,b=fresh(name,cs,ir=ir);a=asset(b,cs[0],'K1',role='clean_keyframe');before=bind(case,p,[a],mode='keyframe')
    before_frame=copy.deepcopy(b['frames'][0]['points']);before_state=copy.deepcopy(b['requests'][0]['subject_state'])
    if mutation=='unused_entity':ir['entities'][-1]['appearance']='unused yellow prop'
    else:ir['timeline']['actions'][0]['feedback']='After the turn, B notices A'
    shutil.rmtree(case);case,p,b2=fresh(name,cs,ir=ir);after=bind(case,p,[a],mode='keyframe')
    note(name,'new-probe','irrelevant change retains t=0 clean frame',{'before':before,'after':after,'frame_points_unchanged':before_frame==b2['frames'][0]['points'],'instant_state_unchanged':before_state==b2['requests'][0]['subject_state']},after['status']=='BOUND_DRAFT')


# NEW: valid native fractional event time cannot be represented by request schema.
ir=fixture();ir['timeline']['actions'][0]['start_ms']=1000.5
root=OUT/'N07_fractional_event'
if root.exists():shutil.rmtree(root)
root.mkdir();(root/'source.txt').write_text('fractional event native fixture');ir['sources'][0]['sha256']=sha(root/'source.txt')
validate_source(ir,root);write(root/'native-precondition.json',{'native_validation_passed':True,'event_start_ms':1000.5})
assert_case('N07_fractional_event','new-probe',lambda:make(root,ir=ir,cfg=config([control()])),True)

# NEW: camera pole degeneracy is swallowed but projection state remains PLANNED.
ir=fixture();ir['shots'][0]['camera']['look_at']=[0,4,0]
case,p,b=fresh('N08_camera_degenerate',ir=ir);a=asset(b,b['plan']['controls'][0],'K1');mf=manifest(case,[a]);req=copy.deepcopy(b['requests'][0]);req.update(generation_mode='generate',master_anchors=['K1'])
r=check_request(req,p,mf)
note('N08_camera_degenerate','new-probe','invalid camera projection blocks readiness',{'camera':b['frames'][0]['camera'],'points':b['frames'][0]['points'],'keyframe_check':r},r['status']=='BLOCKED')



ir=fixture();ir['output']['aspect_ratio']='9:16'
result=outcome(lambda: fresh('N06_aspect_conflict',ir=ir,cfg=config([control()],16/9)))
note('N06_aspect_conflict','new-probe','conflict rejected at build',result,not result['accepted'])
write(OUT/'current-summary.json',{'source':'Original GPT-6 Pro native fixture and selected original probe bodies; workspace imports and early aspect rejection adapted, original snapshot hash guard removed because target changed', 'count':len(RESULTS),'failed':[x['id'] for x in RESULTS if not x['assertion_passed']],'browser_check':'NOT_RUN','scope':'Selected A01-A09 probes, not the whole original 71-assertion suite'})
raise SystemExit(1 if any(not x['assertion_passed'] for x in RESULTS) else 0)
