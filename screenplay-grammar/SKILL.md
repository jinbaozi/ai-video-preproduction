---
name: screenplay-grammar
description: >
  独立创作或增强故事与剧本：支持一句话成稿、中文与国风创作、补全续写、润色扩写、
  改编、诊断和分集开发；按叙事问题选择方法，保留原文约束，可导出有来源的制作合同
  与导演交接包。适用于故事正文、分场剧本和局部改稿；镜头、调度和视频提示词由下游负责。
metadata:
  version: "1.0.0"
---

# Screenplay Grammar

用户要故事或剧本，就交付可读正文。当前 Agent 负责创作，脚本负责确定性检查与导出。
没有导演技能、视频模型、参考图、API 密钥，也能完成编剧任务。默认简体中文，尊重指定语言。

## 任务与工作尺度

1. 读取实际原文与已有决定，辨别新创作、故事、补全、续写、润色、扩写、改编、诊断或结构修订。只追问影响范围、正确性或重大变更的缺口。
2. 一句话创作请求默认直接写完整短篇，简述必要假设，不先要求用户填表或反复选择。故事用故事正文，剧本用分场、动作、对白；大纲不能替代要求的成稿。
3. 润色默认只改表达；补全与续写保留既有正文和出口状态；扩写增加过程而不偷换结果。诊断只指出证据、影响和修法。改编保留来源取舍记录。
4. 先选择一个适合当前问题的叙事主配置，再按需读取技法与中文题材规则。主风格是方法选择，作者姓名只是检索入口。不要为凑字段添加机关、疾病、秘密身份或反转。
5. 写作后检查人物目标、行动后果、认知来源、对白声音和用户保留项。克制、留白与开放结局可以成立，不能强制三幕、每场反转或短剧爽点。
6. 单段、单场和一次润色直接交付正文，必要时简述改动。长期项目、版本保护或导演交接才建立完整机器包。用户不用手工填写 JSON。

## 唯一职责

本技能决定故事事实、因果、人物选择、结局、台词、潜台词、人物认知与信息揭示约束。
剧情必要动作（藏钥匙、拒绝归还）属于编剧；手指如何发力、人物怎样走位、景别和机位属于导演。
导演可以换镜头，但不能把怀疑变成识破、把承诺变成讽刺。此类变化返回有来源与影响范围的编剧修订请求。
剧情声音、旁白、内心声与画面文字分别登记；不要把心理描述自动改成画内对白。
详见 [上下游边界](references/ownership.md)。

## 按需读取

| 当前任务 | 资源 |
|---|---|
| 一句话、故事、补全、续写、润色、扩写 | [写作入口](references/writing.md) |
| 中文对白、历史、武侠、仙侠、玄幻、志怪、古偶 | [中文与国风](references/chinese.md) |
| 长篇改编、剧集、续写状态与来源覆盖 | [长篇与剧集](references/long-form.md) |
| 因果、认知、结构、对白诊断与改稿 | [修订](references/revision.md)，只读选中的 `references/techniques/` 卡 |
| 风格选择、作者方法 | `registries/styles.json`、`registries/writers.json`；无需全部加载 |
| 项目主稿、工具、导出 | [协议与命令](references/runtime.md) |
| 来源、合同、验收、版本保护 | [制作合同](references/contract.md) |
| 导演与总工作流接入 | [交接](references/cooperation.md) |
| 研究出处、证据限制 | [研究来源](references/sources.md)、`registries/evidence.json` |

## 项目模式

`project.json` 是唯一可编辑主稿（ScriptIR）；`narrative-ir.json` 是只读投影。
来源、Canon 引用、人物、命题、事件、正文、合同、锁与改写权限形成同一版本。
外部 Canon 是项目事实与实体 ID 的权威；独立项目的 Canon 仅登记当前事实及来源。
角色台词、怀疑、误信、提案与事实不可混同；认知工具只检验显式建模的条件，不证明自然语言无矛盾。

编译前运行 `validate`，完成适合当前任务的语义复核。复核绑定内容指纹；改稿后旧复核失效。
未审草稿可以导出，必须保留 DRAFT 和未审状态；不能交接为已通过的制作剧本。
合同按“来源→要求→正文/事件→实现→执行步骤→检查→证据”闭环。评审是检查手段，不是剧情的实现渠道。

## 运行

Python 3.10+，依赖见 `requirements.txt`。脚本不调用语言模型、不上传、不生成媒体。

```bash
python scripts/sg.py init --project-id MY_STORY --title 我的故事 --brief '守灯人发现灯中住着昨日的自己' --out project.json
python scripts/sg.py route examples/lantern.project.json
python scripts/sg.py validate examples/lantern.project.json --final
python scripts/sg.py compile examples/lantern.project.json --out outputs/lantern-v001
python scripts/sg.py apply examples/keys.project.json examples/keys.patch.json --out outputs/keys-v002.json
python scripts/sg.py diff examples/keys.project.json outputs/keys-v002.json
```

初始化只建立待创作容器，不能当成成稿。`apply` 只替换已许可路径，生成新文件；不修改 Canon、锁和授权。
非空输出目录或已有目标文件拒绝覆盖。退出码 0=当前操作成功、2=校验/交接阻塞、1=输入或工具错误。
时长分目标、估计、实测；不按视频模型段长切剧情，不用字数估时冒充读演结果。

## 交付

轻量模式交正文；项目模式交正文、结构化快照、合同、来源映射、检查结果及可选导演交接。
新提案不伪装用户批准，历史断言不伪装核验事实，静态 PASS 不伪装专业盲评或媒体验收。
本包的验收范围见 [验证说明](references/verification.md)。
