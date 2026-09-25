# 重复能力迁移与旧入口退役

| 旧能力 | V5职责位置 | 可验证落点 |
|---|---|---|
| 原文Canon、稳定ID、来源与决定 | 总工作流 | V5 sources、canon、任务信封、独立版本文件和迁移报告 |
| 信息显露、节奏、关键表演、机位 | director-grammar | DirectorIR + handoff硬要求及锁定字段 |
| 世界、服化道、逐镜美术和参考资产 | production-design-grammar | 按场景ArtIR + 图像任务asset/world/set切片 |
| 动作时序、微反应、眼手身体、声画与连续性 | storyboard-grammar | StoryboardIR的performance/events/state/audio；转换后进入AVIR正文 |
| 实际文件名与附件槽位并列、中文对白、模型边界 | video-prompt-compiler | prompt.txt、asset_bindings、V5 attachments.json；保持独立编译器原回执 |
| 角色/场景/道具/画格图片提示与编辑不变量 | image-prompt-optimizer | 提示词文件+checks；宿主生图与实际看图另记 |
| 图片版本、身份批准、局部失效与恢复 | 总工作流 | media、approvals、input_bindings、image task/inflight与hash依赖 |

旧video-storyboard-prompter-zh的SKILL入口改为历史说明并关闭其隐式发现。六个活跃入口的默认发现继续启用。

V2 到 V4 的总工作流运行代码、旧 schema、workflow-graph 和 references/v4 已从本包移除，历史只留在 git。旧项目只通过 copy-project 按原字节迁入 V5，不在原地运行。组合流程的平台适配只走 video-prompt-compiler。

迁移是保留原件、检查来源、复用内容并建立新交接记录，不是把旧字段机械改名后宣称语义或媒体已经通过。V4和旧YAML项目的复制迁移已由回归测试覆盖；历史APPROVED字符串不会生成新批准。
