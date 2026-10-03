# Gemini Omni：入口隔离

核验日期2026-10-03。官方资料见社区目录的 `OMNI_CLOUD_T2V`、`OMNI_CLOUD_MODEL`、`OMNI_DEVELOPER`、`OMNI_GUIDE`；本文件为本项目独立归纳。

## 本轮实现

精确target是 `gemini-omni-1.1-flash-preview`：Google Cloud Agent Platform 的文生视频提示计划，单次3至10整数秒，画幅16:9或9:16。360p/720p为原生分辨率选项，1080p/4k属于升采样交付。本地profile只开放text模式，引用上限设0是**当前适配实现边界**，不是说模型不能参考图片或视频。

原生AVIR的逐镜动作、机位、光源、台词、声音仍完整投影。适用技巧包括按合同明确一镜到底/切镜、把负向限制写成正文、以主体与区间描述局部修改。没有独立negative_prompt字段声明；不输出猜测的API载荷。实际执行始终submitted=false/runnable=false。

## 不能混用

Gemini Developer API的 `gemini-omni-1.1-flash`、Cloud的preview ID、Veo以及Kling Omni不是同一个入口。本地不把它们设为别名。Cloud文生视频请求中duration的秒字符串以及响应配置形状，不直接推广为Developer请求字段。

所读Developer API文档描述previous_interaction_id多轮编辑和延长；输入音频参考不支持，参考视频音轨会被忽略。输入来源、clip时长、地区和存储状态有各自限制。生成音频不等于支持上传音轨参考。上述Developer特性是对照与未来适配依据，不说明本地Cloud编译器已实现它们。

edit/extend在本地仍由原生未实现操作门阻塞；不能把“修已有视频”降级为“新生成一段”。累计延长长度也不能成为首次生成的时长上限。任何未来升级需提交新的能力快照、输入与时间合同、真实请求/结果解析及对抗测试。

## 检查顺序

先核对精确入口和账户，再核对原文锁定、时长画幅、素材消费与声音归属；生成后才核对实际媒体与父版本差异。低分辨率候选可用于明确授权的预演，但不能默认为最终交付降质。模型营销页面的能力不能替代当前API条款。
