# 七技能套装 V6

七个入口各自可用，总工作流另外携带六个专业模块的锁定包。新项目默认采用 V6 编排协议：内核确定任务和状态门，Codex 宿主真实派发专业子智能体，独立审阅者复核候选。旧 V5 项目保留原协议。`hypit-ai` 保持原状。

## 完整制作从哪里进

完整制作的入口是 [ai-comic-drama-workflow/SKILL.md](ai-comic-drama-workflow/SKILL.md)。阶段、责任、依赖、检查与适用条件来自 [workflow-v6.json](ai-comic-drama-workflow/workflow-v6.json)。

运行 `ai-comic-drama graph --format mermaid` 可从这份可执行定义直接生成 V6 流程图；`--format json` 可同时查看节点字段。

`run` 返回待执行动作；Codex 宿主派发真实子智能体，登记派发回执、消息、候选结果和独立审阅。专业智能体只在自己的候选目录工作，正式产物和状态由内核提交。`ACCEPTED` 需要冻结输入、真实执行身份、专业检查、完整交接与独立审阅都通过；`NOT_APPLICABLE` 也必须有规则与证据。详见 [V6 执行接口](ai-comic-drama-workflow/references/v6/runtime.md)。

| 入口 | 独立使用示例 | 协作职责 |
|---|---|---|
| ai-comic-drama-workflow | 根据原文制作参考图、分镜和视频提示词完整包 | 唯一项目入口，管理事实、资产、决定和版本 |
| screenplay-grammar | 一句话生成中文/国风故事或剧本，补全润色扩写 | 故事因果、人物认知、信息约束与台词 |
| director-grammar | 为这段剧本设计信息显露、关键表演与镜头原则 | 决定与锁定 |
| production-design-grammar | 为这个场景设计角色服装、空间、道具与光源 | 世界与逐镜美术约束 |
| storyboard-grammar | 直接把这段原文细化为三镜分镜 | 细化未锁镜头、动作、画格和连续性 |
| video-prompt-compiler | 把这条镜头需求编成可复制模型提示词 | 冻结分镜到模型提示词与附件的唯一出口 |
| image-prompt-optimizer | 优化这张角色参考图的生成或编辑提示词 | 保持设计，改善图片提示表达与约束检查 |

所有专业技能：轻量需求直接给正文；完整任务由Agent整理原生格式并运行脚本，用户不需要填写JSON。没有上游时可以在用户范围内设计补充，并区分事实和设计来源。

复杂镜头的图片交接支持冻结宿主输入和登记实收关键帧：`keyframe-stage` 保存请求、提示词与有序参考副本，`keyframe-receive` 核对返回文件并保留逐项审图状态。它们不调用模型，也不自动写入审核通过或上传成功；详见[镜头控制合同](video-prompt-compiler/references/shot-control.md)。

完整调用：

```text
使用 $ai-comic-drama-workflow，按这份资料制作完整前期包，目标入口 Agnes Video 2.5。
按 V6 编排专业子智能体与独立审阅；复用已有有效内容，保留来源、对白与实体 ID。
交付实际参考图、分镜、可复制视频提示词、附件表和验收记录。
```

独立成果接续：保留原生包 `project_id` 和来源证据，进入相应节点验证与复核后复用；导入本身不直接满足完成门。总包内置模块与独立发行包应是同一构建结果，项目不会被全局安装升级静默改变。

旧项目：原件按 V5 协议继续；运行 `ai-comic-drama migrate-v6 OLD --destination NEW` 复制迁移。副本保留原字节、真实图片和原决定证据；旧成果经 V6 来源验证与复核后才能接受，缺少的派发或审阅证据不补写历史。

[工作流用法](ai-comic-drama-workflow/README.md) · [V6 执行接口](ai-comic-drama-workflow/references/v6/runtime.md) · [V5 旧接口](ai-comic-drama-workflow/references/v5/runtime.md) · [验收边界](ai-comic-drama-workflow/references/v5/verification.md)

发行目录为 [dists](dists/)，包含 7 个 `.skill`、各自的 manifest 与 SHA-256，以及 suite-manifest。安装时选择需要的入口即可；总工作流无需安装相邻专业目录。V6 源码与文档变更后的发行包须重新构建并验证，不能把旧包当成当前版本。


## 两个交付终点

`full` 与 `text-only` 仍区分前期包是否需要实际参考图。V6 的 `text-only` 对图片提示词与媒体节点留 `NOT_APPLICABLE` 记录，前期检查和审阅通过后记 `DELIVERED`。旧项目没有 `production_target` 时仍按原协议的 `none` 处理。

`production_target=video` 才进入成片链：冻结执行请求、真实提交或人工回收、Take 复探测、逐镜与相邻验收、总装和整片审阅。验收计划、选定 Take 与最终输出字节必须仍匹配，通过后才记 `VIDEO_DELIVERED`。编译产物里的 `submitted=false` 保持原样，执行状态写在生产台账。

能力以注册表生成的 [能力矩阵](video-prompt-compiler/references/capability-matrix.md) 为准。文本适配不等于该模型已能执行或已通过质量验证。

当前规则见 [当前执行合同](video-prompt-compiler/references/current-contract.md)。V5.1 至 V5.3 的增量说明在 [迁移](ai-comic-drama-workflow/references/v5/migration.md)。

三镜样板：`ai-comic-drama-workflow/examples/production/envelope-3shot/`。没有 `AGNES_API_KEY` 和可访问附件时，真实视频保持 NOT_RUN。

## 历史增量

以下段落保留给旧项目重放，不是新任务的默认阅读路径。

## V5.2 使用与边界

新完整制作使用 ScriptIR 1.0 → DirectorIR 1.2 → ArtIR 1.0 → StoryboardIR 1.2 → AVIR 1.2。ArtIR 不重复维护动作时间轨；保留导演原文件绑定和空间/服化道约束。轻量独立任务不强制结构化包。

推荐启动提示词：

```text
使用 ai-comic-drama-workflow V5.2，根据以下原文、参考和已有制作包完成前期制作。
目标模型/入口：[填写]；画幅与总时长：[填写]；输出目录：[填写]；交付范围：[完整参考图与提示词包 / 仅文本]。
必须保持：[角色身份、对白原文、关键动作顺序、服化道等]；允许补充：[既定动作的执行细节等]。
有参考视频时实际抽帧并查看关键变化，单独登记未听审的声音和未观察范围。
逐动作保留手别、路径、速度、接触、支撑、控制权、表情与视线，摄影机按分时操作展开。
对白和声音保留起止时间、说话人、画内/画外/旁白及原生/后期渠道；跨镜一句不重复。
既有决定沿用，普通修正自动继续。缺少中间姿态先补设计并标来源，不假定物理插值。
交付完整制作说明、可复制正文、覆盖报告和真实文件名附件表；超限保留完整版并提出拆段。
分别报告静态检查、实际图片审核、参考视频观察和实际视频执行状态。
```

已安装技能目录中运行 `python scripts/run_v5_example.py --version v52 --out NEW_DIR` 可重现三镜文本协作样例。它使用预先创作的虚构场景，只验证制作链，不生成视频或证明画质。

独立编译器示例：`python scripts/vpc.py compile examples/v51/cafe.avir.json --target agnes-video-2.5 --mode text --out NEW_DIR`。新版正文保持完整，不静默按字数截断；`segment-plan.json` 中缺少相位/关键姿态的切片保持 BLOCKED，完整切片仍需单独核验入口限制。

V6 新项目有适用的视频来源时，阶段图派发 `reference_observation` 专业任务；观察者用锁定模块提帧并实际查看，登记 `observation-register/6.0`、原始观察文件及哈希，再由独立审阅和内核复核。未观看范围及未听审声音仍是未验证。旧 V5 项目才使用 `NEEDS_REFERENCE_OBSERVATION` 与 `ai-comic-drama import-observation PROJECT OBSERVATION_DIR` 入口。

详见各包自带 [V5.1 细节合同](video-prompt-compiler/references/history/detail-contract-v51.md)。老项目不自动升级模块锁；旧协议读取、原版本重放和新标准达成是三种不同状态。当前结构性检查不能替代语义复核和真实媒体验收。

## V5.2 运动与空间使用

使用时说明：需要控制的主体/部位、运动路径与节奏、身体/头部/视线方向、相对位置的坐标依据、动态构图及遮挡、对白和声音时间、锁定项、目标入口、参考文件及允许补充范围。没有数值依据可用明确相对描述，不要求全部填坐标。

```text
依据所附原文和参考，使用 V5.2 制作完整参考图与视频提示词包。
只补齐既定行为的执行细节，不增加剧情或情绪转折。
人物整体、头部、视线、右手与道具分别保留运动；横移、摇摄、转焦分别定时。
逐动作写起止状态、路径、速度变化、接触/支撑/控制权及收束；逐时段写动态构图和可见性。
对白原文、归属、口型和声音起止时间不变。缺少坐标依据使用明确相对描述。
正文保留全部适用细节；超限给完整稿和拆段方案，未知姿态或连续性不猜测。
分别交付正文、附件表、覆盖/空间检查和真实媒体状态。
```

详见 [V5.2 空间合同](video-prompt-compiler/references/history/spatial-contract-v52.md)。原生包升级使用各原生技能内 `scripts/upgrade_spatial.py`，输出新目录中的原件、草案和缺项报告。工作流局部修订增加 `--node-id`、`--track-id`，与既有动作/镜头范围互斥。旧模块锁不会静默更新。

## V5.3 独立编剧接入

新增 screenplay-grammar（中文、国风、一句话故事与剧本、补全润色扩写）。新套件为总工作流加六个专业模块；编剧决定剧情语义，导演负责视听实现。旧项目按原锁继续，显式升级才改用原生 ScriptIR。标准发行在 [dists](dists/)，验收方法与边界见 [验证说明](ai-comic-drama-workflow/references/v5/verification.md)。

## 镜头控制资产 0.1

视频编译器 1.11.0、图片优化器 1.9.0 增加同源调度预览、关键帧请求、编辑差量、事件切点、素材核验、Agnes 模式检查、正文/参数/附件联合编译、按用途失效与返修任务，显式几何 Blender 白模渲染、表演排练卡、分责光色资产、实际 LUT 调色，以及二维媒体观察。使用方法与实装边界见 [镜头控制合同](video-prompt-compiler/references/shot-control.md)。旧项目及 AVIR 版本不迁移，旧 `compile` 输出语义保持；显式使用 `vpc.py control` 启用。

这项镜头控制增量是本地前期工具，包含已实测的几何白模渲染入口；该增量本身没有证明生成模型关键帧、远端视频执行或模型效果。分阶段落实情况见 [实施记录](IMPLEMENTATION-SHOT-CONTROL.md)。
