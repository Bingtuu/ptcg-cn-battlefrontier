"""单卡 DSL 测试（task 026 WP8）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批 3 张 C 级特殊能量（机制 = WP8 provide_energy 被动框架 + 换位触发 +
protection 能量来源）：
- 喷射能量（G 标 5 印刷）：视作1个【无】；手动从手牌附着备战宝可梦时该宝可梦
  与战斗宝可梦互换（own_attach_from_hand_to_bench + switch self）。
- 夜光能量（G 标池内 1 印刷 CSV1C-127 文本类；另 7 印刷异文本类未落地）：
  视作1个所有属性能量（彩虹）；持有者有其他特殊能量时降级为【无】
  （holder_special_energy_count_ge:2，含自身）。
- 薄雾能量（H 标 3 印刷）：视作1个【无】；持有者不受对手宝可梦招式的效果影响
  （protection scope=opponent_attack_effects 挂能量卡文档）。
清单 9 闸 1 防回归用例：夜光池内文本类混入异文本印刷必须被拦。
"""

from pathlib import Path

import pytest
from helpers import basic, energy, in_play, inst, main_state

from battlefrontier.cli import main as cli_main
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    SpecialCondition,
)

CARDS_DIR = Path(__file__).parent.parent / "cards"
DB_PATH = Path(r"C:/Vibe Project/Pokearena/data/ptcg-cn.db")
needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="本机无 ptcg-cn.db")

JET_DOC = load_card_doc(CARDS_DIR / "喷射能量.yml")
NIGHT_DOC = load_card_doc(CARDS_DIR / "夜光能量.yml")
MIST_DOC = load_card_doc(CARDS_DIR / "薄雾能量.yml")

FX = {"喷射能量": JET_DOC, "夜光能量": NIGHT_DOC, "薄雾能量": MIST_DOC}


def special(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy",
                   is_basic_energy=False)


def jet(iid: int) -> CardInstance:
    return inst(iid, special("喷射能量"))


def night(iid: int) -> CardInstance:
    return inst(iid, special("夜光能量"))


def mist(iid: int) -> CardInstance:
    return inst(iid, special("薄雾能量"))


def poke(name: str, *, hp: int = 300, attacks: tuple = ()) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=hp, attacks=attacks, retreat_cost=1)


def fire_mon(name: str, cost: tuple = ("火",), damage: int = 30) -> CardDef:
    return poke(name, attacks=(AttackDef(name="火击", cost=cost, damage=damage),))


def engine_at_seed(state, seed: int = 0) -> GameEngine:
    e = GameEngine(RandomSource(seed))
    e.state = state
    return e


def board(*, p0_active=None, p0_bench: tuple = (), p0_extra_hand: tuple = (),
          p1_active=None, effects: dict | None = None) -> GameEngine:
    state = main_state(p0_extra_hand=p0_extra_hand)
    p0 = state.players[0].model_copy(update={
        "active": p0_active if p0_active is not None else in_play(1, poke("战斗兽"), 1),
        "bench": p0_bench,
    })
    p1 = state.players[1].model_copy(update={
        "active": p1_active if p1_active is not None else in_play(2, basic("硬兽", hp=500), 1),
    })
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = effects if effects is not None else FX
    return e


def attack_kinds(e: GameEngine, player: int = 0) -> list[int]:
    return [a.attack_index for a in e.legal_actions(player) if a.kind == "attack"]


def prim_results(e: GameEngine, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


# ── 喷射能量 ─────────────────────────────────────────────────────────


def test_喷射能量_视作1个无能量() -> None:
    """正例：附着喷射 = 1 个【无】——无色费用可攻，有色费用不可攻。"""
    e = board(p0_active=in_play(1, fire_mon("火兽"), 0).model_copy(
        update={"attached_energy": (jet(90),)}))
    assert attack_kinds(e) == []  # 【无】不抵【火】
    colorless = poke("无兽", attacks=(AttackDef(name="打击", cost=("无",), damage=30),))
    e = board(p0_active=in_play(1, colorless, 0).model_copy(
        update={"attached_energy": (jet(90),)}))
    assert 0 in attack_kinds(e)


def test_喷射能量_手动附着备战互换() -> None:
    """正例：手动从手牌附着于备战宝可梦 → 该宝可梦与战斗宝可梦互换；
    附着战斗场不触发。"""
    e = board(
        p0_active=in_play(1, poke("战斗兽")),
        p0_bench=(in_play(70, poke("备战兽")),),
        p0_extra_hand=(jet(60),),
    )
    e.apply(0, Action(kind="attach_energy", iid=60, target_iid=70))
    p0 = e.state.players[0]
    assert p0.active.current.iid == 70
    assert p0.bench[0].current.iid == 1
    assert p0.energy_attached_this_turn is True
    assert any(ev.kind == "trigger_on_event"
               and ev.detail.get("event") == "own_attach_from_hand_to_bench"
               for ev in e.events)
    # 附着战斗场：不互换、无事件
    e = board(p0_extra_hand=(jet(60),))
    e.apply(0, Action(kind="attach_energy", iid=60, target_iid=1))
    assert e.state.players[0].active.current.iid == 1
    assert not any(ev.kind == "trigger_on_event" for ev in e.events)


# ── 夜光能量 ─────────────────────────────────────────────────────────


def test_夜光能量_单独附着视作所有属性() -> None:
    """正例：单独附着 = 彩虹——单张抵【火】；【火】【火】需 2 单元。"""
    e = board(p0_active=in_play(1, fire_mon("火兽"), 0).model_copy(
        update={"attached_energy": (night(90),)}))
    assert 0 in attack_kinds(e)
    e = board(p0_active=in_play(1, fire_mon("重火兽", cost=("火", "火")), 0).model_copy(
        update={"attached_energy": (night(90),)}))
    assert attack_kinds(e) == []


def test_夜光能量_有其他特殊能量降级为无() -> None:
    """边界：+喷射（其他特殊能量）→ 降级【无】——不抵【火】、可抵【无】；
    2 张夜光互相降级；基本能量不触发降级。"""
    e = board(p0_active=in_play(1, fire_mon("火兽"), 0).model_copy(
        update={"attached_energy": (night(90), jet(91))}))
    assert attack_kinds(e) == []
    colorless = poke("无兽", attacks=(AttackDef(name="打击", cost=("无", "无"), damage=30),))
    e = board(p0_active=in_play(1, colorless, 0).model_copy(
        update={"attached_energy": (night(90), jet(91))}))
    assert 0 in attack_kinds(e)
    # 2 张夜光互相降级：不抵【火】【火】
    e = board(p0_active=in_play(1, fire_mon("重火兽", cost=("火", "火")), 0).model_copy(
        update={"attached_energy": (night(90), night(91))}))
    assert attack_kinds(e) == []
    # 夜光 + 基本火能量：不降级（基本能量不计）——彩虹 + 火抵【火】【火】
    e = board(p0_active=in_play(1, fire_mon("重火兽", cost=("火", "火")), 0).model_copy(
        update={"attached_energy": (night(90), inst(91, energy("基本火能量", "火")))}))
    assert 0 in attack_kinds(e)


# ── 薄雾能量 ─────────────────────────────────────────────────────────

STATUS_DOC_TEXT = """
card:
  name_group: 麻痹撒菱兽
effects:
  - trigger: on_attack
    attack: 麻痹撒菱
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 30}}
      - {action: apply_status, selector: opponent_active, args: {status: paralyzed}}
"""


def test_薄雾能量_不受对手招式效果() -> None:
    """正例：持有者不受对手招式附加效果（伤害照算、状态被挡）；无薄雾对照照常。"""
    from battlefrontier.dsl import parse_card_doc

    doc = parse_card_doc(STATUS_DOC_TEXT)
    attacker = poke("麻痹撒菱兽", attacks=(
        AttackDef(name="麻痹撒菱", cost=("无",), damage=None),))
    defender_with_mist = in_play(2, poke("防守兽"), 0).model_copy(
        update={"attached_energy": (mist(90),)})
    fx = {**FX, "麻痹撒菱兽": doc}
    e = board(p0_active=in_play(1, attacker, 1), p1_active=defender_with_mist,
              effects=fx)
    e.apply(0, Action(kind="attack", attack_index=0))
    p1_active = e.state.players[1].active
    assert p1_active.damage == 30                              # 伤害照算
    assert p1_active.conditions == frozenset()                 # 状态效果被挡
    assert prim_results(e, "apply_status")[0]["reason"] == "protected"
    # 对照：无薄雾 → 麻痹照常
    e = board(p0_active=in_play(1, attacker, 1),
              p1_active=in_play(2, poke("防守兽")), effects=fx)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert SpecialCondition.PARALYZED in e.state.players[1].active.conditions


# ── 清单 9：闸 1 防回归（故意取错印刷必被拦）─────────────────────────────


@needs_db
def test_闸1_夜光混入异文本印刷被拦_防回归(tmp_path, capsys):
    """夜光池内文本类（CSV1C-127）混入异文本类印刷（CSV8C-264）→
    dsl-check --db 必须 FAIL（归一化 text_raw 不一致）。"""
    src = (CARDS_DIR / "夜光能量.yml").read_text(encoding="utf-8")
    assert "card_ids: [CSV1C-127]" in src
    p = tmp_path / "夜光能量.yml"
    p.write_text(src.replace("card_ids: [CSV1C-127]",
                             "card_ids: [CSV1C-127, CSV8C-264]", 1),
                 encoding="utf-8")
    rc = cli_main(["dsl-check", str(p), "--db", str(DB_PATH)])
    out = capsys.readouterr().out
    assert rc == 1 and "FAIL" in out and "文本" in out
