# 编剧上游与导演实现

故事前提、事件因果、人物选择、结局、台词文本、潜台词、人物认知和信息顺序约束由 screenplay-grammar 维护。导演负责视点、构图、机位、走位、表演细节、声音实现与剪辑。改景别无需改剧本；改“怀疑”为“识破”必须返回编剧修订。

```bash
python scripts/dg.py import-screenplay /path/to/director-handoff.json --out director-brief.json
python scripts/dg.py validate director.json --screenplay-handoff /path/to/director-handoff.json --screenplay-map screenplay-map.json
python scripts/dg.py compile director.json --target generic-t2v --out outputs/v001 --screenplay-handoff /path/to/director-handoff.json --screenplay-map screenplay-map.json
```

导入只输出只读简报，不编造机位或 DirectorIR。hand-off 引用的 ScriptIR 必须通过来源/完整性检查并有当前版本语义复核；这不是自动批准。

screenplay-map.json 遵循 schemas/screenplay/director-map.schema.json，记录 screenplay_sha256、director_sha256、reviewer、findings 与 mappings。每项 mapping 对应一条来源指纹，填写目标原生 hard clause、实际视听字段断言及理由。台词需同时保持文本和 speaker ID；硬要求不能只留在旁注或 sources。

编译输出 screenplay-binding.json。未提供编剧包的独立旧任务为 NOT_CHECKED，不宣称完成编剧一致性验收。总工作流在新六模块锁下强制映射；旧五模块项目沿用旧路径。

协议与 schema 由编剧维护并在发布时检查副本字节一致，不 import 同级源码。机读检查覆盖显式条件与指纹，语义等价仍由当前 Agent 实际复核，不能把本地声明当专业盲评。
