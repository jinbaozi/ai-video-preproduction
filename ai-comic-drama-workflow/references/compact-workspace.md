# 顺序目录与最少持久上下文

新 `start --profile lean` 默认 `--output-profile compact`。既有项目和原 `init` 不迁移；`--output-profile audit` 保留原布局与副本，audited/V6 必须使用 audit。不要更改进行中项目的 output_policy 来切换布局。

## 人工入口

只从 `00-progress.md` 查看当前阶段、待决定事项、阻塞、已接受产物和下一步。它是从状态派生的导航页，不是验收依据。目录随进入阶段或产生必要产物创建，未开始的后续阶段不预建空目录。

| 顺序 | 目录 | 内容 |
|---|---|---|
| 01 | `01-source/` | 原始资料、已接受 Canon、实际参考观察 |
| 02 | `02-screenplay/` | 已接受 ScriptIR |
| 03 | `03-director/` | 已接受 DirectorIR |
| 04 | `04-art/` | 按场景的已接受 ArtIR、服化道 |
| 05 | `05-assets/` | 必需视觉资产与其图像提示词 |
| 06 | `06-storyboard/` | 已接受 StoryboardIR、必要调度控制素材 |
| 07 | `07-boards/` | 必需分镜图片与其图像提示词 |
| 08 | `08-video-prompts/` | 冻结编译包、分段提示词、附件与模型限制 |
| 09 | `09-delivery/` | 当前验收结果与 `index.md` 交付入口 |
| 10 | `10-video/` | 请求并实际回收/生成的视频字节；无视频则不创建 |

原生结果按 `v001/`、`v002/` 保存；修订不改写已接受字节。`project.json`、`state.json`、`modules.lock.json` 分别是配置、状态/来源/依赖/决定的检查点、模块锁。`.runtime/` 保留不可省略的模块字节、任务和结果收据、发生路径重定位的原件、共享依赖、事务恢复及真实生成记录。不要求人工逐份打开。

## 宿主的最少读写

1. 读取当前 `task_file`，按 `output_file` 直接写当前原生产物（目录由宿主创建），避免作者草稿再被复制一份；无该字段时按 `output_directory` 与该任务的原生媒体/控制协议工作。已经批准的上游只引用，不复制或另写总结。不要为了本轮任务再运行各专业模块的独立整包导出；执行当前要求的原生验证即可。
2. `handoff.inputs[].fields` 只保留字段指针，完整值在 `native_uri` 中，由 `native_sha256` 绑定。按需读取指针对应字段；硬交接条款、坐标约定、用户锁定、专业方法与验收要求不截断。
3. `task.craft` 已含选中方法，不再生成/读取同内容的 `runtime/craft/*.json`。任务上下文指纹和既有 craft_review 仍强制检查；不能把省略副本理解为跳过参考或采用验收。
4. RoleResult 可通过标准输入提交，不要求先创建额外 result.json；需要重试已接受结果时可使用 `.runtime/results/<task_id>.json`。原生文件路径、哈希、模块读取收据、交接及方法采用字段仍按当前结果协议提供。

```sh
ai-comic-drama start '创意' --project ./project --target 已核验目标
# 宿主将已构造的完整 RoleResult JSON 写入此命令的标准输入：
ai-comic-drama step ./project --result -
ai-comic-drama status ./project
ai-comic-drama context ./project
ai-comic-drama context ./project --slot director --pointer /shots/0
```

标准输入接收一份完整 JSON 后以 EOF 结束；管道或进程 stdin 均可，不提供虚假的默认通过字段。`context` 不生成文件；`--slot` 使用 state 中的实际 slot，指针读取前校验来源、依赖与内容哈希，失效内容拒绝返回为当前上下文。`run/status --verbose` 与 `step --verbose` 可显式查看完整响应。

## 不再默认产生的副本

不写 `manifest.json` 中的 state 投影、`phase-index.json` 常量表、`delivery/index.json` 的全状态副本、已嵌入任务的重复方法文件、逐次快照的 import.json。原生依赖按字节去重复用；一个产物不再把上游整套 raw/native/files 递归复制一遍。路径重定位改变原生 JSON 时，只留一份按内容寻址的原件；字节不变则原生文件就是原件。普通旧记录的 history 镜像可由当前状态和既有接受收据/原生字节追溯，不再写重复 JSON。

该策略不是“隐藏所有中间文件”，也不是“只留最后一个视频”：真实参考图、完整原生上下文、原文、必要制作/审阅证据、失败恢复备份和未确定生成任务不能省略。不会清扫用户输入、任意旧目录、媒体或未完成任务；已有项目不因升级而丢文件。

文件存在本身不消耗模型 token；收益来自避免让宿主生成、读取或回显重复文本。基准记录文件数与 UTF-8 文本字节，不把这些指标换算为模型实际 token、成本或成片质量。
