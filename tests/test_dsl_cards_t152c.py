"""单卡 DSL 测试（task 152c）：伽勒尔 喵喵 + 波克基斯——从 cards/ 真实文件装载。

伽勒尔 喵喵（30thC-080 档，基础钢 70，无特性，J 标 2 印刷等价类）：
「【无】 聚宝功 10——从自己牌库上方抽取1张卡牌。」（damage 10 + draw 1，
draw 缺省 selector=own_deck 牌库顶；牌库空 → 抽完即止不卡）
「【钢】 宝物突进 10×——造成自己手牌张数×10伤害。」（新计数词
own_hand_count（D-152c-2）×10——求值点在伤害节点，发动后手牌变化
不影响本次伤害）

波克基斯（CSV9C-075 档，2阶 140，H 标 3 印刷等价类）：
「特性: 奇迹之吻——只要这只宝可梦在场上，每当对手的战斗宝可梦【昏厥】时，
自己抛掷1次硬币。如果为正面，则多拿取1张奖赏卡。这个效果，无论拥有这个
特性的宝可梦有多少只，都不会叠加。」（task 152c 引擎扩展，D-152c-1：
新事件词 opponent_active_ko（昏厥结算点 _knockout_one 发射入队、链收尾
统一排水；任意来源——招式/效果/指示物/自伤；发射侧按卡名去重不叠加）
+ 新原语 take_extra_prize 1（走 core 拿奖赏路径：不足按剩余拿取、拿完即胜）；
coin_flip → if_flip_heads 节点门控（桌台市/粉碎之锤先例））
「【无】【无】【无】 高速之翼 140」——vanilla 白板，不绑 DSL（库内惯例）。
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    InPlayPokemon,
    SpecialCondition,
)

CARDS_DIR = Path(__file__).parent.parent / "cards"
MEOWTH_DOC = load_card_doc(CARDS_DIR / "伽勒尔 喵喵.yml")
TOGE_DOC = load_card_doc(CARDS_DIR / "波克基斯.yml")

HEADS = next(s for s in range(30) if RandomSource(s).flip_coin())
TAILS = next(s for s in range(30) if not RandomSource(s).flip_coin())


# ── 伽勒尔 喵喵 ──────────────────────────────────────────────────────────────


def meowth(iid: int) -> InPlayPokemon:
    """钢能附着的伽勒尔 喵喵（聚宝功/宝物突进两招式）。"""
    card = CardDef(
        card_id="30thC-080", name="伽勒尔 喵喵", supertype="pokemon",
        hp=70, stage=0, energy_type="钢",
        attacks=(
            AttackDef(name="聚宝功", cost=("无",), damage=10),
            AttackDef(name="宝物突进", cost=("钢",), damage=10),
        ),
        retreat_cost=1,
    )
    steel = CardDef(card_id=f"stub-钢能{iid}", name="钢能", supertype="energy",
                    energy_type="钢", is_basic_energy=True)
    return InPlayPokemon(stack=(inst(iid, card),),
                         attached_energy=(inst(9000 + iid, steel),))


def meow_game(*, p0_hand: tuple | None = None, p0_deck: tuple | None = None):
    """main 阶段：p0 战斗场 = 喵喵；p1 战斗场 = 厚盾（hp 300，吃不伤）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": meowth(1),
        "hand": p0_hand if p0_hand is not None else state.players[0].hand,
        "deck": p0_deck if p0_deck is not None else state.players[0].deck,
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("厚盾", hp=300), 1),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"伽勒尔 喵喵": MEOWTH_DOC}
    return e


def test_伽勒尔喵喵_挂载等价类() -> None:
    """J 标 2 印刷同文本等价类全收（闸 1 --db 已核归一化 text_raw 一致 + 赛制合法）。"""
    assert MEOWTH_DOC.card.card_ids == ("30thC-080", "30thC-117")


def test_伽勒尔喵喵_聚宝功_伤害10并抽1() -> None:
    """聚宝功：对手受 10 伤害 + 牌库顶 1 张入手（默认手牌 2 张 → 3 张）。"""
    e = meow_game()
    hand_before = len(e.state.players[0].hand)
    deck_before = len(e.state.players[0].deck)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 10
    p0 = e.state.players[0]
    assert len(p0.hand) == hand_before + 1
    assert len(p0.deck) == deck_before - 1


def test_伽勒尔喵喵_聚宝功_牌库空不卡() -> None:
    """牌库空 → 抽完即止：伤害照算、不抽牌、效果链正常收尾。"""
    e = meow_game(p0_deck=())
    hand_before = tuple(e.state.players[0].hand)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 10
    assert e.state.players[0].hand == hand_before
    assert e.state.players[0].deck == ()


def test_伽勒尔喵喵_宝物突进_零手牌伤害0() -> None:
    """手牌 N=0 → 0×10 = 0 伤害，招式仍可宣言结算。"""
    e = meow_game(p0_hand=())
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 0


def test_伽勒尔喵喵_宝物突进_三手牌伤害30() -> None:
    """手牌 N=3 → 3×10 = 30 伤害（求值点锁定，发动不消耗手牌）。"""
    extra = tuple(inst(60 + i, basic("填充")) for i in range(3))
    e = meow_game(p0_hand=extra)
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 30
    assert len(e.state.players[0].hand) == 3  # 手牌未被消耗


# ── 波克基斯 ────────────────────────────────────────────────────────────────


def togekiss(iid: int) -> InPlayPokemon:
    card = CardDef(
        card_id="CSV9C-075", name="波克基斯", supertype="pokemon",
        hp=140, stage=2, evolves_from="波克基古", energy_type="无",
        attacks=(AttackDef(name="高速之翼", cost=("无", "无", "无"), damage=140),),
        retreat_cost=1,
    )
    return InPlayPokemon(stack=(inst(iid, card),))


def poisoned(iid: int, name: str = "毒靶", *, hp: int = 30) -> InPlayPokemon:
    """ lethal 毒伤 stub：hp-10 伤害指示物 + 中毒（检查阶段 +10 即昏厥）。"""
    mon = in_play(iid, basic(name, hp=hp), 1)
    return mon.model_copy(update={
        "damage": hp - 10,
        "conditions": frozenset({SpecialCondition.POISONED}),
    })


def toge_game(*, toge_count: int = 1, p1_active=None, p1_bench: tuple = (),
              p0_prizes: tuple | None = None, current: int = 0):
    """p0 打手（40 伤害白板）+ p0 备战 toge_count 只波克基斯；p1 指定战场。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, basic("打手", hp=90, damage=40, cost=1), 1),
        "bench": tuple(togekiss(5 + i) for i in range(toge_count)),
        "prizes": p0_prizes if p0_prizes is not None else state.players[0].prizes,
    })
    p1 = state.players[1].model_copy(update={
        "active": p1_active if p1_active is not None
        else in_play(2, basic("靶兽", hp=30), 1),
        "bench": p1_bench,
    })
    e = engine_at(state.model_copy(update={
        "players": (p0, p1), "current_player": current,
    }))
    e.card_effects = {"波克基斯": TOGE_DOC}
    return e


def flip_events(e) -> list:
    """掷币明细落 effect_primitive 事件（coin_flip 原语 docstring 口径）。"""
    return [ev for ev in e.events if ev.kind == "effect_primitive"
            and ev.detail.get("action") == "coin_flip"]


def miracle_triggers(e) -> list:
    return [ev for ev in e.events if ev.kind == "trigger_on_event"
            and ev.detail.get("event") == "opponent_active_ko"]


def test_波克基斯_挂载等价类() -> None:
    """H 标 3 印刷同文本等价类全收（闸 1 --db 已核归一化 text_raw 一致 + 赛制合法）。"""
    assert TOGE_DOC.card.card_ids == ("CSV9C-075", "SVP-367", "SVP-481")


def test_波克基斯_奇迹之吻_正面多拿1奖() -> None:
    """己方攻击致对手战斗场昏厥：正面 = 正常奖赏 1 + 额外 1（总 2 张，剩 4）。"""
    e = toge_game(p1_bench=(in_play(9, basic("替补"), 0),))  # 备战非空：不判负
    e.rng = RandomSource(HEADS)
    e.apply(0, Action(kind="attack", attack_index=0))
    p0 = e.state.players[0]
    assert len(p0.prizes) == 4
    assert len(flip_events(e)) == 1
    assert len(miracle_triggers(e)) == 1
    assert len([ev for ev in e.events if ev.kind == "take_prize"]) == 2
    assert e.state.phase == "promote"  # 被昏厥方换上（攻击已消耗其回合）


def test_波克基斯_奇迹之吻_反面不多拿() -> None:
    """反面 = 只拿正常奖赏 1 张（剩 5），无额外 take_prize。"""
    e = toge_game(p1_bench=(in_play(9, basic("替补"), 0),))
    e.rng = RandomSource(TAILS)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert len(e.state.players[0].prizes) == 5
    assert len(flip_events(e)) == 1
    assert len([ev for ev in e.events if ev.kind == "take_prize"]) == 1


def test_波克基斯_奇迹之吻_指示物致昏厥也触发() -> None:
    """对手战斗场被检查阶段中毒指示物致昏厥：特性同样触发（卡面无来源限定）。

    p1 回合结束 → 宝可梦检查 → p1 战斗场毒昏（active_ko）→ p0 拿 1 奖 +
    奇迹之吻正面再拿 1（剩 4）；检查拦截回本函数、换上后开 p0 回合。
    """
    e = toge_game(p1_active=poisoned(2), p1_bench=(in_play(9, basic("替补"), 0),),
                  current=1)
    e.rng = RandomSource(HEADS)
    e.apply(1, Action(kind="end_turn"))
    assert len(e.state.players[0].prizes) == 4
    assert len(flip_events(e)) == 1
    assert len(miracle_triggers(e)) == 1
    assert e.state.phase == "promote"


def test_波克基斯_奇迹之吻_两只在场只掷一次() -> None:
    """不叠加：p0 备战 2 只波克基斯 → 只入队/触发 1 次（掷币 1 次、额外奖至多 1）。"""
    e = toge_game(toge_count=2, p1_bench=(in_play(9, basic("替补"), 0),))
    e.rng = RandomSource(HEADS)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert len(e.state.players[0].prizes) == 4  # 1 正常 + 1 额外（非 +2）
    assert len(flip_events(e)) == 1
    assert len(miracle_triggers(e)) == 1


def test_波克基斯_奇迹之吻_拿完即胜不崩() -> None:
    """额外奖赏拿空奖赏堆：take_extra_prize 触发胜利条件①终局（winner=p0）。"""
    prizes = tuple(inst(200 + i, basic("赏")) for i in range(2))
    e = toge_game(p1_bench=(in_play(9, basic("替补"), 0),), p0_prizes=prizes)
    e.rng = RandomSource(HEADS)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "game_over"
    assert e.state.winner == 0
    assert len([ev for ev in e.events if ev.kind == "take_prize"]) == 2


def test_波克基斯_奇迹之吻_备战昏厥不触发() -> None:
    """备战区昏厥（非战斗场）→ active_ko 门拦截：不掷币、不多拿奖。"""
    e = toge_game(p1_bench=(poisoned(8, "毒备"),), current=1)
    e.rng = RandomSource(HEADS)  # 若误触发会被消耗——断言事件数兜住
    e.apply(1, Action(kind="end_turn"))
    assert len(e.state.players[0].prizes) == 5  # 仅正常奖赏 1 张
    assert flip_events(e) == []
    assert miracle_triggers(e) == []
    assert e.state.phase == "main"  # 检查完毕直接开 p0 回合（无换上）
    assert e.state.current_player == 0


def test_波克基斯_高速之翼_白板140() -> None:
    """高速之翼 140 vanilla：白板伤害路径结算，不绑 DSL 效果。"""
    e = toge_game()
    wing = togekiss(1).model_copy(update={
        "attached_energy": tuple(
            inst(9100 + j, CardDef(card_id=f"stub-无{j}", name="无", supertype="energy",
                                   energy_type=None, is_basic_energy=True))
            for j in range(3)
        ),
    })
    e.state = e.state.model_copy(update={"players": (
        e.state.players[0].model_copy(update={"active": wing}),
        e.state.players[1].model_copy(update={
            "active": in_play(2, basic("厚盾", hp=300), 1),
        }),
    )})
    e.rng = RandomSource(HEADS)  # 不应有任何掷币消费
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 140
    assert flip_events(e) == []
    assert miracle_triggers(e) == []
