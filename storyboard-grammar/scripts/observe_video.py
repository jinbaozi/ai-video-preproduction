#!/usr/bin/env python3
"""Extract real timestamped frames. Extraction is never a visual or audio review."""
import argparse
from bisect import bisect_left
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import subprocess

VERSION='1.1.0'
def encoded(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def filehash(p):return sha256(Path(p).read_bytes()).hexdigest()
def run(args):return subprocess.run(args,check=True,capture_output=True,text=True).stdout

def extract(source,out,start,end,step=0.5):
 source=Path(source).resolve();out=Path(out).resolve()
 if not 0<=start<end or step<=0:raise ValueError('Require 0 <= start < end, step > 0')
 if out.exists() and any(out.iterdir()):raise ValueError('Use a new observation version directory')
 probe=json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(source)]))
 frames=json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(source)]))['frames']
 timestamps=[float(x['best_effort_timestamp_time']) for x in frames]
 if not timestamps or end>float(probe['format']['duration'])+0.001:raise ValueError('Requested range exceeds media')
 out.mkdir(parents=True,exist_ok=True);selected=[];t=Fraction(str(start));limit=Fraction(str(end));increment=Fraction(str(step))
 while t<limit:
  i=min(bisect_left(timestamps,float(t)),len(timestamps)-1)
  if timestamps[i]<end and i not in selected:selected.append(i)
  t+=increment
 records=[]
 for i in selected:
  name=f'frame-{i:08d}.png';dest=out/name
  run(['ffmpeg','-v','error','-i',str(source),'-vf',fr'select=eq(n\,{i})','-frames:v','1','-vsync','0',str(dest)])
  records.append({'id':'FRAME_'+str(i),'frame_index':i,'pts_seconds':timestamps[i],'file':name,'sha256':filehash(dest)})
 report={'schema':'video-observation/1.1','extractor_version':VERSION,'source':str(source),'source_sha256':filehash(source),
  'range_seconds':[start,end],'step_seconds':step,'probe':probe,'frames':records,'status':'EXTRACTED',
  'visual_review':'NOT_RUN','audio_review':'NOT_RUN','unobserved':'All extracted frames remain unreviewed until an explicit review is recorded.'}
 (out/'observation.json').write_bytes(encoded(report));return report

def record_review(bundle,review):
 bundle=Path(bundle);m=json.loads((bundle/'observation.json').read_text());r=json.loads(Path(review).read_text())
 if r.get('source_sha256')!=m['source_sha256'] or filehash(m['source'])!=m['source_sha256']:raise ValueError('Review source mismatch')
 frames={f['id']:f for f in m['frames']}
 if not r.get('reviewer') or not r.get('findings') or not r.get('viewed_frame_ids'):raise ValueError('Require reviewer, findings and viewed frame IDs')
 for id in r['viewed_frame_ids']:
  if id not in frames or filehash(bundle/frames[id]['file'])!=frames[id]['sha256']:raise ValueError('Unknown or changed viewed frame')
 if not set(r.get('audio_review',{})) >= {'status','method'}:raise ValueError('Explicit audio review status and method required')
 if r['audio_review']['status'] not in ('NOT_RUN','PARTIAL','PASS','FAIL'):raise ValueError('Invalid audio review')
 for finding in r['findings']:
  if not finding.get('observation') or not finding.get('frame_ids') or not set(finding['frame_ids'])<=set(r['viewed_frame_ids']):raise ValueError('Observation requires viewed frame evidence')
 r['schema']='video-review/1.1';r['unreviewed_frame_ids']=sorted(set(frames)-set(r['viewed_frame_ids']))
 r['visual_review']='PARTIAL' if r['unreviewed_frame_ids'] else 'SAMPLED_FRAMES_REVIEWED'
 r['complete_motion_coverage']=False
 (bundle/'review.json').write_bytes(encoded(r));return r

def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 q=sub.add_parser('extract');q.add_argument('source');q.add_argument('--out',required=True);q.add_argument('--start',type=float,required=True);q.add_argument('--end',type=float,required=True);q.add_argument('--step',type=float,default=.5)
 q=sub.add_parser('review');q.add_argument('bundle');q.add_argument('--record',required=True)
 a=p.parse_args()
 try:
  r=extract(a.source,a.out,a.start,a.end,a.step) if a.command=='extract' else record_review(a.bundle,a.record)
  print(json.dumps({'status':r.get('status',r.get('visual_review')),'frames':len(r.get('frames',r.get('viewed_frame_ids',[]))),'audio_review':r['audio_review']},ensure_ascii=False));return 0
 except (OSError,ValueError,subprocess.CalledProcessError) as e:p.exit(2,str(e)+'\n')
if __name__=='__main__':raise SystemExit(main())
