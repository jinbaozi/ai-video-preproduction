# 审核结论：Request changes

**C01 已独立验证为修复；F02 的完整 `stage→receive→compile→verify-compile` 链路本轮已跑通。** 但新增反例发现一个 **C02／P2**：宿主请求进入冻结阶段前，仍可用 `false` 冒充位置数值 `0`，或用数值 `0` 冒充布尔状态 `false`，且后续交接没有识别这种类型偏离。

本轮固定审查：

```text
提交：71a2f65094b3395b4074d726cd6d4bf4fc278ea3
父提交：6a195d86a947491587f31678d4ceff06349e06a4
标题：Verify full host to joint compile handoff after audit
```

以上来自 GitHub 精确提交查询，未使用浮动 `main`。

:chatgpt-content-reference{index="5"}[下载完整原始审核报告](sandbox:/mnt/data/audit-71a2f65/AUDIT-REPORT.zh-CN.md)　｜　:chatgpt-content-reference{index="6"}[下载可重跑用例与完整证据包](sandbox:/mnt/data/71a2f65-incremental-functional-audit.zip)　｜　:chatgpt-content-reference{index="7"}[查看机器可读结果](sandbox:/mnt/data/audit-71a2f65/evidence/summary.json)

证据包已完成 ZIP 完整性和逐文件 SHA-256 检查，包含源码依赖、原生夹具、实际输入、重封反例、运行日志和生成的交接包。

## 一、实际运行范围

本轮取得了可读执行回执，不再停留于源码推导。

| 测试集合 | 独立执行结果 |
|---|---:|
| 当前 `test_joint_control.py` | **10/10 通过** |
| 当前 `test_keyframe_host.py` | **13/13 通过** |
| 额外对抗性检查 | **33 项：31 项符合预期，2 项漏放** |
| 缺陷归并 | 两项漏放属于同一个 **C02／P2** |

使用了两个完整原生 AVIR 1.2：仓库十二秒三镜头咖啡馆示例，以及审计自建的八秒双角色双镜头夹具。均经 **`build→verify`** 进入；联合编译正例满足语义审核、明确状态和分段边界等前置条件。

**45 个运行依赖文件**已核对当前 Git blob。关键文件如下，完整清单在证据包中：

```text
joint_compile.py
5438af7ec888aca432d4c6311f9f61d01e4f12d6

keyframe_host.py
7fffafd5a4ac0554fc62778663ed44f377aa4b6d

keyframes.py
918f3b58c19a6c94bee70cb2264d3d44e1090514
```

这些摘要与目标提交的目录树一致。

运行对象是**源码依赖子集，不是正式 Skill 安装包**。PNG 是实际可解码文件，但图片内容、语义签核、视觉审核、宿主声明和上传地址均为合成测试材料，不是供应商执行或生成质量证据。仓库原有的投影舍入测试按原样使用了投影函数 mock；独立缺陷反例没有替换验证器、Schema 或媒体解码工具。

## 二、C01：已验证修复，不再只是静态判断

从实际生成并通过复验的 `COMPILED_DRAFT` 出发，同时修改：

```text
REQUEST_001.json：
    parameters.n       1 → true
    payload_draft.n     1 → true

joint-compile.json 对应请求：
    parameters.n       1 → true
    payload_draft.n     1 → true
```

重算两个文件的清单摘要后，当前 `verify_export()` 返回：

```text
ValueError: Joint request differs from verified inputs
```

正例先通过，反例只改变指定字段，因此不是被缺文件或不合法前置偶然挡住。

额外检查也确认：`scope.start_ms: 0→false`、`submitted/runnable: false→0`、总产物布尔字段改数值均被拒绝；合法的 `0→0.0`、`1→1.0` 数值等价通过。同步修改正文及其副本、附件编号／摘要、来源绑定或时长参数并重封，也不能通过复验。

当前实现确实先检查重派生文件全集，再用 `same_json_value()` 比较单请求与总产物。

**C01 可在上述原反例和补充回归范围内关闭。**

## 三、新问题 C02／P2：冻结入口仍接受不可变请求的类型替换

### 精确位置

全部对应本次 SHA：

```text
video-prompt-compiler/scripts/shot_control/keyframes.py:16–18

相关入口：
video-prompt-compiler/scripts/shot_control/keyframe_host.py:50–71、89–106

相关 Schema：
video-prompt-compiler/schemas/keyframe-request.schema.json:51–55
```

`check_request()` 对不可变字段仍使用普通 Python 比较：

```python
mutable = {'generation_mode', 'master_anchors', 'base_asset_id', 'edit_delta'}
if any(request[k] != v for k, v in original.items() if k not in mutable):
    raise ValueError('Keyframe state differs from frozen source')
```

这里没有复用 `same_json_value()`。

### 有效前置与最小复现

使用已经完成以下正例的原生包：

```text
build → verify → keyframe-check
→ stage → receive → compile → verify-compile
```

三份身份／场景母版、基图、用途配方和审核记录均有效。复制其宿主 `request.json`，不修改 AVIR、控制包、PNG、提示词或其他字段，分别测试：

```python
# E01：原值是数字 0
request["camera_state"]["position"][0] = False

# E04：另一份独立副本，原值是布尔 false
request["subject_state"]["physical_interpolation"] = 0
```

这是**进入冻结阶段前的错误接纳**，不需要篡改已有 stage 清单。

### 实际与预期

| 用例 | 实际结果 | 预期 |
|---|---|---|
| E01：位置 `0→false` | `check_request` 无原因；stage 成功；`verify_stage` 接受 | 拒绝不可变字段类型偏离 |
| E04：状态 `false→0` | 同上 | 拒绝 |
| 对照：位置 `0→0.5` | `Keyframe state differs from frozen source` | 正确拒绝 |
| 对照：位置 `0→0.0` | 接受 | 正确数值等价 |

我又对 E01/E04 补齐与新 stage 匹配的合成宿主回执，实际继续执行：

```text
receive → verify_received → export → verify_export
```

两例均得到：

```text
MEDIA_RECEIVED
VERIFIED_RECEIVED_KEYFRAME
COMPILED_DRAFT
VERIFIED
```

实收包中的 `stage/request.json` 保留了错误类型，原制作包仍保留正确类型。对应原件、变更件及完整交接产物均在证据包中。

**这不是 `payload.n` 再次失守，也没有证明画面发生变化。** 联合编译仍从原 AVIR 获取制作状态。缺陷在于：宿主冻结输入与制作端不可变请求发生类型偏离，入口未识别；后续回执比较只是确认了这份已经错误接纳的请求。因此评为 **P2**，不沿用 C01 的 P1。

### 修复与验收门

最小修复是让请求入口采用相同的类型敏感比较，保留四个可修改字段的白名单：

```diff
-from .package import verify_package, recipe
+from .package import verify_package, recipe, same_json_value

-    if any(request[k] != v for k, v in original.items() if k not in mutable):
+    if any(not same_json_value(request[k], v)
+           for k, v in original.items() if k not in mutable):
```

本轮没有修改目标代码，也没有把建议补丁计为修复后通过。

**验收门：**E01/E04 在 `check_request/stage` 入口被拒绝且不发布半包；正常请求及 `0/0.0` 继续通过；补齐 `true↔1` 和其他嵌套字段的类型反例；现有 stage、实收、联合导出的重封回归不退化。

## 四、F01–F03：本轮补齐了哪些验证

| 旧问题 | 本轮实际运行结果与边界 |
|---|---|
| **F01：完整图片解码** | 仓库四类损坏 PNG 在有效 stage 后被拒绝接收，并检查无半包；有效 PNG、NOT_RUN、FAIL、UNDETERMINED、PASS 对照通过。另在真实 `compile_package` 入口替换三类损坏 PNG，同时更新文件、审核和绑定摘要，仍因 probe／decode／尺寸错误拒绝，而非仅靠哈希失配。 |
| **F02：宿主与视频消费隔离** | **三母版完整 `stage→receive→compile→verify-compile` 已运行。** 母版保留在原 AVIR 和 `source_bindings`，`consumer=image_host`、`native_slot=null`；视频附件仅实收 K 的 `first_frame`，正文明确母版未作为本请求附件提供，参数为四秒。 |
| **F02：真正原生 reference 义务** | 独立添加硬 `reference` 义务：实际提交索引存在时得到 `REFERENCES_MAPPED`；仅有 `keyframe_input` 不能冒领该视频参考义务。显式 `image_reference/first_frame` 的非法模式混用继续阻断。去重索引及跨请求 URL／哈希冲突也已随仓库联合测试运行。 |
| **F03：事件与参考范围分离** | 事件保持点时刻，另带冻结 `reference_scope`，完整参考联合导出及复验通过。合法实收 K 可作编辑基图；扩大用途范围并重算用途审核摘要后，lower／compile 均 BLOCKED，verify-compile 返回明确的 `file set differs`，编辑基图检查返回 `ANCHOR_REFERENCE_SCOPE_MISMATCH:K`。恢复原清单后再次通过。 |

上述结果可关闭**所列旧反例及本轮补齐的指定链路缺项**，不等于所有媒体格式、所有模型模式或整个生产系统已经无缺陷。C02 作为独立的新入口问题保留。

## 五、未运行边界与交付结论

本轮未执行全源码 `discover`、独立视频包十二模块 184 项全集、七个正式 Skill 的隔离安装／内置一致性／重复构建、真实 Blender 渲染、浏览器标签检查，以及任何真实图片或视频模型调用。原 N03/N04 时轴媒体也未在本轮逐字节重放，不新增这些项目的通过结论。

证据包提供：

```bash
python reproduce_all.py --out /absolute/path/to/new-audit-run
```

各执行步骤已分别运行并记录；整合入口做了语法检查，未再完整重复执行一遍。当前代码下，预期为仓库 **23 项通过**，独立 **33 项中 E01/E04 两项未满足拒绝要求**，最终退出码为 **1**。另附的 `repro_C02.py` 已单独运行并取得 `C02_REPRODUCED` 回执。

**最终意见：Request changes，修复 C02／P2 后再完成本补丁验收。** C01 的修复和 F02 完整联合链路已有独立运行证据；完整制作方案、图片构图达标、真实首尾帧平台执行和视频控制收益仍应单独验收，本轮没有新增任何生成质量 PASS。
