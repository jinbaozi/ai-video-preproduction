# 提示词方法分层实现与验证

## 变更

先行方案提交 `44cadc52568496b4670ff86f3b1277ba819ccafe`，基于主线 `5587ea12c145d1a627a00a9bb66f8af830bdc7c8`。源码参考固定于 LearnPrompt/awesome-seedance `9ca56354b3af0d11db22a935a6b831d7d8582c04`。

- 编译器 1.21.0：6项通用方法、27个重新归纳的任务模板、10个精确profile策略。Wan/Runway未知入口只获得通用层，不升级能力。字段映射、写作骨架、检查点、来源路径和哈希保留在目录中，宿主仅加载命中项。
- 工作流 0.17.0：复用 source-bound craft_context、原任务和 craft_review；选中规则必须有原生产物采用/不适用证据。已采用分镜模板传给真实编译命令，选择影响构建指纹及导入复用；不新增项目状态或中间报告。
- 编译、模型正文、逐段投喂、附件、音轨和后期路径仍使用现有 AVIR/native renderer。冻结IR不被模板重写。方案及客观检查嵌入 artifact，manifest/replay保留选择，verify重算防篡改。
- 模型专有层按ID、模型名、能力注册表版本、后端、模板与模式隔离。社区参数或引用符号不提升原生支持，未知/变更profile不回退到近似名称。
- 旧锁定模块/旧冻结任务不追补本扩展；无模板的旧编译包仍按旧manifest校验。原Flow、生产回收、Jianying和视频QA门禁未被替代。
- 新增专用CI；保留主线原有完整工作流、编译器、独立发行包和Blender真实预演验证。

## 新增对抗验证

23项编译器测试：完整目录来源、全profile通用语义、精确模型隔离、未知版本/后端/模板、未实现操作、RunningHub模式、自动选择歧义、冲突模板、反向语义标签、源与capability指纹、参考职责矛盾、时间轴缺口、原文及音轨保真、AVIR1.2、lean/audit等价、replay、重新封装的伪造报告拒绝、CLI入口。

5项工作流测试：原有采用门、改写/删除规则拒绝、跨目标方案拒绝、旧任务兼容、只传递实际采用的分镜模板。既有原生端到端测试追加检查：从创作到DELIVERED的编译manifest和artifact确实含选中模板，提交状态仍为false。测试作者文字是明确合成夹具，不冒充真实创作或视觉审核。

## 可复现命令

```sh
python ai-comic-drama-workflow/scripts/sync_shared.py --check
python ai-comic-drama-workflow/scripts/package_suite.py --out dists
python -m unittest discover -s video-prompt-compiler/tests -p 'test_prompt_techniques.py' -v
PYTHONPATH=ai-comic-drama-workflow/src:ai-comic-drama-workflow python -m unittest tests.test_prompt_methods tests.test_craft_end_to_end -v
python -m unittest discover -s video-prompt-compiler/tests -p 'test_*.py' -v
python ai-comic-drama-workflow/scripts/run_tests.py
python ai-comic-drama-workflow/scripts/verify_suite.py --packages dists --out /tmp/prompt-technique-suite
```

全量与发行测试结果以最终提交的 GitHub Actions Checks 和所附验证记录为准，不预填通过。Python本地环境无Blender时会明确跳过真实预演；远端control-render任务安装Blender后执行。真实模型生成、Google Flow服务、剪映原生导出与成片主观质量本次均为 NOT_RUN；不得把本功能静态通过解读为这些服务已经执行。
