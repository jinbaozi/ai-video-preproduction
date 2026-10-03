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

新 lean 项目从 `00-progress.md` 查看阶段，从 `09-delivery/index.md` 获取实际分段、投喂正文、附件和验收依据；旧项目保留 `delivery/index.md`。`step` 不是一次命令自动生成整片的模型客户端。

新 `start` 按镜头风险选择最少控制素材：简单镜头不做白模，接触/遮挡用事件几何帧，耦合运动用连续白模预演。几何帧必须成为分镜图的真实输入，不止存放在目录中；未知轨迹、失效素材和未支持通道仍阻断。详情见[自适应控制](video-prompt-compiler/references/adaptive-control.md)和[对抗审查记录](audit/adaptive-control.md)。

## ChatGPT Desktop → RunningHub H3

```text
使用 video-prompt-compiler，目标 runninghub-h3-fl2va。
依据我附上的 RunningHub「Export Workflow API」文件，先识别真实节点与首尾帧模式。
生成 H3 专属提示词：成年工程师右手放下钥匙，暖台灯与冷窗光对照，焦点从钥匙移到眼睛；台词“终于找到了。”原样保留。
输出可复制提示词、节点修改表和必要风险；不改连线、不自动降步、不提交付费任务。
```

没有工作流文件也能先制作 H3 文本草案，但不能编造节点编号。使用 [H3 按需入口](video-prompt-compiler/references/models/minimax-h3.md)；Desktop 宿主是否支持工具、脚本或技能安装须以实际能力为准，阅读 Markdown 并复制提示词不依赖模型 API。新增实现与静态验证见 [H3 审查记录](audit/h3-runninghub.md)。

## 通用视频模板与模型专属能力

提示词技巧现在分为通用视听方法、27个任务模板和精确模型适配策略。依据已绑定来源的语义标签按需选择，采用证据进入现有 craft_review；分镜实际采用的模板随编译进入 artifact 和 manifest，不增加中间文件。Seedance的引用语法/模态推断不会泄漏到Agnes、Kling、H3或Veo，模板也不会重写冻结AVIR。

查看索引：`python video-prompt-compiler/scripts/vpc.py techniques list`。只读取一个模板：`... techniques plan --target seedance2.5 --template food-asmr`。原文台词、动作、目标模型、时长、声音路由和已锁定风格优先；未知能力及真实媒体验收继续由原门禁裁决。参见[方法分层合同](video-prompt-compiler/references/prompt-techniques.md)及[先行方案](audit/prompt-techniques-plan.md)。

## 未点名也默认启用专业方法

新 `start` 的 `craft-routing/1.0` 从原文提取有证据的语义特征，按职责选择方法与参考入口，并要求写进当前原生 IR。它不是关键词命中后列一串名人：任务附带选中方法、适用依据、来源、实际采用位置和可观察检查；没有采用证据不能接受结果。图片和视频编译继承既有规则，不重新决定风格。

主语法在项目/连续场景中保持稳定，当前场/镜按冻结范围细化；硬冲突回到原所有者，不用“自动最优”覆盖锁定项。独立专业技能也默认执行。只读取命中的规则与人物，不加载整个参考库。用户无需点名或填写 JSON；明确关闭时使用 `--craft-routing off`，旧项目保持旧协议。

参见[默认路由合同](ai-comic-drama-workflow/references/craft-routing.md)与[方案/测试记录](audit/automatic-craft-routing.md)。方法证据可检查，电影质量仍须通过真实生成与审片验证；不保证任何模型自动产出大片。

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

## 按顺序看进度，不遍历中间文件

完整任务默认 **autonomous-until-blocked**：普通阶段由 Agent 自主定稿并连续推进；只有登录/权限、未授权费用、UNKNOWN 执行、能力缺失或有界返修后仍无法通过质量门时才通知用户。

新 lean 默认 compact 输出；不用额外配置。从 `00-progress.md` 查看当前阶段、已接受产物、阻塞和下一步。目录仅在进入阶段或产生必要产物时创建：

```text
00-progress.md
01-source/          原始资料与项目事实
02-screenplay/      剧本
03-director/        导演方案
04-art/             美术与服化道
05-assets/          视觉资产
06-storyboard/      分镜与必要控制素材
07-boards/          分镜图片
08-video-prompts/   模型提示词与冻结编译包
09-delivery/        验收与交付入口
10-video/           有真实视频字节时创建
```

权威内容只保留一份；任务按字段指针读取它，不复制上游正文。已经嵌入任务的方法卡不再另存一份。原生依赖按内容去重复用，省去重复 manifest、阶段表和全状态交付副本。宿主按 `task.output_file` 创作，用 `step --result -` 提交 JSON，可省去作者草稿和额外 result 文件。`.runtime/` 只承担必要的模块、任务/结果证据、共享依赖、原件及恢复记录，不是阅读入口。

显式 `--output-profile audit` 保留原布局；已有项目与 audited 不自动改名或清理。文件少不等于上下文截断，也不等于跳过专业验收。参见[输出合同](ai-comic-drama-workflow/references/compact-workspace.md)与[方案及实测](audit/compact-workspace.md)。

## 少文件，不少质量依据

lean 不再默认写出重复的制作规格、上下文、覆盖/损失报告等旁路副本；权威 `avir.json`、完整 `artifact.json`、能力快照、完整性清单和实际分段交付仍保留。成功事务清理自己的恢复备份，失败恢复继续保留证据，不自动删除旧项目或历史原件。

素材按实际消费用途规划，不默认凑齐所有多视图、空镜、LUT 或白模。已经接受为必需的资产不能跳过。多主体交互、接触与复杂运镜继续触发既有 [镜头控制合同](video-prompt-compiler/references/shot-control.md)；来源、身份、动作、光色、转焦、声音及连续性要求不因精简而删除。

未知能力、内容篡改、过期审阅和缺失媒体仍会阻塞。静态检查通过不代表模型已经遵从，也不保证实际画质。

## 两个交付终点

`full` 默认需要真实参考图；`text-only` 只有用户明确要求时使用，缺图不能自动降级。实际图片通过原看图审核后，默认经 Google Flow 做保真 2K 派生参考素材，再进入视频模型附件映射；Flow 需要登录或保真/分辨率验收失败时阻断，不用 resize 冒充。

`DELIVERED` 表示前期包完成。`production_target=video` 还要完成真实提交或人工回收、Take 复探测、逐镜/相邻验收、总装和整片审阅。总装默认优先使用 `jinbaozi/jianying-headless` / `yichen-jianying-edit` 构建可编辑剪映草稿；需要成片时原生导出并验证 MP4。当前输出字节与冻结证据一致后才能成为 `VIDEO_DELIVERED`。`DRAFT_REQUIRES_TARGET_CHECK` 不是执行就绪，`submitted=false` 也不能写成已生成。

模型能力以锁定注册表及 [能力矩阵](video-prompt-compiler/references/capability-matrix.md) 为准。当前具体执行边界见 [执行合同](video-prompt-compiler/references/current-contract.md)。三镜静态样板在 `ai-comic-drama-workflow/examples/production/envelope-3shot/`；不提供真实入口/媒体时，真实视频状态保持 `NOT_RUN`。

## 安装、验证与历史

[dists](dists/) 包含七个 `.skill`、各自 manifest/SHA-256 和套装清单。总包内置模块必须与独立包字节一致，源码修改后须重建，不能把旧发行包当作当前版本。具体用法见 [工作流 README](ai-comic-drama-workflow/README.md)。

本次方案、变更和静态实测见 [IMPLEMENTATION-LEAN.md](IMPLEMENTATION-LEAN.md)。CI 并行检查原生工作流、编译器与七包隔离安装；基准不包含 LLM 创作、模型排队/推理和最终画质。

历史协议按需阅读：[迁移说明](ai-comic-drama-workflow/references/v5/migration.md)、[V5.1 细节](video-prompt-compiler/references/history/detail-contract-v51.md)、[V5.2 空间](video-prompt-compiler/references/history/spatial-contract-v52.md)、[镜头控制实施](IMPLEMENTATION-SHOT-CONTROL.md)。旧项目显式迁移使用 `migrate-v6 OLD --destination NEW`，保留原件；缺少的真实派发或审阅证据不补写虚构历史。

## Flow 与剪辑运行时修复

工作流 0.16.0 将 Flow 2K 与剪映节点接入真实宿主动作和字节证据校验。新 audited 项目冻结扩展图，旧项目保留原 25 阶段合同；丢失新项目冻结图会阻断。Flow 未知执行只回收，项目搬迁不会生成新请求身份。剪映原生后端与显式 portable-ffmpeg 后端分别报告，后者只交付 JSON 时间线，不冒充原生草稿。见[宿主执行合同](ai-comic-drama-workflow/references/flow-and-editing.md)。
