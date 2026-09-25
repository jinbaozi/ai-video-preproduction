# V5 当前 Agent 执行接口

在 Skill 根目录运行 `PYTHONPATH=src python -m ai_comic_drama_workflow`，或安装后的 `ai-comic-drama`。
Python 3.12+，依赖 jsonschema；图片登记另外需要 ffmpeg/ffprobe。模型、图片工具均由真实宿主提供，不由 Python 模拟。

## 命令

- `init <资料文件或文本...> --project <空目录> [--project-id PROJECT] [--delivery full|text-only] [--production-target none|video] [--target 目标ID] [--mode text|reference|keyframe|edit|extend] [--no-run]`
- `production <项目> plan|execute|receive-take|review-take|check-adjacent|assemble|status`：成片台账。`execute` 需要 `AGNES_API_KEY`。编译包 `submitted` 不被改写。
- `run <项目>`、`status <项目>`：返回当前任务/决定/阻塞；当前 Agent 自动执行可继续的任务。
- `host <项目> --capabilities <JSON>`：`image_capability` 为 available/unavailable/unknown；`evidence` 是真实宿主工具清单证据。可选 `video_capabilities` 只能登记控制注册表里已有的模型、模式和入口。
- `submit <项目> --result <JSON>`：提交下述结果记录；相同结果重复提交返回 ALREADY_ACCEPTED，冲突重复被拒绝。
- `begin-image <项目> --task-id TASK_...`：调用图片工具前登记；中断后的 run 返回待回收状态。
- `recover-image <项目> --evidence <明确重试决定的来源>`：确认需要重试后解除不确定调用；不能凭等待超时重复调用。
- `resume <项目> --decision <JSON>`：request_id、value、evidence；选择目标另带 target、mode。evidence引用实际用户决定，推荐选项不是批准。
- `import-artifact <项目> canon|screenplay|director|art|storyboard|avir <原生JSON> [--scene-id ID] [--locks JSON] [--handoff JSON]`
- `revise <项目> <kind> [--shot-id ID|--scene-id ID|--asset-id KEY] [--target ID --mode MODE]`
- `import-compiled <项目> <原生编译包目录>`：校验版本、清单和AVIR，原离线回执保持原字节。
- `request-decision <项目> --proposal <JSON>`：仅用于具体创作冲突、显著费用或能力取舍；给出kind、question、context，可包含有当前版本绑定的lock_updates。
- `compile <项目> [--mapping JSON]`：当前StoryboardIR映射、检查和平台编译；不提交生成。
- `validate <项目> [--final]`、`export <项目> [--draft]`
- `add <项目> <补充资料...>`；`copy-project <旧项目> --destination <新目录>`。
- `update-modules <项目> --lock <新锁文件> --archives <对应skill包目录>`：显式升级，保存旧锁；重检受影响结果。
- `doctor`：输出运行边界与模块锁；不伪造宿主生图能力。

退出码：0=当前动作完成/等待任务或决定；2=BLOCKED或校验未通过；1=输入、结构或工具错误。

## 当前 Agent 循环

1. 读取 run 返回的 task。只读 inputs、scope、module.path/SKILL.md 和相关 reference；无需加载全部模块。
2. 对照 output_contract、原生Schema与示例工作。前两阶段的规范JSON包含 project_id、revision、content、source_refs；canon还含entities（稳定id）和locks（kind/check）。source_refs只引用任务给出的来源ID。
3. 原生IR保留project_id，与项目一致；已有独立包可在初始化时沿用其ID。不能静默重命名相互冲突的实体。
4. 输出角色结果后submit，再run。complete=false允许分批续写；每个创作提交最多新增/修改5镜，既有完整包用import或reused=true并真实审核。
5. 只有必要用户决定才暂停依赖工作。缺图片能力不阻止独立文本设计；不要把缺媒体伪装为已完成。

## RoleResult 5.0

规范结果：

```json
{
  "schema": "role-result/5.0",
  "task_id": "从当前任务复制",
  "context_fingerprint": "从当前任务复制",
  "artifact": "/绝对路径/原生IR.json",
  "artifact_sha256": "实际原生文件的64位SHA-256",
  "checks": ["本次实际执行的检查与结论"],
  "handoff": [],
  "complete": true,
  "conflicts": [],
  "unresolved": []
}
```

image-prompt任务用 `prompt`（完整正文）与 `checks`（实际约束检查列表）替代artifact。
image任务用media：path、sha256、provider（image_gen或provided）、call_evidence、input_bindings、visual_review。
input_bindings逐项复制真实送入工具的job.references之key/sha256，并实际附带这些图片；不能只在文字中提及。
visual_review包含status=PASS、该图片sha256、findings（实际看图发现）。工具调用返回文件不等于视觉通过。
图片身份定稿使用resume提交实际用户决定。阶段9的QA原生JSON包含project_id、passed、build_id和checks，绑定当前构建。

独立导入的制作包保留原字节，已存在依赖被复制并显式重定位；原生校验前后各运行一次。草稿和完整制作包的限制不能互换。

## 锁定与显式语义映射

任务信封的handoff字段包含导演/美术原生字段切片、坐标依据和required_handoffs。每条交接记录声明requirement_id、source_fingerprint、target_checks、reason；StoryboardIR还必须以target_clause引用自己的硬合同，并保留原允许执行渠道。原始来源文件仍是权威，简报不替代原生IR。

转换器不能处理的硬字段会阻塞。当前Agent确认语义后可提交mapping文件：storyboard_sha256绑定当前登记版本，mappings按原JSON Pointer记录owner、reason和目标check。不能用一条无关存在性检查掩盖尚未满足的要求；Kernel检查源断言、所有者和目标断言，语义等价仍由当前Agent审核并记录。更换分镜后旧映射失效。

用户明确批准变更锁定字段时，proposal.lock_updates每项含slot、index和check；新check必须对应原锁路径。resume只能应用绑定当前文件和原锁的批准，历史记录保留。用户拒绝的方案保持阻塞，直到提交修订方案。普通检查不走这个决定接口。

完整流程默认reference模式，text-only默认text；用户明确模式优先。选择keyframe、edit、extend仍受专用编译器的真实已实现边界限制，不能自动降级。

每个画格任务有明确frame与moment，参考用途进入视频提示词硬合同；同一实际文件用于多个实体时按哈希复用物理附件，逻辑用途分别保留。附件数量超过目标能力时明确阻塞，不丢图。图片提示词只依赖它消费的资产/世界或画格/机位/事件字段，无关镜头备注不会使已审核图片失效。

独立制作包可先导入；当其上游就绪后，run给出带previous的复核任务，当前Agent复用原作并补齐交接记录即可，无需重新创作。项目ID必须一致；初始化新项目时可沿用独立包的project_id。不同实体ID或身份含义不能静默合并。


## V5.1 增量入口

`ai-comic-drama import-observation PROJECT OBSERVATION_DIR` 登记实际提帧、查看范围及独立声音状态。任务信封 handoff.reference_observations 提供完整观察记录；变更观察证据会改变来源指纹，不能继续沿用旧资料结论。

`ai-comic-drama revise PROJECT storyboard --action-id ACTION_ID` 按新版时间轨动作依赖确定修订范围。提交时不仅检查 shots，还检查 actions、performances、camera_operations、audio_events、state_samples 等实际变化。画格按其明确时刻及完整依赖指纹复用，未改变的实际图片保留。

所有旧命令和默认 text-only/full 含义不变。新版项目存储版本仍为 5.0，发行版本 0.5.1；原生制作协议版本 1.1、转换器版本 1.1.0 分开记录，不由项目存储版本推断内容标准。

## V5.2 增量入口

新完整制作采用 1.2 原生协议，项目存储仍 5.0，发行 0.5.2，转换器 1.2.0。专业模块发行 1.3.0。旧 1.0/1.1 制作包按版本分支读取，旧项目模块锁保持。

`revise storyboard --node-id NODE_ID` 或 `revise storyboard --track-id TRACK_ID` 按节点、轨道和实际依赖限定任务范围；不要同时指定另一种动作/镜头范围。画格依赖该时刻消费值，其他时刻的无关修改不重做图片。`scripts/run_v5_example.py --version v52 --out NEW_DIR` 运行三镜预先创作文本样例。
