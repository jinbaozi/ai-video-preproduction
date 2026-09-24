#!/usr/bin/env python3
"""Local shot-control derivation, media checks and evidence-bound handoff."""
import argparse
import json
from pathlib import Path
import sys
import subprocess
from shot_control.common import read, write, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build'); p.add_argument('input'); p.add_argument('--config'); p.add_argument('--out', required=True)
    p = sub.add_parser('probe'); p.add_argument('input')
    p = sub.add_parser('edit-check'); p.add_argument('input')
    p = sub.add_parser('keyframe-check'); p.add_argument('input'); p.add_argument('--package', required=True); p.add_argument('--artifacts', required=True)
    p = sub.add_parser('verify'); p.add_argument('package')
    p = sub.add_parser('segment'); p.add_argument('input'); p.add_argument('--target', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('lower'); p.add_argument('package'); p.add_argument('--target', required=True); p.add_argument('--mode', required=True); p.add_argument('--artifacts', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('review'); p.add_argument('input'); p.add_argument('--package', required=True); p.add_argument('--media', required=True); p.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'build':
            from shot_control.control_plan import build
            result = build(args.input, args.out, read(args.config) if args.config else None)
        elif args.command == 'probe':
            from shot_control.media_probe import probe
            result = probe(args.input)
        elif args.command == 'edit-check':
            from shot_control.control_lowering import validate_delta
            result = validate_delta(read(args.input))
        elif args.command == 'keyframe-check':
            from shot_control.keyframes import check_request
            result = check_request(read(args.input), args.package, args.artifacts)
        elif args.command == 'verify':
            from shot_control.package import verify_package
            verify_package(args.package)
            result = {'status': 'VERIFIED', 'media_review': 'NOT_RUN'}
        elif args.command == 'lower':
            from shot_control.control_lowering import lower
            result = lower(args.package, args.target, args.mode, args.artifacts)
            if Path(args.out).exists():
                raise ValueError('Use a new output file')
            write(args.out, result)
        elif args.command == 'segment':
            from vpc_core import profile, validate
            import spatial_runtime as spatial
            from shot_control.segment_candidates import propose
            source = Path(args.input).resolve(); ir = read(source)
            if ir.get('schema') != 'avir/1.2' or any(e['severity'] in ('error','blocker') for e in validate(ir, source.parent)):
                raise ValueError('Requires valid AVIR 1.2')
            result = propose(ir, spatial, profile(args.target)['duration_ms'])
            if Path(args.out).exists(): raise ValueError('Use a new output file')
            write(args.out, result)
        else:
            from shot_control.media_review import evaluate
            review = read(args.input)
            if sha(args.media) != review['media_sha256']:
                raise ValueError('Observed media hash mismatch')
            result = evaluate(review, args.package, args.media)
            if Path(args.out).exists():
                raise ValueError('Use a new output file')
            write(args.out, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get('status') == 'BLOCKED' else 0
    except (OSError, ValueError, KeyError, IndexError, TypeError, subprocess.TimeoutExpired) as e:
        print(json.dumps({'status': 'ERROR', 'message': str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
