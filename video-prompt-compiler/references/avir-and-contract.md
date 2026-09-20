# AVIR与制作合同

以`schemas/avir.schema.json`为准。严格JSON，未知字段拒绝；每个集合ID唯一，动作事件ID全局唯一。
自然语言解析、读图、听音与视频观察由当前Agent完成，CLI不声明看懂未检查素材。

| 字段 | 用途 |
|---|---|
| schema/project_id/revision/tenant_id | `avir/1.0`、稳定项目与递增修订；tenant_id仅是归属标签，不是权限系统 |
| sources | 来源ID、类型、URI、页码/段落/时间码、事实、核验状态、可选原文件SHA-256 |
| entities | 主体、外貌、固定身份/服装/数量；旁白也有说话人身份 |
| scenes | 场景、米制世界坐标、世界光源；反打不改变真实光源 |
| assets | 真实文件名、类型、路径、哈希、URL、观察状态 |
| bindings | 资产→允许/禁止职责→人物/场景→镜头；同镜同目标同维度一个权威资产 |
| output | 总毫秒、画幅、分辨率意图；有证据的后端才提升为原生字段 |
| shots | 时轴、用途、场景、构图、机位、空间关系、起止状态、动作、风格、来源 |
| audio.utterances | 原文、说话人、语言、起止、语气、对白/旁白/内心独白、native/post |
| audio.cues | 音乐/环境/音效/静音、时间、同步事件与执行渠道 |
| contract | 每条制作要求的来源、字段断言、执行方法、验收条件和失败处理 |
| policy/expansions | 语义扩写开关、预算、Context策略；候选不改写权威Core |

`source_refs`覆盖结构作用域。不同字段来自不同原文时拆分来源，并在合同用精确JSON Pointer对应。
`provided`只表示用户提供过；`observed`须有真实读图/听音/观看证据。不可把整个研究报告当作台词剧情来源。
本地Canon/导演/美术文件绑定原始字节哈希；相对路径基于输入AVIR目录，重放保留原基目录。

## 五环制作条款

1. 来源：`source_refs`指向原始需求或观察证据。
2. 结构：`checks[].path`必须可解析。
3. 约束：`level=hard|soft`；`equals/contains/exists`验证结构化事实。
4. 执行：`channel=prompt|parameter|reference|post`，`execution`写明谁、何时、用什么路径实施。
5. 验收：`acceptance.method=static|media|human`及可观察条件，不写笼统“高级、好看”。

硬要求不能`on_unsupported=warn`。`post`是已有合同允许的后期路径，不是自动改剧情授权。
字段断言通过不证明自由文本等价或视频效果。条款状态与实际媒体结果分开。
例：递杯需检查先持握、接收手接触后交出、松手时点、唯一杯子、末态持有人及下一镜承接。

## 空间与时间

轴固定`x=world-right,y=up,z=depth`，原点在scene内。画面左右在composition；人物自身左右在动作。
`start_state/end_state`保留所有本镜实体，出画实体用`visible_parts=[]`而非删除世界状态。
relations为本镜不变关系，起止都检查；关系变化应在分段镜头中表达。接触/面对关系仍须人工语义及媒体检查。
同场连续镜头需承接位置、姿态、视线、支撑、道具；景别可改变可见部位。时间跳跃或换轴侧需理由。
毫秒使用全片绝对时间；镜头从0连续覆盖总长。CLI检查边界，不做身体仿真或任意文字矛盾推理。

## 修订与迁移

首版没有历史Schema自动迁移器。其他版本拒绝猜测转换；Agent读取旧协议后做显式映射并列出损失。
新revision输出新目录；回滚使用完整旧Skill构建与清单。`replay`遇运行文件哈希变化拒绝混用新规则。
静态可重放不代表供应商视频可重现。制作合同是制作规格，不是法律合同。
