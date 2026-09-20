# 交付与验证记录

版本：1.0.0。检查日期：2026-09-19。

## 实际完成

- 标准Skill入口与UI元数据，按需披露的导演知识、制作合同与现有工作流接入说明。
- 12种风格、18项技法、引用对话中的20位导演检索映射、9个明确区分能力边界的目标档案。
- 5份JSON Schema：DirectorIR、制作合同、ExecutionIR、QA、Edit Manifest。
- 可执行的校验、风格检索、确定性编译、证据核对、Hypit本地Take装配导出及确定性打包。
- 三个完整输入示例：15秒悬疑、6秒非叙事教学、缺失首帧。

## 已运行的检查

| 检查 | 结果 | 能证明什么 |
|---|---|---|
| skill-creator quick_validate | PASS | 入口与frontmatter符合校验器规则 |
| Draft 2020-12 schema检查与3例语义校验 | PASS | 本版结构/静态不变量 |
| unittest | 33/33 PASS，无跳过 | 路由、时间预算、负向输入、媒体门禁、编译/QA行为 |
| MiniMax茶馆静态编译 | PLANNED，3个6秒任务，剪辑总360帧 | 请求时长与15秒成片预算分离，未提交 |
| 缺首帧、度量相机、未知入口 | BLOCKED | 不伪造可执行能力，不静默丢弃要求 |
| Hypit 0.1.10 Author check | ok=true，2 units/1 asset/17 modules | 导出的源可被当前版本读取 |
| Hypit 0.1.10 Run check | ok=true，target=final.video | Run引用与输出结构有效 |
| Hypit 0.1.10 plan | ok=true，5 requests/0 request issues | 图上为本地媒体处理与渲染计划，未执行 |

Hypit测试使用FFmpeg生成的灰色视频+静音：1280×720、24fps、144帧；回归测试用64×64版本。
它们是协议测试素材，不是导演样片；没有把灰色视频作为“动作教学质量通过”的证据。
QA正向测试只验证合成记录完整性；语义质量并未由脚本观察。

## 独立前向测试与修复

两轮独立测试复现并修复，最终针对性复核通过：教学例串用茶馆路径/来源；教学范围未进硬条款；普通文本冒充视频证据；
同图首尾帧角色合并；声音硬要求落入无原生音频请求；普通文本冒充首帧。
相应回归包括角色不丢失、图像解码、ffprobe视频检查、原生能力不得静默后期替代、跨镜头信息不提前泄露。

## 尚未声称完成的能力

没有模型API调用、附件上传、付费生成、平台账号实测、Hypit build/成片渲染或真实导演质量评测。
Runway/Kling是UI计划；即梦/OiiOii/Seko执行入口未锁定。Hypit仅装配已裁切Take。
完整三维投影、遮挡/碰撞、音画语义理解、真实空间连续与微表情质量仍需关键帧/预演和实际素材审核。
编译器不做自由语言推理；是否完整表达原意需要导演复核，不能由STATIC_PASS替代。

## 复现与打包

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/package_skill.py --out dist
.venv/bin/python scripts/package_skill.py --verify dist/director-grammar.skill
```

标准包为 `director-grammar.skill`、`director-grammar.skill-manifest.json`、`director-grammar.skill.sha256`。
归档含单一根目录、固定时间戳、逐文件哈希，排除输出与缓存；manifest保留本次归档精确哈希。
交付验证还需在临时目录解包重跑测试和CLI，并比较同源重复构建哈希。
