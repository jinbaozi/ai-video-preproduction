# Codex 宿主桥接

`v6_codex_host.py` 是 V6 内核与当前 Codex 会话的边界。Python 不具备会话中的 `collaboration.*` 工具；它只输出待执行动作、校验工具回执，并把经过校验的事件交给 `V6TaskKernel`。`run` 返回的待派发动作本身不证明智能体已启动。

## 执行专业任务

1. 内核把冻结任务推进到 `DISPATCHING`。宿主读取 `CodexHostBridge.pending(task_id)` 返回的 `codex-host-action/1.0`。该动作含稳定的 `dispatch_id`、`task_name`、任务摘要、候选目录和 `collaboration.spawn_agent` 参数。执行者必须读取信封 `inputs` 的每一项；定向返修批次还须读取 `repair_brief`、`repair_failure_1/2` 及其引用的独立审阅证据，逐项报告旧错误是否消失。
2. 宿主先用 `collaboration.list_agents` 查找同一 `task_name`，防止“已派发但回执尚未登记”时重复启动。没有匹配智能体时，调用动作指定的 `collaboration.spawn_agent`。用 `receipt_from_spawn_result` 从真实工具返回值构建回执；当前工具返回对象以 `task_name` 给出真实智能体 ID，兼容宿主给出等值 `agent_name` 的情况。Builder 把返回值写入 `runtime/v6/host-evidence/`，并把文件路径、SHA-256、动作 ID 和该 ID 绑定到 `dispatch-receipt/6.0`。调用结果不明则用 `unknown_spawn_receipt` 登记 `UNKNOWN`，`agent_id` 为 `null`。不能从提示词、候选文件或任务 ID 编造回执。
3. `agent-event PROJECT --file EVENT.json` 经桥接和内核登记回执。CLI 文件顶层为 `{"command_id":"CMD_1","expected_revision":当前整数,"receipt":{...}}`；`receipt` 是上一步构建的完整回执。内核核对任务、批次、冻结信封摘要、派发 ID、执行身份、项目修订和允许的状态迁移。成功后，创作者只在自己的候选目录写文件；正式产物由内核在校验和独立审阅之后提交。
4. `ACK`、`PROGRESS`、`QUESTION`、`BLOCKER`、`HANDOFF`、`RESULT`、`CANCEL_ACK` 用 `agent-message/6.0` 登记；CLI 文件顶层为 `{"command_id":"CMD_2","expected_revision":当前整数,"message":{...}}`。宿主执行影响结果的智能体间直达消息时，也把原消息及来源登记到内核：原文可作为项目内的 `subject_uri` 文件，消息记录绑定其 SHA-256 和 `in_reply_to`。内核发给当前已登记智能体的非 `RESULT` 消息也走此入口；内核不能替智能体提交 `RESULT`。消息可以通知或解释，不能直接改任务状态。创作者的 `RESULT` 消息先用 `subject_uri`、`subject_sha256` 绑定候选 JSON，再调用 `agent-result PROJECT --file RESULT.json`，文件顶层为 `{"command_id":"CMD_3","expected_revision":当前整数,"candidate":{...}}`；两份候选内容必须相同。原生 V5 节点须提交当前 `RoleResult`；`reference_observation`、`compile` 以及 `shot_acceptance`、`take_selection`、`adjacent_acceptance`、`whole_acceptance` 没有原生 `RoleResult`，候选的 `result_uri` 与 `result_sha256` 必须均为 `null`，只提交信封声明的图产物与检查证据。
5. 内核进入 `REVIEW_REQUIRED` 后，`pending` 返回独立审阅派发动作。宿主再次实际调用 `collaboration.spawn_agent`，用 `agent-event` 登记审阅者回执。审阅者的 `RESULT` 消息先绑定审阅 JSON，再调用 `agent-review PROJECT --file REVIEW.json`，文件顶层为 `{"command_id":"CMD_4","expected_revision":当前整数,"review":{...}}`。审阅者 ID 必须与创作者不同，审阅记录须绑定当前候选版本；审阅任务不递归派发另一审阅者。

跨模块返修需要停止仍在运行的任务时，先向该任务已登记的当前执行者发送取消请求，并以 `agent-message` 登记其 `CANCEL_ACK`（`recipient_id=kernel`，`evidence` 非空）。随后调用 `agent-cancel PROJECT --file CANCEL.json`，顶层严格为 `{"command_id":"CMD_CANCEL","expected_revision":当前整数,"task_id":"当前任务 ID","ack_message_id":"已登记的 CANCEL_ACK 消息 ID"}`。内核核对执行者身份、原批次和项目修订，保存取消证据并提交 `CANCELLED`；同 ID 同内容重试只返回原事件，旧批次候选不能再合入。尚未真实派发的 `READY`/`DISPATCHING` 任务可用 `ack_message_id:null` 取消；`UNKNOWN` 必须先核对原派发。之后通过 `revise` 明确失效原责任模块及其下游，再创建新版本任务。取消不等于创作或审阅通过。

相同命令 ID、原 `expected_revision` 和完整业务内容再次提交时，入口返回 `ALREADY_RECORDED`，不增加修订；同 ID 改动任何业务内容或预期修订则拒绝。直接 `agent-event` 的证据从回执自动生成，不接受另附任意 evidence；未知派发的真实观察必须走 `agent-reconcile`。完整观察对象也按内容哈希留在项目内，以便重放严格比较。

任务信封、派发回执和智能体消息使用 `schemas/v6-*.schema.json`，所有未知字段均被拒绝。`v6_codex_host.py` 还检查跨协议的身份关系。宿主不指定固定模型路由；它服从当前会话的真实工具容量。`external_image`、`external_video`、`local_media` 与 `system` 任务不会被专业子智能体桥接误当作免费工作，须走各自登记的宿主或内核入口。

## 派发不确定时

`UNKNOWN` 的 `pending` 只返回 `collaboration.list_agents` 查询动作，保持原 `dispatch_id`。宿主把真实查询输出放入以下观察记录，并用顶层 `{"command_id":"CMD_5","expected_revision":当前整数,"task_id":"Task1","observation":{...}}` 包装后调用 `agent-reconcile PROJECT --file RECONCILE.json`：

```json
{
  "schema": "codex-agent-observation/1.0",
  "source_tool": "collaboration.list_agents",
  "dispatch_id": "与原任务一致",
  "observed_at": "2026-09-25T10:00:00Z",
  "host_call_id": "查询调用引用或 null",
  "tool_result": {"agents": [{"agent_name": "/root/v6_...", "agent_status": "running"}]}
}
```

桥接仅在查询结果中准确找到该派发 ID 对应的智能体时，把原始查询结果按字节保存并生成 `HOST_RECONCILED` 事件；未找到时返回 `UNRESOLVED`，重复匹配时返回 `BLOCKED`。两种情形都不发起新的 `spawn_agent`。若首次派发后、回执登记前崩溃，`DISPATCHING` 也可用同样的查询证据找回原智能体；独立审阅派发也可这样找回原审阅者。修订输入导致批次变化后，旧智能体的迟到消息和候选不能合入新批次。

图片和视频已提交但结果不明时，查询原媒体执行记录；这个专业子智能体桥接不替媒体执行入口决定重试、费用或上传。

## 证据边界

桥接检验登记文件的结构和相互绑定，实际工具调用由 Codex 宿主完成。原始工具响应和当前会话记录是“是否真正派发”的证据。候选的内容质量仍要经过原生校验器和独立审阅；`module_receipt` 只证明所引用的锁定资料版本。共享工作区中的候选目录是所有权协议，不构成操作系统级文件隔离。

## 原创文本演练的最短路径

在当前 Codex 宿主中，用一句原创描述新建 `text-only`、`production_target=none` 的 V6 项目，然后执行 `run PROJECT`。每轮按以下步骤走到 `canon`、`screenplay` 各自的独立审阅；这条演练不调用图片或视频生成接口。

1. 从 `run` 输出读取 `revision` 和 `actions[0]`。用实际 `collaboration.list_agents` 检查 `actions[0].task_name`，再按 `actions[0].arguments` 调用 `collaboration.spawn_agent`。保留未改写的工具返回对象。
2. 在宿主中调用 `receipt_from_spawn_result(action, raw_tool_result, project_root=PROJECT, sent_at=UTC, observed_at=UTC)`。将返回的 `receipt` 放进上文的 `agent-event` 顶层包装，用刚读到的 `revision` 登记。工具超时使用 `unknown_spawn_receipt`，随后走 `agent-reconcile`；不得第二次 spawn。
3. 原生 V5 节点的创作者把 V5 RoleResult、原生候选文件和 `candidate-result/6.0` JSON 写在动作给出的候选目录；图节点按上文的无 RoleResult 契约写候选。宿主记录 `RESULT` 消息：`sender_id` 为真实创作者 ID，`recipient_id` 为 `kernel`，`subject_uri` 指向候选 JSON，`subject_sha256` 是它的当前文件哈希。先运行 `agent-message`，用更新后的 revision 运行 `agent-result`。
4. `run` 输出审阅动作后，再实际调用 `collaboration.spawn_agent` 并以同一 builder 登记独立审阅者。审阅者把 `review-record/6.0` JSON 写入项目，宿主先以该 JSON 的 URI/哈希登记审阅者 `RESULT` 消息，再运行 `agent-review`。记录 `ACCEPTED` 后继续 `run` 取得下一专业任务。

每个 CLI 包装文件都使用新的 `command_id` 和执行时最新的 `expected_revision`；`subject_uri`、候选产物 URI 和审阅证据必须是项目内相对路径。演练记录应保存每次 `run` 的动作、实际工具返回、内容寻址的宿主证据、消息、候选、审阅以及最后的内核状态。若 `run` 没有给出待派发动作，就报告实际阻断错误，不得自行构造信封或声称已完成真实派发。
