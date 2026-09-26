# 宿主桥接代码指纹更新后的 Control 重派发

真实演练项目：`/private/tmp/ai-video-v6-real-efKlQy/project`。旧 Control `TASK_eed007d42920d3df5b4f00f7` 因输入变更于修订 615 从 `ACCEPTED` 转为 `STALE`；原 Compile 同步于修订 616 转为 `STALE`。新 Control `TASK_f2d0f9805f575ed23ebfdb6d` 于修订 631 创建，修订 633 发出冻结动作。这里归档该轮真实派发和独立审阅证据；事件摘录在 `kernel/event-excerpt.json`，修订 685 的任务状态快照在 `kernel/task-state-excerpt.json`。

- 创作者 `/root/host_bridge/v6_360635fbdf384545b917078b` 经 `collaboration.spawn_agent` 真正派发，`host/hostfix-control-spawn-raw.json` 为原始回复，`host/normalized/9646641fd119ab861b37047d7af8b40cdc23d403f979b82ad28d7e3d0812058d.json` 为内核登记的规范字节；`host/hostfix-control-event.json` 将派发回执登记为修订 634 的 `RUNNING`。`host/hostfix-run2.json` 保留原始冻结动作。
- 创作者先以结构化 `QUESTION` 报告可见性疑点。宿主的指导与创作者只读诊断分别保存在 `host/messages/` 和 `host/subjects/`。冻结链复核确认 12000 ms 的 `PROP_LETTER.visible_parts=[]` 已由权威样本覆盖，遂提交候选。候选文件 SHA-256 为 `ac85da5aab0e3d685e76f38a2b47920424be8904aa3e34e2f732db9ca0ff54d6`，修订 645 进入 `REVIEW_REQUIRED`。
- 独立审阅者 `/root/host_bridge/v6_92b84faa63ee0c7816752382` 经真实派发并于修订 646 登记。三项必需检查 `module_receipt`、`control_verify`、`handoff` 均为 `PASS`；审阅记录 SHA-256 为 `1df07faa62e372410af4927c2ec12f2c28430385ff652f6e8c5a021c666775be`。审阅证据包含锁定 AVIR 原生校验、Control CLI 复核、独立重建逐字节比较。内核于修订 650 将任务从 `REVIEW_REQUIRED` 转为 `ACCEPTED`，修订 679 创建新的 Compile 任务，修订 681 请求派发。

控制包包含 121 帧 `PLANNED_PROJECTION` 和 14 项关键帧请求。`candidate/evidence/projection-limit.json` 及 `review/control-verify.review.json` 明示图片、视频、模型轨迹、接触和实际媒体审核均未运行；本次结果仅验证前期调度包，不能作为模型实际控制效果的证明。

本目录保留原始小型文件、宿主消息和内核事件摘录。较大的 AVIR、帧报告、HTML 和规格文件没有复制；`omitted-large.json` 列出其原始路径、字节数和 SHA-256。`SHA256SUMS` 校验本目录所有已归档文件，不包含自身。
