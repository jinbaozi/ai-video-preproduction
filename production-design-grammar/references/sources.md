# 来源、研究与覆盖边界

核验日期：2026-09-19。完整机器索引在 `registries/evidence.json`。
已读取引用聊天的完整一轮用户/助手文本；接口返回attachments为空，未取得其声称的v0.1.0下载包。
本目录按方案与当前导演合同重新实现，不沿用聊天所称46项测试通过作为本次证据。

| 来源 | 本次使用 |
|---|---|
| [美术指导SKILL方案](chatgpt-conversation://6aaddbd7-d0d8-83e8-a492-932455471296) | 两层美术职责、12语法方向、ArtIR、状态链、平台交接与验收框架 |
| 当前 `../director-grammar` v1.0.0 | 实读SKILL、集成/空间/表演/合同文档、Schema、完整茶馆示例；按其现有字段绑定 |
| [British Film Designers Guild](https://britishfilmdesigners.com/resources/job-roles-explained/) | 制作设计与美术执行、陈设及部门协作分工 |
| [Agent Skills规范](https://agentskills.io/specification) | 标准入口与渐进式披露 |
| [Omni-Art-Skills美术审查](https://raw.githubusercontent.com/waterblower/Omni-Art-Skills/main/image-art-direction/SKILL.md) | 实际读图、参考用途分级、质量/风格/连续性区分 |
| [LibTV官方Skill仓库](https://github.com/libtv-labs/libtv-skills) | 客户端技能与平台内部创作实现的边界 |
| [Hypit仓库](https://github.com/hypit-ai/hypit)与[运行文档](https://hypit.ai/quickstart/run/) | 源与运行意图、实际提交和显式复用边界 |

外部材料用于方法和接口边界研究，未复制其代码或大段正文。核心Schema、编译器、设计规则为本次新增。
打包器基于本工作区director-grammar的同用途本地实现调整；测试用导演夹具保留原字节。

## 名家索引

`registries/research-index.json`保留聊天中的20位/组国内外案例与学习问题。
电影署名来自引用聊天，本次未重新逐项核验；标为CONVERSATION_DERIVED_NOT_REVERIFIED_FILM_CREDITS。
需要将作品署名写入对外研究文章时，回查奖项机构、片方或创作者原始资料。
检索映射是本包设计建议，不宣称代表创作者全部风格，也不把导演/摄影/服装团队贡献归于单一人。

平台页面与main分支会变化。本文没有宣称检索覆盖全网，也未取得闭源平台内部美术Skill。
用户项目的史实与文化细节仍需针对实际年代/地域研究，不能从示例自动继承“已核验”标签。
