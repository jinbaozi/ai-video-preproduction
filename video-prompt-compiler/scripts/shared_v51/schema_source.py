"""Single source for the versioned temporal fragment; native IRs remain separate."""
from copy import deepcopy

S={'type':'string','minLength':1}
ID={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_-]*$'}
N={'type':'number','minimum':0}
def arr(item,minimum=0):return {'type':'array','items':item,'minItems':minimum}
def obj(props,required=None):return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}
def opt(x):return {'anyOf':[x,{'type':'null'}]}
def enum(*x):return {'enum':list(x)}
ORIGIN=obj({'kind':enum('observed','source','design'),'source_refs':arr(ID,1),'locator':S})
DETAIL=obj({'status':enum('specified','not_applicable','not_visible','unknown'),'text':S})
DEPENDENCY=obj({'action_id':ID,'relation':enum('after_end','after_start','overlaps','at_marker'),'marker':opt(ID),'offset_ms':{'type':'number'}})
STATE=obj({'position':opt(arr({'type':'number'},3)),'pose':S,'body_facing':S,'head_facing':S,'gaze':S,'contacts':arr(S),'supports':arr(S),'controllers':arr(S),'visible_parts':arr(S),'condition':S})
STATE['properties']['position']['anyOf'][0]['maxItems']=3
CHANGE=obj({'entity_id':ID,'field':enum(*STATE['properties']),'before':{},'after':{},'at_ms':N})
SPAN={'id':ID,'start_ms':N,'end_ms':N,'shot_ids':arr(ID,1),'origin':ORIGIN}
ACTION=obj({**SPAN,'parent_id':opt(ID),'semantic_id':ID,'actor_id':ID,'target_id':opt(ID),'effector':DETAIL,'operation':S,'trigger':S,'path':DETAIL,'speed':DETAIL,'support':DETAIL,'contact':DETAIL,'feedback':S,'settle':S,'depends_on':arr(DEPENDENCY),'markers':arr(obj({'id':ID,'at_ms':N,'meaning':S})),'changes':arr(CHANGE)})
PERFORMANCE=obj({**SPAN,'action_ids':arr(ID),'actor_id':ID,'behavior':S,'trigger':S,'feedback':S,'settle':S,'face':DETAIL,'eyes':DETAIL,'hands':DETAIL,'body':DETAIL,'breathing':DETAIL,'voice':DETAIL,'needed_parts':arr(S),'readability':enum('body','face','detail'),'psychology':opt(obj({'intent':S,'visible_translation':S,'audibility':enum('silent','internal_voice'),'utterance_id':opt(ID)}))})
CAMERA=obj({**SPAN,'operation':enum('unknown','locked','dolly_in','dolly_out','truck','pan','tilt','pedestal','orbit','tracking','handheld','zoom','rack_focus'),'start_position':S,'end_position':S,'start_framing':S,'end_framing':S,'height':S,'orientation':S,'path':S,'speed':S,'look_at':S,'focus':S,'axis':S,'sync_action_ids':arr(ID),'precision':enum('intent','reference_required','controlled')})
AUDIO=obj({**SPAN,'kind':enum('dialogue','narration','internal_voice','sfx','ambience','music','silence'),'speaker_id':opt(ID),'text':S,'placement':enum('on_screen','off_screen','voice_over','environment'),'lip_sync':{'type':'boolean'},'route':enum('native','post'),'delivery':S,'mix':S,'overlap_reason':opt(S),'source_utterance_id':opt(ID),'sync':opt(obj({'action_id':ID,'anchor':enum('start','end','marker'),'marker_id':opt(ID),'offset_ms':{'type':'number'}})),'phrases':arr(obj({'start_ms':N,'end_ms':N,'text':S,'delivery':S}))})
SNAPSHOT=obj({'id':ID,'shot_id':ID,'at_ms':N,'entities':{'type':'object','propertyNames':ID,'additionalProperties':STATE},'origin':ORIGIN})
VISIBILITY=obj({'shot_id':ID,'entity_id':ID,'start_ms':N,'end_ms':N,'parts':arr(S),'readability':enum('body','face','detail'),'reason':S})
SEGMENT=obj({'id':ID,'start_ms':N,'end_ms':N,'shot_ids':arr(ID,1),'status':enum('proposed','accepted'),'continuous_shot':{'type':'boolean'},'entry_state':S,'exit_state':S,'camera_continuity':S,'audio_continuity':S,'reference_plan':S,'overlap_ms':N,'cost_impact':S})
EXTENSION=obj({'name':S,'version':S,'channel':enum('prompt','post','parameter','review'),'instruction':S,'payload':{},'supported':{'type':'boolean'},'origin':ORIGIN})
TIMELINE=obj({'schema':{'const':'detail-timeline/1.1'},'coordinate_system':{'const':'x-right,y-up,z-depth; screen and anatomical directions are separate'},'action_groups':arr(obj({'id':ID,'parent_id':opt(ID),'purpose':S,'beat_ids':arr(ID),'origin':ORIGIN})),
 'actions':arr(ACTION),'performances':arr(PERFORMANCE),'camera_operations':arr(CAMERA,1),'audio_events':arr(AUDIO),
 'state_samples':arr(SNAPSHOT,2),'visibility':arr(VISIBILITY),'segments':arr(SEGMENT),
 'source_time_maps':arr(obj({'source_id':ID,'source_start_ms':N,'source_end_ms':N,'project_start_ms':N,'project_end_ms':N,'method':enum('identity','trim','retime','design'),'evidence':S})),
 'extensions':arr(EXTENSION),'semantic_review':obj({'status':enum('PENDING','PASS','FAIL'),'reviewer':opt(S),'input_sha256':opt(S),'findings':arr(S)})})


def schema(kind, original):
 d=deepcopy(original);d['$id']=d.get('$id','https://local/'+kind).replace('.schema.json','-1.1.schema.json')
 key='schema' if kind=='avir' else 'schema_version'
 d['properties'][key]={'const':{'avir':'avir/1.1','storyboard-ir':'storyboard-ir/1.1','director-ir':'1.1'}[kind]}
 d['properties']['timeline']=deepcopy(TIMELINE);d['required'].append('timeline')
 if kind in ('avir','director-ir'):d['properties']['entities']['items']['properties']['kind']['enum'].append('voice')
 if kind=='avir':d['properties']['sources']['items']['properties']['utterances']=arr(obj({'id':ID,'speaker_id':ID,'kind':enum('dialogue','narration','internal_voice'),'text':S,'span':obj({'start':N,'end':N})}))
 # Keep established native static fields. Temporal authoring has exactly one owner.
 shot=d['$defs']['shot'] if kind=='storyboard-ir' else d['properties']['shots']['items']
 for field in ('events','performance','phases','dialogue'):
  if field in shot['properties']:shot['properties'][field]={'const':[]}
 if 'audio' in d['properties']:d['properties']['audio']={'const':{'utterances':[],'cues':[]}}
 # Fractional frame rates are native timebase values, not rounded integers.
 if kind=='storyboard-ir':d['$defs']['delivery']['properties']['fps']={'oneOf':[{'type':'number','exclusiveMinimum':0},{'type':'string','pattern':'^[1-9][0-9]*/[1-9][0-9]*$'}]}
 if kind=='director-ir':d['properties']['format']['properties']['fps']={'oneOf':[{'type':'number','exclusiveMinimum':0},{'type':'string','pattern':'^[1-9][0-9]*/[1-9][0-9]*$'}]}
 return d
