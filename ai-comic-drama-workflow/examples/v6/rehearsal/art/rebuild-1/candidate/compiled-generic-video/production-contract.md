# 美术制作合同

ART_RAIN_NIGHT / revision 2 / ArtIR 2

SC_RAIN_NIGHT 单镜文字美术候选，依据当前冻结 Canon 版本 12 与 DirectorIR 版本 18；两者只读；尚无真实图片或视频。

创作与执行协作协议；导演/摄影/表演决策通过只读引用交接。

## A_RAIN · hard

保留雨夜；不指认具体地点、年代或室内外状态。

来源：CANON, DIRECTOR
字段：/world/era, /world/region, /set/atmosphere, /assets/4, /shots/0/composition_support/background
执行：TASK_A_RAIN / prompt / 将雨夜与无地点标识后景作为美术补充；实际画面审雨夜可辨且未引入无来源地点。
验收：C_INPUT, C_DESIGN, C_MEDIA, C_FINAL
变更：新 revision，重编译；不能静默弱化硬要求。

## A_SINGLE_LETTER · hard

只使用 PROP_LETTER 这一封未拆且封口完整的信；交接、验封和收存保持同一外观。

来源：CANON, DIRECTOR
字段：/assets/2, /world/materials/1, /shots/0/composition_support/separation
执行：TASK_A_SINGLE_LETTER / prompt / 给信件唯一资产ID与完整封口边缘；下游与导演时间线逐点核对身份、接触和控制权。
验收：C_DESIGN, C_MEDIA, C_FINAL
变更：新 revision，重编译；不能静默弱化硬要求。

## A_ORDER · hard

交信完成后乙确认完整封口，确认后才收进同一个 PROP_BACKPACK；美术不重排导演动作。

来源：CANON, DIRECTOR
字段：/assets/2/identity_locks, /assets/3, /shots/0/composition_support/occlusion
执行：TASK_A_ORDER / prompt / 宿主合并只读 DirectorIR /timeline/actions 的 ACT_EXTEND→ACT_GRIP→ACT_RELEASE→ACT_CONFIRM_SEAL→ACT_STOW；本美术包只保障对应证据可见。
验收：C_MAP, C_MEDIA, C_FINAL
变更：新 revision，重编译；不能静默弱化硬要求。

## A_ENDING · hard

同一封信收进乙背包即结束；不添加信件内容、人物动机、对白或后续情节。

来源：CANON, DIRECTOR
字段：/assets/2/design, /assets/3/design, /shots/0/composition_support
执行：TASK_A_ENDING / prompt / 合并导演末态后检查信入包并停在来源终点；不给画面增添故事线索。
验收：C_MEDIA, C_FINAL
变更：新 revision，重编译；不能静默弱化硬要求。

## A_EVENTS · hard

三项来源事件各有可见美术证据：接触与交接、完整封口、包口及入包；不新增事件。

来源：CANON, DIRECTOR
字段：/shots/0/composition_support, /shots/0/performance_support, /set/functional_zones
执行：TASK_A_EVENTS / prompt / 按导演三事件与五个动作节点留出无遮挡物理区域；不把美术状态说明改写为人物表演。
验收：C_DESIGN, C_MAP, C_MEDIA
变更：新 revision，重编译；不能静默弱化硬要求。

## A_REVEAL · hard

观众先见交接，再见封口完整，最后见同一封信收入包内；雨夜后景不得抢先暗示信件内容或后续。

来源：CANON, DIRECTOR
字段：/shots/0/composition_support/background, /shots/0/composition_support/occlusion, /world/color_script
执行：TASK_A_REVEAL / prompt / 逐节点观察同一封信、封口和包口；美术可读性随导演时间线检查，保持单镜夜色连续。
验收：C_MAP, C_MEDIA, C_FINAL
变更：新 revision，重编译；不能静默弱化硬要求。

## A_ASSET_LOCKS · hard

甲乙身份与衣装、唯一信件、同一背包和雨夜后景连续；真实参考取得后才可绑定并审图。

来源：CANON, DIRECTOR, ART_DESIGN
字段：/shots/0, /assets/0, /assets/1, /assets/2, /assets/3, /assets/4, /references
执行：TASK_A_ASSET_LOCKS / prompt / 以稳定ID制作资产卡；参考仍为 planned，宿主补入真实文件、哈希、用途及权利后再做视觉审核。
验收：C_INPUT, C_DESIGN, C_MAP, C_MEDIA
变更：新 revision，重编译；不能静默弱化硬要求。

## 来源、验收与执行边界

```json
{
  "checks": [
    {
      "blocking": true,
      "evidence_required": "本次 source-integrity 与 module-receipt 证据，含当前导演版本与哈希。",
      "gate": "G0",
      "id": "C_INPUT",
      "method": "static",
      "owner": "art_planner",
      "predicate": "输入 Canon/DirectorIR/任务与模块哈希、稳定ID及未指定项记录一致。",
      "scope": "project"
    },
    {
      "blocking": true,
      "evidence_required": "ArtIR 字段审阅与导演只读绑定。",
      "gate": "G1",
      "id": "C_DESIGN",
      "method": "static",
      "owner": "art_director",
      "predicate": "美术色材、空场拓扑和资产可读性不改导演镜头或原文事实。",
      "scope": "project"
    },
    {
      "blocking": true,
      "evidence_required": "本次合同覆盖表及六条 V5、两条 V6 交接映射。",
      "gate": "G2",
      "id": "C_MAP",
      "method": "static",
      "owner": "host_reviewer",
      "predicate": "每条硬要求有源、ArtIR 字段、执行渠道和后续可观察检查。",
      "scope": "project"
    },
    {
      "blocking": true,
      "evidence_required": "真实 Take 文件/哈希，关键时间码及具名逐帧观察；当前 NOT_RUN。",
      "gate": "G3",
      "id": "C_MEDIA",
      "method": "frame_review",
      "owner": "visual_reviewer",
      "predicate": "实际镜头可辨雨夜、唯一未拆信、完整封口、包口与先后动作，且没有新地点或剧情。",
      "scope": "S1"
    },
    {
      "blocking": true,
      "evidence_required": "最终文件/哈希及完整播放记录；当前 NOT_RUN。",
      "gate": "G4",
      "id": "C_FINAL",
      "method": "playback",
      "owner": "final_reviewer",
      "predicate": "完整播放后只得到雨夜交信、验封和收存；同一封信入包即终点。",
      "scope": "project"
    }
  ],
  "execution": {
    "authorization_ref": null,
    "budget_amount": 0,
    "currency": "CNY",
    "max_attempts_per_job": 1,
    "mode": "plan_only",
    "stop_conditions": [
      "仅交付文字与静态候选；生成媒体需独立执行任务",
      "G3/G4 未完成前不声明实际画面通过"
    ]
  },
  "sources": [
    {
      "claim": "雨夜；甲将一封未拆的信交给乙；乙确认封口完整后收进背包。",
      "id": "USER",
      "kind": "user",
      "locator": "原始一句话雨夜交信文本",
      "uri": "/private/tmp/ai-video-v6-real-efKlQy/project/sources/SRC_69a71adcfaca/source.txt",
      "verification": "read"
    },
    {
      "claim": "稳定人物、道具和场景ID；一封未拆信与三事件顺序；地点、年代、外观、室内外未定。",
      "id": "CANON",
      "kind": "canon",
      "locator": "/content /entities /event_order /source_requirements /unspecified",
      "uri": "/private/tmp/ai-video-v6-real-efKlQy/project/artifacts/canon/4bbb635979d6feb720b76de93a3e508572b5751b3c06670dc4886061248692c2/native/befdfe311a8fed6f_canon.json",
      "verification": "read"
    },
    {
      "claim": "当前冻结 DirectorIR 的单镜布局、手部交接、封口及包口可见约束；动作时序与控制权以只读 /timeline/actions 为准。",
      "id": "DIRECTOR",
      "kind": "director",
      "locator": "/scenes/0 /shots/0 /timeline/actions /contract",
      "uri": "/private/tmp/ai-video-v6-real-efKlQy/project/runtime/v6/candidates/TASK_ae94f4322a77ebd18dbb635d/1/director-ir.json",
      "verification": "read"
    },
    {
      "claim": "无具体地点和人物外观事实的低干扰雨夜美术；纸信封口与背包开口可读；未生产或审查任何媒体。",
      "id": "ART_DESIGN",
      "kind": "design",
      "locator": "本次 ArtIR 场景与资产的中性可读设计；参考旧候选复核但不采信其旧来源绑定",
      "uri": "design://TASK_71abb1f14640b94809ef3db2/art-scope-revision-2",
      "verification": "inference"
    }
  ]
}
```
