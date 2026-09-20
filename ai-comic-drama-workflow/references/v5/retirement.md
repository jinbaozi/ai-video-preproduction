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
旧脚本、Schema、参考资料和dists仍在原目录；原SKILL及完整源码/发行包另以固定元数据ZIP冻结在工作区archive，附逐文件清单和SHA-256。本次没有删除旧项目，没有重新打包旧技能发行物。

V4源实现和workflow-graph.json保留，V5单独使用workflow-v5.json与v5-*协议。旧总工作流编译器不参与V5运行。导演原独立compile/export兼容保留；组合流程的新平台适配只走video-prompt-compiler。

迁移是保留原件、检查来源、复用内容并建立新交接记录，不是把旧字段机械改名后宣称语义或媒体已经通过。V4和旧YAML项目的复制迁移已由回归测试覆盖；历史APPROVED字符串不会生成新批准。
