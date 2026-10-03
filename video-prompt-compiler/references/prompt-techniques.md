# 通用方法、任务模板与模型专属能力

## 责任与来源

`registries/prompt-techniques.json` 包含 6 项通用方法、27 个任务模板和按精确 profile 匹配的模型适配策略。参考 LearnPrompt/awesome-seedance 的固定提交 `9ca56354b3af0d11db22a935a6b831d7d8582c04`，逐条保留模板路径与原始文件 SHA-256；中文方法卡为重新归纳的适配，不批量复制案例或媒体。

**三层不可混淆。** 通用层表达可移植的视听语义，不能保证模型遵从；任务层决定要描述哪些已授权内容，不能新增剧情；模型层仅决定已有能力范围内的表达与交接。具体参数、模态、最大时长、真实上传槽位仍由 `capabilities.json`、实际入口和冻结附件控制。源仓库的“verified”不等于本项目跨模型测试或实际生成验收通过。

目录内容的归纳参考按 CC BY 4.0 署名；本项目新增运行时代码沿用根 LICENSE。未复制第三方图片、视频、人物脸或原始案例正文。来源的代码 MIT 许可与原始媒体权利不能混用。

## 渐进使用

```sh
# 只查看精简索引。
python scripts/vpc.py techniques list
# 只取食物模板与当前模型规则；单条提示词由宿主在现有授权范围内创作。
python scripts/vpc.py techniques plan --target seedance2.5 --template food-asmr
# 原生字段、参考互斥和时间轴检查，不发起生成。
python scripts/vpc.py techniques check --target agnes-video-2.5 --input examples/v52/cafe.avir.json
# 已冻结AVIR只能投影，不根据模板自由改写。模板选择进入manifest和replay。
python scripts/vpc.py compile examples/v52/cafe.avir.json --target agnes-video-2.5 \
  --template dialogue-performance-beats --out /tmp/dialogue-build --output-profile lean
```

完整工作流默认将来源已绑定的 `craft_context` 语义标签用于精确模板标签匹配。它不对原文做盲目关键词命中：多个外观体系冲突，或匹配超过两个任务模板时，只列候选，保持通用方法，交给宿主在当前原生创作范围内定稿；不询问用户例行审批。显式冲突的外观模板会报错。模板不是人名、不是新的主风格，不覆盖既有导演或美术的 primary。

通用方法和选中模板成为原有 `task.craft.rules` 的一部分。宿主用原有 `craft_review.applications` 提供实际字段指针、内容哈希、引用、原因和可观察检查，或有条件的 `not_applicable`；规则未覆盖、来源变化或证据不匹配不能接受。已采用的分镜模板随真实编译参数进入 `artifact.json`，编译选择参与构建指纹及导入复用判断；模板不适用也不伪装成已采用。当前 Agent 的语义判断不是独立审阅或真实媒体验收。

## 字段承载与不可降级项

| 方法 | 原生承载 | 检查边界 |
|---|---|---|
| 固定项与末/初态交接 | entities、shots.start_state/end_state | 身份、服装、道具、空间、时间与信息不因切镜重置 |
| 参考职责 | assets、bindings.roles/negative_roles | 同一职责同时继承与禁止继承会阻塞；真实附件映射仍走原校验 |
| 因果动作与表演 | purpose、timeline.actions/performances | 一个重点不等于删除其他动作；接触、力源和反应需在画面可读 |
| 摄影机与身体 | camera、camera_operations、motion_tracks | 机位、朝向、视线与三种左右分开，不承诺文本精确控制坐标 |
| 声音归属 | audio、timeline.audio_events | 原句、人物、语言、位置、路由和原音轨不能静默替换 |
| 连续时间与实际分段 | output.duration_ms、shots、timeline.segments | 半开区间连续覆盖；独立生成段重述必要上下文，切点仍须原验收 |

各模板带 `writing_pattern`、字段入口与验收点，不存第二份完整AVIR。对“食品质感”“手持真实感”“悬念”等不可纯代码证明的内容，静态检查不捏造通过。

## 模型隔离

适配器按 **id + model + registry version + backend + template + mode** 匹配，不按名字前缀。Seedance 2.0 与 2.5、Agnes 正常版与 Flash、Kling 与 Omni、H3 本体与两种 RunningHub 模式分别登记。Veo 保留独立时长规则。未知或变更的选择器只获得通用方法，专有层为 `UNRESOLVED_NO_MODEL_RULES`；既有能力门仍决定能否编译/执行。

Seedance 案例里的引用符号不进入 Agnes/Kling/H3；本层不生成任何平台槽位。Seedance reference 模板不提升当前未知的引用数量或媒体支持；edit/extend 继续保持原来的不支持状态。H3 节点仍须真实 Export Workflow API。目录只给与当前入口有关的表达/审核策略，绝不是新的 API 后端。

网格分镜是通用审阅方法，**整页网格直接驱动视频不是通用原生能力**。默认复用逐格资产与现有分镜附件路径；整图消费须额外真实入口证据。不得把格号、边框或时码误烘焙到成片。精确字幕、HUD、定格帧率和原音轨同步只能走已验证的原生/后期通道，不因源模板示例而作保证。

## 输出、复核和旧项目

不新增产物目录或旁路报告。`artifact.prompt_techniques` 保存选择、源指纹、精确适配器、输入指纹和客观检查。原manifest保存全部文件和运行时字节；`verify` 重算选择，`replay` 重用显式模板。lean/audit正文和核心内容一致，不重复落盘方法文件。

旧任务没有此扩展时不追补证据；旧锁定模块没有该脚本时按旧协议执行。变更模块、源目录或适配能力会使新增方案失效，不能静默复用。真实 Flow、模型提交、视频回收、剪映和整片 QA 继续使用原有门禁；本功能的 execution 始终为 `submitted=false / runnable=false / media_quality=NOT_RUN`。
