# 导演：独立与协作契约

落实编剧确定的信息顺序与剧情约束，决定视听意图、关键表演与已锁定镜头；分镜细化未锁部分。独立使用保留现有compile与导出命令；协作模式的最终视频提示词统一交给video-prompt-compiler。

## 独立入口

只安装本Skill即可完成本领域任务，不import同级技能代码。单条需求给可用正文；需要可追溯制作包时，由Agent建立原生结构并运行已有校验器。没有上游时，在用户范围内补充设计并标注来源，不伪造Canon批准或素材。

## 协作入口

ai-comic-drama-workflow V5由当前Agent顺序调用本模块。任务信封给出当前范围、输入文件/哈希、角色、锁定项、模块版本和输出契约。
先读原件与当前Schema，再使用现有命令；不要求用户填写JSON，不递归启动另一个总工作流。
专业包单独发布；总包携带同源构建的锁定副本，不维护第二套专业规则。

结果交回role-result/5.0：task_id、context_fingerprint、原生artifact路径、artifact_sha256、checks、complete，以及conflicts/unresolved；导演/美术下游另提交handoff逐条映射。
图像优化任务使用prompt和checks；真实生成由宿主负责。没有外部模型调用也可以完成静态任务。

原文事实、实体ID、真实文件名、版本/哈希、台词和用户锁定项不可静默改写。可复制正文保留图片真实名称及必要槽位；对白采用`说话人：“台词内容”`。
表演细节必须进入相应正文，按景别/时长选择眼神、眉眼、手部、发力、空间轨迹、语气和停顿；不能增加原文没有的事件来填字段。
矛盾返回owner、来源、字段、现值、建议和影响范围；有效旧决定直接沿用。修订创建新版本，保留旧包和真实媒体记录。
静态检查、图片审核和视频执行分别记录。submitted=false或NOT_RUN不能由人工改字段冒充执行。

结果格式必须声明`schema: role-result/5.0`。任务内`handoff.required_handoffs`给出上游硬要求及源指纹；交回requirement_id、source_fingerprint、target_checks、reason，分镜另给target_clause。先在目标原生Schema中保留硬合同，再解释语义映射；仅复制文字或留在旁注不算满足执行要求。

编剧上游交接必须按 [screenplay-handoff.md](screenplay-handoff.md) 验证，角色认知、对白语义和结局的修订返回编剧。
