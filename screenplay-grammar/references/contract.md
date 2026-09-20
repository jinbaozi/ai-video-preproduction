# 有来源、有结构、有约束、有执行路径、有验收条件

每条 clause 定位 sources 的真实输入或明确原创设计，paths 指向正文/人物/命题/叙事内容，realization 声明如何在正文实现，steps 声明创作、检查、编译和导演交接的执行顺序，check_ids 对应具体检查。

hard 必须连接 blocking 检查；不得将仅在备注中的要求算成实现。static 检查给 JSON Pointer 断言；semantic 检查给可回答的问题与所需证据。语义评审记录 reviewer、findings 和完整内容指纹，不能用空模板作 PASS。

主稿状态 DRAFT/READY 与静态状态、语义复核声明、专业盲评、真实媒体各自独立。READY 是当前 Agent 已复核的交付声明，不是用户批准。用户授权与业务批准沿用项目已有记录，工具不会自行授予。

导出草稿允许，但 ready=false 的 handoff 不能作为完成的导演上游。历史待核验、未登记 Canon 提案及关键未决事项仅阻塞其正式交接，不阻塞无关写作。

source.sha256 是文件字节证据；content_sha256 对携带哈希的引用去掉运输路径后计算，允许原件无损搬迁。正文和合同的实际变动仍使评审失效。
