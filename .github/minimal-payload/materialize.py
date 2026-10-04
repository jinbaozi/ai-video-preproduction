import bz2, hashlib, json, re, subprocess
from pathlib import Path, PurePosixPath
folder=Path('.github/minimal-payload')
parts=[(folder/f'part-{i}.bin').read_bytes() for i in range(1,5)]
# Correct one observed transfer byte; both final payload and source-file hashes remain mandatory.
assert hashlib.sha1(b'blob 9000\0'+parts[1]).hexdigest()=='7b49313ac199479d99c5d55f9d4130620227009c'
part=bytearray(parts[1]);assert part[1595]==247;part[1595]=251;parts[1]=bytes(part)
data=b''.join(parts)
assert len(data)==30949
assert hashlib.sha256(data).hexdigest()=='09c8246b4622332ddeead123cf6d5c7ac944a59d1430bd18a2e87c7b2f0e6411'
decoder=bz2.BZ2Decompressor();payload=decoder.decompress(data,max_length=150321)
assert decoder.eof and not decoder.unused_data and len(payload)==150320
assert hashlib.sha256(payload).hexdigest()=='1851082be477eb9e2589b5e02a8f7de28ff456cc82045dfc4e4adad5a84c371b'
obj=json.loads(payload);assert obj['schema']=='reviewed-line-edits/1' and len(obj['files'])==57
allowed={'README.md','audit','ai-comic-drama-workflow','screenplay-grammar','director-grammar','production-design-grammar','image-prompt-optimizer','storyboard-grammar','video-prompt-compiler'}
root=Path.cwd().resolve();seen=set()
def safe(value):
    p=PurePosixPath(value)
    assert not p.is_absolute() and '..' not in p.parts and p.parts[0] in allowed
    target=root/Path(value)
    assert target.resolve().is_relative_to(root) and not target.is_symlink()
    return target
for row in obj['files']:
    path=row['path'];assert path not in seen;seen.add(path);target=safe(path)
    if row['source']:
        safe(row['source'])
        original=subprocess.check_output(['git','show','HEAD:'+row['source']])
    else:
        assert not target.exists();original=b''
    assert hashlib.sha256(original).hexdigest()==row['source_sha256']
    text=original.decode('utf-8')
    if row.get('transform')=='detailed-execution/1':
        assert path.endswith('/references/detailed-execution.md')
        body=re.sub(r'^---\n.*?\n---\n','',text,flags=re.S)
        def link(match):
            url=match.group(1)
            return match.group(0) if url.startswith(('#','http:','https:','//','mailto:')) else ']('+('../'+url)+match.group(2)+')'
        body=re.sub(r'\]\(([^\s)]+)([^)]*)\)',link,body)
        rendered='# 完整执行参考（按需）\n\n默认先使用阶段核心合同；本页保留原有专业细节、旧协议和专门任务入口，不是每次全量读取清单。\n\n'+body
    else:
        assert 'transform' not in row
        lines=text.splitlines(keepends=True);parts=[];cursor=0
        for start,end,replacement in row['edits']:
            assert type(start) is int and type(end) is int and cursor<=start<=end<=len(lines)
            parts.extend(lines[cursor:start]);parts.append(replacement);cursor=end
        parts.extend(lines[cursor:]);rendered=''.join(parts)
    output=rendered.encode('utf-8');assert hashlib.sha256(output).hexdigest()==row['sha256'],path
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(output)
subprocess.run(['git','add','--',*sorted(seen)],check=True)
print('Verified source files:',len(seen))
