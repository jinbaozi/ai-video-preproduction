"""Source-bound rehearsal cues, material swatches, lighting handoff and grading LUTs."""
from pathlib import Path
from html import escape
import json
import shutil
import subprocess
from .common import read, write, sha, digest, pointer, schema_check, confined
from .package import verify_package


def validate_look(ir, look):
    schema_check(look, 'look-design')
    shots = {s['id'] for s in ir['shots']}; entities = {e['id']:i for i,e in enumerate(ir['entities'])}
    ids = set(); graded = set()
    for swatch in look['material_palette']:
        if swatch['id'] in ids: raise ValueError('Duplicate swatch ID')
        ids.add(swatch['id'])
        if swatch['entity_id'] not in entities or not set(swatch['shot_ids']) <= shots: raise ValueError('Unknown swatch entity or shot')
        prefix = '/entities/'+str(entities[swatch['entity_id']])
        if not set(swatch['source_pointers']) <= {prefix+'/appearance',prefix+'/locks'}:
            raise ValueError('Material swatch must bind original appearance or locks')
    for grade in look['grading_plan']:
        if grade['shot_id'] not in shots or grade['shot_id'] in graded: raise ValueError('Unknown or duplicate grading shot')
        graded.add(grade['shot_id'])
    for row in look['material_palette']+look['grading_plan']:
        for path in row['source_pointers']: pointer(ir,path)


def look_for_shot(config, shot_id):
    look = config.get('look_design')
    if look is None: return None
    return {**look,'material_palette':[s for s in look['material_palette'] if shot_id in s['shot_ids']],
            'grading_plan':[g for g in look['grading_plan'] if g['shot_id']==shot_id]}


def performance_cues(ir):
    nodes = {n['id']:n for n in ir['timeline']['spatial_nodes']}
    def entity(nid):
        seen=set()
        while nid:
            if nid in seen:raise ValueError('Cyclic performance node hierarchy')
            seen.add(nid);node=nodes[nid]
            if node['entity_id']:return node['entity_id']
            nid=node['parent_id']
        return None
    shots = {s['id']:s for s in ir['shots']}; cues = []
    rank = {'body':1,'face':2,'detail':3}
    for index, performance in enumerate(ir['timeline']['performances']):
        for sid in performance['shot_ids']:
            start = max(performance['start_ms'],shots[sid]['start_ms'])
            end = min(performance['end_ms'],shots[sid]['end_ms'])
            if start >= end: continue
            compositions = [c for c in ir['timeline']['composition_tracks'] if sid in c['shot_ids'] and c['start_ms']<end and c['end_ms']>start]
            edges = sorted({start,end}|{max(start,c['start_ms']) for c in compositions}|{min(end,c['end_ms']) for c in compositions})
            intervals = []
            for a,b in zip(edges,edges[1:]):
                subjects = [s for c in compositions if c['start_ms']<=a and b<=c['end_ms'] for s in c['subjects']
                            if entity(s['node_id'])==performance['actor_id']]
                visible = [s for s in subjects if s['presence']!='outside']
                ok = any(set(performance['needed_parts'])<=set(s['visible_parts']) and rank.get(s['readability'],0)>=rank[performance['readability']] for s in visible)
                intervals.append({'start_ms':a,'end_ms':b,'status':'PLANNED_VISIBLE' if ok else 'BLOCKED',
                                  'composition':subjects,'observed_visibility':'NOT_RUN'})
            cues.append({'id':performance['id']+'_'+sid,'shot_id':sid,'start_ms':start,'end_ms':end,
                'source_pointer':f'/timeline/performances/{index}','source_sha256':digest(performance),
                'performance':performance,'visibility':intervals,
                'audio_context':[{'source_pointer':f'/timeline/audio_events/{i}','event':e}
                    for i,e in enumerate(ir['timeline']['audio_events']) if sid in e['shot_ids'] and e['start_ms']<end and e['end_ms']>start],
                'status':'BLOCKED' if any(i['status']=='BLOCKED' for i in intervals) else 'REHEARSAL_REQUEST',
                'owner':'director-grammar','media_generated':False,
                'acceptance':['核对触发、反应、手别、视线和收束，保持来源时点', '实际表演参考必须检查身份/造型与镜头可读性',
                              '不把心理活动或内部强度参数当作厂商控制字段']})
    return cues


def transform(rgb, grade):
    # BT.709 signal -> linear-light Rec.709 -> authored adjustment -> BT.709 signal.
    def decode(x): return x/4.5 if x < .081 else ((x+.099)/1.099)**(1/.45)
    def encode(x): return 4.5*x if x < .018 else 1.099*x**.45-.099
    linear = [(decode(x)*2**grade['exposure_stops']-.18)*grade['contrast']+.18 for x in rgb]
    luma = sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
    linear = [luma+(v-luma)*grade['saturation'] for v in linear]
    return [encode(min(1,max(0,v))) for v in linear]


def cube(grade, size=33):
    rows = ['TITLE "AVIR authored Rec709 grading"',f'LUT_3D_SIZE {size}','DOMAIN_MIN 0 0 0','DOMAIN_MAX 1 1 1']
    for b in range(size):
        for g in range(size):
            for r in range(size):
                rows.append(' '.join(f'{v:.9f}' for v in transform([r/(size-1),g/(size-1),b/(size-1)],grade)))
    return '\n'.join(rows)+'\n'


def derive(bundle):
    ir,config = bundle['ir'],bundle['config']; look = config.get('look_design',{'material_palette':[],'grading_plan':[]})
    cues = performance_cues(ir)
    materials = [{**s,'source_values':{p:pointer(ir,p) for p in s['source_pointers']},'pixel_match_guaranteed':False} for s in look['material_palette']]
    lighting = []
    for shot in ir['shots']:
        scene_index = next(i for i,s in enumerate(ir['scenes']) if s['id']==shot['scene_id'])
        lighting.append({'shot_id':shot['id'],'scene_id':shot['scene_id'],'source_pointer':f'/scenes/{scene_index}/lighting',
            'source_intent':ir['scenes'][scene_index]['lighting'],
            'dynamic_tracks':[t for t in ir['timeline']['motion_tracks'] if shot['id'] in t['shot_ids'] and t['property'] in ('light','color','material','atmosphere')],
            'owner':'production-design-grammar','numeric_light_rig':'NOT_INFERRED','rendered_reference':'NOT_RUN'})
    grading = [{**g,'source_values':{p:pointer(ir,p) for p in g['source_pointers']},
                'input_encoding':'BT709_NONLINEAR_RGB_FULL_AFTER_LIMITED_YUV_DECODE',
                'working_space':'LINEAR_REC709','output_encoding':'BT709_NONLINEAR_RGB_TO_LIMITED_YUV',
                'out_of_gamut':'CLIP_0_1','lut_size':33,'interpolation':'tetrahedral','applied':False} for g in look['grading_plan']]
    return {'schema':'control-craft/0.1','source':bundle['plan']['source'],'performance_cues':cues,
            'material_palette':materials,'lighting_plan':lighting,'grading_plan':grading,
            'media_generation':'NOT_RUN','media_quality':'NOT_RUN'}


def files_for(data):
    encode = lambda value: json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'
    files = {'craft.json':encode(data),'performance-cues.json':encode(data['performance_cues']),
             'material-palette.json':encode(data['material_palette']),'lighting-plan.json':encode(data['lighting_plan']),
             'grading-plan.json':encode(data['grading_plan'])}
    cards = ['# 表演排练交接','', '仅派生已有 AVIR 节拍；实际演员/动画参考制作与审核尚未执行。','']
    for cue in data['performance_cues']:
        p=cue['performance'];cards += [f"## {cue['id']} · {p['actor_id']} · {cue['start_ms']}–{cue['end_ms']} ms",'',
            f"状态：{cue['status']}；来源：{cue['source_pointer']}",f"触发：{p['trigger']}",f"行为：{p['behavior']}"]
        for name in ('body','eyes','face','hands','breathing','voice'):
            cards.append(f"{name}：{p[name]['status']} · {p[name]['text']}")
        cards += [f"反馈：{p['feedback']}",f"收束：{p['settle']}",f"可见部位：{', '.join(p['needed_parts'])}；可读程度：{p['readability']}",'']
        if p['psychology']:
            cards.append('心理与可见转译（保持原可听性）：'+encode(p['psychology']).strip())
        for context in cue['audio_context']:
            audio=context['event']; line=f"{audio['speaker_id']}：“{audio['text']}”" if audio['kind']=='dialogue' else audio['text']
            cards.append(f"声音 {audio['start_ms']}–{audio['end_ms']} ms · {audio['kind']} · {audio['route']} · {audio['placement']} · lip_sync={audio['lip_sync']}：{line}；{audio['delivery']}")
        cards.append('')
    files['rehearsal.md']='\n'.join(cards)+'\n'
    swatches=data['material_palette']; height=100+90*len(swatches)
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}">',
         '<rect width="100%" height="100%" fill="#f5f2eb"/><g font-family="sans-serif" fill="#202631">',
         '<text x="24" y="35" font-size="22">材质色板 · 设计色样，不是最终像素保证</text>']
    for i,s in enumerate(swatches):
        y=65+i*90; label=escape(f"{s['id']} · {s['entity_id']} · {s['color_srgb']} · {' / '.join(s['shot_ids'])}")
        svg += [f'<rect x="24" y="{y}" width="140" height="64" rx="8" fill="{s["color_srgb"]}"/>',
                f'<text x="188" y="{y+26}" font-size="18">{label}</text>',
                f'<text x="188" y="{y+52}" font-size="13">{escape(s["evidence"])}</text>']
    files['color-script.svg']=''.join(svg)+ '</g></svg>\n'
    for index,grade in enumerate(data['grading_plan']): files[f'grades/grade-{index:03d}.cube']=cube(grade)
    return files


def export(package,out):
    bundle=verify_package(package);data=derive(bundle);out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Output directory must be empty')
    out.mkdir(parents=True,exist_ok=True)
    files=files_for(data)
    for name,content in files.items():
        path=out/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
    write(out/'craft-manifest.json',{'schema':'control-craft-manifest/0.1','source_package':str(Path(package).resolve()),
        'source_package_sha256':sha(Path(package)/'package-manifest.json'),
        'files':{name:sha(out/name) for name in files}})
    return {'status':'CRAFT_ASSETS_DERIVED','out':str(out),'performance_requests':len(data['performance_cues']),
            'blocked_performances':[c['id'] for c in data['performance_cues'] if c['status']=='BLOCKED'],
            'grading_luts':len(data['grading_plan']),'media_quality':'NOT_RUN'}


def verify(out):
    out=Path(out).resolve();manifest=read(out/'craft-manifest.json')
    if manifest.get('schema')!='control-craft-manifest/0.1':raise ValueError('Invalid craft manifest')
    package=Path(manifest['source_package']);bundle=verify_package(package)
    if sha(package/'package-manifest.json')!=manifest['source_package_sha256']:raise ValueError('Craft source changed')
    data=derive(bundle);expected=files_for(data)
    if set(manifest['files'])!=set(expected):raise ValueError('Incomplete craft file set')
    for name,content in expected.items():
        path=confined(out,name)
        if sha(path)!=manifest['files'][name] or path.read_text(encoding='utf-8')!=content:raise ValueError('Craft derivation mismatch: '+name)
    return data,bundle


def video_color(path):
    result=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
        'stream=color_space,color_transfer,color_primaries,color_range,pix_fmt','-of','json',str(path)],capture_output=True,text=True,timeout=30)
    if result.returncode:raise ValueError('Cannot inspect video color encoding')
    streams=json.loads(result.stdout)['streams']
    if len(streams)!=1:raise ValueError('Expected one selected video stream')
    return streams[0]


def grade_video(craft,shot_id,media,out):
    from .media_probe import probe
    data,bundle=verify(craft); grades=data['grading_plan']
    index=next((i for i,g in enumerate(grades) if g['shot_id']==shot_id),None)
    if index is None:raise ValueError('No authored grade for this shot')
    shot=next(s for s in bundle['ir']['shots'] if s['id']==shot_id)
    media=Path(media).resolve(); info=probe(media); color=video_color(media)
    if info['detected_kind']!='video' or info['duration_ms']!=shot['end_ms']-shot['start_ms'] or info['rotation_deg']!=0 or info['sample_aspect_ratio'] not in ('1:1',None):
        raise ValueError('Grade requires an unrotated, square-pixel shot clip with exact source duration')
    expected={'color_space':'bt709','color_transfer':'bt709','color_primaries':'bt709','color_range':'tv'}
    if any(color.get(k)!=v for k,v in expected.items()) or color.get('pix_fmt') not in ('yuv420p','yuv422p','yuv444p'):
        raise ValueError('Explicit 8-bit limited-range BT709 input required; do not relabel unknown or HDR media')
    out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Output directory must be empty')
    out.mkdir(parents=True,exist_ok=True);shutil.copyfile(Path(craft)/f'grades/grade-{index:03d}.cube',out/'grading.cube')
    # Fixed relative LUT path avoids shell/filter path interpolation. Explicit matrix/range both ways.
    filters='scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=gbrp16le,lut3d=file=grading.cube:interp=tetrahedral,scale=out_color_matrix=bt709:in_range=pc:out_range=tv,format=yuv420p'
    cmd=['ffmpeg','-v','error','-noautorotate','-i',str(media),'-map','0:v:0','-map','0:a?',
         '-vf',filters,'-fps_mode','passthrough','-c:v','libx264','-crf','12','-c:a','copy',
         '-x264-params','colorprim=bt709:transfer=bt709:colormatrix=bt709',
         '-colorspace','bt709','-color_trc','bt709','-color_primaries','bt709','-color_range','tv',str(out/'graded.mp4')]
    result=subprocess.run(cmd,cwd=out,capture_output=True,text=True,timeout=300)
    if result.returncode:raise ValueError('Grading failed: '+result.stderr[:1000])
    observed=probe(out/'graded.mp4');output_color=video_color(out/'graded.mp4')
    if any(observed[k]!=info[k] for k in ('width','height','fps','duration_ms','audio')) or any(output_color.get(k)!=v for k,v in expected.items()):
        raise ValueError('Grading changed timeline, geometry, audio presence or color encoding')
    receipt={'schema':'control-grading-receipt/0.1','status':'GRADED_LOCAL','shot_id':shot_id,'craft_package':str(Path(craft).resolve()),
        'craft_manifest_sha256':sha(Path(craft)/'craft-manifest.json'),'source_media':info,'source_color':color,
        'grade':grades[index],'lut_sha256':sha(out/'grading.cube'),'filter':filters,'output_media':observed,
        'output_color':output_color,'quality_review':'NOT_RUN','model_execution':'NOT_RUN'}
    write(out/'grading-receipt.json',receipt)
    return {'status':'GRADED_LOCAL','out':str(out),'media_sha256':observed['sha256'],'quality_review':'NOT_RUN'}


def verify_grade(out):
    from .media_probe import probe
    out=Path(out).resolve();receipt=read(out/'grading-receipt.json')
    if receipt.get('schema')!='control-grading-receipt/0.1':raise ValueError('Invalid grading receipt')
    craft=Path(receipt['craft_package']);data,_=verify(craft)
    grade=next((g for g in data['grading_plan'] if g['shot_id']==receipt['shot_id']),None)
    if grade!=receipt['grade'] or sha(craft/'craft-manifest.json')!=receipt['craft_manifest_sha256']:
        raise ValueError('Stale grading source')
    if (out/'grading.cube').read_text()!=cube(grade) or sha(out/'grading.cube')!=receipt['lut_sha256']:
        raise ValueError('Grading LUT changed')
    for path,expected,color in [(receipt['source_media']['path'],receipt['source_media'],receipt['source_color']),
                                (out/'graded.mp4',receipt['output_media'],receipt['output_color'])]:
        actual=probe(path)
        if any(actual[k]!=expected[k] for k in ('sha256','width','height','fps','duration_ms','audio','rotation_deg','sample_aspect_ratio')) or video_color(path)!=color:
            raise ValueError('Grading media changed')
    return {'status':'VERIFIED_LOCAL_GRADE','quality_review':'NOT_RUN','model_execution':'NOT_RUN'}
