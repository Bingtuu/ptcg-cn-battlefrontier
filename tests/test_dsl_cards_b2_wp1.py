"""单卡 DSL 测试（task 026 WP1）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批卡（filters/conditions 高频解锁项随之解锁 + 老大的指令顺带落地）：
- 老大的指令：gust 无门控版（switch opponent_bench，反击捕捉器同机制减 condition）。
- 尖钉镇道馆：stadium_grant 检索「玛俐的宝可梦」入手（owner_pokemon:<名> 过滤器）。
- 赫普的古月鸟：随性喷吐 condition opponent_prizes_in:[4,3]——不满足则招式失败
  （不结算伤害/效果，回合照常结束；on_attack condition 引擎钩子，task 026 WP1）。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef, CardInstance

CARDS_DIR = Path(__file__).parent.parent / "cards"

BOSS_DOC = load_card_doc(CARDS_DIR / "老大的指令.yml")
SPIKEMUTH_DOC = load_card_doc(CARDS_DIR / "尖钉镇道馆.yml")
CRAMORANT_DOC = load_card_doc(CARDS_DIR / "赫普的古月鸟.yml")


def supporter(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="支援者")


# ── 老大的指令 ───────────────────────────────────────────────────────────


def boss_engine(p1_bench: tuple) -> object:
    """main 阶段、p0 手牌含老大的指令（iid 60）、对手备战区可调。"""
    state = main_state(p0_extra_hand=(inst(60, supporter("老大的指令")),), p1_bench=p1_bench)
    engine = engine_at(state)
    engine.card_effects = {"老大的指令": BOSS_DOC}
    return engine


def test_老大的指令_full_flow() -> None:
    """全链路：挂起选对手 1 只备战 → 与战斗宝可梦互换 → 本体进弃牌区。"""
    bench = (in_play(80, basic("小拉达")), in_play(81, basic("喵喵")))
    e = boss_engine(bench)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert sorted(a.choices for a in choices) == [(80,), (81,)]  # 强制选 1（无空集）
    e.apply(0, next(a for a in choices if a.choices == (81,)))
    p1 = e.state.players[1]
    assert e.state.phase == "main"
    assert p1.active.current.iid == 81  # 喵喵被拉上战斗场
    assert [m.current.iid for m in p1.bench] == [80, 2]  # 原战斗小火龙回备战
    assert [c.iid for c in e.state.players[0].discard] == [60]
    assert e.state.players[0].supporter_played_this_turn


def test_老大的指令_对手无备战不可用() -> None:
    """可行性门：对手无备战宝可梦 → 无合法落点不枚举（无效果不可使用）。"""
    e = boss_engine(())
    plays = [a for a in e.legal_actions(0) if a.kind == "play_trainer"]
    assert plays == []


# ── 尖钉镇道馆 ───────────────────────────────────────────────────────────


def marnie_pokemon(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=70, stage=0, owner="玛俐")


def spikemuth_engine(deck: tuple) -> object:
    """main 阶段、场上竞技场为尖钉镇道馆（p0 放置）、p0 牌库为指定构成。"""
    state = main_state()
    stadium = inst(70, CardDef(
        card_id="stub-尖钉镇道馆", name="尖钉镇道馆", supertype="trainer",
        trainer_subtype="竞技场",
    ))
    state = state.model_copy(update={"stadium": stadium, "stadium_owner": 0})
    p0 = state.players[0].model_copy(update={"deck": deck})
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"尖钉镇道馆": SPIKEMUTH_DOC}
    return engine


def spikemuth_deck() -> tuple:
    return (
        inst(100, marnie_pokemon("玛俐的捣蛋小妖")),
        inst(101, marnie_pokemon("玛俐的莫鲁贝可")),
        inst(102, basic("小拉达")),          # 非玛俐宝可梦
        inst(103, energy()),                  # 能量
        inst(104, supporter("老大的指令")),   # 训练家
    )


def test_尖钉镇道馆_full_flow() -> None:
    """全链路：use_stadium → 检索「玛俐的宝可梦」1 张入手 → 洗牌；每回合限 1 次。"""
    e = spikemuth_engine(spikemuth_deck())
    e.apply(0, Action(kind="use_stadium"))
    assert e.state.phase == "choice"
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert sorted(a.choices for a in choices) == [(), (100,), (101,)]  # up-to（可以不找）
    e.apply(0, next(a for a in choices if a.choices == (100,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert [c.iid for c in p0.hand] == [50, 51, 100]
    assert len(p0.deck) == 4  # 取走 1 张且已洗牌
    shuffles = [ev for ev in e.events
                if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
    # 「每次在自己的回合有1次机会」：本回合不可再次发动
    assert not [a for a in e.legal_actions(0) if a.kind == "use_stadium"]


def test_尖钉镇道馆_filters() -> None:
    """负例：非「玛俐的宝可梦」（无 owner 宝可梦/能量/训练家）不进检索池。"""
    e = spikemuth_engine(spikemuth_deck())
    e.apply(0, Action(kind="use_stadium"))
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {100, 101}


# ── 赫普的古月鸟 ─────────────────────────────────────────────────────────


def cramorant() -> CardDef:
    from battlefrontier.engine.state import AttackDef

    return CardDef(
        card_id="stub-赫普的古月鸟", name="赫普的古月鸟", supertype="pokemon",
        hp=110, stage=0,
        attacks=(AttackDef(name="随性喷吐", cost=("无",), damage=120),),
    )


def cramorant_engine(p1_prizes: int) -> object:
    """main 阶段、p0 战斗场为赫普的古月鸟（iid 1，已附 1 能量）、对手奖赏数可调。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, cramorant(), 1)})
    p1 = state.players[1].model_copy(update={
        # 高 HP 桩（200）：120 伤害不昏厥，直接断言伤害落点
        "active": in_play(2, basic("卡比兽", hp=200), 1),
        "prizes": tuple(CardInstance(iid=400 + i, card=basic("小火龙")) for i in range(p1_prizes)),
    })
    engine = engine_at(state.model_copy(update={"players": (p0, p1)}))
    engine.card_effects = {"赫普的古月鸟": CRAMORANT_DOC}
    return engine


def test_赫普的古月鸟_奖赏4张_正常结算() -> None:
    """对手剩余奖赏 4 张（在 [4,3] 内）：随性喷吐 120 伤害，回合移交。"""
    e = cramorant_engine(4)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 120
    assert e.state.current_player == 1


def test_赫普的古月鸟_奖赏3张_正常结算() -> None:
    e = cramorant_engine(3)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 120


def test_赫普的古月鸟_奖赏5张_招式失败() -> None:
    """对手剩余奖赏 5 张（不在 [4,3]）：招式失败——无伤害无效果，回合照常结束。"""
    e = cramorant_engine(5)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0
    assert e.state.current_player == 1  # 攻击已消耗，回合移交
    failed = [ev for ev in e.events if ev.kind == "attack" and ev.detail.get("failed")]
    assert len(failed) == 1 and failed[0].detail["attack"] == "随性喷吐"
