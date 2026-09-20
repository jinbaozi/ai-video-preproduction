# 来源与覆盖范围

本次读取了用户引用对话的全部两轮文本；接口返回无可访问附件，因此没有冒充取得此前“18文件设计包”。
本技能根据该设计方案与当前核验重新实现。导演20人索引来源于引用对话，其映射标为本项目检索配方，不宣称重新验证影史排名。

核验日期：2026-09-19。机器索引见 `registries/evidence.json`，每条记录有版本、主张和核验范围。

| 来源 | 本次用途与边界 |
|---|---|
| [引用对话](chatgpt-conversation://6aadc843-aca4-83e8-a176-dd65aa2de97f) | 两级IR、三类注册表、制作合同、20位导演检索范围 |
| [DirectorSKILL](https://github.com/wuwangzhang1216/DirectorSKILL/blob/main/SKILL.md) | 参考导演知识按需组织；本包未复制其正文/模板/代码 |
| [Seedance社区Skill](https://github.com/Emily2040/seedance-2.0/blob/main/SKILL.md) | 参考入口、参考维度和任务区分思路；社区资料不作为API权威 |
| [MiniMax官方API](https://platform.minimax.io/docs/api-reference/video-generation-t2v) | 本包选定T2V参数与运镜词法，无接口/成片测试 |
| [Runway Gen-4指南](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide) | I2V文字形态与UI时长，不据此输出API请求 |
| [Kling VIDEO 3.0指南](https://app.klingai.com/cn/quickstart/klingai-video-3-model-user-guide) | 自定义多镜头UI说明，不代表所有第三方网关 |
| [LibTV官方Skill仓库](https://github.com/libtv-labs/libtv-skills) | 会话message形状，非内部导演实现 |
| [Seedance官方发布资料](https://seed.bytedance.com/zh/blog/official-launch-of-seedance-2-0) | 模型与产品入口区分，未锁定当前即梦账号 |
| [OiiOii文章](https://articles.oiioii.ai/how-to-make-an-animated-music-video-with-ai-2) | 官方站点创作分工；首页读取失败，未得到可调用协议 |
| [Seko公开页面](https://seko.sensetime.com/explore) | 产品上下文；未得到可调用协议，不断言平台不存在API |
| [Hypit仓库](https://github.com/hypit-ai/hypit) | 本机0.1.10与安装包协议交叉读取，导出/检查范围见verification |

编译器、JSON Schema、制作合同、技法条件、空间规则与测试为本项目新增实现。
未复制外部开源项目代码；若后续引入代码、素材或字体，另行保留对应许可与署名。
网页main分支为浮动快照；重要外部执行前复核。没有以搜索摘要替代当前调用契约。
