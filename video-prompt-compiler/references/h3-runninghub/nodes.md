# RunningHub 原生 H3 节点操作

依据 [RunningHub 官方 API 文档](https://www.runninghub.ai/runninghub-api-doc-en/doc-8287464) 和 [固定 Comfy 源码](https://github.com/Comfy-Org/ComfyUI/blob/a7169322485d0049380fb207fa17e9fb3ec40486/comfy_extras/nodes_minimax_h3.py)。本适配器生成离线修改计划，不是 RunningHub 客户端，也不自动操作网页或提交任务。

## 最小闭环

保存原工作流副本，从 RunningHub 导出 **Export Workflow API**，不是含 `nodes/widgets_values` 的编辑器 JSON。先删除 API Key 等凭据；不要把账户秘密粘进对话。读取实际节点 ID、`class_type`、输入和连接，再决定修改，不使用教程里的 ID。

```bash
python scripts/vpc.py h3 inspect workflow-api.json
python scripts/vpc.py h3 plan workflow-api.json \
  --node '<实际 H3 节点 ID>' --sha256 '<inspect 返回的 workflow_sha256>' \
  --prompt h3-prompt.txt --out output-h3-v001
```

输出 `h3-prompt.txt`、`runninghub-plan.json`、`workflow-api.patched.json` 和中文 `README.md`。原文件不改，输出目录必须为空；读取后的图变了就重新 inspect。JSON 输入顺序参与指纹，引用顺序不能被 `sort_keys` 悄悄改动。

## 修改对象与保护项

| 目的 | 确认后修改 | 不做什么 |
|---|---|---|
| 提示词 | 原生 H3 节点的 `prompt`；被转换成输入时，显式绑定真实上游字符串节点 | 不假定另有 CLIPTextEncode；不把连接数组改成文字 |
| 替换图片 | 实际 LoadImage 的 `image`，使用上传回执里的 `fileName` | 不填本机绝对路径、外部 URL 或虚构上传名 |
| 固定随机性 | 相关采样链的 `seed/noise_seed` 显式列入 `nodeInfoList` | 不依赖 UI 的随机切换状态 |
| 时长 | H3 的 `length` 帧数；核对向上对齐与尾帧 | 不把 5 秒填成 length=5 |
| 画布 | 已确认的宽高，32 倍数、基础像素预算内 | 不把基础模型改成大尺寸冒充 Regenerate |
| 质量/速度 | 仅有依据且被用户选中的实际采样字段 | 不自动降步、切 LoRA、改 CFG 或安装节点 |

补充标量改动使用 `--edits edits.json`：

```json
[{"nodeId":"实际ID","classType":"实际类名","fieldName":"steps","expectedValue":20,"fieldValue":25}]
```

这里的 20→25 是结构示意，不是统一优化推荐。旧值和类型必须与快照一致，节点、字段不存在则阻断。连接、结构化输入、`control_after_generate` 不允许写入；重复写同一字段也阻断。

若 `prompt` 是连接，`--prompt-binding` 文件形如 `{"nodeId":"实际字符串节点","classType":"实际类名","fieldName":"value"}`；必须位于提示词的真实上游路径。自定义字符串节点的输出语义仍需操作者核对，静态连通不证明拼接内容正确。

改 LoadImage 时另加 `--upload-receipts uploads.json`，映射为 `{"实际节点ID":{"code":0,"data":{"fileName":"上传接口真实返回值"}}}`。工具不上传图片，调用方提供的回执也不等于已验证云端文件内容。

## 模式、帧数与采样链

`MiniMaxH3ImageToVideo` 对应 FL2VA 家族权重，按 first_frame/last_frame 是否连接识别四种子模式；`MiniMaxH3ReferenceToVideo` 对应 Ref2VA 家族权重。视觉参考须有 video VAE，音频须有 audio VAE。工具核对可见文件名与采样连接，不验证权重真实字节或 GPU 支持。

H3 输出必须进入相关采样器的正向 conditioning，只有 latent 或 negative 连接不算提示词生效。所有相关显式种子都会加入 `nodeInfoList`；这改善复现条件，但不承诺跨后端逐像素确定性。

| 请求 length | 实际帧数 | 24fps 时长 |
|---|---|---|
| 120 | 124 | 5.1667 秒 |
| 240 | 243 | 10.1250 秒 |
| 360 | 362 | 15.0833 秒 |

原生训练范围提示与官方 4–15 秒 API 口径不同；低于124帧警告需实测。输出同时给最后帧时刻 `(frames-1)/24`，不要将“结束时间”与“最后帧采样时间”混用。改变帧数后重新审阅切点、口型、动作终态；不自动重定时。

## 明确边界与排障

仅支持已识别的原生 H3 API 图。未知 Partner/API 包装节点、子图内部、普通数组常量及不支持的自定义结构均停止自动改写；它们不是“坏工作流”，而是超出此适配器范围。不得猜节点的 widgets 位置。

`E_RH_WORKFLOW_DRIFT`：重新导出并核对；`E_RH_PROMPT_BINDING`：查看真实字符串生产者；`E_RH_CHECKPOINT_FAMILY`：先确认实际权重与节点家族；`E_RH_REFERENCE_LINK`：检查上传和连接，不把 URL 当图片输入；`E_RH_SEED`：找到真实采样链的种子；`E_RH_PROMPT_CHECK`：修复对应模式语法，不能删去用户硬要求。

实际执行时记录工作流版本、节点包/权重版本、种子、分辨率、帧数、步数、采样器及回收媒体。失败先定位配置/输入/排队/推理/输出阶段；费用或提交状态未知时先查询原任务，不能盲目重试造成重复计费。当前工具不提供查询和重试客户端。
