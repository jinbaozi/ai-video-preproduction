# V6 真实宿主演练索引

本目录保存本次 Codex 会话执行原创句子“雨夜，甲把一封未拆的信交给乙；乙确认封口完整后收进背包。”的精选证据。每个子目录有自己的 `README.md` 与 `SHA256SUMS`，保留可离线阅读的输入、候选、审阅、工具回执和逐项检查；锁定 Skill 模块全文不重复收录。

| 归档 | 实际状态 | 运行项目 |
| --- | --- | --- |
| [`canon/`](canon/) | text-only Canon 已经真实创作、返修、独立审阅，V6 `ACCEPTED`，V5 `canon.complete=true` | `/private/tmp/ai-video-v6-real-efKlQy/project` |
| [`screenplay/`](screenplay/) | text-only Screenplay 已经真实创作、独立审阅，V6 `ACCEPTED`，V5 `screenplay.complete=true` | 同上 |
| [`director/`](director/) | 原 Director 两批 `handoff` 失败、第 3 批接受后因语义审阅绑定失效而 `STALE`；重建版 rev220 后又因 Compile 机位坐标矛盾失效；跨责任返修在 rev386 真实创作、独审并 `ACCEPTED` | 同上 |
| [`art/`](art/) | 原 Art rev132 与重建版 rev238 曾接受后失效；跨责任返修下游新 Art 真实创作、独审并在 rev422 `ACCEPTED`，媒体 `NOT_RUN` | 同上 |
| [`storyboard/`](storyboard/) | 原分镜首批校验摘要错误、第 2 批接受后因语义绑定失效而 `STALE`；重建版 rev276 后再因 Director 返修失效；新分镜真实创作、独审并在 rev435 `ACCEPTED`，媒体 `NOT_RUN` | 同上 |
| [`control/`](control/) | 历史取消和多次代码指纹失效均保留；状态读面修复后又由真实创作者/独审重建，于修订 782 曾 `ACCEPTED`，随后严格前驱门检出旧原生编译审阅仍有效的选路错误；媒体/模型轨迹 `NOT_RUN` | 同上 |
| [`routing/`](routing/) | 本演练局部 `seedance2.0` prompt-plan 静态目标决策已保存；旧 `STALE` skip 的历史证据哈希冲突已修，修订 324 进入真实 Compile 派发 | 同上 |
| [`compile/`](compile/) | 旧编译坐标失败及 graph-only RoleResult 错误均保留；修订 695 曾接受静态包。后续 Compile 的独立审阅于修订 938 补登记接受，修订 941 正文复核待真实派发，媒体 `NOT_RUN` | 同上 |
| [`compile-semantic/`](compile-semantic/) | 旧 `compile_semantics=FAIL` 的信件终态可见性冲突经责任重建关闭；新 `compile_review` 真实派发，17/17 硬条款静态审阅通过，于修订 707 `ACCEPTED`，后期义务仍 `PLANNED` | 同上 |
| [`preproduction-final/`](preproduction-final/) | 真实前期 QA 与内核交付曾在修订 738 返回 `DELIVERED`；只读 `status` 同时错误显示 `BLOCKED`。此状态快照与源码指纹修复后的重演分开记录，视频未生成、视频验收 `NOT_RUN` | 同上 |
| [`status-recovery/`](status-recovery/) | 记录读面修复后的源码指纹、修订 739–766 正式失效链，以及修订 769 新 Control 待派发动作；该窗口无虚构宿主回执 | 同上 |
| [`replay/`](replay/) | 同一 Director 派发命令重放返回 `ALREADY_RECORDED`；修改旧 `expected_revision` 返回 `COMMAND_COLLISION`，revision 均不变 | 同上 |
| [`full/`](full/) | 独立 full 项目已真实接受 Canon、Screenplay、新 Director、Art 及甲/信件/背包/雨夜四项静态图片提示词；乙首批失败历史保留；rev274 停在 image-capability 决策，图片生成/视觉审阅与后续分镜尚未执行 | `/private/tmp/ai-video-v6-full-demo/project` |

text-only 链保留了 V5 快照语义绑定失配、导演机位坐标冲突、AVIR 终态可见性冲突及 graph-only RoleResult 错误的失败史。每次影响输入或运行码的变更均使旧任务 `STALE`，由真实创作者和独立审阅重建。修订 738 曾形成前期交付与 [text-only 交付索引](preproduction-final/delivery-index.md)，但只读 `status` 把历史失败也计为当前阻断；该读面差异正按新源码指纹修复和重演，修订 738 暂作为历史证据。full 链从新项目重新开始，不复制 text-only 链的已审结历史；静态图片提示词已审结四项，实际图片素材尚未提交或视觉验收，未调用付费图片或视频生成接口。

JSON 包装记录的是实际 Codex 工具返回与宿主对智能体原文消息的结构化登记；内核事件和候选哈希提供任务/批次/输入/审阅绑定。共享文件系统中的候选所有权是工作流约束，不是操作系统隔离。临时项目保留本轮完整运行状态；本归档特意保留必要的小型内容，避免以后仅靠绝对临时路径理解结果。
