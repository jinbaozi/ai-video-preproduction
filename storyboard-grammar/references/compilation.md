# 编译与可复现交接

## 运行

在Skill目录建立自己的Python 3.10+环境并安装requirements.txt；不要把测试机的绝对Python路径写成用户必需路径。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/storyboard.py inspect examples/cafe.ir.json
```
`route query`只建议标签；`inspect input`校验已结构化IR；`compile input --out 新目录`生成派生文件；`verify 输出目录`验证包完整性。
所有命令离线，无上传、付费、生成、渲染或发布操作。编译不会覆盖非空目录。

## 产物

| 文件 | 内容 |
|---|---|
| storyboard.ir.json | 完整输入IR，保留来源、状态、合同、画格 |
| storyboard.md | 可审阅镜头正文，包含空间、表演、原词、声画、参考和终态 |
| panel-briefs.json | 画格节点、机位、构图、参考用途；generated=false |
| production-contract.json / .md | 类型化与人类可读制作合同 |
| animatic.plan.json | 时轴与声音计划；不是animatic视频 |
| style-decision.json | 选中语法及规则快照、选择理由 |
| compiler-handoff.json | 宿主交接协议、原IR哈希、时间基、资产基路径 |
| qa.report.json | 结构结果、诊断、合同断言和未执行验收 |
| loss.report.json | AVIR字段缺口、原生控制与渠道待解析项 |
| compile-manifest.json | 输入、编译规则/代码/Schema和全部产物哈希 |

示例包括[cafe.ir.json](../examples/cafe.ir.json)（12秒/3镜/8格）、[product.ir.json](../examples/product.ir.json)（6秒/竖屏/无人声）和[missing-reference.ir.json](../examples/missing-reference.ir.json)（预期BLOCKED）。
同一输入、运行规则和资产基路径产生相同输出。产物不混入当前时钟时间；历史构建可以独立保留。
相对源文件、上游及参考路径相对于输入IR所在目录；交接记录asset_base。编译后的IR移到输出目录后，不应换错基目录直接inspect。
如需搬运真实制作项目，连同来源/参考文件搬运、重写URI与哈希并产生新revision；verify本身只核对交付文件，不下载缺失素材。

## 发布与检查

`python scripts/package_skill.py --out dist`生成单根storyboard-grammar.skill、manifest和SHA-256三件套。
归档包含Skill、agents、references、registries、styles、schemas、scripts、examples、tests及requirements；排除outputs、dist、缓存和环境。
ZIP排序、固定时间和权限确保可重复。发布脚本拒绝符号链接，检查ZIP安全路径、逐文件哈希和归档校验和。
交付前还需在独立解压目录跑quick_validate、单元测试、示例compile/verify和重复构建比对。
这些证明静态包可运行与可复现，不证明模型生成质量。
