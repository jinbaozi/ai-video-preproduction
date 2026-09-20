# 验证记录 · v1.0.0

日期：2026-09-19。本次重新制作；不是聊天中未取得的v0.1参考包。以下为静态代码、契约及文本检查。

| 检查 | 实际结果 |
|---|---|
| Skill frontmatter与入口检查 | quick_validate通过；入口60行，保留默认自动发现策略 |
| JSON Schema | 4份Draft 2020-12 Schema有效；交接、制作合同与QA输出通过对应Schema |
| 行为/回归/发布测试 | 86项通过；含正常、反例、错误退出、不可覆盖输出和归档篡改 |
| 咖啡馆示例 | 12秒、24fps、3镜、8格；结构VALID，compile/verify通过 |
| 产品示例 | 6秒、9:16、1镜、3格，无人物/台词；结构VALID，compile/verify通过 |
| 缺硬参考示例 | 预期BLOCKED，保留可审阅计划；未伪称素材就绪 |
| 正文语义审阅 | 修正近景手部与尚未接触信封的冲突；保留原台词、等待与拿取因果 |
| 确定性 | 同一输入/基路径编译字节一致；重复打包SHA-256一致 |
| 独立解压 | 临时目录重新运行86项测试、quick_validate、CLI帮助、3个示例编译与verify通过 |
| 归档完整性 | 单根目录、成员安全、逐文件哈希、manifest和SHA-256一致 |
| 原有工作区技能 | 只读取导演、美术和AVIR契约；未修改原包 |

完整测试见[tests/test_storyboard.py](../tests/test_storyboard.py)。
发布后的实际归档哈希与成员数以dist中的manifest/checksum为准；工作区最终运行记录另存outputs/release-verification.json。
发布包包含全部测试和示例，可在无同级Skill的目录复验。运行只需Python 3.10+及requirements.txt；测试不需要图像或视频平台。

## 证据边界

十张语法卡为原创规则，29条来源带核验状态。没有从这些资料推导“已生成质量评分”。
本次没有实际分镜图片、animatic视频、口型或混音素材；visual/media QA为NOT_RUN。
未运行任何视频生成API、Hypit或OTIO，也没有将新handoff直接传给AVIR编译器。
当前AVIR字段映射已文档化，自动转换及真实入口联调尚未实现。固定轴、声明画框和状态检查不等于完整三维碰撞/遮挡或摄影投影验证。
