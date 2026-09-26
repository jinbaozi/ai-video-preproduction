# 前期交付状态读取修复与正式失效恢复

演练项目：`/private/tmp/ai-video-v6-real-efKlQy/project`；交付目标为 `text-only`。本目录固定修订 **738–769** 的证据。修订 769 之后的真实智能体派发和候选产物由后续演练记录负责，这里的 `DISPATCHING` 只表示内核发出了待宿主执行的动作。

## 逐修订事实

| 修订 | 可观察事实 |
| --- | --- |
| 738 | `raw/hostfix-final-status.json` 是当时的历史快照。前期交付任务 `V6_preproduction_13e89f5eb81bc5856bc8` 已 `ACCEPTED`，`preproduction_complete=true`，但状态读取面仍报 `BLOCKED`。旧 `status()` 因历史上的任意 `STALE`/`FAILED`/`BLOCKED` 任务遮蔽了当前已完成的交付。修订 738 的事件另把不需要的视频交付标成 `NOT_APPLICABLE`。 |
| 739–741 | `v6_runtime.py` 的内容指纹改变后，内核将旧 Control、Compile、Compile Review 分别以 `INPUT_CHANGED` 从 `ACCEPTED` 转为 `STALE`。`raw/statusfix-run1.json` 明列这三个直接失效任务。 |
| 742–766 | 下游跳过记录、QA、前期交付等依次以 `DEPENDENCY_STALE` 失效。修订 757 的前期交付由 `ACCEPTED` 转为 `STALE`。修订 766 的状态快照已是 `BLOCKED`、`preproduction_complete=false`，与当时的权威任务状态一致。 |
| 767–769 | 内核创建新 Control `TASK_4c69e10662f9834bb335155d`，经 `PENDING → READY → DISPATCHING`，返回真实 `collaboration.spawn_agent` 待执行动作。修订 769 快照为 `AWAITING_HOST`；在本段事件中尚无派发回执，也没有声称已派发智能体。 |

新 `status()` 按项目范围寻找最新前期及视频交付节点，并与 V5 原生交付状态核对；`kernel/runtime-source-change.diff` 保留修复的精确代码差异。这里没有把修订 738 的旧快照改写成新状态，也没有补写虚构的派发历史。代码更新会使绑定旧源码指纹的运行任务正式失效，因而即使历史交付已接受，也需要按新输入重新走内核交付门。

## 证据索引

- `raw/` 保存五份原始 CLI 输出，未裁切或改写。`kernel/status-summary.json` 只提取关键状态、修订及任务，便于阅读；原文仍以 `raw/` 为准。
- `kernel/event-excerpt-738-769.json` 保留原始事件对象和哈希链字段；`kernel/transition-summary.json` 是可读摘录。事件 739–769 完整覆盖该次失效与新动作，738 是交付基线。
- `kernel/old-control-v6-envelope.json` 与 `kernel/new-control-v6-envelope.json` 保存变更前后冻结资源声明；`kernel/new-control-frozen-native-task.json` 是新任务的原生冻结输入。`raw/statusfix-run2.json` 保存原始待执行动作；`kernel/new-control-host-action.json` 仅将其中唯一动作独立提取。
- `kernel/runtime-source-hashes.json` 逐项核对旧、新任务信封声明的 SHA-256、项目内冻结源码的实测 SHA-256，以及本目录副本的 SHA-256。旧 Control 的 `v6_runtime.py` 为 `6f763946439d79c8957a23215c25219325cbb74ada3865b5d0a33206b4dc1a45`，新 Control 为 `cf51dfeccb9e851219cdbea02e4493cc29c1e62b02d197112ec2621913d137be`；`v6_runtime_fingerprint.py` 和 `v6_codex_host.py` 在两份信封中哈希未变。冻结目录和本目录副本均经重新读取计算，六项一致。
- `sources/` 保存以上受核对的源码字节。`SHA256SUMS` 覆盖本目录所有归档文件，但不包含它自身。

本证据只涉及前期编排、状态读取和真实宿主动作边界。没有调用付费图片或视频生成，也没有验证生成模型的成片效果。
