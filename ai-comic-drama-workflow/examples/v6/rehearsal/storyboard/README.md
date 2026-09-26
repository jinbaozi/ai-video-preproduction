# 分镜真实宿主演练

运行项目：`/private/tmp/ai-video-v6-real-efKlQy/project`；任务 `TASK_3240f8bc6a9896032b95d091`；模块 `storyboard-grammar@1.3.2`。两批创作者及第 2 批独立审阅均通过真实 Codex `collaboration.spawn_agent` 派发；原始工具返回、动作、收据、消息和逐项证据以批次归档。运行项目保留完整锁定模块与事务日志。

第 1 批的 StoryboardIR 原生 `inspect` 实际返回 `VALID`，但 RoleResult 的 `validator.status` 错写 `STATIC_VALID`。`agent-result` 在修订 142 拒绝，记录 `Validator summary does not match a fresh run`；旧候选字节保持原样。第 2 批从同一已接受上游重新派发，StoryboardIR 字节不变，RoleResult 以 fresh `VALID` 结果修订并重新绑定哈希。候选在修订 152 进入 `REVIEW_REQUIRED`，独立审阅者复跑原生 `inspect`、离线 `verify`、1,437 条 V5 交接和 3 条 V6 交接，三项检查均 PASS；内核在修订 158 登记 `ACCEPTED`，V5 原生提升成功。

`batch-1/` 保存失败候选和错误事件；`batch-2/` 保存成功候选、审阅及真实派发证据。`native-package/` 只精选 QA、compiler handoff 与可读分镜文本，完整离线编译包在运行项目中。每批 `SHA256SUMS` 校验本目录字节。StoryboardIR 给出角色/镜头/道具时间轴、俯视调度与遮挡约束；照明 `position_m` 被明确标为预演可读性锚点，ArtIR 没有真实锁定灯位。媒体与视觉审看均 `NOT_RUN`；静态检查不能证明生成视频会遵循调度。

后来 V5 快照重定位导致第 2 批已接受 StoryboardIR 的语义审阅哈希失配，内核将其置为 `STALE`。`rebuild-1/` 保存基于当前 Director 与 Art 的新 Storyboard 责任批次，真实创作者和独立审阅者重新核对输入、原生状态 `VALID`、语义摘要、1437 条 V5 与三条 V6 交接；内核于修订 276 重新接受，修订 279 进入控制包任务。旧批次证据没有被覆盖。

`upstream-repair-1/` 保存 Compile 独审按 Director 责任回流、Director 与 Art 重建后重新派发的分镜任务。新创作者和独立审阅者复核两种锁定坐标约定的换算、六个状态样本、七个面板、语义摘要及九个编译文件字节；内核于修订 435 接受，媒体仍 `NOT_RUN`。
