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
              ('shot-control', 'shot-control-config', 'keyframe-request', 'edit-delta', 'control-artifacts', 'control-media-review')]
    for path in files:
        destination = target/path.relative_to(source)
        if check:
            if not destination.is_file() or destination.read_bytes() != path.read_bytes():
                raise ValueError('Shot control shared source drift: '+str(destination))
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    return len(files)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--check', action='store_true'); args = p.parse_args()
    print(sync(check=args.check))
