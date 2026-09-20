# Hypit可选后期后端

定位：把已选择、已裁切的本地Take装配成Author/Run源。导演决策与事实仍在DirectorIR。
本版按本机 `hypit --version` 返回的 **0.1.10** 和安装包文档编写；不是跨版本语法保证。
导出前检查当前版本，变更后运行check和plan重新核验。

## 已实现的边界

`scripts/export_hypit.py` 读取IR、ExecutionIR和 `edit-manifest.schema.json` 格式的Take选择清单。
每镜头恰好选一个Take，文件与sha256相符，审片记录存在，且ffprobe测得帧数/FPS/尺寸与镜头合同一致。
它复制已选媒体，生成真实的 `main.svml`、`main.svs`、`build.svrun`、`export-receipt.json`。
不会把JSON改后缀伪装成SVML；不会提交生成、调用build或修改现有Runtime配置。

```bash
.venv/bin/python scripts/export_hypit.py project.director.json build/execution.json edit-manifest.json --media-root project --out outputs/hypit-v001
hypit check outputs/hypit-v001/main.svml --workspace outputs/hypit-v001
hypit check outputs/hypit-v001/build.svrun --workspace outputs/hypit-v001
hypit plan outputs/hypit-v001/build.svrun --workspace outputs/hypit-v001
```

导出器只支持已精确裁切的片段，按顺序硬切、contain布局、复用源音轨。
精确入点、混音、字幕、变速、特效、生成请求等需要在各自实现层完成后重新验收。
`--test-fixture` 仅给测试媒体使用，输出 TEST_SOURCE_EXPORTED，不能签收为真实创作结果。

## 计划、执行与复用

check验证源与引用；plan展示所选图和待执行工作；build才触发新Build。
本包只调用前两种检查。本地渲染和外部付费请求仍需按任务授权与预算决定，不因存在build文件自动执行。

导出器直接引用已接受本地Take，因此不包含生成节点。若未来改为生成图或继续已有Hypit项目，
按安装版本声明 `<build-record>` 与 `<satisfy>` 复用已有输出；不能假定重复build有隐式缓存。
本版没有build-record转换器、运行源合并器或Provider配置器，不把这些文档路径说成已实现功能。

Hypit实现未被复制进本包。其独立许可证见[仓库LICENSE](https://github.com/hypit-ai/hypit/blob/main/LICENSE)；
如要分发其代码/服务，应依据当时许可证核对适用条件。
