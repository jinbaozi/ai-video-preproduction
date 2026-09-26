# Canon 直达沟通摘录

以下是本次 Codex 会话中影响 Canon 候选或审阅范围的直达消息原文摘录。任务 ID 为 `TASK_0e0c8a4ca94c8ffdbb7e14ae`；creator 为 `/root/host_bridge/v6_98512993c68d19b0338077b6`，reviewer 为 `/root/host_bridge/v6_e184a8b19af38523257bb812`。这些消息产生于候选/审阅接受前，但当时的内核消息入口只允许执行者为发送者，宿主回复没有在接受前登记。此文件保留可检查的文字与归档哈希，不能当作当时已入内核事件日志的消息。

## 宿主发给 creator 的返修

> 请修订你自己的 Canon 候选（当前尚未登记 RESULT）：1) candidate-result.json 的 handoffs[0] 按冻结 V6 envelope.handoffs 补齐 source_slot 等每个必填字段，逐字段保持原样；2) role-result.json 的 artifact 改成当前候选目录 canon.json 的绝对路径，以便 V5.submit 从任意 cwd 能读取；3) 重新计算 role-result.json SHA-256 并同步 candidate 中相应 result_sha / artifact 哈希，如受影响；4) 用当前仓库 V6 candidate 与 V5 RoleResult schema 和 Canon 校验器复验，回复修订文件路径、哈希及结果。请保留旧候选快照或清楚记录修订历史；不要伪造任何执行或审阅证据。你不是唯一在代码库工作的人，不要覆盖他人的改动。

> 补充：我看到 role-result.json 的 handoff[0] 同样缺 source_slot。请按冻结 envelope.handoffs 为 candidate.handoffs 与 RoleResult.handoff 两处都补齐，保证 V5/V6 交接映射一致，并重新计算 result_sha256。

creator 的修订前后字节见 `candidate-result.v1.json`、`role-result.v1.json` 与当前无 `.v1` 后缀文件。其最终回复报告 candidate SHA-256 `a65393aa6125cd9ce984a61fcf07e087059e914e165df8f3e8b5728f0687d3a7`、RoleResult SHA-256 `a53bbb9a8273a3faaaf033b4bc8d61a4257b21ac2957f271ae2247cba6517d3d`；宿主随后重新检查并登记 RESULT。

## 宿主发给 reviewer 的审阅说明

> 请在审阅开始时回复一条简短 ACK：确认已读取冻结 envelope、候选与审阅职责，并列出正在检查的项目；我会把你的真实 ACK 登记为 agent-message。

> 请每项 review check 指向你自己在 review_dir 下写的审阅证据文件，记录实际复查方法与发现；不要只重用创作者声明的证据路径。review.candidate_digest 用当前已登记 candidate 对象的 v6_protocol.candidate_digest 计算，reviewer_dispatch_id 用冻结 review receipt。

审阅者的 ACK 与 RESULT 已登记在 `canon-review-ack.json`、`canon-review-result-message.json`，实际三项独立证据见 `review-evidence/`。
