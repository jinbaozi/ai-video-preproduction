# Agnes Video 2.5 / Flash

仅绑定国际站`https://apihub.agnes-ai.com/v1/videos`的[官方2.5文档](https://www.agnes-ai.com/zh-Hans/docs/agnes-video-25)
及[Flash差异](https://www.agnes-ai.com/zh-Hans/docs/agnes-video-25-flash)，快照2026-09-19。

提示词按主体场景→动作→镜头→风格→声音节奏→一致性组织，引用先界定职责。
`seconds`字符串4–12，`n=1`；比例使用白名单，分辨率提升为size。禁止凭空发送fps、width、height、steps等参数。
`1K`为固定方形，不能借它承诺其他画幅；具体像素应按实收元数据确认。

| 模式 | 映射 |
|---|---|
| text | 无媒体字段 |
| keyframe | 图片绑定first_frame/last_frame，至少一个；不混参考数组 |
| reference | images/audios/videos至少一项，不能混首尾帧 |

reference数组按本次引用资产首次出现顺序生成；每类从1编号为`<Picture N>`、`<Audio N>`、`<Video N>`。
共享同一资产只上传一次，多个职责仍保留。视频数组元素是`{"url": ...}`，不是纯字符串。
2.5最多8图/1视频/3音频，总12；Flash最多5图/3音频、无有效视频输入，size只能720P。
参考文件缺失/哈希不符/未查看会阻塞。无公开URL时保留附件清单，不伪造payload；URL可用性仍需提交前核验。

公共文档说明声音与节奏参考，但未充分确认本包依赖的原文对白原生生成契约，因此native_audio暂为null。
强制native对白会阻塞；已有后期配音约定用post，视频提示词仍保留画内台词/口型。不得偷偷改声音路线。
引用素材尺寸、字节总量、帧率、音视频片段长度与URL有效性属于G2；本版未实现媒体探测器，payload_draft不是提交资格。
提交/查询由宿主实现，本包没有网络动作。轮询使用当前官方video_id+model_name规则，不能套代理服务的id协议。
