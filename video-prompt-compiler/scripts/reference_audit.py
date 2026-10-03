"""Audit local documentation reachability. Never run commands found in documents.

The generated index supplies a progressive metadata-only entry point; current,
model-specific and historical resources are all discoverable, not all auto-loaded.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

MODULES = ('ai-comic-drama-workflow', 'screenplay-grammar', 'director-grammar',
           'production-design-grammar', 'image-prompt-optimizer', 'storyboard-grammar', 'video-prompt-compiler')
INDEX = 'references/resource-index.md'


def documents(root):
    return sorted(p for p in (Path(root)/'references').rglob('*.md') if p.is_file())


def title(path):
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('# '): return line[2:].strip()
    return path.stem


def index_text(root):
    root = Path(root)
    lines = ['# 按需资料索引', '', '这里只列入口，不批量读取正文。先匹配当前职责、模型和任务；历史协议仅供显式兼容或迁移。',
             '代码命令示例不是执行授权；目录可达不等于每份资料中的操作均已实现。', '']
    for group in ('current', 'history'):
        lines += ['## ' + ('当前与专门任务资料' if group == 'current' else '历史与兼容资料'), '']
        for path in documents(root):
            rel = path.relative_to(root).as_posix()
            if rel == INDEX: continue
            historic = '/history/' in rel or '/v5/' in rel or '/v6/' in rel
            if historic != (group == 'history'): continue
            label = title(path).replace('[','').replace(']','').replace('\n',' ')
            lines.append('- ['+label+']('+path.relative_to(root/'references').as_posix()+')')
        lines.append('')
    return '\n'.join(lines)


def links(path, root):
    text = re.sub(r'(?ms)^(`{3,}|~{3,}).*?^\1[^\n]*$', '', path.read_text(encoding='utf-8'))
    output = []
    for raw in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"\n]*")?\)', text):
        target = unquote(raw.strip('<>'))
        if target.startswith('#') or urlparse(target).scheme or target.startswith('//'): continue
        target = target.split('#',1)[0]
        if not target:continue
        resolved = (path.parent/target).resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ValueError('Reference link leaves module: '+str(path)+' -> '+target)
        if not resolved.exists():
            raise ValueError('Broken reference link: '+str(path)+' -> '+target)
        if resolved.is_file() and resolved.suffix == '.md':output.append(resolved)
    return output


def audit(root):
    root = Path(root).resolve()
    if not (root/'SKILL.md').is_file() or not (root/INDEX).is_file():
        raise ValueError('Module entry/index missing: '+str(root))
    if (root/INDEX).read_text(encoding='utf-8') != index_text(root):
        raise ValueError('Stale resource index: '+str(root))
    seen, pending = set(), [root/'SKILL.md']
    while pending:
        path = pending.pop()
        if path in seen:continue
        seen.add(path)
        pending += links(path, root)
    missing = set(documents(root)) - seen
    if missing:raise ValueError('Unreachable documents: '+', '.join(str(x.relative_to(root)) for x in sorted(missing)))
    return {'module':root.name, 'status':'PASS','documents':len(documents(root)),
            'files':{p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in documents(root)},
            'boundary':'Local paths read and link traversal tested; historical commands and external APIs NOT_EXECUTED.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',type=Path);parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--write-index',action='store_true')
    args=parser.parse_args()
    try:
        roots=[args.suite/m for m in MODULES] if args.suite else [args.root]
        if args.write_index:
            for root in roots:(root/INDEX).write_text(index_text(root),encoding='utf-8')
        result={'status':'PASS','modules':[audit(root) for root in roots]}
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,UnicodeError) as error:
        print(json.dumps({'status':'BLOCKED','error':str(error)},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
