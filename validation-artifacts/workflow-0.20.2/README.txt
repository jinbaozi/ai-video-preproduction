ai-comic-drama-workflow 0.20.2 — V2.0 发布验证记录

基于 V2.0 分支 0.20.1 技能包修改；本目录记录 0.20.2 的本地验证过程，发布包位于仓库 dists/。

完成内容
1. 新 studio 冻结 studio-execution/1.0。生图前复核原生前置、当前提示词、任务和引用；生成结果必须绑定原执行记录。
2. 新增 dispatch_image 宿主适配入口：先预留、调用一次、保存候选；异常留 UNKNOWN，不自动通过视觉验收或重试。
3. 新增 images/full 交付终点；缩小范围保留 Canon、剧本、导演、美术依赖，恢复后复用已接受产物。
4. 验收逐项覆盖人物、构图、道具、空间、光线和参考；可配置精确宽高/比例，实际解码检查。
5. image-report/export 依据原生收据和实际字节输出状态；候选、过期和正式图片交付分开，不能以图片验收冒充视频完成。
6. 结构化恢复绑定原任务与厂商ID；未决任务不能通过改范围或导入图片清除。

安装/使用
安装 ai-comic-drama-workflow.skill，或在展开的技能根目录执行 python -m pip install -e .。
新项目：ai-comic-drama start brief.txt --project ./film --stop-after images
切换范围：ai-comic-drama scope ./film --stop-after images --reason "用户先要图片"
恢复全流程：ai-comic-drama scope ./film --stop-after full --reason "用户恢复制作"
图片状态：ai-comic-drama image-report ./film

旧项目不自动升级，不修改已有用户素材或账目。图片终点为第5阶段美术参考及其图片提示词；分镜图和模型视频包仍走 full。

验证
新增22项门禁测试通过。全量首次运行478项，476通过，2处索引/装载问题已修正并分别补测通过；详细过程见 validation.json 及日志。将来全量测试使用 python -m unittest discover -s tests -t . -q。
技能包逐文件校验、源码补丁试应用、独立启动检查均通过。所有图片/服务返回为合成测试夹具，没有调用真实付费生成服务。

能力边界
当前会话的外部生成工具权限不由本地技能包控制。要阻止所有旁路调用，宿主需要接入 dispatch_image 等受控代理，并收回直接工具/凭据访问；本包没有安装此宿主级隔离。语义与视觉仍需实际审阅，字段齐全不是艺术质量证明。
