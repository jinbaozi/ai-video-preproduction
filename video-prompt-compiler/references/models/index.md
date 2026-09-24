# 模型参考索引

先运行`profiles`读取`registries/capabilities.json`，只读选中模型参考。
能力快照2026-09-19；正文布局依据2026-09-24核对的目标文档，详见[正文投影](../model-prompt-projection.md)。限制注明model或entrypoint范围。账户、地区、入口可用性与实际生成均未验证。

| 精确目标ID | 文档 | 已实现 |
|---|---|---|
| seedance2.0 / seedance2.5 | [Seedance](seedance.md) | 专属提示词计划、时间预算、引用职责；API载荷未核验 |
| agnes-video-2.5 / agnes-video-2.5-flash | [Agnes](agnes.md) | 参数提升、槽位编号、模式/数量/时长、载荷草案 |
| kling-v3 / kling-v3-omni | [Kling](kling.md) | 分镜与音画提示词计划，版本区分；当前渠道槽位未绑定 |
| minimax-h3 / veo3.1 | [扩展模型](extensions.md) | 结构化上下文/音画提示词计划和已核验模型时长检查 |
| wan3.0 / runway-gen4.5 | [扩展模型](extensions.md) | 待核验适配候选，输出草案但状态BLOCKED |

`COMPILED`不是“已实现所有厂商API”。相同AVIR产生不同能力检查、逐镜正文布局及参数映射；不能因为版本更高就自动迁移。H3 的原生字段布局不套用其他模型的标题写法。
时长超限返回错误。Agent若需分段，先对齐故事节拍、对白、起末态，修订为独立合同；本版不自动拆镜或拉伸时间。
