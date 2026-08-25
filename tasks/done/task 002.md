# task 002 · 随机源与 GameState 数据模型

- 状态：完成（2026-08-25）
- 关联：PRD §6.1（GameState）、§6.3（隐藏信息与随机源）；里程碑 M1

## 目标

实现引擎的两个地基：单一可注入随机源 + 完整可序列化的局面数据模型。本 task 不含任何规则流转逻辑。

## 验收标准（测试清单）

随机源（`RandomSource`）：

- [x] 同一种子构造的两个实例，洗牌 / 掷币 / 抽牌序列逐项一致
- [x] 不同种子产出不同序列（统计冒烟即可，不做分布检验）
- [x] 随机源状态可快照/恢复（并行分发与 MCTS rollout 的前置）

GameState：

- [x] 区域完整：双方牌库 / 手牌 / 弃牌堆 / 奖赏区（6 张）/ 战斗场 / 备战区（≤5）/ 竞技场位
- [x] 场上宝可梦携带：进化链、附着能量、伤害指示物、特殊状态（中毒/灼伤/睡眠/麻痹/混乱）
- [x] 卡牌实例与卡定义分离：实例只存引用 id + 场上状态，卡内容来自数据层（白板期可为 stub）
- [x] 序列化往返：GameState → dict/JSON → GameState 逐字段相等
- [x] 不可变性：对局推进返回新状态（或受控副本），原状态不被修改
- [x] 可见视图过滤：`visible_state(player)` 中对手手牌/牌库只剩数量，无内容

## 实现要点

- Pydantic v2 模型（frozen 优先）；随机源独立模块 `engine/rng.py`，引擎任何位置不得直接调 `random`
- 种子决定洗牌顺序：开局布阵时牌库顺序即由种子确定（PRD §6.3）

## 结果与遗留

- **结果**：17 测试全绿（rng 5 + state 8 + scaffold 4）+ ruff 零告警。两个模块：`engine/rng.py`（RandomSource：shuffle/flip_coin/snapshot/restore）、`engine/state.py`（CardDef/CardInstance/InPlayPokemon/PlayerState/GameState + visible_state 过滤视图），全部 frozen Pydantic。
- **TDD 记录**：rng、state 各自先 RED（模块不存在）后 GREEN；state 期间修一处测试自身笔误（stub- 双前缀）。
- **遗留**：抽牌/洗牌的引擎操作（在牌库区域上实际移动卡）属 task 003 阶段机职责，本 task 只交付数据模型与随机源。
