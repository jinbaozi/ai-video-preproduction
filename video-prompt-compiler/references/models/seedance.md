# Seedance 2.0 / 2.5

资料：[2.0官方模型页](https://seed.bytedance.com/en/seedance2_0)、[2.0论文](https://arxiv.org/abs/2604.14148)、
[2.5官方发布](https://seed.bytedance.com/en/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5)。

2.0使用统一文字、图片、音频、视频输入及音视频联合生成。提示词先界定参考用途，再按时间写动作、摄影机、声音与身份连续性。
2.0模型预算按4–15秒检查；不是任意渠道账户的已确认参数。
2.5官方提出最长30秒、增强参考和时间定位编辑。编译保留原始长度与叙事节拍，不因为模型上限更长而扩写剧情。
长叙事把各角色、场景、动作、切镜及声音职责写清；白模可用于空间/运镜意图，不能凭空增加白模附件。

两版本各有独立profile。当前输出参数为intent_only，原生槽位UNRESOLVED，payload_draft=null。
即使官方展示`@Image`或大量附件，也不自动当作用户实际网页/API的槽位与上限。
使用实际渠道前读取当前契约：模型ID、mode、duration、ratio、resolution、references及精确引用规则；
核验后新增渠道profile与测试，不能覆盖model-level源记录。
edit/extend在能力概述中有记载，本版CLI对这些操作明确阻塞，不能将编辑视频伪装成新生成。
