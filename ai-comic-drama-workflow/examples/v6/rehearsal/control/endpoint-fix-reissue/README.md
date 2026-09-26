# Control 终态可见性修复后的真实重派

运行项目 `/private/tmp/ai-video-v6-real-efKlQy/project`，任务 `TASK_92a2f36e9b05a414fec43209`。两批均通过真实 Codex `collaboration.spawn_agent` 派发；`action.json`、`spawn-raw.json`、`dispatch.json`、消息与事件摘录保存任务名、执行身份、输入摘要及状态。`SHA256SUMS` 核对本目录精选证据，锁定模块全文和大体量逐帧预览未复制，完整文件仍在运行项目。

- 第 1 批创作者提交 SHA-256 `f5651f5723808b6ba0862d38e5935fdf58daeb7a92c882be1a63b5242da6cbac`；内核候选预审曾到 `REVIEW_REQUIRED`，随后发现运行时代码指纹变化，转 `STALE`。此候选保留历史，未派独审、未接受。
- 第 2 批由另一真实创作者基于新冻结代码重建；候选 SHA-256 `57fc771f2150f54e5de18f57886d6ebb393b09b9135100d21bb3ab0ea2906c56`。独立审阅 SHA-256 `5ebf30d05acbff17671d0092493b11433e231a23840e57e438e2a024ff217bc3`，三检查 PASS、原生 `VALID`、包校验 `VERIFIED`，内核于修订 548 `ACCEPTED`。随后运行时代码再更新，本批在修订 549 按代码指纹门正式 `STALE`；现行重建版见 `../endpoint-fix-final/`。StoryboardIR、AVIR、控制包在 12000 ms 的 `PROP_LETTER.visible_parts=[]` 一致。

121 帧相机仍只是 `PLANNED_PROJECTION`，环境根点未确定，14 个关键帧请求待宿主审核；实际媒体生成、模型控制及真实轨迹质量均为 `NOT_RUN`。候选与审阅包中仅精选结构、边界证据与哈希；完整锁定包仍由原项目持有。
