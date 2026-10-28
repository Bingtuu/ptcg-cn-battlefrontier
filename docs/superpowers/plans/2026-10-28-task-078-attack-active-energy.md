# 攻击 / 前场 / 能量启发式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **owner 已整包拍板 Q1–Q8（按规格建议），规划 PR #5 merge `6bbcdbf`。** Task 1（078）按本文执行。Task 2 / 2b / 3（079 / 血月 / 080）本轮不做。

**Goal:** 让启发式在「低伤前场占着能斩杀的备战」「能量喂给差一张就能打的那只」「复制/变量招式按可见伤害选」三处改决策，并用沙奈朵 × N索的同种子 100 局看结构是否离开 deck_out 主导。

**Architecture:** 三刀都在 `HeuristicAgent` 内，各有一个 `HeuristicParams` 布尔开关，默认开，`False` 回到 `09e6a4c` 的行为。`pokemon_score` 公式不动。复燃的计数词补进 `dsl_estimate._visible_counter`，不走开关。不改引擎枚举、不改 DSL schema。

**Tech Stack:** Python 3.12+、现有 `HeuristicAgent` / `GameEngine` 测试夹具（`tests/helpers.py`）、pytest、ruff。局级验收用 `bfsim`，需要本机 `ptcg-cn.db`。

**权威设计：** `docs/superpowers/specs/2026-10-28-task-078-attack-active-energy-design.md`。

## Global Constraints

- 默认零卡名分支。规格 Q8 的例外清单为空；拍板前不要写 `if name ==`。
- `pokemon_score` 的公式与默认权重不动。`tests/test_features.py` 的 `RICH_EXPECTED` 不得改期望去迁就实现。
- 新布尔不进 `tune/space.py` 的 10 维。`tests/test_tune_space.py` 的 `bool_fields` 要包含新字段，`len(search_space())` 仍是 10。
- 费用匹配继续用印面 `_energy_satisfied`（D-WP8-5），除非 Q4 改为要读减费。默认 Q4 = 否，Task 2b 不执行。
- 不引入 JEV/LLM，不改 MCTS/蒸馏路径，不改 DSL/引擎规则，不跑 18000 矩阵。
- 失败局必须是 0。单测红→绿之后才能跑 100 局。云端无库，不在 CI 里跑 `bfsim`。
- 确定性：tie-break 用 iid 或下标升序，不消费随机源。
- 每一刀单独提交。下一刀开始时上一刀的开关默认已经是 True。

---

### Task 1: 078 前场与撤退

**Files:**
- Create: `tests/test_heuristic_board_gate.py`
- Create: `experiments/t078-gard-zoro.example.yml`（从 `experiments/t077-gard-zoro.example.yml` 复制，只改 `name`）
- Modify: `battlefrontier/agent/heuristic.py`（`HeuristicParams`、`_pick_place`、`_pick_retreat`；必要时抽出 `_attack_table` 能对「假设的战斗场」打分）
- Modify: `tests/test_tune_space.py`（`bool_fields` 加上 `board_quality_gate`）
- Modify: `tasks/task 078.md`、`STATUS.md`（实现收尾时写结果，不是本步的测试）

**Interfaces:**
- Consumes: `pokemon_score`、`_energy_satisfied`、`estimate_attack_damage`、`_attack_table` 的伤害口径
- Produces: `HeuristicParams.board_quality_gate: bool = True`
- Produces: `_pick_place` 在开关开时用 `_place_key`；关时键仍是 `(-pokemon_score, iid)`
- Produces: `_pick_retreat` 在开关开时，按规格 D-078-5 增加「备战能斩杀且战斗场不能」的撤退；关时只保留付不起才撤

- [x] **Step 1: Write the failing test**

`tests/test_heuristic_board_gate.py`：

```python
"""task 078：前场质量门控。不改 pokemon_score 公式。"""

from helpers import basic, energy, engine_at, in_play, inst, main_state, stage1

from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams, pokemon_score
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef, CardInstance


def decide(engine, params=None):
    agent = HeuristicAgent(params)
    view = engine.state.visible_state(0)
    return agent.observe(view, engine.legal_actions(0))


def two_attack(name: str, *, hp: int, damage: int, cost: int, retreat: int) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, retreat_cost=retreat,
        attacks=(AttackDef(name="打击", cost=("无",) * cost, damage=damage),),
    )


def test_retreat_to_bench_ko_when_active_chip_cannot_ko():
    """战斗场 60 付得起但不斩杀；备战 190 付得起且斩杀 → 撤退。"""
    active = two_attack("低伤", hp=110, damage=60, cost=1, retreat=0)
    bench = two_attack("杀招", hp=200, damage=190, cost=1, retreat=1)
    opp = two_attack("靶", hp=150, damage=10, cost=1, retreat=1)
    state = main_state(p0_active_energies=1, p1_active_energies=0)
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(3, bench, energies=1),),
        "hand": (),  # 手里有能量时 _decide_main 会先附着，测不到撤退
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp, energies=0)})
    state = state.model_copy(update={"players": (p0, p1)})
    act = decide(engine_at(state))
    assert act == Action(kind="retreat", bench_index=0)


def test_no_retreat_when_active_already_kos():
    """战斗场自己 190 已能斩杀 → 不撤，打出攻击。"""
    active = two_attack("已能杀", hp=200, damage=190, cost=1, retreat=0)
    bench = two_attack("备选", hp=200, damage=200, cost=1, retreat=1)
    opp = two_attack("靶", hp=150, damage=10, cost=1, retreat=1)
    state = main_state(p0_active_energies=1)
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(3, bench, energies=1),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp, energies=0)})
    state = state.model_copy(update={"players": (p0, p1)})
    act = decide(engine_at(state))
    assert act.kind == "attack"


def test_gate_off_keeps_chip_active():
    """board_quality_gate=False：付得起就不撤。"""
    active = two_attack("低伤", hp=110, damage=60, cost=1, retreat=0)
    bench = two_attack("杀招", hp=200, damage=190, cost=1, retreat=1)
    opp = two_attack("靶", hp=150, damage=10, cost=1, retreat=1)
    state = main_state(p0_active_energies=1)
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(3, bench, energies=1),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp, energies=0)})
    state = state.model_copy(update={"players": (p0, p1)})
    params = HeuristicParams(board_quality_gate=False)
    act = decide(engine_at(state), params)
    assert act.kind != "retreat"


def test_setup_prefers_basic_that_heads_a_line_in_hand():
    """高伤基础 vs 低伤基础+手里的一阶 → 放低伤基础。"""
    fat = basic("高伤", hp=110, damage=60)
    baby = basic("幼基", hp=60, damage=10)
    evo = stage1("一阶", "幼基", hp=90, damage=30)
    hand = [inst(10, fat), inst(11, baby), inst(12, evo), inst(13, energy())]
    from test_heuristic_agent import engine_with, setup_state
    act = decide(engine_with(setup_state(hand)))
    assert act == Action(kind="place_active", iid=11)


def test_setup_without_line_still_uses_pokemon_score():
    """手里没有进化关系 → 仍放 pokemon_score 更高的基础。"""
    fat = basic("高伤", hp=110, damage=60)
    weak = basic("弱", hp=40, damage=10)
    hand = [inst(10, weak), inst(11, fat)]
    from test_heuristic_agent import engine_with, setup_state
    act = decide(engine_with(setup_state(hand)))
    assert act == Action(kind="place_active", iid=11)
    assert pokemon_score(inst(11, fat), HeuristicParams()) > pokemon_score(
        inst(10, weak), HeuristicParams())


def test_promote_still_follows_pokemon_score():
    """promote 不改：分高的备战换上。"""
    from test_heuristic_agent import engine_with
    from battlefrontier.engine.state import GameState, PlayerState
    low = in_play(3, basic("弱", hp=40, damage=10))
    high = in_play(4, basic("强", hp=100, damage=50))
    p0 = PlayerState(
        deck=tuple(inst(100 + i, basic("垫")) for i in range(10)),
        bench=(low, high),
    )
    p1 = PlayerState(deck=tuple(inst(300 + i, basic("对手")) for i in range(10)))
    state = GameState(players=(p0, p1), current_player=0, phase="promote")
    act = decide(engine_with(state))
    assert act == Action(kind="promote", bench_index=1)
```

`setup_state` / `engine_with` 今天在 `tests/test_heuristic_agent.py`，没有从 `tests/helpers.py` 导出。测试文件要么从那里导入（上面的写法），要么把那两个函数抄进新文件。导入失败就抄，不要改旧测试的夹具语义。

`test_setup_prefers_basic_that_heads_a_line_in_hand` 在今天的代码上会选 iid 10（高伤），这是预期的红。

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_heuristic_board_gate.py -q`

Expected: `test_retreat_to_bench_ko_when_active_chip_cannot_ko` 与 `test_setup_prefers_basic_that_heads_a_line_in_hand` FAIL。`test_no_retreat_when_active_already_kos`、`test_gate_off_keeps_chip_active`、`test_promote_still_follows_pokemon_score`、`test_setup_without_line_still_uses_pokemon_score` 应当已经 PASS（锁旧行为；前两个要手里没有能量，否则附着排在撤退和斩杀前面，测不到它们）。若 promote 测试因夹具不合法而报错，先修夹具使 `legal_actions` 含 `promote`，不要改 `_pick_promote`。

- [x] **Step 3: Write minimal implementation**

`HeuristicParams` 增加：

```python
board_quality_gate: bool = True
```

`_pick_place`：

```python
def _pick_place(self, view, acts):
    hand = {c.iid: c for c in view.own.hand}
    return min(acts, key=lambda a: self._place_key(hand[a.iid], view.own.hand))


def _line_names(root: str, hand: tuple) -> set[str]:
    names = {root}
    changed = True
    while changed:
        changed = False
        for c in hand:
            if c.card.evolves_from in names and c.card.name not in names:
                names.add(c.card.name)
                changed = True
    return names


def _place_key(self, card: CardInstance, hand: tuple) -> tuple:
    score = pokemon_score(card, self.params)
    line = (
        self.params.board_quality_gate
        and card.card.stage == 0
        and len(_line_names(card.card.name, hand)) > 1
    )
    if not line:
        return (1, 0, -score, card.iid)
    top = max(
        pokemon_score(c, self.params)
        for c in hand
        if c.card.name in _line_names(card.card.name, hand)
    )
    return (0, -top, -score, card.iid)
```

键长固定为 4，避免 `min` 比较不同长度的元组。开关关时第一、二项是常数，次序与今天的 `(-score, iid)` 相同。`_line_names` 只用 `name` / `evolves_from`。

`_pick_retreat`：先算战斗场已付清招式的最高有效伤害是否 ≥ 对手剩余 HP（弱点/抗性沿用 `_attack_table` 的后处理；把备战换算成战斗场时复制 `VisibleGameState`，用 `model_copy`，不写回引擎）。若否，且某个合法 `retreat` 的备战宝可梦已付清招式能斩杀，选伤害最高、bench 下标最小的那个。若是，返回 None。若谁都不能斩杀，调用今天的「付不起才撤」逻辑（把现有函数体留成 `_pick_retreat_powerless`）。`board_quality_gate is False` 时直接走 `_pick_retreat_powerless`。

不要为了让撤退测试变绿去改 `_decide_main` 的大顺序。斩杀仍在撤退之前。

- [x] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_heuristic_board_gate.py tests/test_heuristic_agent.py tests/test_features.py tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/heuristic.py tests/test_heuristic_board_gate.py tests/test_tune_space.py
```

Expected: PASS，ruff 零告警。`test_features.py` 的手算期望一字不改。

- [x] **Step 5: 实验 YAML**

`experiments/t078-gard-zoro.example.yml` 与 `experiments/t077-gard-zoro.example.yml` 同构：`name: t078-gard-zoro`，`games: 100`，`seed_start: 208000`，`mik_moe:678647` × `mik_moe:690359`，两边 heuristic，不写卡名参数。文件头注释写明结构指标和「云端不跑」。

加一条测试：该 YAML 能被实验加载器解析，`games==100`，`seed_start==208000`。仿 `tests/test_heuristic_ability_gate.py` 里对 t077 YAML 的读法（`read_text(encoding="utf-8")`）。

- [x] **Step 6: Commit**

```bash
git add battlefrontier/agent/heuristic.py tests/test_heuristic_board_gate.py tests/test_tune_space.py experiments/t078-gard-zoro.example.yml
git commit -m "task(078): 前场质量门控——斩杀撤退与进化线开局"
```

- [ ] **Step 7: 本机 100 局（有 ptcg-cn.db 的机器；云端跳过并在 STATUS 写明）**

本实现 PR 在云端跳过：无 `ptcg-cn.db`，不跑 `bfsim`。命令留在 `tasks/task 078.md` 与 `STATUS.md`，由父代理在 Diupi-Yun 跑。

先在开关关闭时跑同一 YAML（两边 `params: {board_quality_gate: false}`），记下攻击名 / `attach_energy.target` / `evolve` / `game_over.reason`。再跑默认开。比较规格 §6。失败局必须是 0。胜率写实，不凑 60%。这一步的数字回写 `tasks/task 078.md` 与 `STATUS.md`。不要跑 `experiments/v2-calibration.example.yml`。

---

### Task 2: 079 能量附着目标

**Files:**
- Create: `tests/test_heuristic_energy_target.py`
- Modify: `battlefrontier/agent/heuristic.py`（`energy_target_gate`、`_pick_energy_attach`）
- Modify: `tests/test_tune_space.py`

**Interfaces:**
- Consumes: `_energy_role`、`_energy_symbol` 的语义（077 已有）；`has_hand_ammo_pattern`（D-032-5）
- Produces: `HeuristicParams.energy_target_gate: bool = True`
- Produces: 开关开时，优先「这一张能量使某招从付不起变为付得起、且该招有效伤害最高」的宝可梦

依赖：Task 1 的 `board_quality_gate` 可以已在树上，但本任务的测试不打开那个行为来证明自己。能量测试的局面里不要同时依赖撤退。

- [ ] **Step 1: Write the failing test**

```python
"""task 079：手牌能量优先贴到再贴一张就付清的高伤目标。"""

from helpers import energy, engine_at, in_play, inst, main_state

from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef


def _split_state():
    active_card = CardDef(
        card_id="stub-双招", name="双招", supertype="pokemon", hp=130, stage=0,
        retreat_cost=2,
        attacks=(
            AttackDef(name="小", cost=("无",), damage=20),
            AttackDef(name="大", cost=("无",) * 4, damage=170),
        ),
    )
    bench_card = CardDef(
        card_id="stub-差一张", name="差一张", supertype="pokemon", hp=100, stage=0,
        retreat_cost=1,
        attacks=(AttackDef(name="中", cost=("无", "无"), damage=120),),
    )
    opp = CardDef(
        card_id="stub-靶", name="靶", supertype="pokemon", hp=100, stage=0,
        attacks=(AttackDef(name="撞", cost=("无",), damage=10),), retreat_cost=1,
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active_card, energies=1),
        "bench": (in_play(3, bench_card, energies=1),),
        "hand": (inst(51, energy()),),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp, energies=0)})
    return state.model_copy(update={"players": (p0, p1)})


def _observe(state, params=None):
    engine = engine_at(state)
    agent = HeuristicAgent(params)
    return agent.observe(engine.state.visible_state(0), engine.legal_actions(0))


def test_attach_to_bench_that_becomes_ready_not_active_second_attack():
    """战斗场 1 能招已付清、4 能招还差得远；备战 2 能招已有 1 张 → 贴备战。"""
    act = _observe(_split_state())
    assert act == Action(kind="attach_energy", iid=51, target_iid=3)


def test_gate_off_feeds_active_unpaid_second_attack():
    """energy_target_gate=False → 战斗场还有没付清的招，能量仍给战斗场。"""
    params = HeuristicParams(energy_target_gate=False)
    act = _observe(_split_state(), params)
    assert act == Action(kind="attach_energy", iid=51, target_iid=1)
```

`test_hand_ammo_still_skips_when_active_can_attack` 不经过 `observe` 的整段排序。把 `tests/test_agent_dsl_estimate.py` 里「手牌弹药型主动已能开打 → `_pick_energy_attach` 返回 None」那个测试的卡、文档和 `acts` 原样抄进新文件，断言在 `HeuristicParams()`（开关默认开）下仍然是 None。不要改旧文件里的那个测试。

今天的第一测会把能量给 `target_iid==1`，所以是红。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_heuristic_energy_target.py -q`

Expected: 贴备战的测试 FAIL（实际 `target_iid==1`）。开关关闭的测试在实现前也会 FAIL（字段不存在）或在字段加上、函数未改时 PASS。手牌弹药测试在实现前应 PASS（旧行为）。

- [ ] **Step 3: Write minimal implementation**

```python
energy_target_gate: bool = True
```

`_pick_energy_attach` 在现有「战斗场是手牌弹药且已能打 → return None」之后。`add` 取候选能量卡的 `energy_type`（无色是 `None`，与 077 的 `_energy_role` 一致）。有 `enable` 目标才走新分支：

```python
if self.params.energy_target_gate:
    ranked = []
    active_iid = view.own.active.current.iid if view.own.active else None
    for mon in _in_play(view.own.active, view.own.bench):
        if _mon_energy_role(mon, add) != 0:
            continue
        dmg = self._newly_enabled_damage(view, mon, add)
        on_active = 0 if mon.current.iid == active_iid else 1
        ranked.append(( -dmg, on_active, mon.current.iid, mon))
    if ranked:
        _, _, target_iid, _ = min(ranked)
        targeted = [a for a in acts if a.target_iid == target_iid]
        return min(targeted or acts, key=lambda a: (a.target_iid or 0, a.iid))
```

`_newly_enabled_damage` 对每条招式调用 `_energy_role(当前附着属性, atk.cost, add)`，只保留返回 `"enable"` 的招式（贴上之前付不起、贴上之后付得起）。伤害用 `estimate_attack_damage`，返回 None 时用印面 `atk.damage or 0`。弱点 ×2、抗性 −`RESISTANCE_AMOUNT` 与 `_attack_table` 相同，来源属性用这只宝可梦的 `energy_type`，不用战斗场那只的属性。

没有 `enable` 目标时，函数余下部分保持今天的 `needs_energy` 逻辑，一个字不改语义。

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_heuristic_energy_target.py tests/test_agent_dsl_estimate.py tests/test_heuristic_ability_gate.py tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/heuristic.py tests/test_heuristic_energy_target.py
```

Expected: PASS。077 的附伤门控测试不改断言。

- [ ] **Step 5: Commit**

```bash
git add battlefrontier/agent/heuristic.py tests/test_heuristic_energy_target.py tests/test_tune_space.py
git commit -m "task(079): 能量优先贴到再贴一张就付清的目标"
```

- [ ] **Step 6: 本机 100 局**

复用 `experiments/t078-gard-zoro.example.yml`，默认两开关都开。对照 Task 1 默认开的那次 100 局（不是对照开关全关）。看 `attach_energy` 的 `detail.target` 是否从高费用第二招的宝可梦挪走，以及暗夜王牌 / 血月的 `attack` 事件局触及率。失败 0。不跑矩阵。

### Task 2b: 血月减费（仅当规格 Q4 拍板为「要读」）

默认不执行。Q4 维持「否」时跳过本节，079 即完成。

**Files:**
- Modify: `battlefrontier/agent/heuristic.py`（只在能量/撤退的费用判断里减【无】）
- Test: `tests/test_heuristic_energy_target.py` 追加

- [ ] **Step 1: Write the failing test**

对手奖赏剩余 4（已拿 2）。血月形态的印面费用是 5 个【无】，DSL：

```yaml
- trigger: passive_static
  actions:
    - {action: modify_attack_cost, args: {attack: 血月, value: opponent_taken_prizes}}
```

这只身上已有 3 张无色，备战另一只没有任何能量、印面 1 费。开关开、且 Q4 实现之后：`needs` 判断认为血月已付清，能量不要为了印面剩下的 2 张继续堆在它身上，而应去点亮备战那只 1 费（若那只是 enable）。`energy_target_gate=False` 时仍按印面 5 费，继续喂血月。

不要在测试里把卡命名成「月月熊」。招式名用 `血月` 只因为 DSL 的 `args.attack` 要和 `AttackDef.name` 对齐，卡名用 `stub`。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_heuristic_energy_target.py::test_colorless_reduction_from_visible_prizes -q`

Expected: FAIL（当前按印面 5 费，能量仍给这只）。

- [ ] **Step 3: Implement**

在 Agent 内写纯函数：读该宝可梦文档的 `passive_static` / `modify_attack_cost`，`value` 仅为 `opponent_taken_prizes` 时减免 = `6 - view.opponent.prizes_count`，只从该招式费用的【无】里扣，下限 0。把扣完的费用元组交给现有 `_energy_satisfied` / `_energy_role`。不调用 `GameEngine._effective_attack_cost`。道具来源的减免、`types: all` 不在这刀：文档来源不是持有者本人时保持印面，测试不要覆盖那种卡。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_heuristic_energy_target.py tests/test_heuristic_board_gate.py -q`

Expected: PASS。078 的撤退测试仍用没有减费文档的 stub，行为不变。

- [ ] **Step 5: Commit**

```bash
git commit -m "task(079): 能量判断读取奖赏减免的无色费用"
```

---

### Task 3: 080 可见伤害与复制目标

**Files:**
- Create: `tests/test_heuristic_attack_quality.py`
- Modify: `battlefrontier/agent/dsl_estimate.py`（`_visible_counter`）
- Modify: `battlefrontier/agent/heuristic.py`（`attack_quality_gate`、`_pick_choose` 的复制两段）
- Modify: `tests/test_tune_space.py`

**Interfaces:**
- Consumes: `estimate_attack_damage`、`PendingChoice.pool` / `payload`、`copy_attack` 的两段池名 `own_bench` 与 `anchored_pokemon_attack`
- Produces: `_visible_counter("opponent_discard_basic_energy_count")` 返回对手弃牌区基本能量张数
- Produces: `HeuristicParams.attack_quality_gate: bool = True`，只包复制目标的排序

- [ ] **Step 1: Write the failing test**

计数词（直接打估算器，不经过对局）：

```python
def test_relight_uses_opponent_basic_energy_in_discard():
    """弃牌区 4 张基本能量 → 30× 估算 120，高于另一招印面 90。"""
    from battlefrontier.agent.dsl_estimate import estimate_attack_damage
    from battlefrontier.dsl import parse_card_doc
    doc = parse_card_doc("""
card:
  name_group: 变量手
effects:
  - trigger: on_attack
    attack: 复燃
    actions:
      - {action: damage, selector: opponent_active, count: opponent_discard_basic_energy_count, args: {op: "×", per: 30}}
""")
    # 构造 VisibleGameState：对手 discard 含 4 张 is_basic_energy，
    # 攻击方 active 的 attacks[0] 名为复燃、印面 damage=30。
    est = estimate_attack_damage(view, "复燃", 30, source_card, {"变量手": doc})
    assert est is not None and est.amount == 120 and est.lethal_ok
```

`view` 用 `main_state()` 改 `players[1].discard` 后 `visible_state(0)`。今天这个词返回 None，估算器返回 None，测试为红。

同一局面再加一招印面 90，`HeuristicAgent._pick_attack` 在两招都付得起时选 index 0（复燃，120）而不是 index 1（90）。弃牌区改成 0 张基本能量时选 90。

复制（引擎走到 choice，再问启发式）：

```python
def test_copy_chooser_prefers_ko_donor_over_higher_pokemon_score():
    """供体 A：HP 800、伤害 10（pokemon_score 更高、斩杀不了）。
    供体 B：HP 80、伤害 200，对手 HP 100。
    两只 owner 都是 N。暗夜王牌宣言之后，第一次 choose 是 B 的 iid。
    attack_quality_gate=False 时选 A。
    """
```

夹具结构抄 `tests/test_primitives_t071.py` 的 `test_wp10_copy_bench_attack_owner_filter`：`parse_card_doc` 的 `copy_attack selector=own_bench_attack`，`filters: ["owner_pokemon:N"]`，`e.apply(attack)` 之后 `pending_choice.pool == "own_bench"`。然后：

```python
act = HeuristicAgent(card_effects=effects).observe(
    e.state.visible_state(0), e.legal_actions(0))
assert act.kind == "choose" and act.choices == (b_iid,)
```

第二段：手动 `apply` 选中 B 之后，`pending_choice.pool == "anchored_pokemon_attack"`。给 B 两个招式，index 0 伤害 10，index 1 伤害 200。`observe` 应返回 `choices==(1,)`。开关关闭时返回 `choices==(0,)`（今天的下标 tie-break）。测试开头断言 `pending_choice.payload` 含 B 的 iid；若引擎把供体 iid 放在别的字段，改断言到实际字段，并在启发式里读那个字段。不要在测试失败时改引擎去迁就启发式。

回归：同一只两个招式，60 与 190 都付得起，`_pick_attack` 选 190。只有 60 时选 60，不返回 end_turn。这条在今天就是绿，保持绿。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_heuristic_attack_quality.py -q`

Expected: 复燃估算 FAIL；复制选择在实现前 FAIL（选了高 HP 低伤供体，或第二段选了下标 0）。190 回归 PASS。

- [ ] **Step 3: Write minimal implementation**

`dsl_estimate._visible_counter` 增加：

```python
if word == "opponent_discard_basic_energy_count":
    return sum(1 for c in view.opponent.discard if c.card.is_basic_energy)
```

`_pick_choose` 在现有 cost / 附伤分支之后、通用 `pokemon_score` 之前：

```python
if self.params.attack_quality_gate and pc is not None and pc.pool == "own_bench":
    if self._pending_is_copy_attack(view):
        return min(acts, key=lambda a: self._copy_donor_key(view, a))
if self.params.attack_quality_gate and pc is not None and pc.pool == "anchored_pokemon_attack":
    return min(acts, key=lambda a: self._copy_attack_key(view, a))
```

`_copy_donor_key`：用 `a.choices[0]` 找到备战宝可梦，取其招式里最高有效伤害；能斩杀的排前（键的第一项 0），否则 1；然后 `-damage`，然后 iid。`_copy_attack_key`：`payload[0]`（或 Step 1 断言确认的字段）是供体 iid，`a.choices[0]` 是招式下标，同一套斩杀键。`_pending_is_copy_attack`：用 `doc_for` + `pc.effect_index` 看当前步骤的 `action=="copy_attack"`。读不到文档时不要猜，回落到今天的 `pokemon_score`。

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_heuristic_attack_quality.py tests/test_agent_dsl_estimate.py tests/test_t076_matrix_failures.py tests/test_primitives_t071.py tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/dsl_estimate.py battlefrontier/agent/heuristic.py tests/test_heuristic_attack_quality.py
```

Expected: PASS。`test_primitives_t071.py` 里手写 `apply(choose)` 的复制测试不改，它们不经过启发式。

- [ ] **Step 5: Commit**

```bash
git add battlefrontier/agent/dsl_estimate.py battlefrontier/agent/heuristic.py tests/test_heuristic_attack_quality.py tests/test_tune_space.py
git commit -m "task(080): 复燃计数进估算，复制目标按伤害排序"
```

- [ ] **Step 6: 本机 100 局**

仍是 `experiments/t078-gard-zoro.example.yml`，三个开关默认开。对照 Task 2 的 100 局。记录：`game_over.reason` 分布、沙奈朵胜率、`detail.attack` 为精神幻觉 / 奇迹之力 / 暗夜王牌 / 复燃 / 血月的局数、失败数。按规格 D-078-9 写实。不跑 500，不跑矩阵，不把 \|Δ\| 写成闭环。

---

## 规格覆盖（写计划时自检）

| 规格 | 计划落点 |
|---|---|
| D-078-5 撤退斩杀 / 开局进化线 / promote 不动 | Task 1 三组测试 |
| D-078-3 `pokemon_score` 不动 | Task 1 Step 4 跑 `test_features.py` 且不改期望 |
| D-078-6 能量 enable | Task 2 |
| D-078-4 开关不进 tune | 每个 Task 改 `bool_fields`，不断言 10 维变长 |
| Q4 减费默认不做 | Task 2b 默认跳过 |
| D-078-7 复燃计数 + 复制排序 + 60/190 回归 | Task 3 |
| D-078-8 100 局、事件字段 | 每刀 Step 的本机命令；YAML 在 Task 1 创建 |
| 明确不做：矩阵、JEV、引擎大改、end_turn | Global Constraints；Task 3 回归「只有 60 仍攻击」 |
| Q5 弱点加分 | 无步骤。拍板改为「要」时另写测试，不塞进 Task 1 |
