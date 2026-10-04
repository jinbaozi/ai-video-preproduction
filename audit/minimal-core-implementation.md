# 最小阶段闭环：实现与验收

## 范围

基线 `dc954fe1579a40c50bf0e86d7059c487c8f57b61`；先行方案提交 `26424ebab0bd66569a9c76da84d2fb55b5137ef1`。不另造内容IR或工作流内核，不删除名家、场景、通用方法、模型方法或社区资料注册表。

每阶段保留必要输入/锁定、原生输出、采用证据、校验、交接和异常。七个技能仍可独立使用；完整项目沿原生状态机串联。原有完整说明移到各自 `references/detailed-execution.md`，不是删除能力。

## 实现

- 七个短SKILL入口与每技能 `references/stage-core.md`：职责、必要输入、原生表示/交付、四步流程、失败责任和按需读取。复杂任务、历史协议、独立审阅或模型模式的资料按原条件读取。
- 新lean项目默认冻结 `minimal-core/1.0`；`start --context-profile audit` 保留完整上下文，audited不允许core。旧项目不迁移、不补造新审计。
- `minimal.py` 是已有任务的呈现/结果适配层：`context` 给出当前任务、全部命中及继承规则、实际选中参考段落和必要文档，完整原生任务仍在原位置。去重同一指令、哈希/来源元数据和检索候选，不裁剪用户锁定、信息顺序、规则正文/作用域、H3等模式必要读取或社区段落。
- 宿主提交 `core-result/1.0`：显式 `read_ack`，实际原生文件、采用或不适用及语义/视觉结论。程序填实际文件/模块/段落指纹、读取回执和原生校验结果。HOST_DECLARED与真实媒体QA区分，不将ack当作人类或Agent认知的证明。
- 分组采用只允许显式rule_ids、同一作用域和同一事实证据；遗漏、重复、通配符、混用applications/groups、错误quote/hash、元数据证据、缺rationale或缺semantic_review拒绝。展开后继续走原有逐规则检查。四个专业创作技能提供 `craft_router.py --plan --review --artifact` 独立绑定入口；不替用户决定采用状态。
- 每次提交原件校验、归档后校验保留；第三次对原件的重复校验只复用当前提交内同kind/path/sha的实际报告。跨调用不缓存PASS，改字、归档路径变化、失败或修订不沿用旧报告，finally清理。
- 同一编译包的正文复核与最终前期QA可在一次显式宿主结果中提供。内核仍派发/校验两份原生任务与收据。build/read-set不一致即停止批处理；无真实检查、不通过、缺硬条款即失败，失败事务回滚。不是取消QA，也不把一次ack用于不同构建或新读取。

## 合成对照计量

同一预先写好的咖啡馆text-only夹具；两侧均lean+compact，原生检查实际执行。三个独立进程交替运行取中位数，Python3.13.5。下面不是LLM调用或真实视频生产基准。

| 计量 | 基线 | 本轮 | 减少 |
|---|---:|---:|---:|
| 七个SKILL入口UTF-8字节 | 86,378 | 11,348 | 86.86% |
| 阶段任务与必读说明字节 | 359,751 | 178,755 | 50.31% |
| 宿主结果提交字节 | 89,684 | 27,476 | 69.36% |
| 宿主提交轮次 | 7 | 6 | 14.29% |
| 原生校验器调用 | 12 | 8 | 33.33% |
| 本地夹具总耗时（秒） | 25.3674 | 19.3665 | 23.66% |

任务JSON用紧凑UTF-8序列化；基线另加模块必读文件原始字节，本轮计入实际内嵌readings。两侧仍需读取的原始来源、原生内容IR和媒体不计入上下文总数。七个入口字节单列，不与上下文重复相加。提供了基线理想复用已读文档的下界作参考；不把字节当token，不承诺每个项目或模型都节省同比时间。磁盘审计仍保留，发行ZIP大小略增，不宣称安装包变小。

重跑脚本为 `ai-comic-drama-workflow/scripts/benchmark_minimal.py`，汇总在 [minimal-core-benchmark.json](minimal-core-benchmark.json)。CI使用固定基线和Python3.12另行生成报告，性能门只比较字节/调用数，不以共享runner墙钟时间作为通过门槛。

## 已做专项与回归入口

本地新增22项通过，包括真实原生前期交付、原生8次校验、最终批处理与事务回滚、重复提交、锁定策略/读取/任务/证据篡改、四技能独立绑定CLI、所有已登记名家和专业场景路线。登记覆盖为编剧30条人物、导演20条、美术20条（合计70条登记项，不承诺去重人数），以及46类专业场景profile；相关共用方法ID逐项测试。原有无点名语义路由、社区和模型专项继续执行，目录内容未删除。

首轮全量回归发现两项短入口可发现性退化：默认专业路由标题，以及自主执行、Flow与剪映的入口被移入深层。已恢复七个默认路由标题与必要直达链接，没有修改或放宽原断言；受影响的59项既有测试重跑通过。最终入口修复后重新进行三轮对照计量，表格使用该轮结果。

本次191份reference文档完成可达性检查；原有14张社区卡173种声明组合仍按实际读取审计。可达性不是所有历史命令/代码分支执行覆盖。

```sh
python ai-comic-drama-workflow/scripts/sync_shared.py --check
python video-prompt-compiler/scripts/reference_audit.py --suite .
python video-prompt-compiler/scripts/vpc.py knowledge audit
PYTHONPATH=ai-comic-drama-workflow/src:ai-comic-drama-workflow \
  python -m unittest tests.test_minimal_core -v
python ai-comic-drama-workflow/scripts/run_tests.py
python -m unittest discover -s video-prompt-compiler/tests -v
python ai-comic-drama-workflow/scripts/package_suite.py --out dists
python ai-comic-drama-workflow/scripts/verify_suite.py --packages dists --out /tmp/minimal-suite
```

完整主工作流、编译器、Blender、七包隔离和新增基准，以最终提交的GitHub Actions日志为准，不用早期版本的通过结果代替。发行隔离检查中包含本轮22项，而不只是源目录中能运行。

版本：总工作流0.19.0、视频编译器1.23.0、图像1.17.0、编剧1.1.0、导演1.5.0、美术1.4.0、分镜1.4.0。原生协议/旧运行时版本未随包版本强改；六内置模块与独立发行包保持字节一致。

## 保留的生产与异常边界

核心路径不默认创建子Agent团队，不逐阶段向用户请求定稿。输入不明或锁冲突回责任阶段；证据失效只重做受影响依赖；未知外部执行先回收，不重复提交；有界返修失败报告阻塞。

full仍需要真实图片和审阅，不能自动降为text-only。Flow2K保真、模型能力、真实引用、费用、登录、生成回收、相邻镜头QA、剪映/成片验收沿用现有门禁。本文本合成验证未执行这些外部服务，未进行真实视频视觉验收，不把DELIVERED前期包等同VIDEO_DELIVERED或保证艺术质量。
