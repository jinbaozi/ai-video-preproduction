# Codex 原生生图执行桥（仅有 media_job 时加载）

Python 不提供原生工具 API。读取当前 TaskEnvelope.media_job；一次执行一个候选，遵守当前宿主 Imagegen Skill。
先检查真实工具是否可调用。不可用时提出补充能力、导入已有图片或明确草稿范围；不自动改用 CLI/API/其他模型。
先检查 allowed_providers；只有 provided 时仅接收用户提供的图片，不能调用生图工具，也不计入原生生图调用预算。
本地参考图先查看。实际把 reference_bindings 对应文件传给工具，按当前契约使用一种引用机制，不混用互斥参数。
只用工具真实返回的数据：不得猜测模型名、种子、费用、输出路径控制或参数。返回路径必须是真实文件。
返回标准 AgentResult，artifact 包含 job_id、input_hash、output_path、sha256、provider（codex-imagegen 或 provided）、call_evidence 和实际 reference_bindings。
Kernel 导入文件后检查文件完整性，随后仍需用户审核。文件可读不代表画面质量通过。
provided 结果的参考绑定是用户导入声明，不是已发生的生图调用证据；必须检查成图与当前角色、时点和空间一致后交给用户审核。
响应不确定时返回 needs_decision，不重试。技术失败最多三次重试且不超过批准的调用数量与额度；创意返修独立记录。
故事板必须实际引用已批准身份图和空间关键帧；只描述 job 对应时刻，不把全镜动作堆进一个静帧。
