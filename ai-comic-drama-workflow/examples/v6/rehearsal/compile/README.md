# 编译与正文复核演练

`batch-1/` 保存真实编译专家、独立审阅者、冻结输入、候选、四项逐项检查与失败结论。锁定原生 AVIR/manifest 校验和文件哈希通过，但独审发现同一机位在正文中出现两组不等价世界坐标。`compile_manifest=FAIL`、`failure_owner=director`；内核于修订 339 将本批次置为 `FAILED`，并未接受 AVIR 或 CompilePackage。

旧候选及失败证据保持原字节。下一步须由导演责任修订，继而分镜、控制包和编译重新绑定；静态 `COMPILED` 不能代替正文语义复核。媒体、模型调用、后期义务均未完成。

`upstream-repair-1/` 保存内核跨责任回流后，Director、Art、Storyboard、Control 全部重建并审结所触发的新编译。新创作者与独立审阅者复核旧机位坐标错误已消除，四项检查 PASS，内核于修订 493 接受静态 AVIR/CompilePackage。原批次 FAIL 保留；新包的 provider transport、后期义务与媒体 QA 仍未完成。

[`semantic-fix-attempts/`](semantic-fix-attempts/) 保存旧语义失败路由触发的新构建的两批真实执行：第 1 批因 graph-only 候选错误声明原生 RoleResult 而 `FAILED`，第 2 批因宿主桥源码纳入运行码指纹而暂停并于修订 616 `STALE`。两批均未获独立审阅接受。

[`host-fingerprint-reissue/`](host-fingerprint-reissue/) 保存新指纹下绑定原语义失败证据的 Compile 重建：真实创作者提交 graph-only 候选，独立审阅四项 PASS，内核于修订 695 `ACCEPTED`。旧信件终态可见性冲突在新 AVIR、时间线和正文静态闭合；模型与媒体执行仍 `NOT_RUN`。

[`independent-review-registration/`](independent-review-registration/) 保存后续 Compile `V6_compile_68030bc9fd64468372e1` 的独立审阅原文补登记。审阅记录早已落盘，宿主在修订 937–938 登记 `RESULT` 并接受；修订 941 的正文复核仍停在 `DISPATCHING`，没有新的 `spawn_agent` 回执。
