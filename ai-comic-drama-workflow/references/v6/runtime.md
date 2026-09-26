# V6 Codex 编排执行接口

V6 是项目的编排协议：项目存储继续使用 `schema_version=5.0`，原生 ScriptIR、DirectorIR、ArtIR、StoryboardIR 和 AVIR 沿用各自版本。发行套装版本为 `0.11.0`，复用的原生 IR 与校验合同仍为 `0.10.0`。新项目默认 `orchestration_protocol=6.0`、`execution_mode=codex-agents`。旧 V5 项目继续原协议；新建项目若明确要旧流程，可用 `init ... --orchestration current-agent`。旧项目通过 `migrate-v6 OLD --destination NEW` 复制进入新协议：保留原件与迁移报告；旧成果只有经过 V6 来源验证和复核才能接受，缺少的执行和审阅证据不能补写成虚构历史。

## 唯一阶段图

阶段、责任角色、锁定 Skill、依赖、输出、检查器和适用条件以包内 [`workflow-v6.json`](../../workflow-v6.json) 为准。`run` 和状态判断使用同一图；下列顺序帮助阅读，不另立一套可执行规则。

`sources → reference_observation → canon → screenplay → director → art → visual_prompts → visual_media → storyboard → control → board_prompts → board_media → compile → compile_review → preproduction_qa → preproduction_delivery`

`production_target=video` 再接 `video_freeze → video_execution → take_recovery → shot_acceptance → take_selection → adjacent_acceptance → assembly → whole_acceptance → video_delivery`。

阶段图默认最多并行两个专业执行任务和一个独立审阅任务，仍受当前 Codex 宿主实际容量限制；互不依赖的分场美术及图片提示词任务可同时派发，同一产物或重叠范围的写入串行。图片与视频实际生成仍按各自的调用记录和预算门执行。

参考观察只在需要观察参考时适用；`text-only` 的视觉资产与分镜图片提示词和媒体节点、无需调度图的 `control`、无视频目标的成片链都由图中条件产生显式 `NOT_APPLICABLE` 记录，记录规则依据、证据和受影响交付项。缺少任务不等于节点通过。已存在的独立成果先验证来源并作为候选复核，随后仍走相应节点的检查与审阅。
上游版本或模块锁变化后，原 `NOT_APPLICABLE` 记录会失效；新记录的身份绑定当前前驱任务及版本，不能沿用旧跳过命令推进新图。

`control` 适用时由 AVIR 与相机配置派生俯视 X–Z、侧视和摄影机画面预览，供角色根节点走位、镜头轨迹与构图核对；AVIR 仍是运动权威。俯视图是审阅资产，不能直接当作生成模型的轨迹控制通道，也不能证明人体步态、遮挡或碰撞已求解。具体文件与边界由锁定的 `video-prompt-compiler/references/shot-control.md` 说明。

适用的 `ShotControlPack` 必须由锁定 `control_cli.py verify` 实测为 `VERIFIED`，与当前分镜重新转换的 AVIR 和创作者配置逐字节绑定，并且所有预览帧的摄影机投影已确定；出现 `UNDETERMINED` 时停在 `control_verify` 返修。通过此门仍只表示可审阅的计划投影，`media_review=NOT_RUN` 不会被改写为生成模型已服从轨迹。

V5 原生产物复制到项目时会重定位来源 URI 和嵌套来源哈希。若复制前的 `semantic_review` 确实绑定原内容，内核只对这次确定性重定位重新计算导入副本的摘要，并保留 raw/native 和导入映射证据；原审阅失效时不会补写 `PASS`。既有项目中导入副本的旧摘要若不匹配，V6 将该已接受任务及下游置为 `STALE`，由原责任任务新批次复核，不把静态 Schema 通过当成语义审阅通过。
导演稿的编剧交接映射先对创作者原件验证，再把 `review.director_sha256` 绑定到重定位后的正式 DirectorIR 内容指纹并重新验证；正式交接记录因此对应当前正式产物。

## 宿主循环

在 Skill 根目录运行 `PYTHONPATH=src python -m ai_comic_drama_workflow`，或安装后运行 `ai-comic-drama`。`init` 建项目，`run PROJECT` 返回当前可执行动作或阻塞。Python 内核只生成和校验协议动作，不调用 Codex 子智能体工具；Codex 宿主执行真实 `spawn_agent`、后续消息或回收，并把工具回执登记到项目。

```sh
ai-comic-drama init 原文.txt --project /绝对路径/新项目 --project-id MY_STORY --target agnes-video-2.5
ai-comic-drama migrate-v6 /绝对路径/旧项目 --destination /绝对路径/迁移副本
ai-comic-drama run /绝对路径/新项目
ai-comic-drama graph --format mermaid
ai-comic-drama agent-event /绝对路径/新项目 --file EVENT.json
ai-comic-drama agent-message /绝对路径/新项目 --file MESSAGE.json
ai-comic-drama agent-result /绝对路径/新项目 --file CANDIDATE.json
ai-comic-drama agent-review /绝对路径/新项目 --file REVIEW.json
ai-comic-drama agent-reconcile /绝对路径/新项目 --file REPORT.json
ai-comic-drama image-begin /绝对路径/新项目 --file IMAGE-BEGIN.json
ai-comic-drama image-result /绝对路径/新项目 --file IMAGE-RESULT.json
```

`graph` 直接读取并校验 `workflow-v6.json`，输出由同一节点与依赖生成的 Mermaid 流程图；`--format json` 同时给出节点字段与图文本。阶段条件和角色以该可执行定义为准。

`status` 以最新项目范围的 V6 `preproduction_delivery` / `video_delivery` 事件与原生 V5 交付状态交叉核对。当前交付证据一致时返回 `DELIVERED`、`PREPRODUCTION_DELIVERED` 或 `VIDEO_DELIVERED`；更早批次的 `STALE`、`FAILED` 和 `BLOCKED` 仍逐项出现在 `v6_tasks`，但不会覆盖后来有效的交付。最新交付事件与原生状态不一致时返回 `BLOCKED`。视频目标的 `PREPRODUCTION_DELIVERED` 表示前期完成、`video_complete=false`；只有 V6 视频交付事件与原生 `VIDEO_DELIVERED` 同时成立才报告成片完成。

七个 `--file` 文件都是精确字段的命令包装对象，顶层必须有唯一 `command_id` 和当前 V6 台账的 `expected_revision`。其余字段分别为：`agent-event` 的 `receipt`、`agent-message` 的 `message`、`agent-result` 与 `agent-review` 的 `candidate` / `review`；`agent-reconcile` 使用 `task_id` 和 `observation`；`image-begin` 使用 `task_id`，`image-result` 使用 `candidate`。内层对象须匹配对应 V6 Schema。先读取 `run` 或 `status` 的当前修订再提交；旧修订、未知字段与同 ID 不同内容会被拒绝。

这些登记命令只接受实际执行后得到的证据。宿主将待派发动作绑定真实 Codex agent ID、工具回执和任务批次；专业子智能体只读取冻结输入和锁定模块，在自己的候选目录写文件。候选结果带输入指纹、产物清单与哈希、实际检查、模块读取收据、交接映射和未决项。独立审阅者检查候选版本及全部检查项，创作者不能审结自己的任务。内核独占正式文件登记和状态提交。真实工具调用与不确定派发的逐步处理见 [Codex 宿主桥接](codex-host.md)。

图片素材节点由单独宿主动作执行。`run` 给出图片待执行动作后，宿主先用 `image-begin` 登记原调用及批次，再调用已登记的工具或导入已提供文件；拿到结果后用 `image-result` 提交候选。`image-host-action/6.0` 绑定图片提示词、参考哈希与本批次；实际工具返回或用户提供的文件形成内容寻址的 `image-host-record/6.0`，保存在项目的 `runtime/v6/host-evidence/`。图片候选须写 `host_record_uri` 和 `host_record_sha256`，其 V5 媒体结果中的 `call_evidence` 精确引用该记录哈希、工具名与调用 ID。内核还重新核对图片可解码、真实参考输入、字节哈希和看图结论。调用状态不明时只核对原调用，不再发起新生成。

## 协议与状态门

协议文件在 `schemas/v6-*.schema.json`。任务信封为 `task-envelope/6.0`，绑定项目、节点、任务、批次、角色、范围、输入修订与哈希、模块锁、必读资源、预期产物、检查器、依赖及交接要求。派发回执、智能体消息、候选结果、审阅记录、状态事件、定向返修简报、图片宿主动作与结果、参考观察登记各有严格 Schema；未知字段与缺少的条件字段会被拒绝。参考观察登记须列出实际观察文件及其哈希，再由原生观察校验器复核。

主路径为 `PENDING → READY → DISPATCHING → RUNNING → RESULT_SUBMITTED → VALIDATING → REVIEW_REQUIRED → ACCEPTED`。`BLOCKED`、`FAILED`、`UNKNOWN`、`STALE` 和 `CANCELLED` 只能经协议允许的事件进入或恢复。每个状态事件绑定命令 ID、预期项目修订、任务与批次、对象版本、初末状态、原因、检查结果和证据。相同命令同内容重复提交是幂等操作；同 ID 内容冲突、过期批次、迟到结果、错误角色或旧审阅不能推进。

任务之间的 `ACK`、`PROGRESS`、`QUESTION`、`BLOCKER`、`HANDOFF`、`RESULT`、`CANCEL_ACK` 使用结构化消息登记，绑定发送者、接收者、任务批次、关联消息和证据。影响制作结果的直接沟通也必须登记；聊天回复不改变项目权威输入。交接记录逐条绑定来源要求和版本、目标字段、执行渠道及检查证据；无法满足时返回原责任模块修订。

导演、美术和分镜任务同时具有两份不同的交接合同：原生任务文件的 `handoff.required_handoffs` 对应 V5 `RoleResult.handoff`，V6 任务信封的 `handoffs` 对应 `candidate.handoffs`。两者都需逐项落实；原生交接会在独立审阅派发前预检，不能用 V6 的产物映射代替编剧到导演的语义映射与审阅绑定。

内核在一次状态提交中核对协议、当前输入版本、执行身份、允许迁移、依赖文件与哈希、专业校验、独立审阅和交接。模块收据仅证明所读资料的版本；它不能证明语义已正确实现。文件内容与登记哈希不符时阻断后续执行。网络或模型等待期间不持有项目写锁。
经 V6 gateway 执行会改写 `project.json` 的正式决策、输入修订或模块更新时，先把旧 manifest 字节按 SHA-256 归档；历史事件即使指向 `project.json`，重放也必须命中对应的内容寻址归档，不能拿新 manifest 冒充旧证据。

## 失败与恢复

无外部副作用的专业任务最多尝试三次；同一检查连续两批失败时，内核冻结两次失败事件、审阅证据及哈希为严格的 `repair-brief/6.0`，并把 `repair_brief`、`repair_failure_1`、`repair_failure_2` 加入第 3 批冻结输入。子智能体逐项纠错，内核拒绝任意改字段冒充返修；第 3 批仍未通过则停止。独立审阅把缺陷归于上游专业节点时，内核仅接受图中的上游 Skill 专家，并要求其能唯一解析到当前候选的已接受依赖任务；随后冻结原审阅记录与失败检查证据，生成严格的 `upstream-repair-brief/6.0`，使原责任节点通过新 V6 任务返修。无法唯一解析任务范围或责任节点不支持原生修订时保持 `REPAIR_REQUIRED`，不猜测责任对象。派发结果不明进入 `UNKNOWN`，先按任务和批次查询实际 Codex 子智能体，再登记恢复报告。图片或视频调用已经提交但结果未知时，只查询或回收原调用，不自动重发。输入变更会使依赖它的运行任务失效；旧批次结果可保留历史，不能合入当前版本。

错误记录须含错误码、责任节点、失败检查、证据、可否重试和恢复动作。普通修正继续执行；创作锁定、费用或宿主能力的新决定应绑定具体候选方案及版本。没有真实宿主工具、附件或凭证时，记录阻塞与可继续的独立任务，不把文本编译结果标成媒体执行。

## 成片完成门

前期 `DELIVERED` 与成片 `VIDEO_DELIVERED` 分开记录。视频执行请求绑定当前编译包、附件字节、目标入口、执行范围和预算；实收 Take 绑定真实执行记录、文件哈希与本地媒体探测。逐镜验收覆盖每个要求的镜头及时间段，相邻验收覆盖实际剪辑顺序的每对镜头，并绑定已选定 Take。

成片 CLI 使用 `ai-comic-drama production PROJECT <子命令>`。按冻结和验收顺序执行：

| 子命令 | 输入与作用 |
|---|---|
| `freeze` | `--shots` 有序镜头 ID JSON 列表、`--shot-ranges` 每镜头起止毫秒 JSON 映射（如 `{"S1":{"start_ms":0,"end_ms":1000}}`）、`--plan` 验收合同、`--spec` 输出规格，必要时 `--obligations` 后期义务。V6 输出规格须明确宽、高、帧率及 `preserve_native_audio` 布尔值；所有范围来自已决定的制作计划，不按媒体长度猜。 |
| `plan` | `--compile` 编译清单、`--manifest-sha` 其实际 SHA-256、`--request` 清单中的请求 ID、`--attachments` 冻结附件。V6 默认每任务一次尝试；增加 `--max-attempts` 须提供 `--budget-authorization` JSON 文件，含 `decision=APPROVED`、`request_id`、`max_attempts`、`project_cap`、`actor` 和 `evidence`，文件字节与哈希一同冻结。 |
| `execute` / `recover-execution` / `receive-take` | 自动执行、查询原执行记录，或用 `--execution-evidence` 登记人工执行与本地 Take；不把查询失败当作重发授权。 |
| `review-take` / `select` / `check-adjacent` | `review-take --take` 绑定实际 Take 并派发逐镜独立审阅；该审阅通过后，`select` 再派发选片复核。相邻检查逐对收集实际观察记录，收齐后派发覆盖整条剪辑顺序的独立审阅。命令返回待审阅动作不等于已通过。 |
| `assemble` / `post-obligation` / `review-sequence` | 用选定 Take 的 EDL 总装，登记后期义务证据，`review-sequence` 派发绑定最终输出文件的独立整片审阅。 |
| `deliver` | 重新检查冻结清单、所有验收、媒体字节与后期义务，通过后由内核登记 `VIDEO_DELIVERED`。 |

人工回收的 `--execution-evidence` 必须有 `channel`、`external_task_id`、`request_id`、`payload_sha256`、按冻结顺序的 `attachment_sha256s`、`proof_uri` 和 `proof_sha256`；证据文件须真实存在且字节哈希匹配。`--shot-ranges`、验收观察和 EDL 都是已决定的输入，不由 CLI 推测或补齐。

冻结验收计划后校验内容摘要；缺项、重复项、错误范围、过期媒体或未确定结论不能完成。总装只引用已登记、已选定的 Take，检查帧范围、顺序、时间覆盖、输出规格和实际需要的原生及后期音频。整片审阅绑定最终输出字节与总装版本。只有当前交付清单和实际媒体检查全部通过，内核才产生 `VIDEO_DELIVERED`。

共享文件系统下，候选目录与正式目录的区分是协议和校验约束，不等于操作系统级隔离。静态校验、真实派发、图像生成、视频生成和观看听审分别留证；任何一类通过都不能冒称另一类完成。
