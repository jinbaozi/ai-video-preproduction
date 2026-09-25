# 旧项目复制迁移

V5不原地运行或改写V4、旧版十三阶段或video-storyboard-prompter-zh项目。
copy-project要求全新且不在源项目内部的目标目录，逐文件保留原字节、SHA-256和原相对位置。
imports/migration.json列出全部文件、图片候选和待核验项；未知字段在原件中完整保存。
V4的1—12秒连续镜头与最多5张上传参考保留为迁移合同，不自动变成新项目通用限制。

复制只是迁移第一步。当前Agent读取原Canon、剧本、分镜、资产表及决定记录，复用内容并整理V5任务。
图片以实际文件重新登记；只有文件、身份、用途和原决定绑定均未变，才能引用原用户决定。不能复制APPROVED字符串当作新的批准。
旧提示规范已进入各专业技能和当前执行合同。V2 到 V4 运行代码已移除，历史在 git。

迁移报告另含native_candidates、identifier_evidence和decision_evidence。JSON中的原始ID逐项保留来源位置；无法确定的YAML字段保留在原文，交给当前Agent核对，不推断新ID。每个图片任务会显示迁移中的真实图片候选；通过看图、用途及版本核对后作为provided导入即可，不要求重新生成。旧项目ID可被V5使用时直接沿用。

## V5.4 交付终点

`production_target` 缺省为 `none`。`full` / `text-only` 仍只描述前期包。视频完成是单独状态 `VIDEO_DELIVERED`。当前规则合并为 `references/current-contract.md`；V5.1 与 V5.2 原文在各包 `references/history/`。

## V5.3 编剧接入

新锁包含 screenplay-grammar，共六个专业模块、七个发行技能。第二阶段提交原生 ScriptIR，导演阶段需要来源绑定、原生硬合同与语义映射。原有五模块锁继续使用旧编剧路径；update-modules 显式升级保留旧归档与媒体，失效旧式剧本及受影响下游，不自动改写源稿。
