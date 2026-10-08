> 历史实施记录（0.20.0）。默认关闭方法路由及对应精简基准已由[0.20.1 工作流修复](workflow-repair.md)取代，不代表当前 studio 默认。

# V2.0 实现与验证记录

日期：2026-10-08。基线 `b195d583f30b3f62e4d76c8ab229fda741b73ff3`，开发分支 `V2.0`，工作流包 `0.20.0`。

## 验证范围

本次是软件开发与本地工程验收，没有调用收费媒体模型，没有生成或发布真实短剧。所有合成音视频、provider 状态、授权及语义观察夹具都标明为测试数据；它们验证程序，不证明创作质量。

| 检查 | 结果 |
|---|---|
| 工作流源码全量回归 | PASS，451 项（含 26 项 V2.0 专项） |
| V2.0 专项 | 26 项通过；包含真实本地音视频、预算并发、事务回滚、原任务回收、五镜门、对白局部变更和失败 Take 返工 |
| 共享脚本同步 | PASS，6 个共享入口一致 |
| 七技能资料可达性 | PASS，索引与链接闭合 |
| 视频编译知识库审计 | PASS |
| 原生 studio 前期闭环 | `--version v52 --studio` 返回 DELIVERED；真实视频 NOT_RUN |
| 七个 .skill 包构建 | BUILT，真实 SHA-256 与源代码对应 |
| 七包隔离测试与可重复构建 | PASS，7 包、59 条隔离命令；7 包重复构建字节一致 |
| wheel 构建与独立安装启动 | PASS，安装后默认 studio 返回 AWAITING_CURRENT_AGENT |
| 真实模型五镜与先导集 | NOT_RUN |
| Flow / 剪映原生 / 其他 AI 宿主实跑 | NOT_RUN |
| 实际发布 | NOT_RUN |

3 项需要实际 Blender 环境的渲染测试按条件跳过：`test_previs.py` 两项、`test_adaptive_control.py` 一项。它们不计入真实渲染通过。

[机器检查索引](checks.json) · [七包报告](package-verification.json) · [完整日志归档](validation-logs.zip)

运行命令：

```sh
python ai-comic-drama-workflow/scripts/sync_shared.py --check
python video-prompt-compiler/scripts/reference_audit.py --suite .
python video-prompt-compiler/scripts/vpc.py knowledge audit
python ai-comic-drama-workflow/scripts/run_tests.py
python ai-comic-drama-workflow/scripts/run_v5_example.py --version v52 --studio --out <empty-directory>
python ai-comic-drama-workflow/scripts/benchmark_studio.py --out <report.json>
python ai-comic-drama-workflow/scripts/package_suite.py --out dists
python ai-comic-drama-workflow/scripts/verify_suite.py --packages dists --out <verification-directory>
python -m pip wheel --no-deps --no-build-isolation ./ai-comic-drama-workflow --wheel-dir <wheel-directory>
```

## 精简基准

在相同预写故事、真实原生校验与 core 传输下，对比旧 lean 的自动方法路由与 studio 的按需方法。此夹具为旧原生 1.0 文本案例，不包含 adaptive control、模型调用、原生输入文件读取、图像视频质量或外部等待。

| 指标 | 旧 lean | studio | 变化 |
|---|---:|---:|---:|
| 宿主上下文 UTF-8 字节 | 179,189 | 91,514 | 减少 48.93% |
| 宿主结果 UTF-8 字节 | 27,530 | 18,019 | 减少 34.55% |
| 宿主提交轮次 | 6 | 6 | 不变 |

不把字节数当 token，不把本地夹具运行时间当实际出片速度。具体逐阶段数据见 [benchmark.json](benchmark.json)。

## 新增能力的验收要点

- 超时后换 request/job ID，但仍涉及同一镜头：拒绝第二次提交。
- 两个并发尝试都可能超预算：仅一个完成预留；execution/event 与金额记录失败一起回滚。
- UNKNOWN 或任务尚未结束：禁止结算释放预留；明确失败也先保留到有账单。
- 恢复原任务、重复对账、接收原 Take：不新增执行尝试；V6 原生图同步。
- 五镜实际选择、探测与审阅齐全：放行；被改字节后立即阻塞。
- 两位说话人音频：实际解码、相加并留间隔，超出时间给出拆镜要求。
- 第二句被改：第一句内容指纹不变；提交第二句涉及的任务被阻断。
- Take 失败再重做：新的 Take 审阅有独立 ID，旧失败记录保留，不冲突覆盖。
- 截断视频/错误解码：失败；同字节重复探测可复用技术缓存，但不能产生视觉批准。
- 默认配置变化：只对新 studio 项目生效；明确 lean/audited 及已有冻结配置继续测试。

## 依赖和实际制作边界

仓库自身遵循根 Apache-2.0 许可。没有重新分发 jianying-headless、模型权重、电影参考图片或附件原件。默认 FFmpeg 依赖执行环境真实安装，其构建许可不由本仓库代替；显式剪映路径仍遵循原有环境与许可检查。

当前财务报表覆盖视频执行尝试，未自动包含 TTS、图像、订阅和人工费用。任意已冻结生产清单的自动重基、自动发布、多厂商平台、OCR/人脸模型及真实跨宿主媒体 canary 不在本次已实现声明内。

实际制作验收仍需真实入口、账号能力、素材、适用授权、费用上限与实看片/听音。源码和包测试通过不等于真实短剧已经制作完成。
