# 1a3eb6c 功能正确性与交付验收审查

## 版本和两个结论

- 仓库：jinbaozi/ai-video-preproduction。
- 本次固定提交：`1a3eb6c510a7f387369b0c1e183b830e35e3c7c3`。
- 父提交：`7065b47b6984364aafe179019430e73e8bb150fd`。
- 提交标题：Render frozen event keyframes and record actual composition failures。
- 提交信息由 GitHub 连接器直接查询；不是从作者变更说明推定。此前 886e931 的未完成审查没有通过结论。

**补丁功能审查：Request changes。** 本轮复现三个可行动问题：损坏 PNG 的技术漏检；图片宿主参考与视频模型附件混在同一消费集合；事件采样时刻与参考适用时段共用字段造成交接阻塞。前两个列 P1，第三个列 P2。严重度表示功能修复优先级，不是安全漏洞评级。

**整体方案：尚未完整交付。** 代码中已有宿主交接、联合编译、返修、几何预演及 craft 等模块；本轮不能把它们统称为未实现，也不能凭模块存在或作者本地日志认可完整生产闭环。满足构图的干净关键帧、真实视频入口/回执/实收观察、控制收益及专用后端实验仍需证据。

## 实际执行范围

在容器中建立目标文件的测试依赖子集，32 个文件的 Git blob SHA-1 与精确提交对应的 GitHub 文件/树记录一致，见 `evidence/source-integrity.json`。包含原版 AVIR 1.1/1.2 Schema、时间轴/空间运行时和本轮控制模块。没有修改目标实现、放宽验证器或替换 ffprobe。不是完整仓库检出，也不是七个发行归档的安装。

基线是审查者编写的完整原生 AVIR 1.2：两个成年角色、两个镜头、8 秒，明确来源文件摘要、实体、场景、动作变化、状态样本、位置轨、构图、机位和合同。它经目标原版 `build` 和 `verify_package` 进入测试。基线产生 82 个预览状态、7 个关键帧请求、160 个评价样本。每个宿主用例还使用真实本地 PNG、原生身份/场景绑定以及源配方，先确认合法前置，再改变待测因素。

三个脚本合计 **43 项功能断言：37 项达到预期，6 项未达到预期，归并为三个问题**。不能将其称为全绿。逐项结果见 `evidence/summary.json`，原始日志为 `host-run.log`、`additional-run.log`、`edge-run.log`。`collect_results.py` 在此快照返回退出码 1。

浏览器另外执行两个视口：1440 与 390 像素，使用实际 Chromium，检查时间轴输入、播放、脚本异常、页面横向溢出、9:16 SVG 比例、标签边界和完整图例。截图已查看；本夹具未出现标签被画框裁切，图例保留三个完整 ID。这不是复杂群像或所有布局的验收。

所有图片与 host/review/binding 声明均为**合成软件测试夹具**。测试中的 PASS 不代表模型图片质量通过；HTTPS 地址不是实际上传。没有执行图片/视频模型，也没有查看作者保存在本地的实验原图。

## 已通过的关键路径

| 范围 | 本轮观察 |
|---|---|
| 编辑输入顺序 | 基图 K 在前，之后 IDA、IDB、SCN；返回哈希序列重排被拒绝 |
| 冻结绑定 | 错 stage、prompt、output 哈希被拒绝；失败接收没有留下输出半包 |
| 审核全集 | 缺项、逆序和重复项被拒绝；包括编辑差量新增验收项 |
| 状态分离 | PASS/FAIL/UNDETERMINED 按定义传播；未审结果为 NOT_RUN；UNDETERMINED 不生成 PASS 资产审核 |
| 画幅 | 完整 PASS 声明不能覆盖明确的宽高比错误 |
| 编辑基图 | 审核 FAIL 的独立 clean_keyframe 可作编辑基图；FAIL 主锚点、无差量、过期基图被阻断 |
| FOV 修订 | 原请求与新冻结状态不一致被拒绝；主身份参考可复用；旧关键帧配方失效 |
| 事件预检 | S1 的 2000 ms 事件只派生一个样本；错镜头请求被拒绝；1000.5 ms 保真 |
| 独立源码依赖 | 无兄弟视频目录的图片侧子集运行 stage/receive/verify；联合编译返回明确的视频包依赖错误 |
| 降译对照 | 不含宿主主锚点控制的合法独立首帧包可 BOUND_DRAFT；FAIL/未审资产被阻断 |

## F01 / P1：损坏 PNG 可保留 PASS，部分还能进入 BOUND_DRAFT

### 精确位置

所有路径均在上述 SHA：

- `video-prompt-compiler/scripts/shot_control/media_probe.py:13–25`。
- `video-prompt-compiler/scripts/shot_control/keyframe_host.py:137–147,159–165`。
- `video-prompt-compiler/scripts/shot_control/control_lowering.py:99–104`。

### 有效前置与最小复现

`probe_additional.py` 调用 `prepare()`，先完成完整原生 `build → verify → keyframe-check → stage → verify-stage`。仅替换宿主返回的实际图片为坏 PNG，并同步**实际文件哈希**；提供绑定当前阶段和全部验收项的合成 PASS 审核声明。

`make_badpng.py` 创建三类本地文件：没有 IDAT、无效 zlib IDAT、解压后栅格数据不足。PNG 头和相应 chunk CRC 按格式构造；这不是把无效 AVIR 送给验证器。

### 实际结果

| 探针 | ffprobe 尺寸 | receive/verify_received | 独立像素解码 |
|---|---|---|---|
| N03_nondecodable_no_idat | 0×0 | visual_review=PASS，technical_issues=[] | 失败 |
| N03_nondecodable_bad_idat | 512×288 | 同上 | broken data stream |
| N03_nondecodable_zeros_idat | 512×288 | 同上 | image file is truncated |

额外的 `N03_lower_nondecodable` 从另一个原生有效首帧包进入，使用坏 IDAT PNG、匹配哈希/配方/合成审核和绑定：返回 `BOUND_DRAFT`，reasons 为空。此前同一路径的有效 PNG 是正例，FAIL/未审状态是已阻断对照。

### 原因与预期

元数据探测不等于完整像素解码。当前只看 ffprobe 返回码、类型和元数据，既没有要求正尺寸，也没有确认栅格可解码。0×0 还满足零值宽高比关系。

接收器可以保存失败原件作为证据，但不得把坏文件标记成技术可用图片，更不能让合成/人工 PASS 声明覆盖可确定的解码失败。

### 修复和验收门

在共享媒体验证层执行：有限大小/像素预算；width/height > 0；严格的完整图片解码。选择 Pillow 时要区分结构 verify 与重新打开后的 load；选择 ffmpeg 时须明确解码失败的处理。保留元数据探测与解码证据为不同结果。

回归门：三种坏 PNG 都被拒绝或登记为明确技术 FAIL，lower 不得返回可绑定草案；有效 PNG 仍通过；原始错误文件可以保存，但不得伪装为模型生成成功或真实视觉质量失败。

## F02 / P1：图片宿主的主锚点被当作视频模型附件，首尾帧交接阻塞

### 精确位置

- `video-prompt-compiler/scripts/shot_control/keyframes.py:58–72`：主锚点须有冻结控制责任。
- `video-prompt-compiler/scripts/shot_control/control_lowering.py:34–51`：将当前镜头的所有控制都投入目标视频模式。
- `video-prompt-compiler/scripts/shot_control/joint_compile.py:48–64`：对当前镜头全部原生绑定要求进入提交附件索引（此处仅源码核查，未运行完整联合编译）。

### 有效前置与最小复现

`N01_same_package_keyframe`：完整原生包的 S1 使用 IDA/IDB/SCN 三个 image_reference 主锚点制作图片；输出 K 声明为 first_frame。这组配置通过原生 build、verify、keyframe-check、stage。接收真实合成 512×288 PNG，完整合成审核为 PASS。

随后为实收清单中的真实文件添加明确标为 synthetic 的 HTTPS 绑定，调用：

```python
lower(package, 'agnes-video-2.5', 'keyframe', manifest,
      {'start_ms': 0, 'end_ms': 4000})
```

### 实际与预期

实际 BLOCKED，原因包括 `C_IDA/C_IDB/C_SCN:UNSUPPORTED_CHANNEL`、图片和总数预算。制作 K 的三张主参考被作为视频首尾帧模式的直接输入。

改成 reference 模式会正确拒绝 K 的 first_frame 控制；该行为单列保护性正例 `R05_reference_rejects_first_frame`，不是要求模型接受非法混用。独立仅 K 的首帧包已通过正例。

预期是同一权威 AVIR 下，宿主制作参考与视频执行附件可以分责：首尾帧请求传实际 K，而其主锚点保留为 K 的来源证据，不被强行上传或占用视频槽位。

### 修复和验收门

在派生任务/控制用途层标明消费者，例如 image_host 与 video_model；lower 按执行任务选取控制。联合原生附件映射同步采用这份消费范围，不能一边排除 host-only 参考，一边又报 UNMAPPED_SOURCE_ASSET。

不需要另造轨迹 IR，也不能静默丢弃真正要求直接上传的参考义务。

回归门：单一原生源完成主锚点→stage→receive→视频 keyframe 输入生成，不删除原生来源、不人工改已经冻结的中间包。首尾帧与参考模式非法混用继续阻断，附件数量按实际提交子集计算。

## F03 / P2：事件捕获时间与参考适用范围共用字段，接收出的参考不可消费

### 精确位置

- `video-prompt-compiler/scripts/shot_control/keyframe_host.py:30–40`。
- `video-prompt-compiler/scripts/shot_control/previs_frame.py:11–18,21–26`：复用同一 `_uses`（只执行了事件计划预检，没有实际 Blender 渲染）。
- `video-prompt-compiler/scripts/shot_control/control_lowering.py:66–82`。

### 有效前置与最小复现

`N02_point_reference_scope`：从完整原生基线出发，三个主锚点和输出 K 的通道**全部是 image_reference**，排除了 F02 的模式混用因素。K 为 S1 的冻结 0 ms 事件图。经 build/verify/stage/receive，图片为 512×288、合成审核 PASS。

`_uses` 无论目标是首尾帧还是普通参考，都把 K 记为 start_ms=end_ms=0。

### 实际与预期

调用 `lower(reference, scope=0–4000)` 返回 `C_K:NO_VALID_ASSET_FOR_SCOPE`。lower 要求 image_reference 的用途区间覆盖整个请求，点用途不能覆盖非零时长区间。

预期是区分“该图表现哪个瞬间”与“允许在哪个请求中起什么参考作用”。不能为通过检查就把采样时刻改成整段动作，也不能无提示地产生后续必然无法消费的声明。

### 修复和验收门

分别保存 source_event/capture_time 与 execution_applicability；机位/姿态配方继续按真实事件求值，适用范围及允许继承维度进入用途审核。另一种可接受方案是提前标为待补用途，并提供可验证的提升/绑定入口。

回归门：事件图作为普通参考进入合法 reference 请求；原始时刻和镜头归属不变；错镜头/错切点、未授权扩展参考范围仍被拒绝；previs-frame 与 host receive 使用一致的语义。

## 分发和未运行范围

GitHub 中图片侧 shot_control 目录树与视频侧相同，control_cli、detail_runtime、spatial_runtime 和本轮必需 Schema 的内容摘要一致。隔离测试只复制这些已核对的源码依赖，不包含兄弟视频目录或 vpc_core；在子进程中执行图片侧 CLI 的 stage 验证、receive 和 received 验证成功。compile 按设计报告需要 video-prompt-compiler。

这不等于七个 .skill 归档安装测试。以下均没有独立完成：作者所称 165 项全仓回归、两个实际 Blender 集成、七包内置一致性/重复构建、完整 joint compile、真实图片/视频模型和作者原图检查。当前容器未找到 Blender 或 bpy；previs-frame 尝试停在 executable unavailable，记 NOT_RUN，不能计作渲染成功或产品渲染失败。

## 作者实验与完整交付

已读取当前 SHA 的 `validation-artifacts/host-keyframe-clay-evidence.json`。记录是 FAIL，并注明原图不在仓库、是手工估计而非自动跟踪：冻结中心约 (0.378362,0.716245)，记录的观察约 (0.433014,0.577046)，每轴阈值0.02。本轮未看到该原图，也未重测这个坐标。

完整交付尚需：符合构图要求且可通过技术/视觉审核的干净关键帧；真实视频模型入口、请求回执与实收视频观察；表演/光色控制的收益验证；VACE 或 SymphoMotion 之一的独立实验。代码实现、合成测试、当地渲染与视频模型效果是不同证据，不能互相替代。

## 来源定位

所有源码定位使用前述固定 SHA，GitHub 路径形式：
`https://github.com/jinbaozi/ai-video-preproduction/blob/1a3eb6c510a7f387369b0c1e183b830e35e3c7c3/<path>#L<line>`。

原始探针数据、命令日志、环境版本、损坏媒体生成脚本和当前源码摘要清单均包含在证据包中。缺陷结论由实际探针支撑；joint_compile 影响范围仅作为源码分析，不计作运行结果。
