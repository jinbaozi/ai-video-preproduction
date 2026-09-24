# AVIR 1.2 模型正文投影

完整制作合同仍以 AVIR 1.2 为权威。`production-specification.json` 保存原字段；`artifact.json.detail_blocks` 与 `detail-coverage.json` 保存分维度审计投影。`artifact.json.prompt`、顶层 `prompt.txt` 保存全长正文；项目超过目标单次时长时，这份全长正文只供审计。实际投喂从 `segment-delivery.json` 选逐段文件，不能把审计详稿或超长全片当作单次上传文本。

## 按目标时长交付独立文件

读取当前目标 `registries/capabilities.json.duration_ms`：Seedance 2.0 单次最多 15 秒，Seedance 2.5 单次最多 30 秒；其他目标依各自 profile 的最大值、最小值、允许时长及步长。总片长较短也生成一份独立文件；总片长较长时优先以最大合法时长分段，尾段不足最小时长则调整前段，离散时长无合法分配时返回 `BLOCKED`，未知上限不猜。模型上限不等于用户所选网页或账户已核实的可用时长。

每份 `prompt-序号_起止ms.txt` 从原 AVIR 重新渲染本段，时间从片段 0 秒计；包含涉及本段镜头的真实图片名、引用对象和职责、场景/光线/身份锚点，以及逐时段构图、空间关系、状态变化、每个动作、摄影机操作、运动轨、原生对白与声音。重启的单独生成不依赖上一份文件的隐含上下文。仅在本段完全相同且未变化的状态可省去机械重复；不得以全片 `prompt.txt` 的字符截取、短摘要或仅有 `segment-plan.json` 的计划代替正文。跨段后期声音保留原文与全局时点，并在对应 `post-*.txt` 标明本段局部重叠；它不是模型原生对白。

`segment-delivery.json` 记录每份提示词的项目起止、局部时长、图片职责映射及去重后的实际参考文件清单、文件哈希、独立的 `prompt-coverage-*.json`、状态及阻塞原因。每段逐一检查图片名在正文中、执行字段覆盖、字符预算、参考文件数量和时长。缺少边界关键姿态、动作/表演/运镜/原生声音/运动轨跨切点而没有明确分相时，仍保存完整草案，但文件名加 `BLOCKED-` 且状态为 `BLOCKED`；不猜测中间状态，也不把生成草案宣称为已提交或可拼接视频。`verify` 重新渲染逐段文件以检测缺失或篡改。旧 `segment-plan.json` 保留上游明确接受的片段与连续性计划，不能代替目标专属的逐段交付。

## 正文顺序

1. 片段时长、画幅与当前片段局部时间；相关参考素材按真实文件名、目标和允许/禁止继承职责说明一次。已核验的模型引用标签仍按对应入口规则处理，未知上传槽位保留 `UNRESOLVED`，不得猜测。
2. 涉及当前片段的空间锚点只说明一次。逐镜交代进入该镜头时可见的主体、场景、光线、转换、镜头透视和变化的风格。已离画人物的完整资料留在审计记录，不沿每个状态样本反复写入正文。
3. 镜头内按事件开始时间排列。构图、空间关系、独立叶动作、表演、摄影机操作、附属运动轨与原生声音保留各自时段和对象；同一时刻放在同一时间组，不靠维度目录把同步关系拆散。状态样本只输出首次可见状态和之后明确变化，未变化值仍由制作合同及正文覆盖映射追踪；不据此插值未知姿态。
4. 后期声音在 `post-production.json` 执行；画内后期对白仍在对应时段给出原文与口型视觉指令。画外后期对白不要求画内人物张嘴。硬合同的保持/禁止项只写一次，必须能指向实际正文或明确后期执行渠道。

`compiled-artifact/1.3` 增加 `prompt_coverage`；每行记录来源指针及指纹、正文块、字符范围、片段指纹和转换规则。`prompt-review.json` 固定为 `PENDING_AGENT_REVIEW` 并绑定输入与成稿指纹；它是待复核记录，不是自动批准。校验能发现来源或正文片段被改动，不能证明文字的语义等价、视频实际执行或画面质量。对照原件与成稿的 Agent 复核须另记双方指纹、发现和未决冲突；例如“手机在包内”与“右手持机自拍”同时出现时应报告冲突，不能以字段已覆盖为由判通过。硬要求只在审计附件而未到正文或后期渠道时返回 `BLOCKED`。

## 模型边界

| 后端 | 正文投影 |
|---|---|
| Seedance 2.0/2.5、Veo 3.1 | 参考职责加逐镜/逐时段内容；精确时点是制作意图，非已验证帧级控制。 |
| Kling 3.0/Omni | `Shot N` 与镜头时长、构图、动作、运镜和音画节拍相邻；当前未绑定的网页/API 控件仍只是提示词计划。 |
| Agnes Video 2.5/Flash | 一个 `prompt` 字符串；`mode`、时长、画幅和素材数组仍由已核验参数草案单独表达。 |
| MiniMax H3 | 文本/关键帧模式保留 `integrated_multimodal_description`、`overall_soundscape`、`non_diegetic_music`；全参考模式保留六字段结构。后期音轨不伪装成原生生成。 |

布局以 `templates/backends.json.projection_v12` 为准。依据包括 [Seedance 2.0 官方 15 秒能力](https://seed.bytedance.com/en/blog/seedance-2-0-official-launch)、[Seedance 2.5 官方 30 秒能力与分时示例](https://seed.bytedance.com/en/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5)、[Kling 3.0 Custom Multi-Shot 指南](https://kling.ai/quickstart/klingai-video-3-model-user-guide)、[Agnes Video 2.5 参数与提示词](https://www.agnes-ai.com/zh-Hans/docs/agnes-video-25)、[MiniMax H3 基础模式](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/base-en.txt)和[全参考模式](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/.agents/skills/h3-prompt-writing/references/ref-en.txt)。H3 当前确定性投影保留字段名、顺序和时间链；语言、参考标签与对白标记仍需 Agent 对照官方范例复核，不把静态字段检查称为完整原生格式验收。旧 AVIR 1.0/1.1 输出路径不变；Wan 3.0 与 Runway Gen-4.5 的现有能力阻塞不因正文变短而解除。
