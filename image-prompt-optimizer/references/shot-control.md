# 镜头控制资产 0.1

复杂走位、联合运镜、接触或跨镜连续性任务读取本文件；简单提示词沿用轻量入口。源码在视频编译器 `scripts/shot_control/`，`sync_shot_control.py` 同步图片包所需副本，禁止分别手工修改。AVIR 1.2 继续唯一持有运动、表演和构图，派生包不增加另一套轨迹权威。

## 可执行入口

视频编译器中运行（安装原有 `requirements.txt`；媒体探测另需系统 ffprobe）：

```bash
python scripts/vpc.py control build examples/v52/cafe.avir.json --config examples/control/cafe-control.json --out outputs/control-v001
python scripts/control_cli.py verify outputs/control-v001
python scripts/control_cli.py segment examples/v52/cafe.avir.json --target agnes-video-2.5 --out outputs/event-segments.json
python scripts/control_cli.py probe /absolute/path/to/actual-media.mp4
python scripts/control_cli.py lower outputs/control-v001 --target agnes-video-2.5 --mode reference --artifacts /absolute/path/to/control-artifacts.json --out outputs/lowering.json
```

`review/index.html` 为离线三视图和时间轴；`review/blocking-*.svg` 为带标记审阅图。颜色仅编码对象。当前预览绘制根节点轨迹，不能当作人体行走、骨架、遮挡求解或碰撞证明。世界地面为 X–Z，摄影机位置、朝向、变焦、焦点分别读取；未支持的变焦单位导致投影未知。剪辑点按镜头分别求值，不把后镜头机位借给前镜头终点。固定摄影机可使用明确 locked 操作和源镜头观察点，动态机位必须有可求值轨道。没有镜头内参时保留 UNDETERMINED；配置中的 `authored_proxy` 仅为明确设计代理，`calibrated` 必须附校准来源，二者都不是模型原生参数。

事件分段在动作、表演、构图与机位阶段边界及明确姿态中寻找合法切点，同时遵守目标最小/最大/离散时长。没有合法分割保持 BLOCKED，不改变既有 `segment-delivery` 或重排对白。控制视频跨段还需明确帧率与时间映射，不能把该提案当成素材已裁剪。

## 图片关键帧与编辑交接

`keyframe-requests.json` 按事件生成请求，保存来源内容摘要、原始指针、镜头状态、主体姿态及可见性与绑定。每条符合 `keyframe-request.schema.json`。Agent 从现有资产登记中补齐真实 `master_anchors`（身份、造型和场景分责），选择 generate/edit，然后在图片优化器独立包运行：

```bash
python scripts/control_cli.py keyframe-check request.json
python scripts/control_cli.py edit-check edit-delta.json
```

图片独立包只使用 keyframe-check、edit-check、probe、review；build/segment 由持有 AVIR 运行时的视频编译器执行。`edit-delta/0.1` 用属性路径区分允许变化和保持项，检测父子路径冲突。不要把普通身份图同时当作衣服、动作、风格权威。每帧依附主身份与场景锚点，相邻帧只作辅助，避免无限串行编辑漂移。

优化器交付请求和提示词；宿主依用户已有授权生成/编辑，实际查看后登记文件和哈希、审核人、具体检查项与 PASS/FAIL。`control-artifacts/0.1` 还需绑定 source_sha256；上游变动必须重新审核适用性。静态校验不会自己填写生成或审图成功。审阅 SVG 禁止放入首尾帧或主体参考；干净帧还需实际检查箭头、标签、时间码污染。未知姿态回分镜补齐，不插值手势和接触。

## 表演、色彩与所有权

复用 `timeline.performances` 中触发、可见反应、身体/头部/视线、起止、反馈与收束。依据 composition 的可见部位及可读尺度验收；背面和远景不能以微表情作为通过条件。缺必要景别返回导演/分镜，编译器不新增特写。FACS 或强度曲线仅为内部设计，不能新增未经证实的 API 字段。

美术保持三种职责：`material_palette` 为物体固有色，`lighting_plan` 为光源方向和受光，`grading_plan` 为后期调色。这些是设计分类，不向 AVIR 1.2 注入未知字段。将现有美术来源/资产职责绑定到控制项 `source_pointers`，缺上游证据则返回 production-design；色彩参考不能覆盖身份/服装。后期配方需声明输入编码、工作空间和输出变换；肤色、衣服、背景分区观察。必须精确的标志、字幕、品牌色走确定性后期，不承诺生成像素精确。

## 入口和执行覆盖

能力键为厂商、精确型号、界面、端点、模式、版本。新增 registry 将 documented、probe_passed、quality_validated 分开。目前只实现 Agnes 国际 API 的媒体字段静态降译，依据 [2.5 文档](https://www.agnes-ai.com/zh-Hans/docs/agnes-video-25) 和 [Flash 文档](https://www.agnes-ai.com/zh-Hans/docs/agnes-video-25-flash)，核验日 2026-09-24。没有账户探测或质量实测。参考视频仅是条件参考，不是专用三维轨迹通道；Flash 白模视频路线阻断。首尾帧与参考数组互斥，附件不能超入口预算。

每个 control 绑定原硬要求、源指针、所选通道、真实资产和 fallback。缺文件、摘要变化、未审图、过期来源、审阅图、槽位冲突、媒体限制、未解析上传绑定均阻断；`report_loss` 不自动批准降级。`media_fields_draft` 只有媒体字段，必须与独立验证的正文和参数合并，由宿主核查 URL 可达性。未选路线的硬要求保持未覆盖，不把“表达在 prompt 中”记成实际控制。

证据链按计划→真实文件→检查→宿主绑定→提交回执→实收媒体→实际观察推进。当前脚本实现计划派生和绑定草案，始终 `submitted=false`、`runnable=false`、`video_qa=NOT_RUN`；不伪造后三阶段，`COMPILED` 原义不变。执行器网络提交仍属于外部集成。

## 观察与局部返修

宿主记录实际视频哈希、观察者、原始归一化二维点、可见性及事件时间，使用 `control-media-review/0.1`：

```bash
python scripts/control_cli.py review observations.json --media actual.mp4 --out evaluation.json
```

误差按像素距离除画面对角线，丢失、遮挡和跟踪失败仍计入覆盖率分母；时间点必须精确匹配，不自动时间拉伸。分别记录事件提前/延后、身份、造型、接触、表情、色彩和叠字问题。FAIL 生成带时段、源指针及责任模块的返修项。该工具整理人工或外部跟踪器观察，未集成 CoTracker，也不自动判断整片通过或推断厘米误差。

## 阶段边界

已实现：派生合同、三视图/时间轴、事件关键帧请求、编辑冲突检查、事件切点提案、媒体元数据探测、两种 Agnes 模式静态绑定、二维观察与返修、独立包携带资源。

待外部生产条件：真实身份/场景锚点的生成和审图、包含明确几何/骨架的白模渲染器、实际模型提交与效果对照。当前根节点预览不是白模 MP4。VACE/SymphoMotion 专用编码、权重及运行器保持 NOT_INTEGRATED；Seedance 2.5 实际入口保持 ENTRY_UNRESOLVED，不能继承其他型号能力。没有已生成媒体，不得宣称画质、轨迹或情绪控制提升。后续实验保留所有尝试、失败、耗时与费用，先做纯文本/参考/关键帧/白模的小范围对照。
