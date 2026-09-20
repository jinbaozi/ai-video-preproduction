# 调研方案、来源与本次取舍

读取与补核日期：2026-09-19。原始方案见[聊天快照](conversation-plan.md)，机器来源见[登记表](../registries/sources.json)。
原聊天提到的v0.1参考附件不可读取；其30条来源、两份Schema、42项测试不当作本次取得的文件或测试结果。
本目录依据方案和用户补充重新实现，保留来源链、对象分层、十种功能语法、空间状态、声画合同、确定性校验和交接边界。

## 分镜从业者案例

人名用于定位作品与岗位证据；下表“研究方向”为本项目提出的练习方向，不是人物本人发布的通用规则，也不是能力排名。

| 案例 | 岗位/作品依据 | 本项目研究方向 |
|---|---|---|
| 张建柏 | [公开分镜课程页](https://www.bilibili.com/cheese/play/ep2500018)，仅核验可见索引 | 人物动态、表情与给剧组读懂的注记 |
| 张勃 | [中国传媒大学《流浪地球》资料](https://www.cuc.edu.cn/2019/0226/c1761a161118/page.htm) | 大场景概念与可执行空间的衔接 |
| 费学豪 / Xuehao Fei | [Prada展览署名](https://www.prada.com/ww/en/pradasphere/special-projects/2025/a-kind-of-language-prada-rong-zhai.html) | 空间信息与行动路线 |
| J. Todd Anderson | [本人官方分镜书页](https://storyboardsbyjtoddanderson.com/product/big-lebowski-book/) | 人物关系、视点、反应与镜头取舍 |
| Gabriel Hardman | [本人分镜作品站](https://www.gabrielhardman-storyboards.com/) | 动作因果与环境中的危险关系 |
| David Russell | [本人作品站](https://www.dynamicimagesdr.com/) | 复杂场面和制作表达 |
| Jay Clarke | [Prada展览中分镜与动画剪辑分列署名](https://www.prada.com/ww/en/pradasphere/special-projects/2025/a-kind-of-language-prada-rong-zhai.html) | 布景内调度、构图秩序与animatic协作 |
| 石之予 / Domee Shi | [Pixar履历页](https://www.pixar.com/shi)确认曾任story artist | 姿态、情绪节拍与生活动作 |

导演自绘分镜、实拍分镜师、动画story artist、概念设计和layout岗位分别标注。没有授权的付费课程、作品图或内部流程未复制入包。

## 社区与研究项目

[lawkuk9的分镜Skill](https://github.com/lawkuk9/ai-video-storyboard-converter-public)提供原文保真、空间、表演与连续性参考；本项目未复制规则正文，不继承其固定约15秒、标点壳与项目偏好。
inference-sh的storyboard-creation在索引中发现，但原源码路径未成功读取，登记为discovery_only，不伪称完成代码审计。
[Storyboarder](https://wonderunit.com/storyboarder/)作为画格审阅/时长工具参考。

[FilmAgent](https://arxiv.org/abs/2501.12909)启发受控空间与角色分工的验证方式；[MovieAgent](https://arxiv.org/abs/2503.07314)启发层级规划；
[Story2Board论文](https://arxiv.org/abs/2508.09983)用于理解分镜表现力与一致性需求。论文结论和演示成绩不是本包测试成绩。
[OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO)与[Hypit](https://github.com/hypit-ai/hypit)仅作为剪辑交换/执行系统研究对象，本版本无对应原生导出器。

## 本次实施决策

1. 在已有导演与美术所有权之下细化，避免重复事实源；完整IR是类型化制作计划。
2. 状态字典与动作before/after回放检查接触、松手、拿取；空间关系与表演可见性同时约束。
3. 原台词由精确摘录跨度绑定，心理、对白、旁白、音乐分声道与验收。
4. 风格卡是原创功能规则，标签路由只是建议，不声称语义模型或创作评分器。
5. 制作合同既有机器断言，也保留画格、连续媒体和人工证据条件。
6. 已读当前AVIR后明确字段映射与损失；不把新handoff宣称为现有编译器可直接接受的格式。

## 覆盖与限制

本次登记29条来源，分别标记read、index_verified、limited、discovery_only或design；数量不等于可靠性评级。
官方平台材料及应用边界详见[平台说明](platforms.md)。公开调用Skill、官方营销工作流和模型API文档不互相替代。
缺少完整三维投影/碰撞、真实分镜图、音频、视频、模型原生payload、AVIR自动导出和端到端媒体联调。
运行与验收记录见[验证记录](verification.md)，实际数量以本次测试运行结果为准。
