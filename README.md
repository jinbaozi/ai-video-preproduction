# 七技能创意到视频

七个专业职责可独立交付，也可经一个入口组成流水线。每阶段保留核心功能、原生中间表示、交付物、审计和异常恢复。新lean使用最小上下文；编译不等于模型已执行，前期交付不等于成片通过。

## 一句话开始

```text
使用 $ai-comic-drama-workflow：成年旅人雨夜拾起信封，街灯由冷转暖，焦点从信封移向表情。
目标 Agnes Video 2.5。按默认最小流程连续完成，普通创作选择自行定稿。
只制作镜头使用的素材，保留身份、动作、光色、转焦、声音与连续性。
```

用户不填写JSON。宿主负责理解、创作、看图/审片与工具操作；程序负责状态、指纹、确定性校验和交接。缺实际权限、能力或必要媒体时报告阻塞，不自动改成文字交付。

## 每阶段最小闭环

**必要输入与锁定 → 自动方法路由 → 一个权威原生结果 → 校验、审计与交接。**

| 独立Skill | 核心功能 | 原生交付 |
|---|---|---|
| [总工作流](ai-comic-drama-workflow/SKILL.md) | 来源、状态、依赖、范围、异常恢复 | Canon、进度与交付索引 |
| [编剧](screenplay-grammar/SKILL.md) | 因果、人物认知、信息顺序、原句台词 | ScriptIR、必要来源映射 |
| [导演](director-grammar/SKILL.md) | 表演、运镜、视听意图、光色与转焦 | DirectorIR、导演锁定 |
| [美术](production-design-grammar/SKILL.md) | 身份/服装/道具/空间与光源 | ArtIR、按用途的资产需求 |
| [图像](image-prompt-optimizer/SKILL.md) | 输入理解、图像表达与参考控制 | 提示词、真实素材与审阅 |
| [分镜](storyboard-grammar/SKILL.md) | 动作、机位、节拍、起止态与连续性 | StoryboardIR、必要控制及分镜资产 |
| [视频编译](video-prompt-compiler/SKILL.md) | 模型隔离、时间分段与附件映射 | AVIR、模型正文、附件、覆盖与阻塞 |

独立任务只补齐当前职责需要的输入，不伪造上游团队；串联复用同一份原生产物，消费者不重写冻结决定。复杂几何、模型语法及历史协议从每个Skill的按需索引展开。

## 宿主执行

```sh
python -m pip install -e ./ai-comic-drama-workflow
ai-comic-drama start '成年旅人雨夜拾起信封。' \
  --project ./rain-letter --target agnes-video-2.5 --delivery full
# 读取返回的context、其中readings与指向的原生输入，写入output_file。
# 提交宿主实际创作与检查；程序填写指纹、模块回执和原生校验报告。
ai-comic-drama step ./rain-letter --result -
```

| 路径 | 用途 |
|---|---|
| `start`（默认lean/core） | 最小任务视图，实际阶段说明随任务提供，当前宿主连续执行 |
| `start --context-profile audit` | lean内核，完整阅读要求与原生结果接口 |
| `start --profile audited` | V6真实子智能体派发与独立审阅；原`init`默认保持此路径 |

最小视图不截断规则、原文、异常或必要字段。相同范围/字段/发现的采用证据可列举rule_ids分组，展开后仍恰好覆盖每条规则。只在一次提交内复用相同原件的验证报告，原件和归档后结果各验一次，不跨任务缓存通过状态。末尾同一build的编译复核与前期QA可由一次宿主提交完成；两份原生收据与失败回滚保留。详见[最小宿主合同](ai-comic-drama-workflow/references/minimal-core.md)。

## 自动路由不删减

未指定名家时，宿主从来源提取目标与语义标签，确定性路由选择本职责的方法和参考人物；指定名家时仍须与任务及锁定项兼容。场景按既有导演决定细化。方法落实在原生字段，由实际采用或有条件的不适用证据交接，不能用人名代替实现。

全部已登记人物、专业语法、场景、通用方法、27类模板和14条社区经验保留。只有当前命中的方法和章节进入上下文；索引保留全库可达性。精确模型/模式隔离，不能把Seedance引用语法或H3模式当通用能力。

[专业路由](ai-comic-drama-workflow/references/craft-routing.md) · [模板/模型分层](video-prompt-compiler/references/prompt-techniques.md) · [社区读取与来源](video-prompt-compiler/references/community-knowledge.md) · [能力与执行边界](video-prompt-compiler/references/current-contract.md)

## 交付、审计与异常

新lean按执行顺序创建必要目录：`01-source`、`02-screenplay`、`03-director`、`04-art`、`05-assets`、`06-storyboard`、`07-boards`、`08-video-prompts`、`09-delivery`；有真实视频和剪辑时才进入`10-video`、`11-edit`。从`00-progress.md`看当前阶段，从`09-delivery/index.md`拿正文、实际分段、附件及验收。完整信封、接受收据和恢复记录留在`.runtime`，不是例行阅读入口。

审计保留来源/输入/输出指纹、采用证据、约束检查、结论与异常。失败回到拥有该字段的阶段；受影响下游失效重审，其余正确产物复用。UNKNOWN外部执行先回收，不盲目重提交。普通决定自行定稿，登录/权限、未授权费用、能力缺失或失败质量门需要真实解决。

`full`保留实际参考图和Flow保真2K流程；明确指定`text-only`才交文字。需要成片时沿原有真实执行、Take回收、逐镜/相邻验收、剪映和整片审核继续。`DELIVERED`只代表前期包；`VIDEO_DELIVERED`需要真实字节与验收。当前Agent审阅不是独立审阅，静态PASS不证明画质。

[输出合同](ai-comic-drama-workflow/references/compact-workspace.md) · [Flow与剪辑](ai-comic-drama-workflow/references/flow-and-editing.md) · [H3入口](video-prompt-compiler/references/models/minimax-h3.md) · [Omni入口](video-prompt-compiler/references/models/gemini-omni.md)

## 安装、测试与历史

[dists](dists/)提供七个可独立安装的`.skill`、manifest和SHA-256。总工作流内置六模块与独立包保持相同字节；修改源码后重建。已有项目沿用锁定模块，不静默迁移或删除历史产物。

```sh
python ai-comic-drama-workflow/scripts/sync_shared.py --check
python video-prompt-compiler/scripts/reference_audit.py --suite .
python video-prompt-compiler/scripts/vpc.py knowledge audit
python ai-comic-drama-workflow/scripts/run_tests.py
python ai-comic-drama-workflow/scripts/package_suite.py --out dists
```

[先行设计](audit/minimal-core-plan.md) · [实施与基准](audit/minimal-core-implementation.md) · [工作流接口](ai-comic-drama-workflow/README.md) · [历史审计](audit/)
