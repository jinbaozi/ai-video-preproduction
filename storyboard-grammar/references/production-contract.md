# 有来源、结构、约束、执行与验收的制作合同

这里的合同是制作规格与交接约定，不是法律合同。每条要求的链条为：
来源与版本 → 语义要求 → 所有者 → 作用镜头/JSON Pointer → 强度 → 执行渠道 → 验收与证据 → 不支持时处理。

| 字段 | 要求 |
|---|---|
| id / statement | 稳定条款ID及可观察、无歧义的要求 |
| source_refs | 指向已定位的原文、用户决定、上游或明确设计补充 |
| owner | canon/director/art/storyboard/camera/sound/edit/host |
| strength | hard必须满足，soft允许记录偏差 |
| shot_ids | 受影响镜头；空数组表示项目范围 |
| checks | JSON Pointer + equals/contains/exists + value；程序检查结构 |
| channel / execution | prompt、parameter、reference、previs、post及实际执行说明 |
| acceptance | structure/panel/media/human分别定义判据与所需证据 |
| fallback | block/revise/post/warn；hard不能自动warn |

## 示例

```json
{
  "id": "REQ_CUSTODY",
  "statement": "结尾信封由B右手持有，A不持信封。",
  "source_refs": ["SRC_SCRIPT"],
  "owner": "storyboard",
  "strength": "hard",
  "shot_ids": ["S3"],
  "checks": [{"path": "/shots/2/state_end/ENVELOPE/holder", "op": "equals", "value": "B.right_hand"}],
  "channel": "prompt",
  "execution": "在画面生成描述中保留接触、松手、拿取与收束；宿主审查实拍或生成连续媒体。",
  "acceptance": [
    {"phase": "structure", "criterion": "状态与事件回放一致。", "evidence": "IR及QA诊断"},
    {"phase": "media", "criterion": "连续媒体中B右手先接触后拿起，末帧A空手。", "evidence": "带时间码的视频与最后一帧"}
  ],
  "fallback": "block"
}
```

值相等只能证明被检查字段一致，不能自动证明句子所有含义实现。一个条款有多项硬内容时拆条或加多个checks；不要用exists冒充身份、数量或动作顺序符合。
将人物外形、场景事实、动作因果、对白、构图可读性、声音和交付规格分别建条款，按任务需要选择，避免为缺失内容造剧情。

## 执行渠道与失效

prompt只能表达意图；参数仅在真实模型/入口暴露该控制时可绑定；reference需实际素材和用途；previs用于硬几何；post用于声音、字幕、合成等可后期实现项。
合同不能把“画内人物以指定口型说话”无条件改为旁白。post降级需语义仍满足原要求，否则block或请求必要决定。
缺少硬参考可交付BLOCKED规划包供审阅，不生成可冒充执行的payload。
来源、上游、资产或规则变更使依赖条款与旧build失效；更新revision并重编译，别只改Markdown。

## 证据分层

结构检查可自动PASS；panel/media/human必须保留NOT_RUN直到宿主取得实际证据。
人工或媒体验收另存不可混淆的记录：条款ID、输入与build哈希、take文件/哈希、时间码或画格、审阅人/工具、结论与修复。
写了条款、编译成功、收到视频、审片通过是四个不同事实。
