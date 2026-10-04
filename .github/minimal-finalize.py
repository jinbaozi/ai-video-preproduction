"""Apply reviewed entry discoverability and final local benchmark corrections."""
import hashlib
import json
from pathlib import Path

skills = {
    'ai-comic-drama-workflow': '84cbb8c757b6d1baf80210e5002f0c3a014a4cfbf7cce52fb9eab20ef6c2114f',
    'director-grammar': 'af6660702b8a3df1274fb236cc05fa4aad05c71d86188dac6ca19a65438e07c5',
    'image-prompt-optimizer': '9808c95ed792acc8be5fa706375aa306addb3f1c0175ca1c7aef5177e7d07203',
    'production-design-grammar': 'df5b39ceee09c51bf8598dc6780f25e4094e8662b2899aef42192872354ebb85',
    'screenplay-grammar': 'f5bafb41394add49d87850bccd49878bd8b4f4a5bfc9ec20ea61fa03f1350387',
    'storyboard-grammar': '82e2c7e3e3f82f65be0079eb1aa9765bfb4bc9a8b2483ac1a10f346e26bd3030',
    'video-prompt-compiler': '3920e9724e717e92f1695fd5b83dfd8ee076faccc34791b001757d9dc8bd43e8',
}
for name, digest in skills.items():
    path = Path(name) / 'SKILL.md'
    text = path.read_text()
    assert text.count('## 保留边界') == 1
    assert text.count('名家、场景与技巧按任务路由') == 1
    text = text.replace('## 保留边界', '## 默认专业方法路由')
    text = text.replace('名家、场景与技巧按任务路由', '[名家、场景与技巧](references/craft-routing.md)按任务路由')
    if name == 'ai-comic-drama-workflow':
        text += '\n[自主执行与阻塞](references/autonomous-until-blocked.md) · [Flow 2K](references/flow-2k-reference.md) · [剪映交接](references/jianying-postproduction.md)。只在相关生产任务读取。\n'
    assert hashlib.sha256(text.encode()).hexdigest() == digest
    path.write_text(text)

path = Path('audit/minimal-core-benchmark.json')
report = json.loads(path.read_text())
report['summary']['baseline']['seconds'] = 25.3674
report['summary']['core'].update(seconds=19.3665, seven_entry_bytes=11348, host_context_bytes=178755)
report['summary']['reduction_percent'].update(seconds=23.66, seven_entry_bytes=86.86, host_context_bytes=50.31)
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
path = Path('audit/minimal-core-implementation.md')
text = path.read_text()
for old, new in {'10,843':'11,348','87.45%':'86.86%','178,540':'178,755','50.37%':'50.31%','24.2851':'25.3674','17.9470':'19.3665','26.10%':'23.66%'}.items():
    assert old in text
    text = text.replace(old, new)
text = text.replace('本地最终新增22项通过', '本地新增22项通过')
needle = '本次191份reference文档完成可达性检查；'
assert needle in text
text = text.replace(needle, '首轮全量回归发现两项短入口可发现性退化：默认专业路由标题，以及自主执行、Flow与剪映的入口被移入深层。已恢复七个默认路由标题与必要直达链接，没有修改或放宽原断言；受影响的59项既有测试重跑通过。最终入口修复后重新进行三轮对照计量，表格使用该轮结果。\n\n' + needle)
path.write_text(text)
