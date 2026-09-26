# Director 第 3 批：已派发，未提交

`repair-brief.json` 由前两批真实失败事件和审阅证据冻结生成。`creator-action.json` 是待执行动作，`creator-host-proof.json` 是真实 Codex 派发返回。`candidate/` 中的文件由所派发创作者写入项目候选目录后复制归档。

宿主用量中断时，`frozen-record.json` 记录项目修订 72、任务 `RUNNING`、`candidate_registered=false`。没有 RESULT 消息、内核候选登记或独立审阅；这些文件不能视为通过验收。`SHA256SUMS` 核对本目录的归档字节。
