#!/usr/bin/env python3
"""One text-mode Agnes call. Proves submit and download. Does not claim shot quality."""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ai_comic_drama_workflow.executors.agnes_api import AgnesApiExecutor
from ai_comic_drama_workflow.executors.agnes_http import AgnesHttpTransport
from ai_comic_drama_workflow.production import ProductionLedger
from ai_comic_drama_workflow.v5 import V5Kernel


def main():
    if not os.environ.get('AGNES_API_KEY'):
        raise SystemExit('AGNES_API_KEY is required')
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    project = out / 'project'
    if project.exists():
        raise SystemExit('probe project already exists: ' + str(project))
    kernel = V5Kernel.initialize(project, ['文生视频执行探测，不是三镜质量验收。'], delivery='text-only', production_target='video', target='agnes-video-2.5-flash', mode='text')
    ledger = ProductionLedger(kernel)
    payload = {
        'model': 'agnes-video-2.5-flash', 'mode': 'text', 'seconds': '4', 'size': '720P',
        'aspect_ratio': '16:9', 'n': 1,
        'prompt': '一张木桌，一只蓝色信封静置在桌面中央，固定机位，无人物，自然光。',
    }
    request = {'id': 'REQUEST_001', 'submitted': False, 'payload_draft': payload, 'scope': {'shot_ids': []}}
    job = ledger.plan_job(request, hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), [], [], {'max_attempts': 1, 'project_cap': 1})
    dest = out / 'take.mp4'
    result = AgnesApiExecutor(ledger, AgnesHttpTransport()).execute(job['id'], dest)
    public = {k: v for k, v in result.items() if k != 'take'}
    if result.get('take'):
        take = result['take']
        public['take'] = {k: take[k] for k in ('id', 'sha256', 'automatic', 'probe', 'uri')}
    (out / 'result.json').write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': public.get('status'), 'out': str(out)}, ensure_ascii=False))
    return 0 if public.get('status') == 'SUCCEEDED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
