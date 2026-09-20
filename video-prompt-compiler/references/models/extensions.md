# 扩展模型

## MiniMax H3

[官方模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3)说明Context-IR、Base、Regenerate分层，
Context-IR托管预处理没有完全开源。内部AVIR不能当作官方Context-IR序列化，通用描述不能冒充H3-Base专用输入。
本版提供结构化音画上下文提示词计划，4–15秒模型范围；保留主体关系、参考角色、时间、动作与声音关联。
真实H3托管/本地入口需另行核验专属tokenizer、帧网格、模型checkpoint和媒体接口。

## Veo 3.1

[官方文档](https://ai.google.dev/gemini-api/docs/veo?hl=en)给出4/6/8秒；参考图与1080p/4k要求8秒。
本版检查这些组合，提示词分开画面/运动/声音；其他入口参数只保留制作意图，不输出未经验证的请求body。
扩展、首尾帧和参考图是不同操作。除本版已支持的新生成text/keyframe/reference外，其他操作明确阻塞。
非英语语义由Agent根据用户要求决定是否翻译，台词原文不改变，不假装已做翻译质量评测。

## Wan 3.0与Runway Gen-4.5

报告建议纳入。Wan官网正文未能读取；Runway本次只读取到API目录，未取得目标完整操作契约。
已注册草案后端，状态BLOCKED，不把报告中的参数当作本次已确认API事实。
Wan文档/网页参考先抽取页码/段落与事实，再写sources和场景；原文不直接作为视频媒体附件。
Runway保持prompt、比例和时长分开，待当前官方操作schema核验后再提升为原生参数。
新增完整profile需来源快照、模式与参数组合、参考语法、错误条件和契约回归，不靠改名称“支持新模型”。
