"""task 027 机制测试：TERA 备战免伤（D-027-1，规则骨架）/ ACE SPEC 校验钉住
（D-027-2）/ 新冲天 provide_energy count + holder_stage（D-027-4）/
厄诡椪 attach_energy own_hand→self + 计数词（D-027-5）/ 多龙巴鲁托
place_damage_counters distribute（D-027-6）。

设计决议（tasks/task 027.md，2026-09-20 定稿）：
- D-027-1：备战区 is_tera 宝可梦受招式伤害 → 0（双方招式；规则骨架非 DSL，
  与 D-WP7-5 谢米守卫同落点不同源）；指示物/招式效果不受影响；战斗场太晶
  正常受伤。注意：现有 damage 原语备战落点只有 opponent_pokemon_any（对手侧），
  「己方招式打己方备战」无选择器可达——守卫为目标侧判定（读 target.is_tera，
  无侧别比较），未来若增己方备战伤害落点天然覆盖（本文件以断言钉住目标侧口径）。
- D-027-2：load_deck 对 2 张 ACE 构筑抛错（db validate_deck 口径）；池内 9 套
  各 ≤1 ACE 回归。
- D-027-4：provide_energy args.count（缺省 1；2 彩虹单元可抵 2 个任意符号）；
  条件词 holder_stage:N（栈顶 CardDef.stage）。
- D-027-5：attach_energy selector own_hand + args.target_pool=self（目标固定
  来源持有者，无段2）；手牌无匹配能量 → 特性不可用（ability_feasible 门控）。
  计数词 attached_energy_on_both_actives = 双方战斗场附着能量总数。
- D-027-6：place_damage_counters opponent_bench + args.distribute——N 个指示物
  逐只挂起分配（可集中可分散）；全部分配完统一落点 + check_knockouts；
  备战空 no-op；备战太晶照常收指示物（指示物非伤害）。
- D-WP8-3 归正（2026-09-20 主会话裁决）：「从手牌附着」无附着原因限定——
  attach_energy own_hand 来源效果附着目标为备战区时同样入队
  own_attach_from_hand_to_bench（效果完成后排水）；discard/deck 来源不触发。
"""

from types import SimpleNamespace

import pytest
from helpers import energy, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.chooser import condition_met
from battlefrontier.dsl.loader import DslError, load_vocabularies
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    InPlayPokemon,
)

# ── 夹具 ─────────────────────────────────────────────────────────────


def pokemon(
    name: str, *, hp: int = 500, attacks: tuple | None = None, damage: int = 20,
    cost: int = 1, stage: int = 0, is_tera: bool = False,
    energy_type: str | None = None, has_ability: bool = False,
) -> CardDef:
    if attacks is None:
        attacks = (AttackDef(name="打击", cost=("无",) * cost, damage=damage),)
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=stage, attacks=attacks, is_tera=is_tera,
        energy_type=energy_type, has_ability=has_ability,
    )


def special_energy(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy",
                   is_basic_energy=False)


def mon(
    iid: int, card: CardDef | None = None, *, damage: int = 0,
    energies: int = 0, attached: tuple[CardInstance, ...] = (),
) -> InPlayPokemon:
    card = card or pokemon(f"兽{iid}")
    return InPlayPokemon(
        stack=(inst(iid, card),),
        attached_energy=(
            tuple(inst(9000 + iid * 10 + j, energy()) for j in range(energies))
            + attached
        ),
        damage=damage,
    )


def board_engine(
    *, p0_active=None, p0_bench: tuple = (), p1_active=None, p1_bench: tuple = (),
    p0_extra_hand: tuple = (), p0_deck=None, p1_deck=None, p1_hand=None,
    turn: int = 2, current: int = 0, seed: int = 0, effects: dict | None = None,
) -> GameEngine:
    state = main_state(p0_extra_hand=p0_extra_hand)
    p0 = state.players[0].model_copy(update={
        "active": p0_active if p0_active is not None else mon(1),
        "bench": p0_bench,
    })
    if p0_deck is not None:
        p0 = p0.model_copy(update={"deck": p0_deck})
    p1 = state.players[1].model_copy(update={
        "active": p1_active if p1_active is not None else mon(2),
        "bench": p1_bench,
    })
    if p1_deck is not None:
        p1 = p1.model_copy(update={"deck": p1_deck})
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
    e = GameEngine(RandomSource(seed))
    e.state = state.model_copy(update={
        "players": (p0, p1), "turn": turn, "current_player": current,
    })
    e.card_effects = effects or {}
    return e


def prim_results(e: GameEngine, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


def attack_kinds(e: GameEngine, player: int = 0) -> list[int]:
    return [a.attack_index for a in e.legal_actions(player) if a.kind == "attack"]


# ── TERA 备战免伤（清单 1，D-027-1）────────────────────────────────────

SNIPE_DOC = parse_card_doc("""
card:
  name_group: 狙击兽
effects:
  - trigger: on_attack
    attack: 狙击
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 50}}
""")

COUNTER_DOC = parse_card_doc("""
card:
  name_group: 撒菱兽
effects:
  - trigger: on_attack
    attack: 撒菱
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 3}}
""")


def _sniper(doc_name: str = "狙击兽") -> CardDef:
    attack = "狙击" if doc_name == "狙击兽" else "撒菱"
    return pokemon(doc_name, attacks=(AttackDef(name=attack, cost=("无",), damage=None),))


def snipe_engine(**kw) -> GameEngine:
    return board_engine(
        p0_active=mon(1, _sniper(), energies=1),
        effects={"狙击兽": SNIPE_DOC}, **kw,
    )


def test_tera_bench_attack_damage_immune() -> None:
    """清单1：备战太晶受招式伤害 → 0；备战非太晶正常受伤；战斗场太晶正常受伤；
    指示物放置不受影响；守卫为目标侧判定（双方招式同口径）。"""
    tera = pokemon("太晶兽", is_tera=True)
    # 备战太晶：招式伤害归零
    e = snipe_engine(p1_bench=(mon(80, tera),))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 0
    assert prim_results(e, "damage")[0]["protected"] is True
    # 备战非太晶：正常受伤
    e = snipe_engine(p1_bench=(mon(80, pokemon("普通兽")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 50
    # 战斗场太晶：正常受伤（免伤仅备战区）
    e = snipe_engine(p1_active=mon(2, tera))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[1].active.damage == 50
    # 指示物放置不受免伤影响（指示物非招式伤害）
    e = board_engine(
        p0_active=mon(1, _sniper("撒菱兽"), energies=1),
        p1_bench=(mon(80, tera),),
        effects={"撒菱兽": COUNTER_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 30
    # 目标侧判定无侧别：站在防守方视角重放同一招式路径（p1 攻击 p0 备战太晶），
    # 守卫读 target.is_tera 与持有方/攻击方归属无关——卡面「双方招式」语义
    e = board_engine(
        p0_bench=(mon(80, tera),),
        p1_active=mon(2, _sniper(), energies=1),
        current=1, effects={"狙击兽": SNIPE_DOC},
    )
    e.apply(1, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="choose", choices=(80,)))
    assert e.state.players[0].bench[0].damage == 0


# ── ACE SPEC 校验钉住（清单 3，D-027-2）─────────────────────────────────

from pathlib import Path

DB_PATH = Path(r"C:/Vibe Project/Pokearena/data/ptcg-cn.db")
needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="本机无 ptcg-cn.db")

POOL_DECK_IDS = (
    "mik_moe:644634",  # 沙奈朵（秘密箱）
    "mik_moe:650353",  # 喷火龙大比鸟（极限腰带）
    "mik_moe:652967",  # 猛雷鼓厄诡椪（顶尖捕捉器）
    "mik_moe:655545",  # 多龙巴鲁托黑夜魔灵（不公印章）
    "mik_moe:655776",  # 多龙巴鲁托喷火龙（不公印章）
    "mik_moe:643572",  # 玛俐的长毛巨魔雪妖女（秘密箱）
    "mik_moe:655513",  # 赛富豪（能量输送PRO）
    "mik_moe:648346",  # 多龙巴鲁托（新冲天能量）
    "mik_moe:655512",  # 赫普的苍响（顶尖捕捉器）
)


@needs_db
def test_ace_spec_two_in_deck_rejected() -> None:
    """清单3：含 2 张 ACE SPEC 的构筑装载抛错（violations 明细含 ACE）；
    is_ace_spec 字段断言；含 1 张的池内构筑通过。"""
    from ptcgdb.sdk import open_db

    from battlefrontier.data import deck as deck_mod

    db = open_db(str(DB_PATH))
    try:
        base = db.get_deck("mik_moe:650353")  # 喷火龙大比鸟（含极限腰带 1 ACE）
        assert any(
            db.get_card(en.card_id).is_ace_spec for en in base.cards
        )
        # 换入第二张 ACE（不公印章 CSV8C-173）替换一张非 ACE 卡
        swapped = []
        done = False
        for en in base.cards:
            if not done and not db.get_card(en.card_id).is_ace_spec:
                swapped.append(SimpleNamespace(card_id="CSV8C-173", count=1))
                done = True
                if en.count > 1:  # 保 60 张
                    swapped.append(SimpleNamespace(
                        card_id=en.card_id, count=en.count - 1))
            else:
                swapped.append(en)
        fake_deck = SimpleNamespace(cards=swapped)
        date = db.snapshots("standard")[-1].effective_from
        ids = [en.card_id for en in swapped for _ in range(en.count)]
        assert len(ids) == 60
        report = db.validate_deck(ids, date, "standard")
        assert not report.ok
        assert any("ace" in str(v).lower() for v in report.violations)
    finally:
        db.close()
    # load_deck 级钉住：同一构筑经 load_deck 抛 ValueError（violations 明细透出）
    real_open = deck_mod.open_db

    class _WrappedDb:
        """get_deck 返回捏造构筑，其余调用透传真实 db（validate_deck 为真判定）。"""

        def __init__(self, real):
            self._real = real

        def get_deck(self, deck_id):
            return fake_deck

        def __getattr__(self, name):
            return getattr(self._real, name)

    def fake_open(path):
        return _WrappedDb(real_open(path))

    import battlefrontier.data.deck as dm
    orig = dm.open_db
    dm.open_db = fake_open
    try:
        with pytest.raises(ValueError, match="(?i)ace"):
            dm.load_deck(str(DB_PATH), "mik_moe:650353")
    finally:
        dm.open_db = orig
    # 含 1 张 ACE 的池内构筑正常装载
    d = dm.load_deck(str(DB_PATH), "mik_moe:650353")
    assert sum(1 for c in d.cards if c.is_ace_spec) == 1


@needs_db
def test_ace_spec_pool_decks_regression() -> None:
    """清单3：池内 9 套各 ≤1 ACE 且全部正常装载（回归）。"""
    from battlefrontier.data.deck import load_deck

    for did in POOL_DECK_IDS:
        d = load_deck(str(DB_PATH), did)
        aces = [c.name for c in d.cards if c.is_ace_spec]
        assert len(aces) <= 1, f"{did} 含 {len(aces)} 张 ACE: {aces}"
        assert len(d.cards) == 60


# ── 新冲天能量（清单 5，D-027-4）────────────────────────────────────────

BOOST_DOC = parse_card_doc("""
card:
  name_group: 新冲天能量
effects:
  - trigger: passive_static
    condition: holder_stage:2
    actions:
      - {action: provide_energy, args: {types: all, count: 2}}
  - trigger: passive_static
    actions:
      - {action: provide_energy, args: {types: [无]}}
""")


def boost(iid: int) -> CardInstance:
    return inst(iid, special_energy("新冲天能量"))


def test_boost_energy_stage2_two_rainbow_units() -> None:
    """清单5：附着 2 阶 → 2 彩虹单元（单卡满足【火】【水】双符号费用）；
    附着非 2 阶 → 1【无】（无条件块回退）。"""
    dual = pokemon("双费兽", attacks=(AttackDef(name="双击", cost=("火", "水"), damage=30),))
    # 2 阶持有者：单张新冲天满足【火】【水】
    e = board_engine(p0_active=mon(1, pokemon("大二阶", stage=2, attacks=dual.attacks),
                                   attached=(boost(90),)),
                     effects={"新冲天能量": BOOST_DOC})
    assert 0 in attack_kinds(e)
    # 3 符号需求：2 单元不够
    tri = pokemon("三费兽", attacks=(AttackDef(name="三击", cost=("火", "水", "无"), damage=30),))
    e = board_engine(p0_active=mon(1, pokemon("大三阶", stage=2, attacks=tri.attacks),
                                   attached=(boost(90),)),
                     effects={"新冲天能量": BOOST_DOC})
    assert attack_kinds(e) == []
    # 1 阶持有者：回退 1【无】——不抵有色，可抵无色
    e = board_engine(p0_active=mon(1, pokemon("中一阶", stage=1, attacks=dual.attacks),
                                   attached=(boost(90),)),
                     effects={"新冲天能量": BOOST_DOC})
    assert attack_kinds(e) == []
    plain = pokemon("无兽", attacks=(AttackDef(name="打击", cost=("无",), damage=30),))
    e = board_engine(p0_active=mon(1, pokemon("中一阶", stage=1, attacks=plain.attacks),
                                   attached=(boost(90),)),
                     effects={"新冲天能量": BOOST_DOC})
    assert 0 in attack_kinds(e)


def test_boost_energy_count_and_holder_stage_validation() -> None:
    """清单5：count 缺省 = 1（WP8 三卡回归由全量套件守护）；count 畸形
    （0/负/非 int）→ DslError；holder_stage 词注册 + 畸形 DslError。"""
    for bad_count in ("0", "-1", "'2'", "true"):
        bad = parse_card_doc(f"""
card:
  name_group: 坏冲天
effects:
  - trigger: passive_static
    actions:
      - {{action: provide_energy, args: {{types: all, count: {bad_count}}}}}
""")
        e = board_engine(p0_active=mon(1, attached=(inst(90, special_energy("坏冲天")),)),
                         effects={"坏冲天": bad})
        with pytest.raises(DslError, match="count"):
            e.legal_actions(0)
    # holder_stage:N 注册（读栈顶 stage）
    e = board_engine(p0_active=mon(1, pokemon("大二阶", stage=2), attached=(boost(90),)),
                     effects={"新冲天能量": BOOST_DOC})
    holder = e.state.players[0].active
    assert condition_met("holder_stage:2", e, 0, holder) is True
    assert condition_met("holder_stage:1", e, 0, holder) is False
    assert condition_met("holder_stage:2", e, 0, None) is False
    with pytest.raises(DslError, match="holder_stage"):
        condition_met("holder_stage:x", e, 0, holder)
    # 词表同步：计数词注册（D-027-5）
    assert "attached_energy_on_both_actives" in load_vocabularies().counters


# ── 厄诡椪 碧草之舞 / 万叶阵雨（清单 6，D-027-5）──────────────────────────

OGERPON_DOC = parse_card_doc("""
card:
  name_group: 厄诡椪桩
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: attach_energy, selector: own_hand, choose: 1, destination: attach, filters: [basic_energy, energy_草], args: {target_pool: self}}
      - {action: draw, count: 1}
  - trigger: on_attack
    attack: 万叶阵雨
    actions:
      - {action: damage, selector: opponent_active, count: attached_energy_on_both_actives, args: {base: 30, per: 30, op: "+"}}
""")


def ogerpon(name: str = "厄诡椪桩") -> CardDef:
    return pokemon(name, hp=210, energy_type="草", attacks=(
        AttackDef(name="万叶阵雨", cost=("草", "草", "草"), damage=None),))


def test_ogerpon_ability_attach_from_hand_to_self() -> None:
    """清单6：特性——手牌 1 张基本草能量附着自身 + 抽 1（每回合 1 次）；
    手牌无草能量 → 特性不可用；备战位持有者同样可附着自身。"""
    grass = inst(60, energy("基本草能量", "草"))
    fire = inst(61, energy("基本火能量", "火"))
    fx = {"厄诡椪桩": OGERPON_DOC}
    # 正例：手牌有草能量 → 特性可发动
    e = board_engine(p0_active=mon(1, ogerpon()), p0_extra_hand=(grass, fire),
                     effects=fx)
    use = [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    assert len(use) == 1 and use[0].iid == 1
    hand_before = len(e.state.players[0].hand)
    e.apply(0, use[0])
    assert e.state.phase == "choice"
    e.apply(0, Action(kind="choose", choices=(60,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [60]  # 草能量附上自身
    assert len(p0.hand) == hand_before - 1 + 1                  # -1 能量 +1 抽牌
    assert 61 in [c.iid for c in p0.hand]                       # 火能量未动
    assert e.state.phase == "main"
    # 每回合 1 次：本回合不再枚举
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    # 手牌无草能量 → 特性不可用（ability_feasible 门控）
    e = board_engine(p0_active=mon(1, ogerpon()), p0_extra_hand=(fire,),
                     effects=fx)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    # 备战位持有者：特性可用，能量附上备战自身
    e = board_engine(p0_bench=(mon(70, ogerpon()),), p0_extra_hand=(grass,),
                     effects=fx)
    use = [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    assert len(use) == 1 and use[0].iid == 70
    e.apply(0, use[0])
    e.apply(0, Action(kind="choose", choices=(60,)))
    assert [c.iid for c in e.state.players[0].bench[0].attached_energy] == [60]


def test_ogerpon_attack_both_actives_energy_count() -> None:
    """清单6：万叶阵雨 30+双方战斗场能量总数×30（含最低基准断言）。"""
    fx = {"厄诡椪桩": OGERPON_DOC}
    g = lambda iid: inst(iid, energy("基本草能量", "草"))
    # 攻击方 3 草（费用）+ 对手 0 → 30 + 3×30 = 120
    e = board_engine(
        p0_active=mon(1, ogerpon(), attached=(g(90), g(91), g(92))),
        p1_active=mon(2, energies=0), effects=fx,
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 120
    # 对手 2 能量 → 30 + 5×30 = 180
    e = board_engine(
        p0_active=mon(1, ogerpon(), attached=(g(90), g(91), g(92))),
        p1_active=mon(2, energies=2), effects=fx,
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 180


# ── 多龙巴鲁托 幻影潜袭 distribute（清单 7，D-027-6）──────────────────────

PHANTOM_DOC = parse_card_doc("""
card:
  name_group: 多龙桩
effects:
  - trigger: on_attack
    attack: 幻影潜袭
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 200}}
      - {action: place_damage_counters, selector: opponent_bench, args: {counters: 6, distribute: true}}
""")


def dragapult(name: str = "多龙桩") -> CardDef:
    return pokemon(name, attacks=(
        AttackDef(name="幻影潜袭", cost=("无",), damage=None),))


def phantom_engine(**kw) -> GameEngine:
    return board_engine(
        p0_active=mon(1, dragapult(), energies=1),
        effects={"多龙桩": PHANTOM_DOC}, **kw,
    )


def test_phantom_dive_distribute_concentrate_and_spread() -> None:
    """清单7：200 伤害照算 + 6 指示物任意分配——集中 1 只 / 分散多只 /
    分配致昏厥走正常 check_knockouts。"""
    # 集中：6 个全给 A（hp100 → 60 伤害，存活）
    e = phantom_engine(p1_bench=(mon(80, pokemon("A", hp=100)),
                                 mon(81, pokemon("B", hp=100))))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 200  # 伤害先落
    for _ in range(6):
        assert e.state.phase == "choice"
        e.apply(0, Action(kind="choose", choices=(80,)))
    p1 = e.state.players[1]
    assert p1.bench[0].damage == 60 and p1.bench[1].damage == 0
    assert prim_results(e, "place_damage_counters")[0]["placed"] == 6
    # 分散 + 致昏厥：B（hp30）收 3 个 → 昏厥拿奖赏；A 收 3 个
    e = phantom_engine(p1_bench=(mon(80, pokemon("A", hp=100)),
                                 mon(81, pokemon("B", hp=30))))
    e.apply(0, Action(kind="attack", attack_index=0))
    for iid in (80, 81, 80, 81, 80, 81):
        e.apply(0, Action(kind="choose", choices=(iid,)))
    p1 = e.state.players[1]
    assert p1.bench[0].damage == 30
    assert len(p1.bench) == 1                    # B 昏厥离场
    assert len(e.state.players[0].prizes) == 5   # 攻击方拿 1 奖赏
    assert e.state.current_player == 1           # 攻击后回合推进


def test_phantom_dive_empty_bench_noop_and_tera_takes_counters() -> None:
    """清单7：备战空 → 指示物段 no-op 伤害照算（不挂起）；备战太晶照常收
    指示物（指示物非伤害，D-027-1 反面）。"""
    e = phantom_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 200
    assert e.state.phase != "choice"  # 无挂起
    assert prim_results(e, "place_damage_counters")[0]["placed"] == 0
    # 备战太晶：照常收指示物
    e = phantom_engine(p1_bench=(mon(80, pokemon("太晶备战", hp=200, is_tera=True)),))
    e.apply(0, Action(kind="attack", attack_index=0))
    for _ in range(6):
        e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 60


def test_distribute_form_validation() -> None:
    """清单7：distribute 形态校验——choose 互斥 / 非 opponent_bench / 非 bool
    → DslError（不猜）。"""
    for bad_args in (
        ", choose: 1, args: {counters: 6, distribute: true}",
        ", args: {counters: 6, distribute: 1}",  # YAML 1.1 yes→bool，非 bool 须用 int
    ):
        bad = parse_card_doc(f"""
card:
  name_group: 坏分配
effects:
  - trigger: on_attack
    attack: 坏招
    actions:
      - {{action: place_damage_counters, selector: opponent_bench{bad_args}}}
""")
        e = board_engine(p0_active=mon(1, energies=1), effects={"兽1": bad})
        src = e.state.players[0].active.current
        from battlefrontier.dsl import ExecutionContext, run_effect
        ctx = ExecutionContext(engine=e, player=0, source=src,
                               effect_id="test", trigger="on_attack")
        with pytest.raises(DslError, match="distribute"):
            run_effect(ctx, bad.effects[0])
    # 非 opponent_bench selector + distribute → DslError
    bad = parse_card_doc("""
card:
  name_group: 坏分配2
effects:
  - trigger: on_attack
    attack: 坏招
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 6, distribute: true}}
""")
    e = board_engine(p0_active=mon(1, energies=1), effects={"兽1": bad})
    src = e.state.players[0].active.current
    from battlefrontier.dsl import ExecutionContext, run_effect
    ctx = ExecutionContext(engine=e, player=0, source=src,
                           effect_id="test", trigger="on_attack")
    with pytest.raises(DslError, match="distribute"):
        run_effect(ctx, bad.effects[0])


# ── D-WP8-3 归正：效果附着 own_hand 来源触发喷射换位（2026-09-20 裁决）────────

JET_DOC = parse_card_doc("""
card:
  name_group: 喷射能量
effects:
  - trigger: passive_static
    actions:
      - {action: provide_energy, args: {types: [无]}}
  - trigger: trigger_on_event
    event: own_attach_from_hand_to_bench
    actions:
      - {action: switch, selector: self}
""")


def jet(iid: int) -> CardInstance:
    return inst(iid, special_energy("喷射能量"))


def test_effect_attach_own_hand_to_bench_triggers_jet() -> None:
    """裁决归正：「当将这张卡牌从手牌附着于备战宝可梦身上时」无附着原因限定——
    效果附着（attach_energy own_hand→self，等价碧草之舞测试卡）目标为备战区时
    触发喷射换位；时序 = 效果全部完成（附能+抽 1）后排水换位；不占每回合附着权。"""
    ability_doc = parse_card_doc("""
card:
  name_group: 测试椪
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: attach_energy, selector: own_hand, choose: 1, destination: attach, filters: [energy], args: {target_pool: self}}
      - {action: draw, count: 1}
""")
    holder = pokemon("测试椪", has_ability=True)
    e = board_engine(
        p0_bench=(mon(80, holder),),
        p0_extra_hand=(jet(61),),
        effects={"测试椪": ability_doc, "喷射能量": JET_DOC},
    )
    e.apply(0, Action(kind="use_ability", iid=80))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool == "own_hand" and pc.pool_iids == (51, 61)
    e.apply(0, Action(kind="choose", choices=(61,)))
    p0 = e.state.players[0]
    # 效果完成：附能 + 抽 1 已结算；排水后换位——持有者与战斗宝可梦互换
    assert p0.active.current.iid == 80
    assert p0.bench[0].current.iid == 1
    assert [c.iid for c in p0.active.attached_energy] == [61]  # 喷射随持有者上战斗场
    assert 100 in [c.iid for c in p0.hand]  # 抽 1（牌库顶）照常
    assert p0.energy_attached_this_turn is False  # 效果附着不占每回合附着权
    triggers = [ev for ev in e.events
                if ev.kind == "trigger_on_event"
                and ev.detail.get("event") == "own_attach_from_hand_to_bench"]
    assert len(triggers) == 1 and triggers[0].detail.get("name") == "喷射能量"
    assert e.state.phase == "main" and e.state.current_player == 0


def test_effect_attach_own_hand_to_active_no_trigger() -> None:
    """归正边界：own_hand 效果附着到战斗场持有者 → 不触发（仅备战区目标分发）。"""
    ability_doc = parse_card_doc("""
card:
  name_group: 测试椪
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: attach_energy, selector: own_hand, choose: 1, destination: attach, filters: [energy], args: {target_pool: self}}
""")
    holder = pokemon("测试椪", has_ability=True)
    e = board_engine(
        p0_active=mon(1, holder),
        p0_extra_hand=(jet(61),),
        effects={"测试椪": ability_doc, "喷射能量": JET_DOC},
    )
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(61,)))
    p0 = e.state.players[0]
    assert p0.active.current.iid == 1
    assert [c.iid for c in p0.active.attached_energy][-1] == 61
    assert not any(ev.kind == "trigger_on_event" for ev in e.events)


def test_effect_attach_own_discard_to_bench_no_trigger() -> None:
    """回归（裁决保留「从手牌」限定）：discard 来源效果附着到备战 → 不触发
    （deck 来源回归由 WP8 清单 7 既有用例守护）。"""
    ramp_doc = parse_card_doc("""
card:
  name_group: 测试附能
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_discard, filters: [energy], choose: 1, destination: attach, args: {target_pool: own_bench}}
""")
    state = main_state(p0_extra_hand=(inst(60, CardDef(
        card_id="stub-测试附能", name="测试附能", supertype="trainer",
        trainer_subtype="物品")),))
    p0 = state.players[0].model_copy(update={
        "bench": (mon(70, pokemon("备战兽", hp=300)),),
        "discard": (jet(61),),
    })
    e = GameEngine(RandomSource(0))
    e.state = state.model_copy(update={"players": (p0, state.players[1])})
    e.card_effects = {"测试附能": ramp_doc, "喷射能量": JET_DOC}
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(61,)))  # 选弃牌区喷射
    e.apply(0, Action(kind="choose", choices=(70,)))  # 附着备战兽
    p0 = e.state.players[0]
    assert [c.iid for c in p0.bench[0].attached_energy] == [61]  # 已附着
    assert p0.active.current.iid == 1                            # 未换位
    assert not any(ev.kind == "trigger_on_event" for ev in e.events)
