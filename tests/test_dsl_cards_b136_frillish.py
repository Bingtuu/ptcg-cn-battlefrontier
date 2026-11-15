"""单卡 DSL 测试（task 136 批次 1/5）：轻飘飘——从 cards/ 真实文件装载。

轻飘飘（CSV10.6C-041 等价类 2 印刷，I 标，基础，超，HP80）：
- 招式 大海之影（【超】 20）：damage 20 + lock_play item（「在下一个对手的回合，
  对手无法从手牌使出物品」；含羞苞 痒痒花粉先例，task 029 D-029-3）。
"""

from pathlib import Path

from helpers import engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

FRILLISH_DOC = load_card_doc(CARDS_DIR / "轻飘飘.yml")

ITEM_DOC = parse_card_doc("""
card:
  name_group: 测试物品
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")

SUPPORTER_DOC = parse_card_doc("""
card:
  name_group: 测试支援者
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 2}
""")


def frillish() -> CardDef:
    return CardDef(card_id="stub-轻飘飘", name="轻飘飘", supertype="pokemon",
                   hp=80, stage=0, energy_type="超",
                   attacks=(AttackDef(name="大海之影", cost=("超",), damage=None),),
                   retreat_cost=1)


def psy_energy(iid: int) -> CardDef:
    return CardDef(card_id=f"stub-超{iid}", name="基本超能量", supertype="energy",
                   energy_type="超", is_basic_energy=True)


def trainer(name: str, subtype: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype=subtype)


def frillish_engine() -> object:
    """main 阶段：p0 轻飘飘攻击位（iid 1，附着 1 超能），p1 手牌物品+支援者。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, frillish()).model_copy(update={
            "attached_energy": (inst(9001, psy_energy(1)),),
        }),
    })
    p1 = state.players[1].model_copy(update={
        "hand": (inst(60, trainer("测试物品", "物品")),
                 inst(61, trainer("测试支援者", "支援者"))),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"轻飘飘": FRILLISH_DOC, "测试物品": ITEM_DOC,
                      "测试支援者": SUPPORTER_DOC}
    return e


def play_trainer_iids(e, player: int) -> set:
    return {a.iid for a in e.legal_actions(player)
            if a.kind == "play_trainer"}


def test_轻飘飘_挂载同文本等价类() -> None:
    """I 标 2 印刷（CSV10.6C-041/124）同文本等价类全收。"""
    assert FRILLISH_DOC.card.card_ids == ("CSV10.6C-041", "CSV10.6C-124")


def test_轻飘飘_大海之影_伤害20加对手物品锁() -> None:
    """攻击后：对手战斗场 20 伤害 + 物品锁标记；对手下回合物品不枚举、
    支援者照常。"""
    e = frillish_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
    assert e.state.players[1].item_lock_mark == (2, 0)  # (施加时 turn, 施加方)
    assert e.state.phase == "main" and e.state.current_player == 1
    assert 60 not in play_trainer_iids(e, 1)  # 物品被锁
    assert 61 in play_trainer_iids(e, 1)      # 支援者照常


def test_轻飘飘_大海之影_被锁回合结束解除() -> None:
    """锁作用于玩家侧回合标记：对手被锁回合结束即解除。"""
    e = frillish_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert 60 not in play_trainer_iids(e, 1)
    e.apply(1, Action(kind="end_turn"))
    assert e.state.players[1].item_lock_mark is None
    e.apply(0, Action(kind="end_turn"))
    assert 60 in play_trainer_iids(e, 1)
