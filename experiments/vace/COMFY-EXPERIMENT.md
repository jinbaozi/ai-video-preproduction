# ComfyUI 本地 VACE 实验

这是官方 CUDA 运行器之外的独立路线。`comfy-runtime-lock.json` 固定实际 ComfyUI 提交、相关源码摘要、三份权重的 Hugging Face revision／大小／SHA-256，以及实际 Apple MPS 运行时。`comfy-cafe-workflow.json` 是本次实际提交的 API 工作流，不代表任意版本 ComfyUI 都兼容。

本实验只使用本地资源，无商业 API 费用。主权重、文本编码器、VAE 合计约 11.3 GB，下载后逐份校验，未向已有 Python 环境安装依赖。服务使用独立 base/model/input/output 路径、端口 8189，禁用自定义节点及商业 API 节点。

**必须显式指定独立 `--database-url`。** 此版本仅设置 `--base-directory` 时会自动迁移原安装目录的数据库。本次首次启动发现该行为后已停止实验服务、恢复原数据库并验证原摘要，随后以独立数据库重启；没有读取或发布原数据库内容。可复跑命令必须包含：

```bash
PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BIN" "$COMFY_SOURCE/main.py" \
  --base-directory "$TASK_OUT/runtime" --models-directory "$TASK_OUT/models" \
  --database-url "sqlite:///$TASK_OUT/runtime/user/experiment.db" \
  --listen 127.0.0.1 --port 8189 --disable-all-custom-nodes --disable-api-nodes \
  --reserve-vram 8 --preview-method none
```

上述变量须由操作者指向已核对的运行时和新的绝对实验目录；三份模型按 lock 中 `split_files/` 后的子路径放入 models。`CLIPLoader` 明确使用 CPU，VAE／VACE 在实际 MPS 上执行。没有把 CPU 文本编码器运行说成全部在 GPU 上完成。

## 输入与时间映射

AVIR 来自现有 `video-prompt-compiler/scripts/build_previs_example.py:fixture()`，与实际提交实验中的原生源逐字段相同。它显式声明信封关键位置之间采用线性代理运动。几何仅包含人物头、躯干、信封、桌面和地面；**没有手指、完整骨架、面部表演或真实身份参考**。

从同一 fixture 生成控制包时，把 `config.proxy_scene.fps` 设为 16、`resolution` 设为 `[512,288]`，其他源和摄影机保持原样。通过现有 `build` → `previs --shot S1` → `verify-previs` 得到实际 Blender 像素和读回投影。再运行：

```bash
python experiments/vace/prepare_comfy_cafe.py \
  --render /absolute/path/to/verified-render \
  --out /absolute/path/to/new-control-input
```

脚本核验完整 render，拒绝其他时间／画幅／帧率，提取 0、62.5、…、4000 ms 共 65 个真实帧，保存无损 RGB H.264 和逐帧来源摘要。并非将旧 24 fps 视频拉伸成 16 fps。实际提交的控制视频已通过此脚本重建，字节摘要完全一致。

将 `cafe-control-65.mp4` 复制到独立服务的 input 目录，然后把 `comfy-cafe-workflow.json` 作为 `{"prompt": WORKFLOW, "client_id": "a-new-run-id"}` 提交到本地 `/prompt`。先保留输入、工作流与验收条件的摘要，再记录真实 `prompt_id`；已提交后通过 `/history/<prompt_id>` 和 `/queue` 查询，不在观察超时后重复提交。工作流使用 20 步、固定 seed 20260925、CFG 6、shift 8、uni_pc／simple；这些是本实验冻结选择，不是已经证明最优的参数。

模型原始输出为 65 帧、16 fps，即 4.0625 秒。**事前冻结的交付规则**是保留帧 0–63，删除唯一的第 64 号结束边界控制帧，得到 4 秒视频；不改帧率或重新拉伸。原始输出必须同时留存。结束控制帧对应 AVIR 的 4000 ms 边界，不冒充发生在交付区间内部。

`WanVaceToVideo` 使用实际 RGB 白模作为 `control_video`，未提供 reference_image 或 control_masks；依据固定源码，其遮罩默认全白（全部生成区域）。RGB 白模并未被伪装为深度图或骨架姿态。输入与输出尺寸相同，节点不发生画幅裁切。

## 验收

检查真实历史回执、解码后的帧数／时间／尺寸，然后观察两个人物及服装、单个蓝色信封、右手前送／落桌／松手／收回的时间窗、固定摄影机和中性左窗光。信封中心按事前冻结 AVIR 投影比较，每轴容差 0.02；看不清时记录 UNDETERMINED。512×288 只用于本地执行与控制实验，不能冒充最终分辨率交付。没有身份图时不能声称同脸一致性，通过模型执行也不代表控制质量通过。

本路线的实际执行和质量状态见实验回执；原版 CUDA 预处理的 `evidence.json` 保留原结论，不能用新运行器结果覆盖它。
