# 081 落后抢奖 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **待 Owner 拍板。** 拍板前不执行。Q1–Q8 以 `docs/superpowers/specs/2026-10-29-task-081-prize-pressure-design.md` 拍板后的值为准。下文按「本文建议」起草。复制招式击杀前瞻是 task 082，不在本计划。

**Goal:** 落后时，谁都不能击杀就换上已付清、输出更高的备战；promote 优先能击杀拿奖的备战。同种子 100 局看 A 胜率是否从约 78% 往 60–70% 走。

**Architecture:** 只在 `HeuristicAgent` 内增加 `prize_pressure_gate`。撤退与 promote 在落后时改排序。`pokemon_score` 与 `factor_prize_diff` 不动。不读 `copy_attack`。不改引擎、不改 DSL。

**Tech Stack:** Python 3.12+、`tests/helpers.py`、pytest、ruff。局级验收用 `bfsim`，需要本机 `ptcg-cn.db`。

**权威设计：** `docs/superpowers/specs/2026-10-29-task-081-prize-pressure-design.md`。

## Global Constraints

- 零卡名分支。不要写 `if name ==`。
- `pokemon_score` 与 `factor_prize_diff` 的公式和权重不动。`tests/test_features.py` 的期望不得改。落后是 `own.prizes_count > opponent.prizes_count`。
- `prize_pressure_gate` 不进 `tune/space.py` 的 10 维。`bool_fields` 要包含它，`len(search_space())` 仍是 10。
- 费用继续用印面 `_energy_satisfied`。不读 `modify_attack_cost`。
- 不改 `_pick_energy_attach`、`_place_key`、`_pick_attack`、`_copy_donor_key`、`_attack_table`、`play_stadium` / `end_turn` 的位置、`_decide_main` 的大顺序。
- 不新增 `copy_lethal_gate`。不实现 task 082。
- 不引入 JEV/LLM，不改 MCTS/蒸馏，不改 DSL/引擎，不跑 18000。
- 失败局必须是 0。云端无库，不跑 `bfsim`。
- tie-break 用下标升序，不消费随机源。
- 不新增整数阈值。
- Q7 若否决 promote：不要写 promote 的三条测试，不要改 `_pick_promote`。

---

### Task 1: 落后抢奖

**Files:**
- Create: `tests/test_heuristic_prize_pressure.py`
- Modify: `battlefrontier/agent/heuristic.py`（`prize_pressure_gate`、`_pick_retreat`、`_pick_promote`、`_prize_behind`）
- Modify: `tests/test_tune_space.py`（`bool_fields` 加上 `prize_pressure_gate`）
- Modify: `tasks/task 081.md`、`STATUS.md`（实现收尾时写结果）

**Interfaces:**
- Consumes: `_max_paid_ko_damage`、`_view_as_active`、`pokemon_score`、`_pick_retreat_powerless`
- Produces: `HeuristicParams.prize_pressure_gate: bool = True`
- Produces: `_prize_behind(view) -> bool`
- Produces: 开关开且落后、两边都不能击杀时，撤到已付清有效伤害严格更高的备战
- Produces: 开关开且落后、对手战斗场存在、备战有已付清击杀时，`_pick_promote` 选该备战

夹具不用 `copy_attack`。

- [ ] **Step 1: Write the failing test**

`tests/test_heuristic_prize_pressure.py`：

```python
"""task 081：落后抢奖。不改 pokemon_score 公式。"""

from helpers import engine_at, in_play, main_state

from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams, pokemon_score
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef


def decide(engine, params=None):
    agent = HeuristicAgent(params)
    view = engine.state.visible_state(0)
    return agent.observe(view, engine.legal_actions(0))


def poke(name: str, *, hp: int, damage: int, cost: int, retreat: int) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, retreat_cost=retreat,
        attacks=(AttackDef(name="打击", cost=("无",) * cost, damage=damage),),
    )


def _chip_state(*, own_prizes: int, opp_prizes: int):
    """战斗场 30 付得起，备战 120 付得起，对手 200。都打不倒。手里清空，避免附着。"""
    active = poke("低伤", hp=110, damage=30, cost=1, retreat=0)
    bench = poke("高伤", hp=120, damage=120, cost=1, retreat=1)
    opp = poke("靶", hp=200, damage=10, cost=1, retreat=1)
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(3, bench, energies=1),),
        "hand": (),
        "prizes": state.players[0].prizes[:own_prizes],
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, opp, energies=0),
        "prizes": state.players[1].prizes[:opp_prizes],
    })
    return state.model_copy(update={"players": (p0, p1)})


def test_behind_retreats_to_higher_chip_when_nobody_kos():
    """我方奖赏剩 6、对手剩 2（落后）。30 和 120 都打不满 200 → 撤退。"""
    act = decide(engine_at(_chip_state(own_prizes=6, opp_prizes=2)))
    assert act == Action(kind="retreat", bench_index=0)


def test_tied_prizes_do_not_retreat_for_chip():
    """双方都剩 6。未落后 → 不撤，打出 30。"""
    act = decide(engine_at(_chip_state(own_prizes=6, opp_prizes=6)))
    assert act.kind == "attack"


def test_ahead_does_not_retreat_for_chip():
    """我方剩 2、对手剩 6（领先）→ 不撤。"""
    act = decide(engine_at(_chip_state(own_prizes=2, opp_prizes=6)))
    assert act.kind == "attack"


def test_gate_off_keeps_chip_active_even_when_behind():
    """prize_pressure_gate=False：落后也不为了更高的非击杀而撤。"""
    params = HeuristicParams(prize_pressure_gate=False)
    act = decide(engine_at(_chip_state(own_prizes=6, opp_prizes=2)), params)
    assert act.kind != "retreat"


def test_existing_ko_retreat_still_happens_when_tied():
    """未落后，但备战能击杀、战斗场不能：仍是 078 的撤退。"""
    active = poke("低伤", hp=110, damage=30, cost=1, retreat=0)
    bench = poke("杀招", hp=160, damage=190, cost=1, retreat=1)
    opp = poke("靶", hp=150, damage=10, cost=1, retreat=1)
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(3, bench, energies=1),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp, energies=0)})
    act = decide(engine_at(state.model_copy(update={"players": (p0, p1)})))
    assert act == Action(kind="retreat", bench_index=0)


def _promote_state(*, own_prizes: int, opp_prizes: int):
    """墙：HP 800 印面 10，分更高，0 能量。击杀手：HP 70 印面 90，已付 1 能量。

    对手 HP 80。90 能击杀，10 不能。
    pokemon_score 默认 1/5/−10：墙 800+50−10=840，击杀手 70+450−10=510。
    """
    wall = poke("墙", hp=800, damage=10, cost=1, retreat=1)
    killer = poke("斩", hp=70, damage=90, cost=1, retreat=1)
    opp = poke("靶", hp=80, damage=10, cost=1, retreat=1)
    state = main_state()
    params = HeuristicParams()
    assert pokemon_score(in_play(30, wall), params) > pokemon_score(in_play(31, killer), params)
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (in_play(30, wall, energies=0), in_play(31, killer, energies=1)),
        "hand": (),
        "prizes": state.players[0].prizes[:own_prizes],
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, opp, energies=0),
        "prizes": state.players[1].prizes[:opp_prizes],
    })
    return state.model_copy(update={"players": (p0, p1), "phase": "promote"})


def test_promote_when_behind_prefers_paid_ko():
    """落后 → promote 下标 1（已付清且能击杀），不是分更高的墙。"""
    act = decide(engine_at(_promote_state(own_prizes=6, opp_prizes=2)))
    assert act == Action(kind="promote", bench_index=1)


def test_promote_when_tied_stays_on_pokemon_score():
    """未落后 → 仍 promote 墙（下标 0）。"""
    act = decide(engine_at(_promote_state(own_prizes=6, opp_prizes=6)))
    assert act == Action(kind="promote", bench_index=0)


def test_promote_gate_off_stays_on_pokemon_score():
    params = HeuristicParams(prize_pressure_gate=False)
    act = decide(engine_at(_promote_state(own_prizes=6, opp_prizes=2)), params)
    assert act == Action(kind="promote", bench_index=0)
```

`test_behind_retreats_to_higher_chip_when_nobody_kos` 与 `test_promote_when_behind_prefers_paid_ko` 在今天的代码上会失败：撤退测试实际是 `attack`，promote 测试实际是 `bench_index=0`。未落后的测试与 078 的击杀撤退应当已经 PASS。开关关闭的两条在字段不存在时是 `TypeError`。

若 promote 的 `legal_actions` 不含 `promote`，先修夹具（`phase="promote"`、`active is None`、备战非空），不要改引擎。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_heuristic_prize_pressure.py -q`

Expected: 落后撤退 FAIL（实际 `attack`）。落后 promote FAIL（实际 `bench_index==0`）。未落后与 078 击杀撤退 PASS。

- [ ] **Step 3: Write minimal implementation**

```python
# 落后抢奖（task 081，D-081-4/5）。False = 撤退与 promote 回到今天。
# 不进 tune。落后 = 我方剩余奖赏 > 对手剩余奖赏。不读 factor_prize_diff。
prize_pressure_gate: bool = True
```

```python
def _prize_behind(view) -> bool:
    return view.own.prizes_count > view.opponent.prizes_count
```

`_pick_retreat`：在「备战能击杀」的列表为空、调用 `_pick_retreat_powerless` 之前插入。`board_quality_gate` 关时仍直接走 powerless。

```python
if (
    self.params.prize_pressure_gate
    and _prize_behind(view)
    and active_best is not None
):
    higher: list[tuple[int, Action]] = []
    for act in acts:
        mon = view.own.bench[act.bench_index]
        best = self._max_paid_ko_damage(self._view_as_active(view, mon))
        if best is not None and best > active_best:
            higher.append((best, act))
    if higher:
        return min(higher, key=lambda item: (-item[0], item[1].bench_index))[1]
return self._pick_retreat_powerless(view, acts)
```

`active_best is None` 时不要走这条。`_pick_promote`：

```python
def _pick_promote(self, view, acts):
    def by_score(pool):
        return min(
            pool,
            key=lambda a: (
                -pokemon_score(view.own.bench[a.bench_index], self.params),
                a.bench_index,
            ),
        )

    if not (self.params.prize_pressure_gate and _prize_behind(view)):
        return by_score(acts)
    opp = view.opponent.active
    if opp is None:
        return by_score(acts)
    remaining = (opp.current.card.hp or 0) - opp.damage
    ko = []
    for act in acts:
        mon = view.own.bench[act.bench_index]
        best = self._max_paid_ko_damage(self._view_as_active(view, mon))
        if best is not None and best >= remaining:
            ko.append((best, act))
    if not ko:
        return by_score(acts)
    return min(
        ko,
        key=lambda item: (
            -item[0],
            -pokemon_score(view.own.bench[item[1].bench_index], self.params),
            item[1].bench_index,
        ),
    )[1]
```

不要改 `_decide_main` 的大顺序。红测已经把 `hand` 设成 `()`。

- [ ] **Step 4: Run test to verify it passes**

`tests/test_tune_space.py` 的 `bool_fields` 加上 `"prize_pressure_gate"`。不要放进 `CONTINUOUS_DIMS` 或 `INTEGER_DIMS`。

Run:

```bash
python -m pytest tests/test_heuristic_prize_pressure.py tests/test_heuristic_board_gate.py tests/test_heuristic_agent.py tests/test_features.py tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/heuristic.py tests/test_heuristic_prize_pressure.py tests/test_tune_space.py
```

Expected: PASS，ruff 零告警。`test_features.py` 期望不改。078 的击杀撤退仍 PASS。

- [ ] **Step 5: Commit**

```bash
git add battlefrontier/agent/heuristic.py tests/test_heuristic_prize_pressure.py tests/test_tune_space.py
git commit -m "task(081): 落后时换上更高输出，promote 优先能击杀拿奖的备战"
```

---

### Task 2: 本机 100 局（Diupi-Yun；云端跳过）

**Files:**
- Modify: `tasks/task 081.md`、`STATUS.md`
- 不修改 `experiments/t078-gard-zoro.example.yml`

- [ ] **Step 1: 确认单测已绿**

云端到此为止：无 `ptcg-cn.db`，不跑 `bfsim`。结果节写「云端跳过 100 局」。

- [ ] **Step 2: 默认开关开**

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t081-gard-zoro.db
bfsim report <id> --results results/t081-gard-zoro.db --decisions
```

对照 task 080 的同种子 100 局（A78 / B22，失败 0）。记下 A/B 胜率、A 的 prizes / deck_out / no_pokemon、失败数。失败必须是 0。

有效带：A 胜率进入 **60–70%** 算 081 方向有效。到不了也写实。不写「达到真实 30%」。不写「|Δ| 闭环」。不跑 `experiments/v2-calibration.example.yml`。不把这次和以后的 082 合成一条带。

- [ ] **Step 3: Commit**

```bash
git add tasks/task\ 081.md STATUS.md
git commit -m "docs(081): Diupi-Yun 100局验收回写"
```

---

### Task 3: 短行样本（仅当规格 Q4 拍板要跑）

Q4 维持「短行不是有效带」时可以跑，数字不拿来改 60–70%。Q4 若改成「只 100」，跳过本节。

**Files:** 五份单格实验，目录 `experiments/t081-nzoro-row/`。每份都是 `decks` + `games`，不要用 `matrix:`。模板与 `experiments/t078-gard-zoro.example.yml` 同构，两边 heuristic。

| 文件 | 对手 deck_id | games | seed_start |
|---|---|---|---|
| `t081-nzoro-gard.example.yml` | `mik_moe:678647` | 50 | 220000 |
| `t081-nzoro-pult.example.yml` | `mik_moe:677868`（多龙巴鲁托） | 50 | 220000 |
| `t081-nzoro-grimm.example.yml` | `mik_moe:687339` | 50 | 220000 |
| `t081-nzoro-bolt.example.yml` | `mik_moe:676249` | 20 | 220000 |
| `t081-nzoro-joltik.example.yml` | `mik_moe:677291` | 20 | 220000 |

N索侧都是 `mik_moe:690359`。不要覆盖 `results/t081-gard-zoro.db`。

停手：沙奈朵 / 多龙 / 玛俐三格的 N索胜率低于本刀前同种子重放。猛雷鼓 / 电电虫只记 deck_out 胜场。恶化写进任务卡，不调阈值。云端跳过。

- [ ] **Step 1: 写 YAML 并确认加载器能解析**

仿 `tests/test_heuristic_ability_gate.py` 的 `read_text(encoding="utf-8")`，断言 `games` 与 `seed_start`。沙奈朵这份不要要求 `games==100`。

- [ ] **Step 2: 本机运行**

```bash
bfsim run experiments/t081-nzoro-row/t081-nzoro-pult.example.yml --workers 8 --results results/t081-nzoro-pult.db
bfsim report <id> --results results/t081-nzoro-pult.db
```

其余四份换路径。失败局必须是 0。不跑 18000。不要提交 `results/*.db`。

- [ ] **Step 3: Commit**

```bash
git add experiments/t081-nzoro-row tasks/task\ 081.md STATUS.md
git commit -m "docs(081): N索短行样本回写"
```

---

## 规格覆盖

| 规格 | 计划落点 |
|---|---|
| D-081-5 落后才换更高输出；未落后不撤 | Task 1 前四条 |
| D-081-5 078 击杀撤退保持 | `test_existing_ko_retreat_still_happens_when_tied` |
| D-081-5 promote（Q7 默认包含） | Task 1 后三条；Q7 否决则删除 |
| D-081-3 公式冻结 | Task 1 Step 4 跑 `test_features.py` |
| D-081-4 不进 tune | `bool_fields` |
| D-081-2 零卡名 | 夹具全是 stub |
| Q2 血月 / Q6 end_turn | 无步骤 |
| D-081-6 100 局，对照 080 | Task 2 |
| D-081-6 短行 | Task 3，仅 Q4 批准 |
| 不实现 082 | 无 `copy_lethal_gate` 步骤 |
