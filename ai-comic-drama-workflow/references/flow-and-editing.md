# Flow 参考图与真实剪辑

此合同用于 0.16.0 新 `start`。普通创作选择由当前宿主自动完成，实际看图、逐镜、相邻和整片验收不省略。已有项目、旧 `init` 保持其冻结协议。`step` 返回真实宿主动作，不是后台模型客户端。

## 默认与边界

- 新 lean/full 与 audited/full：图片生成 → Google Flow 参考重制 → 2K 字节与相似性复核 → 下游分镜/视频引用
- 新视频目标：真实 Take → 逐镜/相邻验收 → Jianying Headless 时间线剪辑 → MP4 复探测 → 整片审阅 → VIDEO_DELIVERED
- 新 `start` 默认 `--creative-policy automatic`：普通人物身份定稿、未锁定的创意选择由当前宿主记录依据后继续。`--creative-policy ask` 可显式保留人工定稿
- 自动创作不授权登录、验证码、付费、额外软件执行、敏感数据传输、版权或安全权限，不修改用户锁定事实。真实阻塞须立即说明，不用更低质量结果冒充完成
- `--reference-refinement off` / `--editing-backend ffmpeg` 仅供用户明确选择其他路径，不能为绕过失败自动启用
- audited/V6 仍要求图内独立审阅；新 `start` 冻结配置对应的参考图 2K、故事板 2K 与剪映执行关卡，真实宿主收据、下载字节与剪辑包复验通过后才能继续。已有无扩展图的 25 阶段项目保持原协议，不静默迁移；原 `init` 保持显式配置

## Flow：浏览器宿主执行，返回实际文件

必须使用 Google 官方 Flow 界面与当前实际可用功能。这个仓库没有假造的 Flow API，也不调用内部接口。宿主看到 `AWAITING_FLOW_REFINEMENT` 后按返回合同操作；真实浏览器检查决定当前模型、账号、套餐和下载能力。优先账号可通过 `--flow-account ACCOUNT` 在本地项目指定；公开仓库不内置任何个人账号，不保存密码或令牌。

```sh
ai-comic-drama reference PROJECT plan --media-key MEDIA_KEY
ai-comic-drama reference PROJECT begin --media-key MEDIA_KEY
# 宿主实际上传冻结参考、调用、下载，并对照看图，按 plan 的 receipt_contract 写结果
ai-comic-drama reference PROJECT receive --media-key MEDIA_KEY --result flow-result.json
ai-comic-drama step PROJECT
```

`begin` 必须先于生成调用，持久化本次意图。超时或结果不确定返回 `RECONCILE_ONLY`，只能找回原任务；不得重提。已确认失败及其证据允许在冻结上限内重试；默认最多 2 次。登录、地区/账号资格、额度、功能或工具权限问题记录为真实 `BLOCKED` 并持续保持，直到通过 `reference PROJECT resume --media-key KEY --result resolution.json` 提交真实恢复观察；不会在用户尚未登录时自动消耗下一次尝试。登录只提示用户通过安全渠道完成，不把登录成功预写进收据。

通过条件同时包括：

1. 原图仍有效，源哈希、实际上传引用、调用与下载证据一致
2. 导出的是实际可解码 PNG/JPEG/WebP，长边实测至少 2048 像素，长宽比保持。截图、只有链接、空文件、尺寸声明或把原图直接复制不能过关
3. 记录分辨率来源：原生生成或服务提供的官方放大。官方放大可以满足“实际 2K 参考文件”，但绝不声称原生 2K；未知来源或本地任意插值不被冒充
4. 宿主同时查看原图与结果，对身份、构图/空间、服装、道具、光色、文字逐项记录实际发现，适用项均须通过，不适用项须说明原因。检查绑定两份文件哈希，不能复用其他图片的 PASS
5. 任何主体、服装、空间或关键文字漂移均修复或阻断。生成模型不能保证数学意义上的完全复刻；通过是有证据的任务符合性，不是零误差承诺

合格结果会提升为原生 media 的当前文件，保留原图和调用链。后续图片绑定、AVIR 资产、附件索引和执行收据均引用这份实际 Flow 输出及哈希。直接 `compile` 和最终校验也会重复检查，不可跳过此阶段。修改原图、导出图、收据或已绑定父参考会使验收失效。

## Jianying Headless：独立核心、可执行剪辑

核心：[jinbaozi/jianying-headless](https://github.com/jinbaozi/jianying-headless)，固定审阅 commit 为 `42b3d75b15bd9f3a9bb4c11b2f5205f7b4312252`。本套装不重新分发第三方核心。使用完整工作流目录，以及单独的核心 checkout。安装/运行前由宿主取得相应权限；不因自动创作策略隐式执行未知来源软件。

核心目前的[许可证](https://github.com/jinbaozi/jianying-headless/blob/42b3d75b15bd9f3a9bb4c11b2f5205f7b4312252/LICENSE)限制个人非商业用途；商业执行须有版权方书面许可。用户自己的项目用途不能由宿主猜测，未知或不匹配的许可不继续。

```sh
ai-comic-drama production PROJECT editing-readiness \
  --core-root /absolute/path/jianying-headless --backend portable-ffmpeg
ai-comic-drama production PROJECT edit \
  --edl edl.json --spec frozen-spec.json --out PROJECT/11-edit/final.mp4 \
  --core-root /absolute/path/jianying-headless --backend portable-ffmpeg \
  --authorization execution-approval.json --usage personal-noncommercial
```

需要获取核心时，先取得 install-jianying-headless 的实际授权，再使用 `production PROJECT editing-install --destination /absolute/path/jianying-headless --authorization install-approval.json`。该命令只从官方指定仓库取回固定 commit 并验证文件，不安装依赖、不执行核心；执行是另一个授权动作。

授权 JSON 的具体字段由 `jianying.py` 定义，须是实际宿主取得的当前操作授权，绑定核心 commit、后端和用途，不能从测试样板复制一份假授权。准备检查只读；实际执行会验证固定 commit 的所有跟踪文件与许可证，阻止本地改动或未审阅升级。

- `native`：Apple Silicon macOS、匹配剪映环境、核心 doctor 通过；交付真实离线原生草稿和导出。原生草稿未注册/未 UI 验收的状态须如实保留
- `portable-ffmpeg`：调用核心真实 `windows-ffmpeg` 入口，可在满足依赖的平台运行；交付核心生成的可编辑 JSON 时间线、所需素材与 MP4。不是剪映原生 draft，不得以文件扩展名伪装

剪辑把经过选择和验收的 Take 按 EDL 的源入点/出点、记录位置放上时间线，保留冻结音频策略，并加入明确的后期音轨。禁止自动变速、裁切、改变尺寸/帧率、丢弃原生声音或私自换 Take。暂不支持的剪辑效果须显式阻断；不将文字说明算作已执行效果。

返回 CHECKED 必须有真实 MP4、逐帧计数、尺寸/帧率/时长/音轨复探测、源哈希和输出哈希。时间线、计划和执行收据一并快照进项目；缺失或被修改会阻断 VIDEO_DELIVERED。整片语义与听审仍由宿主执行并绑定当前输出，静态测试不能代替真实成片质量验证。

## 验证

`test_flow_references.py` 使用本地真实解码测试像素/篡改/重试/来源门；不声称已经登录或调用 Google。`test_jianying_adapter.py` 验证核心计划、授权、许可与输出验收，并模拟第三方执行边界；没有实际核心许可/环境时不声称已跑真实核心。`test_flow_editing_pipeline.py` 检查默认配置、旧项目兼容、自动创意范围和不可绕过的门。执行全量回归和打包检查，参见仓库 README。
