# 分场美术真实宿主演练

运行项目：`/private/tmp/ai-video-v6-real-efKlQy/project`。任务 `TASK_0560d46ecc764c68ee9a590e`，场景范围 `SC_RAIN_NIGHT`，模块 `scene-painter`。创作者 `/root/host_bridge/v6_2dea6a2a9ca676085285dc07` 和独立审阅者 `/root/host_bridge/v6_c67d66bf19aa53d39fb4168d` 分别由真实 `collaboration.spawn_agent` 派发；原始返回、内容寻址回执、动作和结构化消息均在本目录。

`candidate/` 存放 ArtIR、RoleResult、`candidate-result/6.0`、原生校验和交接证据；`review/` 存放逐项独立证据与 `review-record/6.0`。第一次原生校验在系统 Python 缺 `jsonschema` 时尚未读取 ArtIR，错误作为消息与候选证据保留。创作者改用项目既有 `.venv/bin/python`，未安装依赖或修改模块。锁定原生校验返回 `STATIC_VALID`，离线编译标记 `PLANNED`。

审阅者复核冻结输入、模块收据、ArtIR 语义与交接，三项检查均为 PASS，协议候选摘要与文件 SHA 分别绑定。上游 DirectorIR 的 shot phases 为空，因此 ArtIR events 为空；五个定时动作仍受上游时间线约束。内核于修订 132 将本任务置为 `ACCEPTED`，随后把 text-only 资产提示词和媒体节点按各自条件记为 `NOT_APPLICABLE`，进入分镜任务。图片与视频媒体均未执行或审核。

`frozen-record.json` 和 `event-excerpt.json` 保留内核状态/事件摘录；`SHA256SUMS` 可逐文件核对本目录归档字节。临时运行项目保留完整模块锁和事务记录。

后续控制包诊断令原 Director 与本任务失效，原 Art `ACCEPTED` 已转为 `STALE`。`rebuild-1/` 保存基于新 Director 的真实 Art 创作者与独立审阅证据；内核在修订 238 接受新 ArtIR。此后调度器重建旧视觉提示词跳过任务时遇 `COMMAND_COLLISION`，错误输出也在该目录；修正 skip ID 后于修订 261 进入新分镜任务。

`upstream-repair-1/` 保存 Compile 审阅按 Director 责任回流后，新 Director 被审结所触发的 Art 重建。真实创作者与独立审阅者核对静态场景坐标和时间轴坐标经轴序换算的一致性，三项检查 PASS，内核于修订 422 接受。初步坐标疑虑及复核后的修正结论都以结构化消息保留，媒体仍 `NOT_RUN`。
