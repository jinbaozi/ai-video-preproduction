# Screenplay 真实宿主演练

临时项目：`/private/tmp/ai-video-v6-real-efKlQy/project`。任务 ID：`TASK_1b94794070565f70c7f697a7`。原文与 Canon 见相邻 `../canon/`。本目录只归档小型候选、审阅、回执和事件摘录；锁定 Skill 模块原包仍在临时项目中。

`creator-action.json`、`reviewer-action.json` 是当时真实 `run` 返回的待执行动作；`spawn-screenplay.json`、`spawn-screenplay-review.json` 是两次实际 `collaboration.spawn_agent` 返回的对象，内容寻址副本是 `creator-host-proof.json`、`reviewer-host-proof.json`。执行者与独立审阅者分别为 `/root/host_bridge/v6_e0ad76147ac04f3d8c0d1d21` 和 `/root/host_bridge/v6_e0f12f0efac55ace2c0387d7`。派发回执、ACK、RESULT、候选提交与审阅提交的 CLI 包装保存在本目录顶层。

冻结 V5 任务要求 `role-result/5.1` 与真实模块收据。执行者发现版本约束后，其问题与宿主回复分别进入 `screenplay-version-report.json`、`screenplay-version-reply.json`，原文及哈希保存在 `version-report-source.json`、`version-reply-source.json`，通过 `in_reply_to` 相连。正式候选位于 `creator/`，独立审阅与各项复查证据位于 `reviewer/`。内核事件修订 18–32 的摘录在 `event-excerpt.json`；修订 32 将 screenplay 置于 `ACCEPTED`，V5 `screenplay.complete=true`，随后创建导演任务。

`SHA256SUMS` 记录归档文件字节哈希。此处的工具返回、宿主消息和临时项目状态共同构成演练证据；归档本身不能代替重新执行，也不证明任何图片或视频生成质量。
