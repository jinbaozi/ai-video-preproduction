# Compile 语义审阅失败证据（第 1 批）

真实项目：`/private/tmp/ai-video-v6-real-efKlQy/project`。V6 任务 `TASK_ede3a3425d547d3569e53ec4`、批次 1，真实执行者 `/root/host_bridge/v6_42abfe0c85c46ba290a73be2`。`spawn-raw.json` 是 Codex `collaboration.spawn_agent` 的实际返回；`dispatch.json` 与消息包装记录批次、执行身份、输入指纹及候选 RESULT 的内容摘要。`event-excerpt.json` 是从项目原始事件日志按任务和批次摘取的记录，含原日志字节摘要；并非另起执行史。

审阅发现 `AVIR_END_VISIBILITY_CONFLICT`：AVIR 镜头终态 `/shots/0/end_state/4/visible_parts` 为 `["body","prop"]`，同一 AVIR 与源 StoryboardIR 的 12000 ms 时间点均为 `[]`；编译正文同样描述信件已入包、不可见。候选的 `compile_semantics=FAIL`，机位坐标旧问题已闭环；这两个结论分别记录在 `candidate/compile-review.json`。候选 SHA-256 为 `f29d28558a5473de7df24c44dc52bb99b7f4952a5b5f496c73f6256a7320bee9`，原生交接文件及逐项检查证据均在 `candidate/`。

宿主按真实 RESULT 消息提交后，内核将本批标为 `FAILED`，`failure.json` 明确 `failed_check=compile_semantics`；随后生成同任务第 2 批 `DISPATCHING`（项目修订 502），**尚未派发或产生新候选**。当前锁定适配器对终态可见性仍采用静态构图值；本轮没有静默修改已接受 CompilePackage，也没有宣布 QA 或前期交付。`SHA256SUMS` 核对本目录所附字节。
