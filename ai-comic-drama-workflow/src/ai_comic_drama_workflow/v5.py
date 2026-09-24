"""V5 local coordinator: current-agent tasks, immutable native artifacts and real media records."""
from __future__ import annotations

from copy import deepcopy
from functools import wraps
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from .transactions import transaction, before_write
from .utils import atomic_write
from .v5_adapters import encoded, digest, pointer, assert_check, role_brief, image_briefs, storyboard_to_avir
from .v5_protocol import validate_protocol
from .v5_handoff import briefing, requirements, validate_handoff
from .v5_adapters import VERSION as ADAPTER_VERSION
from .v5_modules import ROOT, MODULES, read, digest_file, default_lock, module_path, native_validate, load_python, verify_archive, verify_module

STAGES = [(1,'资料与项目事实','canon',None), (2,'故事与剧本','screenplay','screenplay-grammar'),
          (3,'导演方案','director','director-grammar'), (4,'美术方案','art','production-design-grammar'),
          (5,'视觉资产','visual','image-prompt-optimizer'), (6,'分镜制作','storyboard','storyboard-grammar'),
          (7,'分镜图片','boards','image-prompt-optimizer'), (8,'视频提示词','compile','video-prompt-compiler'),
          (9,'验收与交付','qa',None)]
STAGE_BY_KIND={'canon':1,'screenplay':2,'director':3,'art':4,'storyboard':6,'avir':8,'qa':9}


def mutate(method):
    @wraps(method)
    def wrapper(self,*args,**kwargs):
        self.require_v5()
        with transaction(self.root):
            self.project=read(self.root/'project.json')
            if self.state.get('inflight') and method.__name__ not in ('run','submit','recover_image','host'):
                raise ValueError('Recover the in-flight image result before changing this project')
            return method(self,*args,**kwargs)
    return wrapper


def safe_id(value):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',value):
        raise ValueError('IDs must start with an ASCII letter and contain letters, numbers, _ or -')
    return value


class V5Kernel:
    def __init__(self,project,skill_root=ROOT):
        self.root=Path(project).expanduser().resolve()
        self.skill_root=Path(skill_root).resolve()
        self.project=read(self.root/'project.json') if (self.root/'project.json').exists() else {}

    def require_v5(self):
        if self.project.get('schema_version')!='5.0':
            raise ValueError('Legacy project is read-only. Use copy-project into a new V5 directory.')

    def path(self,relative):
        p=Path(relative)
        if p.is_absolute() or '..' in p.parts:raise ValueError('Expected a contained project path')
        target=(self.root/p).resolve()
        if not target.is_relative_to(self.root):raise ValueError('Path escapes project through a symlink')
        return target

    def write(self,relative,value):
        target=self.path(relative);before_write(self.root,target)
        atomic_write(target,encoded(value) if not isinstance(value,bytes) else value)
        return relative

    @property
    def state(self):return read(self.root/'state.json')

    def save(self,state):
        validate_protocol('state',state,self.skill_root)
        self.write('state.json',state)
        self.write('manifest.json',{'schema_version':'5.0','artifacts':state['artifacts'],'media':state['media']})

    def modules(self,name):return module_path(self.root,name,self.skill_root)

    def screenplay_protocol(self):
        if 'screenplay-grammar' not in read(self.root/'modules.lock.json')['modules']:return None
        return load_python(self.modules('screenplay-grammar'),'screenplay_protocol.py')

    def stage_module(self,kind):
        module=STAGES[STAGE_BY_KIND[kind]-1][3]
        if kind=='screenplay' and 'screenplay-grammar' not in read(self.root/'modules.lock.json')['modules']:return None
        return module

    @classmethod
    def initialize(cls,project,inputs,*,project_id='PROJECT',delivery='full',target=None,mode=None,skill_root=ROOT):
        root=Path(project).expanduser().resolve()
        if root.exists() and any(root.iterdir()):raise ValueError('New project directory must be empty')
        if delivery not in ('full','text-only'):raise ValueError('Delivery must be full or text-only')
        safe_id(project_id)
        root.mkdir(parents=True,exist_ok=True)
        kernel=cls(root,skill_root)
        kernel.project={'schema_version':'5.0','workflow_id':'ai-comic-drama-v5','project_id':project_id,
            'execution_mode':'current-agent','delivery':delivery,'target':target,'mode':mode or ('reference' if delivery=='full' else 'text'),
            'max_shots_per_task':5,'legacy_constraints':{},'adapter_version':ADAPTER_VERSION}
        validate_protocol('project',kernel.project,kernel.skill_root)
        kernel.write('project.json',kernel.project)
        lock=default_lock(skill_root);kernel.write('modules.lock.json',lock)
        for name in lock['modules']:
            source=Path(skill_root)/'assets/bundled-skills'/(name+'.skill')
            if digest_file(source)!=lock['modules'][name]['sha256']:raise ValueError('Bundled module differs from lock')
            dest=root/'runtime/module-archives'/(lock['modules'][name]['sha256']+'.skill')
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        kernel.write('phase-index.json',{'schema_version':'5.0','phases':[
            {'index':i,'name':n,'role':r,'module':m if m in lock['modules'] else None} for i,n,r,m in STAGES]})
        state={'schema_version':'5.0','artifacts':{},'media':{},'prompts':{},'approvals':{},'decisions':[],
               'completed_tasks':{},'active_task':None,'active_decision':None,'inflight':None,
               'status':'RUNNING','revision_scope':{},'provided_jobs':[],'host':{'image_capability':'unknown','evidence':None},
               'sources':[],'build':None}
        kernel.save(state)
        kernel.add(inputs)
        return kernel

    @mutate
    def add(self,inputs):
        state=self.state
        for value in inputs:
            p=Path(value).expanduser()
            try:is_file=p.is_file()
            except OSError:is_file=False
            if is_file:
                data=p.read_bytes();name=p.name;original=str(p.resolve())
            else:
                data=str(value).encode();name='source.txt';original='user-text'
            checksum=hashlib.sha256(data).hexdigest()
            if any(s['sha256']==checksum for s in state['sources']):continue
            ident='SRC_'+checksum[:12]
            uri='sources/'+ident+'/'+name
            self.write(uri,data)
            state['sources'].append({'id':ident,'uri':uri,'sha256':checksum,'original':original})
        state['active_task']=None;state['build']=None;state['status']='RUNNING'
        self.save(state)
        return self.status()

    def data(self,slot,state=None):
        record=(state or self.state)['artifacts'][slot]
        if digest_file(self.path(record['uri']))!=record['sha256']:raise ValueError('Artifact bytes changed: '+slot)
        return read(self.path(record['uri']))

    def dependency(self,slot,paths=None):
        value=self.data(slot)
        paths=paths or ['']
        return {'slot':slot,'pointers':paths,'fingerprint':digest([self.portable_content(pointer(value,p)) for p in paths])}

    def dependencies_valid(self,dependencies,state=None):
        state=state or self.state
        for dep in dependencies:
            try:
                if dep['slot']=='@sources':current=self.source_fingerprint_inputs()
                elif dep['slot']=='@target':current=[self.project.get('target'),self.project['mode'],self.project['delivery']]
                else:
                    artifact=state['artifacts'][dep['slot']]
                    if artifact.get('invalidated'):return False
                    if dep.get('selector',{}).get('kind')=='spatial_panel':
                        from .v52_spatial_runtime import panel_state
                        from .v52_adapters import spatial_panel_dependency
                        selector=dep['selector'];current=spatial_panel_dependency(panel_state(self.data(dep['slot'],state),selector['shot_id'],selector['at_ms']))
                    else:current=[self.portable_content(pointer(self.data(dep['slot'],state),p)) for p in dep['pointers']]
                if digest(current)!=dep['fingerprint']:return False
            except (KeyError,IndexError,ValueError,FileNotFoundError):return False
        return True

    def valid(self,slot,state=None):
        state=state or self.state;record=state['artifacts'].get(slot)
        if not record or record.get('invalidated') or not record.get('complete',True):return False
        if record.get('needs_reconciliation') and self.prerequisites_ready(record['kind']):return False
        try:
            data=self.data(slot,state)
            if slot=='qa' and (not state['build'] or data.get('build_id')!=state['build']['build_id']):return False
            if any(digest_file(self.path(p))!=h for p,h in record['files'].items()):return False
        except (ValueError,OSError):return False
        return self.dependencies_valid(record['dependencies'],state)

    def prerequisites_ready(self,kind):
        needed={'canon':[],'screenplay':['canon'],'director':['canon','screenplay'],
                'art':['canon','director'],'storyboard':['canon','director'],'avir':['storyboard'],'qa':['storyboard']}
        ready=all(self.valid(k) for k in needed.get(kind,[]))
        if kind=='storyboard' and ready:
            ready=all(self.valid('art:'+s['id']) for s in self.data('director')['scenes'])
        return ready

    def handoff_inputs(self,dependencies):
        state=self.state
        return [(d['slot'],self.data(d['slot'],state),state['artifacts'][d['slot']])
                for d in dependencies if not d['slot'].startswith('@')]

    def input_records(self,dependencies,state):
        return [dict(slot=d['slot'],uri=str(self.path(state['artifacts'][d['slot']]['uri'])),
            sha256=state['artifacts'][d['slot']]['sha256'],pointers=d['pointers'])
            for d in dependencies if not d['slot'].startswith('@')]

    def role_dependencies(self,kind,scope=None):
        state=self.state;scope=scope or {}
        if kind=='canon':return [{'slot':'@sources','pointers':[],
            'fingerprint':digest(self.source_fingerprint_inputs())}]
        if kind=='screenplay':return [self.dependency('canon')]
        if kind=='director':return [self.dependency('canon'),self.dependency('screenplay')]
        if kind=='art':
            director=self.data('director');sid=scope['scene_ids'][0]
            paths=[f'/scenes/{i}' for i,s in enumerate(director['scenes']) if s['id']==sid]
            paths += [f'/shots/{i}' for i,s in enumerate(director['shots']) if s['scene_id']==sid]
            paths += ['/entities','/contract']
            return [self.dependency('director',paths),self.dependency('canon')]
        if kind=='storyboard':
            return [self.dependency(k) for k in state['artifacts'] if k=='director' or k.startswith('art:')]+[self.dependency('canon')]
        if kind=='avir':return [self.dependency('storyboard')]
        if kind=='qa':
            deps=[self.dependency('storyboard')]
            deps.append({'slot':'@target','pointers':[],
                'fingerprint':digest([self.project.get('target'),self.project['mode'],self.project['delivery']])})
            return deps
        return []

    def task(self,kind,slot,stage,module,dependencies,scope=None,extra=None):
        state=self.state
        extra=extra or {}
        context={'kind':kind,'slot':slot,'dependencies':dependencies,'scope':scope or {},
                 'modules':read(self.root/'modules.lock.json'),'extra':extra,'project':self.project,
                 'completed_count':len(state['completed_tasks']),
                 'previous':state['artifacts'].get(slot) or state['media'].get(slot)}
        task_id='TASK_'+digest(context)[:24]
        task={'schema':'task-envelope/5.0','task_id':task_id,'context_fingerprint':digest(context),
              'project_id':self.project['project_id'],'stage':stage,'kind':kind,'slot':slot,
              'execution_mode':'current-agent','scope':scope or {},'dependencies':dependencies,
              'inputs':self.input_records(dependencies,state),'sources':state['sources'],
              'module':{'name':module,'path':str(self.modules(module)),
                        **context['modules']['modules'][module]} if module else None,
              'max_shots_per_task':5,'expected_result':'role-result/5.0','output_contract':{'kind':kind,'format':'native artifact + role-result/5.0'},
              'brief':role_brief(kind,self.input_records(dependencies,state),scope),
              'project':self.project,'handoff':briefing(kind,self.handoff_inputs(dependencies),scope,self.screenplay_protocol() if kind=='director' else None),**extra}
        task['handoff']['reference_observations']=self.observation_status()
        if slot in state['artifacts']:task['previous']=state['artifacts'][slot]
        task['existing_media']=[v for v in state['media'].values() if self.media_valid(v,state)]
        migration=self.root/'imports/migration.json'
        if migration.exists():
            task['migration_report']=str(migration)
            task['reusable_media_candidates']=read(migration)['media_candidates']
        validate_protocol('task-envelope',task,self.skill_root)
        self.write('runtime/tasks/'+task_id+'.json',task)
        state.update(active_task=task_id,active_task_sha256=digest(task),status='AWAITING_CURRENT_AGENT')
        self.save(state)
        return {'status':state['status'],'task':task,'task_file':str(self.path('runtime/tasks/'+task_id+'.json'))}

    def decision(self,key,question,context,options):
        state=self.state
        identifier='DEC_'+digest({'key':key,'context':context})[:24]
        request={'id':identifier,'key':key,'question':question,'context':context,'options':options}
        state.update(active_decision=request,status='AWAITING_USER_DECISION')
        self.save(state)
        return {'status':state['status'],'decision':request}

    @mutate
    def host(self,image_capability,evidence):
        if image_capability not in ('available','unavailable','unknown') or not evidence:
            raise ValueError('Host capability and evidence are required')
        state=self.state;state['host']={'image_capability':image_capability,'evidence':evidence}
        if image_capability=='available' and (state['active_decision'] or {}).get('key')=='image-capability':
            state['active_decision']=None
        self.save(state)
        return self.status()

    def image_jobs(self,stage):
        state=self.state;jobs=[]
        kinds=[(k,'art') for k in state['artifacts'] if k.startswith('art:')] if stage==5 else [('storyboard','storyboard')]
        for slot,kind in kinds:
            ir=self.data(slot,state)
            for brief in image_briefs(kind,ir):
                if kind=='art' and not brief['entity_id']:
                    continue  # Design proposals must first receive a Canon entity ID.
                deps=[self.dependency(slot,brief['dependency_paths'])]
                if brief.get('spatial_dependency'):
                    sample=brief['spatial_dependency'];deps.append({'slot':slot,'pointers':[],'selector':{'kind':'spatial_panel','shot_id':sample['shot_id'],'at_ms':sample['at_ms']},'fingerprint':digest(sample['value'])})
                key=('ASSET_'+ir['set']['scene_id']+'_' if stage==5 else 'BOARD_')+brief['id']
                refs=[]
                if stage==7:
                    shot=ir['shots'][int(brief['source_pointer'].split('/')[2])]
                    panel=shot['panels'][int(brief['source_pointer'].split('/')[4])]
                    participants=set(panel.get('subject_ids',shot['state_start']))
                    refs=[{'key':m['key'],'uri':m['uri'],'sha256':m['sha256'],'entity_id':m.get('entity_id'),
                           'purpose':('identity/wardrobe' if m['role']=='identity' else 'object/scene appearance')+' only; preserve the requested panel composition'}
                          for m in state['media'].values() if m['stage']==5 and m.get('entity_id') in participants and self.media_valid(m,state)]
                scoped={k:v for k,v in brief.items() if k!='source_hash'}
                fingerprint=digest({'brief':self.portable_content(scoped),'references':[{k:v for k,v in r.items() if k!='uri'} for r in refs],'module':read(self.root/'modules.lock.json')['modules']['image-prompt-optimizer']['sha256']})
                jobs.append({'key':key,'stage':stage,'brief':brief,'dependencies':deps,'references':refs,
                    'fingerprint':fingerprint,'entity_id':brief.get('entity_id'),'shot_id':brief.get('shot_id'),
                    'role':'identity' if brief.get('kind') in ('character','role','costume','person') else brief['kind']})
        return jobs

    def media_valid(self,media,state=None):
        try:
            state=state or self.state
            if media.get('invalidated') or digest_file(self.path(media['uri']))!=media['sha256']:return False
            if not self.dependencies_valid(media['dependencies'],state):return False
            for binding in media.get('input_bindings',[]):
                parent=state['media'].get(binding['key'])
                if not parent or parent.get('invalidated') or parent['sha256']!=binding['sha256']:return False
                if digest_file(self.path(parent['uri']))!=parent['sha256']:return False
            return media['visual_review']['status']=='PASS'
        except (KeyError,ValueError,OSError):return False

    def images_step(self,stage):
        state=self.state
        if self.project['delivery']=='text-only':return None
        for job in self.image_jobs(stage):
            if job['brief'].get('state_evaluation', {}).get('status') == 'NEEDS_KEY_POSE':
                return {'status':'BLOCKED','reason':'Exact panel key pose is missing; submit an explicit state sample, not inferred interpolation','shot_id':job['shot_id'],'frame':job['brief']['frame']}
            media=state['media'].get(job['key'])
            if media and self.media_valid(media,state) and media['input_fingerprint']==job['fingerprint']:
                if media['role']=='identity' and state['approvals'].get(job['key'],{}).get('token')!=self.approval_token(media):
                    return self.decision('identity:'+job['key'],'请确认该角色身份参考图是否定稿。',
                        {'media_key':job['key'],'sha256':media['sha256'],'uri':str(self.path(media['uri'])),
                         'token':self.approval_token(media)},['approve','revise'])
                continue
            prompt=state['prompts'].get(job['key'])
            if not prompt or prompt['input_fingerprint']!=job['fingerprint'] or not self.prompt_valid(prompt):
                return self.task('image-prompt',job['key'],stage,'image-prompt-optimizer',job['dependencies'],extra={'job':job})
            if state['host']['image_capability']!='available' and job['key'] not in state.get('provided_jobs',[]):
                return self.decision('image-capability','宿主未证明生图能力可用；可提供真实图片、配置能力后继续，或明确选择纯文本。',
                    {'job':job['key'],'capability':state['host']},['provide-media','text-only'])
            return self.task('image',job['key'],stage,None,job['dependencies'],
                extra={'job':job,'prompt':prompt,'host_action':'generate-or-import-image'})
        return None

    def prompt_valid(self,prompt):
        try:return digest_file(self.path(prompt['uri']))==prompt['sha256']
        except OSError:return False

    @staticmethod
    def approval_token(media):
        return digest({k:media.get(k) for k in ('key','sha256','input_fingerprint','entity_id','role','revision')})

    @mutate
    def import_observation(self,bundle):
        """Register real extracted/reviewed frame bytes without altering source media."""
        from .v51_observe_video import record_review
        bundle=Path(bundle).resolve();manifest=read(bundle/'observation.json')
        sources=[x for x in self.state['sources'] if x['sha256']==manifest['source_sha256']]
        if not sources:raise ValueError('Observation source is not registered in this project')
        # Validate the original evidence in place, then copy immutable bytes.
        review=record_review(bundle,bundle/'review.json')
        key=digest({'manifest':manifest,'review':review});prefix='observations/'+manifest['source_sha256']+'/'+key
        for frame in manifest['frames']:
            file=Path(frame['file'])
            if file.name!=frame['file']:raise ValueError('Observation frame path must be a filename')
            if digest_file(bundle/file)!=frame['sha256']:raise ValueError('Observation frame changed')
            self.write(prefix+'/'+file.name,(bundle/file).read_bytes())
        self.write(prefix+'/observation.json',manifest);self.write(prefix+'/review.json',review)
        files={f['file']:f['sha256'] for f in manifest['frames']}
        files.update({'observation.json':digest_file(self.path(prefix+'/observation.json')),'review.json':digest_file(self.path(prefix+'/review.json'))})
        self.write(prefix+'/manifest.json',{'source_sha256':manifest['source_sha256'],'files':files})
        return {'status':'REGISTERED','uri':prefix,'visual_review':review['visual_review'],'audio_review':review['audio_review'],'complete_motion_coverage':False}

    def source_fingerprint_inputs(self):
        rows=[(s['id'],s['sha256']) for s in self.state['sources']]
        for p in sorted(self.path('observations').glob('*/*/manifest.json')):rows.append((str(p.relative_to(self.root)),digest_file(p)))
        return rows

    def observation_status(self):
        rows=[]
        for source in self.state['sources']:
            if Path(source['uri']).suffix.lower() not in ('.mp4','.mov','.mkv','.webm','.m4v','.avi'):continue
            records=[]
            folder=self.path('observations/'+source['sha256'])
            for receipt in sorted(folder.glob('*/manifest.json')):
                record=read(receipt)
                if record['source_sha256']!=source['sha256'] or any(not (receipt.parent/name).is_file() or digest_file(receipt.parent/name)!=checksum for name,checksum in record['files'].items()):raise ValueError('Observation evidence changed')
                records.append({'uri':str(receipt.parent.relative_to(self.root)),'review':read(receipt.parent/'review.json')})
            rows.append({'source_id':source['id'],'source_uri':source['uri'],'status':'RECORDED_SCOPE_ONLY' if records else 'NEEDS_ACTUAL_OBSERVATION','records':records})
        return rows

    @mutate
    def run(self):
        state=self.state
        if state.get('blocked_decision'):
            return {'status':'BLOCKED','decision':state['blocked_decision'],'instruction':'Revise the affected proposal before continuing.'}
        for source in state['sources']:
            if not self.path(source['uri']).is_file() or digest_file(self.path(source['uri']))!=source['sha256']:
                return {'status':'BLOCKED','reason':'Source file missing or changed','source_id':source['id']}
        observations=self.observation_status()
        if any(x['status']=='NEEDS_ACTUAL_OBSERVATION' for x in observations):
            return {'status':'NEEDS_REFERENCE_OBSERVATION','sources':observations,'instruction':'Use locked director observe_video.py, actually view relevant frames, record scope and audio status, then import-observation. Sampling alone is not a review.'}
        if state['inflight']:
            return {'status':'AWAITING_MEDIA_RESULT','inflight':state['inflight'],
                    'instruction':'Recover the existing tool result. Do not repeat generation without an explicit retry decision.'}
        if state['active_decision']:return {'status':'AWAITING_USER_DECISION','decision':state['active_decision']}
        for kind in ('canon','screenplay','director'):
            if not self.valid(kind):
                i=STAGE_BY_KIND[kind];module=self.stage_module(kind)
                return self.task(kind,kind,i,module,self.role_dependencies(kind),state['revision_scope'])
        director=self.data('director')
        for scene in director['scenes']:
            slot='art:'+scene['id'];scope={'scene_ids':[scene['id']]}
            if not self.valid(slot):return self.task('art',slot,4,'production-design-grammar',self.role_dependencies('art',scope),scope)
        step=self.images_step(5)
        if step:return step
        if not self.valid('storyboard'):
            return self.task('storyboard','storyboard',6,'storyboard-grammar',self.role_dependencies('storyboard'),state['revision_scope'])
        step=self.images_step(7)
        if step:return step
        if state['artifacts'].get('avir',{}).get('invalidated'):
            return self.task('avir','avir',8,'video-prompt-compiler',self.role_dependencies('avir'))
        if not self.project.get('target'):
            return self.decision('target','请指定视频提示词的目标模型/入口。',{},['set-target'])
        build=self.build_fingerprint()
        state=self.state
        if not state['build'] or state['build']['input_fingerprint']!=build:
            compiled=self.compile()
            if compiled['status']=='BLOCKED':return compiled
        if not self.valid('qa'):
            return self.task('qa','qa',9,None,self.role_dependencies('qa'),extra={'build':self.state['build']})
        return self.export()

    def snapshot(self,kind,path):
        """Copy native input and local dependencies; preserve raw bytes and report rebasing."""
        path=Path(path).expanduser().resolve();raw=path.read_bytes()
        closure={}
        def collect(source,native=True):
            source=source.resolve()
            if str(source) in closure:return
            closure[str(source)]=digest_file(source)
            if not native:return
            obj=read(source)
            for entries,field,nested in [('sources','uri',False),('assets','path',False),
                                          ('references','file',False),('upstreams','uri',True)]:
                for entry in obj.get(entries,[]):
                    value=entry.get(field)
                    if value and '://' not in value and (source.parent/value).is_file():collect(source.parent/value,nested)
            if isinstance(obj.get('director'),dict):collect(source.parent/obj['director']['uri'])
        collect(path)
        prefix='artifacts/'+kind+'/'+digest({'raw':hashlib.sha256(raw).hexdigest(),'closure':closure})
        cache={};copies={};rebases=[]
        def copy_file(source):
            source=source.resolve()
            if not source.is_file():raise ValueError('Missing imported dependency: '+str(source))
            relative=prefix+'/files/'+digest_file(source)+'/'+source.name
            self.write(relative,source.read_bytes());copies[relative]=digest_file(source)
            return str(self.path(relative))
        def capture(source,native_kind=None):
            source=source.resolve()
            if str(source) in cache:return cache[str(source)]
            obj=read(source)
            raw_name=prefix+'/raw/'+digest_file(source)[:16]+'_'+source.name
            self.write(raw_name,source.read_bytes());copies[raw_name]=digest_file(source)
            working=prefix+'/native/'+digest_file(source)[:16]+'_'+source.name
            cache[str(source)]=str(self.path(working))
            refs=[]
            for entry in obj.get('sources',[]):
                if entry.get('uri') and '://' not in entry['uri'] and (source.parent/entry['uri']).is_file():
                    refs.append((entry,'uri',False))
            for entry in obj.get('assets',[]):
                if entry.get('path'):refs.append((entry,'path',False))
            for entry in obj.get('references',[]):
                if entry.get('file'):refs.append((entry,'file',False))
            for entry in obj.get('upstreams',[]):refs.append((entry,'uri',True))
            if obj.get('schema')=='script-ir/1.0' and obj.get('canon',{}).get('ref'):
                refs.append((obj['canon']['ref'],'uri',False))
            if isinstance(obj.get('director'),dict):refs.append((obj['director'],'uri',True))
            for entry,field,nested in refs:
                old=entry[field]
                if '://' in old:continue
                dest=capture(source.parent/old) if nested else copy_file(source.parent/old)
                entry[field]=dest
                if nested and 'sha256' in entry:entry['sha256']=digest_file(dest)
                rebases.append({'source':old,'destination':dest})
            self.write(working,obj);copies[working]=digest_file(self.path(working))
            return str(self.path(working))
        captured=Path(capture(path,kind))
        self.write(prefix+'/import.json',{'original_uri':str(path),'original_sha256':hashlib.sha256(raw).hexdigest(),'rebases':rebases})
        return captured.relative_to(self.root).as_posix(),copies

    def check_content(self,kind,value,path):
        if value.get('project_id')!=self.project['project_id']:
            raise ValueError('Native project_id differs; use the same project ID or an explicit source-preserving migration')
        if kind in ('director','art','storyboard','avir'):
            native_validate(kind,path,self.modules)
        elif kind=='screenplay' and self.screenplay_protocol():
            if value.get('schema')!='script-ir/1.0':
                raise ValueError('Legacy screenplay needs source-preserving structuring into ScriptIR; not automatically accepted')
            native_validate(kind,path,self.modules)
            available={s['id']:s for s in self.state['sources']}; hashes={s['sha256'] for s in self.state['sources']}
            original_sources=[s for s in value['sources'] if s['kind'] in ('user','original')]
            if not original_sources:raise ValueError('Screenplay requires a registered original source')
            for source in value['sources']:
                if source['kind'] in ('user','original'):
                    expected=available.get(source['id'],{}).get('sha256')
                    if (expected and source['sha256']!=expected) or source['sha256'] not in hashes:
                        raise ValueError('Unknown or changed narrative source: '+source['id'])
            if self.valid('canon'):
                canon=self.data('canon');ref=value['canon']['ref']
                if not ref or ref['sha256']!=self.state['artifacts']['canon']['sha256']:
                    raise ValueError('Screenplay must bind the current Canon; reconcile design proposals and re-review')
                known={e['id'] for e in canon.get('entities',[])}
                if any(c['id'] not in known for c in value['characters']):
                    raise ValueError('Register screenplay characters with the Canon owner before handoff')
                for lock in canon.get('locks',[]):
                    if lock['kind']=='screenplay' and not assert_check(value,lock['check']):raise ValueError('Canon screenplay lock fails')
        elif kind in ('canon','screenplay'):
            if not value.get('content') or not value.get('source_refs'):
                raise ValueError('Narrative content and source_refs are required')
            available={s['id'] for s in self.state['sources']}
            if not set(value['source_refs'])<=available:raise ValueError('Unknown narrative source ID')
            if kind=='canon':
                entities=value.get('entities',[])
                if len({e['id'] for e in entities})!=len(entities):raise ValueError('Duplicate Canon entity IDs')
                for e in entities:safe_id(e['id'])
        elif kind=='qa':
            if value.get('passed') is not True or not value.get('checks') or value.get('build_id')!=self.state['build']['build_id']:
                raise ValueError('QA must check the current build and contain actual review findings')
        canon=self.data('canon') if kind not in ('canon','screenplay','qa') and self.valid('canon') else None
        if canon and kind=='art':
            known={e['id'] for e in canon.get('entities',[])}
            for asset in value['assets']:
                if asset.get('entity_id') not in known:raise ValueError('Art asset requires a registered Canon entity: '+asset['id'])
        if canon and kind in ('director','storyboard','avir'):
            known={e['id']:e for e in canon.get('entities',[])}
            for entity in value['entities']:
                if entity['id'] not in known:raise ValueError('Unregistered entity: '+entity['id'])
                for field,expected in known[entity['id']].get('locked_fields',{}).items():
                    if pointer(entity,field)!=expected:raise ValueError('Canon identity lock changed: '+entity['id']+field)
        if canon:
            for lock in canon.get('locks',[]):
                if lock['kind']==kind and not assert_check(value,lock['check']):raise ValueError('Canon hard lock fails: '+lock['check']['path'])

    @mutate
    def import_artifact(self,kind,path,*,slot=None,scope=None,dependencies=None,complete=True,locks=None,handoff=None):
        if kind not in STAGE_BY_KIND:raise ValueError('Unknown native artifact kind')
        source=Path(path).expanduser().resolve();value=read(source)
        slot=slot or ('art:'+value['set']['scene_id'] if kind=='art' else kind)
        scope=scope or ({'scene_ids':[value['set']['scene_id']]} if kind=='art' else {})
        self.check_content(kind,value,source)
        state=self.state
        old=state['artifacts'].get(slot)
        for lock in (old or {}).get('locks',[]):
            if not assert_check(value,lock):raise ValueError('Previously locked field changed: '+lock['path'])
        for lock in locks or []:
            if not assert_check(value,lock):raise ValueError('Newly declared lock does not hold: '+lock['path'])
        uri,files=self.snapshot(kind,source)
        self.check_content(kind,self.data_from_uri(uri),self.path(uri))
        ready=self.prerequisites_ready(kind)
        if dependencies is None:
            dependencies=self.role_dependencies(kind,scope) if ready else []
        protocol=self.screenplay_protocol() if kind=='director' else None
        required=requirements(kind,self.handoff_inputs(dependencies),protocol)
        screenplay=(self.data('screenplay'),protocol) if protocol and self.valid('screenplay') else None
        review=validate_handoff(kind,value,required,handoff,screenplay)
        module=self.stage_module(kind)
        record={'kind':kind,'slot':slot,'stage':STAGE_BY_KIND[kind],'uri':uri,'sha256':digest_file(self.path(uri)),
            'original_sha256':digest_file(source),'revision':(old or {}).get('revision',0)+1,'scope':scope or {},
            'dependencies':dependencies,'files':files,'locks':locks if locks is not None else (old or {}).get('locks',[]),
            'complete':complete,'invalidated':False,'needs_reconciliation':not ready,
            'handoff':review,'module':read(self.root/'modules.lock.json')['modules'].get(module),
            'adapter_version':ADAPTER_VERSION}
        if old:self.write('history/'+digest(old)+'.json',old)
        state['artifacts'][slot]=record;state['active_task']=None;state['status']='RUNNING'
        if kind=='director':
            scenes={s['id'] for s in value['scenes']}
            for key in list(state['artifacts']):
                if key.startswith('art:') and key[4:] not in scenes:
                    retired=state['artifacts'].pop(key);self.write('history/retired-'+digest(retired)+'.json',retired)
        if kind!='qa':state['build']=None
        self.save(state)
        return record

    def data_from_uri(self,uri):return read(self.path(uri))

    @mutate
    def submit(self,result):
        result=read(Path(result)) if not isinstance(result,dict) else result
        validate_protocol('role-result',result,self.skill_root)
        state=self.state;task_id=result['task_id']
        if task_id in state['completed_tasks']:
            if state['completed_tasks'][task_id]!=digest(result):raise ValueError('Conflicting duplicate task result')
            return {'status':'ALREADY_ACCEPTED','task_id':task_id}
        if task_id!=state['active_task']:raise ValueError('Result is not for the active task')
        task=read(self.path('runtime/tasks/'+task_id+'.json'))
        if digest(task)!=state.get('active_task_sha256'):raise ValueError('Task envelope hash changed')
        if result.get('context_fingerprint')!=task['context_fingerprint'] or not self.dependencies_valid(task['dependencies']):
            raise ValueError('Stale task context')
        if result.get('conflicts') or result.get('unresolved'):
            uri='runtime/conflicts/'+task_id+'/'+digest(result)+'.json';self.write(uri,result)
            return {'status':'BLOCKED','conflicts':result.get('conflicts',[]),'unresolved':result.get('unresolved',[]),'result_file':str(self.path(uri))}
        kind=task['kind']
        if kind=='image-prompt':
            if not result.get('checks') or not str(result.get('prompt','')).strip():raise ValueError('Prompt text and actual constraint findings are required')
            uri='prompts/'+task['slot']+'/'+digest(result)+'.txt';self.write(uri,result['prompt'].encode())
            state['prompts'][task['slot']]={'uri':uri,'sha256':digest_file(self.path(uri)),
                'input_fingerprint':task['job']['fingerprint'],'checks':result['checks']}
        elif kind=='image':
            media=self.accept_media(task,result)
            old=state['media'].get(task['slot'])
            if old:self.write('history/media-'+digest(old)+'.json',old)
            state['media'][task['slot']]=media;state['inflight']=None;state['build']=None
        else:
            path=Path(result['artifact']).resolve()
            if result.get('artifact_sha256')!=digest_file(path):raise ValueError('Native result artifact hash differs')
            if result.get('manifest') and result.get('manifest_sha256')!=digest_file(Path(result['manifest'])):
                raise ValueError('Native result manifest hash differs')
            value=read(path)
            if not result.get('reused') and isinstance(value.get('shots'),list):
                previous=self.data(task['slot']) if task['slot'] in state['artifacts'] else {'shots':[]}
                old={s['id']:s for s in previous['shots']}
                current={s['id']:s for s in value['shots']}
                changed=[sid for sid in old.keys()|current.keys() if old.get(sid)!=current.get(sid)]
                if previous.get('timeline') and value.get('timeline'):
                    from .v51_detail_runtime import changed_shots
                    if value.get('schema_version')=='storyboard-ir/1.2' or value.get('schema_version')=='1.2':
                        from .v52_spatial_runtime import changed_shots
                    changed=list(set(changed)|set(changed_shots(previous,value)))
                if len(changed)>5:raise ValueError('A creative result may change at most five shots; submit a partial revision or import a reviewed existing package')
                allowed=task.get('scope',{}).get('shot_ids')
                if allowed and not set(changed)<=set(allowed):raise ValueError('Changes exceed the scoped shot revision')
            self.import_artifact(kind,path,slot=task['slot'],scope=task['scope'],dependencies=task['dependencies'],
                complete=result.get('complete',True),locks=result.get('locks'),handoff=result.get('handoff'))
            state=self.state
        state['completed_tasks'][task_id]=digest(result);state['active_task']=None
        if result.get('complete',True):state['revision_scope']={}
        state['status']='RUNNING';self.save(state)
        self.write('runtime/results/'+task_id+'.json',result)
        return {'status':'ACCEPTED','task_id':task_id}

    def accept_media(self,task,result):
        job=task['job'];media=result['media'];path=Path(media['path']).expanduser().resolve()
        if not self.prompt_valid(task['prompt']):raise ValueError('Image prompt file changed')
        if path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
            raise ValueError('A still PNG, JPEG or WebP image is required')
        if media.get('provider') not in ('image_gen','provided') or not media.get('call_evidence'):
            raise ValueError('Media requires a real provider/import and call evidence')
        if media.get('sha256')!=digest_file(path):raise ValueError('Media hash differs')
        expected=[{'key':r['key'],'sha256':r['sha256']} for r in job['references']]
        if media.get('input_bindings')!=expected:raise ValueError('Actual image references do not match the job')
        review=media.get('visual_review',{})
        if review.get('status')!='PASS' or not review.get('findings') or review.get('sha256')!=media['sha256']:
            raise ValueError('Visual review must inspect and bind the actual image bytes')
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,width,height','-of','json',str(path)],capture_output=True,text=True)
        try:streams=json.loads(probe.stdout)['streams']
        except (ValueError,KeyError):streams=[]
        if probe.returncode or not any(s.get('codec_type')=='video' and s.get('width',0)>0 for s in streams):
            raise ValueError('Media cannot be decoded as an image')
        decode=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-frames:v','1','-f','null','-'],capture_output=True)
        if decode.returncode:raise ValueError('Image frame decoding failed')
        old=self.state['media'].get(job['key'],{})
        revision=old.get('revision',0)+1
        uri=f"assets/{job['key']}/v{revision:03d}/{path.name}"
        self.write(uri,path.read_bytes())
        return {'key':job['key'],'uri':uri,'filename':path.name,'sha256':media['sha256'],'revision':revision,
            'stage':job['stage'],'role':job['role'],'entity_id':job['entity_id'],'shot_id':job['shot_id'],
            'frame':job['brief'].get('frame'),'moment':job['brief'].get('moment'),
            'input_fingerprint':job['fingerprint'],'dependencies':job['dependencies'],
            'input_bindings':expected,'visual_review':review,'provider':media['provider'],
            'call_evidence':media['call_evidence'],'prompt':task['prompt'],'invalidated':False}

    @mutate
    def begin_image(self,task_id):
        state=self.state
        if state['active_task']!=task_id:raise ValueError('Not the active task')
        task=read(self.path('runtime/tasks/'+task_id+'.json'))
        if task['kind']!='image':raise ValueError('Only image tasks may be marked in flight')
        if state['inflight']:raise ValueError('A generation is already in flight; recover it first')
        state['inflight']={'task_id':task_id,'key':task['slot'],'input_fingerprint':task['job']['fingerprint']}
        self.save(state);return {'status':'AWAITING_MEDIA_RESULT','inflight':state['inflight']}

    @mutate
    def recover_image(self,evidence):
        if not evidence:raise ValueError('Explicit retry authorization/evidence is required')
        state=self.state
        if not state['inflight']:raise ValueError('No uncertain image generation to recover')
        self.write('history/image-retry-'+digest(state['inflight'])+'.json',
                   {'previous':state['inflight'],'retry_decision':evidence})
        state['inflight']=None;self.save(state)
        return {'status':'RETRY_AUTHORIZED','task_id':state['active_task']}

    @mutate
    def update_modules(self,lock_path,archives):
        lock=read(Path(lock_path));old=read(self.root/'modules.lock.json')
        if set(lock['modules'])!=set(MODULES):raise ValueError('Expected the six professional modules')
        if lock.get('adapter_version')!=ADAPTER_VERSION:raise ValueError('Module lock requires another adapter version')
        changed=[]
        for name,item in lock['modules'].items():
            source=Path(archives)/(name+'.skill')
            verify_module(source,name,item)
            if item!=old['modules'].get(name):changed.append(name)
            self.write('runtime/module-archives/'+item['sha256']+'.skill',source.read_bytes())
        self.write('history/modules-'+digest(old)+'.json',old);self.write('modules.lock.json',lock)
        state=self.state
        affected={'screenplay-grammar':'screenplay','director-grammar':'director','production-design-grammar':'art','storyboard-grammar':'storyboard'}
        for record in state['artifacts'].values():
            if record['kind'] in [affected[n] for n in changed if n in affected]:record['invalidated']=True
        self.write('phase-index.json',{'schema_version':'5.0','phases':[
            {'index':i,'name':n,'role':r,'module':m} for i,n,r,m in STAGES]})
        state.update(active_task=None,build=None,status='RUNNING')
        self.save(state)
        return {'status':'UPDATED','changed':changed,'existing_media':'retained; current dependency and prompt fingerprints will be rechecked'}

    @mutate
    def request_decision(self,proposal):
        proposal=read(Path(proposal)) if not isinstance(proposal,dict) else proposal
        if not proposal.get('question') or proposal.get('kind') not in ('creative','cost','capability'):
            raise ValueError('A concrete creative, cost or capability proposal is required')
        if self.state['active_decision']:raise ValueError('Resolve the pending decision first')
        context=deepcopy(proposal.get('context',{}));updates=[]
        for change in proposal.get('lock_updates',[]):
            record=self.state['artifacts'][change['slot']]
            old=record['locks'][change['index']]
            if old['path']!=change['check']['path']:raise ValueError('A lock revision must address the same field')
            updates.append({**change,'previous':old,'artifact_sha256':record['sha256']})
        context['lock_updates']=updates
        return self.decision('proposal:'+proposal['kind'],proposal['question'],context,['approve','reject'])

    @mutate
    def resume(self,decision):
        decision=read(Path(decision)) if not isinstance(decision,dict) else decision
        state=self.state;request=state['active_decision']
        if not request or decision.get('request_id')!=request['id']:raise ValueError('Unknown or stale decision')
        if not decision.get('evidence'):raise ValueError('A user decision needs its actual message/evidence')
        value=decision['value'];key=request['key']
        if key.startswith('identity:'):
            m=state['media'][request['context']['media_key']]
            if self.approval_token(m)!=request['context']['token']:raise ValueError('Identity decision is stale')
            if value=='approve':state['approvals'][m['key']]={'token':self.approval_token(m),'evidence':decision['evidence']}
            elif value=='revise':
                m['invalidated']=True;state['prompts'].pop(m['key'],None)
            else:raise ValueError('Identity choice must be approve or revise')
        elif key=='image-capability':
            if value=='text-only':self.project['delivery']='text-only';self.write('project.json',self.project)
            elif value=='provide-media':state.setdefault('provided_jobs',[]).append(request['context']['job'])
            else:raise ValueError('Unknown capability choice')
        elif key=='target':
            if not decision.get('target'):raise ValueError('An explicit target is required')
            self.project.update(target=decision['target'],mode=decision.get('mode',self.project['mode']));self.write('project.json',self.project)
        elif key.startswith('proposal:'):
            if value not in ('approve','reject'):raise ValueError('Proposal choice must be approve or reject')
            if value=='reject':state['blocked_decision']={'request':request,'response':decision}
            else:
                for change in request['context']['lock_updates']:
                    record=state['artifacts'][change['slot']]
                    if record['sha256']!=change['artifact_sha256'] or record['locks'][change['index']]!=change['previous']:
                        raise ValueError('Lock revision decision is stale')
                    self.write('history/locks-'+digest(record)+'.json',record)
                    record['locks'][change['index']]=change['check'];record['invalidated']=True
                state['blocked_decision']=None
        else:raise ValueError('Unknown decision kind')
        state['decisions'].append({'request':request,'response':decision});state['active_decision']=None;state['active_task']=None
        state['status']='BLOCKED' if state.get('blocked_decision') else 'RUNNING'
        self.save(state);return self.status()

    @mutate
    def revise(self,kind,*,shot_id=None,action_id=None,node_id=None,track_id=None,scene_id=None,asset_id=None,target=None,mode=None):
        if sum(bool(x) for x in (shot_id,action_id,node_id,track_id))>1:raise ValueError('Choose one shot/action/node/track scope')
        state=self.state
        if target:
            self.project.update(target=target,mode=mode or self.project['mode']);self.write('project.json',self.project)
        elif asset_id:
            if asset_id not in state['media']:raise ValueError('Unknown media asset')
            state['media'][asset_id]['invalidated']=True;state['prompts'].pop(asset_id,None)
        else:
            slot='art:'+scene_id if kind=='art' and scene_id else kind
            if slot not in state['artifacts']:raise ValueError('Unknown artifact to revise')
            state['artifacts'][slot]['invalidated']=True
            ids=[]
            spatial_scope={}
            if node_id or track_id:
                from .v52_spatial_runtime import affected
                native=self.data(slot,state)
                if native.get('timeline',{}).get('schema')!='detail-timeline/1.2':raise ValueError('Spatial revision requires native 1.2')
                spatial_scope=affected(native,node_id=node_id,track_id=track_id);ids=spatial_scope['shot_ids']
            elif action_id:
                native=self.data(slot,state)
                action=next((a for a in native.get('timeline',{}).get('actions',[]) if a['id']==action_id),None)
                if not action:raise ValueError('Unknown temporal action')
                from .v51_detail_runtime import affected_shots
                ids=list(dict.fromkeys(s for sid in action['shot_ids'] for s in affected_shots(native,sid)))
            elif shot_id:
                shots=self.data(slot,state).get('shots',[]);index=next(i for i,s in enumerate(shots) if s['id']==shot_id)
                ids=[s['id'] for s in shots[max(0,index-1):index+2]]
                if self.data(slot,state).get('timeline'):
                    from .v51_detail_runtime import affected_shots
                    ids=list(dict.fromkeys(ids + affected_shots(self.data(slot,state), shot_id)))
            state['revision_scope']={'shot_ids':ids,'scene_ids':[scene_id] if scene_id else [],'action_ids':[action_id] if action_id else [],**spatial_scope}
        state.update(active_task=None,active_decision=None,build=None,blocked_decision=None,status='RUNNING')
        self.save(state);return self.status()

    def build_fingerprint(self):
        return digest({'storyboard':self.state['artifacts']['storyboard']['sha256'],
            'imported_avir':self.state['artifacts'].get('avir',{}).get('sha256') if self.valid('avir') else None,
            'compiled_import':self.state.get('compiled_import',{}).get('manifest_sha256'),
            'mapping':self.state.get('mapping_overrides'),
            'media':{k: v['sha256'] for k,v in self.state['media'].items() if self.media_valid(v)},
            'target':[self.project['target'],self.project['mode'],self.project['delivery']],
            'modules':read(self.root/'modules.lock.json')})

    @mutate
    def compile(self,mapping=None):
        if not self.valid('storyboard'):raise ValueError('Current validated storyboard is required')
        state=self.state;sb=self.data('storyboard')
        source=self.path(state['artifacts']['storyboard']['uri'])
        if mapping is not None:
            mapping=read(Path(mapping)) if not isinstance(mapping,dict) else mapping
            if mapping.get('storyboard_sha256')!=state['artifacts']['storyboard']['sha256']:
                raise ValueError('Mapping review binds a different storyboard')
            self.write('history/mapping-'+digest(mapping)+'.json',mapping)
            state['mapping_overrides']=mapping;state['build']=None;self.save(state)
        mapping=state.get('mapping_overrides')
        if mapping and mapping['storyboard_sha256']!=state['artifacts']['storyboard']['sha256']:
            return {'status':'BLOCKED','reason':'Mapping review is stale; update it for the revised storyboard'}
        avir,report=storyboard_to_avir(sb,source.parent,(mapping or {}).get('mappings'))
        # Compilation adds verified image receipts after the deterministic
        # storyboard adapter. Rebind semantic review only when its source hash
        # was valid before those non-creative receipt additions.
        from .v52_spatial_runtime import content_hash as spatial_content_hash, semantic_status as spatial_semantic_status
        semantic_review_valid=(isinstance(avir.get('timeline'),dict) and 'semantic_review' in avir['timeline'] and spatial_semantic_status(avir))
        pinned_adapter=self.project.get('adapter_version')
        supported={'1.0.0':{'storyboard-ir/1.0'},'1.1.0':{'storyboard-ir/1.0','storyboard-ir/1.1'},ADAPTER_VERSION:{'storyboard-ir/1.0','storyboard-ir/1.1','storyboard-ir/1.2'}}
        if sb.get('schema_version') not in supported.get(pinned_adapter,set()):
            return {'status':'BLOCKED','reason':'Project adapter lock cannot read this native version; explicit module/adapter upgrade is required'}
        if pinned_adapter!=ADAPTER_VERSION:report['adapter']=pinned_adapter
        limits=self.project.get('legacy_constraints',{})
        if 'continuous_shot_seconds' in limits:
            low,high=limits['continuous_shot_seconds']
            for shot in avir['shots']:
                if not low*1000<=shot['end_ms']-shot['start_ms']<=high*1000:
                    report['losses'].append({'severity':'error','path':'/shots/'+shot['id'],'reason':'Explicit migrated V4 duration contract fails'})
                    report['status']='BLOCKED'
        # Actual media is registered separately from original offline receipts.
        for media in state['media'].values():
            if self.project['delivery']=='text-only' or not self.media_valid(media,state):continue
            sid='MEDIA_'+media['key'];asset_id='IMG_'+media['key']
            avir['sources'].append({'id':sid,'kind':'observed','uri':str(self.path(media['uri'])),'locator':'actual image review',
                'claim':'; '.join(media['visual_review']['findings']),'verification':'observed','sha256':media['sha256']})
            duplicate=next((a for a in avir['assets'] if a['sha256']==media['sha256'] and a['kind']=='image'),None)
            if duplicate:asset_id=duplicate['id']
            else:avir['assets'].append({'id':asset_id,'kind':'image','filename':media['filename'],'path':str(self.path(media['uri'])),
                'sha256':media['sha256'],'public_url':None,'inspection':'observed','source_refs':[sid]})
            shot_ids=[s['id'] for s in sb['shots'] if (media['shot_id']==s['id'] if media['shot_id'] else media['entity_id'] in s['state_start'])]
            target=media['entity_id'] or next(s['scene_id'] for s in sb['shots'] if s['id']==media['shot_id'])
            roles=['identity','wardrobe'] if media['role']=='identity' else ['source_content']
            if shot_ids:
                existing=[b for b in avir['bindings'] if b['target_id']==target and set(b['roles'])&{'identity','wardrobe'} and set(b['shot_ids'])&set(shot_ids)] if media['role']=='identity' else []
                if any(b['asset_id']!=asset_id for b in existing):
                    return {'status':'BLOCKED','reason':'Conflicting identity authority','media_key':media['key'],'shot_ids':shot_ids}
                if not existing:
                    avir['bindings'].append({'id':'B_'+media['key'],'asset_id':asset_id,'target_id':target,'shot_ids':shot_ids,
                        'roles':roles,'negative_roles':[],'source_refs':[sid]})
                    if media['stage']==7:
                        binding_index=len(avir['bindings'])-1
                        avir['contract'].append({'id':'BOARD_USE_'+media['key'],'level':'hard',
                            'requirement':f"参考图 {media['filename']} 对应 {media['shot_id']} 的全局第 {media.get('frame')} 帧、{media.get('moment')}。只继承这个瞬间的构图/场景，不把静态画格当成全部动作或角色身份来源。",
                            'source_refs':[sid],'shot_ids':shot_ids,'checks':[{'path':f'/bindings/{binding_index}/asset_id','op':'equals','value':asset_id}],
                            'channel':'prompt','execution':'按指定画格时刻及用途参考，后续动作遵循分镜',
                            'acceptance':{'method':'media','criterion':'画格时刻与动作、身份参考职责没有越界'},'on_unsupported':'block'})
        if semantic_review_valid:
            avir['timeline']['semantic_review']['input_sha256']=spatial_content_hash(avir)
        imported_record=state['artifacts'].get('avir')
        if imported_record and not self.valid('avir'):
            self.data('avir')  # Byte changes are errors, not permission to discard a package.
            if imported_record.get('needs_reconciliation'):
                if self.portable_content(self.data('avir'))!=self.portable_content(avir):
                    return {'status':'BLOCKED','reason':'Independent AVIR needs semantic reconciliation with the now-available storyboard'}
                self.import_artifact('avir',self.path(imported_record['uri']))
                state=self.state
            elif imported_record.get('invalidated'):
                return {'status':'BLOCKED','reason':'Explicit AVIR revision must be submitted before compilation'}
            else:
                self.write('history/retired-avir-'+digest(imported_record)+'.json',imported_record)
                state['artifacts'].pop('avir');self.save(state)
        if self.valid('avir'):
            imported=self.data('avir')
            if self.portable_content(imported)!=self.portable_content(avir):
                return {'status':'BLOCKED','reason':'Imported AVIR does not match the current frozen storyboard and media; re-review its adaptation'}
            avir=imported
        report['target_hash']=digest(avir)
        build_hash=self.build_fingerprint();folder='builds/'+build_hash
        self.write(folder+'/avir.json',avir);self.write(folder+'/mapping.json',report)
        if report['status']=='BLOCKED':return {'status':'BLOCKED','mapping_report':str(self.path(folder+'/mapping.json')),'losses':report['losses']}
        compiler=self.modules('video-prompt-compiler')
        core=load_python(compiler,'vpc_core.py')
        errors=[e for e in core.validate(avir,self.path(folder)) if e['severity']=='error']
        if errors:return {'status':'BLOCKED','diagnostics':errors}
        output=self.path(folder+'/compiled')
        previous=state.get('compiled_import')
        reuse=previous and previous['target']==self.project['target'] and previous['mode']==self.project['mode']
        if reuse:
            imported=self.path(previous['uri'])
            original_ir=read(imported/'avir.json')
            if self.portable_content(original_ir)!=self.portable_content(avir):
                reuse=False  # Changed inputs require a new compilation; historical output remains intact.
            elif any(not self.path(path).is_file() or digest_file(self.path(path))!=checksum for path,checksum in previous['files'].items()):
                raise ValueError('Imported compiled package changed')
            elif not output.exists():
                for file in imported.iterdir():
                    if file.is_file():self.write(folder+'/compiled/'+file.name,file.read_bytes())
        if not output.exists() or not (output/'artifact.json').exists():
            if output.exists() and any(output.iterdir()):
                return {'status':'BLOCKED','reason':'Interrupted compiler output; retain evidence and use revise/recompile with a new input revision'}
            proc=subprocess.run([sys.executable,str(compiler/'scripts/vpc.py'),'compile',str(self.path(folder+'/avir.json')),
                '--target',self.project['target'],'--mode',self.project['mode'],'--out',str(output)],capture_output=True,text=True)
            if proc.returncode:return {'status':'BLOCKED','compiler_output':proc.stdout,'error':proc.stderr}
        artifact=read(output/'artifact.json')
        if artifact['status']=='BLOCKED':return {'status':'BLOCKED','losses':artifact['losses']}
        if limits.get('max_uploaded_references'):
            if len(artifact['asset_bindings'])>limits['max_uploaded_references']:
                return {'status':'BLOCKED','reason':'Explicit migrated V4 reference-count contract fails'}
        attachment_rows=[]
        for row in artifact['asset_bindings']:
            bound=next((a for a in avir['assets'] if a['id']==row['id']),None)
            attachment_rows.append({**row,'path':bound['path'] if bound else row.get('path')})
        self.write(folder+'/attachments.json',{'submitted':False,'attachments':attachment_rows})
        report['target_hash']=digest(avir);report['compiled_package_reused']=bool(reuse)
        self.write(folder+'/mapping.json',report)
        files={str(p.relative_to(self.root)):digest_file(p) for p in self.path(folder).rglob('*') if p.is_file()}
        state['build']={'input_fingerprint':build_hash,'build_id':read(output/'compile-manifest.json')['build_id'],
            'uri':folder,'files':files,'submitted':False,'video_qa':'NOT_RUN'}
        self.save(state);return {'status':'COMPILED','build':state['build']}

    @staticmethod
    def portable_content(value):
        if isinstance(value,list):return [V5Kernel.portable_content(x) for x in value]
        if not isinstance(value,dict):return value
        result={k:V5Kernel.portable_content(v) for k,v in value.items()}
        for field in ('path','uri','file'):
            checksum=value.get('sha256') or value.get('file_sha256')
            if isinstance(result.get(field),str) and checksum:
                result[field]='sha256:'+checksum
        return result

    @mutate
    def import_compiled(self,package):
        package=Path(package).resolve();compiler=self.modules('video-prompt-compiler')
        proc=subprocess.run([sys.executable,str(compiler/'scripts/vpc.py'),'verify',str(package)],capture_output=True,text=True)
        if proc.returncode:raise ValueError('Compiled package validation failed: '+proc.stderr+proc.stdout)
        manifest=read(package/'compile-manifest.json');artifact=read(package/'artifact.json')
        if artifact['status']!='COMPILED':raise ValueError('Only a valid static compilation can be reused')
        for rel,checksum in manifest['runtime_files'].items():
            p=(compiler/rel).resolve()
            if not p.is_relative_to(compiler) or not p.is_file() or digest_file(p)!=checksum:
                raise ValueError('Compiled package module version differs from project lock')
        if not manifest['runtime_files']:raise ValueError('Missing compiler provenance')
        self.import_artifact('avir',package/'avir.json')
        prefix='imports/compiled/'+digest_file(package/'compile-manifest.json')
        files={}
        for filename in [*manifest['files'],'compile-manifest.json']:
            if Path(filename).name!=filename:raise ValueError('Unsafe native manifest path')
            uri=prefix+'/'+filename;self.write(uri,(package/filename).read_bytes());files[uri]=digest_file(package/filename)
        state=self.state
        state['compiled_import']={'uri':prefix,'manifest_sha256':digest_file(package/'compile-manifest.json'),
            'target':manifest['target'],'mode':manifest['mode'],'files':files,'source_build_id':manifest['build_id']}
        state['build']=None;self.save(state)
        return {'status':'IMPORTED_REVIEW_PENDING','kind':'compiled-prompts','receipt_unchanged':True,'native_artifact':'avir'}

    def validate(self,final=False):
        self.require_v5();state=self.state;errors=[]
        validate_protocol('project',self.project,self.skill_root)
        validate_protocol('state',state,self.skill_root)
        for source in state['sources']:
            if not self.path(source['uri']).is_file() or digest_file(self.path(source['uri']))!=source['sha256']:
                errors.append('Source file missing or changed: '+source['id'])
        for name,item in read(self.root/'modules.lock.json')['modules'].items():
            try:verify_module(self.path('runtime/module-archives/'+item['sha256']+'.skill'),name,item)
            except (ValueError,OSError):errors.append('Locked module missing or changed: '+name)
        for key,prompt in state['prompts'].items():
            if not self.prompt_valid(prompt):errors.append('Image prompt missing or changed: '+key)
        for slot,record in state['artifacts'].items():
            if not self.valid(slot,state):errors.append('Missing, changed or stale artifact: '+slot)
        current_keys={j['key'] for stage in (5,7) for j in self.image_jobs(stage)} if self.valid('storyboard') else set(state['media'])
        for media in state['media'].values():
            if self.project['delivery']=='full' and media['key'] in current_keys and not self.media_valid(media,state):
                errors.append('Missing, changed or stale media: '+media['key'])
        if final:
            for observation in self.observation_status():
                if observation['status']=='NEEDS_ACTUAL_OBSERVATION':errors.append('Reference video has no scoped actual observation: '+observation['source_id'])
            for slot in ('canon','screenplay','director','storyboard','qa'):
                if not self.valid(slot,state):errors.append('Required stage not complete: '+slot)
            if self.valid('director'):
                for scene in self.data('director')['scenes']:
                    if not self.valid('art:'+scene['id']):errors.append('Missing art scene: '+scene['id'])
            if self.project['delivery']=='full' and self.valid('storyboard'):
                for job in self.image_jobs(5)+self.image_jobs(7):
                    if job['brief'].get('state_evaluation', {}).get('status') == 'NEEDS_KEY_POSE':
                        errors.append('Panel key pose missing: '+job['key'])
                    media=state['media'].get(job['key'])
                    if not media or not self.media_valid(media,state) or media['input_fingerprint']!=job['fingerprint']:
                        errors.append('Required image not ready: '+job['key'])
                    elif media['role']=='identity' and state['approvals'].get(job['key'],{}).get('token')!=self.approval_token(media):
                        errors.append('Identity not approved: '+job['key'])
            build=state['build']
            if not build or build['input_fingerprint']!=self.build_fingerprint():errors.append('Current compiled build is missing')
            elif any(not self.path(p).is_file() or digest_file(self.path(p))!=h for p,h in build['files'].items()):errors.append('Compiled files were modified')
        return {'valid':not errors,'errors':errors,'delivery':self.project['delivery'],'video_generated':False,'video_qa':'NOT_RUN'}

    @mutate
    def export(self,draft=False):
        report=self.validate(final=True)
        if not report['valid'] and not draft:return {'status':'BLOCKED','validation':report}
        state=self.state
        status='DRAFT' if not report['valid'] else 'DELIVERED'
        index={'schema':'delivery/5.0','project_id':self.project['project_id'],'status':status,
            'scope':self.project['delivery'],'validation':report,'artifacts':state['artifacts'],'media':state['media'],
            'reference_observations':self.observation_status(),'build':state['build'],'modules':read(self.root/'modules.lock.json'),'submitted':False,'video_qa':'NOT_RUN'}
        self.write('delivery/index.json',index)
        lines=[f"# {self.project['project_id']} · {status}",f"交付范围：{self.project['delivery']}。视频未生成，视频验收 NOT_RUN。"]
        if state['build']:lines.append('[视频提示词](../'+state['build']['uri']+'/compiled/prompt.txt) · [附件表](../'+state['build']['uri']+'/attachments.json)')
        for m in state['media'].values():lines.append(f"- {m['key']}：[ {m['filename']} ](../{m['uri']})；SHA-256 {m['sha256']}")
        if report['errors']:lines+=['待解决：']+report['errors']
        self.write('delivery/index.md',('\n\n'.join(lines)+'\n').encode())
        state['status']=status;self.save(state)
        return {'status':status,'index':str(self.path('delivery/index.md')),'validation':report}

    def status(self):
        if self.project.get('schema_version')!='5.0':
            return {'status':'LEGACY_READ_ONLY','project':str(self.root),'schema_version':self.project.get('schema_version'),
                    'instruction':'Use copy-project --destination NEW_DIR to import into V5.'}
        state=self.state
        return {'status':state['status'],'project':str(self.root),'execution_mode':'current-agent',
            'artifacts':{k:('READY' if self.valid(k,state) else 'STALE') for k in state['artifacts']},
            'media':{k:('READY' if self.media_valid(v,state) else 'STALE') for k,v in state['media'].items()},
            'active_task':state['active_task'],'decision':state['active_decision'],'video_generated':False}

    @classmethod
    def copy_project(cls,source,destination,*,skill_root=ROOT):
        source,destination=Path(source).resolve(),Path(destination).resolve()
        if destination==source or destination.is_relative_to(source):raise ValueError('Migration destination must be outside the source project')
        if not source.is_dir():raise ValueError('Legacy project directory does not exist')
        old=read(source/'project.json') if (source/'project.json').exists() else {}
        identifier=old.get('project_id','PROJECT')
        # IDs inside every copied original remain unchanged even if an old project ID
        # is not a supported V5 directory identifier.
        try:safe_id(identifier)
        except ValueError:identifier='PROJECT'
        kernel=cls.initialize(destination,['Legacy project copied from '+str(source)],project_id=identifier,skill_root=skill_root)
        records=[];candidates=[];native=[];identifiers=[];decisions=[]
        for p in sorted(source.rglob('*')):
            rel=p.relative_to(source)
            if any(part in ('.git','.venv','__pycache__') for part in rel.parts):continue
            if p.is_symlink():raise ValueError('Migration requires explicit handling of symlinked files')
            if not p.is_file():continue
            uri='imports/legacy/'+rel.as_posix();kernel.write(uri,p.read_bytes())
            records.append({'original':str(rel),'uri':uri,'sha256':digest_file(p)})
            if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
                candidates.append({'uri':uri,'filename':p.name,'sha256':digest_file(p),'review':'PENDING',
                    'approval':'NOT_IMPORTED','reuse_action':'Inspect these existing bytes and submit as provided media for a matching image task; do not regenerate by default.'})
            if p.suffix.lower()=='.json':
                try:value=read(p)
                except ValueError:continue
                if isinstance(value,dict):
                    schema=value.get('schema_version',value.get('schema'))
                    if schema in ('storyboard-ir/1.0','avir/1.0') or (schema=='1.0' and 'contract' in value):
                        native.append({'uri':uri,'schema':schema,'project_id':value.get('project_id'),'status':'REVALIDATE_NATIVE_AND_HANDOFF'})
                    def scan(obj,pointer=''):
                        if isinstance(obj,dict):
                            for key,item in obj.items():
                                path=pointer+'/'+key.replace('~','~0').replace('/','~1')
                                if key in ('id','entity_id','asset_id','character_id','scene_id','shot_id') and isinstance(item,str):
                                    identifiers.append({'uri':uri,'pointer':path,'id':item})
                                if key in ('approval','approvals','decisions','authorization_ref') and item:
                                    decisions.append({'uri':uri,'pointer':path,'status':'ORIGINAL_EVIDENCE_ONLY'})
                                scan(item,path)
                        elif isinstance(obj,list):
                            for i,item in enumerate(obj):scan(item,pointer+'/'+str(i))
                    scan(value)
        if old.get('schema_version')=='4.0' or old.get('workflow_id')=='ai-comic-drama-v4':
            kernel.project['legacy_constraints']={'continuous_shot_seconds':[1,12],'max_uploaded_references':5,
                'segment_target_s':old.get('segment_target_s'),'source':'imports/legacy/project.json'}
        kernel.write('project.json',kernel.project)
        report={'schema':'migration/5.0','source':str(source),'source_schema':old.get('schema_version','vsp-yaml'),
            'files':records,'media_candidates':candidates,'native_candidates':native,'identifier_evidence':identifiers,
            'decision_evidence':decisions,'original_project_id':old.get('project_id'),
            'approval_reuse':'requires unchanged bytes, identity, scope and actual original decision evidence',
            'unknown_fields':'preserved in immutable originals','status':'COPIED_REVIEW_REQUIRED'}
        kernel.write('imports/migration.json',report)
        state=kernel.state
        for record in records:
            if Path(record['original']).suffix.lower() in ('.json','.yaml','.yml','.md','.txt'):
                state['sources'].append({'id':'LEGACY_'+record['sha256'][:12], 'uri':record['uri'],
                    'sha256':record['sha256'],'original':str(source/record['original'])})
        # Deduplicate equal files while retaining every copied original in the migration report.
        state['sources']=list({s['id']:s for s in state['sources']}.values());kernel.save(state)
        return kernel
