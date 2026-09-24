# 原生关键帧构图修复：实收成功，质量 FAIL

这次实验只执行一次 Codex 内置 image_gen 编辑。生成前冻结请求、提示词、四张输入的顺序和摘要，以上一张实收摄影图为基图，保留人物身份、服装、摄影机及场景背景，允许调整信封、前臂与桌面位置。没有改变原 AVIR 或放宽验收阈值。

原始返回 PNG 原样保存在本地 outputs/host-keyframe-composition-repair-r1/actual-keyframe.png，未上传仓库；1672×941、1862254 字节。准确提示词在 [prompt.txt](prompt.txt)，编辑合同在 [request.json](request.json)。工具调用约 40 秒；未暴露供应商模型、执行编号或价格，这些字段保留 null，不能写成零费用或供应商签名证明。

实际查看输出及参考后，信封手工标记中心为 (745,577)，独立记录标记不确定性 ±12 像素。归一化中心 (0.445574,0.613177)，相对冻结目标 (0.378362,0.716245) 的误差约 (+0.0672,-0.1031)，即使考虑标记不确定性也超出每轴 ±0.02 的标准。结果为 FAIL；身份与材质仅作定性观察，手别及全部手部细节未确定。原始六项审图记录在 [visual-review.json](visual-review.json)。不因输出可辨识而声称可作合格首帧。

实收包校验返回 VERIFIED_RECEIVED_KEYFRAME，同时保留 visual_review=FAIL、submitted=false。首次作者回执误填了 stage 数据摘要，接收器正确拒绝且没有留下半包；随后只将作者声明中的 stage_sha256 改为 stage-manifest.json 的文件摘要。冻结 stage、提示词、输入及输出图均未改。这是作者回执纠正，没有修改产品校验器。

Agnes keyframe 降译结果为 BLOCKED，但存在多项阻断：原冻结实验包仍含三个 image_reference 通道，未迁移到后续新增的 keyframe_input；当前首帧审图失败、上传绑定和尾帧资产缺失，另有预算检查失败。因此不能把这次降译描述成仅由审图 FAIL 导致的独立负例，也没有真实提交视频生成。

本目录是公开实验摘要，**不是可独立重放的完整制作包**。原始输出图、完整 stage、四张输入、实收包、首次被拒的作者声明和完整降译报告保留在本地 outputs/host-keyframe-composition-repair-r1。公开文件摘要和验证边界见 [evidence.json](evidence.json)。没有进入 Skill 发行包，也没有追加同方法采样。
