# Jianying Headless 后期接入合同

当 `production_target=video` 且逐镜与相邻镜头验收完成后，assembly 默认优先尝试 Jianying Headless。核心实现来自 `jinbaozi/jianying-headless` 的 `skills/yichen-jianying-edit`，不复制其源码到本仓库。

## 运行顺序

1. 检查或安装完整 Skill；独立安装时配置本机 `JIANYING_HEADLESS_ROOT`。
2. 运行 `headless_draft.py doctor`。版本、组件身份、固定哈希或本机剪映不匹配即 BLOCKED，不放宽校验。
3. 由已接受的 SelectedTake、连续性决定、后期义务和冻结音频生成剪辑 plan；不得重新解释上游剧情或偷偷替换 Take。
4. `build` 创建隔离的可编辑草稿，`verify-build` 校验结构。
5. 成片目标要求真实 MP4 时，使用已验证冻结快照执行 `export`，并对 `render.mp4` 做 ffprobe、完整解码、时长/帧率/音轨与关键画面检查。
6. 有 UI 条件时继续打开、播放、保存、退出、冷重开回读；缺 UI 条件不能冒充已完成原生持久化验收。

## 回退原则

Jianying Headless 不可用时，不静默换成简易拼接并宣称成片完成。可以保留现有 assembly 能力作为显式 fallback 候选，但必须记录后端和能力差异；用户要求剪映交付时缺少剪映后端属于 BLOCKED。

## 自动推进

剪辑方案、切点、字幕、基础音量和必要转场由 Agent 根据冻结剧本、导演/分镜意图和已接受 Take 自主定稿。只有安装/版本/权限/付费资源、素材缺失或无法自动修复的质量问题才通知用户。
