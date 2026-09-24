#!/usr/bin/env python3
"""Ship one control source in independent image/video Skills; never change project locks."""
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[2]


def sync(workspace=ROOT, check=False):
    workspace = Path(workspace)
    source, target = workspace/'video-prompt-compiler', workspace/'image-prompt-optimizer'
    files = [source/'scripts/control_cli.py', source/'registries/control-capabilities.json',
             source/'references/shot-control.md']
    files += list((source/'scripts/shot_control').glob('*.py'))+list((source/'scripts/shot_control').glob('*.html'))
    files += [source/'schemas'/f'{name}.schema.json' for name in
              ('shot-control', 'shot-control-config', 'keyframe-request', 'edit-delta', 'control-artifacts', 'control-media-review', 'control-package', 'previs-geometry')]
    files += [source/'scripts'/n for n in ('spatial_runtime.py', 'detail_runtime.py')]
    files += [source/'schemas'/n for n in ('avir-1.1.schema.json', 'avir-1.2.schema.json')]
    for path in files:
        destination = target/path.relative_to(source)
        if check:
            if not destination.is_file() or destination.read_bytes() != path.read_bytes():
                raise ValueError('Shot control shared source drift: '+str(destination))
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    for name, destination_name in (('cafe.avir.json', 'control.avir.json'), ('cafe.source.txt', 'cafe.source.txt')):
        fixture = target/'tests/fixtures'/destination_name
        example = source/'examples/v52'/name
        if check:
            if not fixture.is_file() or fixture.read_bytes() != example.read_bytes():
                raise ValueError('Standalone control fixture drift')
        else:
            fixture.parent.mkdir(parents=True, exist_ok=True)
            fixture.write_bytes(example.read_bytes())
    return len(files)+2



if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--check', action='store_true'); args = p.parse_args()
    print(sync(check=args.check))
