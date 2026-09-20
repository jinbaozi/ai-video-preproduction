# 编译器与协议

## 输入

Python 3.10+，`requirements.txt` 的 jsonschema 4.x。Schema 为 Draft 2020-12，离线注册本包引用，不从网络解析Schema。
`scripts/dg.py` 集中提供 route、validate、compile、qa；不用四个内容重复的包装脚本。
所有命令从技能目录执行；可以用绝对路径从任意工作目录调用。

DirectorIR 的关键分区：

| 字段 | 责任 |
|---|---|
| sources / canon_ref / entities | 来源、上层事实指针、当前切片实体 |
| intent / scenes[].style_id | 任务、目标、风格请求和已决定场景风格 |
| scenes / start_state / end_state | 世界坐标、轴线、姿态、接触、支撑和视线 |
| beats / narrative / phases | 信息变化、故事顺序、展示顺序和整数帧阶段 |
| composition / must_show | 画面框、注意力、可见部位、必须看清的证据 |
| camera / performance / sound / dialogue | 镜头表达、具体表演与声音时间窗 |
| assets / references | 文件、哈希、实体与维度所有权、参考角色 |
| continuity / acceptance_ids / contract | 连续性前驱、要求、执行边界和验收 |

Schema严格拒绝未知字段；新增字段先修改schema、编译与测试，不能只写进JSON自称已生效。
规范版本 `1.0` 与 Skill/编译器 `1.0.0` 分开；升级若改变解释需要新版本和迁移说明。

## 编译阶段

1. 类型/版本校验，解析ID和来源。
2. 校验合同路径和检查ID、风格与任务约束、时序、可见性、初终态、轴线和基础投影。
3. 读取一个具体能力快照；按持续时间选择合法请求时长，不静默切断动作。
4. 把拍摄计划转成文本，保留本镜头信息与表演。T2V包含静态场景；I2V由首帧承载静态视觉。
5. 核对实际素材路径、文件名、sha256与批准状态，建立附件表；无已核验路径则阻塞。
6. 输出目标词法/请求体/UI字段/Agent任务、损失与语义映射。
7. 记录整数帧剪辑段与未选Take；真实源入点后续根据视频确定。

相关单镜头硬条款进入正文。跨镜头条款保留在总合同，避免把后镜头危险证据提前灌入前镜头。
每镜头 `narrative` 映射上游规定的信息变化；跨镜头信息顺序仍需人工及G4理解验收。
没有原生音频时，声轨/对白保留后期路径；触发声音的可见反应仍属于画面动作。

## 确定性与输出

输入、能力快照、注册表和编译器版本固定时，输出规范JSON相同。哈希使用排序键、UTF-8、缩进2、末尾换行。
输出目录含：

- `director_contract.json`：完整DirectorIR与合同，不丢弃源语义。
- `execution.json`：Jobs、Edit Segments、Losses、Semantic Map、静态状态。
- `capability-snapshot.json`：具体入口快照。
- `style-decision.json`：启发式路由建议；实际采用风格以IR为准。
- `technique-plan.json`：所选技法的前置条件、不可改变项、失败与验收配方，待导演复核。
- `post-production.json`：原台词、声音、剪辑帧预算及检查ID，状态NOT_RUN。
- `prompts.md`：可复制正文与实际文件名/槽位表。
- `production-contract.md`：审阅用条款及损失。
- `qa-report.json`：绑定当前哈希，全部NOT_RUN，等待真实证据。

`semantic_map.destination` 的 `JOB.prompt:Shot:field` 是有名文本区块，不是字符偏移。
`contract_review` 表示留存并审查，不能误称已进入生成参数。原件留存、文本表达、后期执行和实片验证各自有责任。

## 命令示例

```bash
.venv/bin/python scripts/dg.py compile examples/teahouse.director.json --target kling-3-ui-multishot --out outputs/tea-kling-v001
.venv/bin/python scripts/dg.py compile examples/missing-reference.director.json --target runway-gen4-ui-i2v --out outputs/missing-v001
.venv/bin/python scripts/dg.py qa examples/teahouse.director.json outputs/tea-v001/execution.json outputs/tea-v001/qa-report.json --evidence-root outputs/tea-v001
.venv/bin/python -m unittest discover -s tests -v
```

缺首帧和空QA两例预期退出2，表示门禁正常工作。
不支持自动时长拆分、语义压缩、联网提交、成本计费、视觉评分和跨项目状态同步；这些由后续执行器/审片流程完成。
未知能力不能通过构造新API字段绕过；应增加有证据的能力配置与适配代码及其回归测试。
