"""单卡 DSL 测试分片：task 025 批 1 wave 3（w3）。

本 wave 卡单 6 张逐卡核对 text_raw 与 filters/condition/counters 注册表后
**全部 blocked**（级别初判 A「现有原语」与实际机制缺口不符），未写 DSL、无测试：

- 奥琳博士的气魄（CSV6C-121）：缺场上宝可梦「古代」特质过滤器（db labels 有「古代」，
  engine CardDef 无 labels 字段）；缺 attach_energy「选 ≤2 目标、各附 1 张弃牌区
  基本能量」多目标模式（现两段式 = 选 N 能量 → 单一目标）。
- 怒鹦哥ex（CSV2C-105）：特性「英武重抽」缺 condition 词 first_own_turn
  （「最初的自己的回合」，特性枚举路径无 first-turn 门）；招式「鼓足干劲」缺
  attach_energy up-to-N（最多 2 张，现 exact N）与仅备战区目标池。
- 赤松（CSV9C-196）：缺检索多选「属性各不相同」约束、检索结果拆分去向
  （1 张入手 + 剩余附着）；reveal 在词表但原语未实现。
- 飞天螳螂（151C-123）：「辅助斩」缺 filter 词 energy_草（现仅硬编码 energy_超，
  无参数化属性能量过滤器）；缺 attach_energy 仅备战区目标池。
- 猛雷鼓ex（CSV7C-154）：「极雷轰 70×」缺弃置场上附着能量的原语（discard 仅
  own_hand）与计数取自前节点选择数的 damage 计数词；「飞溅咆哮」虽可写，
  整卡不降级，标 blocked。
- 猛雷鼓（CSV8C-161）：「落雷风暴」缺 counters 词 attached_energy_on_target
  （目标宝可梦附着能量数 ×30；现仅有 attached_energy_on_opponent_active）。

所需新词/机制明细见批 1 wave 3 交付报告，由主会话统一注册后解锁重写。
"""
