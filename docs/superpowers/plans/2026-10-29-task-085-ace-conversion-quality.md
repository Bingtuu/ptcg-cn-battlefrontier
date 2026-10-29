# 085 王牌转换质量 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **未拍板。** 规格 `docs/superpowers/specs/2026-10-29-task-085-ace-conversion-quality-design.md` 第 5 节待 Owner 勾选。**本计划在 Task 1 停止。Task 2 起不执行**，除非 Q1–Q10 整包按「本文建议」（主刀 B，`copy_conversion_gate=True`）。任何一行改选，先改规格和本计划，再写测试。

**Goal:** 在不改复制击杀短路的前提下，让非斩杀的能量启用分、撤退、换上和多招 `_pick_attack` 使用一层复制前瞻的伤害，使已付清或再贴一张就付清的复制路径不再被印面 0 伤当成磨血。

**Architecture:** 083 的 `_ko_prize_lookahead` 继续回答「能不能斩杀、复制伤害是多少」。084 Q2=C 继续让 `can_ko` 的复制招式走 `_lethal_attack`。本刀只加 `HeuristicParams.copy_conversion_gate`。开着时，四个非斩杀消费者读同一出口；关着时这四个回到今天。`_one_layer_copy` 增加 `extra_types: tuple[str | None, ...] = ()`，只给「再贴一张」打分。空元组时付清判断仍走 `_energy_satisfied`。基本能量的 `energy_type is None` 表示无色垫，必须放进元组里传，不能用 `None` 充当「不加能量」。

**Tech Stack:** Python 3.12+、pytest、ruff。局级用 `bfsim`（Diupi-Yun / 本机 `ptcg-cn.db`）。

**权威设计：** `docs/superpowers/specs/2026-10-29-task-085-ace-conversion-quality-design.md`。

## Global Constraints

- 零卡名分支。
- 不改 `_lethal_attack` 的返回条件。复制击杀仍先于道具 / 撤退 / 物品 / 支援者 / 竞技场。
- 不改 `_ko_prize_lookahead` 的 `can_ko` / `via` 语义，不改 `_attack_table`，不改 `_copy_donor_key` / `_pick_choose`。
- `pokemon_score` 与 `factor_prize_diff` 不动。`tests/test_features.py` 期望不得改。
- `copy_conversion_gate` 不进 tune 的 10 维。`len(search_space())` 仍是 10。
- 费用继续印面。不读 `modify_attack_cost`。`extra_types` 只模拟多出来的属性列表，不调用 `GameEngine._effective_attack_cost`。
- 不新增 `prize_pressure_gate` / `copy_lethal_policy` / `ABLATION_COPY_NOT_LETHAL`。
- 不实现「落后且都不能斩杀则换更高的非复制身体」。
- 不改 `_decide_main` 的大顺序，不改 `play_stadium` / `end_turn`。
- 不引入 JEV/LLM，不改 MCTS/蒸馏，不改 DSL/引擎，不跑 18000。
- 失败局必须是 0。云端无库，不跑 `bfsim`。
- 局级对照写两列：t080 A78/B22（B prizes 9），083 A72/B28（B prizes 14）。不对照 081 的 A80。
- 不宣称到 real 30.4%。

## File map

| 文件 | 职责 |
|---|---|
| `battlefrontier/agent/heuristic.py` | `copy_conversion_gate`；`_one_layer_copy(..., extra_types=())`；能量 / 撤退 / 换上 / `_pick_attack` 四个消费者。Task 1 不改 |
| `tests/test_heuristic_copy_conversion.py` | 新红测。Task 1 不建 |
| `tests/test_tune_space.py` | 新字段进 `bool_fields`，维数仍 10 |
| `battlefrontier/tune/space.py` | 模块说明里补上这个开关不进 10 维 |
| `tests/test_heuristic_ko_prize_lookahead.py` | 不改断言。复制斩杀先于支援者、印面更高也不撤，都要保持绿 |
| `tasks/task 085.md` / `STATUS.md` | Task 1 只写「待拍板」 |

不改 `tests/test_features.py` 的期望。不改 `tests/test_heuristic_attack_quality.py` 的 chooser 断言。不新建第二套击杀前瞻。

---

### Task 1 — 文档落盘，然后停

**Files:**
- Create: `docs/superpowers/specs/2026-10-29-task-085-ace-conversion-quality-design.md`
- Create: `docs/superpowers/plans/2026-10-29-task-085-ace-conversion-quality.md`
- Create: `tasks/task 085.md`
- Modify: `STATUS.md`（「当前」指向 085 待拍板）

- [x] **Step 1: 写规格、计划、task，STATUS 只声明待拍板**

不写「TDD 已开始」。不改 `heuristic.py`。

- [ ] **Step 2: Owner 勾选 Q1–Q10**

勾选写进规格第 5 节的「拍板」列，并改 task 文档。整包等于「本文建议」才做 Step 3。有改选则先重写 Task 2 起。

- [ ] **Step 3: 整包采纳后再进入 Task 2**

Q2 不是 B，或 Q10 仍是「停在文档」：Task 2 起继续不执行。

---

Task 2–5 **不执行**，直到 Task 1 Step 2 完成且 Q 表等于「本文建议」。下面是该默认包的草稿，不是本分支的授权。

### Task 2 — 红测（仅拍板 = 本文建议）

**Files:**
- Create: `tests/test_heuristic_copy_conversion.py`
- Modify: `tests/test_tune_space.py`（字段不进搜索空间；先写断言，实现前会红）

**Interfaces:**
- Consumes: `HeuristicParams`、`Action`、`tests/helpers.py` 的 `basic` / `energy` / `engine_at` / `in_play` / `inst` / `main_state`
- Produces: 默认 `copy_conversion_gate is True` 时期望的四个行为；`False` 回到今天
- 不产生：`_lethal_attack` 行为变化、`prize_pressure_gate`

现有 `tests/test_heuristic_ko_prize_lookahead.py` 里这两条不要改、不要删：

- `test_copy_ko_attacks_before_supporter`：复制斩杀仍是 `Action(kind="attack", attack_index=0)`
- `test_neither_ko_does_not_retreat_just_because_behind`：两边都不能斩杀时，不因为落后撤到更高印面伤

- [ ] **Step 1: Write the failing tests**

新文件全文如下。夹具卡名是 stub，不是产品分支。

```python
"""task 085：非斩杀路径上的一层复制输出。

不改复制击杀短路。不引入 prize_pressure_gate。
"""

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams
from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

COPY_DOC = parse_card_doc("""
card:
  name_group: 复制手
effects:
  - trigger: on_attack
    attack: 复制
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
FX = {"复制手": COPY_DOC, "双招复制": COPY_DOC, "测试支援者": SUPPORTER_DOC}


def _observe(state, params=None, card_effects=FX):
    engine = engine_at(state)
    engine.card_effects = card_effects
    agent = HeuristicAgent(params, card_effects=card_effects)
    return agent.observe(engine.state.visible_state(0), engine.legal_actions(0))


def _donor() -> CardDef:
    return CardDef(
        card_id="stub-供体", name="供体", supertype="pokemon",
        hp=100, stage=0, retreat_cost=0, owner="N",
        attacks=(AttackDef(name="打击", cost=(), damage=200),),
    )


def _copier(*, cost: tuple[str, ...] = ("无",)) -> CardDef:
    return CardDef(
        card_id="stub-复制手", name="复制手", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="复制", cost=cost, damage=None),),
    )


def _printed(name: str, *, hp: int, damage: int, cost: tuple[str, ...] = ("无",)) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="打击", cost=cost, damage=damage),),
    )


def test_copy_ko_still_attacks_before_supporter_with_conversion_gate():
    """084 Q2=C：转换开关默认开，也不推迟复制斩杀。"""
    supporter = CardDef(
        card_id="stub-测试支援者", name="测试支援者", supertype="trainer",
        trainer_subtype="支援者",
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (inst(61, supporter),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=100, damage=10), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    act = _observe(state, HeuristicParams())
    assert act == Action(kind="attack", attack_index=0)


def test_retreat_onto_higher_copy_when_neither_kos():
    """都不能斩杀。备战复制 200 > 战斗场印面 60 → 撤。关开关则不撤。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _printed("芯片", hp=110, damage=60), energies=1),
        "bench": (
            in_play(3, _copier(), energies=1),
            in_play(70, _donor(), energies=0),
        ),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="retreat", bench_index=0)
    off = HeuristicParams(copy_conversion_gate=False)
    act_off = _observe(state, off)
    assert act_off.kind == "attack"
    assert act_off != Action(kind="retreat", bench_index=0)


def test_active_copy_ko_still_refuses_retreat():
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=100), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="attack", attack_index=0)


def _unpaid_donor() -> CardDef:
    """印面 200，但两费未付。pokemon_score 高；自己的前瞻伤害是 0。复制仍可读这 200。"""
    return CardDef(
        card_id="stub-未付供体", name="未付供体", supertype="pokemon",
        hp=180, stage=0, retreat_cost=0, owner="N",
        attacks=(AttackDef(name="打击", cost=("无", "无"), damage=200),),
    )


def test_promote_non_ko_prefers_copy_over_higher_score():
    """供体分更高，但自己没付清。复制前瞻 200，对手 400 血，两边都不斩杀 → 换上复制。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (
            in_play(3, _copier(), energies=1),
            in_play(70, _unpaid_donor(), energies=0),
        ),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1), "phase": "promote"})
    assert _observe(state) == Action(kind="promote", bench_index=0)
    off = HeuristicParams(copy_conversion_gate=False)
    assert _observe(state, off) == Action(kind="promote", bench_index=1)


def test_promote_without_copy_candidate_keeps_score_order():
    """没有复制候选：高分墙仍优先于低分芯片。"""
    wall = _printed("墙", hp=250, damage=10)
    chip = _printed("芯片", hp=80, damage=20)
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (in_play(3, chip, energies=1), in_play(4, wall, energies=1)),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1), "phase": "promote"})
    assert _observe(state) == Action(kind="promote", bench_index=1)


def test_energy_enables_copy_over_smaller_printed_attack():
    """复制差一张，启用后前瞻 200；印面差一张只有 40。贴复制身体。"""
    printed = _printed("小招", hp=100, damage=40, cost=("无", "无"))
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _printed("已付清", hp=90, damage=30), energies=1),
        "bench": (
            in_play(3, printed, energies=1),
            in_play(4, _copier(cost=("无", "无")), energies=1),
            in_play(70, _donor(), energies=0),
        ),
        "hand": (inst(51, energy()),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="attach_energy", iid=51, target_iid=4)
    off = HeuristicParams(copy_conversion_gate=False)
    assert _observe(state, off) == Action(kind="attach_energy", iid=51, target_iid=3)


def test_pick_attack_uses_copy_damage_when_not_lethal():
    """两招都付清、都斩杀不了：复制 200 高于印面 50。关开关选印面。"""
    body = CardDef(
        card_id="stub-双招复制", name="双招复制", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0,
        attacks=(
            AttackDef(name="芯片", cost=("无",), damage=50),
            AttackDef(name="复制", cost=("无",), damage=None),
        ),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, body, energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="attack", attack_index=1)
    off = HeuristicParams(copy_conversion_gate=False)
    assert _observe(state, off) == Action(kind="attack", attack_index=0)


def test_single_copy_attack_is_unchanged_when_it_does_not_ko():
    """只有一条复制招式、且斩杀不了：两个开关都打出 attack_index=0。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="attack", attack_index=0)
    off = HeuristicParams(copy_conversion_gate=False)
    assert _observe(state, off) == Action(kind="attack", attack_index=0)


def test_lookahead_gate_off_hides_copy_from_conversion():
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _printed("芯片", hp=110, damage=60), energies=1),
        "bench": (
            in_play(3, _copier(), energies=1),
            in_play(70, _donor(), energies=0),
        ),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    params = HeuristicParams(ko_prize_lookahead_gate=False, copy_conversion_gate=True)
    act = _observe(state, params)
    assert act.kind == "attack"
    assert act != Action(kind="retreat", bench_index=0)
```

`tests/test_tune_space.py` 的 `bool_fields` 加上 `"copy_conversion_gate"`，并断言 `HeuristicParams().copy_conversion_gate is True`。`len(search_space()) == 10` 保持。

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_heuristic_copy_conversion.py tests/test_tune_space.py -q
```

预期：`copy_conversion_gate` 不存在，或默认行为仍按印面分（撤退测试得到 `attack`，能量测试贴到 iid 3，双招测试 `attack_index=0`）。

- [ ] **Step 3: Commit the red tests**

```bash
git add tests/test_heuristic_copy_conversion.py tests/test_tune_space.py
git commit -m "test(085): copy conversion on non-lethal choices"
```

---

### Task 3 — 最小实现（仅拍板 = 本文建议）

**Files:**
- Modify: `battlefrontier/agent/heuristic.py`（`HeuristicParams`、`_one_layer_copy`、`_newly_enabled_damage`、`_pick_retreat`、`_pick_promote`、`_pick_attack`）
- Modify: `battlefrontier/tune/space.py`（说明文字补开关名）
- Modify: `tests/test_tune_space.py`（若 Step 2 已改完则这里不再改断言）

**Interfaces:**
- Consumes: `_ko_prize_lookahead(...).via` / `.best_damage` / `.can_ko` / `.attack_index`；`_one_layer_copy`；`_cost_satisfied`；`_energy_role`
- Produces: `HeuristicParams.copy_conversion_gate: bool = True`
- 不产生：`_lethal_attack` 的新分支、`prize_pressure_gate`、`pokemon_score` 公式变化

- [ ] **Step 1: 字段**

在 `ko_prize_lookahead_gate` 旁边：

```python
# 非斩杀路径是否采用一层复制的前瞻伤害（task 085）。
# 不改变 _lethal_attack。不进 tune。关 = 能量/撤退/换上/_pick_attack 回到印面。
copy_conversion_gate: bool = True
```

- [ ] **Step 2: `_one_layer_copy` 的可选 extra_types**

签名改为：

```python
def _one_layer_copy(
    self, view: VisibleGameState, index: int, *,
    extra_types: tuple[str | None, ...] = (),
) -> tuple[int, bool] | None:
```

付清判断换成：

```python
def _copy_cost_paid(
    self, mon: InPlayPokemon, cost: tuple[str, ...],
    extra_types: tuple[str | None, ...],
) -> bool:
    if not extra_types:
        return _energy_satisfied(mon.attached_energy, cost)
    types = [e.card.energy_type for e in mon.attached_energy]
    return _cost_satisfied([*types, *extra_types], cost)
```

空元组必须仍调用 `_energy_satisfied`，今天的斩杀路径不改口径。非空时只把这些属性并进费用检查，不写回视图。`None` 是无色垫（`energy()` 的 `energy_type`），不是「不加」。供体、filter、一层、不递归，全部保持。

- [ ] **Step 3: 四个消费者**

`_newly_enabled_damage`：对 `_energy_role == "enable"` 的招式，若 `self.params.copy_conversion_gate`，调用

```python
self._one_layer_copy(scoring, index, extra_types=(add,))
```

`add` 来自手牌能量的 `energy_type`，可以是 `None`。返回不是 None 就用该伤害；否则保持现在的估算 / `atk.damage or 0`。`scoring` 仍是 `_view_as_active(view, mon)`。备战被看成战斗场时，同 iid 已在 `_one_layer_copy` 里从供体中排除。

`_pick_retreat`：在「没有人 `can_ko`」且即将调用 `_pick_retreat_powerless` 之前，若 `copy_conversion_gate`：

```python
active_dmg = self._ko_prize_lookahead(view).best_damage or 0
better: list[tuple[int, Action]] = []
for act in acts:
    look = self._ko_prize_lookahead(view, mon=view.own.bench[act.bench_index])
    if look.via == "copy" and (look.best_damage or 0) > active_dmg:
        better.append((look.best_damage or 0, act))
if better:
    return min(better, key=lambda item: (-item[0], item[1].bench_index))[1]
```

战斗场 `can_ko` 时函数开头已经 `return None`，不要改那段。

`_pick_promote`：`ko_prize_lookahead_gate` 关时仍只 `score_key`。转换关时仍是现有 `ko_key`（击杀优先，然后分数）。转换开且存在 `via=="copy"` 且 `best_damage>0` 的候选时：

```python
def conv_key(act: Action) -> tuple:
    look = looks[act.bench_index]
    if look.can_ko:
        return (0, *score_key(act))
    return (1, -(look.best_damage or 0), *score_key(act))
```

击杀之间仍比 `pokemon_score`，不比伤害。没有复制候选时不要走 `conv_key`（印面换上顺序保持）。

`_pick_attack`：在 deck-low 过滤之后，若转换开且总闸开：

```python
look = self._ko_prize_lookahead(view)

def rank(act: Action) -> tuple[int, int]:
    damage = table[act.attack_index][0]
    if (
        look.via == "copy"
        and look.attack_index == act.attack_index
        and look.best_damage is not None
    ):
        damage = look.best_damage
    return (damage, -act.attack_index)

return max(candidates, key=rank)
```

这发生在 `_decide_main` 的后段。斩杀已经在前面返回过，这里不要再提前攻击。

- [ ] **Step 4: Run tests — expect PASS；ruff clean**

```bash
python -m pytest tests/test_heuristic_copy_conversion.py tests/test_heuristic_ko_prize_lookahead.py tests/test_heuristic_energy_target.py tests/test_heuristic_board_gate.py tests/test_heuristic_attack_quality.py tests/test_heuristic_agent.py tests/test_features.py tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/heuristic.py battlefrontier/tune/space.py tests/test_heuristic_copy_conversion.py tests/test_tune_space.py
```

`test_copy_ko_attacks_before_supporter` 与 `test_neither_ko_does_not_retreat_just_because_behind` 必须仍绿，且测试源文件没有为了迁就实现而改断言。

- [ ] **Step 5: Commit**

```bash
git add battlefrontier/agent/heuristic.py battlefrontier/tune/space.py tests/test_heuristic_copy_conversion.py tests/test_tune_space.py
git commit -m "task(085): score paid copy damage outside the lethal short-circuit"
```

---

### Task 4 — 一百局（Diupi-Yun；云端跳过）

种子 `208000..208099`。失败必须 0。不改 `experiments/t078-gard-zoro.example.yml` 的 `games`。

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t085-gard-zoro.db
bfsim report <id> --results results/t085-gard-zoro.db --decisions
```

表内写：A/B 胜率、prizes、deck_out、no_pokemon、暗夜王牌次数与触及局、失败数、相对 t080 的翻转。旁边列 t080（A78/B22，B prizes 9）和 083（A72/B28，B prizes 14）。

方向相对 A72 读。不预设必须低于 72。触及后胜率若从事件里数得出来，对照 STATUS 行扫描的沙奈朵格 23%（深挖 357 局里 83 胜）。数不出来就写「报告无此列」，不新做报告器。

不宣称 30.4%。不跑 18000。

回写 `tasks/task 085.md` 与 `STATUS.md`。一百局方向反了：写实，不在同一 PR 里改公式或重开 081。

---

### Task 5 — 行诊断（Q6 默认：必跑、不设过线；云端跳过）

仓库里没有行扫描脚本。诊断用四份与 `experiments/t078-gard-zoro.example.yml` 同构的单格 YAML，`games: 100`，`seed_start: 208000`，两边 `type: heuristic`。N索固定为 B，`deck_id: "mik_moe:690359"`。A 侧 deck_id 抄 `config/target-pool.v2.yml`（STATUS 短名 → 池内全名）：

| STATUS 短名 | archetype | deck_id |
|---|---|---|
| 沙奈朵 | 沙奈朵 | `mik_moe:678647` |
| 多龙 | 多龙巴鲁托 | `mik_moe:677868` |
| 黑夜魔灵 | 多龙巴鲁托 黑夜魔灵 | `mik_moe:676344` |
| 玛俐 | 玛俐的长毛巨魔 雪妖女 | `mik_moe:687339` |

沙奈朵这一份不必新建：Task 4 的 `experiments/t078-gard-zoro.example.yml` 已是该对、该种子、100 局。另外三份放在 `experiments/t085-nzoro-row/`，例如：

```yaml
# task 085 行诊断。100 局，不替代正式矩阵 500。
name: t085-nzoro-pult
games: 100
seed_start: 208000
decks:
  a: {source: db, deck_id: "mik_moe:677868"}
  b: {source: db, deck_id: "mik_moe:690359"}
agents:
  a: {type: heuristic}
  b: {type: heuristic}
```

黑夜魔灵文件用 `mik_moe:676344`，玛俐用 `mik_moe:687339`，`name` 改成 `t085-nzoro-dusk` / `t085-nzoro-grim`。各跑：

```bash
bfsim run experiments/t085-nzoro-row/t085-nzoro-pult.example.yml --workers 8 --results results/t085-nzoro-pult.db
bfsim report <id> --results results/t085-nzoro-pult.db --decisions
```

每格记下 A/B 胜率、失败数、B 的 prizes / deck_out、暗夜王牌次数与触及局。触及后胜率沿 STATUS：打出该招式的局数当中 B 的胜局占比。这 100 局不要写成正式矩阵 Δ（沙奈朵 −49.6 等）的替代数。同格 500 不在本任务里跑。

整行不动不否决 Task 4 的方向记录，也不构成加码理由。四格没回写则 task 不标收口。

---

### Task 6 — 实现 PR 自检（仅 Task 3 之后）

- [ ] 无 `prize_pressure_gate`
- [ ] 无 `copy_lethal_policy`
- [ ] 无 `ABLATION_COPY_NOT_LETHAL`
- [ ] 无卡名分支
- [ ] `_lethal_attack` 在复制能斩杀时仍返回攻击（支援者仍被短路跳过）
- [ ] `tests/test_features.py` 未改期望
- [ ] tune `len(search_space()) == 10`
- [ ] 未读 `modify_attack_cost`
- [ ] `pokemon_score` 函数体无 diff
- [ ] `_decide_main` 的 kind 顺序无 diff

## 与 083 / 084 计划的关系

| 计划 | 关系 |
|---|---|
| `docs/superpowers/plans/2026-10-29-task-083-shared-ko-prize-lookahead.md` | 已执行并合入 PR #12。本计划不重做 F1/F3 |
| `docs/superpowers/plans/2026-10-29-task-084-copy-lethal-short-circuit.md` | Q2=C 已收口。本计划不执行它的 Task 2–5 |
| `docs/superpowers/plans/2026-10-29-task-081-prize-pressure.md` | 继续不执行 |
