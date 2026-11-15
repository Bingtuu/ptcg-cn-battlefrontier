"""单卡 DSL 测试（task 136 批次 2/5）：胖嘟嘟ex——从 cards/ 真实文件装载。

胖嘟嘟ex（CSV10.6C-042 等价类 3 印刷，I 标，1阶，超，HP270，ex）：
- 特性 海之咒术：passive_static lock_play 广义门类（task 136 引擎扩展 D-136-1）
  category=item + category=tool，condition holder_is_active（「只要这只宝可梦在
  战斗场上」；退到备战区即解锁）。
- 招式 力量压制（【超】【无】 80+）：基准 80；附着能量 ≥ 费用 2+2=4 追加 80
  （节点条件 if_attached_energy_ge:4，D-136-2）。
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef, InPlayPokemon

CARDS_DIR = Path(__file__).parent.parent / "cards"

JELLICENT_DOC = load_card_doc(CARDS_DIR / "胖嘟嘟ex.yml")

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


def jellicent() -> CardDef:
    return CardDef(card_id="stub-胖嘟嘟ex", name="胖嘟嘟ex", supertype="pokemon",
                   hp=270, stage=1, energy_type="超", has_ability=True,
                   rule_box="ex",
                   attacks=(AttackDef(name="力量压制", cost=("超", "无"), damage=80),),
                   retreat_cost=2)


def any_energy(iid: int) -> CardDef:
    return CardDef(card_id=f"stub-能{iid}", name="基本超能量", supertype="energy",
                   energy_type="超", is_basic_energy=True)


def trainer(name: str, subtype: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype=subtype)


def lock_engine(*, on_bench: bool) -> object:
    """p1 场上胖嘟嘟ex（战斗场或备战区），p0 手牌 = 物品 + 道具 + 支援者。"""
    state = main_state(p0_extra_hand=(
        inst(60, trainer("测试物品", "物品")),
        inst(61, trainer("测试道具", "宝可梦道具")),
        inst(62, trainer("测试支援者", "支援者")),
    ))
    jx = in_play(2, jellicent())
    if on_bench:
        p1 = state.players[1].model_copy(update={"active": None, "bench": (jx,)})
    else:
        p1 = state.players[1].model_copy(update={"active": jx, "bench": ()})
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.card_effects = {"胖嘟嘟ex": JELLICENT_DOC, "测试物品": ITEM_DOC,
                      "测试支援者": SUPPORTER_DOC}
    return e


def attack_engine(n_energy: int) -> object:
    """p0 战斗场胖嘟嘟ex（附着 n 个超能），p1 战斗场 hp400。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": InPlayPokemon(
            stack=(inst(1, jellicent()),),
            attached_energy=tuple(inst(9000 + i, any_energy(i))
                                  for i in range(n_energy)),
        ),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, basic("厚皮兽", hp=400))})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"胖嘟嘟ex": JELLICENT_DOC}
    return e


def test_胖嘟嘟ex_挂载同文本等价类() -> None:
    """I 标 3 印刷（CSV10.6C-042/162/170）同文本等价类全收。"""
    assert JELLICENT_DOC.card.card_ids == (
        "CSV10.6C-042", "CSV10.6C-162", "CSV10.6C-170")


def test_胖嘟嘟ex_海之咒术_战斗场锁对手物品和道具附着() -> None:
    """声明者在战斗场：对手物品从手牌打出不枚举、道具附着不枚举，支援者照常。"""
    e = lock_engine(on_bench=False)
    plays = {a.iid for a in e.legal_actions(0) if a.kind == "play_trainer"}
    assert 60 not in plays
    assert 62 in plays
    attaches = {a.iid for a in e.legal_actions(0) if a.kind == "attach_tool"}
    assert 61 not in attaches


def test_胖嘟嘟ex_海之咒术_退到备战区即解锁() -> None:
    """「只要这只宝可梦在战斗场上」：备战区不解锁——物品/道具附着恢复枚举。"""
    e = lock_engine(on_bench=True)
    plays = {a.iid for a in e.legal_actions(0) if a.kind == "play_trainer"}
    assert 60 in plays
    attaches = {a.iid for a in e.legal_actions(0) if a.kind == "attach_tool"}
    assert 61 in attaches


def test_胖嘟嘟ex_力量压制_附着3能只打80() -> None:
    """附着能量 3 < 费用 2+2：不追加。"""
    e = attack_engine(3)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 80


def test_胖嘟嘟ex_力量压制_附着4能追加80() -> None:
    """附着能量 4 = 费用 2+2：80+80=160。"""
    e = attack_engine(4)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 160


def test_胖嘟嘟ex_力量压制_附着6能照常追加() -> None:
    """附着能量 6 > 4：追加只触发一次（+80 非 +80×超出数）。"""
    e = attack_engine(6)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 160
