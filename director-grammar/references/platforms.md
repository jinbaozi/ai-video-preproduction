# 平台能力边界

快照日期：2026-09-19。只代表已读取文档/本地协议，不代表用户当前账号、区域、额度或产品更新后的入口。
外部执行前核对具体入口；文档更新、账号权限差异或字段不匹配时重编译。未知不是不支持的断言。
每条能力记录分别保存 provider、entry_point、model_id、mode、版本、日期、source_refs、证据等级与live_test。

| target | 本版实际输出 | 边界 |
|---|---|---|
| generic-t2v | 完整中文镜头正文及合同 | 离线通用文本，不是模型请求 |
| generic-i2v | 动作、摄影、终态正文+首帧表 | 恰好1张已批准真实首帧；无平台专属槽位语法 |
| minimax-hailuo-2.3-t2v | 文档支持的JSON请求体和运镜词法 | 仅该模型T2V，不支持此后端附件或原生配音 |
| runway-gen4-ui-i2v | I2V文本与UI填写表 | Gen-4界面文档；不伪造Runway API字段 |
| kling-3-ui-multishot | 一项任务的自定义多镜头UI表 | VIDEO 3.0 UI，真实分镜切点仍需实片测量 |
| libtv-agent | 目标+镜头+硬要求+验收的message草案 | 会话Agent可重新规划，需核返回计划；未提交 |
| jimeng-entry-unverified | 通用方向与BLOCKED回执 | Seedance模型资料不足以锁定即梦具体账号入口 |
| oiioii-entry-unverified | 通用方向与BLOCKED回执 | 已查公开创作资料，未取得可调用契约 |
| seko-entry-unverified | 通用方向与BLOCKED回执 | 已查产品页面，未取得可调用契约 |

## MiniMax

[官方T2V文档](https://platform.minimax.io/docs/api-reference/video-generation-t2v) 支持本包选定模型的运镜词法。
本适配器选择768P的6/10秒或1080P的6秒，提示词最多2000字符；`prompt_optimizer=false`减少服务端改写。
实际参数只输出 model、prompt、duration、resolution、prompt_optimizer；镜头焦距、坐标、帧率不伪装成原生字段。
词法只有已核验映射；例如推进与拉出分别映射相应命令。环绕仍是自然语言，不能声称它有已核验原生命令。
某片成片4秒可以生成6秒再选用4秒；选用区间与镜头节拍需在真实素材中重新确认，不能默认前4秒总可用。

## Runway

[官方Gen-4指南](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide)
建议I2V聚焦运动、用直接正向描述；首帧负责静态视觉。本版保留5/10秒UI计划。
编译器不做自由翻译或LLM二次改写。希望英文提示词时先把IR的文案字段按同一事实改为英文，再重编译。
使用正向合同表达（“全程固定”“只呈现示范步骤”）；不要把长负向列表灌入正文。

## Kling

[官方VIDEO 3.0指南](https://app.klingai.com/cn/quickstart/klingai-video-3-model-user-guide)
区分Multi-Shot和Custom Multi-Shot；本包只构造自定义模式的镜头内容/时间填写表。
`request_kind=ui_fields` 内的字段是本项目填写说明，不能直接POST到API。
多镜头任务可承载多个Shot，但不能保证生成内每个剪辑边界精确到计划帧。
当前适配器未实现元素库/多参考绑定；带这些需求时会阻塞，不能自动舍弃素材转T2V。

## LibTV、即梦、OiiOii、Seko

LibTV沿用[官方公开会话协议](https://github.com/libtv-labs/libtv-skills)的message形状，仅生成草案。
实际上传时需按入口核验文件回执与引用方法；本版未实现上传，带附件任务不会被当作已绑定。
其余三个入口不猜API、不安装私有Skill、不登录付费提交。可交付人类可执行的导演合同，再补入口证据。

## 扩展

更新能力时记录“具体主张—来源定位—版本—当前可用条件”。渠道分原生参数、专用词法、自然语言、后期、不支持、未知。
证据分官方说明、界面观察、接口测试和实际成片；前一个等级不能代替后一个。
新增后端要测合法输入、非法参数、资源缺失、时长超界、引用冲突和语义损失；不得靠品牌名继承所有能力。
