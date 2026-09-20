# StoryboardIR 1.0 字段与时间约定

机器契约以[Schema](../schemas/storyboard-ir.schema.json)为准。优先从[完整咖啡馆示例](../examples/cafe.ir.json)做有依据的裁剪，而非填空扩写剧情。
本包对结构字段较严格；无相关内容用允许的null/空数组。自然语言用户无需手填此文件，Agent负责建模。

| 字段 | 用途与关键不变量 |
|---|---|
| schema_version / project_id / revision / canon_ref | 项目协议、宿主ID、当前修订及事实来源；不自建全局状态机 |
| scope | 指定来源与镜头顺序；明确排除台词及依据 |
| sources | 摘录、字节哈希、原文字符跨度与发声归属 |
| upstreams | 原文件SHA-256、版本、项目和字段级只读映射锁 |
| entities | 主体/道具/环境/voice身份与外形锁 |
| scenes | 世界坐标、边界、实体名单、轴和固定世界光源 |
| assets / bindings | 真实文件名、版本、状态、用途、禁止继承维度及作用镜头 |
| beats | 信息变化、场景、前置关系、覆盖与排除 |
| style | 媒介、主语法、修饰、理由、禁止项、标签 |
| delivery | 整数fps、总帧数、画幅；未知分辨率用null |
| shots | 视点、观众信息、构图/机位、空间关系、起止状态、事件、表演、画格、转场 |
| audio | 有来源台词及独立声音提示；所有时间为全片帧 |
| contract | 字段断言、执行渠道、验收证据及失败策略 |

## 时间

全片镜头从0开始且连续铺满total_frames，区间为[start_frame,end_frame)。
画格frame必须小于镜头end_frame。事件状态在end_frame生效，可位于镜尾边界；动作音需给同步帧留有效音频区间。
事件按完成时间排序；depends_on中的事件必须先完成，同一实体字段区间不重叠。多个实体的并行动作允许放同一事件或不冲突事件。
seconds = frame / fps。AVIR当前采用整数毫秒；不是每个24fps帧都能精确表示为整数毫秒。
宿主映射时对绝对边界一次舍入，记录每个frame→ms误差及时间碰撞；禁止逐段四舍五入再累加导致总时长漂移。

## 来源与台词跨度

excerpt_sha256 = SHA256(excerpt原文UTF-8字节)，不做空白或标点归一化。
file_sha256 = SHA256(完整源文件原始字节)，与摘录哈希不同。给出文件哈希时CLI确认文件存在、字节一致、摘录确在文件内。
span为Python/Unicode字符索引[start,end)，不是UTF-8字节偏移；text必须恰等于excerpt[start:end]。
所有source_utterance_id全局唯一；输出同时匹配text、speaker_id、kind；源范围内没有未说明的删句或重复。
外部URI不会自动联网抓取；应由Agent读取后写来源状态。仅凭输入自己声称read，不构成外部权威性保证。

## 状态与事件

state_start/state_end是以实体ID为键的字典；必须覆盖scene.entity_ids中所有物理实体，voice除外。
每个状态有position_m、身体与头部朝向、pose、gaze_target、support、contacts、holder、condition。
contacts如["TABLE.top", "B.right_hand"]，holder如"B.right_hand"；无持有人用null。
changes只修改列举的状态字段；before必须相等，after必须仍满足状态Schema，最终逐字段匹配state_end。
release与grasp负责持物变化，避免动作描述正确但状态表直接把道具换人。
关键身份事实在entities.identity_locks内跨镜共享；condition记录湿度、破损等变化及事件依据。
编译后的画格附state_evaluation：只回放已经完成的事件，同时列active_event_ids。动作进行中的位置/旋转不插值，不能把completed_state当该帧精确姿态。

## 构图与表演

composition.subjects是画内可見表，不等于全体世界实体。box为[x,y,w,h]，各值0–1。
用于机器可见性检查的部位建议face、eyes、mouth、hands、body；特定道具细节可用自定义部位名，但producer/consumer需一致。
micro_expression为null表示当前无需这类细节；心理可visible_translation而不发声。
schema保存细节不等于模型控制这些细节，具体执行由合同渠道与媒体QA约束。
