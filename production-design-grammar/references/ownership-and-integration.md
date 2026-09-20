# 所有权与导演交接

本包支持独立美术规划。只有用户要求视频交接时才需要 DirectorIR，不把另一个 Skill 安装为硬依赖。
按当前工作区 `director-grammar` v1.0 的字段进行只读绑定；本次未修改其源文件、Schema或编译器。

| 内容 | 最终所有者 | 美术负责的补充 | 冲突处理 |
|---|---|---|---|
| 世界事实、角色身份、资产ID、批准记录 | 宿主 Canon | 有出处的设计补充及候选资产 | 返回 Canon 变更建议，不自行批准 |
| 叙事信息、显露顺序、镜头目的 | 导演 | 环境线索及道具可识别条件 | 不提前泄露隐藏道具 |
| 构图、景别、画幅、机位、运镜、焦点 | 导演/摄影 | 背景分区、层次、负空间、遮挡和反射条件 | 先调未锁定陈设；不能解决时提出机位复核 |
| 三维场景、建筑开口、家具、画内光源 | 美术 | 米制布局、尺度参照、材质及通行区域 | 与导演行动轨迹联合评审 |
| 人物相对位置、视线、走位、手部交接 | 导演 | 场景容纳性、可接触表面、道具尺寸和状态 | 不移动演员来迁就新布景 |
| 情绪、表情时点、眼神、台词、肢体表演 | 导演 | 眉眼嘴可见性、妆发衣领和背景分离 | 不另写微表情表演链 |
| 曝光、布光器材、光学参数、剪辑 | 摄影/导演/剪辑 | 世界光源、表面反射与美术色彩关系 | 数值意图不冒充平台控制 |
| 能力、附件槽位、费用、提交、结果账本 | 宿主执行器 | 资产用途、条款覆盖、依赖和美术 QA | 缺少能力证据阻塞依赖执行 |

## 实际机器映射

`ArtIR.director` 指向本地 DirectorIR 文件、原始字节SHA-256、project_id和revision。
`canon.uri` 必须等于它的 `canon_ref`。Canon具体版本由 `canon.revision` 与宿主记录持有；
DirectorIR v1.0没有可独立比对的 Canon 版本字段，本包不虚构该字段。

- `set.scene_id/location_entity_id/coordinate_system` 对齐 `DirectorIR.scenes`。
- 已有 `assets.entity_id` 对齐 `DirectorIR.entities.id`；新陈设用 `origin=design_proposal`、entity_id=null。
  这只是本地设计ID，宿主批准后才登记正式ID，不能伪装为既有资产。
- `shots[].director_pointer=/shots/N` 读取同ID同场景的原镜头；可选子集，但顺序不可倒置。
- `events[].director_pointer=/shots/N/phases/M` 引用状态事件的导演依据。
- `performance_support.required_parts` 必须包含在该人物的 `composition.subjects.visible_parts` 中。
  本版能发现“看不到眼睛却要求眉眼可读”，不能自动理解表演文字是否真实成立。
- `handoff.shots[].director_context` 是只读原镜头快照，保留哈希链；不是美术重新创作的字段。

宿主合并顺序：核对来源版本 → 校验两份 IR → 读取美术补充与导演原镜 → 联合审查冲突 →
绑定已批准参考 → 解析真实能力 → 形成宿主 ExecutionIR → 执行与回收 → 媒体QA。
本包不会将自己的 `handoff.json` 直接交给现有 `dg.py` 冒充其 ExecutionIR，也没有自动双向同步。

## 字段级修订建议

冲突记录写：输入版本/哈希、owner、JSON Pointer、当前值、冲突证据、建议值、影响镜头、验收条件。
美术可修饰未锁定背景以避开脸部；需要修改 `/shots/2/camera` 或 `/shots/2/performance` 时交给导演。
引用已有用户决定即可，不为每个补丁重复索要批准。已锁硬事实变更必须有明确决定来源。

提供的 `examples/fixtures/teahouse.director.json` 是当前导演示例的原样冻结测试夹具。
真实项目绑定实际原文件；夹具不是第二个项目事实源，也没有声明它已获画面批准。
