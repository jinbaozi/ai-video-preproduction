# 平台与 Hypit 交接

本包不持有平台能力权威，不复制director-grammar的能力注册表。`targets.json`是离线交接目标，
不是平台API适配器。全部固定 `execution_implemented=false/runnable=false/api_submission_allowed=false`。

| 目标 | 交接重点 | 实际执行前由宿主核验 |
|---|---|---|
| generic-keyframe | 当前状态、主体、资产、布景、美术可读性 | 真实图片入口及导演视点 |
| generic-video / generic-i2v | 美术约束与只读导演上下文；I2V需要每镜首帧 | 模型模式、真实上传与字段 |
| LibTV | 美术命题、资产职责、不可改项、验收清单 | 当前客户端Skill与会话协议；平台二次规划需复核 |
| OiiOii / Seko | 场景/角色/道具与镜头关联 | 实际节点/Skill入口与可调用方式 |
| 即梦 / Seedance | 按镜筛选参考维度 | 即梦、豆包、火山或聚合服务不能混用能力 |
| Kling | 内部资产到实际元素引用的映射 | 元素ID、模型与模式；asset_id不是Element ID |
| 海螺 / MiniMax | 资产、状态及增强前合同 | 具体模型/参考格式；增强文本作为新版本核对 |
| Runway / Veo | 主体、场景、风格参考的用途分离 | 对应模型的图像/视频入口，不能跨模式推断 |
| Hypit | 宿主合并后的美术约束、资产和版本依赖 | 原生Author/Run/Runtime契约及显式素材复用 |

平台信息只作为接入问题索引。未读取当前入口文档时不填附件数量、分辨率、秒数、费用或原生镜头控制。
准确键为供应商+产品入口+模型+模式+文档版本+区域+权限；平台品牌名不够。
由宿主返回可核查的上传对象ID与槽位，不能把本包UNRESOLVED当可用参数。

## Hypit 边界

官方[运行文档](https://hypit.ai/quickstart/run/)区分Author、Run与Runtime，并要求跨Build用显式Candidates复用；
`plan`与真正提交的`build`不同。本包生成`hypit-handoff`供宿主消费，不导出伪SVML，也不调用build。
需要原生转换时，在宿主合并DirectorIR和ArtIR之后调用已经验证的转换器，并对具体版本另做check/plan。
现有director-grammar的本地Take装配导出不是本包自动具备的能力。
