"""Authoritative additive native 1.2 schema. Native 1.1 remains immutable."""
from copy import deepcopy
S={'type':'string','minLength':1};ID={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_-]*$'};N={'type':'number','minimum':0};NUM={'type':'number'}
def array(item,minimum=0):return {'type':'array','items':item,'minItems':minimum}
def obj(p):return {'type':'object','properties':p,'required':list(p),'additionalProperties':False}
def nullable(x):return {'anyOf':[x,{'type':'null'}]}
def enum(*v):return {'enum':list(v)}
VEC={**array(NUM,3),'maxItems':3};BOX={**array(NUM,4),'maxItems':4};BASIS={**array(VEC,3),'maxItems':3}
ORIGIN=obj({'kind':enum('observed','source','design'),'source_refs':array(ID,1),'locator':S})
FRAME=obj({'kind':enum('world','screen','local','anatomical'),'anchor_node_id':nullable(ID),'unit':enum('m','normalized','relative'),'transforms':array(obj({'at_ms':N,'origin':VEC,'basis':BASIS}))})
NODE=obj({'id':ID,'entity_id':nullable(ID),'kind':enum('entity','part','camera','region','group'),'label':S,'part':nullable(S),'parent_id':nullable(ID),'frame':FRAME,'bounds':nullable(obj({'min':VEC,'max':VEC})),'origin':ORIGIN})
VALUE=obj({'mode':enum('numeric','relative'),'value':nullable({'oneOf':[NUM,VEC]}),'description':S,'target_node_id':nullable(ID)})
KEY=obj({'at_ms':N,'value':VALUE,'transition':enum('none','hold','linear')})
PROPS=('position','orientation','gaze','rotation','zoom','focus','deformation','extent','group_motion','light','color','material','atmosphere')
TRACK=obj({'id':ID,'node_id':ID,'property':enum(*PROPS),'start_ms':N,'end_ms':N,'shot_ids':array(ID,1),'action_ids':array(ID),'camera_operation_ids':array(ID),'unit':enum('m','normalized','degrees','unitless','relative','kelvin'),'axis':nullable(VEC),'path':S,'speed':S,'keyframes':array(KEY,2),'origin':ORIGIN})
SCOPE={'oneOf':[obj({'kind':{'const':'point'},'at_ms':N}),obj({'kind':{'const':'interval'},'start_ms':N,'end_ms':N})]}
RELATIONS=('world_left_of','world_right_of','world_in_front_of','world_behind','screen_left_of','screen_right_of','above','below','near','far','faces','touching','supports','contains','occludes','attached_to')
REL=obj({'id':ID,'subject_node_id':ID,'object_node_id':ID,'predicate':enum(*RELATIONS),'frame':enum('world','screen','local','anatomical'),'scope':SCOPE,'shot_ids':array(ID,1),'criterion':S,'distance_m':nullable(N),'attachment':nullable(obj({'subject_part':S,'object_part':S,'relative_offset':nullable(VEC),'release_at_ms':nullable(N)})),'origin':ORIGIN})
SUBJECT=obj({'node_id':ID,'box':nullable(BOX),'depth':enum('foreground','midground','background','unspecified'),'visible_parts':array(S),'readability':enum('body','face','detail'),'occlusion':S,'presence':enum('inside','partial','outside'),'description':S})
COMPOSITION=obj({'id':ID,'shot_ids':array(ID,1),'start_ms':N,'end_ms':N,'framing':S,'attention_order':array(ID),'negative_space':S,'safe_area':S,'depth_layers':S,'subjects':array(SUBJECT,1),'origin':ORIGIN})

def schema(kind, previous):
 d=deepcopy(previous);d['$id']=d['$id'].replace('-1.1','-1.2');key='schema' if kind=='avir' else 'schema_version'
 d['properties'][key]={'const':{'avir':'avir/1.2','director-ir':'1.2','storyboard-ir':'storyboard-ir/1.2'}[kind]}
 timeline=d['properties']['timeline'];timeline['properties']['schema']={'const':'detail-timeline/1.2'}
 for name,definition in [('spatial_nodes',NODE),('motion_tracks',TRACK),('spatial_relations',REL),('composition_tracks',COMPOSITION)]:
  timeline['properties'][name]=array(definition,1 if name in ('spatial_nodes','composition_tracks') else 0);timeline['required'].append(name)
 if kind=='storyboard-ir':d['$defs']['shot']['properties']['relations']={'const':[]}
 if kind=='avir':
  d['properties']['shots']['items']['properties']['relations']={'const':[]}
 return d
