# 模块、独立发行与项目锁

六个专业技能各自自包含。总工作流的assets/bundled-skills保存它们的标准发行包，modules.lock.json锁版本和SHA-256。
项目初始化复制归档字节；运行按需解包到项目runtime/modules/<hash>，再使用模块自己的CLI/Schema/规则。
后续更新总Skill不改变已有项目的归档。缓存内容或归档哈希变化会被拒绝；不得静默用相邻开发目录覆盖。
独立安装模块与锁完全相同时可复用同一发行物；当前实现始终优先项目锁定副本，避免全局安装差异。

在开发工作区执行 `python scripts/package_suite.py --workspace <七个源码的父目录> --out <发行目录>`。
它从六份专业源码构建独立包，将同一包字节放入总包，再构建总工作流包。没有第二套人工专业规则。
每个Skill自己的scripts/package_skill.py也可独立打包；总包单独打包前应已有完整bundled-skills与modules.lock。
每包为单根目录、排序成员、固定ZIP时间与权限，附manifest和SHA-256；排除输出、虚拟环境和缓存。

当前活动集合固定七个Skill；video-storyboard-prompter-zh保留历史源码和发行包，不纳入新套装。

## V5.3 编剧接入

新锁包含 screenplay-grammar，共六个专业模块、七个发行技能。第二阶段提交原生 ScriptIR，导演阶段需要来源绑定、原生硬合同与语义映射。原有五模块锁继续使用旧编剧路径；update-modules 显式升级保留旧归档与媒体，失效旧式剧本及受影响下游，不自动改写源稿。
