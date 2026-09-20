# 所有权与当前工作区集成

2026-09-19读取了同级director-grammar、production-design-grammar和video-prompt-compiler的当前Schema与集成说明。
前两者schema_version为1.0；编译器接受avir/1.0。没有修改这三个包；本Skill不import相邻目录代码，移动或独立安装后仍可离线工作。

| 权威内容 | 原所有者 | 分镜层做什么 |
|---|---|---|
| 原文、角色事实、资产ID、批准、版本 | 宿主Canon/用户 | 指向原件和切片，不另建Canon或批准 |
| 信息顺序、视点、已锁镜头与表演 | 导演 | 细化未锁画格、动作时点和交接检查 |
| 场景拓扑、建筑、服化道、材质、世界光源 | 美术 | 检查容纳、可见、接触与连续性 |
| 当前细化的镜头节点、连续性规格 | 分镜 | 输出计划、来源、合同及冲突建议 |
| API模式、附件、费用、提交、素材账本 | 宿主执行器 | 交接所需语义与损失，不能伪造能力 |
| 素材采用、剪点、声音混合 | 剪辑与声音执行 | 接收animatic计划，实际验收另存 |

## 上游只读绑定

upstreams.kind为director/art/canon，uri相对源IR文件目录或绝对本地路径，sha256锁原字节。
核对project_id、revision与schema_version。每个lock保存source_pointer、source_value、target_pointer、target_value及转换理由。
mode=equal要求两端值相同；mode=mapped核对显式声明的两端值。后者不证明转换语义正确，需Agent按实际坐标/单位与所有者检查。
不要只锁project_id就宣称完整继承：把本次使用的台词、剧情、实体ID、空间、机位、动作、参考和硬要求逐项绑定。
当前CLI检查的是声明过的字段，未遍历上游所有锁；完整性与owner冲突保留人工审查。

## 映射到AVIR 1.0

| 当前来源 | AVIR字段 | 必须说明的转换 |
|---|---|---|
| entities | entities | kind=voice需宿主音轨表；不能硬改成画内person |
| scenes / coordinates / lighting | scenes | 保留原点与x-right/y-up/z-depth；其他轴显式变换 |
| assets / bindings | assets / bindings | metadata_only→inspection=metadata_only；用途词按目标枚举转换 |
| delivery / shot frame ranges | output.duration_ms / shots.start_ms,end_ms | 全局帧边界一次转换，记录舍入误差 |
| camera / composition / relations | shots对应字段 | 画框、轴侧命名、look_at与屏幕关系明确映射 |
| state_start/state_end | shots.start_state/end_state | 字典转数组；holder展开为对应人物holding；手别与contacts保留sidecar |
| performance | shots.performance | 时标转换，保留微反应/动作/反馈/收束及心理是否发声 |
| audio | audio.utterances/cues | 保留speaker、kind和文字；画外标记、声音跨镜与同步精度另记 |
| contract | contract | owner、strength→level、checks.path和渠道逐条重定位；不只是复制旧JSON Pointer |
| beats、panels、细粒度events、上游locks | 独立sidecar | AVIR无等价结构，保留原IR/交接包/哈希与映射表，记录无法直接表达项 |

`compiler-handoff.json`不是AVIR，不能直接传给vpc.py。顺序为宿主读取交接 → 核对当前AVIR Schema → 显式转换 →
检查来源、时标及全部硬条款 → 运行下游validate → 选择已核验入口compile → 宿主执行与媒体QA。
本版本交付到平台中立交接层，未实现自动AVIR、OTIO或Hypit导出器；不宣称已完成端到端联调。

## 冲突及版本变化

同一角色换身份、道具同用途参考版本不同、原台词变更、机位/空间矛盾时，输出当前值、冲突来源、建议值、影响镜头和验收条件。
在用户既有授权范围内修复未锁定设计；已锁事实改变交给原所有者。源哈希变化即重新核对并构建，不能保留旧批准假装仍有效。
