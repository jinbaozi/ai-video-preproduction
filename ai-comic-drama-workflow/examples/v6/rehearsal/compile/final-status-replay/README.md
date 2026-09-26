# 最终状态重放：Compile 图节点

源项目：`/private/tmp/ai-video-v6-real-efKlQy/project`。锁定任务：`V6_compile_297e4d54680b970deaed` 第 1 批；冻结构建 `1f2df827a47bf738eadadf0799b46fe347c1b64947fb2f5eb81847aec9423ef0`，冻结目录 `builds/99a4e889069740b797654891d4c7acc18866380e438a4a86d5311b47b467754c`。此次从上一轮已接受的 Control 进入 Compile，旧语义失败 `CSF_74831a102e205da1d82b7605` 由冻结简报绑定，未补写历史。

真实宿主派发见 `dispatch/pending-action-output.json`、`dispatch/spawn-raw.json` 和 `dispatch/dispatch.json`；创作者为 `/root/host_bridge/v6_358a224f5db0a6562d4d60bd`。独立审阅派发见 `review-dispatch/`；审阅者为 `/root/host_bridge/v6_0f15f884265f9b6cd39021f7`。ACK、PROGRESS、RESULT 以及宿主资源提醒均有注册消息与原始文本。内核事件摘录保留原事件的修订、前链哈希和状态摘要；Compile 在修订 **844** 从 `REVIEW_REQUIRED` 进入 `ACCEPTED`。`review-dispatch/accepted-output.json` 为修订 **847** 的后续 `compile_review` 派发输出，不能据此把 Compile 接受时间记为 847。

候选 SHA-256：`1fabbbf3f1d2a4b0205ba6ffc1f64dcaaf616bcf678714305d169d88a0538992`；独审记录 SHA-256：`dcb61d729e2be35f3053138ca5f4e2a8bed93bd72ae9fabafcaea66aba51b748`。这是 graph-only Compile，候选的 `result_uri` 和 `result_sha256` 均为 `null`，没有原生 RoleResult。AVIR `validate=VALID`、冻结编译包 `verify=VERIFIED`；候选与独审的四项检查均为 `PASS`。独审核对 24 个简报文件、20 个编译文件、10 个 Control 文件和 17 个硬约束条款。旧 `AVIR_END_VISIBILITY_CONFLICT` 在冻结字节中静态关闭：StoryboardIR 与 AVIR 于 10500、12000 毫秒的信件 `visible_parts` 都为 `[]`。

归档为精选小文件。完整 AVIR 未复制，源 URI 为 `runtime/v6/candidates/V6_compile_297e4d54680b970deaed/1/avir.json`，SHA-256 `923b964738c685fa2f356ba43000f2b43059751b95eb0260d27d1badef38cd1c`；完整正文未复制，源 URI 为 `builds/99a4e889069740b797654891d4c7acc18866380e438a4a86d5311b47b467754c/compiled/prompt.txt`，SHA-256 `72fe66a15c952c2b580ee0f660d4b524d9f4926189a7e2e996f782dd32232034`。`frozen-build/` 保留交付边界：编译包内的 `prompt-review` 字段仍为 `PENDING_AGENT_REVIEW`，片段执行 `NOT_RUN`，后期义务仍为 `PLANNED`。此节点只证明静态编译和独立审阅，未调用外部媒体生成。文件字节由 `SHA256SUMS` 核对。
