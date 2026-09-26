# 运行时状态修复后的 Control 重派证据

项目：`/private/tmp/ai-video-v6-real-efKlQy/project`。这次归档记录 V6 任务 `TASK_4c69e10662f9834bb335155d` 的真实重派，不把旧批次改写成新执行历史。前一次 `run` 因冻结输入变化将旧 Control、Compile、CompileReview 标记为 `STALE`；随后图在修订 767 创建新 Control，修订 769 请求派发。

创作者 `/root/host_bridge/v6_b98c8a672df44df0318bff26` 与独立审阅者 `/root/host_bridge/v6_c32efbecddd260be4b585eee` 均有原始 `collaboration.spawn_agent` 返回值和内核派发收据。ACK、PROGRESS、RESULT 消息、候选与审阅检查均为真实记录。候选文件 SHA-256 为 `d44e3b7847f7ab2166357468dfe392a1f155e21363a7362e650fa5dabb85c605`；独立 `review-record.json` SHA-256 为 `59c409c3dd0810741af0b7e352d8048562b6cbbbe22264f16a7143ad5aaeb67d`。三项检查 `module_receipt`、`control_verify`、`handoff` 都有审阅证据并为 `PASS`。Control 在 V6 事件修订 782 进入 `ACCEPTED`，产物索引指向本次候选包。

同一条 `agent-review` CLI 命令的后续自动 `run` 返回精确错误：`Predecessor is not complete: compile_review ('project', ())`。`review-submit-output.json` 保留原始错误；`event-excerpt.json` 和 `observed-state-excerpt.json` 证明 Control 接受已经提交。观察时，V6 的旧 `compile_review` 与旧 `compile` 任务均为 `STALE`，而 V5 状态的旧 `compile_review.status` 仍为 `ACCEPTED`，并绑定旧 `build_id`。因此本目录只证明本次 Control 独审通过和后继调度遇阻，不能据此声称新 Compile、QA 或前期交付通过。错误之后的修复或再派发需另存后续证据。

Control 包中的摄影机、俯视调度和关键帧请求仅为规划投影；`control-coverage.json` 将媒体审阅列为 `NOT_RUN`。本案例没有执行付费图片或视频生成，也没有验证生成模型的角色或镜头轨迹控制效果。`SHA256SUMS` 覆盖本目录每个文件（不含自身），可用 `shasum -a 256 -c SHA256SUMS` 核验。
