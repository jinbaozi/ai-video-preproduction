# 离线编译器与协议

入口 `scripts/art_compile.py`；Python 3.10+和requirements.txt。图片/视频证据检查还需ffmpeg/ffprobe。
读取带重复键、NaN或Infinity的JSON会报错。文件路径相对输入ArtIR所在目录解析；不会联网下载引用。

## ArtIR 1.0

| 字段 | 含义 |
|---|---|
| schema_version/project_id/revision/canon | 项目、版本与唯一事实源引用 |
| director | 可空；完整绑定为uri、原始字节sha256、项目及revision |
| sources | 每个事实或设计依据；局部source_refs关联 |
| brief | 世界模式、媒介、标签、禁用/固定主语法和单维辅助语法 |
| world | 美术命题、年代地域、社会逻辑、形态、色板、材料链和Color Script |
| assets | 宿主entity_id或候选资产、不可改项、材料、初态与允许状态 |
| set | 单场景坐标、边界、布局实例、总数断言、功能区、画内光源与气氛 |
| events | 镜头内有序状态变化及来源/导演事件指针：DirectorIR 1.0 指向 phase，1.1/1.2 指向 timeline action |
| shots | 引用镜头ID，当前可见资产、参考、美术构图/表情支持和相对关系判据 |
| references | 真实文件、字节摘要、用途、继承边界、权利与待制作状态 |
| contract | 条款、检查、执行边界；独立Schema与ArtIR内嵌定义保持一致 |

Schema全部关闭未声明字段，禁止偷偷加入自己的camera、performance、dialogue或timeline。
每镜及其可见资产必须被适用合同条款的路径直接覆盖，资产锁定项不能只留在游离说明里。
`state_rules`只用于离散字符串状态，例如holder、wetness、door_state；连续运动归导演。
绑定 DirectorIR 1.1/1.2 的 Art 事件必须指向 `/timeline/actions/N`，且该动作覆盖 Art 镜头，`changes` 中有同一宿主实体、字段和完全一致的 `before`/`after` 字符串。Art 不另造 Director `phases`；若美术状态无法与现有动作逐字段对齐，交回导演补充动作，或只在资产设计中标为待定，不将它作为已绑定事件入链。DirectorIR 1.0 的 `/shots/N/phases/K` 指针保持原规则。
`set.counts`计布局实例，不计图片中的像素对象；物理三维连续性仍须预演/审片。

## 命令与产物

```bash
python scripts/art_compile.py validate examples/tavern.art.json
python scripts/art_compile.py route examples/product.art.json
python scripts/art_compile.py compile examples/teahouse-linked.art.json --target generic-video --out outputs/tea-v001
python scripts/art_compile.py compile examples/missing-reference.art.json --target generic-i2v --out outputs/blocked-v001
python scripts/art_compile.py verify-qa outputs/tea-v001 outputs/tea-v001/qa-report.json
```

最后两条预期退出2：缺少首帧的BLOCKED和未审素材的NOT_ACCEPTED。
输入INVALID不创建输出；合法但执行依赖缺失则输出完整可审阅阻塞包。已有非空目录不会覆盖。

编译顺序：Schema/ID/指针→导演绑定→参考字节与首帧解码→空间/状态/合同检查→硬筛选风格→
状态递推→可见资产与镜头作用域→美术正文→任务覆盖→依赖、哈希、回执和待审QA。

输出：`art-ir.json`、`visual-bible.md`、`asset-plan.json`、`prompts/<shot>.txt`、`handoff.json`、
`production-contract.md`、`constraint-coverage.json`、`route-report.json`、`dependency-index.json`、
`target-snapshot.json`、`receipt.json`、`qa-report.json`。

关键帧目标正文只表达初态；完整状态事件仍存机器合同用于视频交接，不是单图指令。
美术正文是宿主合并前的补充，不能直接当完整导演提示词或API请求。字幕、图形、参考制作任务按渠道执行。
同源字节、目标和工具版本生成相同结果；回执不注入时间戳或随机ID。

## 范围和限度

一个ArtIR只覆盖一个连续场景；多场景由宿主分别编译，统一Canon/资产ID和主视觉规范。
图像可解码不代表图像内容正确；哈希不证明授权；指针存在不证明事件语义等价；
静态相对关系记录不证明碰撞、反射、透视和遮挡成立。程序不读懂电影，也不代替导演完整校验器。
