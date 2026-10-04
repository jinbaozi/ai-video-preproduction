# 最小阶段执行 / minimal-core/1.0

## 一个阶段，一个原生结果

新 `start` 的 lean 路径冻结 `context_policy=minimal-core/1.0`。阶段保留必要输入、原生结果、采用与约束检查、异常及收据；它不是新的内容IR或模型客户端。`--context-profile audit` 保留完整宿主阅读，`--profile audited` 保留V6独立派发与审阅。旧项目及锁定模块不迁移。

宿主读取 `start/step/run` 返回的 `context`。其中 `readings` 为当前阶段实际读出的必要说明；原生产物仍通过 `inputs`、`handoff` 的URI、字段指针和哈希读取。不能因有最小视图就跳过原文、原生schema、必要媒体或上游锁。`task_file` 是完整审计信封，遇路由争议或异常时按需展开，不再是第二份例行阅读。

`craft.rules`、`craft.inherited` 保留全部规则正文和适用范围；模板保留写作结构，重复的 instruction/check 用明确 rule_id 指回同一规则。社区段落保留原文。检索备选、重复来源哈希与归档元数据留在审计信封；登记的人物、主语法、场景规则、技巧、原生字段和观察检查不削减。源码中的资料索引仍接受全库可达性检查。

## 最小宿主结果

```json
{
  "schema": "core-result/1.0",
  "task_id": "从当前任务复制",
  "read_ack": true,
  "artifact": "当前任务output_file的实际路径",
  "checks": ["本次对照上游事实、动作和锁定项的实际发现"],
  "conflicts": [],
  "unresolved": [],
  "handoff": [],
  "craft_review": {
    "rationale": "本次方法如何服务当前故事、镜头或观众理解。",
    "semantic_review": true,
    "groups": [{
      "rule_ids": ["从当前任务复制同一证据覆盖的规则ID"],
      "status": "applied",
      "pointer": "/实际原生正文路径",
      "quote": "该路径中实际存在的短语",
      "reason": "这处创作决定与所列方法之间的具体关系。",
      "check": "检查动作、视点、时间或光色的可观察结果。"
    }]
  }
}
```

示例是结构说明，不是可冒充通过的内容；`handoff` 必须覆盖任务实际要求，不允许套空数组。Canon提交带来源证据的四职责 `craft_context`；导演提交 `craft_scene_routes`；图像、控制、编译复核继续提供该种类的原生字段。媒体验收需要原有真实字节、调用证据、输入绑定和视觉发现，不能由程序自动生成PASS。

`read_ack:true` 是宿主声明已经阅读本视图与其说明，不是独立的认知证明。程序校验当前任务、模块和说明字节，填充原生结果文件哈希、module_receipt、source_sha256、规则计划/内容指纹与实际原生验证器状态。已提供的内容哈希冲突会拒绝，不重绑旧证据。语义判定仍为 `HOST_DECLARED`；提交时计算哈希不证明此前看过媒体。

`applications` 与 `groups` 二选一。分组只能合并同一字段、同一范围、同一观察结论的证据，规则ID须列举，不接受通配符；展开后每项恰好覆盖一次。`not_applicable` 仍要求条件和理由，不能把全部规则设为不适用。缺原文、缺方法、引用失效、越界修改、重复/遗漏或来源变化继续阻断。

## 合并末尾两个宿主回合

编译复核针对同一冻结build完成后，可在该 `core-result` 中附上宿主所写的 `delivery_audit`：

```json
{"build_id":"当前build_id","passed":true,"checks":["逐项硬约束ID及真实交付发现"]}
```

`step` 在同一本地事务内依次接受编译复核、派发原生QA任务、绑定该审计并通过原有QA门。两份原生收据保留；宿主不重复提交同一build的最后一次审计。QA需要额外说明、build变化、缺硬约束或审计失败时回滚该事务；没有 `delivery_audit` 则仍派发独立QA。程序不添加 passed=true、编造发现或声称视频已生成。

## 本地检查复用与异常

每份原生结果仍验证原件与归档后的字节。只在一次submit内复用第一次原件报告，免去第三次同字节原件校验；完成或失败清除临时报告。文件改变会拒绝，跨操作、改模块、改规则或修改结果后不缓存通过状态。

错误回到实际责任阶段；普通创作选择由宿主定稿，权限、费用、缺媒体、未知执行和失败质量门维持原规则。外部状态UNKNOWN先回收，不重提交。`DELIVERED`是前期包；真实生产、Flow保真2K、剪映导出与整片审阅沿原链执行，完成后才可能 `VIDEO_DELIVERED`。

入口字节、说明字节、宿主提交字节与本地验证耗时需分别计量；它们不是厂商计费token或真实模型生成时间。
