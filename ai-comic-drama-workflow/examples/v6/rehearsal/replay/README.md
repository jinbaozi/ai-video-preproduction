# 真实命令重放与冲突拒绝

在临时项目 `/private/tmp/ai-video-v6-real-efKlQy/project` 的真实 Director 派发已经登记后，用原 `DIRECTOR-event.json` 再次执行 `agent-event`。`replay-observations.json` 记录 CLI 标准输出、退出码和调用前后 V6 revision：返回 `ALREADY_RECORDED`，revision 保持 39。

`director-event-collision.json` 保留相同 command ID 和回执，但把原 `expected_revision` 改为 39。重复调用被 `COMMAND_COLLISION` 拒绝，revision 仍为 39。两份 wrapper 的 SHA-256 与每次返回原文都在 `replay-observations.json`；`SHA256SUMS` 列出本归档字节哈希。这里验证的是命令幂等与冲突门，不代表 Director 候选已审结。
