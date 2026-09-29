# H3 离线合成样例

这里只演示静态检查：节点 ID 是夹具值，模型文件名、输入媒体和节点安装均未实测；Ref2VA 的 `SyntheticVideoFramesAndAudio` 是刻意标注的占位类。图未包含解码/保存出口，不能当作可直接在 RunningHub 运行的完整模板。

在技能目录执行：

```bash
python scripts/vpc.py h3 inspect examples/h3-runninghub/t2va.api.json
# 将上条返回的 workflow_sha256 代入，不复制其他工作流的摘要：
python scripts/vpc.py h3 plan examples/h3-runninghub/t2va.api.json \
  --node 64 --sha256 '<上条真实摘要>' \
  --prompt examples/h3-runninghub/t2va.prompt.txt --out /tmp/h3-example-v001
```

Ref2VA 例子示范伴随视频声轨 Audio 1 和独立音色 Audio 2 的不同用途。实际使用换成自己的 Export Workflow API、真实媒体和匹配模型，重新 inspect，保持引用顺序并语义复核。静态成功仍是 `PLANNED_REQUIRES_RUNTIME_CHECK`。
