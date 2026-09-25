#!/usr/bin/env python3
"""Publish four capability layers from registries. Do not hand-edit the matrix."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _layer(ok, reason):
    return '已支持' if ok else '未支持（' + reason + '）'


def build():
    profiles = json.loads((ROOT/'registries/capabilities.json').read_text())['profiles']
    routes = json.loads((ROOT/'registries/control-capabilities.json').read_text())['routes']
    lines = ['# 能力矩阵', '', '由 `scripts/build_capability_matrix.py` 从注册表生成。', '',
             '| 入口 | 模式 | 文本适配 | 素材绑定 | 实际执行 | 质量验证 |', '|---|---|---|---|---|---|']
    by_route = {(r['model'], r['mode']): r for r in routes}
    for profile in profiles:
        for mode in profile['modes']:
            route = by_route.get((profile['model'], mode)) or by_route.get((profile['id'], mode))
            text = _layer(profile['backend'] in ('agnes_api_draft', 'prompt_plan'), profile['backend'])
            if route is None:
                bound, executed, quality = _layer(False, '无控制路由'), _layer(False, '无控制路由'), _layer(False, '无控制路由')
            else:
                bound = _layer(route.get('documented') and profile['backend'] == 'agnes_api_draft', '仅文档或非 Agnes API')
                executed = _layer(bool(route.get('probe_passed')), 'probe_passed=false')
                quality = _layer(bool(route.get('quality_validated')), 'quality_validated=false')
            lines.append(f"| {profile['id']} | {mode} | {text} | {bound} | {executed} | {quality} |")
    lines.append('')
    return '\n'.join(lines)


if __name__ == '__main__':
    out = ROOT/'references/capability-matrix.md'
    out.write_text(build(), encoding='utf-8')
    print(out)
