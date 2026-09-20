# Kling 3.0 / 3.0 Omni

[3.0官方指南](https://kling.ai/quickstart/klingai-video-3-model-user-guide)、
[Omni官方指南](https://kling.ai/quickstart/klingai-video-3-omni-model-user-guide)。

使用明确ID`kling-v3`或`kling-v3-omni`，避免把泛称Kling固定成旧版本。
按Shot组织时间、景别、主体运动、摄影机、元素一致性、台词说话人与原生声音；最长15秒是模型级预算。
多模态参考或编辑需求优先审查Omni，但用户已选普通V3时先说明差异，不自动改目标。
角色元素、参考图、参考视频与声音职责分开；在未获得真实元素ID前不生成伪造`@角色`绑定。
本包保留真实文件名与asset_bindings，槽位UNRESOLVED；没有声明API body与网页元素库可互换。
当前profile只做新生成提示词计划。模型概述中的编辑能力不等于本包已实现视频编辑载荷。
