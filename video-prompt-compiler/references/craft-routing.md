# 默认专业方法路由 / craft-routing/1.0

**未点名也要执行。** 创作前从真实输入辨别观众目标、场景问题和硬约束，选择本职责的一个主语法及最多两个互补维度。先方法、后参考人，不按名气投票，不加载整个人名库。明确关闭才跳过；不因无命中而冒充已经采用名家经验。

## 工作次序

1. 当前宿主从原文、实际参考和已锁定上游中提取目标、语义标签、任务类型、时代/世界、媒介、显式偏好和禁用项。中文、英文标签均可；确定性检索不是语义理解器。用户不填写 JSON。
2. 完整工作流的新 `start` 默认启用。Canon RoleResult 提交 `craft_context`：`source_sha256` 取任务值，`roles` 包含 screenplay/director/art/storyboard；每个条目是 `features` 与 `evidence:[{source_id,quote}]`。features 必须含 `goal`、`tags`，可含 `task`、`world_mode`、`medium`、`requested`、`forbidden_profiles`、`forbidden_techniques`。所有证据来自注册的原文/已审阅观察，不能把二进制文件名当内容。仅有图片/扫描文档等非文本时先实际查看，在 Canon `/content` 登记观察；证据用 `kind:observation`、实际 `source_id`/`source_sha256`、`pointer:/content`、`quote` 和真实读取的 `inspection_ref`。这些仅为宿主观察声明，不是原文引文或独立媒体验收。无文本与无观察资料时补实际观察，不伪造提取。
3. 内核基于上述语义特征、原生注册表和冻结范围生成 `task.craft`。读取任务指定的 `craft:selected-methods` 即获得选中的规则、人物方法、适用依据、替代项与来源定位。Python 在本地检索注册表，不要求将所有条目装入模型上下文。
4. 导演 RoleResult 还需 `craft_scene_routes`（以原生 scene ID 为键）：每项给 `continuity_group`、`features:{art:{goal,tags,...},storyboard:{goal,tags,...}}` 及 `evidence:{pointer,quote}`。证据必须指向本场的原生场景描述。这里只描述观众/环境需要，不替美术决定设计；同一未中断空间组保持相同美术主语法。美术任务按自己的 scene scope 选方法，分镜按已冻结的场景特征补充局部规则；局部规则的采用位置必须属于该场，不得拿另一场的正文充数。场景级约束不能覆盖全局用户偏好和禁用项。
5. 将主语法写入当前原生字段：ScriptIR `/task/style_request`、DirectorIR `/intent/style_request`（并按原生合同同步 `scenes[].style_id`）、ArtIR `/brief/locked_style`、StoryboardIR `/style/primary`。保持项目/连续场景的基线，在当前场/镜细化规则；不得自动覆盖已有锁。出现不适用、明确混合风格或硬冲突时返回有范围的冲突给原所有者修订，不静默换风格或跳过。
6. 原生 RoleResult 添加 `craft_review`：当前 `plan_sha256`、内容专属 `rationale`、`semantic_review:true`、`applications`。每条选中/继承规则恰好一条记录：`id`、`status`、`reason`、`check`；applied 另给实际输出的 JSON `pointer`、`quote`、`value_sha256`。哈希为 `craft_router.digest(该字符串)`，不是文件 SHA。not_applicable 另给具体 `condition`；不能全跳过。指向真实正文/动作/镜头/美术字段，不指向风格标签、人名或审阅记录。
7. 上游采用项沿现有依赖交接。图片/视频编译不再选名家：图片证据指向包装对象 `/prompt`，编译复核指向冻结 build 的 `avir.json`；保留原来的覆盖、损失、模型能力和真实媒体门禁。改动源、候选或证据后必须重新检查。

```json
{
  "plan_sha256": "从当前任务复制，不手写假值",
  "rationale": "通过先给钥匙磨损细节、后给人物反应，控制观众先于角色获得线索。",
  "semantic_review": true,
  "applications": [{
    "id": "从当前任务复制规则ID",
    "status": "applied",
    "reason": "关键线索在反应镜头之前出现，未提前揭露隐瞒者。",
    "pointer": "/实际原生正文路径",
    "quote": "实际输出中存在的完整短语",
    "value_sha256": "对该路径对应字符串计算规范JSON哈希",
    "check": "逐镜核对线索出现时间、视点和角色认知，确保顺序成立。"
  }]
}
```

## 独立技能

四个创作技能可在自身目录执行 `python scripts/craft_router.py '用户内容' --analysis /临时/宿主语义特征.json`。不传 analysis 是**词法初筛**，必须由当前宿主结合原文复核，不得称为语义最优。没有 Python 时按同一规则手动读取小索引和命中卡，说明采用依据；没有机器执行就不声称内核验收通过。轻量单镜/单段任务交正文及一句方法依据，不强制创建项目或大报告。独立图片/视频技能消费已有锁；没有上游时在授权设计范围内采用本技能基础方法，不虚构一支已实际运行的团队。

旧 init / 已有项目不静默迁移。用户明确不要参考路由时新项目用 `start --craft-routing off`，关闭值冻结到 project/state；不能编辑配置偷关门禁。要修改已冻结的方法，返回原责任者修订事实/语义上下文与受影响下游，不直接篡改接受证据。

## 职责与质量检查

| 职责 | 方法必须落实到什么 | 不得越权 |
|---|---|---|
| 编剧 | 因果、人物目标、认知变化、线索/回收、对白声音 | 不为教学强加反转；不新增违反原文的事实 |
| 导演 | 可见表演、注意力、机位/运动动机、光色、转焦、声画及转场目的 | 不改编剧信息顺序；不以炫技代替可读性 |
| 美术/服化道 | 时代与身份、世界拓扑、色材质、衣装发妆、道具状态、实用光源 | 不重定机位、情绪与对白；连续场景不重置资产 |
| 分镜/剪辑 | 行动与反应、轴线、切点、匹配动作、声桥、入出镜状态 | 不用镜头切换掩盖空间/持物矛盾 |
| 图片/视频编译 | 把批准的规则落到实际正文、参考顺序、可执行通道及损失说明 | 不独立改风格，不猜测目标模型能力 |

每个运镜回答“新看见什么、为何此时移动”；每次转场回答“承接什么信息、动作或声音”；每个色彩/转焦变化有明确主体和情绪用途。无人/无道具场景不强配服化道；安静关系戏不强加爆炸和环绕；展示/教学以动作或物性证据为质量目标。

`SELECTED_NOT_APPLIED` 不等于采用，`EVIDENCE_BOUND` 只说明定位/字节/覆盖成立，语义质量是 `HOST_DECLARED`，实际媒体仍为 `NOT_RUN`。需要独立评审用 audited/V6；不能把同一 Agent 的自查称为盲审。模型可控性、素材质量、表演、剪辑与实际审片共同决定成片；此路由不保证“超级大片”。

人物条目沿用原库的 `CHAT`、`DESIGN`、`CHAT_DESIGN` 或案例研究状态。`project_interpretation_not_independently_verified` 不是当事人原话、已核验电影署名、授权背书或质量排名。最终生成正文写具体方法，不只写“某某风格”。
