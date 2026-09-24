# CPU shift 单变量对照

沿用 [CPU 基线](../cpu-baseline-r1/README.md) 的同一独立服务、模型、提示、种子、尺寸、20 步及单帧条件，仅把采样 shift 从 8 改为 5（输出前缀另设）。提交前冻结文件和实际工作流保留，真实回执显示采样节点未命中缓存，耗时 **96.254 秒**。

![实际 shift=5 原图](actual-output.png)

实际审图仍是明确的卡通插画：左侧深蓝服装人物伸手持竖直蓝纸，右侧米色服装人物伸出手掌，木桌和左窗可辨识，但脸、手及材质缺少自然摄影质感。原质量要求保持不变，结果 **FAIL**；未观察到本次调参恢复自然质感。

尝试较低 shift 的依据是 [Diffusers 官方 Wan 文档](https://github.com/huggingface/diffusers/blob/main/docs/source/en/api/pipelines/wan.md) 的低分辨率参数建议（2026-09-25 查询）。它是本次假设的来源，不是对 ComfyUI/VACE 这组条件的修复保证。只试一个值、一个种子和单帧，不能推论其他参数或正常长度视频都失败。

完整哈希、实际作业与缓存状态见 [evidence.json](evidence.json)。本次不检验动作时序或控制收益，不把竖直蓝纸绑定到某一 AVIR 事件时刻；没有商业 API 费用、环境安装或源码修改。复跑沿用 CPU 基线的独立数据库／目录和 `--cpu --fp32-vae` 启动说明，提交本目录工作流并记录新的真实编号。
