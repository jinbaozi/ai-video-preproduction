# 最终状态修复后的 Control 真实重派证据

本目录为 `/private/tmp/ai-video-v6-real-efKlQy/project` 中 V6 Control 任务 `TASK_4064ef49778d32687a4dde42` 批次 1 的**精选归档**。归档从真实宿主动作、消息、候选、独立审阅和内核事件复制；没有补写不存在的执行。完整候选文件保留在原演练项目，未归档的文件列在 `candidate/omitted-file-digests.json`，各项均含原始字节数和 SHA-256。

- 内核在修订 786 返回冻结派发动作；`host/frozen-control-envelope.json` 固定了 StoryboardIR 输入版本、摘要、模块资源、检查器和预期产物。创作者 `/root/host_bridge/v6_b590c0f743ce11e72a9acb77` 的真实 `collaboration.spawn_agent` 返回值、规范化工具结果和内核派发收据分别保留。规范化结果 SHA-256 为 `f762d50fcc02469582a4714a3c2173196375b7758f02e9eb2ce6117fdd90a131`。
- 创作者 ACK、PROGRESS、RESULT 均通过 `agent-message` 写入修订 788–790。候选清单 `candidate/candidate-result.json` SHA-256 为 `19816a403411dbefea4cea22285670e5b894951b6e5417fce347af3cf306b203`，绑定输入摘要 `7461f42f3571339e42cc024f60f6d153909379d748e9d6c36c01df350207c62a`、RoleResult 摘要 `9cf417f7bd338511638b684a6da2d43e76d556cec308b6387e5ebb89e21d20d5` 和 Control 包 manifest 摘要 `26f1b001fc5bef1454b97040e4ff4625c104a236881fc7ddd2642f6140eebd16`。`module_receipt`、`control_verify`、`handoff` 三项候选检查均为 `PASS`。
- 独立审阅者 `/root/host_bridge/v6_57cc07d2f6dd6d2c0c01c6e5` 的真实派发、ACK、两次 PROGRESS、RESULT 与审阅记录均已归档。审阅记录 SHA-256 为 `487061af5d96d95e84425304de8cd90abc7ce66c9ed695b40ce0b3f75cd20070`；三项逐项审阅均为 `PASS`，审阅者与创作者不同。
- 内核事件修订 **799** 将本 Control 任务转为 `ACCEPTED`。同一次审阅提交触发后继图调度，到修订 **830** 返回 `V6_compile_297e4d54680b970deaed` 批次 1 的待派发动作。`kernel/event-excerpt.json` 保留与 Control 执行直接相关的 784–799 及 Compile 交接 828–830 原始事件；中间 800–827 是 text-only 图像节点跳过，未在此归档。

此包只证明**规划与静态核验**：`control_verify` 为 `VERIFIED`，包含 121 个摄影机规划帧、14 份关键帧请求和 17 条覆盖记录；摄影机状态均为 `PLANNED_PROJECTION`。信件在 10.5 秒与 12 秒的可见部位均为 `[]`。全部覆盖项媒体审阅为 `NOT_RUN`，模型未提交；俯视调度图和镜头轨迹规划不能据此证明生成模型实际服从控制。

在本目录运行 `shasum -a 256 -c SHA256SUMS` 可核对所有归档文件（清单自身除外）。
