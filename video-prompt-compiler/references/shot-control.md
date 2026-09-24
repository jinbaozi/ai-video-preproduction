# 镜头控制资产 0.2

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

`keyframe-requests.json` 按事件生成请求，保存来源内容摘要、原始指针、镜头状态、主体姿态及可见性与绑定。每条符合 `keyframe-request.schema.json`。Agent 从现有资产登记中补齐真实 `master_anchors`（身份、造型和场景分责），主身份与场景锚点必须对应冻结 AVIR 中已 observed 的真实 assets/bindings，ID、文件摘要、文件名和职责一致；身份覆盖当前构图中可见人物，场景对应本镜 scene_id。不能用只有 style 的任意文件充当全部主锚点。选择 generate/edit，然后在图片优化器独立包运行：

```bash
python scripts/control_cli.py keyframe-check request.json --package outputs/control-v001 --artifacts /absolute/path/to/control-artifacts.json
python scripts/control_cli.py edit-check edit-delta.json
```

图片独立包携带同源原生 AVIR 校验运行时，可验证冻结控制包；制作中的 AVIR 编写、build/segment 仍由视频编译器负责。`edit-delta/0.1` 用属性路径区分允许变化和保持项，检测父子路径冲突。不要把普通身份图同时当作衣服、动作、风格权威。每帧依附主身份与场景锚点，相邻帧只作辅助，避免无限串行编辑漂移。

优化器交付请求和提示词；宿主依用户已有授权生成/编辑，实际查看后登记文件和哈希、审核人、具体检查项与 PASS/FAIL。`control-artifacts/0.2` 保存来源版本 `source_sha256`，另用 `uses` 绑定控制 ID、镜头、起止和派生配方 `recipe_sha256`。审核还须绑定 `uses_sha256`。镜头素材依赖源断言、镜头时轨、场景和相机配置；身份/外观/风格/场景母版只依赖对应断言切片，不因无关轨迹修改而全部失效。静态校验不会自己填写生成或审图成功。审阅 SVG 禁止放入首尾帧或主体参考；干净帧还需实际检查箭头、标签、时间码污染。未知姿态回分镜补齐，不插值手势和接触。

### 宿主输入冻结与实收登记

```bash
python scripts/control_cli.py keyframe-stage request.json --package outputs/control-v001 --artifacts masters.json --prompt prompt.txt --artifact K001_0 --out outputs/keyframe-stage
python scripts/control_cli.py verify-keyframe-stage outputs/keyframe-stage
# 外部宿主实际生成后，Agent 按真实调用记录整理 host-result.json，再接收实物：
python scripts/control_cli.py keyframe-receive outputs/keyframe-stage --media actual.png --host-result host-result.json --out outputs/keyframe-received
python scripts/control_cli.py verify-keyframe-received outputs/keyframe-received
```

`keyframe-stage` 验证请求，冻结控制包、提示词原文、主锚点及编辑基图的真实文件。`stage.json.inputs` 是宿主应使用的顺序：编辑基图首先，其后按 master_anchors 顺序去重。输出 ID 必须已在冻结配置中声明，不能替换主锚点。输入副本保留真实文件名，路径用输入序号隔离重名。此操作仅准备输入，不调用模型、不上传文件。

`host-result.json` 遵守 `keyframe-host-result/0.1`：绑定 stage-manifest 文件摘要、提示词文件摘要、实际有序输入摘要、实收文件名与摘要；记录真实 host/model/execution_id/evidence，宿主未暴露型号或执行 ID 时填 null。`recording_mode` 区分 contemporaneous、retrospective 与 synthetic_test。历史实验只能作为 retrospective 回放，不能声称在原调用前已冻结这份新交接包。这是宿主记录的本地一致性检查，不是厂商签名或独立执行证明；不把自填记录当作探测通过。

实收包包含独立 stage 副本、原始输出、host-result、实际 ffprobe 信息与 control-artifacts 清单。默认 `review=null`、输出 `binding=null`；已生成的图片也不能自动算审核通过。登记保留整套输入与每次失败尝试，不覆盖旧包；复制到新位置仍可验证，原始输入随后变化不会篡改已冻结副本。该清单含本次选用的锚点、基图和产物；其他镜头资产仍需由工作流按 ID/摘要显式合并，不隐式丢弃或宣称全片可编译。

实际看图后，可在新的接收目录执行同一命令并添加 `--review visual-review.json`。该文件遵守 `keyframe-image-review/0.1`，绑定图片及 stage 摘要，按顺序逐项覆盖 request.acceptance 和 edit_delta.acceptance 去重后的全集，每项记录 PASS/FAIL/UNDETERMINED 与具体观察依据。任一失败使本图 FAIL，未确定项保留无审核通过状态；不能只填写局部编辑成功。可确定的画幅冲突或非方形像素也会阻止 PASS；实收尺寸保留，不静默缩放。静态检查不自行判读脸、姿态或投影。

`verify-keyframe-received` 重算实收清单和审核摘要，拒绝篡改后重新封装的派生清单。即使输出与旧基图共用逻辑 ID，旧基图仍保存在 stage 中；旧用途失效记录保留并按文件摘要区分。后续修复继续走 keyframe-check/stage；视频上传绑定仍由外部宿主记录，不能改写本次接收包来伪造上传成功。

## 表演、色彩与所有权

复用 `timeline.performances` 中触发、可见反应、身体/头部/视线、起止、反馈与收束。依据 composition 的可见部位及可读尺度验收；背面和远景不能以微表情作为通过条件。缺必要景别返回导演/分镜，编译器不新增特写。FACS 或强度曲线仅为内部设计，不能新增未经证实的 API 字段。

美术保持三种职责：`material_palette` 为物体固有色，`lighting_plan` 为光源方向和受光，`grading_plan` 为后期调色。这些是设计分类，不向 AVIR 1.2 注入未知字段。将现有美术来源/资产职责绑定到控制项 `source_pointers`，缺上游证据则返回 production-design；色彩参考不能覆盖身份/服装。后期配方需声明输入编码、工作空间和输出变换；肤色、衣服、背景分区观察。必须精确的标志、字幕、品牌色走确定性后期，不承诺生成像素精确。

## 入口和执行覆盖

能力键为厂商、精确型号、界面、端点、模式、版本。新增 registry 将 documented、probe_passed、quality_validated 分开。目前只实现 Agnes 国际 API 的媒体字段静态降译，依据 [2.5 文档](https://www.agnes-ai.com/zh-Hans/docs/agnes-video-25) 和 [Flash 文档](https://www.agnes-ai.com/zh-Hans/docs/agnes-video-25-flash)，核验日 2026-09-24。没有账户探测或质量实测。参考视频仅是条件参考，不是专用三维轨迹通道；Flash 白模视频路线阻断。首尾帧与参考数组互斥，附件不能超入口预算。

每个 control 绑定原硬要求、原断言指针、所选通道、真实资产和 fallback，`purpose` 必须为 `supplement`。媒体仅辅助 prompt 类型要求；不能冒领 parameter 或 post 要求。shot_ids 必须落在原合同适用镜头内，hardness 不得降级。缺文件、摘要变化、未审图、过期来源、审阅图、槽位冲突、媒体限制、未解析上传绑定均阻断；`report_loss` 不自动批准降级。`media_fields_draft` 只有辅助媒体字段；使用 control compile 统一编译正文、参数、附件与职责，由宿主核查 URL 可达性。`primary_obligations` 将 prompt/native_parameter/post_production 分开保留为 NOT_COMPILED。单独 lower 的 BOUND_DRAFT 仅说明辅助素材静态绑定成立，不是完整合同覆盖。通过下述显式 compile 入口继续编译主执行义务。

证据链按计划→真实文件→检查→宿主绑定→提交回执→实收媒体→实际观察推进。当前脚本实现计划派生和绑定草案，始终 `submitted=false`、`runnable=false`、`video_qa=NOT_RUN`；不伪造后三阶段，`COMPILED` 原义不变。执行器网络提交仍属于外部集成。

## 观察与局部返修

构建时从 AVIR 和相机配置冻结 `evaluation-plan.json`。宿主只填写其规范化摘要 `evaluation_plan_sha256`、实际视频哈希、观察者、实测归一化二维点、可见性及事件时间；不能提供 planned_points、width/height 或 planned_ms。使用 `control-media-review/0.2`：

```bash
python scripts/control_cli.py review observations.json --package outputs/control-v001 --media actual.mp4 --out evaluation.json
```

误差按 ffprobe 的实际显示画幅计算像素距离并除以对角线；缺失、遮挡、跟踪失败和源投影未知仍保留在完整采样分母中。检查真实视频类型、时长、旋转、画幅及观察时段；暂不接受非方形像素。计划时轴为恒等映射，不能隐式拉伸。切点终点不冒充该镜头可解码帧。事件漏测保留 null。分别记录事件提前/延后、身份、造型、接触、表情、色彩和叠字问题。FAIL 生成带时段、源指针及责任模块的返修项。该工具整理人工或外部跟踪器观察，未集成 CoTracker，也不自动判断整片通过或推断厘米误差。

## 阶段边界

已实现：派生合同、三视图/时间轴、事件关键帧请求、编辑冲突检查、事件切点提案、媒体元数据探测、Agnes 三模式联合编译及静态绑定、二维观察、依赖失效与返修文件、独立包携带资源。

待外部生产条件：真实身份/场景锚点的生成和审图、足够表达动作的几何和关键姿态、实际模型提交与效果对照。下述 Blender 入口可生成本地几何白模；根节点三视图本身仍不是白模 MP4。VACE/SymphoMotion 专用编码、权重及运行器保持 NOT_INTEGRATED；Seedance 2.5 实际入口保持 ENTRY_UNRESOLVED，不能继承其他型号能力。没有实际模型输出，不得宣称画质、轨迹或情绪控制提升。后续实验保留所有尝试、失败、耗时与费用，先做纯文本/参考/关键帧/白模的小范围对照。

## 0.2 升级与校验边界

0.1 控制包不能直接冒充 0.2：保留原始 AVIR 和配置，补充 control.purpose 后重新 build；旧观察表需重新绑定冻结基线。AVIR 本身不升级。包内文件冻结后不要手改；真实资产清单放在包外，通过 --artifacts 显式传入。

verify/lower/keyframe-check/review 共用严格验证器：核对 schema、完整文件集合、摘要、原生 AVIR、控制 ID/镜头/断言、派生计划、关键帧与评价采样。仅给修改后的文件重算摘要不能让不一致的派生数据通过。该机制检测陈旧或错误的交接，不是数字签名或对恶意作者的身份鉴定。

切点的关键帧状态按请求所属镜头取空间关系：S1 尾帧保留 S1 的结束关系，不能混入同一时刻 S2 的开始关系；镜头内部仍按半开区间求值。修复前导出的包应从原始 AVIR/config 重新 build，不重封旧派生文件摘要。

编辑修复允许使用已有 FAIL 审图的 clean_keyframe 作为 base_asset_id，前提是它不兼任 master_anchor，实际文件/用途/配方/审核摘要仍有效，且提供匹配基图与目标请求的 edit_delta 和验收条件。缺审核或失效用途仍阻断；身份/场景母版必须 PASS。允许修复不等于图片通过审图，lower/compile 仍拒绝失败素材。宿主保留每次实际调用提示词、输入顺序与文件摘要、实收文件和审图结果；不得用一次局部修复通过冒领整帧或成片验收。

第二轮审核后的输入规则：原生 reference 合同保留独立 visual_reference 义务，lower 仍为 NOT_COMPILED；联合编译对指向 assets/bindings 的断言映射同一附件索引，未知的参考断言返回 BLOCKED。媒体职责必须符合消费通道：首尾帧为 clean_keyframe 图片，视频参考为 clay/performance 视频，音频参考为 audio，静态参考通道仅接收图片。时序通道不能因 identity/style 标签跳过机位或动作依赖。素材 HTTPS URL 禁止 fragment，query 原样保留。

仅用于图片宿主的身份、场景母版或编辑基图，显式声明 `channel: keyframe_input`。它仍须经过原生来源职责、镜头时段、实际文件、当前用途审核、配方与失效检查；可进入 keyframe-check/stage，但 lower/compile 不把它放进视频附件、配额或首尾帧槽位。`image_reference` 继续表示需要提交给视频模型的参考图，旧配置不自动改写；同一素材若兼有两种用途，分别声明两个控制项。宿主用途不抵销任何原生正文、参数、reference 或后期义务。

收到的 `clean_keyframe` 保留 `start_ms == end_ms == at_ms`。如需作普通参考，控制项必须事前声明 `reference_scopes: {"S2": {"start_ms": 4000, "end_ms": 8000}}`，由原 `source_pointers` 限定允许参考的职责；范围须在对应镜头内并包含采样时刻。stage/previs-frame 在缺范围时先阻断，避免生成必然无法消费的输出。接收器把该范围写入用途的 `reference_scope`，并纳入冻结阶段、配方与用途审核摘要。lower 要求实际请求落在已授权范围内，不能手动扩张范围或修改事件时刻绕过检查；这不是整段姿态保证。首尾帧仍精确匹配执行范围端点，视频和音频仍要求完整区间覆盖。

联合编译与 lower 使用相同消费分类：仅声明 `keyframe_input` 的原生母版保留在 `source_bindings` 和制作来源说明中，明确没有作为本请求附件提供；真正声明为视频参考的控制和原生 reference 合同仍需映射实际附件，不能靠宿主分类抵销。所有实际图片除了文件头探测，还必须具有有效尺寸并通过 FFmpeg 严格像素解码，损坏图片不能靠 PASS 审核声明进入接收或降译流程。

冻结包会重派生并核对审阅 HTML/SVG。lens.aspect × crop.width / crop.height 必须等于原生输出画幅；没有 lens 时使用交付画幅展示未知投影。摄影机基退化保持 UNDETERMINED，不放行到关键帧生成。扩展时刻与原生 number 毫秒一致，不隐式舍入；构建先在临时目录完整校验，再原子发布，失败不留下半包。目标视频 API 的时长步进限制仍独立检查。

单时刻 clean_keyframe 的适用性由该时刻求值状态、参与实体、摄影机、场景与光色/几何设计决定；未来动作反馈和无轨道、无状态、未参与构图的实体外观不再使首帧失效。持续视频参考仍保守依赖整镜；当前有位置/状态的画外实体保留依赖，因为尚无完整遮挡与反射求解。图内长名称缩写并在边缘避让，完整标签在 HTML legend 中保留，圆点坐标不变。

附件按内容和槽位去重，attachment_index 同时决定提交数组和 `<Picture N>/<Audio N>/<Video N>`。同一 URL 声明不同内容立即阻断；同一内容可以承担多个职责。原始绑定 URL 与统一提交 URL 分列。音频单个文件仍需正时长和大小限制，总时长单独检查 2–12 秒。

## 显式几何白模

`control-config.proxy_scene` 可选扩展由 `previs-geometry.schema.json` 严格校验。Agent 明确写出每个几何体的设计依据、节点 ID、镜头范围、尺寸、静态世界偏移和姿态来源；不能加入独立的轨迹或关键帧。box/ellipsoid 可绑定数值 node_direction 或明确的 world_axes；bone 两端分别来自两个 AVIR 节点。未提供的关节、朝向、身体姿态和中间位置不推断，逐帧缺值在启动渲染器之前阻断。人物根节点的几何轮廓仅用于走位，不能作为已完成步态、接触或面部表演。

安装 Blender 与 ffmpeg/ffprobe 后，视频包可以构建和实际渲染合成演示：

```bash
python scripts/build_previs_example.py --out outputs/previs-example
python scripts/control_cli.py previs outputs/previs-example/package --shot S1 --blender /absolute/path/to/blender --out outputs/previs-example/render
python scripts/control_cli.py verify-previs outputs/previs-example/render
```

演示显式补充信封关键位置之间的线性代理移动，并保留设计来源；不偷偷改变已有 cafe 示例。输出包括干净 PNG 帧、事件帧索引、clay.mp4、scene.blend、逐帧计划、真实 Blender 读回和实际媒体回执。影片采用 `[start,end)` 的真实帧序列，终点单独保留为事件图；禁止为凑帧数而拉伸时间。分辨率必须匹配镜头和 crop 的输出比例。

渲染器从出厂空场景构建、保存后重新打开场景，使用 Blender 实际摄影机投影、网格中心/尺寸/方向和骨段端点验证转换；再探测最终视频的帧率、尺寸与时长。只使用中性白模 studio lighting，不将其解释为生产照明、材质色或调色。未知 zoom 或有焦点轨的浅景深任务需光学扩展，当前阻断。当前本机验证 Blender 5.2.1；其他版本须运行真实集成测试：`BLENDER_EXECUTABLE=/absolute/path/to/blender python -m unittest discover -s tests -p test_previs.py -v`。

几何按镜头进入临时资产的派生指纹；修改相应几何会使其失效，无关镜头几何和身份母版不会因此全部作废。artifact-manifest 仅为已有单素材 clay 控制项自动登记实物，review/binding 初始均为 null；多素材控制项由宿主显式登记。渲染成功是 RENDERED_LOCAL，验包是 VERIFIED_LOCAL_RENDER，均不等于视觉审核、模型提交或生成服从度通过。Agent 必须看实际帧并按用途审阅，随后由宿主绑定实际可访问素材。

## 表演、固有色、照明与调色

`craft` 从 AVIR 原生 performances、composition_tracks 和 scenes.lighting 派生排练卡、表演请求及独立光源交接；不重新创作触发、微反应、手别、视线或表情时点。整个表演区间按构图变化划分，逐段检查人物所需部位及 body/face/detail 可读程度；缺段或不可读返回 BLOCKED，由导演/分镜修订，不能擅自加特写。`rehearsal.md` 是可供演员/动画宿主执行的交接卡，绝不是已经拍摄的表演视频。

配置 look_design 后，事件关键帧的只读 craft_state 同时携带本镜光色设计、光线原文和本时刻表演全文；调色标为 POST_PRODUCTION_NOT_MODEL_PARAMETER。这些派生内容由统一验证器重算，宿主不能手改关键帧来源。光色变化按镜头影响临时资产和关键帧请求，并进入返修依赖图；未相关镜头和身份母版不因此全量失效。

可选 `control-config.look_design` 属于美术的显式设计补充，遵守 `look-design.schema.json`。material_palette 每项绑定原实体 appearance/locks 和镜头，色样需标明 authored_proxy 与依据；脚本不把“深蓝”等词自动猜成唯一色号。lighting_plan 保留源场景光线全文及逐镜 light/color/material/atmosphere 轨道，不将固有色、光源颜色和最终调色混成一项。色板 SVG 是审阅资产，不能放进首尾帧槽位；最终肤色、服装和背景需要实际分区观察，不能凭全图直方图或色号宣称合格。

```bash
python scripts/control_cli.py build examples/v52/cafe.avir.json --config examples/control/cafe-look.json --out outputs/cafe-look
python scripts/control_cli.py craft outputs/cafe-look --out outputs/cafe-craft
python scripts/control_cli.py verify-craft outputs/cafe-craft
python scripts/control_cli.py grade outputs/cafe-craft --shot S1 --media /absolute/path/to/shot-bt709.mp4 --out outputs/graded-S1
python scripts/control_cli.py verify-grade outputs/graded-S1
```

`grading_plan` 生成 33³ `.cube` LUT，输入解码为 BT.709 非线性 RGB，经 BT.709 OETF 逆变换进入线性 Rec.709，按显式曝光/对比度/饱和度配方处理，再编码回 BT.709；超范围值明确裁到 0–1。这是本地后期变换，不能用于承诺生成模型精确色彩或品牌色，也不等于显示器校准。公式依据 [ITU-R BT.709](https://www.itu.int/rec/R-REC-BT.709-6-201506-I)，执行使用 [FFmpeg lut3d/scale](https://ffmpeg.org/ffmpeg-filters.html#lut3d)。

当前执行只接收实际 ffprobe 标记齐全的 8-bit、limited-range BT.709、方形像素、无旋转的单镜视频，并要求时长与原镜头一致；未知编码/HDR 被拒绝，不通过补标签猜测。显式控制 YUV/RGB 矩阵和范围，使用 tetrahedral LUT 插值；H.264 输出写入并实查原色、传递函数和矩阵。保留音频流，不拉伸时间；记录源视频、LUT、制作包、输出视频与色彩探测摘要。verify-craft 重派生所有资产，包括 LUT 内容；verify-grade 核验当前输入、配方和实收输出。GRADED_LOCAL 只表示后期文件生成，不是视觉质量 PASS。微表情驱动视频、经确认的风格锚点帧和真实区域质量验收仍由宿主制作、观察后登记。

离线 HTML 将轨迹按镜头只存一份，帧更新节点。摄影机 SVG 使用配置和 crop 的输出比例，不再固定拉伸到 16:9。尚无浏览器视觉验收或真实生成质量结论。

## 联合编译与限定范围

保留旧 vpc.py compile。新增的显式入口只属于视频编译器，读取完整冻结控制包和真实资产清单：

```bash
python scripts/control_cli.py compile outputs/control-v001 --target agnes-video-2.5 --mode text --artifacts outputs/control-v001/artifact-manifest.json --out outputs/joint-text
python scripts/control_cli.py compile outputs/control-v001 --target agnes-video-2.5 --mode keyframe --shot S2 --artifacts /absolute/path/to/control-artifacts.json --out outputs/joint-shot-S2
python scripts/control_cli.py verify-compile outputs/joint-shot-S2
```

同一次编译产生逐请求的正文、原字段到正文的覆盖、API 参数、附件索引、辅助职责、主执行义务和后期任务。附件标签由提交数组同源生成，正文保留真实文件名。已有 AVIR bindings 的 asset_id 必须精确映射到参与提交的清单 ID、摘要和文件名，不能仅凭相同字节悄悄更换来源 ID。跨请求同一 URL 绑定不同内容也阻断。目标能力与控制路由快照一并保存，端点或型号冲突不能合并。

`--shot` 可重复，但必须选择连续镜头；不隐式剪掉中间镜头。未选择时编译全片。按事件及明确状态寻找合法切点，内部首尾帧强制在其镜头边界拆段；片段缺所选模式的媒体时保留 BLOCKED 请求，不丢掉片段。lower 也可用 --shot 绑定请求范围，第二镜首帧不能充当全片首帧。一个 control 可为不同镜头绑定不同关键帧，依实际用途选择各段附件。

分段的 seconds 是本请求时长，全片时长条款保留 ASSEMBLY_REQUIRED；部分镜头导出明确 complete_project_scope=false。参数义务仅记已映射的结构断言，不能据此声称自然语言中的全部技术要求已兑现。后期任务为 PLANNED，所有 media_acceptance 为 NOT_RUN；COMPILED_DRAFT 仍不是已提交或模型控制成功。verify-compile 从原包和清单重新编译并比对正文及 JSON，单纯重算被改文件的摘要不能骗过校验。

## 依赖失效与返修文件

```bash
python scripts/control_cli.py repair outputs/control-v001 outputs/control-v002 --artifacts /absolute/path/to/control-artifacts.json --out outputs/repair-v002
# 有实收视频的失败观察时，在上述命令同时加入：
# --observations observations.json --media actual.mp4
```

命令比较两份同项目的已验证控制包，输出 dependency-graph.json、逐用途状态、关键帧与计划片段依赖、tasks/ 中的 OPEN 返修工作项、output-invalidations.json，以及包含真实文件副本的 artifact-manifest.json。原始 AVIR、清单和素材不修改。下一轮 lower/compile/keyframe-check 使用新清单；失效用途会被实际阻断，未受影响用途继续可用。返修文件是模块工作指令，尚未写入某个实际 V5 项目的 active_task；由当前 Agent 按 owner/module 接续已有项目 revise/任务交接，不能冒充已经完成返修。

失效记录同时绑定资产字节摘要与用途摘要。仅变更用途 ID 或删掉旧记录不是审核；新的图片/视频须重新登记文件哈希、当前配方、用途审核和上传绑定。重新生成并审过的新字节可保留旧失败历史，旧内容的失效标记不会永久封锁新内容。身份/造型/风格/场景母版依赖其职责切片，无关运镜变化不使全部母版失效。

观察输入必须连同实际视频一起重新经过冻结基线验证；FAIL 为该实收媒体的精确时段创建失效记录和责任模块任务。失败视频本身不证明上游身份母版有错，因此不自动废弃所有母版。要修改上游设计，由责任模块修订原生来源，再派生受影响资产和片段。上述命令创建任务和执行阻断，不自动宣称生成、审图或返修质量通过。

单镜头或分段实收视频可在 `control-media-review/0.2` 显式声明 `execution_range: {"start_ms": 4000, "end_ms": 8000}`。它必须与实际请求的项目时间范围一致；本地文件第 0 ms 对应项目第 4000 ms，只允许平移时间原点，不允许拉伸、裁切重映射或改写 AVIR。`evaluation_plan_sha256` 仍绑定原来的完整项目基线，观察点、事件和 finding 的时间全部使用项目绝对毫秒。缺省范围仍表示全片，不能把四秒实收隐式当成十二秒全片。

观察只比较范围内的原计划点和镜头画幅，片段时长须与实收相符；范围外的观察和错误事件被拒绝。切点只包含前段事件的 end 与后段事件的 start 各自所属的一侧，避免将 S2 的开始算作 S1 的漏事件。输出同时记录 `execution_range`、`media_time_offset_ms`、`shot_ids`、局部 `expected_count` 与完整 `project_expected_count`；`complete_project_scope=false` 时的覆盖率只属于该片段，不能用于宣称全片通过。声明映射不是提交回执证明，`mapping_evidence` 明确这一边界，宿主须另保留真实请求/实收关联。repair 沿用项目绝对时间创建失败任务，不因局部失败重写或作废正确的原生计划与母版。

时长及覆盖以实际解码的首个视频流为准，不使用可能由音频撑长的容器总时长。审核严格解码该流，核对逐帧原始显示时间和持续时间；首帧必须从媒体零点开始、帧区间连续、末帧结束与执行区间长度相符，仅允许 1 ms 时间戳量化误差。缺失时序、延迟起始、缺帧造成的时长不足或坏像素均拒绝，不自动补帧、平移或拉伸。`media_probe.duration_ms` 仍保留容器信息，新增 `media_probe.video_timeline` 保存实际帧数、起止时间、逐帧时间摘要及完整解码状态；完整解码仍不是视觉审核通过。

时间判定使用所选流的整数 PTS／持续 tick 与 `time_base`，内部以 Fraction 比较帧间、零点、末端和观察边界，避免精确 1 ms 被浮点相减误判超限。输出的 `start_ms_exact`／`end_ms_exact` 保留有理数毫秒，常规毫秒字段仅用于展示；帧时序摘要绑定整数 tick 序列及时间基，`frame_timing_format` 明确这一格式。没有提高 1 ms 容差。

跨宿主读取冻结包时，首先严格核对全部文件字节摘要，再从原 AVIR 重派生。只有计算得到的 `points[].projection.xy/depth` 允许不超过 8 ULP（浮点数相邻表示间距）的重算差异；源文件、时刻、世界位置、状态及其他字段继续严格比较。通过后保留生产者冻结的投影数值、评价基线和原摘要，不用消费宿主的新浮点结果替换它们。HTML 按既有构造顺序重派生，文件内容仍严格核对。降译、关键帧接收／编辑基图、白模登记和返修配方使用已核验包中对应时刻的冻结帧，避免只有机器舍入差异就作废正确输入。未在包内冻结的任意配方时刻仍按现有规则计算，不宣称任意运行环境或任意时刻都具有逐位相同的计算结果。


## 冻结事件的单张几何关键帧

当某一事件的状态明确、事件之间的运动尚未定义时，可只渲染这个事件，不补造插值：

```bash
python scripts/control_cli.py previs-frame outputs/control-v001 --keyframe K001_0 --artifact PROXY_K0 --blender /absolute/path/to/blender --out outputs/proxy-K001_0
python scripts/control_cli.py verify-previs-frame outputs/proxy-K001_0
```

配置须有明确 proxy_scene，指定 artifact 必须属于当前事件的单时刻控制用途，且不得替换原生身份/场景资产。输出单张 keyframe.png、scene.blend、计划、实际 Blender 读回、文件摘要和待审资产清单；不产生 MP4。复验重新派生来源、用途、摄影机及几何，重封摘要不能放行被改写的用途映射。完整预演仍要求每一帧都有明确运动依据。

RENDERED_LOCAL_KEYFRAME / VERIFIED_LOCAL_KEYFRAME 只代表本地中性几何渲染。无手脚或表情的代理图不得直接作为表演与身份验收通过的关键帧；需实际审图后作为限定用途编辑基图，经 keyframe-stage 冻结输入并由宿主生成、keyframe-receive 收回。普通多图输入不能保证冻结投影得到保留；必须按事前目标测量，失败结果继续保持 FAIL。

新建审阅页使用 `data-label-layout="2"`：标签在相邻行避让并用细线连接原点，节点坐标不移动；极密区域放不下的文字只在完整 legend 中保留。旧版页面与 SVG 仍以旧排布逐字节重派生验证；不能只改标记或重封摘要让混合版本通过。

派生 JSON 比较保留 `0` 与 `0.0` 的数值等价，但在所有嵌套字段区分布尔值和数值；`false` 不能替代时间/坐标的 `0`，`true` 不能替代 `1`，重封文件摘要也不能通过。

此类型区分也适用于宿主 stage、实收回执/资产清单及联合编译的逐请求/总表复核。`submitted`、`runnable`、`edit_base`、`complete_project_scope` 等布尔状态不能改成数字别名；文本和文件摘要校验保持独立。
