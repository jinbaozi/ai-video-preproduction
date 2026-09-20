# 实际采用的来源

2026-09-19 新增的附件溯源、逐项采纳边界、四类后端与评测论文核验见 [研究采纳记录](research-adoption.md)。下列旧快照保留原日期，不代表本次重新核验全部字段。

本文件记录创建与更新技能时实际支撑规则的资料。GPT-Image-2 与 OpenAI 图像工作流核验日期：2026-08-20；其他资料最近核验日期：2026-08-01。模型能力会变化；使用专属语法时仍须重新打开对应官方页面核对。

## 模型官方资料

- [OpenAI Image generation guide](https://developers.openai.com/api/docs/guides/image-generation)：文本／图像输入、生成与编辑、输出配置边界，以及低延迟时的质量、画幅和格式建议。
- [OpenAI GPT-Image-2 model page](https://developers.openai.com/api/docs/models/gpt-image-2)：模型版本、输入输出与能力入口。
- [OpenAI Create image API reference](https://developers.openai.com/api/reference/resources/images/methods/generate/)：当前尺寸、质量、格式等字段；未列独立 `negative_prompt`。
- [OpenAI Edit image API reference（Python 请求参数）](https://developers.openai.com/api/reference/python/resources/images/methods/edit)：多图编辑、遮罩语义、编辑字段，以及 GPT-Image-2 的灵活 `WIDTHxHEIGHT` 请求尺寸。
- [OpenAI Responses API image tool](https://developers.openai.com/api/docs/guides/tools-image-generation)：对话式生成／编辑、`action` 与 `revised_prompt`。
- [OpenAI GPT Image prompting guide](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide)：一致结构、摄影语言、真实纹理与用途导向。
- [OpenAI Codex image generation](https://developers.openai.com/codex/image-generation)：1—3 句提示、生成／编辑分流、参考图角色、精确文字、信息密集型版式与单变量迭代。
- [OpenAI Academy: Image generation](https://openai.com/academy/image-generation/)：简短提示、迭代修改和实际使用范式。
- [OpenAI Image Evals](https://developers.openai.com/cookbook/examples/multimodal/image_evals)：用硬约束与可复核标准评估生成结果。
- [Google Gemini Image generation](https://ai.google.dev/gemini-api/docs/image-generation)：支持语言、画幅／尺寸、参考图和图像模型差异。
- [Google Imagen via Gemini API](https://ai.google.dev/gemini-api/docs/imagen)：英文提示限制、配置字段及弃用／迁移信息。
- [Midjourney Prompt Basics](https://docs.midjourney.com/hc/en-us/articles/32023408776205-Prompt-Basics)：文本提示与参数位置。
- [Midjourney Parameter List](https://docs.midjourney.com/hc/en-us/articles/32859204029709-Parameter-List)：当前参数导航，包括画幅、排除和参考功能。
- [Midjourney Image Prompts](https://docs.midjourney.com/hc/en-us/articles/32040250122381-Image-Prompts)：参考图输入与文本配合方式。
- [Stability AI REST API](https://platform.stability.ai/docs/api-reference)：`prompt`、`negative_prompt`、`aspect_ratio` 及不同图像端点。
- [Stability AI Release Notes](https://platform.stability.ai/docs/release-notes)：端点、模型与能力变更核验。

## 摄影与后期资料

- [Canon：人像镜头与焦段](https://www.canon-europe.com/get-inspired/tips-and-techniques/portrait-lenses-tips-tricks/) 与 [焦距和视角](https://www.canon-europe.com/pro/infobank/understanding-focal-length/)：人像焦段、拍摄距离、视角与透视关系。
- [Nikon：焦距基础](https://www.nikonusa.com/learn-and-explore/c/tips-and-techniques/understanding-focal-length)：焦距与视野的基础说明。
- [Canon：景深](https://www.canon-europe.com/pro/infobank/depth-of-field/) 与 [光圈](https://www.canon-europe.com/pro/infobank/aperture/)：光圈、焦段、距离和景深的共同作用。
- [Canon：自然人像建议](https://www.canon-europe.com/get-inspired/tips-and-techniques/portrait-photography-tips/)：互动、动作与自然表情。
- [Profoto：环境光、轮廓光与柔光补光](https://www.profoto.com/int/en/still-photography/tips-tricks/3-best-modifiers-for-on-location-photography) 与 [软硬光原理](https://www.profoto.com/int/en/still-photography/profoto-stories/flash-photography-for-beginners-profoto-a1x)：光源尺寸、柔硬度、补光和主体分离。
- [Adobe Camera Raw：白平衡与色调](https://helpx.adobe.com/camera-raw/desktop/using/make-color-tonal-adjustments-camera.html)：色温、色调与后期调整顺序。
- [Canon：自然肤色](https://www.canon-europe.com/get-inspired/tips-and-techniques/capturing-natural-skin-tones/)：肤色、曝光与皮肤细节。
- [Adobe：自然皮肤修饰](https://helpx.adobe.com/ca/photoshop-express/using/apply-smooth-skin.html)：避免过度磨皮。

## 视觉科学与自然观看

- [MIT Vision Book：透视成像](https://visionbook.mit.edu/imaging.html) 与 [遮挡边界](https://visionbook.mit.edu/simplesystem.html)：单幅照片由一个投影中心形成，前后关系通过共同边界和遮挡成立；据此检查单一视点、尺度、透视和接触边界。
- [Canon：景深](https://www.canon-europe.com/pro/infobank/depth-of-field/)：景深由焦段、光圈、拍摄距离等共同决定；据此要求一个主要焦区，让离焦程度随物体相对焦平面的位置连续变化，不按语义切割主体与背景。
- [OpenStax：反射定律](https://openstax.org/books/university-physics-volume-3/pages/1-2-the-law-of-reflection)：入射、表面法线和观察位置共同决定镜面反射；据此约束屏幕、玻璃和镜面的高光与可见内容。
- [Land：日常活动中的眼动与动作控制](https://pubmed.ncbi.nlm.nih.gov/16516530/)：人类视觉在日常任务中通过主动、任务相关的眼动获取信息；据此禁止把一张静态图片声称为完整复刻肉眼观看过程。
- [Anstis：周边视敏度的图像化研究](https://doi.org/10.1068/p270817) 与 [Strasburger 等：周边视觉研究综述](https://pubmed.ncbi.nlm.nih.gov/22207654/)：中央与周边视觉的空间处理能力不同；据此使用注意力层级，不把人眼感简化为鱼眼、固定径向模糊或全画面同锐。
- [Purves 等：眼动与感觉运动控制](https://www.ncbi.nlm.nih.gov/books/NBK10991/) 与 [Bernal-Molina 等：调节状态下的人眼景深](https://pubmed.ncbi.nlm.nih.gov/25148219/)：双眼汇聚、调焦和瞳孔属于联动近距反应，人眼景深并非固定摄影光圈；据此只描述唯一注视目标和连续摄影焦深。
- [StatPearls：中央凹的解剖与高视敏度](https://www.ncbi.nlm.nih.gov/books/NBK482301/) 与 [Purves 等：深度知觉线索](https://www.ncbi.nlm.nih.gov/books/NBK11512/)：眼球会把关注目标移到中央凹，遮挡、相对尺度、阴影和双眼差异共同提供深度；据此把注意力与相机景深分开，并检查单一空间关系。
- [Cooper、Piazza 与 Banks：自然透视的观看几何](https://jov.arvojournals.org/article.aspx?articleid=2192052)：所谓“自然”焦距取决于照片尺寸与观看距离的几何关系，不是固定的人眼焦距；据此禁止把 50mm 当作普适人眼参数。
- [Kunkel 与 Reinhard：人类视觉系统同时动态范围再评估](https://dl.acm.org/doi/10.1145/1836248.1836251) 与 [Radonjić 等：人类明度知觉动态范围](https://pubmed.ncbi.nlm.nih.gov/22079116/)：同时亮度知觉受背景、上下文和适应状态影响；据此使用曝光锚、高光滚降、真实黑位和选择性暗部细节，不写固定“人眼 HDR 档数”。
- [Sony：焦距、视角与透视](https://www.sony.com/en-ye/electronics/focal-length-angle-of-view-perspective)：同一机位的透视关系不由单独更换焦距改变；据此先定机位与距离，再用焦段表达取景。
- [Brainard 与 Wandell：自然图像中的颜色恒常性](https://stanford.edu/~wandell/data/papers/BrainardWandell1986.pdf) 与 [非对称配色实验](https://stanford.edu/~wandell/data/papers/BrainardWandell1992.pdf)：颜色恒常性依赖照明与场景上下文且并不完美；据此固定主白平衡意图，同时保留有动机的局部混合光。
- [Moran CORE：Hirschberg 角膜反光与眼位评估](https://morancore.utah.edu/basic-ophthalmology-review/alignment-assessment-hirschberg/) 与 [Barsingerhorn 等：角膜反光眼动追踪误差](https://pmc.ncbi.nlm.nih.gov/articles/PMC5330588/)：眼神光来自外部光源，但会随角膜、头位和注视改变；据此要求双眼来源对应而非机械复制。
- [Madison 等：阴影与互反射对接触判断的作用](https://link.springer.com/article/10.3758/BF03194461)：接触阴影和互反射显著帮助判断物体是否落地；据此检查手—道具、身体—座椅和脚—地面的附着关系，避免漂浮与黑色描边式环境遮蔽。
- [NIST：Display performance under ambient illumination](https://www.nist.gov/system/files/documents/2023/01/19/Penczek-Optical.pdf)：环境光会影响屏幕黑位、对比、色域和眩光；据此约束白天或斜视角屏幕的贴图感、反射和饱和度。

## 开源结构与反例研究

- [OpenAI Cookbook 图像提示指南源码](https://github.com/openai/openai-cookbook/blob/main/examples/multimodal/image-gen-models-prompting-guide.ipynb)：采用目标导向和结构化提示；不把单一模型参数当通用语法。
- [OpenAI imagegen 技能源码](https://github.com/openai/skills/blob/main/skills/.system/imagegen/SKILL.md)：借鉴生成／编辑意图分流、资产类型分类、渐进披露、逐图角色和编辑不变量。
- [wuyoscar/GPT-Image2-Skill](https://github.com/wuyoscar/GPT-Image2-Skill)：借鉴生成、编辑、素材组合的任务分流；不采用未经官方核验的参数或能力承诺。
- [freestylefly/awesome-gpt-image-2](https://github.com/freestylefly/awesome-gpt-image-2)：用于观察社区常见任务、提示结构和失败模式；不把提示词合集当作官方规范。
- [YouMind-OpenLab/awesome-gpt-image-2](https://github.com/YouMind-OpenLab/awesome-gpt-image-2)：用于交叉检查复杂场景和多轮修订实践；拒绝“固定模板必然更优”的推论。
- [NanoPrompts GPT-Image-2 Portrait Handbook](https://nanoprompts.org/gpt-image-2/prompt-handbook/portrait)：借鉴塑料皮肤、眼镜反光、深肤色偏色、年龄漂移和卷发边缘等定向修复；不采用魔法词或成功率承诺。
- [agency-agents Image Prompt Engineer](https://github.com/msitarzewski/agency-agents/blob/main/design/design-image-prompt-engineer.md)：借鉴主体、环境、光线、摄影技术的模块拆分；拒绝其过长入口、固定参数、摄影师姓名和强制负面提示做法。
- [Hugging Face Diffusers](https://github.com/huggingface/diffusers)：确认本地 pipeline 参数属于具体实现，不等于 Stability 托管 API。
- [YouMind ai-image-prompts-skill](https://github.com/YouMind-OpenLab/ai-image-prompts-skill)：借鉴按需加载的分类资源；不采用其强制联网、提示复用和“任意模型通用”假设。

官方资料之间出现冲突时，优先采用当前总览指南与对应端点的模型专属请求参数参考／schema，再依次采用模型页、官方通用指南、官方单个示例与社区经验。当前已记录：Cookbook 的 `<3840` 与指南／生成参考列出的 `3840x2160` 冲突，按当前高优先级资料采用 `<=3840`；部分通用响应对象或联合类型仍只枚举旧固定尺寸，但 Python／CLI edits 请求参数明确支持 `gpt-image-2` 合法 `WIDTHxHEIGHT`，请求能力以模型专属请求参数说明为准并核验下载文件像素。社区资料只用于发现任务结构和失败模式，不能覆盖官方字段、能力或限制。

只在实际回答引用某条现行能力时输出相应直接链接；不要把本页全部来源复制给用户。


## 2026-09-08：视觉锚点与非 API 路径

- OpenAI 图像提示指南：https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide 。支持具体描述、摄影语言、纹理与编辑不变量；未证明 Astra 专属增益。
- OpenAI Image API 指南：https://developers.openai.com/api/docs/guides/image-generation 。仅用于 API 控制边界，不推导聊天端最高分辨率。
- Profoto 白／银美人碟：https://www.profoto.com/int/en/still-photography/tips-tricks/choose-between-white-and-silver-beauty-dish 。摄影布光的一手演示，支持光质与纹理表现的关系。
- Clip Studio / Hyanna Natsu：https://www.clipstudio.net/how-to-draw/archives/161517 。发型绘画与形状组织。
- Clip Studio / miyuli：https://www.clipstudio.net/how-to-draw/archives/157926 。织物、受力与褶皱。
- Clip Studio / Grace Zhu：https://www.clipstudio.net/how-to-draw/archives/162569 。发光插画技法。
- X 搜索发现 https://x.com/liyue_ai/status/2088297669982843181 ，打开未取得正文，未作为验证依据。
- 中文社区搜索结果与提示词合集仅作发现线索，不据此声称参数支持或效果已验证。

混合媒介四条建议由用户提供；区域合同、瑕疵预算及五个完整示例是本次设计综合，未经生图对照实验。
- Adobe 合成教程：https://www.adobe.com/au/learn/photoshop/web/photography-effects 。支持光影、透视、尺度和取景的合成匹配。
- Adobe VHS效果教程：https://www.adobe.com/creativecloud/video/hub/features/add-a-vhs-effect-in-premiere-pro.html 。支持将VHS外观拆为颜色、形变与噪声效果；本技能将其转译为静态图的局部外观要求，不执行视频处理。

## 2026-09-11：真实人像照片感

本轮会话检索并读取以下资料。摄影参数到提示词的映射、四类片段和 A/B/C 评估流程为设计综合，未完成生图增益实验。

- [OpenAI GPT-image-1.5 提示指南](https://developers.openai.com/cookbook/examples/multimodal/image-gen-1.5-prompting_guide)：摄影语言、具体纹理优于泛化质量词的指导；不用于证明其他模型版本的参数能力。
- [Canon 人像教程](https://www.canon-europe.com/get-inspired/tips-and-techniques/portrait-photography-tips/)：构图、自然动作、闪光主体与慢快门环境曝光。
- [Adobe 人像教程](https://www.adobe.com/creativecloud/photography/discover/portrait-photography.html)：被摄者状态、光线与环境。
- [Nikon 焦距说明](https://www.nikonusa.com/learn-and-explore/c/tips-and-techniques/understanding-focal-length)：焦距与取景。
- [Adobe 快门](https://www.adobe.com/creativecloud/photography/discover/shutter-speed.html)、[白平衡](https://www.adobe.com/creativecloud/photography/discover/white-balance.html)、[ISO](https://www.adobe.com/creativecloud/photography/discover/iso.html)：实拍参数基础；不采用 ISO 改变进光量的简化说法，不推导 AI 参数执行保证。

检索未获得文件名、伪 EXIF 或相机型号具有稳定生成增益的可靠对照证据，不将其列为有效性事实。

## 2026-09-12：去噪、真人感与受控成像

本轮会话由 luna_worker 联网检索并打开以下一手资料，随后用于规则更新。以下区分官方示例、摄影因果推导与待生图实测；不更新前文未重新核验的模型字段或能力日期。

| 来源 | 支持的事实与采用范围 | 证据边界 |
| --- | --- | --- |
| [OpenAI Image prompting](https://developers.openai.com/api/docs/guides/image-prompting) | 写实示例使用自然皮肤纹理、适度颗粒、自然色彩及避免重度修饰；相机规格是外观线索 | 官方明确示例；不证明瑕疵词的通用收益或精确物理执行 |
| [ChatGPT Image generation](https://learn.chatgpt.com/docs/image-generation) | 具体视觉语言、参考图和改变／保持的编辑表达 | 官方工作流建议；不把 API 字段迁移为聊天端控制 |
| [Adobe Camera Raw：锐化与降噪](https://helpx.adobe.com/ca/camera-raw/desktop/using/sharpening-noise-reduction-camera-raw.html) | 亮度／色度噪声、细节保护、过度锐化或降噪的取舍 | 摄影因果推导；本技能不执行 Camera Raw 或真实像素降噪 |
| [Nikon：ISO](https://www.nikonusa.com/learn-and-explore/c/tips-and-techniques/understanding-iso-sensitivity) | 数字噪声与胶片颗粒来源不同，设备和处理影响成像 | 摄影因果推导；ISO 不是生成颗粒滑块，也不是噪声唯一成因 |
| [Nikon：闪光摄影基础](https://www.nikonusa.com/learn-and-explore/c/tips-and-techniques/the-basics-of-flash-photography) | 正面直闪可能照平面部，产生反光和背景硬阴影；方向和反射面改变光质 | 摄影因果推导；不能据此声称直闪必然降低 AI 感 |
| [Sony：快门与 S 模式](https://www.sony.com/electronics/support/articles/00267929) | 快门与主体／相机运动共同影响模糊 | 摄影因果推导；不能只凭提示词快门值保证某部分完全冻结 |
| [Adobe Lightroom Classic：修饰](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/retouch-photos.html) | 高反差边缘色差及光学校正 | 摄影因果推导；不把全图彩边当作真实感前提 |
| [Canon：镜头技术](https://files.canon-europe.com/files/webcontent/rf-lens-world/features/technology/index.html) | 镜头设计抑制色差、眩光与鬼影；内部反射与强光相关 | 摄影因果推导；干净锐利同样可以真实 |
| [Fujifilm：Light Leak 设计](https://design.fujifilm.com/en/stories/006/) | 胶片受光效果的采样与模拟 | 摄影风格来源；与正常逆光眩光分开，不推导模型执行机制 |
| [Kamali 等：人类识别合成图像研究，2025](https://arxiv.org/abs/2502.11989) | 解剖、风格、功能、物理和社会文化线索；人类来源判断有局限 | 原始研究；用于评价维度，不输出来源概率，不证明当前 image_gen 的固定缺陷 |
| [Hu 等：角膜高光一致性，2020](https://arxiv.org/abs/2009.11924) | 特定条件下的 GAN 人脸高光线索 | 旧模型与受限光照／视角研究；不要求双眼高光机械一致，不直接外推当前模型 |

“保留纹理的清洁约束”“有条件启用成像瑕疵”和三类描述的单项消融均为项目设计综合，状态为待生图实测。参考规则、文本行为回归与尺寸单元测试通过，也不能升级为图像质量或模型增益已验证。

## 用户提供的人像机位总结（2026-09-15）

本次依据用户粘贴的总结整理，未独立读取或核验其所链接的 [南鸢 nuyoah 文章](https://x.com/nanyuan0412/status/2099683245726355869)。总结归于原文的内容是机位、景别与注意力控制；七变量框架、受力／材质扩展、模块模板及修订诊断为总结中的延伸分析，不归于原作者。对应规则见 [人像机位与视觉目标](portrait-camera-and-framing.md)。示例配图不是受控实验，景别名称没有跨体系统一裁切线，单次生成差异不证明焦段或提示词的因果收益。
