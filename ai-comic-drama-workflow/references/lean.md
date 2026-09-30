# Lean 执行合同

目标是减少组织和重复计算，而不是减少视频质量约束。`start --profile lean` 是现有当前 Agent 原生内核的便捷入口，不是第二套内容协议；`--profile audited` 使用原有 V6。默认完整参考图交付，默认终点为前期包，目标模型未指定或不支持时仍由真实能力/决定流程解决。

## 四个宿主工作段

创意与镜头收敛 → 按需制作实际控制素材 → 模型编译及一次完整交付复核 → 交付（要求视频时继续真实生产）。这是宿主组织方式，不伪造内核节点合并或跨阶段接受：Canon、ScriptIR、DirectorIR、ArtIR、StoryboardIR、AVIR 的原生依赖、锁和检查仍逐项执行。轻量模式减少的是子智能体派发、提交/取任务之间的往返、重复内容输出及重复全量计算。

新任务只给一句话即可开始。用户明确给出时长/模型/人物/台词则全部继承；未给创作细节由宿主合理补齐并标为设计，不当作用户事实。优先使用少量镜头和可复用身份锚点，不为“走流程”增加场景或角色。目标参数以当前锁定模型注册表为准，不硬编码默认全模型时长。

## CLI

```sh
ai-comic-drama start '成年旅人雨夜拾起信封，街灯由冷转暖，焦点从手中信封移到他的表情。' \
  --project ./rain-letter --target agnes-video-2.5 --delivery full
ai-comic-drama step ./rain-letter --result ./result.json
ai-comic-drama step ./rain-letter
ai-comic-drama start 原文.txt --project ./audited-project --profile audited --target agnes-video-2.5
```

`start` 同 `init` 接受资料路径或文本、project-id、target、mode、delivery、production-target。`start` 默认 lean；`init` 默认 codex，兼容已有调用。`step` 默认返回摘要、当前任务文件路径及必读清单，`--verbose` 返回完整结果。相同结果重试复用已有接受记录；发生冲突时保留 BLOCKED 原因，不继续下游。

`step --result` 的提交与取得下一任务是两个各自可恢复的内核动作，不声称跨动作原子提交。若结果已接受而下一步失败，重试同一结果会被识别为 ALREADY_ACCEPTED，不重复接受或生成。V6 禁止通过该参数提交原生结果，仍需 agent-result 与 agent-review。

`run/status/validate/export/revise/host/begin-image/production` 等原命令可继续使用。未知/缺失/篡改输入失败关闭。项目已存在时用 step/run；start 不覆盖旧目录。详情按需查[原生角色结果与宿主媒体协议](v5/runtime.md)。

## 不变的质量门

当前任务信封是唯一依据；全部来源、硬要求映射、原生验证和模块收据保留。身份图片定稿和图片审阅不能写死。最终编译复核依然核对冻结原生规格和每份投喂正文，静态覆盖通过不能代替语义理解。用户要求独立审阅时必须用 audited；lean 不能声称创作者与审阅者独立。

素材在创作阶段按消费用途规划：被镜头使用的身份、空间、动作关键姿态及目标入口附件。最多五张故事板是上限不是必须凑满；关键帧/参考模式限制与制作素材数量分开。决定使用的资产一旦进入接受的 IR，就按原规则制作、哈希、看图与验收，不能为缩短时间跳过。

多主体交互、接触、复杂运镜继续触发现有 ShotControlPack；光色、转焦与叙事意图保存于原生字段和合同，不借“优化提示词”改语义。硬要求无法被目标入口可靠执行时，明确能力限制/拆段/人工审阅义务，不承诺完美遵循。

## 自适应控制

新 `start` 按原生镜头数据推导控制素材，下限由 `--control-minimum 0..4` 提高；不能降低风险推导。L0/L1 不默认渲染白模；L2 按空间/焦点任务选择调度与时间验收；L3 接触/遮挡使用事件白模；L4 耦合连续运动使用完整预演。必要几何帧进入真实分镜图输入，再沿原有正文与附件编译路径交付。无 Blender/缺几何则真实阻断；独立视频参考需走现有联合编译，自动路径不伪称已投喂白模视频。

计划保存在现有 control-plan，证据保存在原生 RoleResult/state；没有新阶段或报告目录。控制任务按需读锁定模块的 `references/adaptive-control.md`。旧项目和 `init` 保持原策略，只有新 start 默认启用。

## 工作目录与读取

新 `start` 默认 compact 输出：`00-progress.md` 给出执行位置，`01-source/` 至 `09-delivery/` 按阶段存放必要产物，真实视频使用 `10-video/`。每轮依据 `task.output_file` 直接写原生结果；没有该字段的提示词、媒体或控制任务仍按其原协议提交，不发明额外产物。用 `step --result -` 提交标准输入 JSON，可避免结果镜像。机器上下文留在权威原生文件和 state，handoff 仅存字段指针；`context` 按需读原值，不生成文件。完整规则见[顺序目录合同](compact-workspace.md)。

任务内嵌的 craft 方法不另写相同读取文件。保持来源、原生验证、craft_review、冻结任务和结果收据；不得通过省略字段使检查失去依据。`--output-profile audit` 显式保留原布局；已有项目与 audited 不变，不扫描删除旧文件。

## 输出策略

lean 只省略可由权威 JSON 恢复的普通编译旁路报告，不删除内容：

- `avir.json`：完整原生制作规格，来源与全部时间/空间/动作/光色/声音要求。
- `artifact.json`：完整编译正文、轨迹映射、覆盖、损失、后期、诊断和未执行状态。
- `capability-snapshot.json`、`compile-manifest.json`：冻结能力与文件完整性。
- `prompt.txt`、`segment-delivery.json` 及各段 prompt/post/coverage：真实交付和投喂依据。

此清单不适用于复杂调度包；其原有检查资产不删。独立编译器 `compile --output-profile lean` 开启，默认 audit 保持旧输出；`replay` 继承原包输出模式。需要人读审计副本时，用同一 AVIR、目标、模式及匹配模块显式编译到新 audit 目录，不改变已冻结旧包。

工程上只缓存相同归档实际字节的完整性检查，仍核验每次归档哈希及所有解压文件哈希；编译内只复用该次不变输入的语义指纹，不跨编译缓存审阅。相同写入不触发事务，成功事务清理冗余恢复备份；恢复失败保留 pending 和备份。无自动删除旧项目/历史原件/不确定媒体任务。

## 完成边界

DELIVERED=前期包；DRAFT_REQUIRES_TARGET_CHECK=尚需目标入口检查；VIDEO_DELIVERED=真实视频完成并验收。这三者不能互换。仅文本模式不生成参考图；完整模式缺图仍阻塞。`step` 不调用模型；由 ChatGPT/Codex 宿主按当前任务实际创作、调工具和回收媒体。本次工程基准使用预先编写的三镜静态样例，不代表一句话创作速度、付费生成耗时或视频质量测量。
