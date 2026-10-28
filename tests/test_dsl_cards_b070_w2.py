"""单卡 DSL 测试（task 070 批 2·WP2 TERA/进化批，6 张卡单中可写的 3 张）：
从 cards/ 真实文件装载（load_card_doc），stub 引擎驱动全链路。

- 伊布ex：虹色因子（modify_evolution 声明驱动进化加宽，task 069 WP1 原语）——
  手牌 rule_box=ex 且 evolves_from=伊布 的卡可进化到伊布ex；登场当回合门不放宽；
  石英闪耀 200 白板不绑定。
- 叶伊布ex：绿叶风暴 60×（计数词 attached_energy_on_opponent_all，对手全场附着
  能量总数）；苔纹玛瑙 230 + heal own_bench 全体各 100（备战空 no-op、伤害照算）。
- 皮卡丘ex：顽强之心（prevent_ko 满 HP 免昏厥截顶留 10；已受伤不免）；黄晶伏特
  300 + discard own_attached_energy choose=3 定点弃自身 3 能。

卡单内 blocked（不写文件，缺词上报主会话）：伊布 CSV9C-153（突进进化 = 进化门
放宽，modify_evolution 只加宽候选不放宽门）/ 厄诡椪 水井面具ex CSV8C-067
（激流水泵 = 附着能量回牌库去向 + 「在这种情况下」节点级门控）/ 火伊布ex
CSV9.5C-023（红玉髓「无法使用招式」= 全招式锁，lock_attack 仅锁绑定招式名，
双招式卡漏锁燃烧充能，D-WP4-5 近似仅适用单招式卡）。
"""

from pathlib import Path

from helpers import energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.state import AttackDef, CardDef, CardInstance

CARDS_DIR = Path(__file__).parent.parent / "cards"

EEVEE_EX_DOC = load_card_doc(CARDS_DIR / "伊布ex.yml")
LEAFEON_DOC = load_card_doc(CARDS_DIR / "叶伊布ex.yml")
PIKACHU_DOC = load_card_doc(CARDS_DIR / "皮卡丘ex.yml")


# ── 夹具（对齐 tests/test_dsl_cards_t29.py 风格）───────────────────────


def mon_card(
    name: str, *, hp: int = 500, energy_type: str | None = None, stage: int = 0,
    attacks: tuple = (), has_ability: bool = False,
    evolves_from: str | None = None, retreat: int = 1, rule_box: str | None = None,
) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=stage, attacks=attacks, energy_type=energy_type,
        has_ability=has_ability, evolves_from=evolves_from,
        retreat_cost=retreat, rule_box=rule_box,
    )


def board(
    *, p0_active=None, p0_bench: tuple = (), p0_hand=None,
    p1_active=None, p1_bench: tuple = (),
    turn: int = 2, current: int = 0, effects: dict,
) -> GameEngine:
    """main 阶段局面：双方场上与 p0 手牌可调。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": p0_active if p0_active is not None else in_play(1, mon_card("战斗兽")),
        "bench": p0_bench,
    })
    if p0_hand is not None:
        p0 = p0.model_copy(update={"hand": p0_hand})
    p1 = state.players[1].model_copy(update={
        "active": p1_active if p1_active is not None
        else in_play(2, mon_card("硬兽", hp=500)),
        "bench": p1_bench,
    })
    e = engine_at(state.model_copy(update={
        "players": (p0, p1), "turn": turn, "current_player": current,
    }))
    e.card_effects = effects
    return e


def typed_energy(iid: int, energy_type: str) -> CardInstance:
    return inst(iid, energy(f"基本{energy_type}能量", energy_type))


def prim_results(e: GameEngine, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


# ── 伊布ex（虹色因子 进化加宽 / 石英闪耀 200 白板）─────────────────────


def eevee_ex() -> CardDef:
    return mon_card(
        "伊布ex", hp=200, energy_type="无", rule_box="ex", has_ability=True,
        attacks=(AttackDef(name="石英闪耀", cost=("火", "水", "雷"), damage=200),),
    )


def test_伊布ex_虹色因子_手牌ex进化枚出并执行() -> None:
    """伊布ex 在场 + 手牌火伊布ex（rule_box=ex 且 evolves_from=伊布）→ 枚出且可执行。"""
    flareon_ex = mon_card("火伊布ex", stage=1, evolves_from="伊布",
                          energy_type="火", rule_box="ex")
    e = board(
        p0_active=in_play(1, eevee_ex()), p0_hand=(inst(50, flareon_ex),),
        effects={"伊布ex": EEVEE_EX_DOC},
    )
    act = Action(kind="evolve", iid=50, target_iid=1)
    assert act in e.legal_actions(0)
    e.apply(0, act)
    p0 = e.state.players[0]
    assert p0.active.current.card.name == "火伊布ex"
    assert 50 in p0.evolved_this_turn
    assert all(c.iid != 50 for c in p0.hand)


def test_伊布ex_虹色因子_非ex或异链不枚出() -> None:
    """无规则盒火伊布（evolves_from=伊布 但非 ex）/ 雷丘ex（ex 但异链）→ 均不枚出。"""
    flareon_plain = mon_card("火伊布", stage=1, evolves_from="伊布", energy_type="火")
    raichu_ex = mon_card("雷丘ex", stage=1, evolves_from="皮卡丘",
                         energy_type="雷", rule_box="ex")
    e = board(
        p0_active=in_play(1, eevee_ex()),
        p0_hand=(inst(50, flareon_plain), inst(51, raichu_ex)),
        effects={"伊布ex": EEVEE_EX_DOC},
    )
    assert not [a for a in e.legal_actions(0) if a.kind == "evolve"]


def test_伊布ex_虹色因子_刚出场回合不可进化() -> None:
    """括号句「刚出场的回合无法进化」= entered_play_this_turn 既有门不放宽。"""
    flareon_ex = mon_card("火伊布ex", stage=1, evolves_from="伊布",
                          energy_type="火", rule_box="ex")
    e = board(
        p0_active=in_play(1, eevee_ex()), p0_hand=(inst(50, flareon_ex),),
        effects={"伊布ex": EEVEE_EX_DOC},
    )
    p0 = e.state.players[0].model_copy(update={"entered_play_this_turn": {1}})
    e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    assert not [a for a in e.legal_actions(0) if a.kind == "evolve"]


def test_伊布ex_石英闪耀_200白板无DSL绑定() -> None:
    """石英闪耀无效果文：引擎白板 200，DSL 不绑定（无 effect_primitive 事件）。"""
    attacker = in_play(1, eevee_ex()).model_copy(update={
        "attached_energy": (
            typed_energy(901, "火"), typed_energy(902, "水"), typed_energy(903, "雷"),
        ),
    })
    e = board(p0_active=attacker, effects={"伊布ex": EEVEE_EX_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 200
    assert not [ev for ev in e.events if ev.kind == "effect_primitive"]


# ── 叶伊布ex（绿叶风暴 60× 计数 / 苔纹玛瑙 230 + 备战全体回 100）─────────


def leafeon_ex() -> CardDef:
    return mon_card(
        "叶伊布ex", hp=270, energy_type="草", stage=1, evolves_from="伊布",
        rule_box="ex",
        attacks=(
            AttackDef(name="绿叶风暴", cost=("草", "无"), damage=None),
            AttackDef(name="苔纹玛瑙", cost=("草", "火", "水"), damage=None),
        ),
    )


def leafeon_with(energy_types: tuple[str, ...], iid: int = 1):
    return in_play(iid, leafeon_ex()).model_copy(update={
        "attached_energy": tuple(
            typed_energy(900 + iid * 10 + j, t) for j, t in enumerate(energy_types)
        ),
    })


def test_叶伊布ex_绿叶风暴_对手全场能量计数乘60() -> None:
    """对手战斗场 2 能 + 备战 1 能 → (2+1)×60=180 落对手战斗场。"""
    p1_active = in_play(2, mon_card("硬兽", hp=500), 2)
    p1_bench = (in_play(80, mon_card("备战兽"), 1),)
    e = board(
        p0_active=leafeon_with(("草", "无")),
        p1_active=p1_active, p1_bench=p1_bench,
        effects={"叶伊布ex": LEAFEON_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 180
    assert prim_results(e, "damage")[0]["final"] == 180


def test_叶伊布ex_绿叶风暴_对手零能量0伤() -> None:
    """对手全场无附着能量 → 0×60=0（攻击机会照耗、回合移交）。"""
    e = board(
        p0_active=leafeon_with(("草", "无")),
        p1_active=in_play(2, mon_card("硬兽", hp=500)),
        p1_bench=(in_play(80, mon_card("备战兽")),),
        effects={"叶伊布ex": LEAFEON_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0
    assert e.state.phase == "main" and e.state.current_player == 1


def test_叶伊布ex_苔纹玛瑙_230加备战全体各回100() -> None:
    """主战 230；备战 A（伤 150）→ 50、备战 B（伤 50）→ 0（不过回复 floor 0）。"""
    bench_a = in_play(80, mon_card("备战兽A")).model_copy(update={"damage": 150})
    bench_b = in_play(81, mon_card("备战兽B")).model_copy(update={"damage": 50})
    e = board(
        p0_active=leafeon_with(("草", "火", "水")),
        p0_bench=(bench_a, bench_b),
        effects={"叶伊布ex": LEAFEON_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 230
    p0 = e.state.players[0]
    assert p0.bench[0].damage == 50
    assert p0.bench[1].damage == 0
    assert prim_results(e, "heal")[0]["healed"] == 150  # 100+50


def test_叶伊布ex_苔纹玛瑙_备战空恢复noop伤害照算() -> None:
    """备战区为空 → heal 节点 no-op，主战 230 照算（落点空不阻却宣言）。"""
    e = board(
        p0_active=leafeon_with(("草", "火", "水")),
        effects={"叶伊布ex": LEAFEON_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 230
    assert prim_results(e, "heal")[0]["healed"] == 0
    assert e.state.phase == "main" and e.state.current_player == 1


# ── 皮卡丘ex（顽强之心 prevent_ko / 黄晶伏特 300 + 弃 3 能）─────────────


def pikachu_ex(hp: int = 200) -> CardDef:
    return mon_card(
        "皮卡丘ex", hp=hp, energy_type="雷", rule_box="ex", has_ability=True,
        attacks=(AttackDef(name="黄晶伏特", cost=("草", "雷", "钢"), damage=None),),
    )


def heavy_attacker(damage: int) -> CardDef:
    return mon_card("重锤兽", attacks=(AttackDef(name="重击", cost=(), damage=damage),))


def ko_names(e: GameEngine) -> list[str]:
    return [ev.detail.get("name") for ev in e.events if ev.kind == "knockout"]


def test_皮卡丘ex_顽强之心_满HP致死截顶留10() -> None:
    """满 HP（200）受 210 致死 → 截顶至 200−10=190，不昏厥，对局继续。"""
    e = board(
        p0_active=in_play(1, heavy_attacker(210)),
        p1_active=in_play(2, pikachu_ex()),
        effects={"皮卡丘ex": PIKACHU_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 190
    assert not ko_names(e)
    assert e.state.phase == "main" and e.state.current_player == 1


def test_皮卡丘ex_顽强之心_已受伤不免昏厥() -> None:
    """已受伤（damage=20，非满 HP）致死 → 不截顶，正常昏厥（ex 拿 2 奖赏）。"""
    hurt = in_play(2, pikachu_ex()).model_copy(update={"damage": 20})
    e = board(
        p0_active=in_play(1, heavy_attacker(210)),
        p1_active=hurt,
        effects={"皮卡丘ex": PIKACHU_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert "皮卡丘ex" in ko_names(e)
    assert len([ev for ev in e.events if ev.kind == "take_prize"]) == 2
    assert e.state.phase == "game_over" and e.state.winner == 0  # 无备战换上 → 判负


def test_皮卡丘ex_黄晶伏特_300并定点弃3能() -> None:
    """附着 3 能（=费用）攻击：主战 300 先结算 → 挂起选 3 能（池=自身附着，
    min=max=3）→ 全弃，附着清空。"""
    attacker = in_play(1, pikachu_ex()).model_copy(update={
        "attached_energy": (
            typed_energy(901, "草"), typed_energy(902, "雷"), typed_energy(903, "钢"),
        ),
    })
    e = board(p0_active=attacker, effects={"皮卡丘ex": PIKACHU_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"
    assert sorted(e.state.pending_choice.pool_iids) == [901, 902, 903]
    e.apply(0, Action(kind="choose", choices=(901, 902, 903)))
    p0 = e.state.players[0]
    assert e.state.players[1].active.damage == 300
    assert p0.active.attached_energy == ()
    assert sorted(c.iid for c in p0.discard) == [901, 902, 903]
    assert prim_results(e, "discard")[0]["discarded"] == 3
    assert e.state.phase == "main" and e.state.current_player == 1


def test_皮卡丘ex_黄晶伏特_4能选3剩余保留() -> None:
    """附着 4 能时池为全 4 张、恰选 3 张弃置，未选 1 张保留在身上。"""
    attacker = in_play(1, pikachu_ex()).model_copy(update={
        "attached_energy": (
            typed_energy(901, "草"), typed_energy(902, "雷"),
            typed_energy(903, "钢"), typed_energy(904, "无"),
        ),
    })
    e = board(p0_active=attacker, effects={"皮卡丘ex": PIKACHU_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert sorted(e.state.pending_choice.pool_iids) == [901, 902, 903, 904]
    e.apply(0, Action(kind="choose", choices=(901, 902, 904)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [903]
    assert sorted(c.iid for c in p0.discard) == [901, 902, 904]
    assert e.state.players[1].active.damage == 300
