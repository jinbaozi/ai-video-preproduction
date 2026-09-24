"""Audit-authored complete AVIR 1.2; not a substitute schema or runtime."""
import sys,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'video-prompt-compiler/scripts'))
from shot_control.common import write,sha
from shot_control.package import validate_source
from shot_control.control_plan import build

def fixture():
    origin={'kind':'design','source_refs':['SRC'],'locator':'Audit-authored staged two-shot scene'}
    refs=['SRC']; cp=copy.deepcopy
    ir={'schema':'avir/1.2','project_id':'AUDIT_TWO_SHOT','revision':1,'tenant_id':'AUDIT',
        'intent':'Two adults in a room, A shifts gaze toward B, camera remains fixed. Synthetic audit fixture.',
        'sources':[{'id':'SRC','kind':'design','uri':'source.txt','locator':'whole file','claim':'Synthetic scene created for software validation only','verification':'provided','sha256':None,'utterances':[]}],
        'entities':[{'id':n,'kind':'person','label':n,'appearance':n+' adult, distinct neutral clothing','locks':['identity'],'source_refs':refs} for n in ['A','B']],
        'scenes':[{'id':'ROOM','description':'An uncluttered room with a door and a window','coordinates':{'unit':'m','axes':'x=world-right,y=up,z=depth','origin':'Room origin'},'lighting':'Window key light','source_refs':refs}],
        'assets':[],'bindings':[],'output':{'duration_ms':8000,'aspect_ratio':'16:9','resolution':None},'shots':[],
        'audio':{'utterances':[],'cues':[]},'contract':[],
        'policy':{'allow_semantic_invention':False,'max_canonical_units':None,'context_ir':'rules'},'expansions':[]}
    timeline={'schema':'detail-timeline/1.2','coordinate_system':'x-right,y-up,z-depth; screen and anatomical directions are separate',
              'action_groups':[],'actions':[],'performances':[],'camera_operations':[],'audio_events':[],
              'state_samples':[],'visibility':[],'segments':[],'source_time_maps':[],'extensions':[],
              'semantic_review':{'status':'PENDING','reviewer':None,'input_sha256':None,'findings':[]},
              'spatial_nodes':[],'motion_tracks':[],'spatial_relations':[],'composition_tracks':[]}
    def states(at):
        return {n:{'position':[(-.6 if n=='A' else .6),1,3],'pose':'standing','body_facing':'toward camera',
                'head_facing':'toward camera','gaze':('B' if at>=2000 else 'door') if n=='A' else 'A',
                'contacts':[],'supports':['floor'],'controllers':[],'visible_parts':['body','face','eyes','mouth','hands'],
                'condition':'unchanged clothing'} for n in ['A','B']}
    for idx in range(2):
        sid=f'S{idx+1}';start=idx*4000;end=start+4000
        shot={'id':sid,'scene_id':'ROOM','start_ms':start,'end_ms':end,'purpose':'Observe the gaze and reaction',
              'transition':'cut','transition_reason':None,
              'composition':{'framing':'medium two-shot','layers':'A and B in middle ground','screen_positions':'A on left, B on right','required_visible':[{'entity_id':n,'parts':['face','body']} for n in ['A','B']]},
              'camera':{'position':[0,1,0],'look_at':[0,1,3],'shot_size':'medium','angle':'eye level','pitch_deg':0,'roll_deg':0,
                        'lens_intent':'normal field of view','movement':'locked','trajectory':'fixed','focus':'A and B','axis_side':'A','axis_change_reason':None},
              'relations':[],'start_state':[],'end_state':[],'performance':[],'style':['neutral'],'source_refs':refs}
        for edge,at in [('start',start),('end',end)]:
            shot[edge+'_state']=[{'entity_id':n,'position':s['position'],'pose':s['pose'],'facing':s['body_facing'],'gaze_target':None,'support':'floor','holding':[],'visible_parts':s['visible_parts']} for n,s in states(at).items()]
        ir['shots'].append(shot)
        timeline['camera_operations'].append({'id':'CAM_'+sid,'start_ms':start,'end_ms':end,'shot_ids':[sid],'origin':cp(origin),
            'operation':'locked','start_position':'fixed','end_position':'fixed','start_framing':'medium two-shot','end_framing':'medium two-shot',
            'height':'eye level','orientation':'look toward A and B','path':'fixed','speed':'stationary','look_at':'A and B','focus':'A and B','axis':'A','sync_action_ids':[],'precision':'intent'})
        for at in [start,start+2000,end]:
            timeline['state_samples'].append({'id':f'ST_{sid}_{at}','shot_id':sid,'at_ms':at,'entities':states(at),'origin':cp(origin)})
        timeline['composition_tracks'].append({'id':'COMP_'+sid,'shot_ids':[sid],'start_ms':start,'end_ms':end,
            'framing':'medium two-shot','attention_order':['NA','NB'],'negative_space':'above heads','safe_area':'central region','depth_layers':'middle ground',
            'subjects':[{'node_id':'N'+n,'box':None,'depth':'midground','visible_parts':['body','face','eyes','mouth','hands'],'readability':'face',
                         'occlusion':'none','presence':'inside','description':n+' visible'} for n in ['A','B']],'origin':cp(origin)})
    for nid,eid,kind,pos in [('NA','A','entity',[-.6,1,3]),('NB','B','entity',[.6,1,3]),('NC',None,'camera',[0,1,0])]:
        timeline['spatial_nodes'].append({'id':nid,'entity_id':eid,'kind':kind,'label':nid,'part':None,'parent_id':None,
          'frame':{'kind':'world','anchor_node_id':None,'unit':'m','transforms':[]},'bounds':None,'origin':cp(origin)})
        timeline['motion_tracks'].append({'id':'POS_'+nid,'node_id':nid,'property':'position','start_ms':0,'end_ms':8000,'shot_ids':['S1','S2'],
          'action_ids':[],'camera_operation_ids':[],'unit':'m','axis':None,'path':'fixed','speed':'stationary',
          'keyframes':[{'at_ms':t,'value':{'mode':'numeric','value':cp(pos),'description':'authored position','target_node_id':None},'transition':'hold' if t==0 else 'none'} for t in [0,8000]],'origin':cp(origin)})
    def detail(text):return {'status':'specified','text':text}
    timeline['actions'].append({'id':'GAZE_A','start_ms':1000,'end_ms':2000,'shot_ids':['S1'],'origin':cp(origin),'parent_id':None,'semantic_id':'LOOK_AT_B',
      'actor_id':'A','target_id':'B','effector':detail('eyes'),'operation':'shift gaze to B','trigger':'notice B','path':detail('door to B'),
      'speed':detail('one beat'),'support':detail('feet on floor'),'contact':detail('no contact'),'feedback':'eyes meet B','settle':'look held',
      'depends_on':[],'markers':[],'changes':[{'entity_id':'A','field':'gaze','before':'door','after':'B','at_ms':2000}]})
    ir['timeline']=timeline
    def clause(i,path,value,channel='prompt',shots=None):
        return {'id':i,'level':'hard','requirement':i,'source_refs':refs,'shot_ids':shots or [],
          'checks':[{'path':path,'op':'equals','value':value}],'channel':channel,'execution':'Preserve the specified field via the declared channel',
          'acceptance':{'method':'human','criterion':'Compare target with specified field'},'on_unsupported':'block'}
    ir['contract']=[clause('REQ_DURATION','/output/duration_ms',8000,'parameter'),
      clause('REQ_ID_A','/entities/0/appearance',ir['entities'][0]['appearance']),
      clause('REQ_ID_B','/entities/1/appearance',ir['entities'][1]['appearance']),
      clause('REQ_SCENE','/scenes/0/description',ir['scenes'][0]['description']),
      clause('REQ_CAMERA','/shots/0/camera/movement','locked',shots=['S1'])]
    return ir

def config(controls=None,aspect=16/9):
    return {'schema':'shot-control-config/0.2','lenses':{s:{'vertical_fov_deg':50,'aspect':aspect,'basis':'authored_proxy','evidence':'Synthetic audit lens'} for s in ['S1','S2']},'controls':controls or []}

def control(cid='C1',aid='K1',rid='REQ_ID_A',channel='image_reference',shots=None):
    paths={'REQ_ID_A':'/entities/0/appearance','REQ_ID_B':'/entities/1/appearance','REQ_SCENE':'/scenes/0/description','REQ_CAMERA':'/shots/0/camera/movement','REQ_DURATION':'/output/duration_ms'}
    return {'id':cid,'requirement_id':rid,'shot_ids':shots or ['S1'],'source_pointers':[paths[rid]],'channel':channel,
            'artifact_ids':[aid],'hardness':'hard','fallback_policy':'block','purpose':'supplement'}

def make(root,ir=None,cfg=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    ir=copy.deepcopy(ir or fixture());cfg=copy.deepcopy(cfg if cfg is not None else config())
    (root/'source.txt').write_text('Two adults A and B, two continuous four-second shots. A shifts gaze toward B during 1–2 seconds.\n')
    ir['sources'][0]['sha256']=sha(root/'source.txt');write(root/'input.avir.json',ir)
    validate_source(ir,root)
    result=build(root/'input.avir.json',root/'package',cfg)
    return root/'package',result

if __name__=='__main__':
    package,result=make(ROOT/'evidence/native-positive-baseline',cfg=config([control()]))
    from shot_control.package import verify_package
    b=verify_package(package)
    print(result)
    print('NATIVE VALID / VERIFIED',len(b['frames']),len(b['requests']),len(b['evaluation']['points']))
