# Flow 参考重制与真实剪辑：历史 0.16.0 实现

此文件保留 2026-10-01 原始实现与历史测试，不是当前修复版验收。当前结果见 `runtime-recovery-validation.json`。

## 范围

基于 `496cdd58a8965a239fb6484180499d37f008d57f`，新增默认 lean/full 的 Google Flow 2K 宿主执行合同、真实文件提升与下游引用门；视频目标增加固定版本 Jianying Headless 安装/执行适配器、可编辑时间线及 MP4 验收。普通创作与身份定稿自动继续，权限、费用、许可、硬冲突及质量门保留。

新 `start` 将创作策略、Flow 配置、剪辑后端和严格生产策略冻结在项目/state 中。已有项目、原 `init` 不迁移。audited 保留独立审阅；未加入图内 Flow 节点前，明确拒绝该组合，不直接替换已接受候选。

## 实现

- `flow.py`：真实解码/像素、源引用与调用证据、六类对照、原生/官方放大来源、派发前记录、不确定结果回收、已解决阻塞证据和有界重试
- `jianying.py`：独立核心固定 commit 与逐文件验证；分离安装和执行授权；非商业许可及商用书面许可门；真实官方 CLI 计划/构建/验证/导出
- `editing.py`：绑定 EDL、源文件、规格、计划、工程、核心回执和 MP4 的一体校验，快照可编辑工程并复验
- 原生内核：Flow 图作为当前 media 进入实际附件链；直接编译/生产/交付无法绕过当前前期包与 Flow 门；相同收据重放不失效已接受下游
- `11-edit/`：只在新 compact 视频项目产生实际剪辑产物时创建；旧布局保留

## 本地验证（2026-10-01）

- 工作流：`python ai-comic-drama-workflow/scripts/run_tests.py`，376 项通过
- 视频编译器：`python -m unittest discover -s video-prompt-compiler/tests -p 'test_*.py' -v`，278 项运行，275 项通过，3 项因无实际 Blender 运行时明确跳过
- 新增针对性测试：Flow 23 项、剪映适配器 23 项、生产管线集成 21 项，包含原图/输出/历史证据篡改、未知调用回收、账户错误恢复、二次收据不改下游、EDL/输出错配、严格账本落盘与父相对路径
- 本地 FFmpeg 实际合成的测试媒体通过解码帧数、尺寸、帧率、音轨、哈希核验；这是测试夹具，不是用户影片，也不是第三方核心执行
- 未授权 `editing-install` CLI 实测返回退出码 2，未创建目标目录、未下载/执行核心
- 共享源码一致性检查、Python 编译与 `git diff --check` 通过
- 七包隔离与可重复构建：以 `flow-editing-validation.json` 的最终结果为准

## 独立审查修复

已补齐并回归：核心 probe 与账本格式统一；剪辑证据和本次 EDL/规格/输出绑定；lean 严格生产与当前前期包绑定；错误账户的失败可持久回收；收据重放幂等；相对路径规范化。

## 未运行的外部步骤

Google Flow 登录后的实际图片生成/下载、Jianying Headless 第三方 Python/原生核心、剪映 UI 验收、真实用户成片审听和 GitHub 远端 CI 未由本地测试代替。Google Flow 的完全复刻和原生 2K 不作确定性保证。便携后端输出 JSON 工程，不声称剪映原生草稿。详细执行和许可边界见 [合同](../ai-comic-drama-workflow/references/flow-and-editing.md)。
