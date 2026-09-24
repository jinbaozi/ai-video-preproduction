#!/usr/bin/env python3
"""Build a synthetic, explicitly authored geometric preview of the cafe fixture."""
import argparse
from pathlib import Path
import shutil
from shot_control.common import read, write
from shot_control.control_plan import build

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    ir = read(ROOT/'examples/v52/cafe.avir.json')
    ir['revision'] += 1
    ir['sources'][1]['claim'] += ' 白模演示补充：信封关键位置之间采用线性代理运动；这不代表已解决手指接触或身体表演。'
    for track in ir['timeline']['motion_tracks']:
        if track['node_id'] == 'N_ENVELOPE' and track['property'] == 'position':
            for k in track['keyframes'][:-1]: k['transition'] = 'linear'
            track['path'] = '白模演示的显式设计补充：按已有关键位置线性移动；不新增路径点。'
            track['origin']['locator'] = 'Synthetic previs example: authored linear envelope interpolation, not measured motion'
    evidence = 'Synthetic authored geometry extents; not calibrated anatomy or production design'
    def solid(ident, node, shape, size, offset):
        return {'id':ident, 'shot_ids':['S1'], 'node_id':node, 'shape':shape, 'dimensions':size,
                'offset_world':offset, 'orientation':'world_axes', 'evidence':evidence}
    geometry = {'schema':'previs-geometry/0.1','basis':'authored_proxy','evidence':evidence,'fps':24,'resolution':[640,360],
                'objects': [solid('A_TORSO','N_A','ellipsoid',[.4,.65,.3],[0,.95,0]),
                            solid('A_HEAD','N_A','ellipsoid',[.25,.3,.25],[0,1.43,0]),
                            solid('B_TORSO','N_B','ellipsoid',[.4,.65,.3],[0,.95,0]),
                            solid('B_HEAD','N_B','ellipsoid',[.25,.3,.25],[0,1.43,0]),
                            solid('ENVELOPE','N_ENVELOPE','box',[.24,.01,.13],[0,0,0]),
                            solid('TABLE','N_TABLE','box',[1.2,.08,.8],[0,.71,0]),
                            solid('FLOOR','N_ROOM','box',[5,.05,5],[0,-.025,0])]}
    config = {'schema':'shot-control-config/0.2','lenses': {s['id']: {'vertical_fov_deg':50,'aspect':16/9,
              'basis':'authored_proxy','evidence':evidence} for s in ir['shots']}, 'controls': [], 'proxy_scene':geometry}
    clause = next(c for c in ir['contract'] if c['channel']=='prompt' and ('S1' in c['shot_ids'] or not c['shot_ids']))
    config['controls'] = [{'id':'CLAY_S1', 'requirement_id':clause['id'],'shot_ids':['S1'],
        'source_pointers':[x['path'] for x in clause['checks']], 'channel':'clay_video_reference','artifact_ids':['CLAY_S1'],
        'hardness':clause['level'], 'fallback_policy':'block','purpose':'supplement'}]
    return ir,config


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',required=True); args=p.parse_args()
    out=Path(args.out).resolve()
    if out.exists() and any(out.iterdir()): raise ValueError('Output directory must be empty')
    ir,config=fixture(); write(out/'source/cafe-previs.avir.json',ir); write(out/'source/control-config.json',config)
    shutil.copyfile(ROOT/'examples/v52/cafe.source.txt',out/'source/cafe.source.txt')
    print(build(out/'source/cafe-previs.avir.json',out/'package',config))


if __name__=='__main__': main()
