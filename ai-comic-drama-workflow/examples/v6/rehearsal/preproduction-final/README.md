# 前期 QA 与交付证据：修订 738 历史快照

运行项目：`/private/tmp/ai-video-v6-real-efKlQy/project`，原创案例 `LETTER_DEMO`。这是 **text-only 前期包** 的一次真实 Codex 智能体演练快照，不是最终当前完成声明。项目后续会因运行时代码指纹变化而失效并重新编排；本目录只保留修订 738 当时的原始文件与事件摘录。

## 派发、检查与状态

- 前期 QA 任务 `TASK_5940525a2a35543b33e08b18`、批次 1、输入修订 707、输入摘要 `5f5f8b48d7c9531b93ef577bff22cadcac7c4896d25540216a9250791a95f824`。`host/action.json` 是冻结任务动作；`host/spawn-raw.json` 是真实 `collaboration.spawn_agent` 返回。内核在修订 711 登记了 Codex 派发回执及执行者 `/root/host_bridge/v6_8831cca9ea8430c5dd325247`。
- `host/` 同时保留 ACK、两次 PROGRESS、RESULT 的结构化消息和原始文本。RESULT 在修订 715 绑定 `candidate/candidate-result.json`，其 SHA-256 为 `4357cf6943a22ee4f8dbd265f5c3e9f66b9fde5f309e67a71cea7e9da0addd4d`。正式候选与 `candidate/role-result.json` 指向同一 `PreproductionQA`；内核执行 `preproduction_final` 检查后于修订 718 转为 `ACCEPTED`。QA 本身是图上的 `review` 执行类，不再递归派发另一个 QA 审阅者；上游编译正文另有独立 `CompileReview`。
- 内核创建系统任务 `V6_preproduction_13e89f5eb81bc5856bc8`，在修订 720 验证并接受交付索引。随后修订 721–738 为 video 后续节点生成九项条件 `NOT_APPLICABLE`。`host/submit-out.json` 精确记录当时命令返回 `DELIVERED`、修订 738；`delivery-index.md` 是当时项目交付页的原字节副本；其中相对链接以原运行项目为基准，归档目录本身没有复制完整 build。

## 边界和后续修正

`candidate/preproduction-qa.json` 的 `passed=true` 只覆盖静态前期范围：`production_target=none`、媒体未提交、`video_qa=NOT_RUN`、`video_delivered=false`。雨声 `AUD_RAIN` 与媒体/关键帧义务 `SB_MEDIA_BOUNDARY` 仍为 `PLANNED`。这次没有生成或验收视频，交付页中的视频提示词也只是编译文本。

同一修订的只读 `status` 输出保存在 `final-status.json`：`preproduction_complete=true`、`v6_revision=738`，但顶层 `status=BLOCKED`。当时状态读取将历史 `STALE`/`FAILED` 计入了顶层状态；因此不能把命令返回的 `DELIVERED` 当作无歧义的最终当前状态。交付索引 JSON 的 `validation.preproduction_complete=false` 也是生成交付索引时的 **V5 预交付验证快照字段**；本目录原样保留这个不一致，不把它改写为完成证据。运行时修正及重跑由主任务负责。

`event-excerpt.json` 从项目原始 `runtime/v6/events.json` 提取修订 708–738，事件对象内容逐项保留，并附原日志 SHA-256；它不是新造的执行史。`SHA256SUMS` 核对本目录包含的全部文件原字节（不包含清单自身）。

## 未随摘录复制的原件

以下文件仍在上述运行项目中；路径相对项目根目录，哈希为 SHA-256，大小为原字节数：

| 路径 | 大小 | SHA-256 |
|---|---:|---|
| `runtime/v6/events.json` | 1,434,054 | `4d310c8ea9ef30d845fd2e225f7e8fad5dadf1656b4210cca5cf6f6fc3d25ccf` |
| `runtime/v6/state.json` | 940,621 | `b0a477f67bd123bdb7b331d135813db7fe439f7dc909ed9536cf337d64da6740` |
| `runtime/v6/candidates/V6_preproduction_13e89f5eb81bc5856bc8/1/delivery-index.json` | 891,174 | `f0822e082ba9bf202e93211a5a98de489c22e091f40391a2cdccbe84e1447a94` |
| `delivery/index.json` | 891,174 | `f0822e082ba9bf202e93211a5a98de489c22e091f40391a2cdccbe84e1447a94` |
| `builds/99259f5ba9dd4c89d0c2ee2b5b19c0f7c79a8d38afb64a279090aea8c4f12175/compiled/prompt.txt` | 30,283 | `72fe66a15c952c2b580ee0f660d4b524d9f4926189a7e2e996f782dd32232034` |
| `builds/99259f5ba9dd4c89d0c2ee2b5b19c0f7c79a8d38afb64a279090aea8c4f12175/attachments.json` | 46 | `5d7e757f1b79ef1ae7e3b2e5cd233e280542cadfea91c4b5347e99c596d4173e` |
| `builds/99259f5ba9dd4c89d0c2ee2b5b19c0f7c79a8d38afb64a279090aea8c4f12175/compiled/post-production.json` | 624 | `5ff6d16237c98f2c2ffd3ddc0b65af1a5e74f584b6695090ae124f40e9b3c988` |

完整构建、已锁定 Skill 和其他历史候选留在运行项目；本目录只选取 QA/交付门所需的可读证据。
