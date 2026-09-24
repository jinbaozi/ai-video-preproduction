# 05e0e4b 视频时轴功能对抗审核

## 结论

固定提交：`05e0e4ba88cc51061fb0b787d54a13698ade39ef`。
父提交：`2e34a9f713fbdc031cbe27fb7d2867a76ec16e8f`。
提交标题：`Validate observed video coverage against decoded frame timelines`。

**补丁意见：Request changes。原 R1 的 N01/N02 漏放反例已被当前实现拒绝，但新增测试复现 1 类 P2：合法 1 ms 时间戳量化被二进制浮点误差误判为超限缺口。**

没有把作者 PASS 计作审计执行，没有推定旧 F01–F03 已关闭。本次不是整体方案交付验收。

## 独立执行与来源

通过 GitHub 连接器查询精确 SHA 和源文件。容器无法解析 codeload.github.com，未取得完整仓库；运行的是 **21 文件源码子集**。已有字节与当前 Git tree 的 blob ID 比较，新获取的两个文件也通过 Git blob SHA-1 检查；没有修改产品验证逻辑、模拟 ffprobe 或放宽 Schema。

当前 scripts tree：`a616c218d8774c0d702cced0b7f554181b007d82`。
当前 schemas tree：`6e2d39e947191febeafaec62aadc257afb8b66a4`。
目标 media_probe.py blob：`3b90be74c7d93329d9925b0be96d7fb5f2d8e0e6`。
目标 media_review.py blob：`d8c8d49ae8bcc450880252ba1ea1d3144d8333c9`。

上一轮原样保留的四个脚本为 run_all.py、native_fixture.py、scoped_fixture.py、run_scoped_tests.py。分别生成完整原生 AVIR 1.2 和真实媒体，执行 validate_source → build → verify。项目为 12 秒、三个 4 秒镜头、两个角色，有源文件、身份 PNG 和原生绑定；得到 123 个预览状态、10 个关键帧请求、240 个评价样本。不是简化或无效的手写 lower 输入。

- 原 42 项：42/42，通过。
- 新增 21 项：19 项通过；N03、N04 两项失败，属于同一缺陷。
- 总计 63 项独立断言：61 项通过，2 项失败。
- 另运行 CLI 复现、严格解码和精确时间算术检查，不把这些重复计入上述 63 项。

环境：Python 3.13.5，FFmpeg/ffprobe 7.1.5-0+deb13u1，jsonschema 4.26.0。所有新媒体均由本地 FFmpeg 编码；观测坐标和视觉 findings 是合成合同数据，不是模型成片服从证据。

## 通过的回归和边界

1. 原样 42 项，包括非零起点 S2、切点事件、局部/全片标记、错误时长/越界/错误基线/局部时刻误填、FAIL 返修与输入保留。
2. 上轮档案中的两份原始 MP4 也逐个重放：N01 返回 `Media duration differs from frozen time map`；N02 返回 `Video starts outside the frozen zero-based media clock`。
3. MKV 缺一帧形成的帧间缺口拒绝；95 帧短尾和 97 帧长尾拒绝。
4. faststart MP4 保留头部后截断像素数据，返回 `Video decode failed`；不是仅凭容器信息通过。
5. 4 秒完整视频与 6 秒音频同封装时通过，保留容器 6000 ms 和视频 4000 ms、96 帧的区别。
6. 第一视频流短、第二视频流长时拒绝；第一视频流完整、第二视频流短时通过，不用后者补前者。
7. 4 秒 MKV 的 24/25/30/50/60 fps 正例通过；12 秒 24 fps MKV 旧全片路径通过。
8. 24 fps MKV 的实际量化末端 3999 ms 映射到 S2 结束 8000 ms，合法 end 事件与端点 FAIL finding 均保留；返修先核对执行，不修改原 AVIR 或失效正确身份图。

## B01 · P2：精确 1 ms 量化被 float 误差误判为超限

### 精确位置

`video-prompt-compiler/scripts/shot_control/media_probe.py:25–33`。
连带调用：`video-prompt-compiler/scripts/shot_control/media_review.py:42`；同文件 44、56 行的端点比较也建议使用相同时间表示，后两处本轮未独立认定为已复现缺陷。

### 有效前置

上文完整 12 秒原生包经 validate_source/build/verify，通过。第一反例使用旧全片观察路径，未提供 execution_range，不修改基线摘要或原生 AVIR。第二反例仅声明范围 4000–8004 ms，仍使用同一项目和基线。

### 最小复现

在已建包上生成普通 MKV：

```bash
ffmpeg -v error -f lavfi -i 'testsrc2=s=320x180:r=30:d=12' \
  -c:v ffv1 -threads 1 -pix_fmt yuv420p normal-30-12s.mkv
```

创建一个合法全片 review，使用该文件真实 SHA-256 和原冻结 evaluation-plan 的 digest；可以使用空 observed_points/events/findings，因为缺观测应记为缺失，不构成拒绝媒体的理由。调用 evaluate 或 control_cli.py review。

实际 CLI 返回码 1：

```json
{"status":"ERROR","message":"Video frame timeline has gaps or overlaps"}
```

无需生成异常视频、篡改媒体或模拟 FFmpeg。

### 两份媒体证据

| 反例 | 帧数/精确起止 | 严格解码 | 原始时间值 | 精确间隙 | 产品 float 间隙 |
|---|---|---|---|---|---|
| N03：30 fps、12 秒 MKV | 360 帧，0–12000 ms | 退出 0，stderr 空 | 前帧 8.033000 s，持续 0.033000 s；下一帧 8.067000 s | 1.000000 ms | 1.0000000000009095 ms |
| N04：24000/1001 fps、4.004 秒 MKV | 96 帧，0–4003 ms；目标 4004 ms | 退出 0，stderr 空 | 前帧 2.002000 s，持续 0.041000 s；下一帧 2.044000 s | 1.000000 ms | 1.0000000000002274 ms |

两份文件的所有相邻间隙，用原始 ffprobe 字符串经 Decimal 计算，均不超过 1 ms。第二份的末端也处在规定的 1 ms 量化容差内。严格像素解码通过。

### 实际与预期

实际：合法量化文件在 video_timeline() 抛 ValueError，无法记录观察或进入后续返修。

预期：符合 <=1 ms 量化合同的文件继续评价；missing/FAIL/UNDETERMINED 仍按原规则记录。不接受大于 1 ms 的真实缺口，不补帧或拉伸。

### 建议与验收门

以有理数或整数时间基保存 PTS 和 duration：优先读取原始整数时间戳与 time_base，通过 Fraction 比较；采用已有十进制时间字符串时，可用 Decimal/Fraction 做精确比较。只在展示或输出中转换 float。帧间、零点、末端和采样边界应共用这套时间算术。

不要将容差从 1 ms 扩大到 1.1/2 ms 掩盖问题，也不要对每帧独立取整导致累计误差。保持既定阈值。

验收门：N03/N04 通过；精确 1 ms 在不同绝对时点结果一致；大于 1 ms 的间隙/重叠仍拒绝；原 42 项和短尾、截断、长音轨、第一视频流选择、FAIL 输入保留全部保持通过。

## 未运行与整体边界

没有运行作者的 13 项仓库专项或 176 项全量测试；虽然阅读了当前 test_control_repair.py，但上述统计来自独立脚本。未运行七个正式 Skill 发行包检查，也未运行 Blender、VACE 或其他模型。

旧 F01–F03 的 stage→receive→联合编译、范围与编辑基图等跨消费者链路未在本轮执行，仍是本轮未验证项，不宣告关闭。

未查看 CPU baseline/shift 的原视频或抽帧，用户给出的质量 FAIL 是作者实验说明，不是本轮观察。没有新增通过的关键帧、视频控制收益或完整方案交付结论。

## 证据索引

- evidence/source-integrity.json：21 文件当前 Git blob 摘要。
- evidence/test-script-integrity.json：原样四脚本摘要。
- run42/evidence/results.json 与 run42/evidence/run.log：原 42 项运行。
- supplemental/results.json、commands.json、reviews/、results/：21 项补测。
- supplemental/metadata/：真实逐帧和流元数据。
- supplemental/float-boundary/：原始数值与 float 反例。
- evidence/exact-timing-check.json：两份有效 MKV 的严格解码和精确时间检查。
- evidence/cli-reproduction.json：CLI 退出 1 复现。
- inputs/original-media/：上一轮原始 N01/N02 媒体。

复跑命令见根目录 README.md。当前版本原 42 项应退出 0，补测应复现上述两个失败并退出 1。
