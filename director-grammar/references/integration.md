# 与现有工作流接入

本目录可独立使用，也可由 `video-storyboard-prompter-zh` 在分镜/提示词阶段调用。
不要求另一个Skill存在；已有总技能存在时引用其Canon、实体ID、资产版本和能力来源。
本次不更改原技能的Schema、状态机或脚本；没有自动迁移/双向同步声明。

| 上层当前概念 | director-grammar | 处理 |
|---|---|---|
| Canon / sources | canon_ref / sources | 指向原件和版本，当前任务只持有必要切片 |
| character / location / prop | entities | 复用稳定ID、身份与事实，不重写原件 |
| segment | scene或交付片段边界 | segment和shot不是固定1:1 |
| timeline / performance_plan | phases / performance / dialogue | 明确单位转换：上层秒→本包整数帧 |
| camera_plan / visual_style | camera / composition / lighting | 保留拍摄意图与真实参数的边界 |
| start_state / end_state | 逐实体状态 | 补世界坐标、支撑与接触时标为设计补充 |
| assets / attachments | assets / references | 文件名、ID、哈希、维度权威与槽位各自记录 |
| model_profile | capability snapshot | 只从已核验入口映射，不按品牌猜测 |
| 项目状态/批准记录 | contract.authorization_ref | 上层仍为唯一权威，PLANNED不自动推进总项目 |

建议调用点：上层分镜草案 → 导演模块校验/补齐 → 上层复核事实 → 冻结DirectorIR → 编译。
返回导演合同、提示词、附件表、执行计划、损失和QA待办；上层仅更新相应片段。

外部入口执行器消费ExecutionIR时，应检查status、losses、素材、授权和预算，再把真实job/take结果写回自己的账本。
本包ExecutionIR固定 `submitted=false` 是离线回执，不能在原件里直接改成true伪装运行日志；实际回执另存并关联哈希。
