# 美术制作合同

ART_SCENE_HANDOFF / revision 1 / ArtIR 2

SCENE_HANDOFF 三镜场景的静态美术合同；实际媒体未生成或审看

创作与执行协作协议；导演/摄影/表演决策通过只读引用交接。

## ART_WORLD · hard

保持雨夜且不确立具体地点、年代、室内外或人物关系。

来源：CANON, DIRECTOR, DESIGN_ART
字段：/world, /set, /assets/4
执行：TASK_ART_WORLD / prompt / 按对应ArtIR字段制作美术交接；由宿主与冻结DirectorIR合并并对实际画面核验，不改镜头、表演、台词或事件时序。
验收：G0INPUT, G1DESIGN, G4FINAL
变更：新 revision，重编译；不能静默弱化硬要求。

## ART_CONTINUITY · hard

同一甲乙、同一未拆信和同一背包的外观跨镜连续；信封始终完整，人物脸部身份未由此美术提案擅定。

来源：CANON, DIRECTOR, DESIGN_ART
字段：/assets/0, /assets/1, /assets/2, /assets/3
执行：TASK_ART_CONTINUITY / prompt / 按对应ArtIR字段制作美术交接；由宿主与冻结DirectorIR合并并对实际画面核验，不改镜头、表演、台词或事件时序。
验收：G1DESIGN, G4FINAL
变更：新 revision，重编译；不能静默弱化硬要求。

## ART_HANDOFF · hard

按冻结导演第1镜交接，同一封信从甲右手到乙右手，双手及接触清楚。

来源：CANON, DIRECTOR
字段：/shots/0, /assets/0, /assets/1, /assets/2, /assets/4
执行：TASK_ART_HANDOFF / prompt / 按对应ArtIR字段制作美术交接；由宿主与冻结DirectorIR合并并对实际画面核验，不改镜头、表演、台词或事件时序。
验收：G3_HANDOFF
变更：新 revision，重编译；不能静默弱化硬要求。

## ART_SEAL · hard

按冻结导演第2镜验封，乙眼神、右手和完整封口可辨，不拆信。 美术状态链在本镜记录乙确认封口完整。

来源：CANON, DIRECTOR
字段：/shots/1, /assets/1, /assets/2, /assets/4, /events/0, /assets/1/initial_state/condition, /assets/1/state_rules/0
执行：TASK_ART_SEAL / prompt / 按对应ArtIR字段制作美术交接；由宿主与冻结DirectorIR合并并对实际画面核验，不改镜头、表演、台词或事件时序。
验收：G3_SEAL
变更：新 revision，重编译；不能静默弱化硬要求。

## ART_STOW · hard

按冻结导演第3镜，验封后信进入背包；8500毫秒后完全在包内，终帧无外露信件。 美术状态链在本镜记录背包由待收纳转为收纳同一封信。

来源：CANON, DIRECTOR
字段：/shots/2, /assets/1, /assets/2, /assets/3, /assets/4, /events/1, /assets/3/initial_state/condition, /assets/3/state_rules/0
执行：TASK_ART_STOW / prompt / 按对应ArtIR字段制作美术交接；由宿主与冻结DirectorIR合并并对实际画面核验，不改镜头、表演、台词或事件时序。
验收：G3_STOW
变更：新 revision，重编译；不能静默弱化硬要求。

## ART_MAPPING · hard

逐镜美术支持只约束材质、环境、服化与可读性；动作、机位、信息顺序沿用冻结DirectorIR。

来源：DIRECTOR, DESIGN_ART
字段：/shots, /director, /references
执行：TASK_ART_MAPPING / prompt / 按对应ArtIR字段制作美术交接；由宿主与冻结DirectorIR合并并对实际画面核验，不改镜头、表演、台词或事件时序。
验收：G2MAP, G4FINAL
变更：新 revision，重编译；不能静默弱化硬要求。

## 来源、验收与执行边界

```json
{
  "checks": [
    {
      "blocking": true,
      "evidence_required": "冻结Canon/Director文件与原生校验结果",
      "gate": "G0",
      "id": "G0INPUT",
      "method": "static",
      "owner": "art_planner",
      "predicate": "源事实、设计补充及导演绑定哈希可分辨。",
      "scope": "project"
    },
    {
      "blocking": true,
      "evidence_required": "ArtIR来源/锁定项审阅记录",
      "gate": "G1",
      "id": "G1DESIGN",
      "method": "static",
      "owner": "art_director",
      "predicate": "资产、场景与色材无来源不明的身份或地点断言。",
      "scope": "project"
    },
    {
      "blocking": true,
      "evidence_required": "ArtIR合同覆盖及V5/V6交接映射",
      "gate": "G2",
      "id": "G2MAP",
      "method": "static",
      "owner": "host_reviewer",
      "predicate": "各镜可见资产、导演动作和硬要求均可追踪。",
      "scope": "project"
    },
    {
      "blocking": true,
      "evidence_required": "实际镜头、哈希与具名逐帧观察",
      "gate": "G3",
      "id": "G3_HANDOFF",
      "method": "frame_review",
      "owner": "visual_reviewer",
      "predicate": "交接时双手与同一封未拆的信接触可辨，甲在乙接稳后松开。",
      "scope": "S_HANDOFF"
    },
    {
      "blocking": true,
      "evidence_required": "实际镜头、哈希与具名逐帧观察",
      "gate": "G3",
      "id": "G3_SEAL",
      "method": "frame_review",
      "owner": "visual_reviewer",
      "predicate": "乙眼神和完整封口可辨且无拆封。",
      "scope": "S_SEAL"
    },
    {
      "blocking": true,
      "evidence_required": "实际镜头、哈希与8500/9000毫秒具名观察",
      "gate": "G3",
      "id": "G3_STOW",
      "method": "frame_review",
      "owner": "visual_reviewer",
      "predicate": "入包过程可辨，8500毫秒后信不外露，终帧信在包内。",
      "scope": "S_STOW"
    },
    {
      "blocking": true,
      "evidence_required": "最终媒体及完整具名审核记录",
      "gate": "G4",
      "id": "G4FINAL",
      "method": "playback",
      "owner": "final_reviewer",
      "predicate": "三镜美术连续、雨夜持续、同一信封完整且结尾入包。",
      "scope": "project"
    }
  ],
  "execution": {
    "authorization_ref": null,
    "budget_amount": 0,
    "currency": "CNY",
    "max_attempts_per_job": 2,
    "mode": "plan_only",
    "stop_conditions": [
      "没有真实媒体和授权时只交付静态计划",
      "真实参考、图像或视频未登记前不得声称视觉验收通过"
    ]
  },
  "sources": [
    {
      "claim": "源事实只有雨夜、甲交一封未拆的信给乙、乙验封后将同一封信收进背包；人物外观、地点和室内外未给出。",
      "id": "CANON",
      "kind": "canon",
      "locator": "/content,/entities,/event_order,/source_requirements,/unspecified",
      "uri": "/private/tmp/ai-video-v6-full-demo/project/runtime/v6/candidates/TASK_44ed8445ba9b638fcd7e9fe8/2/canon.json",
      "verification": "read"
    },
    {
      "claim": "冻结三镜、动作时点和终态；甲乙交接、验封、入包的机位与行为只读继承。",
      "id": "DIRECTOR",
      "kind": "director",
      "locator": "/scenes/0,/shots/0-2,/timeline/actions,/timeline/state_samples",
      "uri": "/private/tmp/ai-video-v6-full-demo/project/runtime/v6/candidates/TASK_bf0865334b4a88be570a164a/2/director-ir.json",
      "verification": "read"
    },
    {
      "claim": "旧取消候选只作只读色材与场景设计参考；本批重新核对当前 Canon、DirectorIR 1.2、锁定 Art 1.3.3 契约并重建离散状态事件。所有美术色材、衣装、平整承托面和参考计划仍为提案。",
      "id": "DESIGN_ART",
      "kind": "design",
      "locator": "/world,/assets,/set,/shots,/references",
      "uri": "local:LETTER_FULL_DEMO/art/SCENE_HANDOFF/revision-2",
      "verification": "inference"
    }
  ]
}
```
