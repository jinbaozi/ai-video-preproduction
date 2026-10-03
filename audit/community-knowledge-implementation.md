# 社区知识接入与对抗审查

## 先行设计与来源

方案先于运行时代码提交：`0d324fda0088f1441e183ed655b934110b093468`。源码基线：`9488a3591e4abf7e4b9361c74acfad080b741e34`。检索日期2026-10-03；不声称穷尽全网。

检索按四组展开：`AI漫剧 / AI short drama / asset character continuity GitHub`、`Seedance prompt storyboard X GitHub`、`MiniMax H3 prompt / Context-IR / recipe`、`Gemini Omni prompting / edit / extend / Interactions API`。X原帖、作者仓库、官方模型介绍、官方接口文档分别核验；搜索摘要不代替原文。源索引有18条记录，其中14条已读取资料、4条原帖不可读的X线索。原始URL、访问日期、固定Git提交（已取得时）及使用边界保存在 `video-prompt-compiler/registries/community-knowledge.json`。

| 来源组 | 独立归纳并采用 | 不采纳的推论 |
|---|---|---|
| Huobao / BigBanana | 角色/场景/道具ID与状态分离、服装变体、各职责输入输出、逐镜与整片交接 | 不复制CC BY-NC-SA代码或改编模板；不宣称一键或保证角色永不变形 |
| LearnPrompt / Seedance官方 | 网格用途、时间顺序、对话节拍、模型版本与入口分离 | 不能把X策展记录当原帖已读；不能把视频延长宣传当本地延长API已实现 |
| H3官方Base/Ref / 1038lab / vLLM-Omni | 三字段/六字段、参考顺序、观察缓存绑定、按任务和权重限制优化配方 | 不采纳100%遵从/零幻觉宣传，不默认四拍15秒或Turbo四步 |
| Gemini Omni官方模型与API | 单镜/切镜意图、局部编辑保留集合、Cloud文生视频边界、Developer输入音轨限制 | 不混用Cloud/Developer/Veo/Kling Omni；累计延长不是首次生成上限 |
| X原帖线索 | 保留4条待复核URL，状态UNAVAILABLE | 不为采纳规则背书，不生成伪造原帖全文或所谓逐帧证据 |

## 第一性原理到实现

只增加使“来源→适用→读取→采用→编译→验证”闭合的结构，不建立第二套制作状态。

- 新增14条独立经验卡。职责、模式、精确能力指纹、来源、原生字段、验收和真实本地段落均可验证。X未读来源不能支持采纳规则，未知或过期模型范围不会近似匹配。
- `community_knowledge.py` 是离线读取器：限定本模块路径，禁止路径穿越和符号链接逃逸；验证文件哈希、唯一章节和段落哈希。URL不执行、不授权，不通过目录传入shell或动态代码路径。
- `prompt_techniques.plan` 将实际读出的适用段落嵌入现有任务。七职责进入既有 `craft_review` 采用/不适用门禁；消费者只继承已接受Canon语义。当前任务只带相关卡片，不全库读取给LLM。
- 编译按已采用模板及精确目标加载相关卡片，在原artifact中保留来源与读证据；原生模型正文、台词、音轨、动作及附件不重写。上游角色方法保存在各自已有收据，不在每镜重复复制。
- RunningHub原节点规划器也实际读取H3对应模式卡；明确修改采样参数才加载配方风险卡。它不根据经验自动改图、降步、换权重或提交费用。
- 新增精确 `gemini-omni-1.1-flash-preview` **Cloud文生视频提示计划**，3至10整数秒，text模式。引用上限0为本地实现边界；不代表模型本身不支持多模态。本轮不实现上传、API提交、编辑或延长，不给Developer ID添加别名。
- 七模块增加资料索引；`reference_audit.py` 沿实际链接访问176份reference文档，包括明确标识的历史/兼容资料。它检查可达性，不执行文档中的命令。索引过期和未登记新文件使CI失败。

## 对抗审查与复现

编译器新增26项测试，工作流新增7项，并增强既有预制作端到端用例。遍历14条卡片的全部173种职责/模式/目标组合，构造真实读取见证；负向测试覆盖不适用范围、缺来源、未读X、重复卡片、空触发、错误章节、资料篡改、缺方法报告、规则删除/重复/改写、越界路径与未实现能力。

首轮回归发现Omni配置包含当前schema不接受的说明字段，已将说明移入按需文档；实现范围和能力数据保持分开。资料/源码/发行包通过相同字段和字节指纹验收，不用单个PASS断言代替路径检查。

```sh
python video-prompt-compiler/scripts/reference_audit.py --suite .
python video-prompt-compiler/scripts/vpc.py knowledge audit
python -m unittest discover -s video-prompt-compiler/tests -p 'test_community_knowledge.py' -v
PYTHONPATH=ai-comic-drama-workflow/src:ai-comic-drama-workflow python -m unittest tests.test_community_routing tests.test_craft_end_to_end -v
python ai-comic-drama-workflow/scripts/run_tests.py
python -m unittest discover -s video-prompt-compiler/tests -v
python ai-comic-drama-workflow/scripts/package_suite.py --out dists
python ai-comic-drama-workflow/scripts/verify_suite.py --packages dists --out /tmp/community-suite
```

工作流0.18.0，编译器1.22.0，其余五专业技能仅为资料入口做补丁版本更新。完整最终结果以PR绑定最终提交的CI和原始日志为准，不把早期本地通过当最终全部通过。`Community knowledge closure` 新增专项；现有主工作流、模型编译、H3、专业方法、精简输出与七包隔离回归继续运行。隔离发行检查新增本轮工作流与编译器专项，不仅检查源码树。

## 边界

本轮的原生端到端为明确合成测试夹具，验证接受、读取、采用证据及前期交付，不是实际电影创作或生成画质。旧项目保留旧锁定模块；当前编译器不把历史包静默迁移。未调用付费模型、Flow服务、真实剪映导出或Codex多Agent派发。静态闭合、READ_LOCAL_NOTE和方法证据不等于模型遵从或真实媒体验收。读取出处不构成对其全部内容的采纳。
