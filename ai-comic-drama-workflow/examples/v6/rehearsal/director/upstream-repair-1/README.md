# Director 跨责任返修（真实 Codex 演练）

- 源项目：`/private/tmp/ai-video-v6-real-efKlQy/project`；Director `TASK_19a3cd14f25bf90e50215d4d` batch 1，V6 revision 386 `ACCEPTED`。
- 源因：旧 Compile 批次 1 独审 `compile_manifest=FAIL`，发现旧导演相机文字 `[0,-2.8,1.2]` 与 AVIR/编译正文数值 `[0,1.2,-2.8]` 未说明轴序；旧 Compile 候选保留为失败历史，见 `../../compile/batch-1/`。
- 内核冻结 `upstream-repair.json`，新 Director task 以独立真实派发与独审完成。Creator：`/root/host_bridge/v6_859d227c7d730ab3b9722469`；Reviewer：`/root/host_bridge/v6_df80385afeacb4a6056c235f`。`spawn-raw.json` 和 `review-spawn-raw.json` 是实际 Codex 工具返回；事件收据绑定 action/task/batch。
- 候选 DirectorIR SHA-256 `3c47e2922471e46f1ad637587a4be06d30dbf86de3f4790439bfa0ac7803ad0b`；review-record SHA-256 `9febdd6ee85bb95befd7cd87f740c43a73bd70fb90af036caee3ff4e64da20f4`；三项独审均 PASS。静态 scene 使用锁定 `X-right,Y-depth,Z-up`，timeline 使用锁定 `x-right,y-up,z-depth`；通过 `[x,深,高] → [x,高,深]` 描述同一物理机位，camera_operations 的文本明确标注时间轴坐标，六个采样点与固定轨迹一致。
- 本记录只证明返修候选和独审通过。后续 Art、Storyboard、Control、Compile 和 QA 需要按图重建；媒体/模型执行 `NOT_RUN`。原始工具输出与项目完整状态仍保留在源项目；本目录精选可离线复核的动作、回执、输入返修简报、候选、原生检查及审阅。
