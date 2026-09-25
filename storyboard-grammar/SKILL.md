---
name: storyboard-grammar
description: >
  将指定原文、导演意图、美术方案及参考资产制作成有来源的叙事节拍、三维调度、
  镜头与画格、可见表演、声画时序和连续性合同，并离线校验、编译为StoryboardIR交接包。
  用于专业分镜制作、分镜修订和一致性审查；具体模型提示词适配与媒体生成交由执行层。
metadata:
  version: "1.3.1"
---

# Storyboard Grammar

## 当前执行合同

按任务读 [当前执行合同](references/current-contract.md) 的「空间」「动作」「摄影机」「声音」。本技能落实可剪接的镜头、时序和连续性。历史增量在 `references/history/`。


把导演意图和视觉世界落实为可见、可执行、可剪接、可验收的分镜制作规格。
默认中文；保留用户语言、原文台词、指定范围、实体ID、真实素材文件名和既有决定。
本包的 StoryboardIR / StoryboardHandoff 是版本化项目协议，不是行业标准或厂商API。

## 任务尺度与边界

- 单镜或小段分镜：Agent直接写可用正文与必要合同，不强迫用户填写JSON。
- 完整制作包：Agent完成语义拆解与结构化，CLI做确定性检查和派生输出。CLI没有自然语言自动解析器。
- 已有导演/美术方案：先读实际文件和Schema。宿主持有Canon、资产与批准；导演持有意图和已锁机位/表演，美术持有视觉世界；分镜只细化未锁定部分。见[所有权与集成](references/ownership-and-integration.md)。
- 仅审查：给出来源位置、失败字段、影响镜头和最小修订，不重写已通过部分。
- 图像、视频、音频生成不在本包CLI内；用户另行要求时，由宿主沿用已有授权调用实际工具。静态交付不要求新增生成许可。

## 工作路径

1. **定位与范围。** 读取原文、上游与实际参考，记录URI、版本、定位、摘录及哈希。只处理指定集/场/镜头。区分原文事实、观察事实、设计补充和未核验资料；后者不能承载硬要求。见[工作流](references/workflow.md)。
2. **节拍与语法。** 拆行动、反应和信息变化，建立覆盖与前置关系。把风格拆为视觉媒介 × 叙事语法 × 交付画幅。读取[语法索引](registries/style-index.json)后只加载选中卡；`route`只是可解释标签建议。硬约束优先于风格。
3. **空间与镜头。** 先做世界布局、人物/道具对应、行动轴和起止状态，再设计构图、机位与画格。世界左右、画面左右和人物自身左右分开。读[空间与构图](references/spatial-composition.md)及[镜头语言](references/shot-language.md)。
4. **动作与表演。** 写触发→微反应→准备/重心→路径/接触→对手反馈→收束。微表情仅在可读景别承担信息；心理先转可见行为。读[表演与动作](references/performance-action.md)。
5. **声画与合同。** 台词、画外对白、旁白、内心独白、环境声、动作声、音乐和静默分别归属、计时、指定执行渠道。每条制作要求连通来源、字段、所有者、强度、执行与验收。读[声音](references/audio.md)和[制作合同](references/production-contract.md)。
6. **检查并编译。** 对照[字段指南](references/ir-guide.md)和[完整示例](examples/cafe.ir.json)建模，运行`inspect`与`compile`。修复结构错误；缺少硬参考的交接标为BLOCKED。用[连续性与QA](references/continuity-and-qa.md)检查语义与不可自动验证项。
7. **交接与修订。** 交付分镜、画格说明、制作合同、时序计划、QA、损失和哈希清单。按[编译说明](references/compilation.md)把当前IR交给宿主映射到实际AVIR；不是把handoff直接塞入下游CLI。改源后增加revision并用新输出目录，原所有者决定变更，已有用户决定无需重问。

## 必须保留的制作语义

- Scene、Beat、Shot、Panel、GenerationJob、Take、EditSegment分别建模；一个镜头可以多画格，一次生成也可以多镜头。不按附件数量或模型默认秒数拆故事。
- 每镜回答：跟谁看、观众获得什么、谁行动谁反应、为什么移动相机、为什么在此切镜。
- 状态表保留画外人物与道具；换景别不等于人物瞬移。支撑、接触、手别、视线与持物归属可回放。
- 表演与构图相互约束：看不到的眼睑变化不能承担关键剧情；细节服务源剧情与时长，不为填字段新增情节、道具、对白或特效。
- `说话人：“台词内容”`进入分镜正文；原文发声类型和归属不变。静默心理不能变旁白，旁白不能变成画内人物口型。
- 主体身份、服化道、场景拓扑、原文信息顺序、光源和资产版本跨镜核对。允许主观/时间跳转时逐条写理由与状态例外。
- 坐标、焦距、速度和表情时点先是制作意图。精确几何由参考/预演/实际拍摄等渠道约束；媒体结果仍需审查。

## 离线命令

Python 3.10+；在本Skill目录执行，依赖见`requirements.txt`，不需要模型或GPU：

```bash
python scripts/storyboard.py route "悬疑 竖屏 人物对话"
python scripts/storyboard.py inspect examples/cafe.ir.json
python scripts/storyboard.py compile examples/cafe.ir.json --out outputs/cafe-v001
python scripts/storyboard.py verify outputs/cafe-v001
python -m unittest discover -s tests -v
```

有效静态包的`execution_ready=false`、`submitted=false`、`visual_qa=NOT_RUN`。
QA区分结构PASS与画格/媒体/人工NOT_RUN；不能用测试通过替代已出图、已配音或已成片。

平台选择时读[平台与执行边界](references/platforms.md)；核查研究依据时才读[调研与证据](references/research.md)。

## 独立使用与V5协作

细化未锁定镜头、画格、时序和连续性；不得改写上游锁定机位、身份、台词。compiler-handoff仍不是AVIR，协作转换由V5宿主执行。

独立任务直接接受用户资料；完整制作包可被总工作流导入并复用。协作任务先读取任务信封、来源与锁定项，只有当前范围需要的参考才加载。具体交接见[协作契约](references/cooperation-v5.md)。
