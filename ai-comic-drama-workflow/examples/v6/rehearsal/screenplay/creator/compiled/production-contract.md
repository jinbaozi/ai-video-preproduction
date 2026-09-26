# 制作合同
仅改写原文的雨夜交信事件；不补写地点、人物关系、动机、信件内容、对白或后续。
- REQ_RAIN_NIGHT [hard] 保留雨夜这一时空事实，不补写具体地点。
  来源：SRC_69a71adcfaca, CANON_INPUT；正文：/scenes/0/blocks/0/text；实现：action；步骤：agent_write → static_validate → semantic_review → text_compile → director_realize；验收：CHECK_RAIN, CHECK_SOURCE_BOUNDARY
- REQ_SINGLE_LETTER [hard] 交接一封未拆的信，后续封口检查与收存指向同一封信。
  来源：SRC_69a71adcfaca, CANON_INPUT；正文：/scenes/0/blocks/1/text, /scenes/0/blocks/2/text, /scenes/0/blocks/3/text；实现：action；步骤：agent_write → static_validate → semantic_review → text_compile → director_realize；验收：CHECK_LETTER, CHECK_SOURCE_BOUNDARY
- REQ_ACTION_ORDER [hard] 甲交给乙；乙确认封口完整；确认后乙把信收进背包。
  来源：SRC_69a71adcfaca, CANON_INPUT；正文：/narrative/events, /narrative/reveal_order, /scenes/0/blocks/1/text, /scenes/0/blocks/2/text, /scenes/0/blocks/3/text；实现：narrative；步骤：agent_write → static_validate → semantic_review → text_compile → director_realize；验收：CHECK_ORDER, CHECK_SOURCE_BOUNDARY
