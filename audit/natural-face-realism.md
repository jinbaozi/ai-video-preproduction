# 自然面容增强：方案、实施与验证

日期：2026-10-12。图像技能版本 1.18.0，视频技能版本 1.24.0。

## 优化方案与实施

将真人感从品质标签改为可见、局部且有来源的约束：五官只重点强化一两个识别点，皮肤按区域分配细节，毛发按密度、边缘与曲面方向生长，先确认人物自然再风格化。重点数量不限制已有身份锚点数量；不为写实新增胡茬、痣、痘印、年龄或永久不对称。

| 责任 | 实施入口 | 边界 |
| --- | --- | --- |
| 图像 | `image-prompt-optimizer/references/natural-face-realism.md`；SKILL、stage-core、人像外观、照片感与评价入口 | 按景别/可见性描述；局部返修保留身份、妆面、造型和锁定灯光 |
| 视频 | `video-prompt-compiler/references/natural-face-realism.md`；注册 `natural-face-realism` 模板 | 前端授权设计或原责任阶段返修；冻结后只投影原生字段 |
| 路由与来源 | 来源绑定的语义标签、条目自身本地来源与 SHA-256；自包含校验 | 不把否定标签子串当命中，不混入外部案例署名；隔离加载可用 |
| 连续性 | 稳定面容/皮肤布局与瞬时表情/光照区分；转头、发束与跨镜检查 | 文本约束不保证逐帧可控；实际质量须看片 |
| 安装 | 两个独立包、总包内置模块、modules.lock 与 suite manifest | 内置模块与独立包字节一致，历史已锁项目不自动迁移 |

来源为用户提供的约 86 秒视频分析文字，本项目没有获得或独立核验原视频、逐帧图和完整口播。材料止于胡茬方向；眉毛、头发、细节形态/锐化及视频时序规则明确标记为延伸。本文不宣称原片画面观察已被本项目证实，也不宣称跨模型增益。

## 验证范围

两个技能分别增加 10 个行为回归请求与验收标准；这些表是待执行标准，不是假定完成的视觉实验。自动回归检查实际方法选择、否定标签、与手持外观共用、本地来源变更/缺失/越界、按文件路径隔离导入、冻结 AVIR/正文/音轨/参数保持、manifest 校验及回放。

最终执行结果在本节下方记录。实际生图、视频生成与全片视觉验收均为 NOT_RUN；静态与安装包验证不替代媒体质量检查。

## 已执行的最终检查

| 检查 | 结果 |
| --- | --- |
| 图像技能完整 unittest | 38 项，OK |
| 视频技能完整 unittest | 335 项，OK，3 项按环境条件跳过；另行执行最终新增回归见下行 |
| 最终新增自然面容回归 | 5 项，OK；源码与最终安装包解压后的独立目录均通过，包含隔离按路径导入 |
| 工作流完整 unittest | 469 项，OK |
| 七技能本地资料可达性审计 | PASS |
| 社区方法读取/路由审计 | PASS |
| 共享源同步检查、git diff --check | PASS |
| Seedance 2.5 精确入口方法计划 | 成功选中本地模板；没有提交生成，NOT_RUN |

复现命令（在仓库根目录）：

```sh
python -m unittest discover -s image-prompt-optimizer/tests
python -m unittest discover -s video-prompt-compiler/tests
python -m unittest discover -s video-prompt-compiler/tests -p test_natural_face_realism.py -v
python ai-comic-drama-workflow/scripts/run_tests.py
python ai-comic-drama-workflow/scripts/sync_shared.py --check
python video-prompt-compiler/scripts/reference_audit.py --suite .
python video-prompt-compiler/scripts/vpc.py knowledge audit
python ai-comic-drama-workflow/scripts/package_suite.py --out dists
python ai-comic-drama-workflow/scripts/verify_suite.py --packages dists --out ./work/verify
```

完整视频回归在新增“按文件路径隔离导入”测试加入前已启动，因此统计为 335；新增文件的最终 5 项另外执行并在最终包中复核。没有用未运行的用例充当媒体质量证据。

发布包最终验证：7 个包、60 项隔离检查全部 PASS；独立安装通过，内置模块与独立包字节一致，重复构建 IDENTICAL。另在最终视频包中运行新增自然面容的 5 项专项回归，全部通过。
