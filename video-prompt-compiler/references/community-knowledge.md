# 社区经验的按需执行合同

## 从来源到实际任务

`registries/community-knowledge.json` 是离线、版本锁定的经验目录。每条采纳记录都有职责、输入模式、语义标签、模型范围、原生承载字段、验收点和本地段落读取描述。

运行期不联网加载最新网页，不运行来源中的命令。路径与章节解析器实际读出选中段落，保存文件哈希与段落哈希；这里的哈希对应本项目独立归纳材料，不伪称外部网页响应原字节。外部URL仅提供出处。全部材料可达不等于每次全量注入上下文。

完整工作流在已有 `task.craft.prompt_methods.community` 内嵌当前相关方法和读到的段落，七类职责都使用原 `craft_review.applications` 绑定实际内容或给出有范围的 `not_applicable`。消费者继承已接受的 Canon 语义标签，不从模型名或任意提示字符串猜风格，不重写原有导演决定。既有任务封套哈希阻止重封方法选择绕过派发。

编译时社区方法随已采用模板的标签和精确目标再筛选，写入原有 `artifact.prompt_techniques.community`，不写重复 sidecar。上游全部角色的采用证据仍在原任务收据，不宣称全部上游卡片正文重复进入最终模型提示词。新增编译清单将本地参考资料纳入运行时指纹；`verify` 重算计划，`replay` 保留模板选择。冻结 AVIR 与模型正文仍由原生编译器投影，不让社区方法暗改剧情、台词、颜色、动作、服装或时长。

## 来源分级与许可

官方接口文档裁决入口参数；官方模型介绍不等于API契约；作者项目说明可以启发工程方法，不能证明该项目的质量或速度宣传；社区索引只提供策展证据。X原帖读取失败的4条线索标为 `UNAVAILABLE`，不得为自动规则提供证据。不能把找到链接等同于读到原文。

BigBanana及Huobao原仓库声明CC BY-NC-SA 4.0。本项目不复制其代码、图像、视频或改编模板，只将资产身份/状态分离和职责交接等思想作独立实现。LearnPrompt策展来源沿用已有CC BY 4.0署名。H3及Google资料仅用于独立事实归纳；模型、素材及账号的权利需按实际来源核验。

## 调用与审计

以下在 `video-prompt-compiler` 目录执行：

```sh
python scripts/vpc.py knowledge list
python scripts/vpc.py knowledge plan --role storyboard --tag 漫剧 --tag 九宫格
python scripts/vpc.py knowledge plan --target runninghub-h3-ref2va --mode reference
python scripts/vpc.py knowledge plan --target gemini-omni-1.1-flash-preview
python scripts/vpc.py knowledge audit
python scripts/reference_audit.py --root .
# 在完整源码工作区检查七个模块的所有reference路径：
python scripts/reference_audit.py --suite ..
```

`knowledge audit` 为每条卡片的每个职责、模式、精确目标组合运行正向选择并读取真实本地段落，不只数文件。负向测试覆盖改模型版本、缺来源、读取失败、缺章节、重复ID、路径穿越、符号链接逃逸、资料改字、方法报告删除和缺采用证据。

[资料索引](resource-index.md)列出本模块全部当前、专门任务与历史资料。`reference_audit` 校验索引是否与实际文件一致，并沿SKILL的Markdown链接访问全部reference文件；不会执行文档里的shell示例，也不会把历史协议升级为当前能力。新增文件未进入索引、死链接或越出模块边界会阻塞CI。

## 旧版本与真实执行边界

旧项目沿用原来锁定的模块和协议；不替换它的编译器后要求它补交新增社区证据。当前编译器针对当前材料版本重算，旧编译包需要对应冻结版本验证/回放，不静默重写为新版本。

本轮新增Omni只提供[Cloud文生视频提示计划](models/gemini-omni.md)。H3节点仍要读取真实Export Workflow API。编辑、延长、费用、登录、缺媒体、Flow保真验收和剪映导出沿用原有门禁。`READ_LOCAL_NOTE`、路由通过、合成夹具端到端通过均不等于真实视频生成或艺术质量通过。
