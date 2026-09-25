## 结论：Request changes，但本轮运行验收尚未完成

已通过 GitHub 查询确认目标为：

```text
提交：ffe3e170a9e889772696cb0a01318a46b980595d
父提交：0c0257ae1d1c1dc4d6288d5154bd5e7ab5875d61
标题：Archive independent approval and remaining review boundaries
```

当前 `joint_compile.py` 的 Git blob 为：

```text
8ade41c58d834b12ae39443ba78d906ebc2323c8
```

该文件与目标提交目录中的记录一致，不是浮动 `main`。 

**本轮不能给出联合链路已通过的结论。** 恢复后的执行工具调用没有返回可读结果，无法确认脚本运行结果及新文件是否落盘。因此，下面区分**已取回源码中的确定性校验缺口**与**未完成的运行验证**，不新增任何独立测试通过数，也不将前次 122/122 搬到本次。

---

## 一、需要修复：布尔／数值区分没有覆盖 `verify-compile`

### C01 · P1：联合编译复验仍可能接受 `n=true` 替换 `n=1`

**精确位置：**

```text
video-prompt-compiler/scripts/shot_control/joint_compile.py
verify_export()，第 253–272 行
关键比较：第 266–269 行
```

该函数重编译原始输入后，对单请求和总编译文件仍使用普通 Python 深比较：

```python
if read(confined(out, prefix+'.json')) != request or ...:
    raise ValueError(...)

if set(manifest['files']) != expected or \
        read(confined(out, 'joint-compile.json')) != result:
    raise ValueError(...)
```

这里没有使用本轮新增的 `same_json_value()`，也没有先对联合编译输出执行能够区分 boolean／number 的完整 Schema 校验。

相比之下，`package.py` 已经明确区分布尔和数值，并将该比较用于冻结帧和控制包派生 JSON。**问题不是新比较器没有生效，而是同一规则没有覆盖联合编译这个消费者。**

### 有效前置与最小变更

前置必须是一个已经通过 `verify_export()`、状态为 `COMPILED_DRAFT` 的真实联合编译导出目录。不能使用缺字段的手写请求。

只在该目录副本中进行如下修改：

```text
REQUEST_001.json：
    parameters.n       1 → true
    payload_draft.n    1 → true

joint-compile.json 中对应 requests[0]：
    parameters.n       1 → true
    payload_draft.n    1 → true
```

提示词、原 AVIR、控制包、素材、请求时间范围均不修改；只重算这两个 JSON 文件的清单 SHA-256。

### 当前实现推导与预期结果

**源码推导：**Python 的普通容器相等判断会把对应位置的 `True` 和 `1` 视为相等。因此，重编译仍得到整数 `1`，却不能通过上述两处比较发现导出文件已经变成布尔值。重封后的文件哈希检查也只能证明“文件与新清单一致”，不能补上类型验证。

**这不是本轮取得的运行回执。** 我没有将它计为“实跑复现成功”；它是由已取回源码和比较语义得出的确定性缺口。

**预期：**这种类型变化必须被拒绝。`VERIFIED` 不能覆盖已经偏离编译产物类型的载荷，即使值在 Python 的宽松比较中相等。

### 修复建议与验收门

在 `verify_export()` 的单请求及总产物比较中使用统一的类型敏感比较，并对联合编译产物建立完整 Schema 校验。参数、范围、状态和执行标志都应覆盖，不能只修 `n`。

验收门如下：

| 用例 | 应有结果 |
|---|---|
| 合法导出文件原样复验 | 通过 |
| `parameters.n / payload_draft.n: 1→true`，重封清单 | 拒绝 |
| `scope.start_ms: 0→false`，重封清单 | 拒绝 |
| `submitted: false→0`，重封清单 | 拒绝 |
| 合同允许的数值 `0→0.0` | 按既定数值等价规则处理 |
| 改正文、附件编号、素材摘要或范围 | 继续拒绝 |

不要依赖清单哈希代替重派生的类型一致性检查。

---

## 二、可运行的定点复现脚本——本轮未执行

以下脚本不创建另一套 AVIR，也不模拟编译器。它要求先提供**当前源码实际生成的有效联合编译导出目录**，验证正例，再修改副本；原始输入和导出目录不变。

```python
#!/usr/bin/env python3
"""检查 verify-compile 是否接受 boolean/number 类型混淆。

前置：--compiled 是已完成原生制作链并导出的 COMPILED_DRAFT。
本脚本不联网、不调用模型、不修改原导出目录。

用法：
python repro_compile_boolean.py \
  --compiler /path/to/video-prompt-compiler \
  --compiled /path/to/compile-output
"""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True,
            indent=2, allow_nan=False
        ) + "\n",
        encoding="utf-8",
    )


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): sha256(p)
        for p in root.rglob("*") if p.is_file()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--compiled", required=True, type=Path)
    args = parser.parse_args()

    compiler = args.compiler.resolve()
    original = args.compiled.resolve()
    sys.path.insert(0, str(compiler / "scripts"))
    from shot_control.joint_compile import verify_export

    baseline = verify_export(original)
    if baseline.get("compile_status") != "COMPILED_DRAFT":
        raise RuntimeError(
            "前置不成立：原导出目录不是有效 COMPILED_DRAFT"
        )

    before = snapshot(original)
    with tempfile.TemporaryDirectory(
        prefix="joint-compile-bool-audit-"
    ) as temp:
        target = Path(temp) / "export"
        shutil.copytree(original, target)

        aggregate = read(target / "joint-compile.json")
        selected = next(
            r for r in aggregate["requests"]
            if r["status"] == "COMPILED_DRAFT"
            and type(r["parameters"].get("n")) is int
            and r["parameters"]["n"] == 1
        )
        request_path = target / (selected["id"] + ".json")
        individual = read(request_path)
        if individual != selected:
            raise RuntimeError("前置不成立：单请求与总产物不一致")

        for request in (selected, individual):
            if type(request["payload_draft"].get("n")) is not int:
                raise RuntimeError("前置不成立：payload.n 不是整数")
            request["parameters"]["n"] = True
            request["payload_draft"]["n"] = True

        write(target / "joint-compile.json", aggregate)
        write(request_path, individual)

        manifest_path = target / "compile-manifest.json"
        manifest = read(manifest_path)
        for name in manifest["files"]:
            manifest["files"][name] = sha256(target / name)
        write(manifest_path, manifest)

        try:
            result = verify_export(target)
        except (ValueError, TypeError) as exc:
            print(json.dumps({
                "case": "resealed_boolean_n",
                "result": "REJECTED",
                "message": str(exc),
            }, ensure_ascii=False, indent=2))
            code = 0
        else:
            print(json.dumps({
                "case": "resealed_boolean_n",
                "result": "TYPE_CONFUSION_ACCEPTED",
                "verification": result,
            }, ensure_ascii=False, indent=2))
            code = 1

    if snapshot(original) != before:
        raise RuntimeError("原导出目录发生变化")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
```

这只是本轮缺口的定点复现入口，**不能替代你要求的完整 `stage→receive→compile→verify-compile` 回归**。

---

## 三、本轮已验证／未验证边界

| 对象 | 本轮状态 |
|---|---|
| 精确提交、父提交及控制目录 blob | 已从 GitHub 读取 |
| `package.py` 的布尔敏感比较实现 | 已读取源码；未完成独立运行矩阵 |
| `render_blocking.py` 新排布及旧排布分支 | 已读取源码；未完成浏览器验证 |
| 新旧 HTML/SVG 混合、伪标记、篡改重封 | 未完成独立运行 |
| 原 N03/N04 媒体、旧生产包、8 ULP | 本轮未重放，不新增通过结论 |
| **F02 同源 stage→receive→compile→verify-compile** | **未取得可核验运行结果，不标通过** |
| F01 损坏 PNG 在完整联合链中的回归 | 未验证 |
| F03 reference scopes／edit base 在完整联合链中的回归 | 未验证 |
| 正式 Skill 隔离安装、嵌入一致性、重复构建 | 未验证 |
| CPU 视频、全部交付帧及播放过程 | 本轮未查看，不引用作者观察作为我的观察 |

本轮尝试生成报告与脚本归档，但没有取得文件存在性和内容校验结果，**因此没有可确认的下载证据包**。上述报告和脚本直接保留在回复中，不提供未经确认的下载链接。

**最终意见仍为 Request changes：先把类型敏感的重派生比较覆盖到 `verify-compile`，再完成联合链路的运行验收。** 当前结果既不关闭旧 F01–F03，也不推翻上一轮对其受测范围的批准；完整制作方案与真实生成质量仍是独立验收项。
