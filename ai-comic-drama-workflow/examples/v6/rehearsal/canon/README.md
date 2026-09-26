# Canon 真实宿主演练

原始输入见 `source.txt`。临时运行项目为 `/private/tmp/ai-video-v6-real-efKlQy/project`，任务 ID 为 `TASK_0e0c8a4ca94c8ffdbb7e14ae`。本目录是从该项目和本次 Codex 会话提取的小型审计样本；项目里的完整事务日志、锁定模块和正式 V5 产物仍在临时项目中。

`creator-action.json` 与 `reviewer-action.json` 分别来自两次真实 `run` 输出的 `actions[0]`。宿主先查 `collaboration.list_agents`，随后实际调用两次 `collaboration.spawn_agent`；原样返回对象保存在 `spawn-canon.json`、`spawn-canon-review.json`，内容寻址的内核登记副本为 `creator-host-proof.json`、`reviewer-host-proof.json`。两位真实智能体 ID 分别是 `/root/host_bridge/v6_98512993c68d19b0338077b6` 和 `/root/host_bridge/v6_e184a8b19af38523257bb812`。

`canon-event.json` 与 `canon-review-event.json` 是由实际工具返回构建的 CLI 回执包装。`canon-ack.json`、`canon-result-message.json`、`canon-review-ack.json`、`canon-review-result-message.json` 是宿主把智能体在本次会话发出的 ACK / RESULT 登记为结构化消息的包装。`canon-submit.json` 和 `canon-review-submit.json` 是候选与审阅提交包装；对应的实际候选、RoleResult、Canon、审阅记录及逐项证据也在本目录。所有包装都绑定当时的项目 revision、任务、批次与真实 agent ID；`event-excerpt.json` 保留修订 8–17 的内核事件摘录。

创作者第一次候选缺少 `handoff.source_slot`，且 RoleResult 使用相对产物路径。原智能体修订后，旧字节留在 `candidate-result.v1.json`、`role-result.v1.json`，修订后字节在无 `.v1` 后缀文件。宿主没有代写创作者的候选。修订后的候选通过 V6/V5 Schema、文件哈希与交接覆盖检查；审阅者独立提交三项 PASS 和自己的证据。内核在修订 17 将 Canon 转成 `ACCEPTED`，随后 V5 `canon.complete=true`，并进入 screenplay 任务。

返修与审阅范围的直接沟通摘录保存在 `direct-communication.md`。这些宿主发出的消息没有在 Canon 终态前进入内核消息日志，因此该摘录是会话证据补充，不能冒充协议内消息；后续 screenplay 的此类沟通改由带原文 SHA 的 `agent-message/6.0` 登记。

本目录的 `SHA256SUMS` 列出归档文件字节哈希。它证明这些归档文件之间的可核对关系；实际工具调用由本次 Codex 会话和临时项目中的原始宿主证据共同证明，单独复制这些 JSON 不等于重新执行智能体。共享文件系统候选目录也不是操作系统级隔离。
