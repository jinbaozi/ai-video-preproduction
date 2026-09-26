# Visual Bible

在地点和室内外仍开放的雨夜，以低干扰色材让交接的双手、同一封完整封口以及入包终态可读。

```json
{
  "set": {
    "atmosphere": "雨夜持续，背景雨幕低频且不遮挡手、封口与包口；具体室内外和可辨建筑不定。光源以同一方位的画外环境漫反射为待实现设计提案，三镜保持手与封口可读。",
    "bounds": {
      "max_m": [
        2,
        2,
        2.5
      ],
      "min_m": [
        -2,
        -2,
        0
      ]
    },
    "coordinate_system": "right-handed:X-right,Y-depth,Z-up;meters",
    "counts": [
      {
        "asset_id": "ENV_RAIN_NIGHT",
        "count": 1
      }
    ],
    "functional_zones": [],
    "layout": [
      {
        "asset_id": "ENV_RAIN_NIGHT",
        "id": "GROUND_1",
        "position_m": [
          0,
          0,
          0
        ],
        "role": "甲乙站立与背包稳定承托的中性连续面；不确定具体地点",
        "size_m": [
          4,
          4,
          0.02
        ],
        "yaw_deg": 0
      }
    ],
    "location_entity_id": "ENV_RAIN_NIGHT",
    "origin": "以冻结DirectorIR的两人交接中点在承托面上的投影为设计原点；以下米值仅为美术搭建范围，不是原文测量。",
    "practical_lights": [],
    "scene_id": "SCENE_HANDOFF"
  },
  "world": {
    "color_script": [
      {
        "change_reason": "甲乙双手与同一封信的接触需要从雨夜背景分离",
        "palette_ids": [
          "BG_NIGHT",
          "WARDROBE_DARK",
          "LETTER_NEUTRAL"
        ],
        "shot_ids": [
          "S_HANDOFF"
        ]
      },
      {
        "change_reason": "乙的眼神、右手与完整封口同框可辨，不暗示拆封",
        "palette_ids": [
          "BG_NIGHT",
          "WARDROBE_DARK",
          "LETTER_NEUTRAL"
        ],
        "shot_ids": [
          "S_SEAL"
        ]
      },
      {
        "change_reason": "前段辨认信进入包口；8500毫秒后信在包内不再外露，终帧由乙手与背包口承载结果",
        "palette_ids": [
          "BG_NIGHT",
          "WARDROBE_DARK",
          "LETTER_NEUTRAL"
        ],
        "shot_ids": [
          "S_STOW"
        ]
      }
    ],
    "era": "原文未指定年代；当代观察语法仅为本次视觉设计提案，不据此补写人物身世或剧情。",
    "materials": [
      {
        "base": "无标识深色织物",
        "craft": "平织与收口袖型",
        "finish": "低反光哑面",
        "id": "MAT_CLOTH",
        "wear": "无指定旧化、品牌与身份标记；雨夜湿痕仅在实际可见且不遮手时使用"
      },
      {
        "base": "普通纸质信封",
        "craft": "折叠封口保持闭合",
        "finish": "中性哑面纸纹",
        "id": "MAT_PAPER",
        "wear": "无拆封、破口、涂写或可读文字；三镜为同一封，封口始终完整"
      },
      {
        "base": "深色无标识织物",
        "craft": "有可开启包口与足够容纳一封信的内腔",
        "finish": "低反光哑面",
        "id": "MAT_BAG",
        "wear": "不添加来源不明的贴章、文字或明显损坏；包口形制三镜不变"
      },
      {
        "base": "中性稳定承托面",
        "craft": "平整可站立",
        "finish": "低反光",
        "id": "MAT_GROUND",
        "wear": "无可识别场所线索；雨夜反光不淹没接触证据"
      }
    ],
    "palette": [
      {
        "color": "低饱和蓝灰",
        "id": "BG_NIGHT",
        "role": "雨夜环境后退，提供人物与动作的低频背景"
      },
      {
        "color": "深石墨灰与深蓝灰",
        "id": "WARDROBE_DARK",
        "role": "两人服装低对比区分，手和信不被暗纹吞没"
      },
      {
        "color": "中性偏暖纸色",
        "id": "LETTER_NEUTRAL",
        "role": "未拆信及封口与深色袖口、背包口分离"
      }
    ],
    "region": "原文未指定地域及具体地点；不加入可辨识城市、建筑、招牌或年代地标。",
    "shape_language": "单一平整承托面、二人相向站立的通行净空和乙可触及的背包位置；不放妨碍手与包口的陈设。",
    "social_logic": "不从衣装、信或背包推断二人关系、动机或信件内容；视觉物件仅服务已锁定动作。",
    "thesis": "在地点和室内外仍开放的雨夜，以低干扰色材让交接的双手、同一封完整封口以及入包终态可读。"
  }
}
```
