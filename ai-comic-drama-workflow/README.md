# 六技能独立运行与协作工作流 V5

当前 Agent 按九阶段把资料制作成参考图、分镜与视频提示词包。只安装本 Skill 即可运行，总包带有五个专业 Skill 的锁定发行物；专业模块也可分别安装。真实视频生成、配音、剪辑和发布由外部执行。

## 开始使用

```text
使用 $ai-comic-drama-workflow，根据这些资料制作参考图与视频提示词包。
复用已有剧本和资产，由当前 Agent 顺序完成；保留原文对白与身份。
只在角色身份首次定稿、硬冲突、显著费用或能力降级时提出必要决定。
```

只需要文字时明确说“仅生成视频提示词，纯文本交付”。单条提示词、独立导演方案、美术或分镜直接调用对应专业 Skill，不强制建项目。

```mermaid
flowchart LR
 A[资料与项目事实] --> B[故事与剧本]
 B --> C[导演方案]
 C --> D[美术方案]
 D --> E[视觉资产]
 E --> F[分镜制作]
 F --> G[分镜图片]
 G --> H[视频提示词编译]
 H --> I[验收交付]
```

已有合格内容直接接续，从最早缺失阶段开始。工作流管理来源、稳定ID、资产版本和用户决定；导演锁定、美术设计、分镜细化、编译转换各有边界。

## 安装与命令

安装为 Skill 时保留整个单根目录。在技能根目录使用Python 3.12+安装requirements（pyproject.toml列出jsonschema依赖），再运行：

```sh
PYTHONPATH=src python -m ai_comic_drama_workflow doctor
PYTHONPATH=src python -m ai_comic_drama_workflow init 原文.txt --project /绝对路径/新项目 --project-id MY_STORY --target agnes-video-2.5
PYTHONPATH=src python -m ai_comic_drama_workflow run /绝对路径/新项目
```

也可`pip install .`使用`ai-comic-drama`。CLI返回任务与验证结果；当前Agent负责理解、创作、执行宿主图片工具和看图。Python本身没有模型调用能力。

- [全部CLI与结果记录](references/v5/runtime.md)
- [职责、交接、版本和媒体边界](references/v5/contracts.md)
- [锁定模块与独立发行](references/v5/modules.md)
- [旧项目安全复制迁移](references/v5/migration.md)
- [固定三镜头样例](examples/v5/cafe/README.md)
- [验证范围与验收记录](references/v5/verification.md)

## 可复现样例与验证

```sh
PYTHONPATH=src python scripts/run_v5_example.py --out /绝对路径/空样例目录
PYTHONPATH=src python -m unittest discover -s tests -p test_v5_workflow.py -v
python scripts/package_skill.py --out /绝对路径/单包发行
```

样例使用固定原文和已编写的原生制作包，证明静态交接和编译可运行，不伪装实时创作或图片生成。完整流程还需要宿主真实生图/导入、实际看图和身份决定。ffmpeg/ffprobe只在真实图片登记时需要。

V5使用独立的project/state/任务协议，默认CLI只进入V5。V4项目与旧全流程只读复制后迁移；原“通过”状态不沿用为V5验收。旧实现及[原V4说明](references/v4/README-frozen.md)保留历史用途。新项目不继承V4固定模型、十阶段或5参考上限。

## V5.2 运动与空间

新完整制作采用 DirectorIR / StoryboardIR / AVIR 1.2，支持部位轨迹、动态构图、时刻画格与 `revise storyboard --node-id ID` / `--track-id ID`。工作流 Skill 0.7.0、视频提示词编译器 1.5.0、转换器 1.2.0；其他专业模块版本以 `modules.lock.json` 为准，项目存储仍 5.0。编译器将完整制作合同保留在审计附件，向模型交付按镜头与时间展开的正文及其字段覆盖，并按模型单次时长生成自包含的分段提示词；每段包含该段所需完整图片引用和细节，阻塞片段保留阻塞状态。既有项目模块锁不自动迁移。

[空间合同](references/spatial-contract-v52.md)说明明确相对描述、数值依据、无损正文及几何判定边界。旧项目模块锁保持，旧包升级只生成新草案。运行 `python scripts/run_v5_example.py --version v52 --out NEW_DIR` 验证内置模块三镜文本链。
