"""task 077：启发式特性质量门控（D-077-1~4）。

交易类 = 弃少量手牌再抽（不按卡名）。附伤类 = 弃牌区附能并放伤害指示物。
无 DSL 文档的特性保持「会用」；门控关闭时回到 min(iid)。
"""

from pathlib import Path

import yaml
from helpers import basic, energy, in_play, inst

from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams
from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    GameState,
    InPlayPokemon,
    PendingChoice,
    PlayerState,
)

CYCLE_DOC = parse_card_doc("""
card:
  name_group: 弃抽手
effects:
  - trigger: ability_manual
    limit: once_per_turn
    cost:
      - {action: discard, selector: own_hand, choose: 1}
    actions:
      - {action: draw, count: 2}
""")

REFRESH_DOC = parse_card_doc("""
card:
  name_group: 整手刷新
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: discard, selector: own_hand, count: all}
      - {action: draw, count: 6}
""")

ATTACH_DOC = parse_card_doc("""
card:
  name_group: 附伤手
effects:
  - trigger: ability_manual
    limit: unlimited
    actions:
      - action: attach_energy
        selector: own_discard
        filters: [basic_energy, energy_超]
        choose: 1
        destination: attach
        args: {target_filters: [pokemon_超, would_survive_20], damage_counters: 2}
""")

DRAW_DOC = parse_card_doc("""
card:
  name_group: 抽牌手
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: draw, count: 1}
""")

ROOT = Path(__file__).parent.parent


def mon(name: str, *, energy_type: str = "无", cost: tuple[str, ...] = ("无",),
        hp: int = 200) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, energy_type=energy_type,
        attacks=(AttackDef(name="打击", cost=cost, damage=30),),
        retreat_cost=1,
    )


def psychic_energy() -> CardDef:
    return CardDef(
        card_id="stub-超能量", name="基本超能量", supertype="energy",
        energy_type="超", is_basic_energy=True,
    )


def placed(iid: int, card: CardDef, energies: int = 0, *, typed: CardDef | None = None,
           ) -> InPlayPokemon:
    fuel = typed if typed is not None else energy()
    return InPlayPokemon(
        stack=(inst(iid, card),),
        attached_energy=tuple(inst(7000 + iid * 10 + j, fuel) for j in range(energies)),
    )


def board(active: InPlayPokemon, hand: list, *, deck_n: int, bench: tuple = (),
          discard: tuple = (), effects: dict) -> GameEngine:
    p0 = PlayerState(
        deck=tuple(inst(1000 + i, basic("垫牌")) for i in range(deck_n)),
        hand=tuple(hand),
        discard=discard,
        prizes=tuple(inst(200 + i, basic("奖")) for i in range(6)),
        active=active,
        bench=bench,
    )
    p1 = PlayerState(
        deck=tuple(inst(3000 + i, basic("对手垫")) for i in range(10)),
        prizes=tuple(inst(400 + i, basic("对手奖")) for i in range(6)),
        active=in_play(2, basic("对手")),
    )
    state = GameState(
        players=(p0, p1), turn=4, current_player=0, phase="main", first_player=0,
    )
    engine = GameEngine(RandomSource(0), card_effects=effects)
    engine.state = state
    return engine


def decide(engine: GameEngine, params: HeuristicParams | None = None) -> Action:
    agent = HeuristicAgent(params, card_effects=engine.card_effects)
    return agent.observe(engine.state.visible_state(0), engine.legal_actions(0))


def ability_iids(engine: GameEngine) -> set[int]:
    return {a.iid for a in engine.legal_actions(0) if a.kind == "use_ability"}


def fodder_hand(n_pokemon: int = 2) -> list:
    """n 只宝可梦 + 1 张基本能量（垫牌）。"""
    cards = [inst(50 + i, basic(f"手牌{i}")) for i in range(n_pokemon)]
    cards.append(inst(80, energy()))
    return cards


# ── 交易类弃抽 ───────────────────────────────────────────

def test_cycle_refused_when_deck_nearly_empty():
    """牌库将尽（≤ 默认地板 12）拒交易类，尽管手牌里有能量垫牌。"""
    engine = board(
        placed(1, mon("弃抽手"), energies=1),
        fodder_hand(),
        deck_n=12,
        effects={"弃抽手": CYCLE_DOC},
    )
    assert 1 in ability_iids(engine)
    assert decide(engine).kind == "attack"


def test_cycle_refused_when_hand_has_no_fodder():
    """手牌差：只有宝可梦、没有能量垫牌 → 拒交易类（牌库很厚也不刷）。"""
    hand = [inst(50 + i, basic(f"手牌{i}")) for i in range(3)]
    engine = board(
        placed(1, mon("弃抽手"), energies=1),
        hand,
        deck_n=40,
        effects={"弃抽手": CYCLE_DOC},
    )
    assert 1 in ability_iids(engine)
    assert decide(engine).kind == "attack"


def test_cycle_refused_when_hand_already_large():
    """手牌张数超过默认上限 4：有垫牌也拒，避免同回合连刷磨牌库。"""
    hand = [inst(50 + i, basic(f"手牌{i}")) for i in range(4)]
    hand.append(inst(80, energy()))
    assert len(hand) == 5
    engine = board(
        placed(1, mon("弃抽手"), energies=1),
        hand,
        deck_n=40,
        effects={"弃抽手": CYCLE_DOC},
    )
    assert 1 in ability_iids(engine)
    assert decide(engine).kind == "attack"


def test_cycle_used_when_deck_and_hand_are_reasonable():
    """牌库高于地板、手牌未超上限、有能量垫牌 → 仍发交易类。"""
    engine = board(
        placed(1, mon("弃抽手"), energies=1),
        fodder_hand(),
        deck_n=13,
        effects={"弃抽手": CYCLE_DOC},
    )
    assert decide(engine) == Action(kind="use_ability", iid=1)


def test_cycle_deck_floor_param_moves_the_line():
    """地板降到 0：牌库 12 也允许（阈值可消融）。"""
    engine = board(
        placed(1, mon("弃抽手"), energies=1),
        fodder_hand(),
        deck_n=12,
        effects={"弃抽手": CYCLE_DOC},
    )
    act = decide(engine, HeuristicParams(ability_cycle_deck_floor=0))
    assert act == Action(kind="use_ability", iid=1)


def test_refresh_all_discard_is_not_a_cycle():
    """整手刷新（count: all + draw）不是交易类：牌库将尽仍走通用价值，会用。"""
    engine = board(
        placed(1, mon("整手刷新"), energies=1),
        [inst(50, basic("手牌"))],
        deck_n=4,
        effects={"整手刷新": REFRESH_DOC},
    )
    assert decide(engine) == Action(kind="use_ability", iid=1)


# ── 附伤类（精神拥抱形态）────────────────────────────────

def _attach_board(*, cost: tuple[str, ...], energies: int, deck_n: int = 20):
    card = mon("附伤手", energy_type="超", cost=cost)
    fuel = psychic_energy() if energies else None
    active = placed(1, card, energies, typed=fuel)
    return board(
        active,
        [inst(50, basic("手牌"))],
        deck_n=deck_n,
        discard=(inst(90, psychic_energy()),),
        effects={"附伤手": ATTACH_DOC},
    )


def test_attach_damage_skipped_without_valuable_target():
    """费用已付清：特性仍合法（活着、弃牌区有能量），但纯加伤，不用。"""
    engine = _attach_board(cost=("无",), energies=1)
    assert 1 in ability_iids(engine)
    assert decide(engine).kind == "attack"


def test_attach_damage_used_when_energy_progresses():
    """两道【超】还没付清：附一张是推进，要用。"""
    engine = _attach_board(cost=("超", "超"), energies=0)
    assert decide(engine) == Action(kind="use_ability", iid=1)


CHARM_DOC = parse_card_doc("""
card:
  name_group: 勇气护符
effects:
  - trigger: passive_static
    condition: holder_is_basic
    actions:
      - {action: modify_hp, args: {amount: 50}}
""")


def _charm_tool() -> CardDef:
    return CardDef(
        card_id="stub-勇气护符", name="勇气护符", supertype="trainer",
        trainer_subtype="宝可梦道具",
    )


def _hurt_attach_value(*, tool: bool, stage: int = 0) -> float:
    """HP 30、已伤 20、再放 2 个指示物（20）。印面会昏厥；基础挂护符后有效 HP 80，还活着。"""
    card = mon("附伤手", energy_type="超", cost=("超",), hp=30)
    if stage:
        card = card.model_copy(update={"stage": stage})
    active = placed(1, card, energies=0)
    updates: dict = {"damage": 20}
    if tool:
        updates["attached_tool"] = inst(81, _charm_tool())
    active = active.model_copy(update=updates)
    effects = {"附伤手": ATTACH_DOC, "勇气护符": CHARM_DOC}
    engine = board(
        active,
        [inst(50, basic("手牌"))],
        deck_n=20,
        discard=(inst(90, psychic_energy()),),
        effects=effects,
    )
    agent = HeuristicAgent(card_effects=effects)
    view = engine.state.visible_state(0)
    return agent._ability_value(view, Action(kind="use_ability", iid=1))


def test_charm_keeps_counter_target_printed_hp_would_ko():
    """印面剩余不够再放 20，护符后还活着 → 附伤特性仍有价值。"""
    assert _hurt_attach_value(tool=True) > 0


def test_no_charm_drops_counter_target_that_would_ko():
    """无道具：再放 20 会昏厥，附伤特性没有活着的目标。"""
    assert _hurt_attach_value(tool=False) == 0


def test_charm_on_evolved_does_not_save_counter_target():
    """holder_is_basic 不成立：护符不加 HP，再放 20 仍视为会昏厥。"""
    assert _hurt_attach_value(tool=True, stage=1) == 0


def test_attach_choice_prefers_pokemon_that_still_needs_energy():
    """两只同分：chooser 选还没付清的那只，不取较小 iid 的已付清战斗场。"""
    card = mon("附伤手", energy_type="超", cost=("超",))
    active = placed(1, card, energies=1, typed=psychic_energy())
    bench = placed(9, card, energies=0)
    p0 = PlayerState(
        deck=tuple(inst(1000 + i, basic("垫牌")) for i in range(10)),
        hand=(inst(50, basic("手牌")),),
        discard=(inst(90, psychic_energy()),),
        active=active,
        bench=(bench,),
    )
    p1 = PlayerState(active=in_play(2, basic("对手")))
    pc = PendingChoice(
        player=0, source=inst(9, card), effect_index=0, cursor=0,
        pool="own_pokemon_in_play",
        filters=("pokemon_超", "would_survive_20"),
        min_choose=1, max_choose=1, destination="attach",
        pool_iids=(1, 9), step_phase="actions", completion="ability",
    )
    state = GameState(
        players=(p0, p1), turn=4, current_player=0, phase="choice",
        first_player=0, pending_choice=pc,
    )
    effects = {"附伤手": ATTACH_DOC}
    engine = GameEngine(RandomSource(0), card_effects=effects)
    engine.state = state
    agent = HeuristicAgent(card_effects=effects)
    act = agent.observe(engine.state.visible_state(0), engine.legal_actions(0))
    assert act == Action(kind="choose", choices=(9,))
    off = HeuristicAgent(HeuristicParams(ability_quality_gate=False), card_effects=effects)
    assert off.observe(engine.state.visible_state(0), engine.legal_actions(0)) == Action(
        kind="choose", choices=(1,))


# ── 多特性按价值，而不是最小 iid ─────────────────────────

def test_multiple_abilities_pick_by_value_not_min_iid():
    """低 iid 交易类合法且合理，但高 iid 附伤类能付清招式 → 选附伤。"""
    cycle = placed(1, mon("弃抽手"), energies=1)
    needy = placed(9, mon("附伤手", energy_type="超", cost=("超",)), energies=0)
    engine = board(
        cycle,
        fodder_hand(),
        deck_n=40,
        bench=(needy,),
        discard=(inst(90, psychic_energy()),),
        effects={"弃抽手": CYCLE_DOC, "附伤手": ATTACH_DOC},
    )
    assert ability_iids(engine) == {1, 9}
    assert decide(engine) == Action(kind="use_ability", iid=9)


def test_quality_gate_off_restores_min_iid():
    """消融开关：同一局面回到最小 iid（交易类），即使附伤更有价值。"""
    cycle = placed(1, mon("弃抽手"), energies=1)
    needy = placed(9, mon("附伤手", energy_type="超", cost=("超",)), energies=0)
    engine = board(
        cycle,
        fodder_hand(),
        deck_n=40,
        bench=(needy,),
        discard=(inst(90, psychic_energy()),),
        effects={"弃抽手": CYCLE_DOC, "附伤手": ATTACH_DOC},
    )
    act = decide(engine, HeuristicParams(ability_quality_gate=False))
    assert act == Action(kind="use_ability", iid=1)


def test_equal_generic_abilities_still_tie_break_by_iid():
    """都是普通抽牌：价值相同，仍取 iid 小者。"""
    engine = board(
        placed(4, mon("抽牌甲"), energies=1),
        [inst(50, basic("手牌"))],
        deck_n=20,
        bench=(placed(2, mon("抽牌乙"), energies=0),),
        effects={"抽牌甲": DRAW_DOC, "抽牌乙": DRAW_DOC},
    )
    assert ability_iids(engine) == {4, 2}
    assert decide(engine) == Action(kind="use_ability", iid=2)


def test_t077_local_experiment_pins_the_diagnosed_cell():
    """本机验收实验：B 诊断同格、种子从 208000 起的 100 局子集。

    只核 YAML 字段（云端无 ptcgdb，不经 load_experiment）。
    """
    raw = yaml.safe_load(
        (ROOT / "experiments" / "t077-gard-zoro.example.yml").read_text(encoding="utf-8"))
    assert raw["name"] == "t077-gard-zoro"
    assert raw["seed_start"] == 208000
    assert raw["games"] == 100
    assert raw["decks"]["a"]["deck_id"] == "mik_moe:678647"
    assert raw["decks"]["b"]["deck_id"] == "mik_moe:690359"
    assert raw["agents"]["a"]["type"] == "heuristic"
    assert raw["agents"]["b"]["type"] == "heuristic"
