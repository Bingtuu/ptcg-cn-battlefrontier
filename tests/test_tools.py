"""task 015：宝可梦道具骨架 + 勇气护符 passive HP + 招式学习器回合末弃置。

规则出处：rules-manual §5（宝可梦道具每只限 1 个）/§8（伤害 ≥ 最大 HP 昏厥——
HP 修饰影响判定）；§4（撤退/进化保留道具）；招式学习器原文「放于宝可梦身上的
这张卡牌，将在自己的回合结束时被放于弃牌区」。
"""

import pytest
from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import load_card_dir, parse_card_doc
from battlefrontier.engine.actions import Action, IllegalActionError
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    InPlayPokemon,
)

CHARM_DOC = parse_card_doc("""
card:
  name_group: 勇气护符
effects:
  - trigger: passive_static
    condition: holder_is_basic
    actions:
      - {action: modify_hp, args: {amount: 50}}
""")

LEARNER_DOC = parse_card_doc("""
card:
  name_group: 招式学习器 进化
effects:
  - trigger: passive_static
    actions:
      - {action: grant_attack, args: {attack: 进化, discard_at_turn_end: true}}
""")


def tool(name: str, attacks: tuple = ()) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具", attacks=attacks)


def tool_engine(card: CardDef, doc, *, active=None, bench=(), iid: int = 60):
    """main 局面：p0 手牌含道具（iid 60），可自带场上配置。"""
    state = main_state(p0_extra_hand=(inst(iid, card),))
    updates = {}
    if active is not None:
        updates["active"] = active
    if bench:
        updates["bench"] = bench
    if updates:
        p0 = state.players[0].model_copy(update=updates)
        state = state.model_copy(update={"players": (p0, state.players[1])})
    e = engine_at(state)
    if doc is not None:
        e.card_effects = {card.name: doc}
    return e


def attach_actions(e):
    return [a for a in e.legal_actions(0) if a.kind == "attach_tool"]


# ── attach_tool 枚举与流程 ───────────────────────────────────────────────

def test_attach_tool_enumeration_and_flow() -> None:
    e = tool_engine(tool("勇气护符"), CHARM_DOC, bench=(in_play(70, basic("小火龙")),))
    acts = attach_actions(e)
    assert sorted(a.target_iid for a in acts) == [1, 70]  # 战斗场 + 备战各一条
    e.apply(0, next(a for a in acts if a.target_iid == 70))
    p0 = e.state.players[0]
    assert p0.bench[0].attached_tool.card.name == "勇气护符"
    assert 60 not in [c.iid for c in p0.hand]
    assert any(ev.kind == "attach_tool" for ev in e.events)


def test_one_tool_per_pokemon() -> None:
    """每只限 1 个：已持有的宝可梦不再成为目标；非法行动抛错。"""
    holder = in_play(1, basic("妙蛙种子"))
    holder = holder.model_copy(update={"attached_tool": inst(90, tool("勇气护符"))})
    e = tool_engine(tool("勇气护符"), CHARM_DOC, active=holder,
                    bench=(in_play(70, basic("小火龙")),))
    assert sorted(a.target_iid for a in attach_actions(e)) == [70]
    with pytest.raises(IllegalActionError):
        e.apply(0, Action(kind="attach_tool", iid=60, target_iid=1))


# ── 勇气护符：passive HP+50 贯穿 KO 判定 ─────────────────────────────────

def _charmed(name="妙蛙种子", hp=70, damage=0, stage_card=None):
    mon_card = stage_card or basic(name, hp=hp)
    return InPlayPokemon(stack=(inst(1, mon_card),), damage=damage,
                         attached_tool=inst(90, tool("勇气护符")))


def test_charm_hp_bonus_survives_ko_check() -> None:
    """110 伤对 70 血：无护符昏厥；有护符（基础 +50 → 120）存活。"""
    e = tool_engine(tool("勇气护符"), CHARM_DOC, active=_charmed(damage=110))
    e.check_knockouts()
    assert e.state.players[0].active is not None  # 存活
    e = tool_engine(tool("勇气护符"), CHARM_DOC, active=_charmed(damage=120))
    e.check_knockouts()
    assert e.state.players[0].active is None  # 120 ≥ 120 昏厥
    # 无护符对照：110 ≥ 70 昏厥
    e = tool_engine(tool("勇气护符"), CHARM_DOC,
                    active=in_play(1, basic("妙蛙种子", hp=70), energies=0).__class__(
                        stack=(inst(1, basic("妙蛙种子", hp=70)),), damage=110))
    e.check_knockouts()
    assert e.state.players[0].active is None


def test_charm_bonus_lost_on_evolution() -> None:
    """「【基础】宝可梦」限定：进化后顶栈非基础，加成立即失效。"""
    from helpers import stage1

    evolved = InPlayPokemon(
        stack=(inst(1, basic("妙蛙种子", hp=70)),
               inst(8, stage1("妙蛙草", "妙蛙种子", hp=90))),
        damage=100,  # 基础 90 已超；带护符若按 90+50 则存活——但非基础不加成
        attached_tool=inst(90, tool("勇气护符")),
    )
    e = tool_engine(tool("勇气护符"), CHARM_DOC, active=evolved)
    e.check_knockouts()
    assert e.state.players[0].active is None  # 100 ≥ 90 昏厥（护符不加成）


def test_knockout_discards_tool_with_stack() -> None:
    """昏厥整叠：道具随进化链+能量一起进弃牌区。"""
    e = tool_engine(tool("勇气护符"), CHARM_DOC, active=_charmed(damage=120))
    e.check_knockouts()
    p0 = e.state.players[0]
    assert sorted(c.iid for c in p0.discard) == [1, 90]  # 宝可梦 + 道具


def test_charm_counts_for_embrace_guard() -> None:
    """would_survive_20 按 effective_hp：70 血 60 伤带护符（120）仍可选为精神拥抱目标。"""
    from test_ability import GARDEVOIR_DOC, gardevoir, psy_energy

    # 护符限【基础】，故目标用超属性基础（拉鲁拉丝）而非沙奈朵ex（stage 2 不加成）
    ralts = CardDef(card_id="stub-拉鲁拉丝", name="拉鲁拉丝", supertype="pokemon",
                    hp=70, stage=0, energy_type="超")
    target = InPlayPokemon(stack=(inst(11, ralts),), damage=60,
                           attached_tool=inst(90, tool("勇气护符")))
    active = InPlayPokemon(stack=(inst(10, gardevoir()),), damage=300)  # 战斗场自身会昏厥
    from helpers import main_state as ms

    state = ms()
    p0 = state.players[0].model_copy(update={
        "active": active, "bench": (target,), "discard": (inst(80, psy_energy()),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"沙奈朵ex": GARDEVOIR_DOC, "勇气护符": CHARM_DOC}
    e.apply(0, Action(kind="use_ability", iid=10))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose"))  # 选能量 80
    choices = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert choices == [(11,)]  # 护符 +50 → 60+20 < 120 存活，可选


# ── 招式学习器：回合末弃置 + 授予招式纪律 ────────────────────────────────

def test_learner_discarded_at_own_turn_end() -> None:
    """「自己的回合结束时被放于弃牌区」：end_turn 与攻击后都触发；对手回合结束不弃。"""
    learner = tool("招式学习器 进化", attacks=(AttackDef(name="进化", cost=("无",), damage=None),))
    holder = in_play(1, basic("妙蛙种子"), energies=1)  # 打击 cost=(无,) 需 1 能量
    holder = holder.model_copy(update={"attached_tool": inst(90, learner)})
    e = tool_engine(learner, LEARNER_DOC, active=holder)
    # 攻击结束回合 → 弃置
    e.apply(0, Action(kind="attack", attack_index=0))
    p0 = e.state.players[0]
    assert p0.active.attached_tool is None
    assert 90 in [c.iid for c in p0.discard]


def test_learner_not_discarded_on_opponent_turn_end() -> None:
    learner = tool("招式学习器 进化", attacks=(AttackDef(name="进化", cost=("无",), damage=None),))
    holder = in_play(1, basic("妙蛙种子"))
    holder = holder.model_copy(update={"attached_tool": inst(90, learner)})
    e = tool_engine(learner, LEARNER_DOC, active=holder)
    e.apply(0, Action(kind="end_turn"))  # p0 结束 → 弃置（自己回合）
    assert 90 in [c.iid for c in e.state.players[0].discard]
    # 对照：学习器在 p1 场上时，p0 回合结束不影响
    holder1 = in_play(2, basic("小火龙")).__class__(
        stack=(inst(2, basic("小火龙")),), attached_tool=inst(91, learner),
        attached_energy=in_play(2, basic("小火龙")).attached_energy)
    state = main_state()
    p1 = state.players[1].model_copy(update={"active": holder1})
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.card_effects = {"招式学习器 进化": LEARNER_DOC}
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[1].active.attached_tool is not None  # 对手回合末不弃


def test_granted_attack_without_binding_not_enumerated() -> None:
    """授予招式的 on_attack 效果归 task 016：本期无绑定 → 不枚举（锁定 defer）。"""
    learner = tool("招式学习器 进化", attacks=(AttackDef(name="进化", cost=("无",), damage=None),))
    holder = in_play(1, basic("妙蛙种子"), energies=1)
    holder = holder.model_copy(update={"attached_tool": inst(90, learner)})
    e = tool_engine(learner, LEARNER_DOC, active=holder)
    # 妙蛙种子自身有 1 个白板招式（20 伤），授予的「进化」无 on_attack 绑定 → 不出现
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert [a.attack_index for a in attacks] == [0]


# ── 定义库与对局级确定性 ────────────────────────────────────────────────

def test_card_library_tools() -> None:
    docs = load_card_dir("cards")
    assert {"勇气护符", "招式学习器 进化"} <= set(docs)
    # 定义库总数断言由最新入库任务的测试持有（当前 test_evolve::test_card_library_twenty）
    charm = docs["勇气护符"].effects[0]
    assert charm.trigger == "passive_static" and charm.condition == "holder_is_basic"
    learner = docs["招式学习器 进化"].effects[0].actions[0]
    assert learner.action == "grant_attack" and learner.args["discard_at_turn_end"] is True


def test_play_game_with_tools_deterministic() -> None:
    """含道具的整局对局：同种子事件流 hash 一致。"""
    from battlefrontier.runner.play import play_game

    deck = ([basic("妙蛙种子")] * 20 + [tool("勇气护符")] * 4
            + [tool("招式学习器 进化")] * 4
            + [energy("基本超能量", "超")] * 16 + [energy()] * 16)
    effects = load_card_dir("cards")
    r1 = play_game(deck, deck, seed=19, card_effects=effects)
    r2 = play_game(deck, deck, seed=19, card_effects=effects)
    assert r1.events_hash == r2.events_hash
