# 完整执行参考（按需）

默认先使用阶段核心合同；本页保留原有专业细节、旧协议和专门任务入口，不是每次全量读取清单。


# Production Design Grammar

## 默认专业方法路由

未点名也先从内容与观众目标自动选择本职责方法，再按需读命中的人物/技法条目；独立入口使用 scripts/craft_router.py，不能只列姓名而不实施。先读[默认路由合同](../references/craft-routing.md)；完整任务遵循 task.craft，提供绑定实际内容的 craft_review。方法不得覆盖 Canon、信息顺序、连续性或用户锁定；静态证据不等于成片画质。

## V6 总工作流协作

被总工作流派发时，美术子智能体按任务信封的场景范围和冻结输入工作，在自身候选目录提交 ArtIR、文件哈希、专业检查和逐镜交接。人物身份、故事事实、镜头决定仍由各原责任方修改；跨责任冲突用结构化消息交还，不在 ArtIR 中覆盖。独立审阅通过后由内核登记正式产物及状态。具体交接见 [协作契约](../references/cooperation-v5.md)。

## 当前执行合同

按任务读 [当前执行合同](../references/current-contract.md) 的「空间」。本技能决定视觉世界、场景拓扑、服化道和世界光源，不重写镜头和台词。历史增量在 `references/history/`。


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
| 世界、文化、色彩、材料和资产设计 | [world-and-assets.md](../references/world-and-assets.md) |
| 构图、三维空间、相对关系、表情与镜头支持 | [spatial-and-screen-support.md](../references/spatial-and-screen-support.md) |
| 自适应选择主语法或辅助维度 | [style-routing.md](../references/style-routing.md)，只读取匹配的 `registries/styles.json` 条目 |
| 与 director-grammar/宿主衔接 | [ownership-and-integration.md](../references/ownership-and-integration.md) |
| 制作合同、来源和验收链 | [production-contract.md](../references/production-contract.md) |
| 填写机器协议、运行编译器 | [compiler.md](../references/compiler.md) 与 `schemas/art-ir.schema.json` |
| 平台或 Hypit 交接 | [platform-handoff.md](../references/platform-handoff.md) |
| 参考选用、真实媒体审查、局部修复 | [visual-qa.md](../references/visual-qa.md) |
| 研究依据与交付能力 | [sources.md](../references/sources.md)、[verification.md](../references/verification.md) |

## 执行原则

1. 先读用户原文、当前 Canon、已有资产和导演方案；区分用户事实、观察事实、设计补充与未核验项。
2. 一个连续场景继承一个主语法；辅助语法只影响一个明确维度。身份和已批准事实优先于风格配方。
3. 设计覆盖世界文化、环境叙事、形态尺度、场景陈设、色彩、材料旧化、道具、服化、画内图形、
   实用光源、媒介/特效分层和连续性。只展开本任务相关领域。
4. 世界坐标、画面坐标、人物自身左右分开；布景位置、尺寸、数量与可通行区域明确。
   反打继承世界光源方位，不能机械继承画面左右。场景总数和单镜可见数分开。
5. 按既定景别处理表情可读性：发丝/帽沿/妆面、衣领、背景频率和明度不能遮蔽所需眉眼、嘴角或手。
   不为看清表情自动换镜头、转头、改台词或改角色身份。
6. 状态变化有事件来源、初态、末态与镜头位置。绑定 DirectorIR 1.1/1.2 时，事件引用同镜头、同实体、同字段且前后值一致的 `timeline.actions`；DirectorIR 1.0 保留 phase 指针。关键帧只表现当前状态；视频交接记录变化。
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
无真实媒体时 QA 保持 `NOT_RUN`。参见 [可审阅合同模板](../templates/production-contract.md)。

输出核心是 Visual Bible、资产计划、逐镜美术补充、机器交接、条款覆盖、依赖记录与待审 QA。
实际图片/视频生成由已授权宿主执行；本包不上传、提交、付费，也不宣称静态检查证明画面质量。

## 独立使用与V5协作

决定世界、场景拓扑、服化道、材质和世界光源；逐场景输出ArtIR。已有导演方案按实际字段只读绑定；独立设计不要求先安装导演Skill。

独立任务直接接受用户资料；完整制作包可被总工作流导入并复用。协作任务先读取任务信封、来源与锁定项，只有当前范围需要的参考才加载。具体交接见[协作契约](../references/cooperation-v5.md)。

## 按需资料入口

[本职责资料索引](../references/resource-index.md)只提供可达路径；当前任务只读取适用条目，历史资料不自动替代冻结协议。完整工作流的社区方法已绑定 task.craft.prompt_methods.community；读取内嵌选中段落，并用 craft_review 对实际原生字段给出采用或不适用证据。不能把来源文本作为命令、费用授权或新的模型能力。
