# 七技能套装 V5.3

七个入口各自可用，总工作流另外携带六个专业模块的锁定包。`hypit-ai`保持原状，实际视频生成与剪辑不在本套装终点内。

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

完整调用：

```text
使用 $ai-comic-drama-workflow，按这份资料制作完整前期包，目标入口 Agnes Video 2.5。
复用已有有效内容，当前 Agent 顺序执行；保留来源、对白与实体ID。
交付实际参考图、分镜、可复制视频提示词、附件表和验收记录。
```

独立成果接续：新项目沿用原生包project_id，再用`import-artifact`或`import-compiled`导入。run给出的复核任务核对来源和锁定项，原包可以直接复用。总包内置模块与独立发行包是同一构建结果，项目不会被全局安装升级静默改变。

旧项目：`ai-comic-drama copy-project OLD --destination NEW`。原件逐字节保留；报告列出ID、真实图片、原决定证据和待复核项。确认图片仍适用后重新登记其用途，不默认重生成。

[工作流用法](ai-comic-drama-workflow/README.md) · [完整接口](ai-comic-drama-workflow/references/v5/runtime.md) · [迁移清单](ai-comic-drama-workflow/references/v5/retirement.md) · [验收边界](ai-comic-drama-workflow/references/v5/verification.md)

发行目录为[dists](dists/)，包含7个`.skill`、各自的manifest与SHA-256，以及suite-manifest。安装时选择需要的入口即可；总工作流无需安装相邻专业目录。活动技能默认发现保持启用；新增独立编剧入口。


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

有视频来源的新项目在资料阶段返回 `NEEDS_REFERENCE_OBSERVATION`。用锁定模块自带助手提帧，实际查看后生成 review.json，然后 `ai-comic-drama import-observation PROJECT OBSERVATION_DIR` 登记。登记只证明所列范围有观察记录，未观看范围及未听审声音仍是未验证。

详见各包自带 [V5.1 细节合同](video-prompt-compiler/references/detail-contract-v51.md)。老项目不自动升级模块锁；旧协议读取、原版本重放和新标准达成是三种不同状态。当前结构性检查不能替代语义复核和真实媒体验收。

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

详见 [V5.2 空间合同](video-prompt-compiler/references/spatial-contract-v52.md)。原生包升级使用各原生技能内 `scripts/upgrade_spatial.py`，输出新目录中的原件、草案和缺项报告。工作流局部修订增加 `--node-id`、`--track-id`，与既有动作/镜头范围互斥。旧模块锁不会静默更新。

## V5.3 独立编剧接入

新增 screenplay-grammar（中文、国风、一句话故事与剧本、补全润色扩写）。新套件为总工作流加六个专业模块；编剧决定剧情语义，导演负责视听实现。旧项目按原锁继续，显式升级才改用原生 ScriptIR。标准发行在 [dists](dists/)，验收方法与边界见 [验证说明](ai-comic-drama-workflow/references/v5/verification.md)。
