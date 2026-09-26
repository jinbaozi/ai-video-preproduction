# 七技能独立运行与协作工作流 V6

新项目默认使用 V6 编排协议：内核按 [唯一阶段图](workflow-v6.json) 生成任务和检查门，Codex 宿主真实派发专业子智能体，独立审阅后才接受候选。总包携带六个专业 Skill 的锁定发行物；专业模块也可分别安装。`production_target=video` 时继续登记真实执行、媒体回收、验收及总装。

## 开始使用

```text
使用 $ai-comic-drama-workflow，根据这些资料制作参考图与视频提示词包。
按 V6 派发专业子智能体并独立审阅；复用已有剧本和资产，保留原文对白与身份。
只在角色身份首次定稿、硬冲突、显著费用或能力降级时提出必要决定。
```

只需要文字时明确说“仅生成视频提示词，纯文本交付”。单条提示词、独立导演方案、美术或分镜直接调用对应专业 Skill，不强制建项目。

阶段图包含资料观察、Canon、编剧、导演、美术、视觉资产、分镜、调度控制包、分镜图片、编译复核和前期交付；视频目标再接执行、Take、逐镜与相邻验收、总装和整片交付。图中条件不适用的节点仍留 `NOT_APPLICABLE` 记录。已有合格内容进入来源验证与职责复核，再从对应节点接续。

## 安装与命令

安装为 Skill 时保留整个单根目录。在技能根目录使用 Python 3.12+ 安装依赖（`pyproject.toml` 列出 `jsonschema`），再运行：

```sh
PYTHONPATH=src python -m ai_comic_drama_workflow doctor
PYTHONPATH=src python -m ai_comic_drama_workflow init 原文.txt --project /绝对路径/新项目 --project-id MY_STORY --target agnes-video-2.5
PYTHONPATH=src python -m ai_comic_drama_workflow run /绝对路径/新项目
PYTHONPATH=src python -m ai_comic_drama_workflow graph --format mermaid
PYTHONPATH=src python -m ai_comic_drama_workflow migrate-v6 /绝对路径/旧项目 --destination /绝对路径/迁移副本
```

也可 `pip install .` 使用 `ai-comic-drama`。V6 的 `run` 返回待执行的 Codex 宿主动作；宿主用真实协作工具派发、登记回执和结构化消息。Python 本身没有模型调用能力。各登记命令和恢复流程见 [V6 接口](references/v6/runtime.md)。

`graph` 从 `workflow-v6.json` 直接生成 Mermaid，阶段字段与内核调度使用同一份定义。

- [V6 CLI、协议与恢复](references/v6/runtime.md)
- [V6 验收证据索引](references/v6/acceptance.md)
- [V5 旧接口与结果记录](references/v5/runtime.md)
- [职责、交接、版本和媒体边界](references/v5/contracts.md)
- [锁定模块与独立发行](references/v5/modules.md)
- [旧项目安全复制迁移](references/v5/migration.md)
- [固定三镜头样例](examples/v5/cafe/README.md)
- [验证范围与验收记录](references/v5/verification.md)

## V5 旧协议样例与验证

```sh
PYTHONPATH=src python scripts/run_v5_example.py --out /绝对路径/空样例目录
PYTHONPATH=src python -m unittest discover -s tests -p test_v5_workflow.py -v
python scripts/package_skill.py --out /绝对路径/单包发行
```

样例使用固定原文和已编写的原生制作包，证明旧协议静态交接和编译可运行，不证明 V6 子智能体派发或媒体质量。完整流程还需要宿主真实工具、实际看图和身份决定。

V5 使用独立的 project/state/任务协议。新项目默认 V6；显式 `init ... --orchestration current-agent` 才使用旧当前 Agent 路径。V4 项目与旧全流程保留各自历史，复制迁移后的旧“通过”状态不自动成为 V6 审阅证据。

## V5.2 运动与空间

新完整制作采用 DirectorIR / StoryboardIR / AVIR 1.2，支持部位轨迹、动态构图、时刻画格与 `revise storyboard --node-id ID` / `--track-id ID`。工作流 Skill 0.11.0、转换器 1.2.0；各专业模块版本以 `modules.lock.json` 为准，项目存储仍 5.0。编译器将完整制作合同保留在审计附件，向模型交付按镜头与时间展开的正文及其字段覆盖，并按模型单次时长生成自包含的分段提示词；每段包含该段所需完整图片引用和细节，阻塞片段保留阻塞状态。既有项目模块锁不自动迁移。

[当前执行合同](references/current-contract.md)说明明确相对描述、数值依据、无损正文及几何判定边界。旧项目模块锁保持，旧包升级只生成新草案。运行 `python scripts/run_v5_example.py --version v52 --out NEW_DIR` 验证内置模块三镜文本链。
