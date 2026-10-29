# 奖杯压力与复制斩杀 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **规格待拍板。** 拍板前不执行本计划。Q1–Q9 以 `docs/superpowers/specs/2026-10-29-task-081-prize-pressure-design.md` 第 5 节拍板后的值为准。下文按「本文建议」列起草：一个 task 081、两个开关、Q4 维持否、Q9 包含 promote、Q5 的短行不是完成条件。

**Goal:** 让启发式在「奖赏落后且谁都不斩杀」时换上更高的已付清一击、在 promote 时优先能斩杀的备战，并把已付清的 `copy_attack` 按一层供体前瞻算进斩杀判定。用沙奈朵 × N索的同种子 100 局看 A 胜率是否从约 78% 往 60–70% 走。

**Architecture:** 两包都在 `HeuristicAgent` 内。`prize_pressure_gate` 管落后时的撤退与 promote。`copy_lethal_gate` 管复制前瞻，写进 `_lethal_attack` 与 `_max_paid_ko_damage`，不写进 `_attack_table`。`pokemon_score` 与 `factor_prize_diff` 不动。不改引擎枚举、不改 DSL schema。

**Tech Stack:** Python 3.12+、现有 `HeuristicAgent` / `GameEngine` 测试夹具（`tests/helpers.py`）、pytest、ruff。局级验收用 `bfsim`，需要本机 `ptcg-cn.db`。

**权威设计：** `docs/superpowers/specs/2026-10-29-task-081-prize-pressure-design.md`。

## Global Constraints

- 默认零卡名分支。规格 Q4 的例外清单为空；不要写 `if name ==`。`owner` 与 DSL `filters` 经 `matches_in_play` 读取，未知 filter 的 `DslError` 不猜，该招式维持印面。
- `pokemon_score` 的公式与默认权重不动。`factor_prize_diff` 的公式与 `w_prize_diff` 不动。`tests/test_features.py` 的期望不得改。落后判定是 `own.prizes_count > opponent.prizes_count`，不要用 `factor_prize_diff > 0`。
- 新布尔不进 `tune/space.py` 的 10 维。`tests/test_tune_space.py` 的 `bool_fields` 要包含新字段，`len(search_space())` 仍是 10。
- 费用匹配继续用印面 `_energy_satisfied`（D-WP8-5）。Q2 维持否，不读 `modify_attack_cost`，不调用 `GameEngine._effective_attack_cost`。
- 不改 `_pick_energy_attach`、`_place_key`、`_copy_donor_key`、`_pick_attack` 的非斩杀排序、`play_stadium` / `end_turn` 的位置。
- 不引入 JEV/LLM，不改 MCTS/蒸馏路径，不改 DSL/引擎规则，不跑 18000 矩阵。
- 失败局必须是 0。单测红→绿之后才能跑 100 局。云端无库，不在 CI 里跑 `bfsim`。
- 确定性：tie-break 用 iid 或下标升序，不消费随机源。
- 复制前瞻只一层、只 `selector=own_bench_attack`。供体不用自己付费。不递归嵌套 `copy_attack`。
- 不新增整数阈值。需要「落后几张」或「伤害差多少」时停下来改规格。
- Q1 若拍板拆成 082：本文件 Task 2 不在 081 的 PR 里做。Task 1 的 `_max_paid_ko_damage` 不含复制前瞻。

---

### Task 1: WP A 奖杯压力

**Files:**
- Create: `tests/test_heuristic_prize_pressure.py`
- Modify: `battlefrontier/agent/heuristic.py`（`HeuristicParams.prize_pressure_gate`、`_pick_retreat`、`_pick_promote`；抽出 `_prize_behind`）
- Modify: `tests/test_tune_space.py`（`bool_fields` 加上 `prize_pressure_gate`）
- Modify: `tasks/task 081.md`、`STATUS.md`（实现收尾时写结果，不是本步的测试）

**Interfaces:**
- Consumes: `_max_paid_ko_damage`、`_view_as_active`、`pokemon_score`、`_pick_retreat_powerless`
- Produces: `HeuristicParams.prize_pressure_gate: bool = True`
- Produces: `_prize_behind(view) -> bool`，真值当且仅当 `view.own.prizes_count > view.opponent.prizes_count`
- Produces: 开关开且落后、两边都不能斩杀时，`_pick_retreat` 撤到已付清有效伤害严格更高的备战；否则行为与今天相同
- Produces: 开关开且落后、对手战斗场存在、备战有已付清斩杀时，`_pick_promote` 选该备战；否则仍按 `pokemon_score`

本任务的夹具不用 `copy_attack`。复制前瞻是 Task 2 的事。Q9 若否决 promote，不要写 `test_promote_when_behind_prefers_paid_ko` 与 `test_promote_when_tied_stays_on_pokemon_score`，也不要改 `_pick_promote`。

- [ ] **Step 1: Write the failing test**

`tests/test_heuristic_prize_pressure.py`：

```python
"""task 081 WP A：落后时的奖杯压力。不改 pokemon_score 公式。"""

from helpers import basic, engine_at, in_play, inst, main_state

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
    """战斗场 30 付得起，备战 120 付得起，对手 200。谁都不斩杀。手里清空，避免附着。"""
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
    """我方奖赏剩 6、对手剩 2（落后）。30 打不满 200，120 也打不满 → 撤退。"""
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
    """prize_pressure_gate=False：落后也不为了更高的非斩杀而撤。"""
    params = HeuristicParams(prize_pressure_gate=False)
    act = decide(engine_at(_chip_state(own_prizes=6, opp_prizes=2)), params)
    assert act.kind != "retreat"


def test_existing_ko_retreat_still_happens_when_tied():
    """未落后，但备战能斩杀、战斗场不能：仍是 078 的撤退，不依赖奖杯压力。"""
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
    """墙：HP 800 印面 10，分更高，0 能量付不起。斩杀手：HP 70 印面 90，已付 1 能量。

    对手 HP 80。90 能斩杀，10 不能。
    pokemon_score 默认 1/5/−10：墙 800+50−10=840，斩杀手 70+450−10=510。
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
    """落后 → promote 下标 1（已付清且斩杀），不是分更高的墙。"""
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

`test_behind_retreats_to_higher_chip_when_nobody_kos` 与 `test_promote_when_behind_prefers_paid_ko` 在今天的代码上会失败：撤退测试实际是 `attack`，promote 测试实际是 `bench_index=0`。这是预期的红。`test_tied_prizes_do_not_retreat_for_chip`、`test_ahead_does_not_retreat_for_chip`、`test_existing_ko_retreat_still_happens_when_tied`、`test_promote_when_tied_stays_on_pokemon_score` 应当已经 PASS。开关关闭的两条在字段不存在时是 `TypeError`，字段加上、函数未改时应当 PASS。

若 promote 夹具的 `legal_actions` 不含 `promote`，先修夹具（`phase="promote"`、`active is None`、备战非空），不要改引擎。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_heuristic_prize_pressure.py -q`

Expected: `test_behind_retreats_to_higher_chip_when_nobody_kos` FAIL（实际 `kind=="attack"`）。`test_promote_when_behind_prefers_paid_ko` FAIL（实际 `bench_index==0`）。开关关闭的测试在字段加上之前可以是 `TypeError`。未落后 / 078 斩杀撤退应当 PASS。

- [ ] **Step 3: Write minimal implementation**

`HeuristicParams` 增加：

```python
# 奖杯压力（task 081，D-081-4/5）。False = 撤退与 promote 回到今天。
# 不进 tune。落后 = 我方剩余奖赏 > 对手剩余奖赏。不读 factor_prize_diff。
prize_pressure_gate: bool = True
```

```python
def _prize_behind(view) -> bool:
    return view.own.prizes_count > view.opponent.prizes_count
```

`_pick_retreat`：在「备战能斩杀」的 `ko_targets` 为空、调用 `_pick_retreat_powerless` 之前插入。`board_quality_gate` 关时仍然直接走 powerless，本刀不绕过 078 的总开关。

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

`active_best is None`（战斗场没有任何已付清且 `lethal_ok` 的招式）时不要走这条，交给 powerless。战斗场 0 伤的纯效果招式若 `lethal_ok` 且费用已付，`active_best` 为 0，备战更高则会撤。WP A 的红测不用这种卡。

`_pick_promote`：

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

不要为了让撤退测试变绿去改 `_decide_main` 的大顺序。手里有能量时附着仍在撤退前面；红测已经把 `hand` 设成 `()`。

- [ ] **Step 4: Run test to verify it passes**

`tests/test_tune_space.py` 的 `bool_fields` 加上 `"prize_pressure_gate"`。不要把该字段放进 `CONTINUOUS_DIMS` 或 `INTEGER_DIMS`。

Run:

```bash
python -m pytest tests/test_heuristic_prize_pressure.py tests/test_heuristic_board_gate.py tests/test_heuristic_agent.py tests/test_features.py tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/heuristic.py tests/test_heuristic_prize_pressure.py tests/test_tune_space.py
```

Expected: PASS，ruff 零告警。`test_features.py` 的手算期望一字不改。078 的 `test_retreat_to_bench_ko_when_active_chip_cannot_ko` 仍 PASS（那条是斩杀撤退，不依赖落后）。

- [ ] **Step 5: Commit**

```bash
git add battlefrontier/agent/heuristic.py tests/test_heuristic_prize_pressure.py tests/test_tune_space.py
git commit -m "task(081): 落后时换上更高的一击，promote 优先能斩杀的备战"
```

---

### Task 2: WP B 复制斩杀前瞻

**Files:**
- Create: `tests/test_heuristic_copy_lethal.py`
- Modify: `battlefrontier/agent/heuristic.py`（`copy_lethal_gate`、`_lethal_attack`、`_max_paid_ko_damage` 或它调用的前瞻）
- Modify: `tests/test_tune_space.py`（`bool_fields` 加上 `copy_lethal_gate`）

**Interfaces:**
- Consumes: `doc_for`、`flatten_steps`、`matches_in_play`、`_copied_strike`、`_energy_satisfied`、Task 1 的 `_prize_behind`（仅交互测试）
- Produces: `HeuristicParams.copy_lethal_gate: bool = True`
- Produces: 已付清、`selector=own_bench_attack` 的 `copy_attack`，其斩杀判定与「战斗场最高有效伤害」等于合法供体的一层 `_copied_strike` 最大值
- 不产生：`_attack_table` 的改动、`_pick_choose` 的改动、`dsl_estimate.py` 的改动

依赖：Task 1 的 `prize_pressure_gate` 可以已在树上。本任务里「复制能斩杀所以不撤退」的测试不把奖杯落后当条件。交互测试（复制 170、备战 120、落后、谁都不斩杀）才同时开两个开关。

- [ ] **Step 1: Write the failing test**

`tests/test_heuristic_copy_lethal.py`：

```python
"""task 081 WP B：copy_attack 的一层斩杀前瞻。不改攻击表，不改 080 的 chooser。"""

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams
from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

COPY_DOC = parse_card_doc("""
card:
  name_group: 复制手
effects:
  - trigger: on_attack
    attack: 暗夜
    actions:
      - {action: copy_attack, selector: own_bench_attack, choose: 1, filters: ["owner_pokemon:N"]}
""")
SUPPORTER_DOC = parse_card_doc("""
card:
  name_group: 测试支援者
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 2}
""")
FX = {"复制手": COPY_DOC, "测试支援者": SUPPORTER_DOC}


def _mon(name: str, *, owner: str | None, hp: int, damage: int, cost: tuple[str, ...]) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, retreat_cost=0, owner=owner,
        attacks=(AttackDef(name="打击", cost=cost, damage=damage),),
    )


def _copier() -> CardDef:
    return CardDef(
        card_id="stub-复制手", name="复制手", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="暗夜", cost=("无",), damage=None),),
    )


def _supporter():
    return CardDef(
        card_id="stub-测试支援者", name="测试支援者", supertype="trainer",
        trainer_subtype="支援者",
    )


def _engine(state):
    engine = engine_at(state)
    engine.card_effects = FX
    return engine


def _observe(state, params=None):
    engine = _engine(state)
    agent = HeuristicAgent(params, card_effects=FX)
    return agent.observe(engine.state.visible_state(0), engine.legal_actions(0))


def _base(*, donor, decoy=None, opp_hp: int, hand=(), own_prizes: int = 6, opp_prizes: int = 6):
    state = main_state()
    bench = [in_play(70, donor, energies=0)]
    if decoy is not None:
        bench.append(in_play(71, decoy, energies=0))
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": tuple(bench),
        "hand": hand,
        "prizes": state.players[0].prizes[:own_prizes],
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=opp_hp, damage=10), energies=0),
        "prizes": state.players[1].prizes[:opp_prizes],
    })
    return state.model_copy(update={"players": (p0, p1)})


def test_copy_ko_attacks_before_supporter():
    """供体 owner=N、印面 200、自己 0 能量。对手 HP 100。手牌只有支援者。

    今天攻击表是 0，先打支援者。前瞻后这一击能斩杀，observe 返回 attack。
    """
    donor = _mon("供体", owner="N", hp=100, damage=200, cost=("无", "无"))
    state = _base(donor=donor, opp_hp=100, hand=(inst(61, _supporter()),))
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_copy_lethal_gate_off_plays_supporter():
    donor = _mon("供体", owner="N", hp=100, damage=200, cost=("无", "无"))
    state = _base(donor=donor, opp_hp=100, hand=(inst(61, _supporter()),))
    params = HeuristicParams(copy_lethal_gate=False)
    act = _observe(state, params)
    assert act == Action(kind="play_trainer", iid=61)


def test_copy_ko_does_not_retreat_onto_bench_that_also_kos():
    """供体费用为空，自己站上场也能斩杀。今天 078 会撤退。前瞻后战斗场已能斩杀，不撤。"""
    donor = _mon("供体", owner="N", hp=100, damage=200, cost=())
    state = _base(donor=donor, opp_hp=100, hand=())
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_owner_filter_ignores_non_matching_ko():
    """N 供体只有 10 伤，打不满 HP 100。非 N 的 400 伤不进池。仍先打支援者。"""
    donor = _mon("供体", owner="N", hp=100, damage=10, cost=())
    decoy = _mon("路人", owner="别人", hp=100, damage=400, cost=())
    state = _base(
        donor=donor, decoy=decoy, opp_hp=100, hand=(inst(61, _supporter()),),
    )
    act = _observe(state)
    assert act == Action(kind="play_trainer", iid=61)


def test_no_doc_on_agent_does_not_guess():
    """引擎有文档（攻击合法），Agent 没文档 → 不猜，仍先支援者。"""
    donor = _mon("供体", owner="N", hp=100, damage=200, cost=("无", "无"))
    state = _base(donor=donor, opp_hp=100, hand=(inst(61, _supporter()),))
    engine = _engine(state)
    agent = HeuristicAgent(card_effects=None)
    act = agent.observe(engine.state.visible_state(0), engine.legal_actions(0))
    assert act == Action(kind="play_trainer", iid=61)


def test_behind_does_not_retreat_off_higher_copy_chip():
    """复制前瞻 170，备战已付清 120，对手 HP 300，谁都不斩杀，且落后。

    两开关都开：战斗场的复制更高，不撤。
    copy_lethal_gate 关：复制按 0，落后时撤到 120。
    """
    donor = _mon("供体", owner="N", hp=80, damage=170, cost=("无",))
    chip = CardDef(
        card_id="stub-备战", name="备战", supertype="pokemon", hp=100, stage=0,
        retreat_cost=0,
        attacks=(AttackDef(name="中", cost=("无",), damage=120),),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": (in_play(70, donor, energies=0), in_play(3, chip, energies=1)),
        "hand": (),
        "prizes": state.players[0].prizes[:6],
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=300), energies=0),
        "prizes": state.players[1].prizes[:2],
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state).kind == "attack"
    off = HeuristicParams(copy_lethal_gate=False)
    assert _observe(state, off) == Action(kind="retreat", bench_index=1)
```

`test_copy_ko_attacks_before_supporter` 今天失败：供体两费且 0 能量，备战斩杀分支不触发，攻击表是 0，实际 `play_trainer`。`test_copy_ko_does_not_retreat_onto_bench_that_also_kos` 今天失败：供体费用为空、200≥100，078 实际 `retreat`。`test_owner_filter_ignores_non_matching_ko` 与 `test_no_doc_on_agent_does_not_guess` 今天 PASS，实现后保持。`test_copy_lethal_gate_off_plays_supporter` 在字段不存在时是 `TypeError`。

`test_behind_does_not_retreat_off_higher_copy_chip` 在 Task 1 已落地、Task 2 未落地时是红：战斗场表内伤害 0，落后，120>0，实际 `retreat` 到下标 1；默认断言要 `attack`。`copy_lethal_gate=False` 在前瞻还没写时就已经是撤退，用来锁消融。不要改 Task 1 去凑这个红。当前 main（Task 1 也还没有）上，战斗场付得起 0 伤，`_pick_retreat_powerless` 返回 None，实际是 `attack`——所以这条红测的前提是 Task 1 先合进同一分支。Task 2 不要单独在没有 `prize_pressure_gate` 的树上跑这条。

`attack_quality` 的 chooser 测试不改断言。本文件不要再测一遍供体排序。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_heuristic_copy_lethal.py -q`

Expected: `test_copy_ko_attacks_before_supporter` FAIL（`play_trainer`）。`test_copy_ko_does_not_retreat_onto_bench_that_also_kos` FAIL（`retreat`）。`test_copy_lethal_gate_off_plays_supporter` 在字段不存在时 `TypeError`。过滤测试与无文档测试 PASS。`test_behind_does_not_retreat_off_higher_copy_chip` 只在 Task 1 已经在这棵树上时 FAIL（实际 `retreat`，断言 `attack`）；没有 Task 1 时它今天就是 `attack`，不能拿来当红。

- [ ] **Step 3: Write minimal implementation**

`HeuristicParams` 增加：

```python
# 复制斩杀前瞻（task 081，D-081-4/6）。False = 复制招式在斩杀/撤退里仍按印面。
# 不进 tune。不改 _attack_table，因此不改 _pick_attack 的非斩杀排序。
copy_lethal_gate: bool = True
```

前瞻只在 `copy_lethal_gate` 且 `self.card_effects is not None` 时运行。对战斗场每个已付清印面费用的招式：`doc_for` + `find_attack_effect`，`flatten_steps` 里找 `action=="copy_attack"` 且 `selector=="own_bench_attack"` 的节点。多个节点取先遇到的一个。没有则返回 None。

供体 = `[m for m in view.own.bench if matches_in_play(m, tuple(node.filters))]`。`matches_in_play` 抛 `DslError` 时整段返回 None（不猜）。对每个供体的每个招式下标调用已有 `_copied_strike`，不要再乘一次弱点。有 `ko` 为真的结果时，伤害取这些里的最大，斩杀为真；否则伤害取全部最大，斩杀为假。`find_attack_effect` 从 `battlefrontier.agent.dsl_estimate` 导入（该模块已有这个函数）。

`_lethal_attack`：在现有 `table` 之外，若某下标的前瞻 `ko` 为真，把该下标算进 `lethal` 列表，排序键用前瞻伤害。表内真实伤害已经 ≥ 剩余 HP 的招式保持今天的行为。前瞻返回 None 的下标不动。

`_max_paid_ko_damage`：在印面循环得到 `best` 之后，若前瞻伤害不是 None，`best = max(best or 0, looked)`，但仅当前瞻对应的那一招印面费用已付清（前瞻函数自己已经检查过就可以直接并）。没有印面伤害也没有前瞻时仍返回 None。

不要修改 `_attack_table`。不要修改 `_pick_choose`。不要在 `dsl_estimate.estimate_attack_damage` 里给 `copy_attack` 编一个伤害。

`test_behind_does_not_retreat_off_higher_copy_chip` 依赖 Task 1。关 `copy_lethal_gate` 时战斗场伤害按 0，`prize_pressure_gate` 默认开且落后。供体费用 `("无",)` 且 0 能量，印面 `_energy_satisfied` 为假，`_max_paid_ko_damage` 不计它。备战下标 1 的 120 伤已付 1 能量，120>0，撤退行动的 `bench_index` 是 1。

- [ ] **Step 4: Run test to verify it passes**

`bool_fields` 加上 `"copy_lethal_gate"`。`len(search_space())` 仍是 10。

Run:

```bash
python -m pytest tests/test_heuristic_copy_lethal.py tests/test_heuristic_prize_pressure.py tests/test_heuristic_attack_quality.py tests/test_heuristic_board_gate.py tests/test_agent_dsl_estimate.py tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/heuristic.py tests/test_heuristic_copy_lethal.py tests/test_tune_space.py
```

Expected: PASS。080 的复制 chooser 断言不改。078 的斩杀撤退不改。

- [ ] **Step 5: Commit**

```bash
git add battlefrontier/agent/heuristic.py tests/test_heuristic_copy_lethal.py tests/test_tune_space.py
git commit -m "task(081): 复制招式按一层供体前瞻参与斩杀"
```

---

### Task 3: 本机 100 局（Diupi-Yun；云端跳过）

**Files:**
- Modify: `tasks/task 081.md`、`STATUS.md`（只回写数字，不改门槛）
- 不修改 `experiments/t078-gard-zoro.example.yml`（已是 `games: 100`、`seed_start: 208000`）

- [ ] **Step 1: 确认单测已绿**

云端实现 PR 到此为止：无 `ptcg-cn.db`，不跑 `bfsim`。在 `tasks/task 081.md` 的结果节写「云端跳过 100 局」。然后由有库的机器执行下面的命令。

- [ ] **Step 2: 默认两开关都开**

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t081-gard-zoro.db
bfsim report <id> --results results/t081-gard-zoro.db --decisions
```

对照 task 080 的同种子 100 局（A78 / B22，失败 0）。记下 A/B 胜率、A 的 `prizes` / `deck_out` / `no_pokemon`、B 的暗夜王牌触及局、触及局中的 B 胜场、失败数。失败必须是 0。

有效带（规格 D-081-8）：A 胜率进入 **60–70%** 算方向有效。到不了也写实。不写「达到真实 30%」。不写「\|Δ\| 闭环」。不跑 `experiments/v2-calibration.example.yml`。

- [ ] **Step 3: 可选消融（不是完成条件）**

同一 YAML，两边 `params: {copy_lethal_gate: false}`，结果库换一个文件名。用来看 WP B 有没有单独贡献。没跑就在结果节写「未消融」。

- [ ] **Step 4: Commit**

```bash
git add tasks/task\ 081.md STATUS.md
git commit -m "docs(081): Diupi-Yun 100局验收回写"
```

---

### Task 4: 短行样本（仅当规格 Q5 拍板要跑）

Q5 维持「短行不是有效带」时，本节可以跑，但数字不拿来改 D-081-8 的 60–70%。Q5 若改成「只 100」，跳过本节，不新增 YAML。

**Files:**
- Create: 五份单格实验，或实现时合并成目录 `experiments/t081-nzoro-row/`。每份都是 `decks` + `games`，不要用 `matrix:`（矩阵会把池内对手也互相配对）。
- 模板与 `experiments/t078-gard-zoro.example.yml` 同构：两边 heuristic，不写卡名参数。

| 文件 | 对手 deck_id | games | seed_start |
|---|---|---|---|
| `t081-nzoro-gard.example.yml` | `mik_moe:678647` | 50 | 220000 |
| `t081-nzoro-pult.example.yml` | `mik_moe:677868`（多龙巴鲁托） | 50 | 220000 |
| `t081-nzoro-grimm.example.yml` | `mik_moe:687339` | 50 | 220000 |
| `t081-nzoro-bolt.example.yml` | `mik_moe:676249` | 20 | 220000 |
| `t081-nzoro-joltik.example.yml` | `mik_moe:677291` | 20 | 220000 |

N索侧都是 `mik_moe:690359`。沙奈朵那份与 `t078` 的 100 局种子不同，不要覆盖 `results/t081-gard-zoro.db`。

停手条件：沙奈朵 / 多龙 / 玛俐三格的 N索胜率低于本刀前同种子重放。猛雷鼓 / 电电虫只记 `deck_out` 胜场，不设必须变好。恶化写进 `tasks/task 081.md`，不调阈值。

云端跳过。

- [ ] **Step 1: 写 YAML 并确认加载器能解析**

仿 `tests/test_heuristic_ability_gate.py` 对 t077 YAML 的读法（`read_text(encoding="utf-8")`），断言 `games` 与 `seed_start`。沙奈朵这份不要要求它等于 100。

- [ ] **Step 2: 本机运行**

```bash
bfsim run experiments/t081-nzoro-pult.example.yml --workers 8 --results results/t081-nzoro-pult.db
bfsim report <id> --results results/t081-nzoro-pult.db
```

其余四份换路径。失败局必须是 0。不跑 18000。

- [ ] **Step 3: Commit**

```bash
git add experiments/t081-nzoro-*.example.yml tests/test_heuristic_prize_pressure.py tasks/task\ 081.md STATUS.md
git commit -m "docs(081): N索短行样本回写"
```

测试若放在别的文件，把实际路径写进 `git add`。不要提交 `results/*.db`。

---

## 规格覆盖（写计划时自检）

| 规格 | 计划落点 |
|---|---|
| D-081-5 落后才换更高一击；未落后不撤 | Task 1 前四条撤退测试 |
| D-081-5 078 斩杀撤退保持 | Task 1 `test_existing_ko_retreat_still_happens_when_tied` + Step 4 跑 board_gate |
| D-081-5 promote（Q9 默认包含） | Task 1 后三条；Q9 否决则删除 |
| D-081-3 `pokemon_score` / `factor_prize_diff` 不动 | Task 1 Step 4 跑 `test_features.py` 且不改期望 |
| D-081-6 复制斩杀先于支援者 | Task 2 `test_copy_ko_attacks_before_supporter` |
| D-081-6 复制能斩杀则不撤到备战 | Task 2 `test_copy_ko_does_not_retreat_onto_bench_that_also_kos` |
| D-081-6 过滤器、无文档不猜 | Task 2 两条锁测试 |
| D-081-6 与 WP A 叠用：更高的复制不撤 | Task 2 `test_behind_does_not_retreat_off_higher_copy_chip` |
| D-081-4 两开关不进 tune | Task 1 与 Task 2 各补 `bool_fields`，不断言 10 维变长 |
| D-081-2 零卡名 | 夹具全是 stub；供体用 `owner` 字段 |
| Q2 / 血月 | 无步骤 |
| Q8 end_turn / stadium | 无步骤。Task 2 不改 `_decide_main` 顺序 |
| D-081-7 100 局 | Task 3。云端跳过 |
| D-081-7 短行 | Task 4，仅 Q5 批准时 |
| D-081-8 不宣称 30% 与 \|Δ\| 闭环 | Task 3 Step 2 的写实要求 |
| 080 chooser 不改 | Task 2 Step 4 跑 `test_heuristic_attack_quality.py` 且不改断言 |
