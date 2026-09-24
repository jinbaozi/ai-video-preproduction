---
name: video-prompt-compiler
description: >
  将视频创意、剧本、分镜及多模态参考转换为类型化AVIR制作合同，经Context-IR整理、
  空间表演与连续性检查，编译为Seedance 2.0/2.5、Agnes Video 2.5、Kling 3.0/Omni等
  模型的专属提示词、参数、引用绑定和验收清单。用于提示词生成、跨模型迁移、编译诊断与制作交接；
  编译与实际视频生成分开。
metadata:
  version: "1.15.0"
---

# Video Prompt Compiler

AVIR 1.2 保留独立的来源、镜头、动作、空间、声音与状态合同。完整项目 `prompt.txt` 是审阅用的全长模型正文；实际逐次投喂选用按目标时长生成的 `prompt-序号_起止ms.txt`。每份独立文件重述本段所需真实图片文件名、引用职责、场景、身份及逐镜/逐时段细节；跨段后期声音另附对应 `post-序号_起止ms.txt`。`production-specification.json`、`detail_blocks` 与 `detail-coverage.json` 是完整审计依据；`prompt-coverage.json` 指向全长正文，`segment-delivery.json` 记录逐段状态。字节覆盖不等于语义等价或模型已执行。

## 镜头控制资产与关键帧

复杂走位、联合运镜、接触或连续关键帧任务，读取 [镜头控制合同](references/shot-control.md)。复用 AVIR 权威轨道，派生三视图、事件关键帧请求和控制包；真实文件、绑定和媒体验收分开记录。普通单图与单条提示词继续轻量处理。

## V5.2 运动与动态空间入口

先读 [运动、动态空间与无损交接合同](references/spatial-contract-v52.md)。完整制作使用原生 1.2，明确相对描述与有依据数值并用；不伪造坐标、速度或几何结论。角色整体、部位、物件、摄影机与环境分别登记运动属性、朝向和时段构图；画格按时刻求值。逐项细节进入正文或明确执行渠道，已拆动作不合并，未知边界和姿态返回补齐任务。独立轻量任务直接交付正文，合作任务复用相同规则。

## V5.1 细节保真入口

先读 [细节、时序与交付合同](references/detail-contract-v51.md)。本 Skill 仍可单独运行；轻量任务直接交付正文，不要求完整项目或用户填 JSON。
新完整制作默认使用原生 1.2 协议（有原生影视 IR 的技能）；旧 1.0、1.1 包继续走对应验证与编译分支。读取旧包不等于达到新版细节标准。
已确定的动作、表情、视线、接触、支撑、控制权和运镜阶段逐项保留。每条声音保留起止时间、原文、归属、口型与执行渠道；不得将后期对白自动变成画内说话。
根据实际依赖读取完整上游字段，不用摘要替代。脚本结构检查与当前 Agent 语义复核分开，复核绑定完整内容指纹。普通修正无需新增用户批准。


交付有来源、有结构、有约束、有执行路径、有验收条件的视频制作合同。
默认中文，保留指定语言、真实素材文件名、角色ID、原文台词及已确定模型。
AVIR与本地Context-IR是本技能的项目协议，不是厂商协议或行业标准。

## 按任务尺度工作

- 单条提示词：当前Agent读取输入和实际参考，做语义检查，直接给可复制正文；不强制用户填写JSON或创建项目包。
- 完整编译包：Agent将输入整理为`avir/1.2`（旧包保留 `avir/1.0`、`avir/1.1` 分支），CLI负责确定性检查、Context投影、后端转换与合同输出。
- 已有导演/美术方案：读取原文件和版本，按[集成映射](references/integration.md)导入；不重新决定已锁定身份、剧情、美术或镜头。
- 修订：定位失败字段、时间码或素材，更新AVIR revision后重编译，保留旧构建对比和回放。

CLI不提供任意自然语言自动解析器；语义前端由使用本Skill的Agent承担，结构通过不证明语义正确。

## 工作路径

1. **来源与合同。** 读用户原文、实际参考和上游协议。区分用户要求、观察事实、设计补充、优化建议及未核验信息。每条硬要求有来源、字段断言、执行渠道和可观察验收条件。只问影响范围、正确性或重大副作用的缺项。
2. **建立AVIR。** 从[字段指南](references/avir-and-contract.md)及`examples/teahouse.avir.json`改写。相关内容各有归属：主体、场景、构图、三维空间、相对位置、空间人物对应、镜头表达、表情与微表情、动作细节、连贯性、音乐、台词、心理活动、旁白。不相关内容允许空数组/null，不为填表新增剧情。
3. **中端整理。** 校验权威Core，按镜头筛选角色/参考，核验时间、部位可见性、视线、轴侧、道具归属与相邻起止状态；只去除完全相同的风格词。扩写与Core分开，见[中端优化](references/passes-and-optimization.md)。
4. **选择后端。** 尊重指定模型；未指定时按硬要求提供候选与理由。只读对应[模型参考](references/models/index.md)。API、网页、第三方渠道分开；未知槽位用`UNRESOLVED`，不猜Seedance/Kling上传语法。
5. **编译。** 冻结AVIR，分别生成完整审计投影与按镜头/时间排列的模型正文，再按目标 profile 的单次最大时长、最小时长和离散时长规则生成独立提示词文件。每段重新投影其全部执行细节与参考，不从全长文件截字；逐项动作与运镜不合并。边界缺关键姿态或穿过未拆分动作时保留正文但标 `BLOCKED`，不得当作可投喂片段。后期声音另附本段交接，不改成原生对白。模型布局与交付判定见[正文投影](references/model-prompt-projection.md)。
6. **验收交接。** 运行受影响检查，并由当前Agent逐项对照来源、AVIR与每个 `prompt-*.txt`，复核真实图片名与职责、手别、持物、可见性、否定、声音归属和跨镜连续性；记录输入与成稿指纹及发现，不能用覆盖表代替语义判断。无媒体时QA为`NOT_RUN`；宿主沿用既有授权执行，按[验收流程](references/evaluation-and-runtime.md)回收证据。只在新增必要决定时询问。

## 保留的语义

- 参考是`asset → role → subject/scene → shot`，同时保存禁止继承维度。真实文件名、ID、哈希和槽位并列；只参考运镜不能改变人物或场景。
- 世界坐标、画面位置、人物自身左右分开；摄影机、人物、道具分别有运动路径。机位、观察点、身体朝向、头部和视线不能混写。
- 动作写出触发→微反应→准备/发力/重心→路径/接触→反馈→结束状态。细节须在景别与时长中可读；背面、远景不要求眉眼微表情。
- 心理先转成可见行为；明示内心独白才进入声音轨。台词格式`说话人：“台词内容”`，不改词、改归属或新增旁白。
- 硬要求不因超长、风格或平台限制而静默丢失。超限保留完整草案，报告阻塞或有依据的分段/后期方案；不自动缩时长、改模型或截断文字。
- 摄影数值、坐标及精确动作时点是意图；除已核验原生参数外，不宣称模型提供精确控制。`canonical_count`是CPT-v1预算单位；`native_count=null`表示未知。
- 冻结后的转换不让LLM自由改写；新语义、素材或规则变动产生新版本和清单。

## 本地命令

在本技能目录执行，Python 3.10+。已有满足`requirements.txt`的环境可直接用；否则创建项目虚拟环境。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/vpc.py profiles
.venv/bin/python scripts/vpc.py validate examples/teahouse.avir.json
.venv/bin/python scripts/vpc.py compile examples/teahouse.avir.json --target agnes-video-2.5 --out outputs/tea-v001
.venv/bin/python scripts/vpc.py batch examples/batch.ndjson --out outputs/batch-v001
.venv/bin/python scripts/vpc.py verify outputs/tea-v001
.venv/bin/python scripts/vpc.py replay outputs/tea-v001 --out outputs/tea-replay
.venv/bin/python -m unittest discover -s tests -v
```

输出目录必须为空。AVIR 1.2 的 `segment-delivery.json` 列出逐段文件、参考清单、哈希与阻塞原因；`BLOCKED-prompt-*.txt` 是保真草案，不能作为已通过切点检查的提示词投喂。全长项目超目标单次时长时，顶层 `prompt.txt` 仍保留供审计，不能直接复制给模型。退出码0=静态操作成功；2=INVALID/BLOCKED；1=输入或工具错误。
`COMPILED`表示提示词编译完成；所有执行回执固定`submitted=false`、`runnable=false`。
Agnes可生成API字段草案；其余已核验模型生成提示词计划与独立制作参数意图，不是已验证API载荷。

## 按需资源

| 情境 | 读取 |
|---|---|
| 来源、字段、制作合同 | [AVIR与合同](references/avir-and-contract.md) |
| 构图、空间、表情、动作、镜头、声音 | [视听语法](references/audiovisual-grammar.md) |
| Context、RAG、预算、扩写、版本 | [中端优化](references/passes-and-optimization.md) |
| 模型与渠道 | [模型索引](references/models/index.md)，再读当前目标 |
| 模型正文布局与字段覆盖 | [正文投影](references/model-prompt-projection.md) |
| 导演、美术与旧分镜 | [集成映射](references/integration.md) |
| 生成交接、QA、A/B、局部修复 | [验收与执行](references/evaluation-and-runtime.md) |
| 原报告、来源及实现取舍 | [研究映射](references/research-and-scope.md) |
| 已测能力与边界 | [验证记录](references/verification.md) |

机器契约在`schemas/`，能力/来源/规则在`registries/`，表达顺序在`templates/backends.json`。
示例均为合成夹具；缺参考例子用于验证阻塞，不能当作已存在图片。

## 独立使用与V5协作

协作模式是唯一模型编译出口；独立使用由当前Agent整理AVIR。冻结后不自由改写语义，不承担生图或视频提交。

独立任务直接接受用户资料；完整制作包可被总工作流导入并复用。协作任务先读取任务信封、来源与锁定项，只有当前范围需要的参考才加载。具体交接见[协作契约](references/cooperation-v5.md)。
