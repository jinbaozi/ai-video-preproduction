# V6 验收证据索引

工作流权威节点与适用条件在 [`workflow-v6.json`](../../workflow-v6.json)。`ai-comic-drama graph --format mermaid` 从该文件生成阶段图。以下检查均为本地回归，不能代替真实创作审阅或生成媒体质量判断。

| 要求 | 可复核检查 |
|---|---|
| 新项目默认 V6、旧入口无法绕过、命令包装字段精确 | `tests/test_v6_cli.py`、`tests/test_v6_runtime.py` |
| 六个锁定 Skill、依赖覆盖、显式 `NOT_APPLICABLE` 与范围交接 | `tests/test_v6_graph.py`、`tests/test_v6_stage_adapter.py` |
| 关闭未知字段、身份与批次、逐项证据、迁移复用来源、非法迁移 | `tests/test_v6_protocol.py` |
| 两次同项失败后的定向返修、新批次证据冻结、任意改输入不可绕过 | `tests/test_v6_runtime.py`、`tests/test_v6_protocol.py` |
| 原生 `RoleResult.handoff` 与 V6 产物交接分开预检、校验失败记到实际检查项 | `tests/test_v6_runtime.py`、`tests/test_v6_codex_host.py` |
| 分场美术及独立图片提示词最多两个并行、冻结原生任务指针按审结对象恢复 | `tests/test_v6_runtime.py` |
| 真实宿主回执格式、消息关联、独立审阅、未知派发恢复 | `tests/test_v6_codex_host.py` |
| 图片宿主调用与提供素材分流、字节校验、不确定调用不重发 | `tests/test_v6_media_host.py` |
| 冻结请求、原调用恢复、逐镜与相邻全覆盖、音频及最终交付门 | `tests/test_v6_production.py` |

运行完整本地检查：

```sh
cd ai-comic-drama-workflow
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t . -q
```

真实 Codex 子智能体派发、候选、消息与独立审阅的选取证据归档在 [`examples/v6/rehearsal/`](../../examples/v6/rehearsal/)；其中每个阶段标明实际完成状态，原始工具结果与文件 SHA-256 可逐项核对。`.local-tests/` 中的本地 ffmpeg 两镜头演练验证媒体与成片门，完整生产图用例中的审阅工具回执明确是合成测试夹具，不算真实智能体审阅，也不代表生成模型效果。发行时另执行 `scripts/verify_suite.py` 对七个独立安装包、manifest、SHA-256 和可重复构建做检查。
