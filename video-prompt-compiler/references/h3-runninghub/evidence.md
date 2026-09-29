# H3 证据、经验与优化边界

核对日期：2026-09-29。官方能力、源码行为、作者经验和本项目推断分开。机器来源索引在 `registries/sources.json`；下述静态核验不包含实际 RunningHub 渲染。

| 来源 / 固定证据 | 可以据此做什么 | 不能据此声称什么 |
|---|---|---|
| [官方 H3 技能](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/SKILL.md)，blob `b6d9b2839384a588763a9c24315225dd8ce19d56` | 按模式加载公开语法，离线由宿主写作 | 本地执行了未开源 Context-IR |
| [官方模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3)及基础/参考指南 | 分开 FL2VA、Ref2VA、音画保留语义 | 每个第三方平台都有全部能力 |
| [原生节点源码](https://github.com/Comfy-Org/ComfyUI/blob/a7169322485d0049380fb207fa17e9fb3ec40486/comfy_extras/nodes_minimax_h3.py)，blob `1ad3c6a4095fdcb756d6222f08ba589452b72091` | 固定帧格、输入名、VAE需求、引用顺序 | RunningHub 当前节点版本相同 |
| [Comfy 原生教程](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native) | 按具体模型/LoRA选工作流与加速路径 | 任意降步或低精度都无损 |
| [RunningHub 官方文档](https://www.runninghub.ai/runninghub-api-doc-en/doc-8287464) | API图、nodeInfoList、seed、上传fileName | 已登录账户、已扣费/已生成 |
| [Context Loop 作者 README](https://github.com/ethanfel/ComfyUI-MiniMaxH3-Context-Loop/blob/main/README.md)，blob `4e3a0bb7a95cec91d245ccf68b62225408dff347` | 分场复用采样、Review Gate、保存take、断点恢复、延后超分 | 官方 Context-IR 或平台默认自带插件 |

## 从控制变量出发优化

先使用已跑通的工作流：保存原始提示词、模型/LoRA版本、节点版本、分辨率、帧数、种子和采样设置。一次只改变提示词的一组内容或一个执行参数；同时记录时延和可见缺陷。固定种子只是比较条件之一，不保证跨GPU/精度/版本结果完全一致。

构图与身份不稳，先检查参考职责、裁剪、参考尺寸和实际消费连接；动作不连贯，先减少同一短片的动作冲突、检查接触和末态；转焦不明显，先让两焦点主体同时具备可见深度关系；口型不符，先确认说话者、语言、时间预算、音频VAE及伴随音轨编号。不能把所有问题都归因于提示词不够长。

## 官方工作流经验：按前提使用

原生教程的普通示例以20步为基线，并有针对运动质量的25步建议；8步 FL Turbo 与4步 Ref Turbo 分别依赖匹配的具体 LoRA/工作流。它们不是同一份权重改 `steps` 即可获得的无损方案。本适配器保留原值，仅输出显式比较实验，不自动套用。

参考尺寸 `match` 与生成画布匹配，`max` 可保留更大参考输入；身份细节与计算成本可能权衡，先固定输入做 A/B。基础画布受32倍数及像素预算约束，Regenerate/超分是另一个阶段，不把提高宽高当成免费细节恢复。

SageAttention、量化、offload 和并行方案先查目标GPU、算子、节点及权重兼容性。教程或个人 Mac 的耗时不等于 RunningHub 的时延；只有实测日志才能区分加载、编码、采样、VAE、排队和后处理瓶颈。

## 社区扩展：只在需要时加载

Context Loop 作者描述了按场复用采样图、Review Gate 重试/接受、保存候选与断点恢复、后续总装和延迟超分；将 vocals 用于口型而 full mix 用于最终声音，属于具体节点包的机制，不是通用 H3 参数。

长片或跨场连续性任务可按作者文档评估 Context Loop + Motion Context MultiRef。先确认 RunningHub 是否有相同版本和依赖，再备份工作流与项目；不自动 git clone、不开启重排队、不修改循环边界。`delete_checkpoints_after_assembly` 会影响恢复和再次超分，默认保留关闭。额外节点和人工 Review Gate 不能在无人值守执行中被假定自动通过。

这些经验采用“来源+前提+可选实验”的方式沉淀，不扩成每次必跑的七层子工作流。单条提示词只读模式指南；真正遇到相关问题才读取本页。
