# 对抗性功能审核原始报告：a7b4072674fdd43d1ae8f12132c45d5d310480fb

## 1. 决策与适用范围

**Approve：接受本补丁的整数视频时轴及冻结投影基线修复，范围为本报告列出的独立测试。**

本轮没有发现可复现、需要阻断这两项修复验收的新功能缺陷。此结论不是全仓、七个正式 Skill 发行包、全部旧问题或真实生成质量的验收。

- 仓库：jinbaozi/ai-video-preproduction。
- 精确提交：a7b4072674fdd43d1ae8f12132c45d5d310480fb。
- 父提交：05e0e4ba88cc51061fb0b787d54a13698ade39ef。
- 标题：Preserve exact video timing and frozen projection baselines。
- Git tree：de040c94441e6af93e9be095ddc7231e120e44f2。

以上来自 GitHub 连接器的精确提交查询。本轮未以 main 作为源码引用。作者的 181 项测试、七包安装及质量实验记录不计入本报告的执行结果。

## 2. 运行环境、源码与前置合同

执行源是 32 个文件组成的源码依赖子集，不是全仓克隆或 .skill 归档。容器网络不能下载 GitHub 仓库，使用连接器取得当前源码／变更，结合已存档、相同 Git blob 的文件重建工作副本，并校验完整文件 Git blob SHA-1。没有删除被测函数、放宽 Schema、替换 ffprobe 或模拟目标函数返回。

`evidence/source-integrity.json` 保存 32 个文件的期望／实际 Git blob、SHA-256 和字节数。`evidence/test-script-integrity.json` 保存原四个脚本的逐字节一致性。环境的 Python、平台、FFmpeg 和 ffprobe 版本见 `evidence/environment.json`。

主夹具为审计方编写的完整 AVIR 1.2：十二秒、三个四秒镜头、两个角色，具有原生合同、来源文件摘要、动作／状态、空间轨道、构图及本地身份 PNG。经当前 `validate_source → build → verify`，生成 123 个预览状态、10 个关键帧请求、240 个评价样本。另一个宿主夹具为八秒双镜头，具有两份身份、场景母版及编辑基图的原生绑定，也经过相同构建／验证前置。

MP4/MKV 是实际媒体文件；用于合同检查的观测坐标、审核声明、宿主回执及 HTTPS 上传记录是合成夹具。零误差和 PASS 不证明生成模型达标。没有读取账户密钥或调用付费模型。

## 3. 独立执行统计

| 集合 | 断言／重放项 | 通过 | 未通过 |
|---|---:|---:|---:|
| 上轮原四脚本中的 42 项 | 42 | 42 | 0 |
| 上轮原 supplemental 脚本 | 21 | 21 | 0 |
| 原 N03/N04 原包原观察重放、字节不变及窄容差 | 27 | 27 | 0 |
| 新增精确时轴边界 | 6 | 6 | 0 |
| 宿主 stage／receive／lower 和参考范围 | 22 | 22 | 0 |
| 隔离图片侧进程一致性 | 2 | 2 | 0 |
| 预演事件配方和视频计划预检 | 2 | 2 | 0 |
| **合计** | **122** | **122** | **0** |

统计包含同一场景在原脚本、原始文件、隔离消费者中的重放，不等同于仓库有 122 个新 unit test。逐项原始结果列于文末及 CASE-RESULTS.md；JSON 和命令日志在相应证据目录。

## 4. B01 原反例原样重放

使用上轮 ZIP 内未改写的制作包、N03/N04 媒体和 observations，不重新生成这些输入。

| 原例 | 实测视频时轴 | 原执行范围 | 结果 |
|---|---|---|---|
| N03：normal-30-12s.mkv | 360 帧，time_base=1/1000，末端精确值 12000 ms | 0–12000 ms；旧全片路径 | OBSERVATIONS_RECORDED |
| N04：normal-24000_1001.mkv | 96 帧，time_base=1/1000，末端精确值 4003 ms | 4000–8004 ms；末端量化误差 1 ms | OBSERVATIONS_RECORDED |

两份原观察的评价基线摘要均保持：

`1aa16a28ef1427a2af76af215c5cfbe22756c66514b585e8c50105774148262d`

原媒体 SHA-256：

- N03：`d729a37fd6912d791d30d83f17f93452897a39b84e98ce786cf4e68a95139329`。
- N04：`c66322b4bf50be4ef8041fe8ce2b6c783a5a93235d040b7bf4cdefe685feb793`。

本轮在调用前后对原制作包全部文件、观察和媒体逐一比较 SHA-256，未发现变化。对应证据为 `numeric/results/ORIGINAL_*.json` 与 `UNMODIFIED_*.json`。

**B01 可以在上述复现范围内关闭。** 接受依据不是作者报告，而是原包原文件和原观察在当前运行时的执行结果。

## 5. 时轴负例与边界

源码定位：

- `video-prompt-compiler/scripts/shot_control/media_probe.py:9–52`：完整解码第一视频流，读取整数 best_effort_timestamp、duration/pkt_duration 与 time_base；使用 Fraction 核对间隔与零点。
- `video-prompt-compiler/scripts/shot_control/media_review.py:43–48,57–59,79–85`：用精确视频末端及项目时间检查总长、样本、事件及 findings。

独立执行包括原 N01/N02、缺帧、短尾、额外尾帧、截断像素、多个视频流、长音轨、普通 MKV 帧率和旧十二秒路径。结果符合预期：短第一视频流不能被长音轨或第二视频流补足，完整四秒画面配六秒音轨则可以进入四秒片段评价。

新增 EBML 边界夹具在正常 MKV 上修改显示时间码，并重算 Cluster CRC；不改编码像素负载。保留全部原始编辑记录和 ffprobe 时钟结果。

| 边界 | 预期 | 实际 |
|---|---|---|
| 局部帧时间戳向后移 4 ms，首个违规相邻间隙为 5 ms | 拒绝 | gaps or overlaps |
| 局部帧时间戳向前移 4 ms，首个违规相邻重叠为 3 ms | 拒绝 | gaps or overlaps |
| 视频从 2 ms 开始 | 拒绝 | starts outside frozen zero-based clock |
| 视频从 1 ms 开始，末端为 4000 ms | 接受量化边界 | 接受 |
| 四秒视频对应 4001 ms 执行长度 | 接受 1 ms 边界 | 接受 |
| 四秒视频对应 4001.001 ms 执行长度 | 拒绝 | duration differs |

MKV 量化末端的合法 end 事件和 FAIL finding 可保留在项目 8000 ms。FAIL 返修保持项目时刻及正确输入，没有为输出失败改写 AVIR。

## 6. 8 ULP 容差挑战

源码定位：

- `package.py:10–30`：只对派生点投影 xy／depth 作 ULP 比较。
- `package.py:94–118`：文件集合、文件 SHA、原生源和派生结构检查。
- `package.py:119–136`：返回文件中已验证的生产端数值，以其重建评价与审阅文件核验值。
- `package.py:139–151`：在冻结采样时刻，recipe 消费传入的冻结帧；其他时刻按原规则求值。

测试做法：从完整 build 产物复制生产端差异样本，只改变选定投影值，并使该样本的评价 JSON、审阅 HTML/SVG 和包清单一致。该操作模拟生产端浮点表示差异，不是假称执行了另一台机器的 libm。负例再分别修改其他字段或超出 ULP 边界。

| 测试 | 实际结果 |
|---|---|
| xy/depth 的 +1、+8、−8 ULP | 验包接受，返回冻结值 |
| xy/depth 的 +9、−9 ULP | 拒绝 |
| xy 增加 0.00001 | 拒绝 |
| 世界位置或时间改变 1 ULP | 拒绝 |
| projection status、节点 ID、帧数、坐标维数、追加机位字段 | 拒绝 |
| projection.xy 填 boolean | 拒绝 |
| 1 ULP 修改但不更新清单摘要 | 文件哈希检查拒绝 |
| 冻结值与本地重算值不同的 recipe | 使用冻结帧的 recipe 与生产端一致；与未传冻结帧的重算 recipe 不同 |
| 相同已验包前后执行 repair | UNCHANGED，没有产生资产失效 |

受测范围内，容差没有扩散到时间、世界位置、状态或结构，也没有写回原文件、替换原评价摘要。没有将“重封清单”等同于签名验证：本机制检验一致性，不认证作者身份。

未测试全部浮点数域、所有相机退化构型或真实双平台 libm 矩阵；不对非冻结采样时点宣称逐位跨平台一致。

## 7. 跨消费者补验与旧 F01–F03 状态

### 7.1 宿主输入与接收

在具有 1 ULP 生产端差异的有效原生包上完成：

`build → verify → keyframe-check → stage → verify-stage → receive → verify-received → lower`

测试包括 FAIL 的 clean_keyframe 作为独立编辑基图、基图先于三张主参考、输入哈希顺序错误、审核缺项，以及 NOT_RUN/PASS/FAIL/UNDETERMINED 的区分。下游 lower 对 FAIL、未审和 UNDETERMINED 维持阻断。

原 no_idat、bad_idat、zeros_idat 三份 PNG 的字节来自此前审核证据，分别进入同一有效 stage 的 receive 后被拒绝。没有把脚本异常或元数据类型错误当作像素质量成功。

### 7.2 keyframe_input 与 reference_scope

三张图片宿主母版使用 keyframe_input，原 AVIR assets/bindings 不删除。实收 K 在 keyframe 模式下成为唯一视频附件；母版不占视频数组或预算。显式 first_frame 改走 reference 模式仍被阻断。

普通事件参考在冻结配置中声明 S1 的 0–4000 ms reference_scope。事件本身仍为 start_ms=end_ms=0。stage/receive 后的 lower 接受对应范围；缺 scope 在宿主执行前拒绝；扩到 8000 ms 的用途被 lower 阻断。

编辑基图的范围测试有有效正例：修订请求的基图 SHA 与实收文件一致，正常清单先通过，再改变 reference_scope；负例唯一原因是 `ANCHOR_REFERENCE_SCOPE_MISMATCH:K`。因此不是由错误路径或旧基图摘要制造的无关失败。

**没有运行完整联合编译。** F02 的正文／参数／来源映射与实际提交索引的最终联合合同，以及原生 reference 义务的完整路径，仍未在本轮验收。F03 也不据本轮选定范围测试宣称全部旧边界关闭。

### 7.3 图片侧隔离和预演

复制同源依赖子集到不含兄弟视频目录的图片侧位置，清除 PYTHONPATH 后，通过 CLI 对原 N03/N04 各运行一次；两份 JSON 评价结果与视频侧结果相等。这不是正式 .skill 安装测试。

预演部分完成原生 AVIR 配置的 build/verify、S2 单事件计划和 96 帧视频计划推导。事件注册用的 recipe 与冻结帧基准一致。未运行 Blender、未生成场景渲染帧，不能将这两项预检解释为真实渲染验收。

## 8. 未执行项目

1. 当前仓库的 181 项全量、七个正式 Skill 安装、嵌入一致性和重复构建。
2. stage→receive→完整 joint_compile，以及所有原生 reference、参数与正文的联合验证。
3. Blender opt-in 集成、实际像素渲染及 Blender 回读。
4. VACE/CPU/shift 实验或任何新生成模型任务。
5. 全部旧 F01–F03 场景、全部数值域、真实双平台 libm 对照。

不把缺少运行证据算作产品失败，也不把作者 PASS 转为本轮测试结果。本轮没有新增通过的关键帧、视频画质或控制收益声明。

## 9. 可重跑入口与证据目录

依赖：Python、jsonschema、referencing、Pillow、系统 FFmpeg/ffprobe。无需 API 密钥，不提交模型请求。

```bash
python reproduce_all.py --out /absolute/path/to/new-audit-run
```

入口创建新工作目录、复制已核对的目标源子集，重跑原 42 项、原 supplemental 21 项及本轮新增测试。期待 122/122；实际输出、环境差异和失败均保存在新目录。已生成目录不应覆盖复用。

- `evidence/summary.json`：本轮统计与未运行边界。
- `evidence/source-integrity.json`：32 个文件的 Git blob/SHA-256。
- `evidence/test-script-integrity.json`：原脚本一致性。
- `numeric/results/UNMODIFIED_*.json`：原包、原媒体和原观察前后摘要。
- `run42/`、`supplemental/`：原脚本的本轮运行结果。
- `numeric/`：ULP 边界与配方基准。
- `timing-edges/`：合法 EBML 时间码变体、CRC 重算和精确时钟。
- `host/`：宿主原生夹具、冻结输入、接收包、审核、范围及 lower 结果。
- `isolation/`：隔离图片侧 CLI 与相等性结果。
- `previs-preflight/`：事件／视频预演计划，明确 rendering=NOT_RUN。
- `previous/`：重放所需的上一轮原始输入和脚本。

附加测试开发期间出现过两个审计夹具问题：首版 FFmpeg 变时基媒体未携带帧 duration，改用正常 MKV 的 EBML 时间码变体；首版编辑范围负例把清单放错相对路径，最终运行补入有效正例并校正路径。它们未计入产品缺陷或最终通过数。两次受执行超时中止的跑次也未纳入最终统计。

## 10. 最终意见

**Approve，范围为本次整数时轴及冻结投影基线修复和报告中的受测消费者路径。** B01 两份原始媒体与观察通过，1 ms 门槛没有被扩大，超过门槛的媒体继续被拒绝，冻结投影容差在本轮反例中没有泄漏到其他字段或改写评价基线。

**完整方案仍未交付。** 本补丁的功能验收不替代完整联合编译、正式分发、真实渲染和生成控制收益的验收。

---

# 逐项用例原始结果索引

## original42

| Case | Result | Expected/actual rejection |
|---|---|---|
| P01_S2_nonzero_offset | PASS |  |
| P02_S1 | PASS |  |
| P03_S3 | PASS |  |
| P04_old_whole_project | PASS |  |
| P05_cut_event_membership | PASS |  |
| P06_no_observations_not_pass | PASS |  |
| P07_missing_denominator | PASS |  |
| P08_occluded | PASS |  |
| P08_tracking_failed | PASS |  |
| R01_missing_range_4s_vs12s | PASS | Media duration differs from frozen time map |
| R02_bad_range_0 | PASS | Invalid execution range in frozen project time |
| R02_bad_range_1 | PASS | Invalid execution range in frozen project time |
| R02_bad_range_2 | PASS | ['execution_range', 'start_ms']: -1 is less than the minimum of 0 |
| R02_bad_range_3 | PASS | Invalid execution range in frozen project time |
| R02_bad_range_4 | PASS | Media duration differs from frozen time map |
| R03_wrong_duration_3s | PASS | Media duration differs from frozen time map |
| R04_wrong_baseline | PASS | Evaluation plan mismatch |
| R05_wrong_media_hash | PASS | Observed media hash mismatch |
| R06_local_point_times | PASS | Duplicate or unmatched observation; time warping is not allowed |
| R07_local_event_times | PASS | Event outside video |
| R08_outside_S1_point | PASS | Duplicate or unmatched observation; time warping is not allowed |
| R09_outside_S3_point | PASS | Duplicate or unmatched observation; time warping is not allowed |
| R10_wrong_cut_shot_id | PASS | Duplicate or unmatched observation; time warping is not allowed |
| R11_cut_and_event_0 | PASS | Duplicate or unmatched event |
| R11_cut_and_event_1 | PASS | Duplicate or unmatched event |
| R11_cut_and_event_2 | PASS | Event outside video |
| R11_cut_and_event_3 | PASS | Event outside video |
| R12_duplicate_point | PASS | Duplicate or unmatched observation; time warping is not allowed |
| R13_duplicate_event | PASS | Duplicate or unmatched event |
| R14_review_cannot_supply_expected | PASS | []: Additional properties are not allowed ('planned_points' was unexpected) |
| R15_review_cannot_supply_dimensions | PASS | []: Additional properties are not allowed ('height', 'width' were unexpected) |
| R16_local_finding_times | PASS | Finding outside video |
| R17_outside_finding | PASS | Finding outside video |
| R18_reversed_finding | PASS | Finding outside video |
| R19_nonexistent_pointer | PASS | list index out of range |
| P09_FAIL_scoped_repair | PASS |  |
| P10_FAIL_repair_export | PASS |  |
| P11_no_repair_PASS | PASS |  |
| P11_no_repair_UNDETERMINED | PASS |  |
| P12_inputs_unchanged | PASS |  |
| N01_container_duration_masks_short_video | PASS | Media duration differs from frozen time map |
| N02_delayed_video | PASS | Video starts outside the frozen zero-based media clock |

## originalSupplemental21

| Case | Result | Expected/actual rejection |
|---|---|---|
| S01_original_N01 | PASS | Media duration differs from frozen time map |
| S02_original_N02 | PASS | Video starts outside the frozen zero-based media clock |
| S03_MKV24_quantized_end | PASS |  |
| S04_one_frame_gap | PASS | Video frame timeline has gaps or overlaps |
| S05_short_last_frame | PASS | Media duration differs from frozen time map |
| S06_extra_last_frame | PASS | Media duration differs from frozen time map |
| S07_truncated_pixels | PASS | Video decode failed: [h264 @ 0x5627c1f12ac0] Invalid NAL unit size (1711 > 1101). [h264 @ 0x5627c1f12ac0] missing picture in access unit with size 1105 [in#0/mov,mp4,m4a,3gp,3g2,mj2 @ 0x5627c1e5cfc0] corrupt input packet in stream 0 [in#0/mov,mp4,m4a,3gp,3g2,mj2 @ 0x5627c1e5cfc0] Task finished with error code: -1094995529 (Invalid data found when processing input) [in#0/mov,mp4,m4a,3gp,3g2,mj2 @ 0x5627c1e5cfc0] Terminating thread with return code -1094995529 (Invalid data found when processing input)  |
| S08_full_video_long_audio | PASS |  |
| S09_container_and_video_separate | PASS |  |
| S10_MKV_25 | PASS |  |
| S10_MKV_30 | PASS |  |
| S10_MKV_50 | PASS |  |
| S10_MKV_60 | PASS |  |
| S11_MKV24_full_project | PASS |  |
| S12_first-short | PASS | Media duration differs from frozen time map |
| S12_first-full | PASS |  |
| S13_MKV_endpoint_FAIL_repair | PASS |  |
| S14_MKV_FAIL_export | PASS |  |
| N03_MKV30_12s_exact_1ms | PASS |  |
| N04_MKV23976_exact_1ms | PASS |  |
| S15_inputs_remain_unchanged | PASS |  |

## numericAndOriginalReplay

| Case | Result | Expected/actual rejection |
|---|---|---|
| ORIGINAL_N03_MKV30_12s_exact_1ms | PASS |  |
| UNMODIFIED_N03_MKV30_12s_exact_1ms | PASS |  |
| ORIGINAL_N04_MKV23976_exact_1ms | PASS |  |
| UNMODIFIED_N04_MKV23976_exact_1ms | PASS |  |
| xy_1ulp | PASS |  |
| depth_1ulp | PASS |  |
| xy_8ulp | PASS |  |
| depth_8ulp | PASS |  |
| xy_9ulp | PASS | Derived data mismatch: review/frames.json |
| depth_9ulp | PASS | Derived data mismatch: review/frames.json |
| xy_-8ulp | PASS |  |
| depth_-8ulp | PASS |  |
| xy_-9ulp | PASS | Derived data mismatch: review/frames.json |
| depth_-9ulp | PASS | Derived data mismatch: review/frames.json |
| world_position_1ulp | PASS | Derived data mismatch: review/frames.json |
| time_1ulp | PASS | Derived data mismatch: review/frames.json |
| projection_meaningful | PASS | Derived data mismatch: review/frames.json |
| projection_status | PASS | Derived data mismatch: review/frames.json |
| projection_shape | PASS | Derived data mismatch: review/frames.json |
| world_shape | PASS | Derived data mismatch: review/frames.json |
| node_identity | PASS | Derived data mismatch: review/frames.json |
| camera_roll_add | PASS | Derived data mismatch: review/frames.json |
| missing_frame | PASS | Derived data mismatch: review/frames.json |
| projection_xy_boolean | PASS | Derived data mismatch: review/frames.json |
| hash_guard | PASS | Package changed: evaluation-plan.json |
| recipe_uses_frozen | PASS |  |
| same_package_repair_retains | PASS |  |

## exactTimeEdges

| Case | Result | Expected/actual rejection |
|---|---|---|
| T_gap4ms | PASS | Video frame timeline has gaps or overlaps |
| T_overlap4ms | PASS | Video frame timeline has gaps or overlaps |
| T_delay2ms | PASS | Video starts outside the frozen zero-based media clock |
| T_delay1ms | PASS |  |
| T_end_plus_1ms | PASS |  |
| T_end_plus_1_001ms | PASS | Media duration differs from frozen time map |

## hostStageReceiveLower

| Case | Result | Expected/actual rejection |
|---|---|---|
| H01_1ulp_stage | PASS |  |
| H02_received_NOT_RUN | PASS |  |
| H03_received_PASS | PASS |  |
| H03_received_FAIL | PASS |  |
| H03_received_UNDETERMINED | PASS |  |
| H04_lower_PASS | PASS |  |
| H04_lower_FAIL | PASS |  |
| H04_lower_UNDETERMINED | PASS |  |
| H04_lower_not_run | PASS |  |
| H05_mode_mixing_reject | PASS |  |
| H06_wrong_input_order | PASS | Host assertion differs from frozen stage, prompt or ordered inputs |
| H07_missing_review_criterion | PASS | Visual review must cover every frozen acceptance criterion in order |
| H08_reject_original_no_idat | PASS | Media has no positive video dimensions |
| H08_reject_original_bad_idat | PASS | Media probe failed: [png @ 0x560cd5327180] inflate returned error -3  |
| H08_reject_original_zeros_idat | PASS | Image decode failed: [png @ 0x55ee2544fa40] IEND without all image [vist#0:0/png @ 0x55ee25440e40] [dec:png @ 0x55ee25446fc0] Decoding error: Invalid data found when processing input [vist#0:0/png @ 0x55ee25440e40] [dec:png @ 0x55ee25446fc0] Error processing packet in decoder: Invalid data found when processing input [vist#0:0/png @ 0x55ee25440e40] [dec:png @ 0x55ee25446fc0] Task finished with error code: -1094995529 (Invalid data found when processing input) [vist#0:0/png @ 0x55ee25440e40] [dec:png @ 0x55ee25446fc0 |
| H09_event_stage | PASS |  |
| H10_event_receive | PASS |  |
| H11_event_scope_lower | PASS |  |
| H12_scope_expansion_lower | PASS |  |
| H13_valid_received_edit_base | PASS |  |
| H13_scope_expansion_edit_check | PASS |  |
| H14_missing_scope_preflight | PASS | Event image_reference output requires an explicit frozen reference scope containing its event |

## isolatedImage

| Case | Result | Expected/actual rejection |
|---|---|---|
| N03_MKV30_12s_exact_1ms | PASS |  |
| N04_MKV23976_exact_1ms | PASS |  |

## previsPreflight

| Case | Result | Expected/actual rejection |
|---|---|---|
| PR01_event_recipe_frozen | PASS |  |
| PR02_video_preflight | PASS |  |

