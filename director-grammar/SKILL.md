---
name: director-grammar
description: >
  将视频创意、剧本、参考素材或已有分镜转成导演级镜头与制作合同，按任务选择叙事、
  构图、三维空间、人物调度、表情动作、摄影和声音方法，并编译为可追溯的平台提示词、
  执行计划与验收条件。适用于单镜头、短片、短剧、动作展示、商品演示和镜头修订；
  不把提示词编译当作实际视频生成或成片验收。
metadata:
  version: "1.3.0"
---

# Director Grammar

## V5.2 运动与动态空间入口

先读 [运动、动态空间与无损交接合同](references/spatial-contract-v52.md)。完整制作使用原生 1.2，明确相对描述与有依据数值并用；不伪造坐标、速度或几何结论。角色整体、部位、物件、摄影机与环境分别登记运动属性、朝向和时段构图；画格按时刻求值。逐项细节进入正文或明确执行渠道，已拆动作不合并，未知边界和姿态返回补齐任务。独立轻量任务直接交付正文，合作任务复用相同规则。

## V5.1 细节保真入口

先读 [细节、时序与交付合同](references/detail-contract-v51.md)。本 Skill 仍可单独运行；轻量任务直接交付正文，不要求完整项目或用户填 JSON。
新完整制作默认使用原生 1.2 协议（有原生影视 IR 的技能）；旧 1.0、1.1 包继续走对应验证与编译分支。读取旧包不等于达到新版细节标准。
已确定的动作、表情、视线、接触、支撑、控制权和运镜阶段逐项保留。每条声音保留起止时间、原文、归属、口型与执行渠道；不得将后期对白自动变成画内说话。
根据实际依赖读取完整上游字段，不用摘要替代。脚本结构检查与当前 Agent 语义复核分开，复核绑定完整内容指纹。普通修正无需新增用户批准。


把“观众需要看懂什么”落实为有来源、有结构、有约束、有执行路径、有验收条件的制作合同。
先决定信息与行为，再决定人物位置、构图和摄影机。默认简体中文；保留用户指定语言。
DirectorIR / ExecutionIR 是本技能的项目协议，不是影视行业统一标准。

## 工作尺度

- 单镜头或只要提示词：输出该镜头的可复制正文；必要限制简短说明。可以在内部用合同检查，不强制创建整套项目文件。
- 要求可编译制作包：建立完整 DirectorIR，校验后编译 ExecutionIR、提示词、合同及待验收记录。
- 已有视频修订：先查看实际素材与失败时间码，只修改造成失败的字段；保持无关素材和授权有效。
- 动作教学、舞蹈、商品与建筑展示：以动作可读性或展示证据为目的，不能强加冲突、反转或对白。

## 按需读取

| 当前问题 | 读取资源 |
|---|---|
| 确定交付、场景节拍和制作顺序 | [workflow.md](references/workflow.md) |
| 构图、三维空间、轴线、相对位置 | [spatial-composition.md](references/spatial-composition.md) |
| 表情、眼神、手部、动作与对白 | [performance.md](references/performance.md) |
| 选择风格、运镜与镜头表达 | [style-and-camera.md](references/style-and-camera.md) |
| 制作合同、来源与变更边界 | [production-contract.md](references/production-contract.md) |
| 填写两级 IR 和运行工具 | [compiler.md](references/compiler.md) |
| 目标平台表达与限制 | [platforms.md](references/platforms.md)，只读目标条目 |
| Hypit 本地素材装配 | [hypit.md](references/hypit.md) |
| 实际素材、最终成片和局部修复 | [quality-and-repair.md](references/quality-and-repair.md) |
| 接入已有总技能及 Canon | [integration.md](references/integration.md) |
| 核实外部知识或平台事实 | [sources.md](references/sources.md) 与 registries/evidence.json |

不要启动时加载全部导演、平台和技法。三类核心注册表是 `styles.json`、`techniques.json`、
`capabilities.json`；`directors.json` 是20位导演的检索别名，`evidence.json` 是证据索引。

## 执行规则

1. 先读用户输入、实际参考文件和上层 Canon。记录事实、用户锁定项、设计补充与未核验项；不把推断写成已观察事实。
2. 按“任务 → 观众目标 → 必须可见的证据 → 人物行为与空间 → 风格/技法 → 平台”规划。一个场景用一个主风格；辅助技法须不冲突。用户明确要求融合时按维度解释并检验。
3. 每个镜头要有用途、触发、行动、反馈和可见终态。摄影机、人物、道具各写各的轨迹；镜头移动要说明新看到什么或注意力为何改变。
4. 世界坐标与画面位置分开；机位位置、高度、观察点、俯仰意图、roll、人物朝向、头部和视线分开。明确遮挡、接触、支撑、重心与道具归属。
5. 微表情只写在能看到的景别与角度中。远景、背面或遮挡镜头改用可见身体行为。面部、手、脚或道具是关键证据时，构图与运动终点都必须保留它们。
6. 同一镜头、同一实体、同一参考维度只有一个胜出来源。保留真实文件名、稳定资产 ID、版本/哈希和入口槽位。未知槽位写 `UNRESOLVED` 并阻止依赖提交。
7. 按具体产品入口、模型、模式和文档快照适配。数值焦距、米级路线、坐标、FPS、像素是设计意图，除非入口有可验证控制且结果通过验收。
8. 合同中的硬要求不能被风格、平台限制、提示词截断或自动修复覆盖。无法保留时输出具体阻塞、影响和可选修订；继续不依赖它的工作。
9. 冻结 IR 后，编译器确定性转换，不让 LLM 静默润色编译输出。润色或剧情/素材变更必须生成新 revision 并重编译。
10. 本包工具只做本地规划、编译、校验及 Hypit 源导出，没有提交/上传/支付命令。后续实际生成沿用用户已授权范围；仅在新增费用、权限或重大变更时补齐必要决定。

## 本地运行

以下命令在本技能目录执行，Python 3.10+。首次将依赖装在项目虚拟环境中：
引用图像解码、实际视频QA和Hypit导出还需本机ffmpeg/ffprobe；纯文本规划不需要它们。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/dg.py route examples/teahouse.director.json
.venv/bin/python scripts/dg.py validate examples/teahouse.director.json
.venv/bin/python scripts/dg.py compile examples/teahouse.director.json --target minimax-hailuo-2.3-t2v --out outputs/tea-v001
```

非空输出目录会被拒绝，修订用新目录。退出码：0=当前静态操作完成，2=INVALID/BLOCKED，1=输入/工具错误。
`PLANNED` 只表示静态计划成立；`submitted=false`、G3/G4=`NOT_RUN` 会保留在编译回执中。

交付前检查：来源与约束对应、必须可见证据、起止状态、提示词与附件、平台损失、实际验收的待办/结果。
实际媒体不存在时交付前期包并明确边界，不能生成虚假的 Take、审片通过、成功率或成本数据。

## 可复用资源

- `schemas/`：DirectorIR、制作合同、ExecutionIR、QA 和 Take 选择清单。
- `examples/teahouse.director.json`：15秒信息差与接触动作，4/5/6秒为剪辑预算。
- `examples/demonstration.director.json`：6秒全身步法教学，不添加叙事冲突。
- `examples/missing-reference.director.json`：缺失首帧的合法规划，I2V编译必须阻塞。
- [制作合同模板](templates/production-contract.md)：人类可审阅版本；机器合同从示例按 Schema 改写。
- `tests/test_dg.py`：非法输入、路由、编译、降级与证据门禁的行为回归。

同一来源固定数据、注册表及编译器版本应产生相同结果；测试通过只证明这些行为。
完整交付状态与本次证据见 [verification.md](references/verification.md)。

## 独立使用与V5协作

决定意图、信息顺序、关键表演与已锁定镜头；分镜细化未锁部分。独立使用保留现有compile与导出命令；协作模式的最终视频提示词统一交给video-prompt-compiler。

独立任务直接接受用户资料；完整制作包可被总工作流导入并复用。协作任务先读取任务信封、来源与锁定项，只有当前范围需要的参考才加载。具体交接见[协作契约](references/cooperation-v5.md)。
