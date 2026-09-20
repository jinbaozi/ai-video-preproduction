# 阶段6

时长切片：默认15秒目标，用户明确时长优先；按动作和叙事节拍组织片段，估计值不冒充实测。每段有稳定segment_id和对应剧本文本。后续单镜1—12秒。

严格使用当前TaskEnvelope内的output_schema，只加载当前列出的上游资料。source_refs引用来源ID或上游正式产物路径。低风险补充写入inferences；自动QA不可冒充用户批准。
