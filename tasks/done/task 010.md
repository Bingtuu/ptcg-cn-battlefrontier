# task 010 · 卡组装载层：db → CardDef + DSL 定义库落盘

- 状态：完成（2026-08-29）
- 关联：PRD §4 架构分层（数据层）/§6.6（ACE SPEC 构筑校验），里程碑 M2；输入 = task 005 锁定卡组（`mik_moe:644634`）、db 支撑批（045 卡组接口 / 046 跨源对账）

## 目标

打通「真实卡组进真实对局」的数据通路：从 ptcgdb SDK 装载沙奈朵代表卡表（60 张）→ `CardDef`，字段映射与校验口径按 2026-08-29 接入约定（prize_cards 校验 / provides 能量属性 / 弱点抗性值校验）；DSL 定义库落盘为独立资产（一卡一 YAML，进版本控制），已实现四卡（博士的研究/高级球/巢穴球/夜间担架）首批入库。

## 验收标准（测试清单）

- [x] `load_deck(db, "mik_moe:644634")` → 60 张 CardDef；装载即跑 db `validate_deck`（60 张/同名/ACE SPEC 限 1），违规报错不猜
- [x] 字段映射抽查：沙奈朵ex（hp310 / 超属性 / 弱点恶 / 抗性斗 / 撤退 2 / rule_box=ex / 奇迹之力 cost=(超,超,无) dmg=190）；拉鲁拉丝 stage=0、奇鲁莉安 stage=1 + evolves_from=拉鲁拉丝、沙奈朵ex stage=2
- [x] 能量卡：`provides` → energy_type + is_basic_energy（基本超能量→超）
- [x] stage 中文串映射（基础/1阶/2阶 → 0/1/2）；未知 stage 串 → 明确报错
- [x] 变量伤害招式：damage_base 装载为 AttackDef.damage，modifier（+/×）进 `AttackDef.damage_modifier`（白板结算忽略，DSL 变量伤害落地时用）；dmg=None（基因侵入等）→ damage=None
- [x] 校验告警（不猜）：db prize_cards 与引擎 PRIZE_BY_RULE_BOX 不符 → warning；弱点/抗性 value 非 ×2/-30 → warning
- [x] 装载的卡组直接 `new_game` + `play_game` 跑通（同种子 hash 一致），已入库四卡效果生效
- [x] DSL 定义库：`cards/*.yml` 一卡一文件（注释引用 text_raw 原文，不改写）；`load_card_dir` 加载 + schema/词表校验；四卡与测试内联文档语义等价
- [x] pytest 全绿 + ruff 零告警

## 实现要点

- `battlefrontier/data/` 新包：`cards.py`（SDK Card → CardDef 映射 + 校验告警汇集，warnings 返回不抛）+ `deck.py`（load_deck：get_deck → validate_deck → 展开 60 张）
- `AttackDef` 增 `damage_modifier: str | None`（开放字符串 +/−/×）；CardDef 其余字段 task 008 已备
- 挂载键：本期 = `name_full`（本卡组无跨印刷歧义）；db SDK 暴露 group_key 后切 name_group（遗留，已向 db 提需求）
- `dsl/loader.py` 加 `load_card_dir(path) -> dict[str, CardEffectDoc]`（按 name_group 键）
- `cards/` 顶层目录（DSL 定义库独立资产，进 git）；四卡 YAML 注释引用 db text_raw 原文（AGENTS 硬性规矩：引用不改写）
- 道具/竞技场/特性卡的 CardDef 字段装载不阻塞对局（骨架未落的卡打不出，归 task 011+）

## 结果与遗留

**结果**（2026-08-29）：

- `battlefrontier/data/` 新包落地：`cards.py::carddef_from_db`（单卡映射 + warnings 汇集）+ `deck.py::load_deck`（get_deck → validate_deck → 按 count 展开 60 张，日期 = 最新 standard 快照 `effective_from`），`LoadedDeck(cards, warnings)` frozen dataclass 返回。
- `AttackDef.damage_modifier`、`CardDef.is_ace_spec` 补位（默认 None/False，存量零影响）。
- `dsl/loader.py::load_card_dir`（目录 → name_group 键字典，重复键报 DslError）。
- `cards/` 定义库首批四卡入库（博士的研究 / 高级球 / 巢穴球 / 夜间担架），YAML 注释引用 text_raw 原文。
- 沙奈朵卡组（`mik_moe:644634`）60 张装载零告警（validate_deck ok）；装载卡组 + 四卡效果 play_game 端到端跑通、同种子事件流 hash 一致。
- 测试：`tests/test_deckload.py` 11 条（映射抽查 / 进化链 / 能量 / 变量伤害 / ACE SPEC / e2e / prize 告警 / stage 报错 / 定义库结构与语义）；全量 127 绿，ruff 零告警。
- **TDD 记录**：先写 `tests/test_deckload.py`，RED（`ModuleNotFoundError: battlefrontier.data`）→ data 包 + 定义库 GREEN；测试搭建期两处修正（SDK 字段实为 `card_type` 非 `supertype`、假卡可变类属性撞 RUF012 改 tuple）。

**遗留**：

- 挂载键本期 = `name_full`；db SDK 暴露 group_key 后切 name_group（已向 db 提需求）。
- 特性/道具/竞技场骨架、混乱状态、计数表达式、效果招式（damage=None 的 DSL on_attack）归 task 011+。
- 装载卡组中无 DSL 效果的训练家卡打不出（预期行为）；随定义库扩编逐批核销。
