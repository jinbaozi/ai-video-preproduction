# 新编译构建的候选级失败与暂停

源项目 `/private/tmp/ai-video-v6-real-efKlQy/project`；任务 `V6_compile_6d907d52041427c68f2a` 绑定旧语义失败记录 `CSF_74831a102e205da1d82b7605` 和新 Control 后的 build。两批均通过真实 Codex `collaboration.spawn_agent` 派发，动作、raw 返回、执行消息和事件摘录在各批目录。

第 1 批创作者报告锁定 validate/verify/replay 通过、20/20 编译文件一致，`evidence/semantic-closure.json` 表明旧 AVIR 终态可见性冲突在新 build 中消失；但它错误地在 graph-only Compile 候选中声明原生 `RoleResult`。内核在修订 605 正式 `FAILED`，`failure.json` 原文为 `Graph-only candidate must not claim a native RoleResult`。这不是独立审阅通过，旧候选没有被接受。

第 2 批真实派发后，宿主桥统一提示中发现 graph-only 与原生 RoleResult 的语义冲突，负责人正在修宿主源码并纳入运行码指纹。宿主暂停指令、创作者 `BLOCKER`、`CANCEL_ACK` 已正式登记；创作者只保留冻结输入、VALID/VERIFIED/COMPILED 的诊断，无 `candidate-result.json`、无 RoleResult、无正式候选提交。代码指纹更新后本批须按 V6 输入失效门处理，不能使用它宣称编译已接受。

本归档只选关键证据，完整静态构建仍在运行项目；媒体和实际模型执行均未运行。`SHA256SUMS` 核对所附字节。
