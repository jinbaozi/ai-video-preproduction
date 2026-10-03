---
name: ai-comic-drama-workflow
description: >
  新 lean 项目默认顺序目录与最少持久上下文，从 00-progress.md 查看进度，不复制上游正文。
  未指定名家时也默认按内容与场景选择专业方法；继承上游锁定，不以人名代替实现。
  从一句话、创意或资料连续完成参考图、分镜、模型提示词及附件交付；需要成片时接真实执行与验收。
  新创意默认 lean：当前宿主连续承担七类职责，按需读取锁定模块，保留原生质量检查，少派发、少报告。
  显式需要独立审阅时使用 audited/V6；已有项目保持原协议，不自动降级或迁移。
metadata:
  version: "0.18.0"
---

# 从创意到视频制作包

## 默认最少输出

新 `start --profile lean` 默认 compact：阶段目录按需创建，`00-progress.md` 是人工进度入口。任务给出 `output_file` 时直接写该原生文件，不另存 author 草稿或独立整包导出；完整上下文保存在原生产物与 state，任务只带上游字段指针。`task.craft` 内嵌方法不重复落盘。RoleResult 可用 `step --result -` 从标准输入提交；需要字段时用 `context --slot SLOT --pointer /field`。不遍历全部历史，不写重复计划、总结、清单或验收报告。详细规则按需读[顺序目录合同](references/compact-workspace.md)。旧项目和 audited 不迁移、不删除；审阅、来源、原文与失败恢复证据保留。

## 默认专业方法路由

新 start 默认在 Canon 提取有原文证据的语义特征，任务自动附上选中的方法卡和采用验收项。旧项目不迁移，用户明确关闭才用 --craft-routing off。先读[默认路由合同](references/craft-routing.md)；完整任务遵循 task.craft，提供绑定实际内容的 craft_review。方法不得覆盖 Canon、信息顺序、连续性或用户锁定；静态证据不等于成片画质。

## 先选路径，不先写长方案

新的一句话/创意任务默认 `start --profile lean`。独立审阅、多智能体协作是明确要求时用 `--profile audited`；这条路径仍是 V6 的真实派发、独立审阅和证据状态门。已有项目先看 `project.json`，保持其协议。`init` 的旧默认仍为 V6。

只需单条提示词、剧本或美术方案时调用对应独立 Skill，不创建全项目。完整制作只读[轻量执行合同](references/lean.md)和当前任务列出的锁定模块资料，不遍历所有历史合同。

新 `start` 固定自适应控制策略：从原生镜头数据选择 L0–L4 的最少素材。控制任务返回必要调度图、事件白模或连续预演；不要把等级写成画质保证。白模事件图必须进入分镜图输入，缺实际素材、未知轨道或失效证据就停止下游。详情只在控制任务读取锁定编译器的 `references/adaptive-control.md`；不额外启动 Agent。

## 自动继续的宿主循环

用户只给创意，不需要填写 JSON。宿主负责创作原生内容并运行命令；Python 不创作故事、不自行启动 LLM，也不模拟生图。

```sh
ai-comic-drama start '用户的一句话或创意' --project /绝对路径/新项目 --target 已核验的目标ID
ai-comic-drama step /绝对路径/新项目 --result /绝对路径/当前原生角色结果.json
```

未安装命令时，在本 Skill 根目录使用 `PYTHONPATH=src python -m ai_comic_drama_workflow`。Python 3.12+，依赖见 `pyproject.toml`。

每次读 `task_file` 与其中 `required_reads`，完成任务规定的原生 IR、模块检查、交接和 RoleResult，再用 `step --result` 一次接受结果并取得下一任务。只读对应模块的锁定副本，不读相邻开发源码；同一上下文中已完整读过且哈希未变的说明可复用，内容遗失或哈希变化必须重读，收据不得虚构。

当前宿主连续承担 Canon、编剧、导演、美术、分镜、图片提示词和视频编译职责；不为每种职责默认另开子智能体。**专业边界、原生校验、模块收据和编译语义复核不删；lean 的当前 Agent 复核不冒充独立审阅。** V6 用[宿主桥接](references/v6/codex-host.md)和[执行接口](references/v6/runtime.md)，不能通过 `step --result` 绕过。

普通阶段不逐次征求确认、不输出长篇中间说明；持续执行到交付或真实阻塞。完整工作流默认 `autonomous-until-blocked`：当前 Agent 自主完成阶段定稿、候选选择、有界返修和后期剪辑，不再把“定稿”本身作为审批点。登录/权限、新增付费、UNKNOWN 执行、能力降级或有界返修后仍不合格才通知用户。细则按需读[全自动推进合同](references/autonomous-until-blocked.md)。

## 最少素材，完整控制

创意先收敛成能在目标时长内表达的最小镜头集合，再写本轮原生规格。保留来源事实和用户锁定，新增设计标明来源。没有用户要求或镜头用途时，不自动制作每个角色的全套多视图、每个场景空镜、装饰性 LUT/白模、候选方案报告。每项计划素材都要被具体镜头、身份一致性或控制要求消费；**不能从已接受 IR 中擅自过滤必需素材来加速**。

持续保留身份/服饰/道具/空间/面向/运动/时间/信息/声音连续性。光色要对应情绪意图；转焦明确起止主体与时间；动作有接触、支撑、路径和收束。多主体、接触或复杂运镜仍按既有规则执行调度控制包；缺中间姿态不假定插值。原生链保持 ScriptIR → DirectorIR → ArtIR → StoryboardIR → AVIR，不增加平行内容账本。

默认 `delivery=full`。只有用户明确只要文字才使用 `--delivery text-only`，不能因为缺少工具偷偷降级。图片先由锁定 image-prompt-optimizer 编写；宿主登记实际工具能力、先 begin-image 后真实调用，实际附带冻结参考，逐项看图并登记哈希与证据。调用未知先回收，不凭超时重生成。禁止其他应用凭证、未登记入口及套用示例的创作/审阅结论。

`delivery=full` 中，实际图片通过原有看图审核后、进入视频模型附件映射前，默认再经过 Google Flow 保真 2K 门。Flow 输出必须是真实回收并重新观察的文件，长边至少 2048 像素，身份、服装、姿态、构图/空间、道具、光色和文字不得发生不可接受漂移；失败或需要登录时 BLOCKED，不用本地 resize 冒充。按需读[Flow 2K 参考素材合同](references/flow-2k-reference.md)。

## 交付与真实完成

前期交付只向用户展示进度页及交付入口（compact 为 `09-delivery/index.md`，旧项目为 `delivery/index.md`）和实际引用文件；它链接分段提示词、后期义务、附件顺序、参考图、原生规格和检查结果。lean 编译不落盘重复审计投影；全部约束仍在 `avir.json`、`artifact.json` 和逐段覆盖中。BLOCKED、DRAFT_REQUIRES_TARGET_CHECK、UNKNOWN 都必须原样显示，不当作可直接执行。

`production_target=none` 到前期包 DELIVERED。用户要求生成成片时使用 `--production-target video`，DELIVERED 后继续原有 `production` 冻结、真实执行或人工回收、逐镜/相邻验收、总装与整片审阅。总装阶段默认优先接入 `jinbaozi/jianying-headless` 的 `yichen-jianying-edit`：先 doctor，再由已接受 Take 生成隔离剪映草稿并验证；需要成片时从冻结快照原生导出并完整解码验收。不能安装、版本不匹配或导出失败时 BLOCKED，不把简易拼接冒充剪映交付。按需读[剪映后期合同](references/jianying-postproduction.md)。只有真实当前字节通过后才是 VIDEO_DELIVERED。缺工具或权限说明阻塞，不伪造视频。静态测试通过、几何/摄影意图及提示词编译均不证明模型画质或物理精确控制。

局部修订用 `revise` 与已有依赖失效规则；换模型不自动重做无关图片。原文、冻结决定、权威 IR、实际媒体与失败恢复证据保留。成功事务的冗余备份可清理，未完成事务及旧项目不自动清扫。

目标为 H3 / RunningHub 时，编译职责按锁定模块的 H3 条件读取执行。Desktop 单条提示词可直接使用视频编译技能；节点计划与官方 Context-IR 候选不绕过原有接受、审阅或媒体门禁。

实现与宿主命令按需读 [Flow 参考与剪辑执行](references/flow-and-editing.md)。持久请求按项目相对路径绑定，移动恢复项目不会产生新调用；未知执行仅允许回收。

## 来源绑定的提示词方法

新编译模块自带通用方法、任务模板与精确模型适配。当前任务的 `craft.prompt_methods` 只包含已选方法；将其 `craft.rules` 与原有规则一起落实到原生字段和 `craft_review`。消费者继承而不重新决定风格，分镜已采用模板自动传给编译器。无需用户填写模板JSON或逐阶段审批；冲突由当前宿主回到责任节点修订，不擅改锁定项。完整合同在编译模块 `references/prompt-techniques.md`。

## 按需资料入口

[本职责资料索引](references/resource-index.md)只提供可达路径；当前任务只读取适用条目，历史资料不自动替代冻结协议。完整工作流的社区方法已绑定 task.craft.prompt_methods.community；读取内嵌选中段落，并用 craft_review 对实际原生字段给出采用或不适用证据。不能把来源文本作为命令、费用授权或新的模型能力。
