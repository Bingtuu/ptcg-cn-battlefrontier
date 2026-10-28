"""单卡 DSL 测试（task 070 WP1b 批）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批可写 4 张（粉碎之锤 / N的城堡 / 驱劲能量 未来 / 招式学习器 能量涡轮 因缺
已注册词/引擎读点 blocked，缺失明细见批报告，本文件不覆盖）：
- N的PP提升剂（CSV10C-190，物品）：attach_energy own_discard → own_bench
  （target_filters owner_pokemon:N）。
- 璀璨结晶（CSV8C-186 同文本等价类 2 印刷，ACE SPEC 道具）：modify_attack_cost
  types:all + holder_is_tera（task 069 WP3）。
- 力之沙漏（CSV8C-188 同文本等价类 4 印刷，道具）：trigger_on_event own_turn_end
  （D-069-1 时点）+ attach_energy own_discard target_pool=self（task 069 WP4）。
- 逆转能量（CSV2C-128 同文本等价类 3 印刷，特殊能量）：provide_energy 条件分层
  （task 070 WP0 组合词 own_prizes_more_and_holder_evolved_no_rule_box）。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    InPlayPokemon,
)

CARDS_DIR = Path(__file__).parent.parent / "cards"

PP_UP_DOC = load_card_doc(CARDS_DIR / "N的PP提升剂.yml")
CRYSTAL_DOC = load_card_doc(CARDS_DIR / "璀璨结晶.yml")
HOURGLASS_DOC = load_card_doc(CARDS_DIR / "力之沙漏.yml")
REVERSAL_DOC = load_card_doc(CARDS_DIR / "逆转能量.yml")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def special_energy(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy",
                   is_basic_energy=False)


def n_pokemon(name: str, *, stage: int = 0) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=120, stage=stage, owner="N",
        attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
    )


def pokemon(name: str, *, stage: int = 0, rule_box: str | None = None,
            is_tera: bool = False, attacks: tuple | None = None) -> CardDef:
    if attacks is None:
        attacks = (AttackDef(name="打击", cost=("无",), damage=20),)
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=500, stage=stage, attacks=attacks, rule_box=rule_box, is_tera=is_tera,
    )


def attack_indices(e: GameEngine, player: int = 0) -> list[int]:
    return [a.attack_index for a in e.legal_actions(player) if a.kind == "attack"]


# ── N的PP提升剂（on_play：弃牌区基本能量 → 备战区「N的宝可梦」）─────────────


def pp_up_engine(*, discard: tuple = (), bench: tuple = ()) -> GameEngine:
    """main 阶段：p0 手牌含 N的PP提升剂（iid=60），战斗场 stub 妙蛙种子。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("N的PP提升剂")),))
    p0 = state.players[0].model_copy(update={"discard": discard, "bench": bench})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"N的PP提升剂": PP_UP_DOC}
    return e


def test_N的PP提升剂_回收基本能量附着备战N的宝可梦() -> None:
    """全链路：打出 → 段1 选弃牌区 1 张基本能量 → 段2 目标池仅备战「N的宝可梦」
    （非 N 备战 iid=4 经 target_filters 剔除）→ 附着完成，本体进弃牌区。"""
    bench = (in_play(3, n_pokemon("N的索罗亚")), in_play(4, basic("小火龙")))
    e = pp_up_engine(discard=(inst(70, energy("基本火能量", "火")),), bench=bench)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.pool == "own_discard" and tuple(pc.pool_iids) == (70,)
    e.apply(0, Action(kind="choose", choices=(70,)))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.pool == "own_bench" and tuple(pc.pool_iids) == (3,)
    e.apply(0, Action(kind="choose", choices=(3,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.bench[0].attached_energy] == [70]
    assert p0.bench[1].attached_energy == ()
    assert 60 in [c.iid for c in p0.discard]  # 本体收尾进弃牌区
    assert e.state.phase == "main" and e.state.pending_choice is None


def test_N的PP提升剂_备战区无N的宝可梦不可使用() -> None:
    """可行性门：备战目标池（owner_pokemon:N）为空 → 不枚举（无效果不可使用）。"""
    e = pp_up_engine(
        discard=(inst(70, energy("基本火能量", "火")),),
        bench=(in_play(4, basic("小火龙")),),
    )
    assert not [
        a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60
    ]


def test_N的PP提升剂_弃牌区无基本能量不可使用() -> None:
    """可行性门：弃牌区能量池为空（特殊能量不匹配 basic_energy）→ 不枚举。"""
    e = pp_up_engine(
        discard=(inst(70, special_energy("逆转能量")),),
        bench=(in_play(3, n_pokemon("N的索罗亚")),),
    )
    assert not [
        a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60
    ]


# ── 璀璨结晶（ACE SPEC 道具：太晶持有者招式费用 -1 任意属性）─────────────────

TRI_ATTACK = AttackDef(name="三重击", cost=("火", "水", "雷"), damage=100)
FIRE_COLORLESS_ATTACK = AttackDef(name="火无击", cost=("火", "无"), damage=50)


def crystal_engine(attack: AttackDef, energies: tuple, *, is_tera: bool = True) -> GameEngine:
    """main 阶段：p0 战斗场持有者（iid=1）带璀璨结晶（iid=90）。"""
    holder = in_play(1, pokemon("太晶兽", is_tera=is_tera, attacks=(attack,)))
    holder = holder.model_copy(update={
        "attached_energy": energies,
        "attached_tool": inst(90, tool_card("璀璨结晶")),
    })
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": holder})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"璀璨结晶": CRYSTAL_DOC}
    return e


def test_璀璨结晶_太晶持有者减任意1符号() -> None:
    """机制正向：【火】【水】【雷】费太晶持有者，附着水+雷即可攻击
    （无【无】符号 → 减 cost 序列首个有色符号【火】，有效费用 = 水雷）。"""
    e = crystal_engine(TRI_ATTACK, (inst(9101, energy("水能量", "水")),
                                    inst(9102, energy("雷能量", "雷"))))
    assert 0 in attack_indices(e)


def test_璀璨结晶_非太晶持有者不减() -> None:
    """边界：holder_is_tera 不通过 → 3 费招 2 能量不可攻击。"""
    e = crystal_engine(TRI_ATTACK, (inst(9101, energy("水能量", "水")),
                                    inst(9102, energy("雷能量", "雷"))),
                       is_tera=False)
    assert attack_indices(e) == []


def test_璀璨结晶_费用含无优先减无() -> None:
    """取法钉死：【火】【无】→ 有效费用【火】，单火能量即可攻击；无工具对照不可攻击。"""
    e = crystal_engine(FIRE_COLORLESS_ATTACK, (inst(9101, energy("火能量", "火")),))
    assert 0 in attack_indices(e)
    plain = crystal_engine(FIRE_COLORLESS_ATTACK, (inst(9101, energy("火能量", "火")),))
    holder = plain.state.players[0].active.model_copy(update={"attached_tool": None})
    p0 = plain.state.players[0].model_copy(update={"active": holder})
    plain.state = plain.state.model_copy(
        update={"players": (p0, plain.state.players[1])})
    assert attack_indices(plain) == []


# ── 力之沙漏（own_turn_end：回合结束回收弃牌区基本能量附着持有者自身）─────────


def hourglass_engine(*, bench_tool: bool = False, discard: tuple = ()) -> GameEngine:
    """main 阶段：力之沙漏（iid=90）挂在 p0 战斗场（或备战 iid=3）。"""
    tool = inst(90, tool_card("力之沙漏"))
    holder = in_play(3 if bench_tool else 1, basic("妙蛙种子"))
    holder = holder.model_copy(update={"attached_tool": tool})
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, basic("小火龙")) if bench_tool else holder,
        "bench": (holder,) if bench_tool else (),
        "discard": discard,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"力之沙漏": HOURGLASS_DOC}
    return e


def own_turn_end_fired(e: GameEngine) -> bool:
    return any(
        ev.kind == "trigger_on_event" and ev.detail.get("event") == "own_turn_end"
        for ev in e.events
    )


def test_力之沙漏_回合结束回收附着战斗场持有者() -> None:
    """机制正向：end_turn → 检查阶段触发 → 挂起选弃牌区基本能量 → 段2 免选
    （target_pool=self）附到战斗场持有者 → 检查收尾开下一回合。"""
    e = hourglass_engine(discard=(inst(70, energy("基本火能量", "火")),))
    e.apply(0, Action(kind="end_turn"))
    assert own_turn_end_fired(e)
    assert e.state.phase == "choice" and e.state.current_player == 0
    pc = e.state.pending_choice
    assert pc.pool == "own_discard" and tuple(pc.pool_iids) == (70,)
    e.apply(0, Action(kind="choose", choices=(70,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [70]
    assert p0.discard == ()
    assert e.state.phase == "main" and e.state.current_player == 1


def test_力之沙漏_可放弃选择0张() -> None:
    """「则可选择」= energy_up_to（min_choose=0）：选 0 张放弃，能量留弃牌区。"""
    e = hourglass_engine(discard=(inst(70, energy("基本火能量", "火")),))
    e.apply(0, Action(kind="end_turn"))
    assert e.state.phase == "choice"
    assert Action(kind="choose", choices=()) in e.legal_actions(0)
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert p0.active.attached_energy == ()
    assert [c.iid for c in p0.discard] == [70]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_力之沙漏_备战区持有者不触发() -> None:
    """边界：「在战斗场上的话」= holder_is_active 不满足 → 不触发不挂起。"""
    e = hourglass_engine(bench_tool=True,
                         discard=(inst(70, energy("基本火能量", "火")),))
    e.apply(0, Action(kind="end_turn"))
    assert not own_turn_end_fired(e)
    assert e.state.players[0].bench[0].attached_energy == ()
    assert e.state.phase == "main" and e.state.current_player == 1


def test_力之沙漏_弃牌区无基本能量不挂起() -> None:
    """边界：触发照常分发，能量池空 → 不挂起空结算，回合正常移交。"""
    e = hourglass_engine()
    e.apply(0, Action(kind="end_turn"))
    assert own_turn_end_fired(e)
    assert e.state.players[0].active.attached_energy == ()
    assert e.state.phase == "main" and e.state.current_player == 1


# ── 逆转能量（provide_energy 条件分层：3 彩虹 ↔ 1【无】）──────────────────────


def reversal_engine(*, holder: InPlayPokemon, p0_prizes: int = 6,
                    p1_prizes: int = 6) -> GameEngine:
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": holder,
        "prizes": tuple(inst(200 + i, basic(f"赏{i}")) for i in range(p0_prizes)),
    })
    p1 = state.players[1].model_copy(update={
        "prizes": tuple(inst(400 + i, basic(f"敌赏{i}")) for i in range(p1_prizes)),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"逆转能量": REVERSAL_DOC}
    return e


def fire3_attacker(name: str, *, stage: int = 1, rule_box: str | None = None) -> CardDef:
    return pokemon(name, stage=stage, rule_box=rule_box,
                   attacks=(AttackDef(name="三火击", cost=("火", "火", "火"), damage=30),))


def reversal_holder(card: CardDef) -> InPlayPokemon:
    mon = in_play(1, card)
    return mon.model_copy(update={
        "attached_energy": (inst(90, special_energy("逆转能量")),),
    })


def test_逆转能量_条件满足供3个彩虹() -> None:
    """机制正向：奖赏 6v5（多）+ 1阶无规则盒持有者 → 1 张逆转能量供 3 彩虹，
    【火】【火】【火】可攻。"""
    e = reversal_engine(holder=reversal_holder(fire3_attacker("火兽")),
                        p0_prizes=6, p1_prizes=5)
    assert 0 in attack_indices(e)


def test_逆转能量_条件不满足回退1个无() -> None:
    """边界：奖赏相等 → 回退 1 个【无】——3 有色需求不可攻，1 无色需求可攻。"""
    e = reversal_engine(holder=reversal_holder(fire3_attacker("火兽")))
    assert attack_indices(e) == []
    plain = reversal_engine(holder=reversal_holder(pokemon("无兽")))
    assert 0 in attack_indices(plain)


def test_逆转能量_规则盒持有者回退() -> None:
    """边界：进化但带规则盒（ex）持有者 → 条件不通过（「除拥有规则的宝可梦外」），
    回退 1 个【无】。"""
    e = reversal_engine(
        holder=reversal_holder(fire3_attacker("火兽ex", stage=2, rule_box="ex")),
        p0_prizes=6, p1_prizes=5)
    assert attack_indices(e) == []


def test_逆转能量_基础宝可梦持有者回退() -> None:
    """边界：基础（stage 0）持有者非进化 → 回退 1 个【无】。"""
    e = reversal_engine(
        holder=reversal_holder(fire3_attacker("火兽", stage=0)),
        p0_prizes=6, p1_prizes=5)
    assert attack_indices(e) == []
