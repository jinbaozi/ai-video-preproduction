# 审核结论：Approve——本次 C02 修复及受测链路通过

本轮实际查询并固定审查的是：

```text
提交：ac65dd8b012109bf258cdcebe8c5f8169b3263a6
父提交：71a2f65094b3395b4074d726cd6d4bf4fc278ea3
标题：Reject boolean aliases in frozen keyframe requests
```

与指定目标一致，未使用浮动 `main`。

**本补丁意见：Approve。** 原 C02／P2 的 E01、E04 已用上轮归档的原包、原请求重放并被拒绝；新增嵌套类型、合法数值等价、编辑字段白名单和下游联合编译检查均符合预期。本轮没有复现需要阻断该补丁验收的新缺陷。

**完整优化方案意见：尚未最终交付。** 图片构图、视频质量、真实首尾帧平台执行及控制收益，与本次软件合同验收分开判断。

:chatgpt-content-reference{index="7"}[下载完整原始审核报告](sandbox:/mnt/data/audit-ac65dd8/AUDIT-REPORT.zh-CN.md)　｜　:chatgpt-content-reference{index="8"}[下载可复跑用例与证据包](sandbox:/mnt/data/ac65dd8-incremental-functional-audit.zip)　｜　:chatgpt-content-reference{index="9"}[查看机器可读结果](sandbox:/mnt/data/audit-ac65dd8/evidence/summary.json)

证据包已完成 ZIP 完整性及逐文件 SHA-256 校验，包含源码依赖、原生夹具、原 E01/E04 输入、运行日志、阶段包、联合编译产物和用例脚本。

## 一、源码与独立运行范围

本轮核对了 **45 个运行依赖文件的 Git blob**。关键文件如下：

```text
keyframes.py
b4db121cdf4c803ee9f6609eda1b2fc506ba4e67

keyframe_host.py
7fffafd5a4ac0554fc62778663ed44f377aa4b6d

joint_compile.py
5438af7ec888aca432d4c6311f9f61d01e4f12d6

package.py
60a0e438c39f1ddd5ca1660faa463270b937e007
```

图片包的 `keyframes.py` 也查询到相同的 `b4db…` blob。这证明该共享源码同步，但不等于本轮执行了图片 Skill 的独立安装验收。

容器直连 GitHub 的 DNS 解析失败，因此复用了上轮归档中 blob 未变的文件；变化文件依据当前连接器返回内容重建，**通过当前 Git blob 校验后才执行**。运行对象是源码依赖子集，不是完整仓库克隆或正式 Skill 安装包。

实际取得的结果为：

| 测试集合 | 本轮结果 |
|---|---:|
| 当前 `test_keyframe_host.py` | **14/14 通过** |
| 当前 `test_joint_control.py` | **10/10 通过** |
| 上轮独立审计脚本的选定链路重放 | **33/33 通过** |
| 原 E01/E04、嵌套类型与白名单矩阵 | **29/29 通过** |
| 合法数值／白名单的完整下游链 | **5/5 通过** |
| 不变输入与 FAIL 输出返修 | **2/2 通过** |

即 **24 个仓库测试方法、69 项独立审计检查**均符合预期。部分是同一反例在不同消费者中的重放，不宣称它们是 93 个互不重复的场景，更不等同于作者的 185 项发行测试。

使用的有效前置包括仓库十二秒三镜头 café AVIR，以及审计自建八秒双角色双镜头 AVIR；均经实际 **`build→verify`** 进入。PNG、来源摘要、用途、配方、审核记录和明确切点齐备。合成宿主回执、合成审核 PASS 和测试 URL，**不作为模型执行或生成质量证据**。

## 二、C02／P2：原反例关闭，白名单没有被误伤

### 修复位置

```text
video-prompt-compiler/scripts/shot_control/keyframes.py
第 4、16–18 行
```

当前对不可变字段使用 `same_json_value()`，仍只允许以下四个字段进入可修改集合：

```text
generation_mode
master_anchors
base_asset_id
edit_delta
```

其余状态与制作端原始请求进行类型敏感比较；白名单字段的合法性仍由后续规则检查。

### 原 E01/E04 的实际重放

先用当前源码验证上轮归档的原制作包和原正确请求，正例通过。然后分别提交上轮保留的错误请求，未修改它们的字节：

| 案例 | 最小变更 | 当前实际结果 |
|---|---|---|
| **原 E01** | `camera_state.position[0]`：`0 → false` | `Keyframe state differs from frozen source`；输出目录不存在 |
| **原 E04** | `subject_state.physical_interpolation`：`false → 0` | 同上 |
| 本次 crop 零值 | `camera_state.crop[0]`：`0 → false` | 同上 |
| 本次 crop 一值 | `camera_state.crop[2]`：`1 → true` | 同上 |

还实际执行了上轮原样 `repro_C02.py`，取得：

```json
{
  "result": "REJECTED",
  "message": "Keyframe state differs from frozen source"
}
```

退出码为 **0**，没有发布输出半包。

### 新增边界检查

深层 `motion_values` 的时间与位置、`state.A.position`、`interpolated` 等字段发生 boolean／number 替换时均被拒绝。关键深层反例先通过请求 Schema，再在不可变源比较中被拒，**不是靠无关的缺字段错误挡住**。

相反，数值 `0→0.0`、`1→1.0` 通过；原有合法布尔字段保持布尔类型。把真正的状态 `false→true` 则被拒绝，没有将其误作数值等价。

**C02／P2 状态：在本轮有效前置、原反例及新增边界范围内关闭。没有新增阻断修复要求。**

## 三、合法变更也完成了下游链路

本轮不只执行了 `check_request` 或 `lower`。

既有合法编辑请求使用一张已审 FAIL 的独立 K 基图和三份 PASS 母版，完成：

```text
build → verify → keyframe-check
→ stage → verify-stage
→ receive → verify-received
→ compile/export → verify-compile
```

另一个正例同时进行了允许的变更：从编辑切换为生成、移除编辑基图与差量、调换母版顺序，并将部分数值改成等价浮点表示。它也完成了整条链路。

实际产物满足：

- 冻结输入顺序与请求一致；生成模式不再携带编辑基图。
- 三份母版保留在原生来源和 `source_bindings`，标记为 `image_host`、`native_slot=null`。
- 视频附件仅实收 K，载荷使用 `first_frame`，没有混入母版 `images` 数组；参数为四秒、`n=1`。
- 导出状态为 `COMPILED_DRAFT`，复验为 `VERIFIED`，执行仍为 `submitted=false`。

缺差量、缺基图、缺可见角色身份母版、编辑改动与保留路径冲突，以及生成模式夹带编辑字段，均被阻断。

**四字段白名单不是“任意修改豁免”，也没有因 C02 修复而失去合法使用路径。**

## 四、旧问题的本轮验证边界

| 项目 | 本轮实际结论 |
|---|---|
| **C01／P1** | 从有效联合导出同时修改两份 JSON 中的 `parameters.n`、`payload_draft.n` 为 `true` 并重封，复验拒绝。正文、附件索引／摘要、来源和时间变更也被拒；合法数值等价通过。 |
| **F01：图片完整解码** | 四类损坏 PNG 在有效 stage 后接收被拒，未留下半包；有效 PNG 和 NOT_RUN／FAIL／UNDETERMINED／PASS 对照通过。独立 compile 入口对三类损坏文件同步更新摘要后仍拒绝。 |
| **F02：消费隔离** | 三母版的完整宿主到联合编译链路通过。真正原生 `reference` 义务通过实际附件索引得到 `REFERENCES_MAPPED`；只有 `keyframe_input` 不能冒领该义务。非法模式混用仍阻断。 |
| **F03：事件与参考范围** | 事件保留点时刻，另有冻结 `reference_scope`。合法联合导出和编辑基图通过；扩大范围并重算用途审核后，lower／compile 阻断，旧导出复验拒绝，编辑基图报告范围不匹配。 |
| **FAIL 返修** | 合成四秒媒体的项目 `500–1500 ms` 失败生成执行核查任务；源包、评价基线和正确输入用途不变，没有强迫修改上游设计。 |

这些是**本轮重新取得回执的范围**，不是继承上一轮通过数。原 B01 的完整时轴矩阵、原 N03/N04 媒体和浏览器标签矩阵，本轮未重放。

## 五、PR1–PR6 的证据边界审计

以下区分“本轮软件运行”“仓库中已有实验记录”和“最终制作效果”。

| 阶段 | 当前证据能支持什么 | 仍未达到或本轮未验证的边界 |
|---|---|---|
| **PR1：基线与能力** | 精确提交、源码摘要、原生合同及选定模式／义务检查有本轮执行证据；AVIR 单一权威保留。 | 未探测全部模型入口、账户和预算；能力注册不等于账户可用。 |
| **PR2：调度与投影** | 制作包及派生文件能被当前消费者验证；已有三视图与几何相关实现。 | 本轮没有浏览器视觉、移动端、密集标签或完整骨架／碰撞／遮挡验收。 |
| **PR3：图片生产合同** | 冻结、接收、编辑差量与类型边界通过软件测试。 | 仓库实际图片构图记录仍为 FAIL；原图不在仓库，本轮未查看或重新测量。不能用合成 PASS 代替构图达标。 |
| **PR4：控制资产与后端交接** | 正文、参数、附件索引、来源和主执行义务的联合编译已有本轮运行证据。 | Blender 本轮未复跑；商业首尾帧执行门仍未过，包括确认可用入口、预算、上传、请求及实收。 |
| **PR5：观察与返修** | 本轮 FAIL 返修保留正确输入和项目时间；局部任务机制可运行。 | 合成 findings 不等于真实测量；真实媒体返修后的质量闭环仍需验收。 |
| **PR6：专用实验** | 仓库已有 VACE 固定运行器／权重锁、工作流、执行与成本记录，不再是“尚未开展的空占位”。 | 本轮只核对记录，未执行 VACE、下载权重或观看公开视频；记录仍为质量 FAIL，控制收益未成立，通用生产适配未集成。 |

仓库图片记录明确保留了原验收目标、手工估计误差、FAIL／UNDETERMINED 及“原图不在仓库”的限制；本轮没有据此声称看过图片。

VACE 材料包含固定源码与三份权重的 revision／摘要；CPU 视频记录为执行成功但质量 FAIL，而且没有控制输入。其耗时、帧数、商业费用等是**读到的作者实验记录，不是本轮测量**。

**PR6 的失败实验可以构成实验交付，不需要反复抽样“制造 PASS”；但实验完成、产品适配完成和控制收益成立，仍是三个不同结论。**

## 六、未运行项与复跑方式

本轮未执行 185 项发行测试全集、全源码 `discover`、七个正式 Skill 的静态／隔离安装／嵌入一致性／重复构建、图片 Skill 的独立完整运行、浏览器、Blender、VACE 或商业视频调用。没有将作者这些项目的 PASS 计入本轮。

解压证据包，在其根目录执行：

```bash
python reproduce_all.py --out /absolute/path/to/new-ac65dd8-audit
```

入口先校验源码 blob，再运行本轮测试和审计脚本。所有子步骤本轮均已执行；整合入口完成语法检查，未另外做一次全套重复运行。`prior/` 中保存的是原反例输入，不计为本轮回执；本轮结果集中在 `evidence/`。

**最终决定：Approve 本次 `ac65dd8` 软件补丁；C02／P2 在受测范围关闭。完整方案仍未最终交付，但缺少真实入口和质量证据，不构成否定这次类型修复的理由。**
