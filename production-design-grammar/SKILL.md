---
name: production-design-grammar
description: >
  为影视、AI短剧、动画、产品展示设计可复用的视觉世界、场景空间、色彩材质、道具、服化与美术连续性，
  按风格编译有来源、约束、执行路径和验收条件的 ArtIR 美术制作合同。
  适用于视觉圣经、资产设计、美术提示词、参考审核及美术修订；构图、表情和镜头通过美术支持约束衔接
  director-grammar，不接管其叙事、表演、人物调度、摄影机或剪辑决策。
metadata:
  version: "1.3.0"
---

# Production Design Grammar

## V5.2 运动与动态空间入口

先读 [运动、动态空间与无损交接合同](references/spatial-contract-v52.md)。完整制作使用原生 1.2，明确相对描述与有依据数值并用；不伪造坐标、速度或几何结论。角色整体、部位、物件、摄影机与环境分别登记运动属性、朝向和时段构图；画格按时刻求值。逐项细节进入正文或明确执行渠道，已拆动作不合并，未知边界和姿态返回补齐任务。独立轻量任务直接交付正文，合作任务复用相同规则。

## V5.1 细节保真入口

先读 [细节、时序与交付合同](references/detail-contract-v51.md)。本 Skill 仍可单独运行；轻量任务直接交付正文，不要求完整项目或用户填 JSON。
新完整制作默认使用原生 1.2 协议（有原生影视 IR 的技能）；旧 1.0、1.1 包继续走对应验证与编译分支。读取旧包不等于达到新版细节标准。
已确定的动作、表情、视线、接触、支撑、控制权和运镜阶段逐项保留。每条声音保留起止时间、原文、归属、口型与执行渠道；不得将后期对白自动变成画内说话。
根据实际依赖读取完整上游字段，不用摘要替代。脚本结构检查与当前 Agent 语义复核分开，复核绑定完整内容指纹。普通修正无需新增用户批准。


把故事中的世界、身份与环境叙事落实为可制作、可追踪、可验收的美术设计。默认简体中文。
ArtIR 是本包的项目协议，不是影视行业通用标准；本包编译产物是离线交接文件。

## 先确定工作尺度

- 单件道具、单场景、单镜头补充：直接给所需设计/提示词与关键约束，不强制全项目合同。
- 完整美术包：世界与主语法 → 资产/空间/状态 → ArtIR → 校验 → 编译 → 实际素材验收。
- 已有图像或视频修订：先实际查看对应素材，记录失败位置，只调整导致失败的美术字段。
- 已有明确风格直接沿用；有实质分歧时给少量策略与取舍。不要每次强制三方案或重复确认。

## 分工不可混写

宿主持有 Canon、身份、资产ID、版本、授权与能力事实；`director-grammar` 持有叙事、镜头、构图、
表情动作、站位轨迹及剪辑。美术持有建筑/陈设、材料色彩、画内光源、服化外观和资产状态约束。

画面构图在这里指**如何布置可供构图的世界**；人物表情在这里指**如何使既定表情可见且身份稳定**。
不重新选择机位、焦距、人物情绪和表演时点。矛盾返回字段级变更建议，由原所有者处理。
没有导演数据时照常做美术；依赖导演的最终视频交接标记缺项，不伪造镜头。

## 按需阅读

| 当前工作 | 资源 |
|---|---|
| 世界、文化、色彩、材料和资产设计 | [world-and-assets.md](references/world-and-assets.md) |
| 构图、三维空间、相对关系、表情与镜头支持 | [spatial-and-screen-support.md](references/spatial-and-screen-support.md) |
| 自适应选择主语法或辅助维度 | [style-routing.md](references/style-routing.md)，只读取匹配的 `registries/styles.json` 条目 |
| 与 director-grammar/宿主衔接 | [ownership-and-integration.md](references/ownership-and-integration.md) |
| 制作合同、来源和验收链 | [production-contract.md](references/production-contract.md) |
| 填写机器协议、运行编译器 | [compiler.md](references/compiler.md) 与 `schemas/art-ir.schema.json` |
| 平台或 Hypit 交接 | [platform-handoff.md](references/platform-handoff.md) |
| 参考选用、真实媒体审查、局部修复 | [visual-qa.md](references/visual-qa.md) |
| 研究依据与交付能力 | [sources.md](references/sources.md)、[verification.md](references/verification.md) |

## 执行原则

1. 先读用户原文、当前 Canon、已有资产和导演方案；区分用户事实、观察事实、设计补充与未核验项。
2. 一个连续场景继承一个主语法；辅助语法只影响一个明确维度。身份和已批准事实优先于风格配方。
3. 设计覆盖世界文化、环境叙事、形态尺度、场景陈设、色彩、材料旧化、道具、服化、画内图形、
   实用光源、媒介/特效分层和连续性。只展开本任务相关领域。
4. 世界坐标、画面坐标、人物自身左右分开；布景位置、尺寸、数量与可通行区域明确。
   反打继承世界光源方位，不能机械继承画面左右。场景总数和单镜可见数分开。
5. 按既定景别处理表情可读性：发丝/帽沿/妆面、衣领、背景频率和明度不能遮蔽所需眉眼、嘴角或手。
   不为看清表情自动换镜头、转头、改台词或改角色身份。
6. 状态变化有事件来源、初态、末态与镜头位置。关键帧只表现当前状态；视频交接记录变化。
7. 每张参考有真实文件名、哈希、用途、可继承/禁止继承信息及权利说明。未读图不能声称视觉合格；
   缺文件标待制作，不伪造图片、上传ID或附件槽位。同镜同资产同维度只有一个权威参考。
8. 每条制作要求关联来源、ArtIR路径、执行渠道/任务和可观察验收项。硬要求不能因平台限制静默降级。
9. 冻结后用确定性编译；自由改写、素材替换或导演修订产生新版本并重编译。
10. 沿用用户已给的授权，仅对影响正确性、显著费用或重大变更的缺项提问；独立设计工作继续。

## 本地工具

Python 3.10+；`jsonschema` 负责完整 Schema 校验。真实参考/验收媒体检查需要 `ffmpeg` 与 `ffprobe`。
在本目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/art_compile.py route examples/tavern.art.json
.venv/bin/python scripts/art_compile.py validate examples/teahouse-linked.art.json
.venv/bin/python scripts/art_compile.py compile examples/tavern.art.json --target generic-keyframe --out outputs/tavern-v001
.venv/bin/python scripts/art_compile.py compile examples/teahouse-linked.art.json --target generic-video --out outputs/tea-v001
.venv/bin/python -m unittest discover -s tests -v
```

非空输出目录被拒绝。退出码 0=本次静态操作完成，2=INVALID/BLOCKED/NOT_ACCEPTED。
`PLANNED` 不等于可提交；所有目标固定 `runnable=false`、`submitted=false`。
无真实媒体时 QA 保持 `NOT_RUN`。参见 [可审阅合同模板](templates/production-contract.md)。

输出核心是 Visual Bible、资产计划、逐镜美术补充、机器交接、条款覆盖、依赖记录与待审 QA。
实际图片/视频生成由已授权宿主执行；本包不上传、提交、付费，也不宣称静态检查证明画面质量。

## 独立使用与V5协作

决定世界、场景拓扑、服化道、材质和世界光源；逐场景输出ArtIR。已有导演方案按实际字段只读绑定；独立设计不要求先安装导演Skill。

独立任务直接接受用户资料；完整制作包可被总工作流导入并复用。协作任务先读取任务信封、来源与锁定项，只有当前范围需要的参考才加载。具体交接见[协作契约](references/cooperation-v5.md)。
