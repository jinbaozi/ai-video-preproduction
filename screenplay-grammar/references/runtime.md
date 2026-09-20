# 协议与执行

Python 3.10+，安装 requirements.txt。所有 schema 在 schemas/。sg.py --help 提供命令；编译完全离线。

- init --project-id ID --title 标题 --brief 需求 --output screenplay|story --out project.json：只建立 DRAFT。
- validate project.json [--final]：常规结构/来源检查；final 额外要求正文、合同、READY、无未决事项和当前语义复核。
- route project.json：12 个叙事配置按标签和禁用技法确定性筛选，返回选择/备选/拒绝原因；30 位作者可作检索别名。
- apply project.json patch.json --out new.json：不覆盖，base_sha256=内容指纹，changes 为 path/value/reason。
- diff old.json new.json：可追溯路径差异，不自动决定修改权限。
- compile project.json --out 新目录：正文、只读快照、来源映射、合同、检查、交接与 manifest。

review.content_sha256 由 scripts/screenplay_protocol.py 的 content_hash(project) 计算；Agent 完成实际复核后填写 status/reviewer/findings。提供函数不代表脚本完成了语义判断。

NarrativeIR 只读，不能双向同步。外部文本改稿需比较正文、形成原生新版本并重新检查。本版不提供 Fountain/FDX 任意回导。

Fountain 子集使用 . 强制中文场景标题、@ 强制中文角色名、! 强制动作；叙事约束保留在 JSON，不承诺所有编辑器显示完全相同。纯故事只输出 story.md，不创建假剧本。
