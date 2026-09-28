# 七技能创意到视频套装

从一句话或创意制作参考图、分镜、可复制的视频提示词和附件包；有真实执行入口时，继续生成、回收和验收视频。七个专业职责保留，简单任务不再默认拆成七个子智能体。总工作流自带六个专业模块，`hypit-ai` 保持原状。

## 一句话开始

```text
使用 $ai-comic-drama-workflow：成年旅人雨夜拾起信封，街灯由冷转暖，焦点从信封移向他的表情。
目标入口 Agnes Video 2.5；用默认 lean 连续完成参考图、分镜、提示词和附件包。
只制作镜头实际需要的资产；保留人物、动作、光色、转焦与声音控制。普通阶段不要反复确认。
```

用户不需要填写 JSON。ChatGPT/Codex 宿主按任务调用专业技能、实际生成并审阅媒体；Python 内核管理原生结果、状态、来源和校验，不代替创作，也不自动调用未登记的模型。

安装工作流目录后，宿主使用：

```sh
python -m pip install -e ./ai-comic-drama-workflow
ai-comic-drama start '成年旅人雨夜拾起信封，街灯由冷转暖。' \
  --project ./rain-letter --target agnes-video-2.5 --delivery full
# 宿主读取返回的 task_file / required_reads，创作当前原生结果，然后连续推进：
ai-comic-drama step ./rain-letter --result ./result.json
```

最终从 `delivery/index.md` 获取实际分段、投喂正文、附件和验收依据。`step` 不是一次命令自动生成整片的模型客户端。

新 `start` 按镜头风险选择最少控制素材：简单镜头不做白模，接触/遮挡用事件几何帧，耦合运动用连续白模预演。几何帧必须成为分镜图的真实输入，不止存放在目录中；未知轨迹、失效素材和未支持通道仍阻断。详情见[自适应控制](video-prompt-compiler/references/adaptive-control.md)和[对抗审查记录](audit/adaptive-control.md)。

## 两种执行路径

| 入口 | 用途 | 审阅方式 |
|---|---|---|
| `start` / `start --profile lean` | 一句话创意、快速连续制作；当前宿主承担专业职责 | 原生检查与当前 Agent 语义/交付复核，不冒充独立审阅 |
| `start --profile audited` | 明确需要专业子智能体分工和独立审阅 | 完整 V6 派发、候选、交接和独立审阅 |
| 原 `init` | 兼容现有脚本 | 仍默认 V6，不静默降级 |

lean 的宿主节奏是：**创意与镜头收敛 → 必要素材 → 模型编译与交付复核 → 交付/真实生产**。它不是新的内容 IR，也不伪造内核节点合并。Canon、ScriptIR、DirectorIR、ArtIR、StoryboardIR、AVIR 的依赖、锁、原生校验与收据仍逐项执行。

audited/V6 的阶段图来自 [workflow-v6.json](ai-comic-drama-workflow/workflow-v6.json)，可用 `ai-comic-drama graph --format mermaid` 查看。此模式的正式接受要求真实派发身份、候选证据和独立审阅；`NOT_APPLICABLE` 也须有条件和证据。旧 V5/V6 项目保留原协议，不因安装新版而迁移。

[Lean 执行合同](ai-comic-drama-workflow/references/lean.md) · [原生接口](ai-comic-drama-workflow/references/v5/runtime.md) · [V6 接口](ai-comic-drama-workflow/references/v6/runtime.md)

## 七个专业入口

| Skill | 职责 |
|---|---|
| [ai-comic-drama-workflow](ai-comic-drama-workflow/SKILL.md) | 唯一项目入口，管理事实、资产、决定、版本和交付 |
| [screenplay-grammar](screenplay-grammar/SKILL.md) | 故事因果、人物认知、信息约束与台词 |
| [director-grammar](director-grammar/SKILL.md) | 表演、叙事显露、视听原则与导演锁定 |
| [production-design-grammar](production-design-grammar/SKILL.md) | 角色服装、空间、道具、材质与光源 |
| [image-prompt-optimizer](image-prompt-optimizer/SKILL.md) | 保持设计，优化图像表达与参考素材控制 |
| [storyboard-grammar](storyboard-grammar/SKILL.md) | 逐镜动作、画格、空间和镜头连续性 |
| [video-prompt-compiler](video-prompt-compiler/SKILL.md) | 冻结分镜到模型提示词与附件的唯一出口 |

各入口可独立使用。没有上游时，允许在用户范围内设计并标明来源；已有成果先验证其原生来源与有效性，再复用，导入不等于通过验收。

## 少文件，不少质量依据

lean 不再默认写出重复的制作规格、上下文、覆盖/损失报告等旁路副本；权威 `avir.json`、完整 `artifact.json`、能力快照、完整性清单和实际分段交付仍保留。成功事务清理自己的恢复备份，失败恢复继续保留证据，不自动删除旧项目或历史原件。

素材按实际消费用途规划，不默认凑齐所有多视图、空镜、LUT 或白模。已经接受为必需的资产不能跳过。多主体交互、接触与复杂运镜继续触发既有 [镜头控制合同](video-prompt-compiler/references/shot-control.md)；来源、身份、动作、光色、转焦、声音及连续性要求不因精简而删除。

未知能力、内容篡改、过期审阅和缺失媒体仍会阻塞。静态检查通过不代表模型已经遵从，也不保证实际画质。

## 两个交付终点

`full` 默认需要真实参考图；`text-only` 只有用户明确要求时使用，缺图不能自动降级。

`DELIVERED` 表示前期包完成。`production_target=video` 还要完成真实提交或人工回收、Take 复探测、逐镜/相邻验收、总装和整片审阅；当前输出字节与冻结证据一致后才能成为 `VIDEO_DELIVERED`。`DRAFT_REQUIRES_TARGET_CHECK` 不是执行就绪，`submitted=false` 也不能写成已生成。

模型能力以锁定注册表及 [能力矩阵](video-prompt-compiler/references/capability-matrix.md) 为准。当前具体执行边界见 [执行合同](video-prompt-compiler/references/current-contract.md)。三镜静态样板在 `ai-comic-drama-workflow/examples/production/envelope-3shot/`；不提供真实入口/媒体时，真实视频状态保持 `NOT_RUN`。

## 安装、验证与历史

[dists](dists/) 包含七个 `.skill`、各自 manifest/SHA-256 和套装清单。总包内置模块必须与独立包字节一致，源码修改后须重建，不能把旧发行包当作当前版本。具体用法见 [工作流 README](ai-comic-drama-workflow/README.md)。

本次方案、变更和静态实测见 [IMPLEMENTATION-LEAN.md](IMPLEMENTATION-LEAN.md)。CI 并行检查原生工作流、编译器与七包隔离安装；基准不包含 LLM 创作、模型排队/推理和最终画质。

历史协议按需阅读：[迁移说明](ai-comic-drama-workflow/references/v5/migration.md)、[V5.1 细节](video-prompt-compiler/references/history/detail-contract-v51.md)、[V5.2 空间](video-prompt-compiler/references/history/spatial-contract-v52.md)、[镜头控制实施](IMPLEMENTATION-SHOT-CONTROL.md)。旧项目显式迁移使用 `migrate-v6 OLD --destination NEW`，保留原件；缺少的真实派发或审阅证据不补写虚构历史。
