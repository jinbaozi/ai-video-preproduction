# 自适应控制：方案与审查记录

基线：4539ced70047b74b985123ee974282f9d07b22a1（PR #2 已合并）。

## 目标

按镜头风险选择最少控制素材，不增设 Agent、不创建第二套内容 IR、不以等级充当画质证明。L0–L4 为规则分支而非质量分数；转焦、光色与几何需求分开。未知输入阻断，不记低风险。新 start 启用，旧项目和 init 保持原协议。

## 落地顺序

1. 同源纯函数从原生 StoryboardIR / AVIR 推导等级、源指针、必要素材和关键时刻。
2. 在现有控制任务和包中保存派生计划；仅几何/接触耦合镜头请求白模。读取详情按需进入专业合同。
3. 接入素材门：实际渲染回执、文件、用途审阅和当前镜头计划需一致；规划或静态验证不得冒领生成完成。
4. 对抗测试覆盖漏判、降级、伪造、陈旧证据、来源范围及老版本兼容；失败修正后重跑。

## 验收要求

- 简单静态场景不触发白模；人物数量、时长、静止轨道数量不构成升级理由。
- 接触/控制权转移、遮挡与耦合运镜不能靠空配置或降级数值规避。
- 缺数据、未知机位、轨道断段、非有限数、布尔数字混用不可视为完成。
- 俯视调度图用于内部审阅；白模不充当身份、细肢体动作或景深验证。
- 每个实际模型附件仍经过既有能力、配额、媒体用途与审阅校验，不新增虚构模型参数。
- 不删除旧原件；改动镜头重新计算计划，旧完成记录不能覆盖当前镜头。

## 审查结果

采用反例驱动的代码审查与测试，不冒充另一位独立审阅者。先写绕过/误判用例，观察失败，再修正并重跑。

| 反例或缺口 | 修正 | 回归依据 |
|---|---|---|
| 顺序走位被当作同时运动，触发不必要 L4 | 比较各主体实际变化区间及与机位的交集 | disjoint_actor_motion / sequential_not_overlapping |
| `path=not_applicable` 掩盖原生位置变化 | 状态 changes 仍触发空间控制 | explicit_position_change |
| 未使用节点使其他镜头素材失效 | 指纹只保留本镜引用节点及祖先 | unrelated_node_label |
| 直接 lower 可绕过本地必需素材 | 联合编译/降译执行同一个素材门，按实际选择镜头作用 | direct_lower / actual_render_selected_scope |
| 删除 project 策略字段导致回退旧逻辑 | 在项目与状态中绑定策略和下限，不允许单侧降级 | deleting_project_policy / explicit_floor |
| 白模只存档，后续图片没有使用 | 把精确事件图绑定到分镜图有序输入，复核实收 input_bindings | exact_scoped_proxy / input_binding_checks |
| 最近帧替代、同一时刻不同几何、篡改图片或报告 | 精确时刻、唯一内容、摘要与来源复核 | nearest_frame / ambiguous / changed_materials |
| 自动工作流忽略自定义视频通道 | 自动路径限定 keyframe_input；显式视频附件交给现有联合编译 | auto_path_rejects_unconsumed |
| 缺少只返修控制素材的恢复入口 | revise control 保留历史、重新发任务，不重做上游剧本 | explicit_control_repair |
| 单独安装时测试误读相邻源码 | 测试使用包内样例和锁定模块；七包隔离验证包含新测试 | shared_routing_bytes / isolated release CI |

本地新原生工作流集成覆盖三镜文本链的完整交付、V6 新建、策略下限及几何输入绑定；原生文本链通过时仍是 PLANNED_NOT_RENDERED，无实收图片与视频。本地没有 Blender，真实渲染测试使用显式环境条件而不是模拟返回成功。CI 的 control-render 安装实际 Blender，在合成几何场景上执行渲染、场景重开、投影读回、媒体探测、逐镜素材门及几何修改后失效测试。测试审核记录标为 synthetic，不作真实看图/视频质量结论。

验证命令：

```sh
python ai-comic-drama-workflow/scripts/sync_shared.py --check
python ai-comic-drama-workflow/scripts/package_suite.py --out dists
python ai-comic-drama-workflow/scripts/run_tests.py
python -m unittest discover -s video-prompt-compiler/tests -p 'test_*.py' -v
BLENDER_EXECUTABLE=/path/to/blender python -m unittest discover -s video-prompt-compiler/tests -p 'test_adaptive_control.py' -v
python ai-comic-drama-workflow/scripts/verify_suite.py --packages dists --out /tmp/adaptive-release-check
```

最终提交的 workflow、compiler、release、control-render 四个 CI 任务提供执行结果和日志；不把先前提交的绿灯当作本提交的证明。现有模型能力、原生内容校验、真实图片审阅、声音与连续性验收、生产预算/重复调用防护均保留。此次不报告视频生成提速比例；真实模型生成、动作遵从与最终画质验收为 NOT_RUN。


## 恢复中断后的补充审查

上次构建失败于真实 Blender 4.0.2 的 Action 不含 layers；发布步骤因依赖失败被跳过，不是 GitHub 写权限错误。恢复时重取固定基线和候选补丁，不使用旧 PR 的测试状态替代本次验收。

| 新增反例 | 修正与回归 |
|---|---|
| 仅支持分层 Action，旧 Blender 渲染失败 | 按对象能力读取 layers/channelbags 或 legacy fcurves；未知布局失败关闭；两条分支单测及实际 Blender 集成测试 |
| 摄影机轨道覆盖全镜，但接触发生在静止区间 | 按实际变化区间而非整条轨道时长判定耦合，避免误升 L4 |
| 接触只写在空间关系中，被动作扫描遗漏 | 区间 touching/attached_to 参与耦合判定 |
| 固定机位下双人接触运动只得到 L3 | 接触参与者和实际运动区间交集触发 L4；无关接触不升级 |
| NaN/布尔坐标/空矩阵轴避开误差比较 | 先验证有限数、向量维数和类型，再比较投影与几何；渲染计划比较不混同 bool 和 number |

11 项补充回归先记录失败，再修正并通过。验证的是已列出的反例与发布条件，不声称穷尽所有缺陷或完成真实视频模型质量验证。真实渲染及最终树的完整测试结果以对应 CI 日志为准。
