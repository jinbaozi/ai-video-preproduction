---
name: ai-comic-drama-workflow
description: "管理来源、原生阶段、依赖、异常和交付；默认单宿主连续执行，默认studio保留自动专业路由与质量证据，简化重复材料、Flow和剪映依赖，调用编剧、导演、美术、图像、分镜和视频编译。"
metadata:
  version: "0.20.2"
---

# 最小创意到视频流水线

## 默认执行

先读[核心合同](references/stage-core.md)，按“必要输入与锁定 → 原生创作 → 校验与交接”执行。简单任务不建立团队、额外计划或重复中间稿；完整流水线也使用同一核心流程。普通定稿自主完成，只在真实阻塞时通知用户。

输入是创意、原始资料、真实参考和目标入口。Canon只记录事实、身份、锁定及来源；不得把补充设计伪装成原文。

每阶段保持一个权威原生产物和原任务/结果收据；00-progress.md是进度入口，09-delivery/index.md是交付入口。新项目默认studio、最小上下文、自动专业路由、实际参考图与FFmpeg；制作任务读[studio手册](references/studio-production.md)。显式--profile lean保留旧默认；--context-profile audit保留完整宿主阅读要求，--profile audited使用既有独立审阅。旧项目不迁移。

## 新 studio 执行门禁

0.20.2 起新 studio 冻结 `studio-execution/1.0`。图片先有已接受的 Canon、ScriptIR、DirectorIR、相关 ArtIR 和图片提示词，再 `begin-image`，最后调用真实工具。结果必须绑定原执行记录和逐项实际视觉观察。优先通过 `execution_gate.dispatch_image` 接入宿主工具；异常保留 UNKNOWN，禁止凭“允许重试”清除原任务。见[执行门禁与图片终点](references/execution-gates.md)。

用户说“先做图片”时使用 `scope --stop-after images`；仅改变交付终点，不另开“独立探索”绕过当前项目的前置阶段。该终点交付第5阶段的必需美术参考与实际图片提示词，不冒充分镜图片或视频提示词验收。恢复使用 `scope --stop-after full`，复用已接受成果。独立探索不得自行升级为正式项目资产。

交付结论读取原生 `image-report` / `export`；DRAFT、候选、过期与正式验收分开。隐藏问题区域只减少当前画幅的验证范围，不等于修复了原空间或动作。不得自行放宽验收标准。代码门禁不能拦截宿主旁路工具或恶意改写本地存储；不得声称本技能已提供宿主级权限隔离。

## 默认专业方法与质量检查

已有原生输入先验证并复用，不重写锁定事实。studio默认开启craft-routing auto，保留专业选人、方法应用和craft_review，[名家、场景与技巧](references/craft-routing.md)按任务路由；不得以人名代替采用证据，不全库加载。硬约束、原文、真实附件、视听连续性、审计和异常处理不能因省token删除。没有真实生成/查看结果时，不宣称画质或视频交付通过。

## 按需深入

[全部资料索引](references/resource-index.md)只作检索入口；[完整执行参考](references/detailed-execution.md)保留专业细节与旧协议。复杂或专属任务只展开命中章节，原生schema/验证器仍是字段规则依据。

[自主执行与阻塞](references/autonomous-until-blocked.md) · [Flow 2K](references/flow-2k-reference.md) · [剪映交接](references/jianying-postproduction.md)。只在相关生产任务读取。

执行必须遵循[阶段质量与如实报告](references/stage-quality.md)：先审人物认知、动机、时间和物件来源，再制作资产；详细提示词、角色采用与原生阶段不得用聊天稿替代。
