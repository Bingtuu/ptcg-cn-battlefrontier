"""单卡 DSL 测试（task 026 WP4）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批卡（rest=shuffle 检视 + attach bench-only/up-to + modify_retreat_cost + cost 弃置排除
随之解锁）：
- 米立龙（H 标 CSV8C-160 揽客等价类）：ability_manual once_per_turn + self_is_active +
  search top_n=6 trainer_supporter rest=shuffle + reveal。
- 宝可装置3.0（G 标 CSV2C-113 等价类）：on_play + top_n=7 trainer_supporter rest=shuffle + reveal。
- 怒鹦哥ex（G 标 CSV2C-105 等价类）：特性英武重抽（first_own_turn + once_per_turn_shared +
  discard all + draw 6）+ 招式鼓足干劲（attach bench-only up-to 2）。
- 飞天螳螂（G 标 151C-123 辅助斩等价类）：on_attack + attach bench-only choose=1 energy_草。
- 紧急滑板（H 标 CSV7C-185 等价类）：passive_static modify_retreat_cost（-1 / HP≤30 全免）。
- 拉帝亚斯ex（H 标 CSV9C-078 等价类）：passive_static modify_retreat_cost own_basic_all。
- 超级能量回收（G 标 CSV3C-115 等价类）：cost discard 2 + recover hand up-to 4
  basic_energy exclude_cost_discarded + reveal。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

TATSUGIRI_DOC = load_card_doc(CARDS_DIR / "米立龙.yml")
POKEGEAR_DOC = load_card_doc(CARDS_DIR / "宝可装置3.0.yml")
SQUAWKABILLY_DOC = load_card_doc(CARDS_DIR / "怒鹦哥ex.yml")
SCYTHER_DOC = load_card_doc(CARDS_DIR / "飞天螳螂.yml")
SKATE_DOC = load_card_doc(CARDS_DIR / "紧急滑板.yml")
LATIAS_DOC = load_card_doc(CARDS_DIR / "拉帝亚斯ex.yml")
SUPER_RECOVERY_DOC = load_card_doc(CARDS_DIR / "超级能量回收.yml")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


# ── 米立龙（揽客：top_n=6 rest=shuffle 特性）──────────────────────────────────


def tatsugiri() -> CardDef:
    return CardDef(
        card_id="stub-米立龙", name="米立龙", supertype="pokemon",
        hp=70, stage=0,
        attacks=(AttackDef(name="冲浪", cost=("火", "水"), damage=50),),
        retreat_cost=1,
    )


def tatsugiri_engine(deck, *, on_bench: bool = False) -> object:
    """main 阶段：p0 米立龙（默认战斗场 iid 1；on_bench=True 时备战区 iid 70）。"""
    state = main_state()
    if on_bench:
        p0 = state.players[0].model_copy(update={
            "bench": (in_play(70, tatsugiri()),), "deck": deck,
        })
    else:
        p0 = state.players[0].model_copy(update={
            "active": in_play(1, tatsugiri()), "deck": deck,
        })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"米立龙": TATSUGIRI_DOC}
    return e


def test_米立龙_揽客_战斗场发动() -> None:
    """战斗场发动：检视顶 6 选 1 支援者入手（给对手看过 = reveal 事件），剩余整库重洗。"""
    deck = (inst(100, supporter_card("支援者甲")), inst(101, supporter_card("支援者乙"))) + tuple(
        inst(102 + i, basic(f"库{chr(19968 + i)}")) for i in range(8)
    )
    e = tatsugiri_engine(deck)
    e.apply(0, Action(kind="use_ability", iid=1))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool_iids == (100, 101)  # 窗内 2 张支援者
    assert pc.min_choose == 0 and pc.max_choose == 1
    e.apply(0, Action(kind="choose", choices=(101,)))
    p0 = e.state.players[0]
    assert 101 in [c.iid for c in p0.hand]
    assert sorted(c.iid for c in p0.deck) == [100, 102, 103, 104, 105, 106, 107, 108, 109]
    assert [c.iid for c in p0.deck] != [100, 102, 103, 104, 105, 106, 107, 108, 109]  # 重洗
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert reveal.detail["iids"] == [101] and reveal.detail["names"] == ["支援者乙"]
    assert any(ev.kind == "effect_observe" and ev.detail["anchor"] == "key_search"
               for ev in e.events)
    assert e.state.phase == "main" and e.state.current_player == 0


def test_米立龙_揽客_备战位不可发动() -> None:
    """self_is_active 条件：备战位的米立龙不枚举特性（「在战斗场上的话」）。"""
    deck = (inst(100, supporter_card("支援者甲")),) + tuple(
        inst(101 + i, basic("妙蛙种子")) for i in range(7)
    )
    e = tatsugiri_engine(deck, on_bench=True)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


def test_米立龙_揽客_窗内无支援者仍重洗() -> None:
    """窗内（顶 6 张）无支援者：no-op 不挂起，但「剩余放回牌库并重洗」依然成立。"""
    deck = tuple(inst(100 + i, basic(f"库{chr(19968 + i)}")) for i in range(6)) + (
        inst(106, supporter_card("窗外支援者")), inst(107, basic("库尾")),
    )
    e = tatsugiri_engine(deck)
    assert Action(kind="use_ability", iid=1) in e.legal_actions(0)  # 全库有支援者，门放行
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "main" and e.state.pending_choice is None  # 不挂起
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51]  # 手牌不变
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 104, 105, 106, 107]
    assert [c.iid for c in p0.deck] != [c.iid for c in deck]  # 整库重洗


def test_米立龙_揽客_限次() -> None:
    """once_per_turn：发动后本回合不再枚举该特性。"""
    deck = (inst(100, supporter_card("支援者甲")),) + tuple(
        inst(101 + i, basic("妙蛙种子")) for i in range(7)
    )
    e = tatsugiri_engine(deck)
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(100,)))
    assert not [a for a in e.legal_actions(0)
                if a.kind == "use_ability" and a.iid == 1]


# ── 宝可装置3.0（on_play top_n=7 rest=shuffle）────────────────────────────────


def pokegear_engine(deck) -> object:
    """main 阶段：p0 手牌含宝可装置3.0（iid 60，物品）。"""
    state = main_state(
        p0_extra_hand=(inst(60, item_card("宝可装置3.0")),),
    )
    p0 = state.players[0].model_copy(update={"deck": deck})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"宝可装置3.0": POKEGEAR_DOC}
    return e


def pokegear_deck() -> tuple:
    """顶 7 张含 2 张支援者（100/103），共 9 张。"""
    cards = {100: supporter_card("支援者甲"), 103: supporter_card("支援者乙")}
    return tuple(inst(100 + i, cards.get(100 + i, basic(f"库{chr(19968 + i)}")))
                 for i in range(9))


def test_宝可装置30_检视选1() -> None:
    """检视顶 7 选 1 支援者入手 + reveal 事件；剩余整库重洗；本体进弃牌区。"""
    e = pokegear_engine(pokegear_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool_iids == (100, 103)  # 窗内支援者（104 起为窗外）
    e.apply(0, Action(kind="choose", choices=(100,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51, 100]
    assert sorted(c.iid for c in p0.deck) == [101, 102, 103, 104, 105, 106, 107, 108]
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert reveal.detail["iids"] == [100] and reveal.detail["names"] == ["支援者甲"]
    assert [c.iid for c in p0.discard] == [60]
    assert e.state.phase == "main"


def test_宝可装置30_空选仍重洗() -> None:
    """空选（选 0 张）：手牌不变，窗内全部视为剩余整库重洗。"""
    deck = pokegear_deck()
    e = pokegear_engine(deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51]
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 104, 105, 106, 107, 108]
    assert [c.iid for c in p0.deck] != [c.iid for c in deck]  # 整库重洗


def test_宝可装置30_牌库不足7() -> None:
    """牌库仅 3 张 → 检视 3 张尽力而为（池 = 窗内支援者）。"""
    deck = (inst(100, supporter_card("支援者甲")), inst(101, basic("妙蛙种子")),
            inst(102, basic("小火龙")))
    e = pokegear_engine(deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool_iids == (100,)
    e.apply(0, Action(kind="choose", choices=(100,)))
    assert 100 in [c.iid for c in e.state.players[0].hand]


# ── 怒鹦哥ex（英武重抽 + 鼓足干劲）─────────────────────────────────────────────


def squawkabilly() -> CardDef:
    return CardDef(
        card_id="stub-怒鹦哥ex", name="怒鹦哥ex", supertype="pokemon",
        hp=160, stage=0, rule_box="ex",
        attacks=(AttackDef(name="鼓足干劲", cost=("无",), damage=20),),
        retreat_cost=1,
    )


def squawk_engine(*, turn: int = 2, p0_bench: tuple = (), discard: tuple = (),
                  hand=None) -> object:
    """main 阶段：p0 战斗场怒鹦哥ex（iid 1，附 1 无能量满足鼓足干劲成本）。"""
    state = main_state()
    active = in_play(1, squawkabilly()).model_copy(update={
        "attached_energy": (inst(9001, energy()),),
    })
    update: dict[str, object] = {"active": active, "bench": p0_bench, "discard": discard}
    if hand is not None:
        update["hand"] = hand
    p0 = state.players[0].model_copy(update=update)
    e = engine_at(state.model_copy(update={
        "players": (p0, state.players[1]), "turn": turn,
    }))
    e.card_effects = {"怒鹦哥ex": SQUAWKABILLY_DOC}
    return e


def test_怒鹦哥ex_英武重抽_首回合可用() -> None:
    """特性英武重抽：最初的自己回合（turn==1）可发动——手牌全弃，抽 6 张。"""
    hand = (inst(50, basic("小火龙")), inst(51, energy()), inst(52, item_card("物品甲")))
    e = squawk_engine(turn=1, hand=hand)
    assert Action(kind="use_ability", iid=1) in e.legal_actions(0)
    e.apply(0, Action(kind="use_ability", iid=1))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.discard] == [50, 51, 52]  # 手牌全弃
    assert [c.iid for c in p0.hand] == [100, 101, 102, 103, 104, 105]  # 抽 6
    assert e.state.phase == "main" and e.state.current_player == 0


def test_怒鹦哥ex_英武重抽_次回合不可用() -> None:
    """first_own_turn：turn==2 起特性不枚举。"""
    e = squawk_engine(turn=2)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


def test_怒鹦哥ex_英武重抽_共享限次() -> None:
    """once_per_turn_shared：一只发动后，同名特性本回合不再枚举（「其他的英武重抽」）。"""
    e = squawk_engine(turn=1, p0_bench=(in_play(70, squawkabilly()),))
    e.apply(0, Action(kind="use_ability", iid=1))
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


def test_怒鹦哥ex_鼓足干劲_选2附1备战() -> None:
    """招式鼓足干劲：20 伤害照算 + 弃牌区 2 张基本能量附着于 1 只备战宝可梦。"""
    discard = (inst(80, energy("草能量", "草")), inst(81, energy("火能量", "火")))
    e = squawk_engine(turn=2, p0_bench=(in_play(70, basic("备战兽")),), discard=discard)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20  # 伤害照算
    pc1 = e.state.pending_choice
    assert pc1.pool == "own_discard" and pc1.min_choose == 0 and pc1.max_choose == 2
    e.apply(0, Action(kind="choose", choices=(80, 81)))
    pc2 = e.state.pending_choice
    assert pc2.pool == "own_bench" and pc2.pool_iids == (70,)
    e.apply(0, Action(kind="choose", choices=(70,)))
    p0 = e.state.players[0]
    assert [e_.iid for e_ in p0.bench[0].attached_energy] == [80, 81]
    assert e.state.phase == "main" and e.state.current_player == 1  # 攻击后回合推进


def test_怒鹦哥ex_鼓足干劲_选0_noop() -> None:
    """「最多2张」：选 0 张能量 → 不进段2 直接完成（伤害照算、回合推进）。"""
    discard = (inst(80, energy("草能量", "草")),)
    e = squawk_engine(turn=2, p0_bench=(in_play(70, basic("备战兽")),), discard=discard)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=()))
    assert e.state.phase == "main" and e.state.current_player == 1
    p0 = e.state.players[0]
    assert p0.bench[0].attached_energy == ()
    assert [c.iid for c in p0.discard] == [80]  # 能量留弃牌区
    assert e.state.players[1].active.damage == 20


def test_怒鹦哥ex_鼓足干劲_无备战仍可宣言_效果noop() -> None:
    """无备战（附着目标空）仍可宣言（2026-09-14 用户裁决：招式附加效果无法执行
    不阻却宣言）：伤害照算、附着效果 no-op 不挂起、回合正常推进。"""
    e = squawk_engine(turn=2, discard=(inst(80, energy("草能量", "草")),))
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert attacks
    e.apply(0, attacks[0])
    assert e.state.phase == "main" and e.state.current_player == 1
    assert e.state.players[1].active.damage == 20
    assert [c.iid for c in e.state.players[0].discard] == [80]  # 能量留弃牌区


# ── 飞天螳螂（辅助斩：attach bench-only choose=1 energy_草）────────────────────


def scyther() -> CardDef:
    return CardDef(
        card_id="stub-飞天螳螂", name="飞天螳螂", supertype="pokemon",
        hp=70, stage=0, energy_type="草",
        attacks=(
            AttackDef(name="辅助斩", cost=("草",), damage=20),
            AttackDef(name="薄片利刃", cost=("草", "无", "无"), damage=70),
        ),
        retreat_cost=0,
    )


def scyther_engine(*, p0_bench: tuple = (), discard: tuple = ()) -> object:
    """main 阶段：p0 战斗场飞天螳螂（iid 1，附 1 草能量满足辅助斩成本）。"""
    state = main_state()
    active = in_play(1, scyther()).model_copy(update={
        "attached_energy": (inst(9001, energy("草能量", "草")),),
    })
    p0 = state.players[0].model_copy(update={
        "active": active, "bench": p0_bench, "discard": discard,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"飞天螳螂": SCYTHER_DOC}
    return e


def test_飞天螳螂_辅助斩_附着备战() -> None:
    """辅助斩：20 伤害 + 弃牌区 1 张基本【草】能量附着于备战宝可梦（目标仅备战）。"""
    discard = (inst(80, energy("草能量", "草")), inst(81, energy("火能量", "火")))
    e = scyther_engine(p0_bench=(in_play(70, basic("备战兽")),), discard=discard)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
    pc1 = e.state.pending_choice
    assert pc1.pool_iids == (80,)  # 火能量被 energy_草 过滤
    e.apply(0, Action(kind="choose", choices=(80,)))
    pc2 = e.state.pending_choice
    assert pc2.pool == "own_bench" and pc2.pool_iids == (70,)  # 战斗场（iid 1）不可选
    e.apply(0, Action(kind="choose", choices=(70,)))
    p0 = e.state.players[0]
    assert [e_.iid for e_ in p0.bench[0].attached_energy] == [80]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_飞天螳螂_辅助斩_弃牌区无草能量_noop_伤害照算() -> None:
    """弃牌区无基本【草】能量：附着效果 no-op（不挂起），攻击伤害照算、回合推进。"""
    e = scyther_engine(p0_bench=(in_play(70, basic("备战兽")),),
                       discard=(inst(81, energy("火能量", "火")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "main" and e.state.current_player == 1
    assert e.state.players[1].active.damage == 20
    assert e.state.players[0].bench[0].attached_energy == ()


# ── 紧急滑板（modify_retreat_cost 道具 holder scope）───────────────────────────


def skate_engine(*, energies: int = 0, damage: int = 0, with_tool: bool = True) -> object:
    """main 阶段：p0 战斗场撤退兽（卡面撤退费 2，HP 70）+ 备战 1 只；道具可调。"""
    state = main_state(p0_active_energies=0)
    active = in_play(1, basic("撤退兽", hp=70, retreat=2), energies).model_copy(
        update={"damage": damage},
    )
    if with_tool:
        active = active.model_copy(update={
            "attached_tool": inst(90, tool_card("紧急滑板")),
        })
    p0 = state.players[0].model_copy(update={
        "active": active, "bench": (in_play(70, basic("占位兽")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"紧急滑板": SKATE_DOC}
    return e


def test_紧急滑板_撤退减1() -> None:
    """撤退费 -1：2 能量付 1 费撤退（枚举层与执行层两触点生效）。"""
    e = skate_engine(energies=2)
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats
    e.apply(0, retreats[0])
    p0 = e.state.players[0]
    assert len(p0.bench[0].attached_energy) == 1  # 只弃 1 张
    assert any(ev.kind == "retreat" and ev.detail["paid"] == 1 for ev in e.events)


def test_紧急滑板_hp30以下全免() -> None:
    """剩余 HP ≤30（70−40=30）：撤退费全免（0 能量可撤退）。"""
    e = skate_engine(energies=0, damage=40)
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats
    e.apply(0, retreats[0])
    assert e.state.players[0].discard == ()
    assert any(ev.kind == "retreat" and ev.detail["paid"] == 0 for ev in e.events)


def test_紧急滑板_hp30以上只减1() -> None:
    """剩余 HP >30（70−10=60）：只 -1 不全免（1 能量付 1 费）。"""
    e = skate_engine(energies=1, damage=10)
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats
    e.apply(0, retreats[0])
    assert len(e.state.players[0].discard) == 1


def test_紧急滑板_离场失效() -> None:
    """道具离场即失效：无滑板时按卡面费用（1 能量 < 2 费不可撤退）。"""
    e = skate_engine(energies=1, with_tool=False)
    assert not [a for a in e.legal_actions(0) if a.kind == "retreat"]


# ── 拉帝亚斯ex（天际线：modify_retreat_cost own_basic_all）─────────────────────


def latias() -> CardDef:
    return CardDef(
        card_id="stub-拉帝亚斯ex", name="拉帝亚斯ex", supertype="pokemon",
        hp=210, stage=0, rule_box="ex", retreat_cost=2,
    )


def latias_engine(*, active_card=None, energies: int = 0,
                  with_latias: bool = True) -> object:
    """main 阶段：p0 战斗场（可调）+ 备战（占位兽 ± 拉帝亚斯ex）。"""
    mon_card = active_card if active_card is not None else basic("撤退兽", retreat=2)
    state = main_state(p0_active_energies=0)
    bench = [in_play(70, basic("占位兽"))]
    if with_latias:
        bench.append(in_play(71, latias()))
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, mon_card, energies), "bench": tuple(bench),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"拉帝亚斯ex": LATIAS_DOC}
    return e


def test_拉帝亚斯ex_天际线_基础全免() -> None:
    """天际线在场：自己【基础】宝可梦撤退费归零（0 能量撤退，不弃能量）。"""
    e = latias_engine(energies=0)
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats
    e.apply(0, retreats[0])
    assert e.state.players[0].discard == ()


def test_拉帝亚斯ex_天际线_进化体不免() -> None:
    """进化体（stage>=1）不免：卡面 1 费、0 能量不可撤退。"""
    evolved = CardDef(card_id="stub-进化兽", name="进化兽", supertype="pokemon",
                      hp=90, stage=1, evolves_from="撤退兽", retreat_cost=1)
    e = latias_engine(active_card=evolved, energies=0)
    assert not [a for a in e.legal_actions(0) if a.kind == "retreat"]


def test_拉帝亚斯ex_天际线_对手不免() -> None:
    """对手不受天际线影响（对手基础宝可梦撤退费按卡面）。"""
    state = main_state(p0_active_energies=0, p1_bench=(in_play(72, basic("对手占位")),))
    p0 = state.players[0].model_copy(update={
        "bench": (in_play(70, basic("占位兽")), in_play(71, latias())),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("小火龙", retreat=2), 1),  # 1 能量 < 卡面 2 费
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1), "current_player": 1}))
    e.card_effects = {"拉帝亚斯ex": LATIAS_DOC}
    assert not [a for a in e.legal_actions(1) if a.kind == "retreat"]


def test_拉帝亚斯ex_天际线_离场失效() -> None:
    """拉帝亚斯ex 不在场 → 撤退费按卡面（0 能量不可撤退）。"""
    e = latias_engine(energies=0, with_latias=False)
    assert not [a for a in e.legal_actions(0) if a.kind == "retreat"]


def latias_attacker() -> CardDef:
    return CardDef(
        card_id="stub-拉帝亚斯ex", name="拉帝亚斯ex", supertype="pokemon",
        hp=210, stage=0, rule_box="ex", retreat_cost=2,
        attacks=(AttackDef(name="无限之刃", cost=("超", "超", "无"), damage=200),),
    )


def test_拉帝亚斯ex_无限之刃_招式锁() -> None:
    """无限之刃：200 伤害 + lock_attack（「下一个自己的回合无法使用招式」）——
    下个自己回合不枚举，再下个自己回合恢复（裁决 2，2026-09-14）。"""
    state = main_state(p1_bench=(in_play(72, basic("对手占位")),))
    active = in_play(1, latias_attacker()).model_copy(update={
        "attached_energy": tuple(inst(9001 + i, energy("超能量", "超")) for i in range(3)),
    })
    p0 = state.players[0].model_copy(update={"active": active})
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("硬兽", hp=500), 1),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"拉帝亚斯ex": LATIAS_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))  # 无限之刃 @turn 2
    assert e.state.players[1].active.damage == 200  # 伤害照算
    assert e.state.players[0].active.attack_locks == ("无限之刃",)
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 3
    assert not [a for a in e.legal_actions(0) if a.kind == "attack"]  # 锁定
    e.apply(0, Action(kind="end_turn"))
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 4
    assert [a for a in e.legal_actions(0) if a.kind == "attack"]  # 恢复可宣言


# ── 超级能量回收（cost discard 2 + recover up-to 4 + 成本排除 + reveal）────────


def super_recovery_engine(*, hand: tuple, discard: tuple) -> object:
    """main 阶段：p0 手牌含超级能量回收（iid 60，物品）+ 自定义手牌/弃牌区。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": (inst(60, item_card("超级能量回收")),) + hand,
        "discard": discard,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"超级能量回收": SUPER_RECOVERY_DOC}
    return e


def test_超级能量回收_弃2能量不可回选() -> None:
    """cost 弃置的 2 张基本能量进弃牌区后不可回选（文本明写「无法选择…」）。"""
    hand = (inst(80, energy("草能量", "草")), inst(81, energy("火能量", "火")))
    discard = (inst(82, energy("水能量", "水")),)
    e = super_recovery_engine(hand=hand, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(80, 81)))  # cost：弃 2 能量
    pc2 = e.state.pending_choice
    assert pc2.pool == "own_discard" and pc2.pool_iids == (82,)  # 80/81 被剔除
    e.apply(0, Action(kind="choose", choices=(82,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [82]
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert reveal.detail["iids"] == [82] and reveal.detail["names"] == ["水能量"]
    assert sorted(c.iid for c in p0.discard) == [60, 80, 81]


def test_超级能量回收_弃非能量正常() -> None:
    """cost 弃置非能量：recover 池含弃牌区既有能量（up-to 4，全选入手）。"""
    hand = (inst(84, item_card("测试物品甲")), inst(85, item_card("测试物品乙")))
    discard = (inst(82, energy("草能量", "草")), inst(86, energy("火能量", "火")))
    e = super_recovery_engine(hand=hand, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(84, 85)))
    pc2 = e.state.pending_choice
    assert pc2.pool_iids == (82, 86)
    e.apply(0, Action(kind="choose", choices=(82, 86)))
    p0 = e.state.players[0]
    assert sorted(c.iid for c in p0.hand) == [82, 86]
    assert sorted(c.iid for c in p0.discard) == [60, 84, 85]


def test_超级能量回收_手牌不足不可使用() -> None:
    """手牌（除本体）<2 张 → 整卡不可使用（「只有…后才可使用」可行性门）。"""
    hand = (inst(80, energy("草能量", "草")),)  # 仅 1 张
    discard = (inst(82, energy("水能量", "水")),)
    e = super_recovery_engine(hand=hand, discard=discard)
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]


def test_超级能量回收_池不足收缩() -> None:
    """弃牌区仅 1 张基本能量（<4）：up-to 收缩，全选入手。"""
    hand = (inst(84, item_card("测试物品甲")), inst(85, item_card("测试物品乙")))
    discard = (inst(82, energy("草能量", "草")),)
    e = super_recovery_engine(hand=hand, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(84, 85)))
    pc2 = e.state.pending_choice
    assert pc2.pool_iids == (82,) and pc2.min_choose == 0 and pc2.max_choose == 4
    e.apply(0, Action(kind="choose", choices=(82,)))
    assert [c.iid for c in e.state.players[0].hand] == [82]
