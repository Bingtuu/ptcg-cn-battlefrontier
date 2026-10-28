"""task 076：v2 正式矩阵两大失败的回归。

1. IndexError：启发式攻击表只读 card.attacks，漏掉 grant_attack 合成招式
   （招式学习器 能量涡轮；卡面 attacks 为空）。合法 attack_index 越出表长。
2. copy_attack 嵌套 ≥2：暗夜王牌 / 基因侵入复制「自身又是 copy_attack」的招式
   须结算到最内层伤害，不得 DslError。同一 (来源 iid, 招式名) 已在栈上则不可再选。
"""

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.agent.heuristic import HeuristicAgent
from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef


def _copy_doc(name: str, attack: str):
    return parse_card_doc(f"""
card:
  name_group: {name}
effects:
  - trigger: on_attack
    attack: {attack}
    actions:
      - {{action: copy_attack, selector: own_bench_attack, choose: 1}}
""")


HIT = parse_card_doc("""
card:
  name_group: 打手
effects:
  - trigger: on_attack
    attack: 直击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 40}}
""")


def _poke(name: str, attack: str, *, owner: str | None = None, damage: int | None = None) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=220, stage=0, owner=owner, energy_type="恶",
        attacks=(AttackDef(name=attack, cost=("无",), damage=damage),),
        retreat_cost=0,
    )


def test_heuristic_scores_synthesized_turbo_attack() -> None:
    """能量涡轮合成招式必须进攻击表，observe 不得 IndexError。"""
    doc = load_card_doc("cards/招式学习器 能量涡轮.yml")
    holder = CardDef(
        card_id="stub-持有者", name="持有者", supertype="pokemon", hp=100, stage=0,
        attacks=(AttackDef(name="拍击", cost=("无",), damage=10),),
    )
    tool = CardDef(
        card_id="stub-招式学习器 能量涡轮", name="招式学习器 能量涡轮",
        supertype="trainer", trainer_subtype="宝可梦道具",
    )
    active = in_play(1, holder, energies=1).model_copy(update={
        "attached_tool": inst(90, tool),
    })
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": active,
        "bench": (in_play(70, basic("备")),),
        "energy_attached_this_turn": True,
        "deck": (inst(91, energy("雷", "雷")),) + state.players[0].deck,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"招式学习器 能量涡轮": doc}
    legal = e.legal_actions(0)
    attack_idx = [a.attack_index for a in legal if a.kind == "attack"]
    assert attack_idx == [0, 1]
    agent = HeuristicAgent(card_effects=e.card_effects)
    view = e.state.visible_state(0)
    assert len(agent._attack_table(view)) == 2
    chosen = agent.observe(view, legal)
    assert chosen in legal


def test_heuristic_drives_past_synthesized_tool_attack() -> None:
    """主阶段已不能再附能量时，启发式会给合成招式打分并走完这一步。"""
    doc = load_card_doc("cards/招式学习器 能量涡轮.yml")
    holder = CardDef(
        card_id="stub-持有者", name="持有者", supertype="pokemon", hp=100, stage=0,
        attacks=(AttackDef(name="拍击", cost=("无",), damage=10),),
    )
    tool = CardDef(
        card_id="stub-招式学习器 能量涡轮", name="招式学习器 能量涡轮",
        supertype="trainer", trainer_subtype="宝可梦道具",
    )
    active = in_play(1, holder, energies=1).model_copy(update={
        "attached_tool": inst(90, tool),
    })
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": active,
        "bench": (in_play(70, basic("备")),),
        "energy_attached_this_turn": True,
        "deck": (inst(91, energy("雷", "雷")), inst(92, energy("草", "草"))) + state.players[0].deck,
    })
    opp = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=300)),
    })
    e = engine_at(state.model_copy(update={"players": (p0, opp)}))
    e.card_effects = {"招式学习器 能量涡轮": doc}
    agent = HeuristicAgent(card_effects=e.card_effects)
    for _ in range(8):
        if e.state.phase == "game_over" or e.state.current_player != 0:
            break
        acts = e.legal_actions(0)
        e.apply(0, agent.observe(e.state.visible_state(0), acts))
    assert e.state.current_player == 1 or e.state.phase == "game_over"


def _bench_copy_engine():
    copier = _poke("复制兽", "镜像")
    hitter = _poke("打手", "直击")
    active = _poke("索罗亚克", "暗夜王牌")
    state = main_state(p0_active_energies=1)
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(10, copier), in_play(11, hitter)),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=300)),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {
        "索罗亚克": _copy_doc("索罗亚克", "暗夜王牌"),
        "复制兽": _copy_doc("复制兽", "镜像"),
        "打手": HIT,
    }
    return e


def test_copy_attack_depth_two_deals_inner_damage() -> None:
    """暗夜王牌复制「镜像」，镜像再复制直击：40 伤落下，不 DslError。"""
    e = _bench_copy_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(10,)))  # 备战复制兽
    e.apply(0, Action(kind="choose", choices=(0,)))   # 它的镜像
    assert e.state.phase == "choice"
    e.apply(0, Action(kind="choose", choices=(11,)))  # 备战打手
    e.apply(0, Action(kind="choose", choices=(0,)))   # 直击
    assert e.state.players[1].active.damage == 40
    assert e.state.current_player == 1
    assert sum(1 for ev in e.events if ev.kind == "copy_attack") == 2


def test_copy_attack_depth_three_deals_inner_damage() -> None:
    """三层复制栈：暗夜王牌 → 镜像 → 再镜像 → 直击。"""
    deep = _poke("深层", "再镜像")
    copier = _poke("复制兽", "镜像")
    hitter = _poke("打手", "直击")
    active = _poke("索罗亚克", "暗夜王牌")
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(10, copier), in_play(12, deep), in_play(11, hitter)),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=300)),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {
        "索罗亚克": _copy_doc("索罗亚克", "暗夜王牌"),
        "复制兽": _copy_doc("复制兽", "镜像"),
        "深层": _copy_doc("深层", "再镜像"),
        "打手": HIT,
    }
    script = (
        Action(kind="attack", attack_index=0),
        Action(kind="choose", choices=(10,)),
        Action(kind="choose", choices=(0,)),
        Action(kind="choose", choices=(12,)),
        Action(kind="choose", choices=(0,)),
        Action(kind="choose", choices=(11,)),
        Action(kind="choose", choices=(0,)),
    )
    for act in script:
        e.apply(0, act)
    assert e.state.players[1].active.damage == 40
    assert e.state.current_player == 1


def test_gene_hack_copies_night_ace() -> None:
    """梦幻ex 基因侵入复制暗夜王牌，暗夜王牌再复制备战上的 copy_attack（嵌套 ≥2）。"""
    mew_doc = load_card_doc("cards/梦幻ex.yml")
    zoro_doc = load_card_doc("cards/N的索罗亚克ex.yml")
    mew = CardDef(
        card_id="stub-梦幻ex", name="梦幻ex", supertype="pokemon",
        hp=180, stage=0, rule_box="ex", energy_type="超",
        attacks=(AttackDef(name="基因侵入", cost=("无",), damage=None),),
    )
    zoro = CardDef(
        card_id="stub-N的索罗亚克ex", name="N的索罗亚克ex", supertype="pokemon",
        hp=280, stage=1, rule_box="ex", owner="N", energy_type="恶",
        attacks=(AttackDef(name="暗夜王牌", cost=("恶", "恶"), damage=None),),
    )
    donor = CardDef(
        card_id="stub-N的打手", name="N的打手", supertype="pokemon",
        hp=120, stage=0, owner="N", energy_type="恶",
        attacks=(AttackDef(name="直击", cost=("无",), damage=None),),
    )
    mirror = CardDef(
        card_id="stub-N的镜像", name="N的镜像", supertype="pokemon",
        hp=120, stage=0, owner="N", energy_type="恶",
        attacks=(AttackDef(name="镜像", cost=("无",), damage=None),),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, mew, energies=1),
        "bench": (in_play(10, mirror), in_play(11, donor)),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, zoro),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {
        "梦幻ex": mew_doc,
        "N的索罗亚克ex": zoro_doc,
        "N的镜像": _copy_doc("N的镜像", "镜像"),
        "N的打手": HIT,
    }
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(0,)))  # 对手暗夜王牌
    e.apply(0, Action(kind="choose", choices=(10,)))  # 备战 N的镜像
    e.apply(0, Action(kind="choose", choices=(0,)))   # 它的镜像（第二层 copy）
    e.apply(0, Action(kind="choose", choices=(11,)))
    e.apply(0, Action(kind="choose", choices=(0,)))
    assert e.state.players[1].active.damage == 40
    assert e.state.current_player == 1


def test_same_pokemon_attack_not_offered_again() -> None:
    """已进入栈的 (iid, 招式名) 不再出现在下一层可选招式里。"""
    e = _bench_copy_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(10,)))
    e.apply(0, Action(kind="choose", choices=(0,)))
    # 内层镜像选备战：复制兽自身的镜像已在栈上，只剩打手
    assert e.state.phase == "choice"
    bench_choices = {a.choices for a in e.legal_actions(0) if a.kind == "choose"}
    assert (10,) not in bench_choices
    assert (11,) in bench_choices
