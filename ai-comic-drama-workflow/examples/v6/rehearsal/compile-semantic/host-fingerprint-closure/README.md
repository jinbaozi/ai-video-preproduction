# Compile 语义闭环：宿主指纹修复后的真实演练

真实项目：`/private/tmp/ai-video-v6-real-efKlQy/project`，项目 `LETTER_DEMO`。这是 V6 图节点 `compile_review` 的第 1 批：任务 `TASK_01b83d9bf3bd9032fd655d18`，真实 Codex 子智能体 `/root/host_bridge/v6_6c3f3e0d88d5182c5cb2b850`。`dispatch/action.json` 是内核待执行动作；`spawn-raw.json`、`host-tool-result.json` 和 `receipt-command.json` 分别记录真实 `collaboration.spawn_agent` 返回、登记的工具返回字节和派发回执。ACK、PROGRESS、状态查询及 RESULT 的结构化包装和原始文本均在 `messages/`。这些文件来自原演练，非补写的执行历史。

上游 Compile 构建 `1f2df827a47bf738eadadf0799b46fe347c1b64947fb2f5eb81847aec9423ef0` 已在修订 695 接受。此节点依次在 697 READY、698 DISPATCHING、699 RUNNING、705 RESULT_SUBMITTED、706 VALIDATING、**707 ACCEPTED**；内核完成门检查 `module_receipt=PASS`、`compile_semantics=PASS`。图定义该节点为独立语义审阅，`review=none`，因此没有递归创建第二个审阅者。`event-excerpt.json` 直接保留原事件日志 695–707 的连续对象和原始哈希链字段；`source_sha256_at_archive` 仅标记当时完整日志字节，日志继续追加后会变化。

候选 SHA-256：`467920298872bbd2d13204318507e0f9aeddbf65d9acce6d56d7e2eba639f734`；RoleResult SHA-256：`bd6021f743edf0f0d262f368c47a49fd87f7784de2b2e44f3dc52027d3c83d8b`；CompileReview SHA-256：`cccbecbebfea36fb4639c9d08db48868e16e696a9cc9efb54cc91f52367ffba7`。静态语义审阅将 17/17 条硬要求逐条对应，并把此前 `AVIR_END_VISIBILITY_CONFLICT` 的旧终态 `["body","prop"]` 与当前 AVIR/时间线的 `[]` 比对后记为 `CLOSED_IN_CURRENT_BUILD`。旧失败原文见 `prior-defect/compile-review.json`。原生 AVIR 校验与编译包核验的输出见 `candidate/evidence/`。

**边界：**本次只证明编译文本及制作合同的静态等价。`media_qa=NOT_RUN`，音频与其他后期义务仍为 `PLANNED`；`submitted=false`、`runnable=false`、`transport=unresolved`，没有调用图片或视频生成接口，也未验证模型媒体效果。`omitted-frozen-files.json` 记录未复制的 3 个冻结输入与 21 个锁定资源的项目相对路径、字节数和 SHA-256，均已逐一匹配任务信封；其中 AVIR 为 126063 字节、编译清单为 10989 字节。`SHA256SUMS` 校验本目录实际保留的字节。
