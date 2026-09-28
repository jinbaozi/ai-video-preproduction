# 按需控制素材

新工作流 `start` 使用 `adaptive-control/1.0`。等级从原生 StoryboardIR / AVIR 1.2 推导，不新增剧情、动作、轨迹或内容 IR。旧项目与 `init` 不迁移。等级是选择素材的规则分支，不是画质评分或模型原生参数。

## 先看本镜需要什么

| 条件 | 等级 | 最少增量 |
|---|---|---|
| 已知机位的静态空镜 | L0 | 原生镜头规格、提示词 |
| 可见人物或表演 | L1 | 复用身份锚点、必要画格 |
| 空间走位、运镜或光学变化 | L2 | 几何运动用俯视调度图与轨迹；转焦用事件帧及时间验收 |
| 接触、控制权转移或遮挡 | L3 | 调度图与事件白模帧；生成后仍检查真实人物/接触 |
| 接触与机位运动重叠、多人物运动与机位运动重叠，或相互接触的两个人物同时运动 | L4 | 连续白模预演及其事件帧，不再额外凑一套白模帧 |

人物数量、时长和静止位置轨道数不触发升级。运动按镜头和实际变化区间的交集判定，机位静止区间不算运镜，固定机位下双人接触运动仍需连续预演。手部与根节点归属于同一人物。未知状态不能降为 L0；L2/L4 的连续轨道缺口回分镜补齐。L3 可使用已定义事件的单帧，不擅自插值。光色和焦点验收独立保留；白模不承担生产照明、景深、身份、步态或细部接触证明。

## 默认宿主循环

宿主在原生 `control` 任务中收到逐镜等级、源指针、必要素材、关键时刻。把 `adaptive: {"policy":"adaptive-control/1.0"}` 加入现有 control-config，不增加另一个计划文件。派生计划写进现有 `control-plan.json`，验证时从原始输入重算。`adaptive.minimum_levels` 可按镜头提高下限，不能降低推导需求；工作流 `start --control-minimum 3` 可在新项目统一要求事件白模。项目下限必须在配置各镜头中保留。

使用锁定视频编译器的原有 `control build`、`previs-frame` 或 `previs`。没有明确 proxy_scene、数值机位/几何或真实 Blender 入口时阻断，不用箭头示意图、空壳回执或模型猜测冒充白模。缺图不把 full 改成 text-only。空间细节、白模配置与渲染命令按需读[镜头控制合同](shot-control.md)。

自动工作流只接受 `keyframe_input` 控制用途或空 controls；白模事件图作为几何输入，身份/服装/场景母版独立保留。配置需要先声明 `previs-frame` 的输出 ID。L4 可从完整预演中复用事件帧，不复制所有中间帧到交付目录。时间必须对应原生 state_samples/画格；找不到精确时刻时补原生事件，不选“最近一帧”。

已接受控制素材的几何事件图加入分镜图任务的有序 `references`。返回图片的 `input_bindings` 必须逐项匹配，且按原生锁定项记录看图结果。只生成白模而不让分镜图消费它，不能通过完整制作的编译/交付门。白模是几何输入，不作为身份或最终风格来源；带箭头/文字的调度 SVG 仅供内部审阅。

直接向视频入口投喂首尾帧、clay video 或轨迹时，使用既有独立 `control lower/compile`，保留原生能力注册表、附件配额和用途检查。自动工作流不静默忽略这类自定义通道，也不把内部 keyframe_input 宣称为已提交视频附件。不支持的入口返回 BLOCKED；需要用户改变模型、明确拆段或修订需求，不偷偷降低控制等级。

## 素材证据（仅控制任务需要）

在现有 RoleResult 中加入 `adaptive_evidence`，无需再建旁路报告。路径相对于项目目录，文件必须位于项目内。下例是格式说明，不能直接当作审阅记录：

```json
{
  "adaptive_evidence": [{
    "shot_id": "S1",
    "kind": "proxy_keyframe",
    "package": "work/proxy-S1-K0",
    "review": {
      "reviewer": "实际审核者",
      "render_manifest_sha256": "实际 render-manifest.json 的 SHA-256",
      "checks": [
        {"criterion":"layout", "result":"PASS", "observation":"实际观察的站位与原生位置对应情况"},
        {"criterion":"camera", "result":"PASS", "observation":"实际机位、方向和投影观察"},
        {"criterion":"key_pose", "result":"PASS", "observation":"当前事件可见的已建模姿态；不得声称未建模手指合格"},
        {"criterion":"scope_limitations", "result":"PASS", "observation":"确认此图仅作几何输入；列出未建模部位与下游验收义务"}
      ]
    }
  }]
}
```

连续白模的 kind 为 `clay_previs`，以 `timing` 替代 `key_pose`。检查项须完整且唯一，观察为空、FAIL 或 UNDETERMINED 不得通过。验证器检查实际文件集合、Blender 读回、媒体探测、当前几何/机位/时刻、摘要及用途审核。单帧不能替代 L4；完整预演可覆盖 L3 所需事件。源包必须保留，不覆盖旧渲染来源。

```sh
python scripts/control_cli.py assess source.avir.json --config control-config.json
python scripts/control_cli.py material-check control-package --evidence role-result.json --base /项目目录
```

独立 lower/compile 的 `control-artifacts/0.2` 也可携带相同 `adaptive_evidence`，路径以清单目录为基准。只核验本请求所选镜头，缺少本镜素材不得绕过，未选镜头不额外渲染。静态 text-only 工作流允许前期计划交付，但状态为 `PLANNED_NOT_RENDERED`，不表示可以执行媒体生成。

## 验收边界

派生等级、审阅 SVG、白模本地渲染、宿主图片生成与视频模型遵从是不同证据。`CONTROL_MATERIALS_VERIFIED` 只表示本地素材和记录经过一致性校验，不是厂商签名或独立看图证明。测试中的模拟审核者不是实际质量结论。

修订原生镜头用已有 revise；只返修控制素材时，lean 可用 `ai-comic-drama revise PROJECT control --shot-id S1` 再 step，保留历史证据并重新派发控制任务，不重写上游剧本。修改镜头、几何、机位或输入文件后重算；只要逐镜派生渲染计划一致且旧包字节有效，未受影响的渲染可复用。新项目固定策略版本和下限；不能单删 project 字段回退旧协议。模型执行与画质保持 NOT_RUN，直到取得并审核真实输出。完整视频验收仍走原生产台账，不因 L4 或本地渲染成功自动通过。
