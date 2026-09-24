"""Replay the retained cafe image experiment; no model call and no invented approval.

Requires the local outputs/host-keyframe-cafe-r2 media (not shipped in Git).
Runs the image Skill's standalone host-receive implementation. These are historical
outputs, so each host assertion is explicitly retrospective, never a new execution.
"""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'image-prompt-optimizer/scripts'))
from shot_control.common import read, write, sha
from shot_control.control_plan import build
from shot_control.keyframe_host import stage, receive, verify_received


def replay(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists(): raise ValueError('Use a new output directory')
    history = read(source/'host-receipts.json')
    for name, key in [('source.avir.json','source_sha256'),('K001_0.request.json','request_sha256'),
                      ('K001_0.edit.request.json','edit_request_sha256')]:
        if sha(source/name) != history[key]: raise ValueError('Historical source or request changed: '+name)
    for name, metadata in history['files'].items():
        if sha(source/name) != metadata['sha256']: raise ValueError('Historical media changed: '+name)
    for call in history['calls']:
        if sha(source/call['prompt_file']) != call['prompt_sha256']: raise ValueError('Historical prompt changed')
    out.mkdir(parents=True)
    for name in ['source.avir.json','control-config.json','cafe.source.txt','masters.json','A-identity.png','B-identity.png','CAFE-scene.png']:
        shutil.copyfile(source/name,out/name)
    build(out/'source.avir.json',out/'package',read(out/'control-config.json'))
    request = next(r for r in read(out/'package/keyframe-requests.json') if r['id']=='K001_0')
    request.update(master_anchors=['ID_A','ID_B','SCENE'],generation_mode='generate')
    entries = []
    for index, call in enumerate(history['calls'],1):
        if index==2:
            old = read(source/'K001_0.edit.request.json')
            request.update({k:old[k] for k in ['generation_mode','base_asset_id','edit_delta']})
        historical_request = read(source/('K001_0.request.json' if index==1 else 'K001_0.edit.request.json'))
        if request != historical_request: raise ValueError('Current derived request differs from the historical call')
        request_path=out/f'request-{index}.json';write(request_path,request)
        anchors = out/'masters.json' if index==1 else out/'received-1/artifact-manifest.json'
        staged = out/f'stage-{index}'
        stage(out/'package',request_path,anchors,source/call['prompt_file'],'K001_0',staged)
        frozen=read(staged/'stage.json')
        # Compare to the actual recorded order, not just the new stage's proposal.
        actual_input_hashes=[sha(source/name) for name in call['input_order']]
        if actual_input_hashes != [i['sha256'] for i in frozen['inputs']]: raise ValueError('Historical input order differs')
        host={'schema':'keyframe-host-result/0.1','stage_sha256':sha(staged/'stage-manifest.json'),
              'prompt_sha256':call['prompt_sha256'],'input_sha256':actual_input_hashes,
              'output_filename':call['output'],'output_sha256':sha(source/call['output']),
              'host':'built-in image_gen','model':None,'execution_id':None,'recording_mode':'retrospective',
              'evidence':'Replay of retained native tool output and host-receipts.json; no new generation. Original tool did not expose model/execution ID. Prior record SHA256: '+sha(source/'host-receipts.json')}
        host_path=out/f'host-{index}.json';write(host_path,host)
        criteria=list(dict.fromkeys(request['acceptance']+(request.get('edit_delta') or {}).get('acceptance',[])))
        checks=[]
        for i, criterion in enumerate(criteria):
            result, evidence = 'UNDETERMINED','Retained master review exists, but no fresh exhaustive identity, pose or camera measurement was performed in this replay.'
            if i==1:
                result='FAIL'
                evidence=('Actual image viewed again: envelope paper plane is upright, contradicting the frozen horizontal pose.' if index==1 else
                          'Actual image viewed again: horizontal envelope is near normalized (0.498,0.498), but frozen center is (0.440,0.643). Manual estimate, not tracker output; feet and exact camera geometry unverified.')
            elif i==2:
                result='PASS'; evidence='Actual image viewed again: no arrows, IDs, timecode or review panels visible.'
            elif index==2 and i==3:
                evidence='Envelope now appears horizontal with right-hand support, but the requested 15 cm height has no calibrated measurement.'
            checks.append({'criterion':criterion,'result':result,'evidence':evidence})
        review={'schema':'keyframe-image-review/0.1','stage_sha256':host['stage_sha256'],'sha256':host['output_sha256'],
                'reviewer':'Codex actual image inspection, with conservative unresolved checks','checks':checks}
        review_path=out/f'review-{index}.json';write(review_path,review)
        received=out/f'received-{index}'
        receive(staged,source/call['output'],host_path,received,review_path)
        status=verify_received(received)
        entries.append({'attempt':index,'output_sha256':host['output_sha256'],'prompt_sha256':host['prompt_sha256'],
                        'input_sha256':actual_input_hashes,'receipt_sha256':sha(received/'receipt.json'),
                        'verification':status,'recording_mode':'retrospective'})
    summary={'schema':'host-keyframe-replay-evidence/0.1','implementation':'image-prompt-optimizer standalone shared runtime',
             'historical_record_sha256':sha(source/'host-receipts.json'),'new_model_calls':0,'submitted':False,'attempts':entries}
    write(out/'summary.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();print(replay(args.input,args.out))
