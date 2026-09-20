# 调研来源与实现映射

用户提供的[完整调研报告](research/deep-research-report.md)已保存原样副本，SHA-256登记在`registries/sources.json`。
先前引用聊天只返回研究启动回复；随后用户补充本地报告，现已阅读全文。报告内部turn引用不是本包可解析的来源链接。
本次对核心厂商和开源设计重新访问一手来源，URL、核验时间与结论范围在sources.json。

| 报告建议 | 当前Skill落地 |
|---|---|
| 意图→AST→typed AVIR | Agent语义前端＋严格AVIR schema；不假装有独立通用语言解析服务 |
| Core/RefGraph/Temporal/Expanded/Compact | 来源、引用角色、镜头事件、可见扩写候选、镜头Context投影 |
| 确定性规则优先 | 无LLM/无网络编译器、稳定rule ID、scope与模板数据 |
| 四个首批模型 | Seedance2.0/2.5、Agnes2.5、Kling3/Omni专属profile与lowering；能力层级明确 |
| 至少两扩展模型 | H3和Veo3.1提示词计划；Wan/Runway有明确BLOCKED候选 |
| 参考为一等对象 | 文件名/ID/hash/职责/禁止职责/镜头/目标/槽位；Agnes真实数组映射 |
| 有源硬约束与解释 | 制作合同、字段断言、trace、覆盖、loss、post路径 |
| 版本与重放 | 全运行构建哈希、输入/产物/来源/模板快照、verify与replay |
| token预算 | 实际CPT-v1计数；原生token未知保留null；不截断硬要求 |
| Context故障降级 | optional未配置返回warning并用完整Core规则路径 |
| RAG/LLM/DSPy/SFT | 按来源ID选择资料及可执行规则；复杂检索、模型训练为宿主扩展流程，未运行 |
| batch/async | 本地NDJSON逐项批编译已实现；异步视频生成队列为宿主工作 |
| REST/gRPC/UI/RBAC/多地域 | 属报告的平台化阶段，未为本次Skill创建空服务或占位工程 |
| VBench/人工A/B/成本延迟 | 给出媒体验收执行合同；没有伪造生成质量、费用或SLA数据 |

本版侧重完成可用Skill和本地编译闭环，报告的SaaS平台与多月生产化路线保留为扩展边界。
不直接使用社区项目代码或模型权重，因此不声明继承其能力、许可证覆盖或评测效果。

## 本次补充的一手研究

- [MiniMax H3模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3)：分层上下文处理、托管IR与Base的边界。
- [OpenH3-IR项目](https://github.com/ruashots/open-h3-ir)：借鉴本地校验与分层产物；不采用其对欠指定需求默认扩写的行为。
- [DSPy](https://github.com/stanfordnlp/dspy)：借鉴离线模板优化，下游评价优先，不强迫每次编译调用优化器。
- [VBench](https://github.com/Vchitect/VBench)：真实视频之后做多维评测，不把静态prompt长度当质量分数。
- Seedance、Agnes、Kling与Veo具体来源在[模型索引](models/index.md)按需读取。

对报告举例的Agnes `duration`做了明确修正：本包实际API字段是官方`seconds`字符串。
当前官方完整2.5与Flash的附件限制分开保存，没有沿用社区仓库中8/5图片及1/3视频的混淆值。
