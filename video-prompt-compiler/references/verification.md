# 验证记录

日期：2026-09-19；版本1.0.0。使用Python 3.12与jsonschema 4.26.0完成本地验证。

- Skill标准frontmatter/命名/未完成脚手架检查通过。
- 24项行为回归通过：schema、跨模型条款、台词口型、音轨路径、空间终态、连续性、轴侧、微表情可见性、
  时轴、来源与哈希、参考角色/槽位/上限、Agnes模式与参数、未知能力、预算、Context纯函数与fallback、
  扩写决策/trace、构建完整性及批量错误隔离。
- 独立前向测试发现后期对白口型依据缺失、终态相对位置未验证，两处已修复并复核通过。
- 独立目录按SKILL命令完成profiles→validate→compile→verify→replay。
- 最终发布包执行独立解包检查、内容哈希/安全路径核对、Schema自检、链接检查及CLI烟测；详见交付目录`outputs/verification.json`。

示例为合成资料，测试参考字节只验证映射逻辑，不是经过视觉QA的真实图像。
Seedance2.0/2.5、Agnes2.5/Flash、Kling3/Omni、H3、Veo3.1有可运行的提示词编译路径。
Agnes可形成文档约束下的API草案；其余是提示词计划。Wan3.0和RunwayGen4.5因具体能力未核实而明确BLOCKED。
无上传/付费/生成/API实测，没有VBench、真人A/B、口型或成片质量通过的声明。
报告中的企业服务、模型训练、异步生成与SLA作为宿主扩展路径，未作为已实现功能交付。
