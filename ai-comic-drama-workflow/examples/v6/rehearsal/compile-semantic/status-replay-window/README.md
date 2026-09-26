# Compile 语义复核：状态重放窗口

真实演练项目：`/private/tmp/ai-video-v6-real-efKlQy/project`（`LETTER_DEMO`）。本目录保留 V6 `compile_review` 任务 `TASK_6cac2b25585760d16bce096d` 第 1 批的真实宿主与候选证据，以及紧接着出现的重复派发动作。这里的文件是修订 857 时从项目运行记录和宿主原始输出摘取的快照。

上游 Compile 在修订 844 被接受；本任务于 845 创建、846 READY、847 DISPATCHING、848 RUNNING。`dispatch/action.json` 是内核在修订 847 返回的待执行动作。真实 `collaboration.spawn_agent` 返回 `/root/host_bridge/v6_af960c7614b2f0ebf91c02d9`，见 `dispatch/spawn-raw.json`；登记命令和按 SHA-256 保存的工具返回分别见 `dispatch/receipt-command.json` 与 `dispatch/host-tool-result.json`。`messages/` 保留 ACK、PROGRESS、RESULT 的原始文本及结构化内核消息。任务在 852 提交结果、853 验证、**854 ACCEPTED**；完成门的 `module_receipt` 和 `compile_semantics` 均为 `PASS`，详见 `event-excerpt.json`。

候选 `candidate/candidate-result.json` SHA-256 为 `aa56dabbf7ea1a5c26364aa00c194585c6a52670a88d0edbb50bbd1c87eb61fa`；原生 `role-result.json` 为 `49cf83cea2b906a7b92c7e5ab5de134d8d30484e3549e66fe0129996484a1c0c`；`compile-review.json` 为 `39918409ba98e131b8befbbee30613188c976190f7eacfc968feaefd88919fab`。候选逐条检查 17 项硬要求，记录旧 `AVIR_END_VISIBILITY_CONFLICT` 在当前静态编译包中关闭。候选内记录的 build ID 为 `1f2df827a47bf738eadadf0799b46fe347c1b64947fb2f5eb81847aec9423ef0`；`media_qa=NOT_RUN`、`submitted=false`、`runnable=false`、`transport=unresolved`，没有生成或验证模型媒体。

**异常窗口：**内核在接受后又于 855 创建同一节点的 `TASK_b093572942cdfdfa08f184e7`，856 READY、857 DISPATCHING，并返回 `duplicate/action.json`。该动作**没有调用 `collaboration.spawn_agent`**；修订 857 的 `state-at-rev857.json` 中，其 `receipt=null`、`candidate=null`。因此本目录只记录重复派发请求，不把它算作已派发或已执行。原始事件的修订与哈希链字段均保存在 `event-excerpt.json`；完整事件文件继续追加时，其整体摘要会变化。

`frozen-file-inventory.json` 对照任务信封逐一核实 3 个冻结输入及 21 个锁定资源的实际字节数和 SHA-256。目录复制了冻结任务本身；其他大文件仅登记本地项目相对路径与摘要。`SHA256SUMS` 校验本目录实际保留的文件。
