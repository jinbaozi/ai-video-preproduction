# AI 短剧制作团队 · V2.0

以现有七技能组成单宿主制作团队：写出对白、量真实时长、锁定人物与空间、先做风险镜头、通过后批量，再剪辑与验收。AI 负责创作和实际看片，程序负责原生校验、状态、费用和字节证据。

[最终分析与实施方案](audit/v2.0/analysis-implementation.md) · [制作手册](ai-comic-drama-workflow/references/studio-production.md) · [验证结果](audit/v2.0/validation.md)

## 开始制作

```text
使用 ai-comic-drama-workflow 的 studio 模式，根据我的剧本制作竖屏短剧。
普通创作自行定稿；先量对白时长，再制作风险镜头。
保持原句、人物参考和道具持有。目标是实际成片。
```

```sh
python -m pip install -e ./ai-comic-drama-workflow
ai-comic-drama start '你的简报或剧本文件' --project ./episode \
  --production-target video --target '<实际模型入口>'
ai-comic-drama step ./episode --result '<宿主实际结果.json>'
```

用户不手填 JSON。宿主读取当前 `context` 和所需原生文件，创作、检查，再提交结果。程序生成哈希与校验回执。缺实际能力时指出阻塞，不把提示词交付改称已成片。

## 新默认减少什么

| 配置 | studio：新默认 | lean：保留旧行为 | audited |
|---|---|---|---|
| 执行者 | 当前宿主连续执行 | 当前宿主连续执行 | 既有独立任务与审阅 |
| 方法库 | 按需，不强制采用材料 | 自动路由并提交采用证据 | 自动路由并审阅 |
| Flow 2K | 不默认要求 | full 默认要求 | full 默认要求 |
| 编辑 | 内置 FFmpeg | 剪映依赖检查 | 剪映依赖检查 |
| 上下文 | 最小 core | 最小 core | 完整 audit |
| 内容与真实媒体门 | 保留 | 保留 | 保留并独立任务审阅 |

可显式设置 `--craft-routing auto`、`--reference-refinement google-flow-2k`、`--editing-backend jianying-headless`。已有项目不自动切换配置。V2.0 不新增八个常驻 Agent，不新增调度器或平行 IR。

## 七项专业责任

| 技能 | 权威产物 |
|---|---|
| [工作流](ai-comic-drama-workflow/SKILL.md) | Canon、来源、依赖、进度与交付 |
| [编剧](screenplay-grammar/SKILL.md) | ScriptIR、对白与因果 |
| [导演](director-grammar/SKILL.md) | DirectorIR、表演与视听意图 |
| [美术](production-design-grammar/SKILL.md) | ArtIR、脸/服装/空间/道具 |
| [图像](image-prompt-optimizer/SKILL.md) | 参考提示词与真实素材合同 |
| [分镜](storyboard-grammar/SKILL.md) | StoryboardIR、起止态与连续性 |
| [视频编译](video-prompt-compiler/SKILL.md) | AVIR、模型正文与附件映射 |

七技能仍可独立使用。必要专业规则留在原生字段，不要求每镜另写方法论文。复杂动作、精确模型控制和来源争议按需展开；不删硬约束或伪造原文。

## 制作事实与交付

新增能力均扩展原生 `production`：真实对白量时长、五镜试制门、金额预留/结算、原任务对账与回收。视频探测实际解码；同字节同进程缓存避免重复解码。UNKNOWN 不能换请求 ID 重提，手动和自动都计尝试。studio 视频提交前必须配置预算；真实报价、授权和工具入口由当前宿主提供。

从 `00-progress.md` 继续工作，从 `09-delivery/index.md` 取成果。`DELIVERED` 表示前期交付，`VIDEO_DELIVERED` 需要真实文件和全片验收；发布另需实际授权和回执。便携 JSON 不是原生剪映工程。自审不是独立审阅，合成测试片不是短剧制作实证。

## 安装与验证

需要 Python 3.12+；实际音视频处理需要环境中可用的 `ffmpeg` 和 `ffprobe`。

[dists](dists/) 包含七个独立 `.skill`、manifest 和 SHA-256；总包内置六模块与独立包字节一致。工作流包为 `0.20.0`，V2.0 是本次方案与分支版本。

```sh
python ai-comic-drama-workflow/scripts/sync_shared.py --check
python video-prompt-compiler/scripts/reference_audit.py --suite .
python video-prompt-compiler/scripts/vpc.py knowledge audit
python ai-comic-drama-workflow/scripts/run_tests.py
python ai-comic-drama-workflow/scripts/package_suite.py --out dists
python ai-comic-drama-workflow/scripts/verify_suite.py --packages dists --out ./work/verify
```

[原生接口与历史](ai-comic-drama-workflow/README.md) · [旧最小核心设计](audit/minimal-core-plan.md) · [历史审计](audit/)
