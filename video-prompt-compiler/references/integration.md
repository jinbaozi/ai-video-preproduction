# 与当前工作区Skill集成

本包独立运行，不要求安装其他Skill。当前读取过同级`director-grammar`和`production-design-grammar` v1.0契约；
未改动它们。导入由Agent按当前源文件/schema完成，CLI只接受AVIR，不假装存在自动双向转换。

| 所有者/来源字段 | AVIR目标 | 转换边界 |
|---|---|---|
| 宿主Canon身份、资产ID、用户决定 | entities.locks、sources、contract | 保留源URI、revision、SHA-256和字段定位 |
| DirectorIR.entities / scenes | entities / scenes | 逐项显式映射，不复制未知属性 |
| DirectorIR.shots中的camera、composition、phases | shots.camera/composition/performance | 转换时间单位；机位、人物和道具路径分别保留 |
| DirectorIR起止状态与声音 | start_state/end_state、audio | ID对齐、说话人归属与原文不改 |
| ArtIR.set/assets、视觉世界/材料/服化 | scenes、entities.appearance、assets | 导演持有机位/动作，美术补充不得改写它们 |
| ArtIR.director.uri/sha256、director_pointer | sources URI/hash/locator | 只读核验链接，不冒充已经兼容的ExecutionIR |
| video-storyboard-prompter-zh的分镜时轴、performance_plan/camera_plan/sound_plan | shots、audio | 读取当前schema再映射；不假设其CLI有compile-prompt命令 |

先读原文件→确认所有者→建立字段对应及无法表达项→按AVIR schema转换→检查字段断言→编译。
发生冲突记录source revision、owner、JSON Pointer、旧值、冲突、建议值及影响镜头，由原所有者修订。
编译器不能用“优化”改变导演剧情、角色姿态或美术主体。已有用户决定直接沿用，不逐字段重复确认。
单独创意输入没有上游时，Agent可在需求范围内做必要设计，并将其标作design来源。
