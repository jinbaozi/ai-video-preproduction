#!/usr/bin/env python3
"""One manifest for shared sources. Packages still receive physical copies."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ('ai-comic-drama-workflow', 'director-grammar', 'production-design-grammar',
          'storyboard-grammar', 'video-prompt-compiler', 'image-prompt-optimizer')


def manifest(workspace):
    workspace = Path(workspace)
    source = workspace/'video-prompt-compiler/scripts/shared_current/current-contract.md'
    return [(source, workspace/name/'references/current-contract.md') for name in SKILLS]


def _copy(pairs, check):
    records = {}
    for source, dest in pairs:
        data = source.read_bytes()
        if check:
            if not dest.is_file() or dest.read_bytes() != data:
                raise ValueError('Shared source drift: ' + str(dest))
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        records[str(dest)] = hashlib.sha256(data).hexdigest()
    return records


def sync(workspace=ROOT, check=False):
    import sys
    workspace = Path(workspace)
    sys.path.insert(0, str(workspace/'ai-comic-drama-workflow/scripts'))
    from sync_v51 import sync as sync_v51
    from sync_v52 import sync as sync_v52
    from sync_screenplay import sync as sync_screenplay
    from sync_shot_control import sync as sync_shot_control
    records = _copy(manifest(workspace), check)
    records['v51'] = sync_v51(workspace, check=check)
    records['v52'] = sync_v52(workspace, check=check)
    records['screenplay'] = sync_screenplay(workspace, check=check)
    records['shot_control'] = sync_shot_control(workspace, check=check)
    return records


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps({'status': 'CHECKED' if args.check else 'SYNCED', 'entries': len(manifest(ROOT))}, ensure_ascii=False))
    sync(check=args.check)
