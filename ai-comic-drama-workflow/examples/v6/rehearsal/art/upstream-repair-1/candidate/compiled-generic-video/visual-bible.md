# Visual Bible

雨夜背景只提供天气与时间线索，人物、同一封未拆信、完整封口和背包开口依次可读；不以布景补写地点或人物关系。

```json
{
  "set": {
    "atmosphere": "雨夜有可辨雨迹或雨层；背景不指认地点与室内外。柔和基础照度支持甲乙手部、封口及包口可读，画内灯具位置尚未定义；不把纸、衣、包自动做成湿透。",
    "bounds": {
      "max_m": [
        1.5,
        0.5,
        2
      ],
      "min_m": [
        -1.5,
        -0.5,
        0
      ]
    },
    "coordinate_system": "right-handed:X-right,Y-depth,Z-up;meters",
    "counts": [],
    "functional_zones": [
      {
        "id": "HAND_BAG_CLEARANCE",
        "max_m": [
          0.95,
          0.3,
          1.45
        ],
        "min_m": [
          -0.45,
          -0.3,
          0.6
        ],
        "purpose": "交信、验封和乙背包开口共用的无固定陈设操作区；人物与道具轨迹以导演时间线为准。"
      }
    ],
    "layout": [],
    "location_entity_id": "ENV_RAIN_NIGHT",
    "origin": "按当前 DirectorIR /scenes/0 的交接中心和示意世界坐标留空操作区域；数值为设计包络而非实景测量。",
    "practical_lights": [],
    "scene_id": "SC_RAIN_NIGHT"
  },
  "world": {
    "color_script": [
      {
        "change_reason": "单镜连续；夜色保持恒定，封口和入包证据靠局部明度与材质分离，不作无来源色彩转场。",
        "palette_ids": [
          "NIGHT",
          "PEOPLE",
          "LETTER",
          "BAG"
        ],
        "shot_ids": [
          "S1"
        ]
      }
    ],
    "era": "年代未指定；当前低干扰观察语法只为美术方案，不成为剧情年代事实。",
    "materials": [
      {
        "base": "未定材质的服装面料",
        "craft": "简洁剪裁与真实袖口",
        "finish": "低反光、纹理频率低",
        "id": "MAT_CLOTH",
        "wear": "不凭空添加损伤；仅保持本镜一致"
      },
      {
        "base": "纸质信件外层",
        "craft": "连续纸面与完整封口折线",
        "finish": "哑光中性浅色",
        "id": "MAT_PAPER",
        "wear": "未拆、封口完整；无可读文字、印章或破损"
      },
      {
        "base": "可弯折的背包面料",
        "craft": "开口和包腔结构可容纳同一封信",
        "finish": "中深灰、低反光",
        "id": "MAT_BAG",
        "wear": "不增加品牌、标记或无来源磨损"
      },
      {
        "base": "雨水",
        "craft": "后景雨迹或水线层",
        "finish": "低对比、局部可见",
        "id": "MAT_RAIN",
        "wear": "不预设人物、纸张或包身被雨淋湿"
      }
    ],
    "palette": [
      {
        "color": "低饱和深灰蓝",
        "id": "NIGHT",
        "role": "无地点标识的雨夜后景，低对比但可辨雨势"
      },
      {
        "color": "相互可分的中性灰阶",
        "id": "PEOPLE",
        "role": "甲乙衣装与背景分离，不用色彩编码身份或情绪"
      },
      {
        "color": "中性偏浅纸色",
        "id": "LETTER",
        "role": "一封信及封口边缘在手部行动区可读"
      },
      {
        "color": "低反光中深灰",
        "id": "BAG",
        "role": "背包开口与浅色信形成明度区别"
      }
    ],
    "region": "地点和室内外未指定；不出现可指认城市、建筑、房间或地标。",
    "shape_language": "只保留两人可交接的空隙、信的封口边缘和乙可触及的背包开口；后景用低频雨夜层次，不添门窗、桌椅或标志。",
    "social_logic": "甲乙身份、关系和交信动机未给；衣装与背包仅服务同一动作链，不暗示职业或阶层。",
    "thesis": "雨夜背景只提供天气与时间线索，人物、同一封未拆信、完整封口和背包开口依次可读；不以布景补写地点或人物关系。"
  }
}
```
