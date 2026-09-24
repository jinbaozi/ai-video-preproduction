#!/usr/bin/env python3
"""Adversarial tests on byte-identical target modules and complete native build packages.
No monkeypatching, validator replacement, model/API calls or remote writes.
Synthetic media and review records exercise code contracts only, not visual quality.
"""
import copy,json,math,struct,zlib,wave,subprocess,sys,shutil,time,re
from pathlib import Path
from native_fixture import ROOT,fixture,config,control,make
from shot_control.common import read,write,sha,digest
from shot_control.package import verify_package,validate_source,recipe
from shot_control.control_lowering import lower
from shot_control.keyframes import check_request
from shot_control.media_review import evaluate
from shot_control.media_probe import probe
from shot_control.render_blocking import export_review

OUT=ROOT/'evidence/round2';OUT.mkdir(parents=True,exist_ok=True)
ASSETS=OUT/'synthetic-media';ASSETS.mkdir(exist_ok=True)
RESULTS=[]

def png(path,variant=0):
    width,height=512,288
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    rgb=bytes([(40+variant*31)%256,(80+variant*17)%256,(120+variant*43)%256])
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+rgb*width)*height))+chunk(b'IEND',b'')
    path.write_bytes(data)

def wav(path,freq=440,seconds=1):
    sr=8000
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr)
        w.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(2*math.pi*freq*i/sr))) for i in range(int(sr*seconds))))

def video(path,seconds=8,size='320x180'):
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'testsrc2=size={size}:rate=25','-t',str(seconds),'-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-movflags','+faststart','-y',str(path)],check=True,timeout=30)

for i in range(10):png(ASSETS/f'p{i}.png',i)
wav(ASSETS/'a1.wav',440);wav(ASSETS/'a2.wav',550);wav(ASSETS/'a3.wav',660)
video(ASSETS/'full.mp4',8);video(ASSETS/'clay.mp4',4)
video(ASSETS/'portrait.mp4',8,'180x320');video(ASSETS/'short.mp4',4)
(ASSETS/'not-video.txt').write_text('This is not a video.')


def fresh(name,controls=None,ir=None,cfg=None):
    case=OUT/name
    if case.exists():shutil.rmtree(case)
    case.mkdir()
    package,result=make(case,ir=ir,cfg=cfg if cfg is not None else config(controls if controls is not None else [control()]))
    bundle=verify_package(package)
    write(case/'precondition.json',{'native_build_result':result,'package_verified':True,'full_native':True})
    return case,package,bundle


def asset(bundle,c,aid,role='identity',media='p0.png',kind='image',url=None,uses=None):
    source=ASSETS/media
    if uses is None:
        uses=[]
        for sid in c['shot_ids']:
            s=next(s for s in bundle['ir']['shots'] if s['id']==sid)
            a,b=s['start_ms'],s['end_ms']
            if c['channel']=='first_frame':b=a
            if c['channel']=='last_frame':a=b
            uses.append({'control_id':c['id'],'shot_id':sid,'start_ms':a,'end_ms':b,
                         'recipe_sha256':recipe(bundle['ir'],bundle['config'],c,sid,role,a,b)})
    h=sha(source)
    return {'id':aid,'path':'../synthetic-media/'+media,'sha256':h,'source_sha256':bundle['plan']['source']['sha256'],
            'kind':kind,'role':role,'uses':uses,
            'review':{'sha256':h,'reviewer':'audit synthetic fixture; not actual model-media review',
                      'result':'PASS','checks':['Synthetic positive structural fixture only'],'uses_sha256':digest(uses)},
            'binding':{'sha256':h,'url':url or ('https://example.com/'+media),'receipt':'synthetic upload record, not a network receipt'}}

# External manifests are kept beside each case, and confined paths cannot use ../.
# Copy actual assets under that case rather than bypassing confinement.
def manifest(case,assets):
    values=copy.deepcopy(assets)
    for a in values:
        name=Path(a['path']).name
        target=case/'assets'/name;target.parent.mkdir(exist_ok=True)
        shutil.copyfile(ASSETS/name,target)
        a['path']='assets/'+name
    p=case/'artifacts.json';write(p,{'schema':'control-artifacts/0.2','artifacts':values,'submitted':False})
    return p


def bind(case,package,assets,mode='reference',target='agnes-video-2.5'):
    result=lower(package,target,mode,manifest(case,assets));write(case/'lowering.json',result);return result


def outcome(fn):
    try:
        r=fn()
        return {'accepted':not (isinstance(r,dict) and r.get('status')=='BLOCKED'),'result':json.loads(json.dumps(r,default=str))}
    except Exception as e:
        return {'accepted':False,'exception':type(e).__name__,'message':str(e)}


def note(name,category,expected,actual,ok):
    row={'id':name,'category':category,'expected':expected,'assertion_passed':bool(ok),'actual':actual}
    RESULTS.append(row);write(OUT/'results.json',RESULTS)
    print(('PASS' if ok else 'REPRODUCED_DEFECT'),name,flush=True)
    return row


def assert_case(name,category,fn,expected_accept=True):
    actual=outcome(fn)
    note(name,category,expected_accept,actual,actual['accepted']==expected_accept)
    return actual


def review_for(bundle,media='full.mp4'):
    baseline=bundle['evaluation']
    return {'schema':'control-media-review/0.2','media_sha256':sha(ASSETS/media),'reviewer':'synthetic numeric observations; not actual visual QA',
       'evaluation_plan_sha256':digest(baseline),'observed_points':[{'shot_id':p['shot_id'],'node_id':p['node_id'],'at_ms':p['at_ms'],'xy':p['xy'],'visibility':'visible'}
         for p in baseline['points'] if p['status']=='IN_FRAME'],
       'events':[{'id':e['id'],'observed_ms':e['planned_ms']} for e in baseline['events']],'findings':[]}


def reseal(package,name):
    m=read(package/'package-manifest.json');m['files'][name]=sha(package/name);write(package/'package-manifest.json',m)

