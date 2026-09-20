# 真实交接

编译后的 director-handoff.json 绑定 script-ir.json 原件字节哈希和内容指纹。导演自带相同的协议校验代码与 schema，解压两包即可协作，不从编剧源码目录 import。

导演先用 dg.py import-screenplay director-handoff.json --out director-brief.json 查看约束与自由范围，再由 Agent 编写 DirectorIR 和 screenplay-director-map/1.0。映射填写 screenplay_sha256、director_sha256、reviewer、findings、mappings。

每项 mapping 包含 requirement_id、source_fingerprint、target_clause、target_checks、reason。target_checks 指向真实镜头、节拍、实体、场景或时轴，并被目标原生 hard clause 的 paths 覆盖；台词及字面锁使用 equals，语义约束记录复核理由。仅把要求写入 sources 或备注不能过关。

导演 validate/compile 添加 --screenplay-handoff 与 --screenplay-map；缺一不可。变更任一已审导演字段会使映射过期，应重新审查更新映射，而非改故事。核验不证明自然语言语义等价，评审是有指纹的本地声明。

总工作流第二阶段加载锁定编剧模块，第三阶段强制映射。role-result/5.0 的 handoff 仍是数组，每行除 mapping 字段外包含同一个 review 对象（screenplay_sha256、director_sha256、reviewer、findings）。源主稿不复制成另一份可编辑 Canon。

新人物或剧情事实先在 canon.proposals 登记；已有授权允许时由当前 Agent 修订唯一 Canon，登记实体 ID，再重绑剧本、清除提案并复核。冲突返回 Canon 所有者；普通创作补充不自动增设用户审批。

旧五模块锁继续旧流程；显式 update-modules 到六模块后，旧式纯文本剧本标记失效，Agent 根据原文整理新 ScriptIR。不会靠包升级自动声称剧情已经通过检查。
