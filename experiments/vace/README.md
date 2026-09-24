# VACE 隔离兼容性实验

此目录不进入七个 Skill 的发行包，不安装模型、不执行网络提交，也不改变 AVIR 的时间或摄影机权威。当前只实际运行固定源码的帧选择和像素预处理函数；**尚未完成 VACE 推理适配与质量实验**。

固定官方仓库 [ali-vilab/VACE](https://github.com/ali-vilab/VACE/tree/48eb44f1c4be87cc65a98bff985a26976841e9f3)，提交、相关源码 SHA-256、Wan 1.3B 预处理参数在 `upstream-lock.json`。检查点名称已选定，权重 revision 仍为 null，未下载或加载，不能当成权重版本已验证。

## 实际结果

| 输入 | 原版预处理及固定 16 fps 保存 | 结论 |
|---|---|---|
| 本地 Blender cafe 白模，640×360、24 fps、96 帧、4 秒 | 640×352、93 帧、5.8125 秒，最大帧时间偏差约 1791.667 ms | BLOCKED：时长、事件映射和画幅发生变化 |
| 独立合成正例，832×480、16 fps、81 帧 | 832×480、81 帧，逐帧时间偏差为 0 | PREPROCESSING_ONLY：本例预处理可兼容；非生成质量通过 |

完整逐帧映射和实收探测在 `evidence.json`。正例的实际 MP4 stream duration 为 5.062012 秒，输入输出一致；81/16 是名义帧时长，未用它覆盖容器实际探测值。预处理预览是对输入像素的确定性转换，不是 VACE 生成视频。两个目录的原始输入及预览留在本地 `outputs/vace-investigation/`。

`inspect_preprocessing.py` 加载未修改的官方 `VaceVideoProcessor`，调用 `_get_frameid_bbox` 与 `_video_preprocess`。解码与时间戳分别来自 FFmpeg/FFprobe，**没有运行官方 decord 读取器**，因此不能将这个函数级结果扩展为完整官方 loader 或推理实测。重采样帧号、裁切尺寸、实际输出时长均保留。

官方 Wan 路径 `wan_vace.py` 显式使用 CUDA；本机实际宿主探测为 Apple arm64、CUDA 不可用、MPS 可用。实验 CPU 环境下 MPS 探测受沙箱影响，另存宿主探测以避免误判。官方 CUDA 路径不能直接在本机执行，但这不代表所有 VACE 实现均不支持本机；[ComfyUI 官方 VACE 路线](https://docs.comfy.org/tutorials/video/wan/vace) 需独立核验，不能继承本实验结论。

## 复跑

需要已有 Python 环境含 numpy、torch、torchvision、Pillow，以及 ffmpeg/ffprobe。使用隔离环境，不向现有 ComfyUI 环境安装依赖。本次只读取已有 PyTorch 运行时，没有安装权重或修改用户 ComfyUI。

```bash
git clone https://github.com/ali-vilab/VACE.git outputs/vace-investigation/upstream
git -C outputs/vace-investigation/upstream checkout 48eb44f1c4be87cc65a98bff985a26976841e9f3

python experiments/vace/inspect_preprocessing.py \
  --upstream outputs/vace-investigation/upstream \
  --media /absolute/path/to/clay.mp4 \
  --out outputs/vace-investigation/new-preprocessing-run

ffmpeg -f lavfi -i testsrc2=size=832x480:rate=16 -frames:v 81 \
  -c:v libx264 -pix_fmt yuv420p outputs/vace-investigation/compatible-control.mp4
```

脚本拒绝源码摘要/提交不匹配、覆盖已有输出目录。实际检查了错误 checkout 和已有输出目录的拒绝路径。命令退出 0 表示实验报告成功写出，**是否可直接保留制作计划必须读取报告 status/reasons**，不把实验执行成功等同模型输入就绪。

## 接续验收门

1. 从冻结 AVIR 重新设计兼容的时基、帧数和画幅，或由上游明确批准时间/裁切映射；不能将 4 秒任务静默改成 5.8125 秒。
2. 固定实际运行器及权重 revision、预处理器、条件编码；记录遮罩白色为生成区域、黑色为保留区域，与参考图职责分离，依据[固定版本官方指南](https://github.com/ali-vilab/VACE/blob/48eb44f1c4be87cc65a98bff985a26976841e9f3/UserGuide.md)。本实验未验证遮罩或深度/姿态编码。
3. 在兼容硬件/运行器上执行冻结镜头，保留原始控制输入、实际模型输出、耗时、费用和失败；进行身份、动作、轨迹、光色观察后，才判断质量。

当前权重加载、VAE/生成推理、成片质量和生成费用均未验证；实际预处理耗时不等于模型生成成本。
