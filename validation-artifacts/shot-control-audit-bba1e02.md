# bba1e02 局部实收与返修功能审核

## 结论

审查对象：`jinbaozi/ai-video-preproduction@bba1e02ce54d7e27145a683e4ae747bfa2637f8a`。
父提交：`b83f6ac5dec08ac9f261928157fcedfdbc50337c`。
提交标题：`Review generated clips against scoped project time and preserve source on output failure`。

补丁结论：**Request changes**。局部项目时轴、相邻切点归属和保留输入的 FAIL 返修通过本轮正反例；视频流覆盖区间仍有一个 P1 功能缺口，两个独立媒体反例复现。
整体方案：**本次不构成完整交付验收**。原 F01–F03 的完整链路没有在本轮复测，不能标为关闭。

## 运行范围与证据

通过 GitHub 连接器查询精确 SHA。容器无法解析 codeload.github.com，因此没有完整克隆；按当前 Git blob 摘要恢复并校验运行子集。21 个源码、模板和 Schema 文件逐字节匹配，见 `evidence/source-integrity.json`。测试没有修改产品实现、放宽原生 Schema 或 mock FFmpeg/ffprobe。

已阅读当前 `media_review.py`、`repair.py`、`control-media-review.schema.json`、`test_control_repair.py`。执行的是本次独立编写的测试，不把作者测试记录或对源码的阅读计作测试通过。

审计自建完整原生 AVIR 1.2：12 秒、3 个四秒镜头、两个成年人物；有实际来源文件摘要、人物与场景、原生合同、动作状态变化、空间轨道、构图、相机操作、语义审查夹具以及真实本地 PNG 身份输入。它不是仓库 cafe.avir.json 的逐字节复刻。经当前 `validate_source → build → verify_package` 进入，得到 123 个预览状态、10 个关键帧请求、240 个冻结评价样本。

编码了真实 3/4/12 秒 MP4 和两种边界 MP4。所有观测坐标、视觉 findings、身份 PASS 记录是合成软件测试数据，不是对 MP4 的实际模型质量判断，不是作者 VACE 的观测结果。

**42 项独立断言：40 项满足预期，2 项未满足，归并为同一缺陷。** 清理运行子集后完成一次全量重跑，结果相同。见 `evidence/clean-rerun-results.json` 和 `evidence/clean-rerun-run.log`。初次整合包装脚本受工具超时中断；随后对生成好的新工作目录重跑完整测试成功结束，结果为上述 42 项，未把中断计作产品缺陷。

另实际执行当前 CLI 的 `review` 命令复现 N01，退出码为 0。见 `evidence/cli-reproduction.json`。

## 已验证的行为

| 类别 | 独立结果 |
|---|---|
| S2 非零起点 | execution_range=4000–8000，offset=4000，shot_ids=[S2]；局部 80 个期待样本，全项目仍为 240；complete_project_scope=false |
| 切点归属 | S2 包含 CAM_S2:start/end，不包含 CAM_S1:end、CAM_S3:start；错误侧事件被拒绝 |
| 原全片路径 | 不填 execution_range 的真实 12 秒 MP4 可评估；4 秒文件冒用默认 12 秒路径被拒绝 |
| 错误输入 | 3 秒文件、错基线、错媒体摘要、倒序/空/越界执行范围、误填局部时间、范围外点/事件、重复点/事件、越界 findings 被拒绝 |
| 基线隔离 | 观察者不能提交 planned_points 或 width/height；删除测量不缩小期待样本分母；缺失事件保留 null |
| FAIL 返修 | 项目 4500–5500 的失败生成一个 external-runner 任务和输出失效记录；scope 保持 4500–5500；所有原输入用途保留，输入无失效；源文件、冻结基线、原资产清单和 PNG 哈希不变 |
| PASS/UNDETERMINED finding | 不自动生成失败返修任务；评价状态不冒称质量 PASS |

## R1 — P1：使用容器时长代替视频流时轴，接受无画面的测量时段

### 精确位置（上述 SHA）

- `video-prompt-compiler/scripts/shot_control/media_probe.py:18–22,38–43`：选中视频流，但 duration 来自 `format.duration`；没有输出该流的起始 PTS 和结束区间。
- `video-prompt-compiler/scripts/shot_control/media_review.py:33–43,47–54,73–79`：时长一致性、样本边界、事件和 finding 范围均依赖上述容器时长。

### 有效前置

完整原生十二秒项目已通过 build/verify，基线未修改。S2 执行范围为 4000–8000。对照文件为 320×180、24 fps、96 帧、视频流 0–4 秒的 MP4；该对照评估通过。

### 最小复现

1. 保持同一冻结包和 execution_range。
2. 制作有效 MP4：视频流只有 1 秒/24 帧，音频流 4 秒；容器时长 4 秒。
3. 使用这个文件的真实 SHA-256，提交 S2 原冻结采样时刻的合成测量，包括项目 7900 ms（本地 3900 ms）。
4. 调用 `evaluate()` 或当前 CLI `review`。

进一步反例：视频流从媒体 2 秒才开始，共 2 秒/48 帧，音频覆盖 0–4 秒。相同路径也接受位于本地 0 秒的测量。

实际 ffprobe 独立输出见 `evidence/stream-probes/*.json`。

| 探针 | 视频起点 | 视频时长/帧数 | 音频/容器时长 | 实际结果 |
|---|---:|---:|---:|---|
| N01 | 0 秒 | 1 秒 / 24 帧 | 4 秒 | 接受 |
| N02 | 2 秒 | 2 秒 / 48 帧 | 4 秒 | 接受 |

两次均返回 `OBSERVATIONS_RECORDED`，`coverage=1`、`mean_error=0`、S2 起止事件误差为零；`complete_project_scope=false` 仍正确。N01 的 CLI 退出码为 0。

这不是产品返回整片“质量 PASS”的问题，也不是说测试视频符合计划。错误是：没有相应编码帧、也没有冻结的延时/持帧映射的时段，被当成有效观测证据；零误差来自故意复制计划点的合成测量。

### 预期

在当前恒等片段映射下拒绝上述媒体，或显式报告视频时轴缺口并拒绝缺口内观测。不得用较长的音频或播放器隐式持帧充当已验证视频覆盖。

### 修复建议

分开记录容器元数据和选中视频流的起止时间、时间基准、可解码帧时间戳及呈现区间。以视频流的实际覆盖验证 execution_range 和每个测量位置；PTS 归零、留白、延时或持帧需要显式映射，不自动猜测。不增加第二套轨迹 IR；仍用原 AVIR 作为期待基线。

### 验收门

- 正常 4 秒 S2 和旧 12 秒全片继续通过。
- 视频短于音频、视频延后开始、视频帧区间存在缺口的用例不能取得完整有效观测。
- 明确支持的时间映射按声明处理，不允许静默补帧、拉伸或推断持帧。
- 失败路径仍保留原基线和正确输入，不自动改写上游。

## 未验证与交付边界

未运行仓库全部测试和七个正式 Skill 的隔离安装/内置一致性/重复构建；未重跑原 F01–F03 的完整跨消费者链；未运行 Blender 或图片/视频模型；未观看或重测 experiments/vace 的原视频与八张抽帧。不能根据作者验证摘要或摘要中的媒体质量结论为这些事项背书。

本轮只对局部实收评价和对应返修作功能结论。真实生成收益、完整交付、通用专用后端以及其他生产流程仍需分别验收。

## 重跑

依赖 Python 3、jsonschema、Pillow、ffmpeg/ffprobe（包含 libx264）。解压后运行：

```bash
python run_all.py --workdir /tmp/bba1e02-fresh-audit
```

必须指定新的工作目录。该脚本重新创建原生源、媒体和输出。在此 SHA 上预期是 42 项断言、40 项通过、N01/N02 失败并退出 1。这里的退出 1 表示审计发现问题，不是测试工具崩溃。没有网络或模型请求。
