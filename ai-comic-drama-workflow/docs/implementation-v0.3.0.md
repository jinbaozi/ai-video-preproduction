# v0.3.0 实施与分项验收记录

记录日期：2026-09-05。当前是待实图与人工验收的开发候选，不能宣称 v0.3.0 完整验收完成。
软件目标 0.3.0、Schema 3.0；保留 13 个编号目录、Canonical、Kernel 提交权和渐进披露。

## 已保存的基线与代码

- 起点 `5a04752`，软件 0.2.0；原有 31 项测试通过，用时 20.861 秒。保留原提交、标签和体检资料。
- `e98e7ba`：可靠性绿色基线，39 项测试通过；最终门、事务、恢复、输入解析和能力误报修复。
- `aa1eea8`：Schema 3.0、导演契约、生图宿主桥、三维与双图核心。
- `2dbf61e`：帧时间、作用域返修、空间诊断、真实图片绑定、当前草稿清单和本地剪辑强化。
- 仅本地 Git 跟踪，无远程配置、推送或历史重写；真实生图和人工验收未完成前不创建 `v0.3.0` 标签。
- Python 3.12.13；依赖 `jsonschema==4.26.0` 安装在项目 `.venv`，没有改动全局 Python。

## 分项结果

| 项目 | 当前结果 | 证据边界 |
|---|---|---|
| 自动化 | `scripts/run_tests.py` 64 项通过，74.793 秒；保留原 31 项覆盖 | 测试中的批准和图片 fixture 不是用户或媒体质量批准 |
| Skill | Skill Creator `quick_validate.py` 通过；入口保持精简 | 静态检查不替代前向使用与创意验收 |
| 打包 | 109 个文件连续两次构建字节一致，包内所有文件 SHA-256 匹配；解压包的三项冒烟测试通过，4.206 秒 | 不包含 `.local-tests` 媒体或真实生图验收声明 |
| 导演与时间空间 | DirectorTreatment、数字相机、米制转换、帧时间、并行轨道、道具归属及镜头交接已实现并测试 | 导演水平、表演与叙事质量仍需实际作品审核 |
| 原生生图桥 | TaskEnvelope → 宿主任务 → submit → 文件导入与预算门往返通过 | 使用明确标识的导入测试图片；尚未调用真实 image_gen |
| Blender | 5.2.1 LTS 实际建场、渲染、状态回读；6 镜、576 帧、24 秒预演 | 是代理几何和关节目标，不是角色身份成图、精确人体 IK 或物理模拟 |
| 双图 | 缺图、白模、错版本、错时点、陈旧哈希、未批准和槽位溢出均有硬门 | 尚无经用户批准的真实角色图及故事板成图，不能宣布正式双图包可交付 |
| 本地剪辑 | 实际 FFmpeg 文件证明顺序、入出点、叠化、音频混入、字幕及禁用字幕有效 | 音频测试为合成测试音；macOS TTS 执行与试听尚未验收 |
| 迁移恢复 | 实际冻结 v2 项目迁移、v1 三项选择、返修、旧批准拒绝与草稿快照已测试 | 原项目和历史保留；草稿 ZIP 是查看快照，不是续跑项目 |

旧版纯提示词黄金场景显式改选 `prompt-draft`；不能以这些旧成功预期替代 v3 的双图硬门。
确定性要求覆盖固定 Canonical、提示词、派生文本和打包，不要求 image_gen 重复调用字节相同。

## 实际预演与抽帧复核

当前预演：`.local-tests/v3-golden-director-reviewed/stages/12-配音字幕与剪辑/media/render/0bb4aa546d15c17d7a14/preview.mp4`。

- SHA-256：`67d7425ab2df5f45d75851e40b0f1cf520dd2ced812296e54d87d98be497a643`。
- 640×360、24fps、24 秒、H.264/AAC；全片解码及黑帧检查通过。
- 静止段检测提示需复核：建立镜头、反应和结束镜头含设计停顿，未把冻结提示伪报为全部通过。
- 原始输入和回读报告在同测试根目录 `runtime/golden-input.json`、`runtime/golden-result.json`；工程、PNG 与逐镜视频在阶段09。
- 已抽看建立、交接、收信和反应关键帧；发现画外角色手部标记未隐藏，修复后重新渲染并抽查。没有把抽帧检查冒充用户完整观看批准。
- 本机 Blender 的 Metal 初始化需要获得本地沙箱外运行许可；没有安装软件，版本探测本身仍只报待执行验证。
- `.local-tests` 是忽略的本地执行证据，不混入确定性 Skill 包。

复验入口：`.venv/bin/python scripts/check_blender_integration.py --output .local-tests/your-check --golden`。
该脚本显式标记 `test_only=true` 和 `human_approved=false`，不是正式创作项目或用户批准的作品。

## 独立前向测试发现与处理

按 Skill Creator 要求使用隔离 Git 快照、独立原文和当前契约推进，未用实现者 fixtures 冒充真实创作。

- 第一轮 `e98e7ba`：发现资产和对白契约不明确、交付索引自引用旧哈希；补专用 Schema、对白覆盖检查和自引用排除。
- 第二轮 `aa1eea8`：前三项不再复现，但发现道具轨道未定义、`speaker_id` 丢失和返修草稿携带旧报告；已修复，并增加针对性回归。
- `2dbf61e` 独立复测三项均通过：旧道具字段在提交前被拒绝、说话人保留、返修草稿内 308 条哈希引用全部匹配且原项目未推进。33 次 CLI 调用仅预期负向提交返回非零；批准均为 synthetic fixtures。
- 独立完整报告及逐条证据：[2dbf61e 三项复测](/private/tmp/ai-comic-forward-2dbf61e.z7htn5/forward-test/REPORT.md)。此结论不涵盖原生媒体或全量创意审计。

## 当前能力与明确未完成项

- 原生 image_gen 集成等待用户确认视觉风格，再实际生成角色参考图、人工批准、共同引用角色图与空间关键帧生成故事板并审核。未自动采用推荐风格。
- 独立 Python 不会伪造原生生图 API；`provided` 路径只允许导入，不授权调用生图。参考绑定的导入声明与真实工具调用证据分别记录。
- Blender/FFmpeg/Pillow/本地 `say` 可发现；没有 pypdf 或 SVG→PNG 转换器，相关功能暂停或明确降级。OCR 程序可发现不等于扫描内容已可靠识别。
- 当前实际运行环境为 macOS；事务锁依赖 POSIX，未宣称 Windows 已适配或验收。
- 未接云端视频、实时导演流、外部平台账号或自动发布；Seedance/Doubao 仅表达适配，实际共同参考方式、限制和效果未验证。
- SFX/音乐保留计划，未注册自动生成执行；音色选择后需验收本地 TTS。预演中的静音音轨不代表对白或配乐已制作。
- 手改 `.blend` 必须转换为可审核的 Canonical 差异提案，经 `revise/submit` 流程处理；不自动执行任意工程中的脚本或把它当第二事实源。
- 人体、网格碰撞、遮挡及表情质量检查有代理和采样精度边界；图像、完整播放和人工导演质量审核仍是正式发布前必需步骤。

## 实际修改文件

代码范围：`5a04752` 至 `2dbf61e`；另包含当前验收文档和重新生成的 Skill 包。

```text
.gitignore
README.md
SKILL.md
docs/implementation-v0.3.0.md
docs/reviews/2026-09-05-director-spatial-audit.md
pyproject.toml
references/artifact-contracts.md
references/blender-execution.md
references/codex-imagegen.md
references/l0-orchestrator.md
references/phases/phase-07.md
references/phases/phase-08.md
references/phases/phase-09.md
references/phases/phase-10.md
references/phases/phase-12.md
references/recovery.md
references/role-director.md
references/runtime-usage.md
resource-catalog.json
schemas/agent-result.schema.json
schemas/approval-record.schema.json
schemas/artifact.schema.json
schemas/asset-plan.schema.json
schemas/capability-snapshot.schema.json
schemas/decision-request.schema.json
schemas/director-treatment.schema.json
schemas/edit-plan.schema.json
schemas/evaluated-frame-state.schema.json
schemas/final-delivery-index.schema.json
schemas/generation-segment-plan.schema.json
schemas/legacy-v2-schemas.json
schemas/manifest.schema.json
schemas/media-job.schema.json
schemas/media-result.schema.json
schemas/phase-index.schema.json
schemas/project.schema.json
schemas/prompt-package.schema.json
schemas/reference-binding.schema.json
schemas/scene-space-plan.schema.json
schemas/shot-timeline-spec.schema.json
schemas/source-registry.schema.json
schemas/storyboard-package.schema.json
schemas/task-envelope.schema.json
schemas/visual-asset-registry.schema.json
schemas/workflow-state.schema.json
scripts/check_blender_integration.py
scripts/package_skill.py
scripts/upgrade_v3_contracts.py
src/ai_comic_drama_workflow/__init__.py
src/ai_comic_drama_workflow/blender_adapter.py
src/ai_comic_drama_workflow/blender_scene.py
src/ai_comic_drama_workflow/capabilities.py
src/ai_comic_drama_workflow/cli.py
src/ai_comic_drama_workflow/editing.py
src/ai_comic_drama_workflow/exporter.py
src/ai_comic_drama_workflow/ingest.py
src/ai_comic_drama_workflow/kernel.py
src/ai_comic_drama_workflow/media_bridge.py
src/ai_comic_drama_workflow/migration_v3.py
src/ai_comic_drama_workflow/pipeline.py
src/ai_comic_drama_workflow/references.py
src/ai_comic_drama_workflow/schema.py
src/ai_comic_drama_workflow/spatial.py
src/ai_comic_drama_workflow/spatial_qa.py
src/ai_comic_drama_workflow/storage.py
src/ai_comic_drama_workflow/timing.py
src/ai_comic_drama_workflow/transactions.py
src/ai_comic_drama_workflow/utils.py
src/ai_comic_drama_workflow/validation.py
tests/golden_director.py
tests/helpers.py
tests/test_recovery_and_media.py
tests/test_reliability.py
tests/test_routing_and_disclosure.py
tests/test_schema_and_choices.py
tests/test_v2_workflow.py
tests/test_v3_contracts.py
tests/test_v3_delivery.py
workflow-graph.json
dist/ai-comic-drama-workflow.skill
```
