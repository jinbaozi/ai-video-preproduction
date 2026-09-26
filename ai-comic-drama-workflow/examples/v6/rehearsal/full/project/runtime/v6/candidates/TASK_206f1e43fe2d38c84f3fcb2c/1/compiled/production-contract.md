# 制作合同
依据来源和当前 Canon 整理单场短剧本，只呈现已给定的事件及顺序。
- REQ_RAIN_NIGHT [hard] 保留雨夜。
  来源：SRC_69a71adcfaca, CANON_V12；正文：/scenes/0/heading, /scenes/0/blocks/0/text；实现：action；步骤：agent_write → static_validate → semantic_review → text_compile → director_realize；验收：RAIN_STATIC, RAIN_SEMANTIC
- REQ_SAME_UNOPENED_LETTER [hard] 交接、检查和收存的是同一封未拆的信。
  来源：SRC_69a71adcfaca, CANON_V12；正文：/scenes/0/blocks/0/text, /scenes/0/blocks/1/text, /scenes/0/blocks/2/text；实现：action；步骤：agent_write → static_validate → semantic_review → text_compile → director_realize；验收：LETTER_STATIC, LETTER_SEMANTIC
- REQ_EVENT_ORDER [hard] 甲交给乙，乙确认封口完整，之后乙将信收进背包。
  来源：SRC_69a71adcfaca, CANON_V12；正文：/narrative/reveal_order, /scenes/0/blocks；实现：action；步骤：agent_write → static_validate → semantic_review → text_compile → director_realize；验收：ORDER_STATIC, ORDER_SEMANTIC
