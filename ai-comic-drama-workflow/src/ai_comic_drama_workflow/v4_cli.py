"""V4 command surface; no video/render/audio commands."""
import argparse
import json
from pathlib import Path
from .v4 import V4Kernel
from .utils import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(prog='ai-comic-drama')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('inputs', nargs='+')
    init.add_argument('--project', required=True)
    init.add_argument('--title')
    init.add_argument('--input-type', choices=['novel', 'screenplay', 'storyboard', 'text', 'reference-image'])
    init.add_argument('--no-run', action='store_true')
    init.add_argument('--style')
    init.add_argument('--canvas')
    init.add_argument('--rights', choices=['authorized', 'draft-only'])
    init.add_argument('--image-budget', type=int)
    init.add_argument('--segment-seconds', type=float, default=15)
    for command in ('run', 'status', 'validate', 'export', 'resume', 'submit', 'host', 'revise', 'add'):
        item = sub.add_parser(command)
        item.add_argument('project')
        if command == 'validate':
            item.add_argument('--final', action='store_true')
        if command == 'export':
            item.add_argument('--draft', action='store_true')
        if command in ('resume', 'submit', 'host'):
            item.add_argument('--' + {'resume': 'decision', 'submit': 'result', 'host': 'capabilities'}[command], required=True)
        if command == 'revise':
            item.add_argument('phase')
            for scope in ('shot-id', 'scene-id', 'asset-id'):
                item.add_argument('--' + scope)
        if command == 'add':
            item.add_argument('inputs', nargs='+')
    copy = sub.add_parser('copy-project')
    copy.add_argument('project')
    copy.add_argument('--destination', required=True)
    sub.add_parser('doctor')
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            result = {'host': 'Codex required', 'models': 'must be verified by host inventory',
                      'image_gen': 'host-only; Python cannot prove availability', 'external_media_tools_required': []}
        elif args.command == 'init':
            kernel = V4Kernel.initialize(args.project, args.inputs, title=args.title, input_type=args.input_type,
                style=args.style, canvas=args.canvas, rights=args.rights, image_budget=args.image_budget, segment_seconds=args.segment_seconds)
            result = kernel.status() if args.no_run else kernel.run()
        elif args.command == 'copy-project':
            result = V4Kernel.copy_project(args.project, args.destination).status()
        else:
            kernel = V4Kernel(args.project)
            if args.command in ('run', 'status'):
                result = getattr(kernel, args.command)()
            elif args.command == 'validate':
                result = kernel.validate(args.final)
            elif args.command == 'export':
                result = kernel.export(args.draft)
            elif args.command == 'resume':
                result = kernel.resume(args.decision)
            elif args.command == 'submit':
                result = kernel.submit(args.result)
            elif args.command == 'host':
                info = read_json(Path(args.capabilities))
                result = kernel.configure_host(info['models'], info['image_capability'], info['evidence'])
            elif args.command == 'revise':
                result = kernel.revise(args.phase, shot_id=args.shot_id, scene_id=args.scene_id, asset_id=args.asset_id)
            elif args.command == 'add':
                result = kernel.add(args.inputs)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('valid') is False or result.get('status') == 'blocked' else 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({'status': 'error', 'error': str(error)}, ensure_ascii=False))
        return 1
