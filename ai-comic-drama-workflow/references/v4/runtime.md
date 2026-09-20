# Codex执行接口

在仓库根目录使用Python3.12运行 `PYTHONPATH=src python -m ai_comic_drama_workflow`，或安装后的 `ai-comic-drama`。

- `init <资料...> --project <新目录> [--input-type novel|screenplay|storyboard|text]`
- `host <项目> --capabilities <JSON>`：models为model/reasoning_effort对象数组；image_capability为available/unavailable/unknown；evidence为当前宿主工具清单证据。环境变量或仅找到Python不能证明能力。
- `run <项目>` / `status <项目>`
- `submit <项目> --result <JSON>`
- `resume <项目> --decision <JSON>`：request_id、value；自定义选项另加custom_value。
- `revise <项目> <阶段号> [--shot-id ID|--asset-id ID|--scene-id ID]`
- `add <项目> <补充资料...>`
- `validate <项目> --final` / `export <项目> [--draft]`
- `copy-project <旧项目> --destination <新目录>`；status旧项目只读。

## AgentResult

读取TaskEnvelope，返回 task_id、context_fingerprint、execution、findings、qa；创作任务另返回data（严格遵守任务内output_schema）。execution包含model、reasoning_effort、实际agent_id和dispatch_evidence。qa包含passed和实际检查记录。不能以模型自报文字伪装宿主派发证据。

图片任务返回media：provider、output_path、sha256、input_hash、bindings、call_evidence；以及qa.visual_findings。bindings必须与当前job一致，代表真实输入，不仅是提示词文字。正式图名由Kernel管理。用真实结果，不制造fixture。

主代理在每个创作或审查任务上使用宿主子代理派发工具，传入TaskEnvelope指定model与reasoning_effort；当前阶段最多5镜一批。不得把整套Skill规则塞入子代理。若派发工具不支持该组合，停在能力门，不用普通文本声明已切换。

阶段既有资料可复用，但最小叙事事实和连续性上下文仍需建立。最终提示词由Kernel编译，Astra阶段10负责事实覆盖审查；确定性编译本身无需模型调用。

V4保留legacy模块只用于旧测试与历史兼容证据；活动入口不运行这些模块。旧13阶段参考文档不是V4阶段规则。
