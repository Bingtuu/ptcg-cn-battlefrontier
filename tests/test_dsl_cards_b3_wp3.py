"""单卡 DSL 测试（task 026 WP3）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批卡（recover 去向扩展 + top_n 检视 + attach 多目标 + own_evolve_from_hand + reveal
随之解锁）：
- 多龙奇（H 标 CSV8C-158 等价类）：侦察指令——ability_manual once_per_turn +
  search_deck top_n=2 检视，选 1 入手、剩余放回牌库下方不洗牌。
- 夜巡灵（H 标 CSV8C-081 等价类）：渡魂——on_attack + recover bench up-to 3
  （name:夜巡灵 过滤器）。
- 奥琳博士的气魄（G 标 CSV6C-121 等价类）：on_play + attach 多目标各附1
  （trait:古代）+ draw 3。
- 猫头夜鹰（H 标 CSV9C-155 等价类）：寻找宝石——trigger_on_event own_evolve_from_hand
  + condition own_tera_in_play + 检索训练家 up-to 2 + reveal + 洗牌。
- 水莲的照顾（H 标 CSV7C-193 等价类）：on_play + recover hand up-to 3
  （pokemon_no_rule_or_basic_energy）+ reveal。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import ExecutionContext, run_effect
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

DRAKLOAK_DOC = load_card_doc(CARDS_DIR / "多龙奇.yml")
DUSKULL_DOC = load_card_doc(CARDS_DIR / "夜巡灵.yml")
ORIM_DOC = load_card_doc(CARDS_DIR / "奥琳博士的气魄.yml")
NOCTOWL_DOC = load_card_doc(CARDS_DIR / "猫头夜鹰.yml")
LANA_DOC = load_card_doc(CARDS_DIR / "水莲的照顾.yml")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


# ── 多龙奇（侦察指令：top_n 检视）────────────────────────────────────────────


def drakloak() -> CardDef:
    return CardDef(
        card_id="stub-多龙奇", name="多龙奇", supertype="pokemon",
        hp=90, stage=1, evolves_from="多龙梅西亚",
        attacks=(AttackDef(name="龙之头击", cost=("火", "超"), damage=70),),
        retreat_cost=1,
    )


def drakloak_engine(deck) -> object:
    """main 阶段：p0 备战区多龙奇（iid 70），牌库自定义。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "bench": (in_play(70, drakloak()),), "deck": deck,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"多龙奇": DRAKLOAK_DOC}
    return e


def test_多龙奇_侦察指令_正常检视() -> None:
    """检视牌库顶 2 张为选择池，选 1 入手、剩余按原序放牌库下方、不洗牌。"""
    deck = tuple(inst(100 + i, basic(f"库{chr(19968 + i)}")) for i in range(4))
    e = drakloak_engine(deck)
    e.apply(0, Action(kind="use_ability", iid=70))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.pool_iids == (100, 101) and pc.min_choose == 0 and pc.max_choose == 1
    e.apply(0, Action(kind="choose", choices=(101,)))
    p0 = e.state.players[0]
    assert 101 in [c.iid for c in p0.hand]
    assert [c.iid for c in p0.deck] == [102, 103, 100]  # 剩余库底、不洗牌
    assert e.state.phase == "main" and e.state.current_player == 0
    assert any(ev.kind == "effect_observe" and ev.detail["anchor"] == "key_search"
               for ev in e.events)


def test_多龙奇_侦察指令_限次() -> None:
    """once_per_turn：发动后本回合不再枚举该特性。"""
    e = drakloak_engine(tuple(inst(100 + i, basic("妙蛙种子")) for i in range(4)))
    assert Action(kind="use_ability", iid=70) in e.legal_actions(0)
    e.apply(0, Action(kind="use_ability", iid=70))
    e.apply(0, Action(kind="choose", choices=(100,)))
    assert not [a for a in e.legal_actions(0)
                if a.kind == "use_ability" and a.iid == 70]


def test_多龙奇_侦察指令_牌库不足() -> None:
    """牌库仅 1 张 → 检视 1 张尽力而为；牌库空 → 特性不枚举（可行性门）。"""
    e = drakloak_engine((inst(100, basic("独苗")),))
    e.apply(0, Action(kind="use_ability", iid=70))
    assert e.state.pending_choice.pool_iids == (100,)
    e.apply(0, Action(kind="choose", choices=(100,)))
    assert 100 in [c.iid for c in e.state.players[0].hand]
    assert [c.iid for c in e.state.players[0].deck] == []
    e2 = drakloak_engine(())
    assert not [a for a in e2.legal_actions(0) if a.kind == "use_ability"]


# ── 夜巡灵（渡魂：recover bench up-to 3）─────────────────────────────────────


def duskull() -> CardDef:
    return CardDef(
        card_id="stub-夜巡灵", name="夜巡灵", supertype="pokemon",
        hp=60, stage=0,
        attacks=(
            AttackDef(name="渡魂", cost=("超",), damage=None),
            AttackDef(name="喃喃自语", cost=("超", "超"), damage=30),
        ),
        retreat_cost=1,
    )


def duskull_engine(*, discard: tuple = (), p0_bench: tuple = ()) -> object:
    """main 阶段：p0 战斗场夜巡灵（iid 1，附 1 超能量满足渡魂成本）。"""
    state = main_state()
    active = in_play(1, duskull()).model_copy(update={
        "attached_energy": (inst(9001, energy("超能量", "超")),),
    })
    p0 = state.players[0].model_copy(update={
        "active": active, "bench": p0_bench, "discard": discard,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"夜巡灵": DUSKULL_DOC}
    return e


def test_夜巡灵_渡魂_3只全回备战区() -> None:
    """渡魂（招式）：弃牌区 3 只夜巡灵全选回备战区（InPlayPokemon + 登场登记），
    其他卡被 name 过滤器排除；攻击结算完回合推进给对手。"""
    discard = (inst(80, duskull()), inst(81, duskull()), inst(82, duskull()),
               inst(83, basic("喵喵")))
    e = duskull_engine(discard=discard)
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert [a.attack_index for a in attacks] == [0]  # 渡魂（喃喃自语能量不满足）
    e.apply(0, attacks[0])
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.pool_iids == (80, 81, 82) and pc.min_choose == 0 and pc.max_choose == 3
    e.apply(0, Action(kind="choose", choices=(80, 81, 82)))
    p0 = e.state.players[0]
    assert [b.current.iid for b in p0.bench] == [80, 81, 82]
    assert {80, 81, 82} <= p0.entered_play_this_turn
    assert [c.iid for c in p0.discard] == [83]
    # 攻击后回合正常推进：对手回合开始（抽牌 + 主阶段）
    assert e.state.phase == "main" and e.state.current_player == 1
    assert any(ev.kind == "draw" and ev.player == 1 for ev in e.events)


def test_夜巡灵_渡魂_弃牌区收缩() -> None:
    """弃牌区仅 1 只夜巡灵：池收缩为 1（up-to，可选 0 或 1）。"""
    e = duskull_engine(discard=(inst(80, duskull()),))
    e.apply(0, Action(kind="attack", attack_index=0))
    picks = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert picks == [(), (80,)]
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert [b.current.iid for b in e.state.players[0].bench] == [80]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_夜巡灵_渡魂_备战满截断() -> None:
    """备战区 4 只在场（容量 1）：回收池截断为 1 只。"""
    bench4 = tuple(in_play(70 + i, basic("占位兽")) for i in range(4))
    discard = (inst(80, duskull()), inst(81, duskull()))
    e = duskull_engine(discard=discard, p0_bench=bench4)
    e.apply(0, Action(kind="attack", attack_index=0))
    pc = e.state.pending_choice
    assert pc.pool_iids == (80,) and pc.max_choose == 1
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert len(e.state.players[0].bench) == 5
    assert [c.iid for c in e.state.players[0].discard] == [81]


# ── 奥琳博士的气魄（attach 多目标各附1 + draw 3）─────────────────────────────


def ancient(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=90, stage=0, labels=("古代",))


def orim_engine(*, p0_bench: tuple = (), discard: tuple = ()) -> object:
    """main 阶段：p0 手牌仅奥琳博士的气魄（iid 60，支援者）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": (inst(60, CardDef(card_id="stub-奥琳博士的气魄", name="奥琳博士的气魄",
                                  supertype="trainer", trainer_subtype="支援者")),),
        "bench": p0_bench, "discard": discard,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"奥琳博士的气魄": ORIM_DOC}
    return e


def test_奥琳博士的气魄_2目标2能量配对_再抽3() -> None:
    """2 只古代 + 2 张弃牌区基本能量 → FIFO 各附 1；随后无条件抽 3 张。"""
    bench = (in_play(70, ancient("古代兽甲")), in_play(71, ancient("古代兽乙")))
    discard = (inst(80, energy()), inst(81, energy()))
    e = orim_engine(p0_bench=bench, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(80, 81)))  # 段1：能量
    e.apply(0, Action(kind="choose", choices=(70, 71)))  # 段2：目标
    p0 = e.state.players[0]
    assert [e_.iid for e_ in p0.bench[0].attached_energy] == [80]
    assert [e_.iid for e_ in p0.bench[1].attached_energy] == [81]
    assert [c.iid for c in p0.hand] == [100, 101, 102]  # 然后抽 3 张
    assert [c.iid for c in p0.discard] == [60]  # 本体进弃牌区
    assert e.state.phase == "main"


def test_奥琳博士的气魄_目标不足收缩() -> None:
    """1 只古代 + 2 张能量 → 收缩 1 对，未配对能量留弃牌区；仍抽 3 张。"""
    bench = (in_play(70, ancient("古代兽甲")), in_play(71, basic("喵喵")))
    discard = (inst(80, energy()), inst(81, energy()))
    e = orim_engine(p0_bench=bench, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(80, 81)))
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert picks == [(70,)]  # 喵喵非古代不进池
    e.apply(0, Action(kind="choose", choices=(70,)))
    p0 = e.state.players[0]
    assert [e_.iid for e_ in p0.bench[0].attached_energy] == [80]
    assert [c.iid for c in p0.discard] == [81, 60]
    assert [c.iid for c in p0.hand] == [100, 101, 102]


def test_奥琳博士的气魄_无合法目标仍抽3() -> None:
    """场上无古代宝可梦：附着段 no-op（能量留弃牌区），抽 3 张无条件执行。"""
    discard = (inst(80, energy()), inst(81, energy()))
    e = orim_engine(discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(80, 81)))
    p0 = e.state.players[0]
    assert p0.active.attached_energy and all(
        e_.iid != 80 for e_ in p0.active.attached_energy
    )
    assert [c.iid for c in p0.discard] == [80, 81, 60]
    assert [c.iid for c in p0.hand] == [100, 101, 102]
    assert e.state.phase == "main"


# ── 猫头夜鹰（寻找宝石：own_evolve_from_hand + reveal）───────────────────────


def hoothoot() -> CardDef:
    return CardDef(card_id="stub-咕咕", name="咕咕", supertype="pokemon",
                   hp=70, stage=0)


def noctowl() -> CardDef:
    return CardDef(
        card_id="stub-猫头夜鹰", name="猫头夜鹰", supertype="pokemon",
        hp=100, stage=1, evolves_from="咕咕",
        attacks=(AttackDef(name="高速之翼", cost=("无", "无"), damage=60),),
        retreat_cost=1,
    )


def tera_mon() -> CardDef:
    return CardDef(card_id="stub-太晶兽", name="太晶兽", supertype="pokemon",
                   hp=120, stage=0, is_tera=True)


def noctowl_engine(*, active_card, deck) -> object:
    """main 阶段（turn=2）：p0 备战区咕咕（iid 70），手牌含猫头夜鹰（iid 60）。"""
    state = main_state(p0_extra_hand=(inst(60, noctowl()),))
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active_card), "bench": (in_play(70, hoothoot()),),
        "deck": deck,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"猫头夜鹰": NOCTOWL_DOC}
    return e


def test_猫头夜鹰_寻找宝石_进化触发() -> None:
    """从手牌进化 + 场上有太晶 → 自动发动：检索 ≤2 训练家入手 → reveal 事件落流 → 洗牌。"""
    deck = (inst(110, item_card("测试物品甲")), inst(111, item_card("测试物品乙"))) + tuple(
        inst(100 + i, basic("妙蛙种子")) for i in range(8)
    )
    e = noctowl_engine(active_card=tera_mon(), deck=deck)
    e.apply(0, Action(kind="evolve", iid=60, target_iid=70))
    assert e.state.phase == "choice"
    trig = next(ev for ev in e.events if ev.kind == "trigger_on_event")
    assert trig.detail["event"] == "own_evolve_from_hand" and trig.detail["iid"] == 60
    e.apply(0, Action(kind="choose", choices=(110, 111)))
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert reveal.detail["iids"] == [110, 111]
    assert reveal.detail["names"] == ["测试物品甲", "测试物品乙"]
    assert any(ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"
               for ev in e.events)
    p0 = e.state.players[0]
    assert p0.bench[0].current.iid == 60
    assert {110, 111} <= {c.iid for c in p0.hand}
    assert e.state.phase == "main" and e.state.current_player == 0


def test_猫头夜鹰_寻找宝石_无太晶不触发() -> None:
    """场上无太晶宝可梦：condition 不满足 → 进化照常、特性不发动（无 reveal/检索）。"""
    deck = tuple(inst(100 + i, basic("妙蛙种子")) for i in range(10))
    e = noctowl_engine(active_card=basic("妙蛙种子"), deck=deck)
    e.apply(0, Action(kind="evolve", iid=60, target_iid=70))
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
    assert not [ev for ev in e.events if ev.kind == "reveal"]
    assert e.state.players[0].bench[0].current.iid == 60  # 进化本身生效


# ── 水莲的照顾（recover hand up-to 3 + reveal）───────────────────────────────


def lana_engine(*, discard: tuple = ()) -> object:
    """main 阶段：p0 手牌仅水莲的照顾（iid 60，支援者）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": (inst(60, CardDef(card_id="stub-水莲的照顾", name="水莲的照顾",
                                  supertype="trainer", trainer_subtype="支援者")),),
        "discard": discard,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"水莲的照顾": LANA_DOC}
    return e


def rule_box_mon(name: str = "规矩兽ex") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=200, stage=0, rule_box="ex")


def test_水莲的照顾_选3_reveal落流() -> None:
    """宝可梦（除规则盒）+ 基本能量合计最多 3 张入手并给对手看过（reveal 事件）。"""
    discard = (inst(80, basic("拉鲁拉丝")), inst(81, energy()),
               inst(84, basic("小拉达")), inst(82, rule_box_mon()),
               inst(83, item_card("高级球")))
    e = lana_engine(discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.min_choose == 0 and pc.max_choose == 3
    assert pc.pool_iids == (80, 81, 84)  # 规则盒宝可梦/训练家不进池（过滤器负例）
    e.apply(0, Action(kind="choose", choices=(80, 81, 84)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [80, 81, 84]
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert reveal.detail["iids"] == [80, 81, 84]
    assert reveal.detail["names"] == ["拉鲁拉丝", "基本能量", "小拉达"]
    assert [c.iid for c in p0.discard] == [82, 83, 60]
    assert e.state.phase == "main"


def test_水莲的照顾_选0合法() -> None:
    """up-to：选 0 张合法（「最多3张」），reveal 事件 iids 为空。"""
    e = lana_engine(discard=(inst(80, basic("拉鲁拉丝")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    picks = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert picks == [(), (80,)]
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert p0.hand == ()
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert reveal.detail["iids"] == []
    assert e.state.phase == "main"


def test_水莲的照顾_池空() -> None:
    """弃牌区无合法目标（全是规则盒宝可梦/训练家）：可行性门拦截枚举；
    原语层 no-op 不挂起（直接跑效果验证）。"""
    discard = (inst(82, rule_box_mon()), inst(83, item_card("高级球")))
    e = lana_engine(discard=discard)
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]
    ctx = ExecutionContext(engine=e, player=0, source=inst(60, e.state.players[0].hand[0].card),
                           effect_id="test", trigger="on_play")
    assert run_effect(ctx, LANA_DOC.effects[0]) is None  # no-op 不挂起
    prim = next(ev for ev in e.events
                if ev.kind == "effect_primitive"
                and ev.detail["action"] == "recover_from_discard")
    assert prim.detail["result"]["found"] == 0
