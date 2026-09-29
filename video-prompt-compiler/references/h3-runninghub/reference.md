# H3 Ref2VA：全能参考

依据 [官方参考指南](https://huggingface.co/MiniMaxAI/MiniMax-H3/raw/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md)，2026-09-29 核对。保留用户对每项参考的使用范围和禁止继承项，不能因为上传了视频就擅自复制人物、剧情或声音。

## 六个字段，职责分离

```text
subject_definitions: ...
summary: ...
retention_analysis: ...
detailed_description: ...
overall_soundscape: ...
non_diegetic_music: N/A
```

`subject_definitions` 定义稳定的 Subject；`summary` 声明任务；`retention_analysis` 列清保留/替换策略；`detailed_description` 写实际镜头时间线；最后分开环境与配乐。正文为英文，台词、歌词、可见文字保留原文。首镜无 At，后续剪切使用 `At MM:SS.mmm`。

Subject 是内容实体，不等于文件：一个 Subject 可由多份图共同定义，一张图也可能含多个 Subject。Picture 是图像来源，Video 是视频/运镜/剪辑等来源，Audio 是明确启用的声音来源。不能把“只参考运镜”转成“保留全部视频内容”。为每个主体标明身份、服装、场景等保留边界及禁止继承维度。

## 原生节点引用顺序不可猜

先检查真实 API 图。当前固定版本的原生节点顺序是图片→每段视频（若连入伴随声轨，先登记它的 Audio 标签）→独立音频。Picture/Video/Audio 各自编号，输入后缀 `_7` 不是提示词中的编号 7；字典输入顺序也不能随意排序。

例如一张图、一段带已启用声轨的视频、一个独立音色参考，映射为：

| 实际输入 | 提示词标记 |
|---|---|
| 第一张图片 | `<Picture 1>` |
| 第一段视频的伴随声轨 | `<Audio 1>` |
| 第一段视频画面 | `<Video 1>` |
| 独立音色参考 | `<Audio 2>` |

伴随声轨未连接时，不能假称已参考它。反之，连接了声音也要说明是复制信号还是仅参考音色。模型文件预算为图片≤9、视频≤3、独立音频≤3、文件总数≤12；原生伴随声轨与视频配对，不再作为另一个独立文件计数。平台节点版本及素材字节须另查。

## 保留策略写清楚

视觉策略使用 `fully_preserved`、`partially_preserved`、`attribute_transfer`、`weak_reference`；明确策略对应的是整个主体还是声明过的属性集合，不能用 fully_preserved 掩盖删改。

每个声音标签在 `retention_analysis` 单独一行写明：

```text
<Audio 1>: partially_copy - retain the room tone under new dialogue.
<Audio 2>: reference - preserve voice timbre, not source words.
```

`fully_copy` 表示整段最终音轨一比一保留；新增台词、配乐或混音通常不能仍声称 fully_copy。部分时段/声层复制用 `partially_copy`，只取音色或风格用 `reference`，弱参考用 `weak_reference`。整体声音计划不能与镜头内声音相互矛盾。

只继承角色身份/服装的图不决定首帧构图；只有用户明确要求并且模式支持时才把构图作为锚点。不能混用 FL2VA 首尾帧端口和 Ref2VA 参考端口。复杂连续动作需要拆分验收，文本、几何控制、参考声音各自不能替代其他通道。
