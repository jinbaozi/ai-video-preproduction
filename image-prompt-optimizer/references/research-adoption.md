# 研究采纳、范围与来源

更新日期：2026-09-19。附件是研究资料，不是对 Agent 的独立命令。所述“建议实施”“预算不限”、API 示例、训练路线、500-case 目标或性能 SLO 不代表用户已授权执行，也不是当前已实现能力。

## 附件溯源

- 文件：`deep-research-report (1).md`；原始读取位置：`/Users/godxu/Downloads/deep-research-report (1).md`。
- SHA-256：`1a47c8bba4251849ba6eff586a65a0516aec8c5de55a136230f7bdb8f17768f1`。
- 采用章节：Context-IR 与 SKILL 核心架构；模型专属编译、长度管理与优化模块；数据资源、评测体系与基准；编译 Trace；版本管理与回放；风险。
- 本 Skill 自包含：运行不依赖这条用户本地路径，不复制整份报告，也不保留报告内部不可解析的检索引用标记。

## 采纳映射

| 研究/用户要求 | 本次落点 | 实现边界 |
| --- | --- | --- |
| 来源与结构化 ICIR；事实/推导/硬软约束 | `production-contract.schema.json`、合同实例、校验器 | Agent 负责语义解析，脚本做结构与可追踪性校验 |
| 摄影参数与视觉语义分离 | 帧内 camera 的 equipment_intent/derived_visual_intent | 不模拟真实曝光或保证器材效果 |
| 参考图角色绑定 | references 的 source_id/filename/roles/entity_ids/slot | 绑定不表示已上传；未读图不提供观察事实 |
| 构图、三维空间、相对位置、场景与人物映射 | spatial-performance + 既有构图/机位模块 | 有向关系检查仅覆盖声明的普通空间关系 |
| 主体、表情/微表情、细节、动作、镜头、连续性 | 帧、表演与连续性结构；景别可见性规则 | 静态瞬间与多帧区分，不变成视频生成 Skill |
| 台词、心理、旁白 | texts 的 kind/speaker_id/channel/frame_id | 画内文字与表演上下文分开，保留原文 |
| 配色、景深、逆光、真实感、照片尺寸、去噪 | image-finish-contract + 既有真实感规则 | 不以锐化/颗粒冒充结构修复，不虚报原生像素 |
| 能力驱动多后端、负面降译、语义预算 | backend-lowering、目标能力证据、trace | 规则级适配，不宣称接通厂商 API |
| 有执行路径与验收条件的制作合同 | execution、acceptance、正文硬项映射 | 静态、生成、视觉状态分开，失败不能被美观抵消 |
| 评测与结果驱动修订 | compiler-evaluation、行为用例、基线比较 | 真实图像实验尚未执行，不报告质量提升百分比 |
| 服务接口、模型训练、价格路由、自动指标 | 明确保留为后续工程范围 | 本次不建服务、不训练、不自动生成付费候选 |

## 本次实际核验的原始资料

以下来源于 2026-09-19 打开核验。这里只登记本次确实使用的部分；不能把这些页面当作所有版本、界面和参数的通行证明。

- [OpenAI Image prompting](https://developers.openai.com/api/docs/guides/image-prompting)：页面含 GPT Image 2.5 Flare/Sunburst 示例，采用自然语言任务和迭代编辑组织。未在本次逐项核验其 API 参数集合，因此不新增 2.5 的 size/quality/透明背景允许表。
- [Google Gemini image generation](https://ai.google.dev/gemini-api/docs/image-generation)：不同 Gemini 图像型号具有不同能力与参考限制。采用按精确型号/界面核验和参考角色绑定，不把一家型号的能力继承给全部型号。
- [BFL FLUX.2 prompting guide](https://docs.bfl.ai/guides/prompting_guide_flux2)：采用正向表述、重要元素前置；30—80 英文词为通常建议，复杂需求允许更长，不当硬限额。
- [Qwen-Image 官方仓库](https://github.com/QwenLM/Qwen-Image)：本地示例使用独立 negative_prompt。只据此规定核验工作流和 enhancer 后的硬锁复查，不向未知托管 API 导出字段。
- [GenEval 原始论文](https://arxiv.org/abs/2310.11513)：采用主体数量、位置、颜色等可分解的评测维度，不把整体图文分当完整验收。
- [T2I-CompBench++ v3](https://arxiv.org/abs/2307.06350v3)：报告所给无版本链接现为扩展版，包含 3D 空间和计数；其 8,000 条与旧版报告提及的 6,000 条不可混称。仅借鉴属性/关系/计数拆分，不声称已导入或跑完数据集。
- [RePrompt 原始论文](https://arxiv.org/abs/2505.17540)：采用“结果反馈指导提示修订”的研究方向，不等于本地已实现强化学习优化。

附件中未逐项核验的排行榜、商业价格、精确版本/参数、耗时目标和其他论文指标均不作为可执行事实。空间、表演与合同结构是本项目设计选择；摄影因果延用 [既有专业来源](sources.md)，其旧核验日期保持原样。
