# 执行门禁与图片终点 / studio-execution/1.0

新 studio 默认启用；旧项目、显式 lean 和 V6 audited 不自动迁移。此版本不修改旧记录、补造旧生成许可或迁移费用。

## 状态与范围

`start --stop-after images` 仍依次完成 Canon → ScriptIR → DirectorIR → 每场 ArtIR → 图片提示词 → 真实图片验收。成功返回 `IMAGES_DELIVERED`，不要求音频或目标视频模型，也不宣称完整前期或视频完成。这个终点对应第5阶段美术参考，不包含第7阶段分镜图和第8阶段模型视频包；后者仍走 full。

```sh
ai-comic-drama start brief.txt --project ./film --profile studio --stop-after images
ai-comic-drama scope ./film --stop-after images --reason '用户要求暂不制作视频，先完成图片'
ai-comic-drama image-report ./film
ai-comic-drama export ./film
ai-comic-drama scope ./film --stop-after full --reason '用户恢复完整制作'
```

scope 将理由留档，保留已有原生文件、收据与依赖；不把交付范围变化当作新剧情来源，不删除上游。当前任务重新派发，未完成阶段仍必须完成。未决图片或视频执行必须先回收。production-target 可保留 video，但在 images 终点下禁止视频计划/执行/交付借用图片验收。

## 唯一生图调用入口

宿主先注册实际能力，再调用 `begin-image --task-id TASK_ID`。内核在事务中复核：

- 活跃原生 image 任务及其未修改的信封；
- 已接受且当前有效的 Canon、剧本、导演、各场美术；分镜图另需 StoryboardIR；
- 当前 job、已接受提示词、精确引用及实际引用文件字节；
- 注册的宿主图像工具、当前交付终点、没有未决生成。

通过后返回 `execution.id` 和 `dispatch`。`dispatch` 含当前提示词路径、参数、参考与注册工具。每次调用的记录为 `IMG_...`；生成结果填写 `media.execution_record_id`。未登记、错任务、错版本的生成结果均拒收。

支持宿主以 Python 注入实际工具适配器：

```python
from ai_comic_drama_workflow.execution_gate import dispatch_image

# host_invoke(dispatch) 是宿主自己实现的真实工具调用，不是本包提供的服务。
# 返回 {"file": 实际图片路径, "call_evidence": 含注册工具名的真实调用证据,
#       "provider_task_id": 实际厂商任务ID或None}
response = dispatch_image(kernel, actual_task_id, host_invoke)
```

适配器调用前先预留；成功只进入 RECEIVED，**不自动视觉验收**。异常或缺实际图片进入 UNKNOWN；禁止适配器内部自动重试付费提交。工具凭据、费用授权和调用由宿主负责，不能把预留记录当作额外费用授权。

如果宿主不能通过 Python 注入工具，就按相同顺序执行 CLI begin → 一次真实工具调用 → 原生结果提交/恢复。要从技术上阻止旁路调用，需要宿主只向执行器暴露受控代理、隐藏直接生成凭据，并隔离项目存储写权限。此包只提供受控路径及拒收机制，不能拦截任意会话工具或抵抗能同时篡改代码与状态的执行者。

## 候选、导入与视觉检查

现有图片可以在当前原生 image 任务导入。`provider=provided` 还要填写 `provenance_kind=user_provided` 或 `external_untracked`，不能补造历史执行记录。导入同样复核原生前置、提示词、图片字节及逐项审阅；未决生成不能借导入清空。

保留已有 `visual_review.status/sha256/findings`；每条硬约束 finding 另有 `status=PASS`。新增 `visual_review.checks`，每项恰好一次：identity、composition、props、space、lighting、reference_fidelity。每项写 status 与 observation；FAIL/未决直接阻止接受。身份、道具或参考确实不适用时允许 NOT_APPLICABLE，并写 condition；构图、可见空间与光线不得全跳过。

```json
{"check":"composition","status":"FAIL","observation":"要求胸部以上，实际画面露出腰部。"}
```

宿主必须据实际图像填写，不能由程序或模板自动补 PASS。程序验证覆盖、字节和收据，不证明艺术质量。独立评审仍可通过 audited 模式开展；此策略不把单宿主自查称为独立评审。

若需要精确尺寸，在已接受提示词的 `params.expected_image` 冻结数值，如 `{"width":1080,"height":1920,"aspect_ratio":[9,16]}`；只写其中需要的字段即可。实际 ffprobe 尺寸必须匹配，比例采用整数精确比较，不擅自把近似9:16宣称为精确9:16。未指定数值时记录实测尺寸，不从“2K”等散文猜规格。

返修只改受影响项。若改变景别以避开几何问题，应先修订拥有此要求的原生阶段，再重新接受提示词与图片；不能以新构图证明原门的开启方向已经正确。角色相似、道具数量一致也不自动代表身份、手部和空间全部通过。

## UNKNOWN 与回收

`recover-image --evidence evidence.json` 在新策略下不接受普通“批准重试”文字。证据必须绑定原 record_id 和 task_sha256，附真实查询结果文件与观察。

```json
{
  "record_id":"原生IMG记录ID",
  "task_sha256":"原记录中的task_sha256",
  "state":"SUBMITTED",
  "provider_task_id":"真实厂商ID",
  "proof_file":"/absolute/provider-history.json",
  "observation":"原提交已在历史中找回，任务与参数匹配。"
}
```

UNKNOWN/SUBMITTED 继续保留预留，不允许改范围或新提交。RECEIVED 需实际 `file`，保存候选并结束未决状态；之后仍需原生视觉审阅。FAILED/NOT_SUBMITTED 只能依据真实终态证据，不以超时或取消请求推断。已知厂商ID不能替换或抹除。相同证据幂等，终态冲突拒绝。以上字段示例不可作为真实查询证据。

## 交付与恢复

`image-report` 只读当前原生任务、收据、引用和字节，区分 DRAFT、STALE、ACCEPTED 与执行候选；不会扫描文件夹后把所有图片判为已接受。`export` 失败则 BLOCKED，显式 `--draft` 只能得到 DRAFT。正式图片交付保存机器报告及索引；上游、提示词、图片或审阅收据改变后，重新查询会降级为 STALE/BLOCKED。

已导出的静态报告是当时快照，不是永久有效许可；继续执行前重新查询。自然语言总结只能解释程序状态，不能升级它。旧项目需保持原协议，或新建项目后以真实来源和候选图片重新走审核，不能手改 execution_policy 假装升级。
