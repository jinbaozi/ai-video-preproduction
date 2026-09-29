# 官方 H3 Context-IR：显式选择，不冒充

[官方 API 文档](https://platform.minimax.io/docs/api-reference/video-generation-v2-h3-context-ir)，核对日期 2026-09-29。官方 Context-IR 是未开源的托管多模态预处理服务，不等于本项目 Context-IR，也不等于社区 Context Loop。

## 三条路径

默认：ChatGPT 宿主依据官方公开的 H3 提示词指南在当前会话整理，零模型 API 调用。来源记为 host-authored，不写“已运行官方 Context-IR”。

可选：用户已有官方结果时，连同原请求、创建回执、查询结果导入新候选。校验只证明文件之间的结构一致性，不证明传输或签名真实性。

可选：用户明确需要 API 接入时输出离线请求草案。凭据留在用户自己的安全调用环境；本 CLI 无网络请求、无 API Key 参数、无计费提交。

## 离线官方请求

```bash
python scripts/vpc.py h3 context-request brief.txt \
  --mode t2va --duration 5 --ratio 16:9 --out context-request-v001
```

生成 `context-request.json` 和 metadata。目标端点为 `POST https://api.minimax.io/v2/h3_context_ir`，正文 `model=MiniMax-H3`、`content`、整数 `duration`、`ratio`。这不是 RunningHub 的 `nodeInfoList`，也不是视频生成请求。

带媒体时 `--media media.json` 是有序数组：

```json
[{"kind":"image","role":"first_frame","url":"https://example.invalid/first.png"}]
```

示例地址不可运行。I2VA 需要 first_frame，L2VA 需要 last_frame，FL2VA 两者各一个；这些模式选 adaptive，不静默覆盖被 API 忽略的具体比例。Ref2VA 用 reference_image/reference_video/reference_audio，不得混合首尾帧端口；T2VA 无媒体且需具体比例。

当前构建器只允许 HTTPS URL，不支持内联 base64、回调或额外供应商字段。已有 `duration_seconds` 时校验参考视频/音频各2–15秒、同类合计≤15秒；实际 MIME、尺寸、时长、权限、文件内容和 URL 可访问性均未探测。仅数组数量合规不能标素材验收通过。官方能力更新时先补证据与测试，不猜字段。

## 导入结果，不直接接受

创建响应提供 `task_id`；必须再取得 Query Task 的 `task` 对象。只有 `status=succeeded`、`task_type=h3_context_ir`、`modality=text`、模型和 task ID 一致，且 duration/ratio 与原请求一致，才读取 `task.content.prompt`。

```bash
python scripts/vpc.py h3 context-import \
  context-request.json create-response.json query-response.json \
  --out context-candidate-v001
```

产物为 `context-candidate.json` 和 `prompt-candidate.txt`，含请求、创建、结果及正文 SHA-256。状态是 `IMPORTED_REQUIRES_SEMANTIC_REVIEW`，来源 `caller_supplied_receipts`，传输认证 `NOT_VERIFIED`。不替换冻结 AVIR，不补写模型生成、人工验收或历史收据。

宿主将候选与原文、参考职责、锁定身份、台词、动作、光色、焦点、时间和声音逐项对照，再按真实工作流映射并 `h3 lint/plan`。不同服务对视频伴随声轨的编号可能不同，不能照抄官方服务标签到本地原生图；重新映射也须作为有差异记录的新候选。

RunningHub 自己的 Context-IR 应用/端点是另一个供应商包装。本次未验证其具体请求/回执格式，不能套用 MiniMax 的 task 字段。提供真实接口说明和脱敏响应后才能新增包装适配；已有 prompt 可先走普通 host candidate 路径，但不伪造官方回执。
