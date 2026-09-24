# 第二轮审核探测复跑

来源是用户授权的 GPT-6 Pro 网页审核附件 `93c10e7-round2-adversarial-audit.zip`。这是测试代码，不属于 Skill 执行模块。

```sh
python validation-artifacts/audit-round2-replay/run_current_probes.py
```

依赖 Python 3.10+、jsonschema/referencing 和 PATH 中的 ffmpeg/ffprobe。脚本只操作本目录的 evidence/，生成合成 PNG/WAV/MP4 并用当前仓库真实模块验证，无网络请求、上传或模型调用。重新运行会重建自己的测试输出。

保留了原作者的完整原生 AVIR 夹具、媒体构造与选定探测代码。适配仅包括：导入当前 workspace 模块而非 93c10e7 快照；不再运行旧 SHA 专属摘要守卫；把当前版本提前拒绝的画幅冲突记为预期拒绝；使已成功构建返回的 Path 可序列化到测试日志。没有修改被测试的实现，也没有替代校验器。

范围是 A01–A09 的 13 个相关探测与对照，不是原始 71 项断言全套，也不含浏览器 A10。原脚本较早的正例缺少当前新增的来源绑定条件，因此未作为当前有效正例直接移用；仓库原生正例由 test_control_audit_round2.py 和 test_keyframe_handoff.py 另行覆盖。

result-summary.json 记录本次实跑及源文件摘要。样例地址和审核记录是合成软件夹具，不能当成真实上传回执或模型质量验收。
