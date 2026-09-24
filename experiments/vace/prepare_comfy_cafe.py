#!/usr/bin/env python3
"""Prepare the fixed cafe experiment from verified Blender pixels; never submit a job."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'video-prompt-compiler/scripts'))
from shot_control.common import read, write, sha
from shot_control.media_probe import probe
from shot_control.previs import verify_render


def prepare(render, out):
    render, out = Path(render).resolve(), Path(out).resolve()
    if out.exists(): raise ValueError('Use a new experiment input directory')
    verify_render(render)
    plan = read(render/'render-plan.json')
    if (plan['shot_id'], plan['start_ms'], plan['end_ms'], plan['fps'], plan['geometry']['resolution']) != ('S1', 0, 4000, 16, [512, 288]):
        raise ValueError('This experiment requires S1, 0..4000 ms, 16 fps, 512x288')
    indices = plan['video_samples'] + [next(i for i,s in enumerate(plan['samples']) if s['at_ms'] == 4000)]
    if [plan['samples'][i]['at_ms'] for i in indices] != [i*62.5 for i in range(65)]:
        raise ValueError('Control samples must preserve the exact native time map')
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.vace-input-', dir=out.parent) as tmp:
        root = Path(tmp); frames = root/'frames'; frames.mkdir()
        mapping = []
        for j,i in enumerate(indices):
            source = render/f'frames/{i:06d}.png'
            shutil.copyfile(source, frames/f'{j:06d}.png')
            mapping.append({'index':j, 'source_at_ms':plan['samples'][i]['at_ms'], 'source_png_sha256':sha(source)})
        media = root/'cafe-control-65.mp4'
        subprocess.run(['ffmpeg','-v','error','-framerate','16','-i',str(frames/'%06d.png'),
                        '-c:v','libx264rgb','-crf','0','-pix_fmt','rgb24',str(media)], check=True)
        info = probe(media)
        if (info['width'],info['height'],info['fps']) != (512,288,16):
            raise ValueError('Encoded control dimensions or rate changed')
        write(root/'input-receipt.json', {'schema':'vace-comfy-input/0.1',
            'source_render_manifest_sha256':sha(render/'render-manifest.json'),
            'source_package_sha256':read(render/'render-receipt.json')['source_package_sha256'],
            'control_sha256':sha(media), 'control_map':mapping, 'codec':'Lossless RGB H.264',
            'raw_duration_ms':4062.5, 'delivery_duration_ms':4000,
            'delivery_rule':'Keep output frames 0..63 at 16 fps; remove guard frame 64 only, without retiming',
            'submitted':False, 'model_execution':'NOT_RUN'})
        Path(tmp).rename(out)
    return {'status':'CONTROL_INPUT_PREPARED','out':str(out),'submitted':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(prepare(args.render,args.out))
