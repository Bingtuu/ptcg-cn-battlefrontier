# 084 复制击杀短路 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **已拍板（2026-10-29）。** Q1–Q8 整包按规格「本文建议」。**Q2=C**：维持 main `4262a9f` 的复制击杀短路。不加字段，不改 `heuristic.py`，不重跑 100 局。**本计划在 Task 1 停止。Task 2 起不执行**（留作若将来重开 B/A 时的草稿，不是本刀授权）。

**Goal:** 决定复制击杀（`via=="copy"` 且 `can_ko`）是否占用 `_lethal_attack` 的「先于训练家」短路；前瞻本身的 `can_ko` 保持 083 合入后的语义。

**Architecture:** 083 的 `_ko_prize_lookahead` 继续回答「能不能斩杀」。本刀只在 `_decide_main` 里、`_lethal_attack` 已经返回攻击之后，按 `copy_lethal_policy` 决定要不要真的返回它。`via=="print"` 始终短路。撤退与 promote 继续只读前瞻，不读这道政策。

**Tech Stack:** Python 3.12+、pytest、ruff。局级用 `bfsim`（Diupi-Yun / 本机 `ptcg-cn.db`）。

**权威设计：** `docs/superpowers/specs/2026-10-29-task-084-copy-lethal-short-circuit-design.md`。

## Global Constraints

- 零卡名分支。
- 不回滚 083：不改 `_ko_prize_lookahead` / `_one_layer_copy` / `_lookahead_on_active` 的 `can_ko` 语义，不改 `_ko_remaining` / `_effective_max_hp`，不改伤害关联弃牌与附伤目标。
- 不把 `can_ko` 改成假来实现「不短路」。
- `pokemon_score` 与 `factor_prize_diff` 不动。`tests/test_features.py` 期望不得改。
- 新字段（若 Q4 要加）不进 tune 的 10 维。`len(search_space())` 仍是 10。
- 不读 `modify_attack_cost`。不改 `_attack_table`、`_pick_attack` 的排序键、`_copy_donor_key`、`_pick_choose`、`play_stadium` / `end_turn` 的排序。
- 不新增 `prize_pressure_gate`。不实现落后换更高非击杀。
- 不引入 `ABLATION_COPY_NOT_LETHAL` 环境变量。
- 不引入 JEV/LLM，不改 MCTS/蒸馏，不改 DSL/引擎，不跑 18000。
- Q2=C：不改 `heuristic.py`，不重跑 100 局。
- 失败局必须是 0。云端无库，不跑 `bfsim`。
- 局级对照写两列：t080 A78/B22，083 A72/B28。不对照 081 的 A80。

## File map

| 文件 | 职责 |
|---|---|
| `battlefrontier/agent/heuristic.py` | 仅当 Q2=A 或 B：`HeuristicParams.copy_lethal_policy` + `_decide_main` 上的短路过滤 + `_setup_trainer_available`。Q2=C 不改 |
| `tests/test_heuristic_ko_prize_lookahead.py` | 仅当 Q2=A 或 B：政策红测。`"always"` 锚保留 |
| `tests/test_tune_space.py` | 仅当加了字段：名字不在 `search_space()`，维数仍 10 |
| `tasks/task 084.md` / `STATUS.md` | Task 1 落盘拍板；实现收尾再回写局级 |

不改 `tests/test_features.py` 的期望。不改 `tests/test_heuristic_attack_quality.py` 的 chooser 断言。不新建第二套击杀前瞻。

---

### Task 1 — 把拍板写进规格与 task，然后停或继续

**Files:**
- Modify: `docs/superpowers/specs/2026-10-29-task-084-copy-lethal-short-circuit-design.md`（状态行 + Q 表勾选）
- Modify: `tasks/task 084.md`
- Modify: `STATUS.md`

- [x] **Step 1: 按 Owner 勾选改 Q 表**

Q1–Q8 已写入规格第 5 节。Q2=C。

- [x] **Step 2: Q2=C 时收口并停止**

行为维持 main `4262a9f`。策略债记录在案。不重跑 100 局。同格 \|Δ\| 47.2 不由本刀关。`STATUS.md` 焦点改为「084 维持短路，残差另计」。未改 `heuristic.py`。未做 Task 2。

- [x] **Step 3: Q2=A 或 B 时才继续**

跳过。Q2=C。

- [x] **Step 4: Commit（无论 C 还是继续）**

```bash
git add docs/superpowers/specs/2026-10-29-task-084-copy-lethal-short-circuit-design.md tasks/task\ 084.md STATUS.md
git commit -m "docs(084): record owner decision on copy lethal short-circuit"
```

---

Task 2–5 **不执行**。Q2=C 已收口。下面的红测与实现草稿留档，不是本分支的授权。

### Task 2 — 红测（仅 Q2=A 或 B；本次跳过）

**Files:**
- Modify: `tests/test_heuristic_ko_prize_lookahead.py`
- Modify: `tests/test_tune_space.py`（字段不进搜索空间）

**Interfaces:**
- Consumes: 现有 `_ko_state()` / `_observe()` / `HeuristicParams`
- Produces: 默认 `copy_lethal_policy` 等于拍板值；`"always"` 在同一夹具上仍返回攻击

现有 `test_copy_ko_attacks_before_supporter` 锁的是「复制斩杀先于支援者」。默认若不再是 always，把该测试改为显式 `copy_lethal_policy="always"`，断言仍是 `Action(kind="attack", attack_index=0)`。不要删掉这句。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_heuristic_ko_prize_lookahead.py` 增加下面这些测试。夹具复用 `_ko_state()`（手牌有支援者 iid=61，复制能斩杀）。

```python
def test_always_copy_ko_still_attacks_before_supporter():
    params = HeuristicParams(copy_lethal_policy="always")
    act = _observe(_ko_state(), params)
    assert act == Action(kind="attack", attack_index=0)


def test_never_copy_ko_plays_supporter_but_lookahead_stays_true():
    params = HeuristicParams(copy_lethal_policy="never")
    state = _ko_state()
    act = _observe(state, params)
    assert act == Action(kind="play_trainer", iid=61)
    agent, view = _agent_view(state, params)
    look = agent._ko_prize_lookahead(view)
    assert look.can_ko is True
    assert look.via == "copy"


def test_never_still_short_circuits_printed_ko():
    """印面 200 对剩余约 90，且这只没有 copy_attack。never 仍先攻击。"""
    attacker = CardDef(
        card_id="stub-印面", name="印面", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="打击", cost=("无",), damage=200),),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, attacker, energies=1),
        "bench": (),
        "hand": (inst(61, _supporter()),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=100, damage=10), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    params = HeuristicParams(copy_lethal_policy="never")
    act = _observe(state, params, card_effects={})
    assert act == Action(kind="attack", attack_index=0)


def test_unless_setup_trainer_defers_when_supporter_legal():
    params = HeuristicParams(copy_lethal_policy="unless_setup_trainer")
    act = _observe(_ko_state(), params)
    assert act == Action(kind="play_trainer", iid=61)


def test_unless_setup_trainer_attacks_when_no_item_or_supporter():
    params = HeuristicParams(copy_lethal_policy="unless_setup_trainer")
    state = _ko_state()
    p0 = state.players[0].model_copy(update={"hand": ()})
    state = state.model_copy(update={"players": (p0, state.players[1])})
    act = _observe(state, params)
    assert act == Action(kind="attack", attack_index=0)
```

`main_state()` 的牌库是 10 张，默认 `deck_low_threshold` 是 6，所以上面的支援者不被抑制。

再加牌库保护那条。`测试支援者` 的文档含 `draw`，`_ko_state()` 已经带这张牌。把地板抬到牌库张数，抑制应生效，复制斩杀重新短路：

```python
def test_unless_setup_trainer_ignores_draw_supporter_when_deck_low():
    params = HeuristicParams(
        copy_lethal_policy="unless_setup_trainer",
        deck_low_threshold=10,
    )
    act = _observe(_ko_state(), params)
    assert act == Action(kind="attack", attack_index=0)


def test_copy_ko_still_refuses_retreat_when_short_circuit_is_off():
    """政策只挡短路。前瞻 can_ko 仍真，所以战斗场仍不撤。"""
    donor = _mon("供体", owner="N", hp=100, damage=200, cost=())
    state = _base(donor=donor, opp_hp=100, hand=())
    params = HeuristicParams(copy_lethal_policy="never")
    agent, view = _agent_view(state, params)
    assert agent._ko_prize_lookahead(view).can_ko is True
    retreats = [a for a in _engine(state).legal_actions(0) if a.kind == "retreat"]
    assert retreats
    assert agent._pick_retreat(view, retreats) is None
```

`"unless_setup_trainer"` 用同一夹具再断言一次 `_pick_retreat(...) is None`。

`tests/test_tune_space.py`：`len(search_space())==10`，且 `"copy_lethal_policy"` 不在搜索维名字里。默认值断言跟 Q2。

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_heuristic_ko_prize_lookahead.py tests/test_tune_space.py -q
```

预期：`copy_lethal_policy` 不存在，或默认行为仍先攻击而新断言要训练家。

- [ ] **Step 3: Commit the red tests**

```bash
git add tests/test_heuristic_ko_prize_lookahead.py tests/test_tune_space.py
git commit -m "test(084): copy lethal short-circuit policy"
```

---

### Task 3 — 最小实现（仅 Q2=A 或 B）

**Files:**
- Modify: `battlefrontier/agent/heuristic.py`（`HeuristicParams`、`_decide_main`、新的 `_setup_trainer_available`）

**Interfaces:**
- Consumes: `_ko_prize_lookahead(view).via` / `.can_ko`；`by_kind` 里的 `play_trainer`
- Produces: `HeuristicParams.copy_lethal_policy` 默认 `"always" | "unless_setup_trainer" | "never"` 中的拍板值
- 不产生：前瞻 `can_ko` 的变化、`_attack_table` 的变化、`prize_pressure_gate`

- [ ] **Step 1: 字段**

在 `ko_prize_lookahead_gate` 旁边增加：

```python
# 复制击杀是否占用斩杀短路（task 084）。
# always：083 合入行为。unless_setup_trainer：有物品/支援者则先打训练家。
# never：复制永不短路。不进 tune。印面斩杀不受影响。
copy_lethal_policy: str = "always"  # 默认改成拍板值
```

默认字符串必须是 Q2 对应的那个值，不要留 `"always"` 当 Q2 已经是 B 或 A。

- [ ] **Step 2: 短路过滤**

`_decide_main` 里现有的：

```python
if acts := by_kind.get("attack"):
    lethal = self._lethal_attack(view, acts)
    if lethal is not None:
        return lethal
```

改为：先取 lethal；若不为 None，再 `_ko_prize_lookahead(view)`。`via != "copy"` 则返回 lethal。`via == "copy"` 时：

```python
def _copy_may_short_circuit(self, view: VisibleGameState, by_kind: dict[str, list[Action]]) -> bool:
    policy = self.params.copy_lethal_policy
    if policy == "always":
        return True
    if policy == "never":
        return False
    if policy == "unless_setup_trainer":
        return not self._setup_trainer_available(view, by_kind)
    return True
```

未知字符串按 `"always"` 处理并保持现有测试绿，不要抛给对局。

`_setup_trainer_available`：看 `by_kind["play_trainer"]`。留下 `trainer_subtype` 为「物品」或「支援者」的。`self._deck_low(view)` 且 `card_has_draw(...)` 的去掉，调用方式抄 `_decide_main` 里物品/支援者两段。剩下非空则 True。不读卡名。不把 `attach_tool` / `play_stadium` / `retreat` 算进来（除非 Q3 改了规格；改了就先改规格再改这个函数）。

`_lethal_attack` 函数体保持「前瞻 can_ko 就返回该攻击」。政策不要写进 `_one_layer_copy`。

- [ ] **Step 3: Run tests — expect PASS；ruff clean**

```bash
python -m pytest tests/test_heuristic_ko_prize_lookahead.py tests/test_heuristic_board_gate.py tests/test_heuristic_agent.py tests/test_heuristic_attack_quality.py tests/test_features.py tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/heuristic.py tests/test_heuristic_ko_prize_lookahead.py tests/test_tune_space.py
```

- [ ] **Step 4: Commit**

```bash
git add battlefrontier/agent/heuristic.py tests/test_heuristic_ko_prize_lookahead.py tests/test_tune_space.py
git commit -m "task(084): gate copy KO on the lethal short-circuit"
```

---

### Task 4 — 局级（仅 Q2=A 或 B；Diupi-Yun；云端跳过）

种子 `208000..208099`。失败必须 0。

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t084-gard-zoro.db
bfsim report <id> --results results/t084-gard-zoro.db --decisions
```

表内写：A/B 胜率、prizes、deck_out、no_pokemon、暗夜王牌触及、失败数、相对 t080 的翻转。旁边列 t080（A78/B22，B prizes 9）和 083（A72/B28，B prizes 14）。

不预设 A 必须低于 72。Q2=A 的消融已是 A75 / B prizes 9，若复跑一致，写「与消融同向」。Q2=B 没有先验，数字是多少写多少。

可选：同格 500 的 sim 与 \|Δ\|（对照 80.0% / 49.6，以及 083 后的 77.6% / 47.2）。Q7 默认不做完成本条件。不跑 18000。

回写 `tasks/task 084.md` 与 `STATUS.md`。

---

### Task 5 — 实现 PR 自检（仅 Q2=A 或 B）

- [ ] 无 `prize_pressure_gate`
- [ ] 无 `ABLATION_COPY_NOT_LETHAL`
- [ ] 无卡名分支
- [ ] `_ko_prize_lookahead` 在复制能斩杀时 `can_ko` 仍为真（政策只挡短路）
- [ ] `_ko_remaining` 与弃牌 / 附伤路径的 diff 为空
- [ ] `tests/test_features.py` 未改期望
- [ ] tune `len(search_space()) == 10`
- [ ] 未读 `modify_attack_cost`
- [ ] `"always"` 回归仍先于支援者攻击

## 与 083 计划的关系

| 计划 | 关系 |
|---|---|
| `docs/superpowers/plans/2026-10-29-task-083-shared-ko-prize-lookahead.md` | 已执行并合入 PR #12。本计划不重做 F1/F3，不改有效 HP |
| `docs/superpowers/plans/2026-10-29-task-081-prize-pressure.md` | 继续不执行 |
