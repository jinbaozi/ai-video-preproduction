# 1.2.0 制作验证记录

日期：2026-09-19。范围：附件研究采纳、Skill规则、制作合同、校验脚本与可分发包；不包含实际生图或供应商API执行。

## 已执行

- Skill Creator `quick_validate.py`：通过。
- `python3 -m unittest discover -s tests -p 'test_*.py'`：36项通过，其中30项合同测试、6项既有尺寸测试。
- `python3 scripts/validate_production_contract.py examples/production-contract.json`：`STATIC_VALID`。合同示例的视觉验收保持`NOT_RUN`。
- Python脚本编译与当前Markdown本地链接检查：通过。
- 代表性成稿已编写并由本次制作Agent自审：单幅台词/心理上下文、三格交杯连续性、同意图跨模型正文，见[完整成稿](../examples/narrative-and-backends.md)。不将自审写成独立Agent盲测。

合同测试覆盖有效/非法输入、未知字段、源引用与未读来源、硬项丢失/改写、源原话改写、软字段合法修订、空间关系/时序循环、局部交叉遮挡不误报、主体坐标归属、文字/说话人、未知原生参数、负面机制、能力来源、阻断记录、步骤依赖、视觉证据、尺寸方向和CLI退出码。

## 检查中发现并修复

- 旧打包器写死版本号：改为读取Skill metadata，使包与Skill版本一致。
- 局部互相遮挡不应被当成空间错误：区分局部`occludes`与完全`fully_occludes`，并新增回归用例。
- 人物自身左右需要明确坐标主人：新增`coordinate_owner`，防止不同参照系误混。
- 附件的无版本T2I-CompBench链接已指向扩展版：按实际论文版本记录，未照搬旧数据集数量。

## 尚未执行或不作证明

- [16项前向行为案例](production-contract-forward-cases.md)为后续Agent实测集合，未宣称全部执行通过。
- 未生成图片，未完成跨厂商A/B、图像质量评分、身份相似度、实际成本/延迟或视觉提升测量。
- 校验器不能判断自然语言语义真伪、图片真实来源、引用内容真实性、模型当前能力或实际视觉合格；它只检查已实现的结构与追踪不变量。
- `.skill`发布包的哈希和文件清单以`dists`内同名manifest与SHA-256文件为准；包不含Downloads中的报告原件，研究映射已自包含。
