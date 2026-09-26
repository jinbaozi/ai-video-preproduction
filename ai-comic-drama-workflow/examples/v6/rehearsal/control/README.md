# 调度控制包真实宿主演练：取消并保留诊断

运行项目：`/private/tmp/ai-video-v6-real-efKlQy/project`；Control 任务 `TASK_60ca76854c7350d8a40f1c72`，批次 1。创作者 `/root/host_bridge/v6_4deca677dad482965c38a58d` 经真实 Codex `collaboration.spawn_agent` 派发并由原任务续做；`raw-spawn-result.json`、动作、收据、通信包装及事件摘录保留派发与取消链。

锁定控制编译器曾从已接受 StoryboardIR 构建并验证诊断包：AVIR 映射损失为 0，静态摄影机位置保持轨派生后，121 帧投影未定数降为 0；媒体状态仍 `NOT_RUN`。后续检查发现 V5 接收 StoryboardIR 时将来源 URI/哈希重定位，原 `semantic_review` 的内容摘要不再绑定 V5 复制件。`diagnostic-candidate/evidence/semantic-review-rebase-blocker.json` 保存逐字段比较；这使 AVIR 语义审阅为 `PENDING`，诊断包不能作为合格成品。

创作者正式回传 `CANCEL_ACK`，未提交 candidate-result、RoleResult 或 RESULT；内核在修订 188 将 Control 置为 `CANCELLED`。随后 `run` 在修订 201 把原 Director 与 Storyboard 及下游 Art 标为 `STALE`。旧包只作为历史诊断，未交付为已接受调度控制包。运行项目保留完整编译包与大体量逐帧/adapter 报告；本归档只选关键可读文件，并列出省略报告的文件哈希与字节数。`SHA256SUMS` 核对归档文件自身，不等同于完整包的离线 verify。

`rebuild-1/` 保存基于重新接受的 StoryboardIR 的新控制责任批次。创作者与独立审阅者由真实 Codex 工具派发，锁定 AVIR、控制包与 V6 预审通过，内核在修订 293 接受 ShotControlPack。包只给出静态规划：121 帧相机投影状态均为 `PLANNED_PROJECTION`，环境根点仍因缺数值位置而 `UNDETERMINED`；14 条关键帧请求待宿主审核，真实模型控制和媒体均 `NOT_RUN`。

`upstream-repair-1/` 保存 Compile 独审引发 Director 跨责任回流后，Control 基于最新分镜的重建。真实创作者与独立审阅者复跑锁定 AVIR/控制包，内核于修订 479 接受。此包继续仅证明静态摄影机投影，保留环境根点未知、关键帧请求待审核及媒体 `NOT_RUN` 的边界。

[`endpoint-fix-reissue/`](endpoint-fix-reissue/) 保存编译语义审阅发现 AVIR 终态信件可见性冲突、适配器修复后的 Control 重派。第 1 批因执行期间运行时代码指纹变化正式 `STALE`；第 2 批由另一创作者和独立审阅者重建，于修订 548 曾 `ACCEPTED`，随后因新的运行时代码指纹变化也正式 `STALE`。两批候选均保留为历史。

[`endpoint-fix-final/`](endpoint-fix-final/) 保存修订 549 运行时代码指纹变化后的 Control 重建。真实创作者及独立审阅者重跑校验，内核于修订 567 曾 `ACCEPTED`；宿主桥源码进入运行码指纹后，此版于修订 615 转为 `STALE`。

[`host-fingerprint-reissue/`](host-fingerprint-reissue/) 保存该指纹更新后的真实派发、诊断问答、Control 候选及独立审阅。内核于修订 650 接受新包；121 帧仍仅是静态规划投影，媒体和模型执行 `NOT_RUN`。

[`status-fix-reissue/`](status-fix-reissue/) 保存状态读面修复引发的新指纹下 Control 再次真实派发与独审，内核于修订 782 接受。随后自动推进遇到 V5 旧 `compile_review` 与 V6 已失效审阅不一致的严格前驱错误；此目录保留原始 `ERROR`，不宣称后续 Compile 完成。
