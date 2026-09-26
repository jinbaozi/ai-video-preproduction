# 宿主桥指纹更新后的 Compile 重派发

源项目：`/private/tmp/ai-video-v6-real-efKlQy/project`。更新后的宿主桥进入冻结运行码指纹后，原 Control 与 Compile 批次失效；新 Control 经独立审阅接受后，内核生成 `V6_compile_ee07749c72a2525a571b` 第 1 批。`frozen/task-brief.json` 绑定当前 Control、Storyboard、新静态构建和旧语义失败路由 `CSF_74831a102e205da1d82b7605`。

本批通过真实 `collaboration.spawn_agent` 派发：创作者 `/root/host_bridge/v6_ac68989ddc22986a6c713a9b`，独立审阅者 `/root/host_bridge/v6_dd023c3fdf9093c33af62abe`。两个派发动作、原始返回、内核回执及 `ACK`、`PROGRESS`、`RESULT` 消息见 `dispatch/` 和 `review-dispatch/`。候选 SHA-256 为 `a767c7331386a5c84eeda05615c754f27827a05eff3c26f7d56f9535d4ad6cce`；这是 graph-only Compile，`result_uri` 与 `result_sha256` 均为 `null`，没有冒称原生 RoleResult。审阅记录 SHA-256 为 `574d1cd7279b25c32bc7cdbc3cd50729d15132ab08e3239d1eefe944341be005`。

锁定编译器的 AVIR `validate` 为 `VALID`，冻结构建 `verify` 为 `VERIFIED`。创作者和独审各自提供 `module_receipt`、`native_validator`、`compile_manifest`、`handoff` 四项 `PASS` 证据。审阅核对 24 个任务简报文件、20 个编译文件、17 个硬约束条款和 10 个 Control 包文件。旧 `AVIR_END_VISIBILITY_CONFLICT` 在当前冻结字节中静态关闭：信件在 10.5 秒和 12 秒的终态可见部位均为 `[]`，当前 AVIR 与正文一致。内核在修订 **695** 才将任务从 `REVIEW_REQUIRED` 转为 `ACCEPTED`；完整迁移证据见 `state-events.json`。

这里只归档精选小文件。未复制的 AVIR 为 **126063 字节**、SHA-256 `923b964738c685fa2f356ba43000f2b43059751b95eb0260d27d1badef38cd1c`；未复制的完整提示正文为 **30283 字节**、SHA-256 `72fe66a15c952c2b580ee0f660d4b524d9f4926189a7e2e996f782dd32232034`，二者仍在源项目。此处结论限于静态编译及 Compile 节点审阅：`prompt-review` 仍为 `PENDING_AGENT_REVIEW`，分段交付仍为 `DRAFT_REQUIRES_TARGET_CHECK`，媒体 QA 为 `NOT_RUN`，未执行外部生成。所附文件字节由 `SHA256SUMS` 核对。
