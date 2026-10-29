# 082 复制招式击杀前瞻 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **待 Owner 拍板。** 拍板前不执行。Q1–Q9 以 `docs/superpowers/specs/2026-10-29-task-082-copy-lethal-design.md` 拍板后的值为准。下文按「本文建议」起草：100 局对照是 081 合入后的同种子，不是当前 main 的 A78。不要在本计划里实现 `prize_pressure_gate`。

**Goal:** 已付清的 `copy_attack` 按一层供体前瞻参与击杀判定，使暗夜王牌这类印面 0 伤的复制招式在能击杀拿奖时走现有的击杀优先，并且不因此被 078 的撤退换下去。

**Architecture:** 只增加 `copy_lethal_gate`。前瞻写进 `_lethal_attack` 与 `_max_paid_ko_damage`，不写进 `_attack_table`。`pokemon_score` 与 `factor_prize_diff` 不动。不改 080 的 chooser。不改引擎、不改 DSL。

**Tech Stack:** Python 3.12+、`tests/helpers.py`、pytest、ruff。局级验收用 `bfsim`，需要本机 `ptcg-cn.db`。

**权威设计：** `docs/superpowers/specs/2026-10-29-task-082-copy-lethal-design.md`。

## Global Constraints

- 零卡名分支。`owner` 与 DSL `filters` 经 `matches_in_play`。未知 filter 的 `DslError` 不猜，该招式维持印面。
- `pokemon_score` 与 `factor_prize_diff` 不动。`tests/test_features.py` 期望不得改。
- `copy_lethal_gate` 不进 tune 的 10 维。`bool_fields` 包含它，`len(search_space())` 仍是 10。
- 费用继续用印面 `_energy_satisfied`。不读 `modify_attack_cost`，不调用 `GameEngine._effective_attack_cost`。
- 不改 `_pick_energy_attach`、`_place_key`、`_copy_donor_key`、`_pick_choose`、`_attack_table`、`_pick_attack` 的非击杀排序、`play_stadium` / `end_turn` 的位置。
- 不新增 `prize_pressure_gate`，不实现 `_prize_behind`。081 已经在树上时，可以读它，不要在本任务里声明这个字段。
- 复制前瞻只一层、只 `selector=own_bench_attack`。供体不用自己付费。不递归嵌套 `copy_attack`。
- 不引入 JEV/LLM，不改 MCTS/蒸馏，不改 DSL/引擎，不跑 18000。
- 失败局必须是 0。云端无库，不跑 `bfsim`。
- tie-break 用下标升序，不消费随机源。
- 局级验收按 Q1 的建议：等 081 合入并回写 100 局。不要把两次胜率合成一条带。

---

### Task 1: 复制招式击杀前瞻

**Files:**
- Create: `tests/test_heuristic_copy_lethal.py`
- Modify: `battlefrontier/agent/heuristic.py`（`copy_lethal_gate`、`_lethal_attack`、`_max_paid_ko_damage`）
- Modify: `tests/test_tune_space.py`（`bool_fields` 加上 `copy_lethal_gate`）

**Interfaces:**
- Consumes: `doc_for`、`find_attack_effect`、`flatten_steps`、`matches_in_play`、`_copied_strike`、`_energy_satisfied`
- Produces: `HeuristicParams.copy_lethal_gate: bool = True`
- Produces: 已付清、`selector=own_bench_attack` 的复制招式，其击杀判定与「战斗场最高有效伤害」等于合法供体的一层 `_copied_strike`
- 不产生：`_attack_table` 的改动、`_pick_choose` 的改动、`dsl_estimate.py` 的改动、`prize_pressure_gate`

- [ ] **Step 1: Write the failing test**

`tests/test_heuristic_copy_lethal.py`：

```python
"""task 082：复制招式击杀前瞻。不改攻击表，不改 080 的 chooser。"""

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


def _base(*, donor, decoy=None, opp_hp: int, hand=()):
    state = main_state()
    bench = [in_play(70, donor, energies=0)]
    if decoy is not None:
        bench.append(in_play(71, decoy, energies=0))
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": tuple(bench),
        "hand": hand,
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=opp_hp, damage=10), energies=0),
    })
    return state.model_copy(update={"players": (p0, p1)})


def test_copy_ko_attacks_before_supporter():
    """供体 owner=N、印面 200、自己 0 能量。对手 HP 100。手牌只有支援者。

    今天攻击表是 0，先打支援者。前瞻后这一击能击杀，observe 返回 attack。
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
    """供体费用为空，自己站上场也能击杀。今天 078 会撤退。前瞻后战斗场已能击杀，不撤。"""
    donor = _mon("供体", owner="N", hp=100, damage=200, cost=())
    state = _base(donor=donor, opp_hp=100, hand=())
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_owner_filter_ignores_non_matching_ko():
    """N 供体只有 10 伤，打不满 HP 100。非 N 的 400 伤不进池。仍先打支援者。"""
    donor = _mon("供体", owner="N", hp=100, damage=10, cost=())
    decoy = _mon("路人", owner="别人", hp=100, damage=400, cost=())
    state = _base(donor=donor, decoy=decoy, opp_hp=100, hand=(inst(61, _supporter()),))
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
```

`test_copy_ko_attacks_before_supporter` 今天失败：供体两费且 0 能量，备战击杀分支不触发，攻击表是 0，实际 `play_trainer`。`test_copy_ko_does_not_retreat_onto_bench_that_also_kos` 今天失败：供体费用为空、200≥100，078 实际 `retreat`。过滤测试与无文档测试今天 PASS，实现后保持。`test_copy_lethal_gate_off_plays_supporter` 在字段不存在时是 `TypeError`。

`attack_quality` 的 chooser 测试不改断言。本文件不要再测供体排序。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_heuristic_copy_lethal.py -q`

Expected: `test_copy_ko_attacks_before_supporter` FAIL（`play_trainer`）。`test_copy_ko_does_not_retreat_onto_bench_that_also_kos` FAIL（`retreat`）。过滤测试与无文档测试 PASS。

- [ ] **Step 3: Write minimal implementation**

```python
# 复制招式击杀前瞻（task 082，D-082-4/5）。False = 复制招式在击杀/撤退里仍按印面。
# 不进 tune。不改 _attack_table，因此不改 _pick_attack 的非击杀排序。
copy_lethal_gate: bool = True
```

前瞻只在 `copy_lethal_gate` 且 `self.card_effects is not None` 时运行。对战斗场每个已付清印面费用的招式：`doc_for` + `find_attack_effect`，`flatten_steps` 里找 `action=="copy_attack"` 且 `selector=="own_bench_attack"` 的节点。多个节点取先遇到的一个。没有则这一招返回 None。

`find_attack_effect` 从 `battlefrontier.agent.dsl_estimate` 导入。`matches_in_play`、`flatten_steps`、`doc_for`、`DslError` 已在 `heuristic.py` 导入。

供体 = `[m for m in view.own.bench if matches_in_play(m, tuple(node.filters))]`。`matches_in_play` 抛 `DslError` 时这一招返回 None。对每个供体的每个招式下标调用已有 `_copied_strike`，不要再乘一次弱点。有 `ko` 为真的结果时，伤害取这些里的最大，击杀为真；否则伤害取全部最大，击杀为假。

`_lethal_attack`：表内真实伤害已经 ≥ 剩余 HP 的招式保持今天的行为。某下标的前瞻击杀为真时，把该下标算进击杀列表，排序键用前瞻伤害。前瞻返回 None 的下标不动。

`_max_paid_ko_damage`：印面循环得到 `best` 之后，若前瞻伤害不是 None，`best = max(best, looked)`（`best` 为 None 时用前瞻伤害）。没有印面伤害也没有前瞻时仍返回 None。这个并入让 078 的「战斗场已能击杀则不撤」看得见复制。若 081 的高低伤比较也读这个函数，它会一并看见复制伤害；本任务仍然不去写落后判定。

不要修改 `_attack_table`。不要修改 `_pick_choose`。不要在 `estimate_attack_damage` 里给 `copy_attack` 编一个伤害。

- [ ] **Step 4: Run test to verify it passes**

`bool_fields` 加上 `"copy_lethal_gate"`。若 081 已合入，集合里同时有 `prize_pressure_gate`。`len(search_space())` 仍是 10。

Run:

```bash
python -m pytest tests/test_heuristic_copy_lethal.py tests/test_heuristic_attack_quality.py tests/test_heuristic_board_gate.py tests/test_agent_dsl_estimate.py tests/test_tune_space.py tests/test_features.py -q
python -m ruff check battlefrontier/agent/heuristic.py tests/test_heuristic_copy_lethal.py tests/test_tune_space.py
```

081 已在树上时，把 `tests/test_heuristic_prize_pressure.py` 加进同一条 pytest。Expected: PASS。080 的 chooser 断言不改。078 的击杀撤退不改。

- [ ] **Step 5: Commit**

```bash
git add battlefrontier/agent/heuristic.py tests/test_heuristic_copy_lethal.py tests/test_tune_space.py
git commit -m "task(082): 复制招式按一层供体前瞻参与击杀"
```

---

### Task 2: 与 081 叠放时的回归（仅当 `prize_pressure_gate` 已在树上）

081 还没有合入：跳过本节。不要为了跑这条去添加 `prize_pressure_gate`。

- [ ] **Step 1: Write the failing test**

追加到 `tests/test_heuristic_copy_lethal.py`：

```python
def test_behind_does_not_retreat_off_higher_copy_chip():
    """081 已在时：复制前瞻 170，备战已付清 120，对手 HP 300，都打不倒，且落后。

    两开关都开：战斗场的复制更高，不撤。
    只关 copy_lethal_gate：复制按 0，落后时撤到 120。
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

供体费用 `("无",)` 且 0 能量，印面未付清，`_max_paid_ko_damage` 不计它。备战下标 1 是 120。关 `copy_lethal_gate` 时期望撤到下标 1，这依赖 081 的落后换人，不是本任务新写的规则。

今天若 081 已合入而前瞻还没有：默认路径是 `retreat`，断言 `attack` 为红。

- [ ] **Step 2: Run test to verify it fails, then passes after Task 1 的前瞻已在**

Run: `python -m pytest tests/test_heuristic_copy_lethal.py::test_behind_does_not_retreat_off_higher_copy_chip -q`

若 Task 1 已完成，这条应当已经 PASS（前瞻并进了 `_max_paid_ko_damage`）。若 FAIL，不要新写落后逻辑，只检查前瞻伤害有没有进 `_max_paid_ko_damage`。

- [ ] **Step 3: Commit**

```bash
git add tests/test_heuristic_copy_lethal.py
git commit -m "test(082): 落后抢奖已在时，更高的复制不撤下去"
```

---

### Task 3: 本机 100 局（Diupi-Yun；云端跳过）

**建议等 081 合入，并且 `tasks/task 081.md` 已回写同种子 100 局。** Q1 若改成对照 main，仍跑下面的命令，结果节写明「081 未合入，对照是 A78/B22，不是两刀叠完」。

**Files:**
- Modify: `tasks/task 082.md`、`STATUS.md`
- 不修改 `experiments/t078-gard-zoro.example.yml`

- [ ] **Step 1: 确认单测已绿，并确认对照是哪一次**

云端不跑 `bfsim`。有库的机器上，先读 081 的结果节。没有 081 的 100 局数字，就停在单测，不要用 A78 填进「082 有效」。

- [ ] **Step 2: 默认开关开**

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t082-gard-zoro.db
bfsim report <id> --results results/t082-gard-zoro.db --decisions
```

对照 **081 的** `results/t081-gard-zoro.db`（同一种子 `208000..208099`），不是 080 的 A78/B22。记下 A/B 胜率、A 的 prizes / deck_out / no_pokemon、暗夜王牌触及局、触及局中的 B 胜场、失败数。失败必须是 0。

有效带（相对 081 那一次，D-082-7）：

- 081 的 A 胜率仍高于 70%：这次进入 **60–70%** 算方向有效。
- 081 已在 60–70%：这次的 A 胜率不得推出这带。
- 到不了也写实。不写「从 78% 一次走到 70%」。不写「|Δ| 闭环」。不跑 18000。

- [ ] **Step 3: Commit**

```bash
git add tasks/task\ 082.md STATUS.md
git commit -m "docs(082): Diupi-Yun 100局验收回写"
```

---

### Task 4: 短行（仅当 081 已经跑过短行）

不把短行升成 082 的有效带。081 的 Q4 没批准、或 YAML 还不存在：跳过。

复用 `experiments/t081-nzoro-row/`，结果库换 `results/t082-nzoro-*.db`。对照是 081 的短行。沙奈朵 / 多龙巴鲁托 / 玛俐的 N索胜率更差则停手写实。猛雷鼓 / 电电虫只记 deck_out。云端跳过。不跑 18000。

- [ ] **Step 1: 本机运行并回写**

```bash
bfsim run experiments/t081-nzoro-row/t081-nzoro-pult.example.yml --workers 8 --results results/t082-nzoro-pult.db
bfsim report <id> --results results/t082-nzoro-pult.db
```

其余四份换路径。失败局必须是 0。

- [ ] **Step 2: Commit**

```bash
git add tasks/task\ 082.md STATUS.md
git commit -m "docs(082): N索短行对照 081 回写"
```

不要提交 `results/*.db`。不要在本任务新建第二套短行 YAML。

---

## 规格覆盖

| 规格 | 计划落点 |
|---|---|
| D-082-5 复制击杀先于支援者 | Task 1 `test_copy_ko_attacks_before_supporter` |
| D-082-5 复制能击杀则不撤到备战 | `test_copy_ko_does_not_retreat_onto_bench_that_also_kos` |
| D-082-5 过滤器、无文档不猜 | Task 1 两条锁测试 |
| D-082-5 不改 080 chooser / 不改攻击表 | Task 1 Step 4 跑 `test_heuristic_attack_quality.py` |
| D-082-3 公式冻结 | Task 1 Step 4 跑 `test_features.py` |
| D-082-4 不进 tune | `bool_fields` |
| 不实现 081 | 无 `prize_pressure_gate` 字段声明。Task 2 仅在字段已存在时跑 |
| D-082-6 对照 081 的 100 局 | Task 3 |
| D-082-7 不与 78% 合成一条带 | Task 3 Step 2 |
| Q5 血月 / Q7 end_turn / Q8 复制选人 | 无步骤 |
| Q9 短行 | Task 4，仅 081 已跑过 |
