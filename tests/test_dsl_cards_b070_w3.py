"""单卡 DSL 测试（task 070 WP3 批：11 张宝可梦卡中可表达的 4 张）：
从 cards/ 真实文件装载（load_card_doc），stub 引擎驱动效果全链路（含 chooser 挂起选择）。

本批 4 张：
- 密勒顿ex：串联装置（ability_manual once_per_turn，检索 ≤2 张【雷】基础宝可梦直放
  备战区 + 重洗）；光子引爆 220 + lock_attack 冷却（拉帝亚斯ex 同构）。
- N的莱希拉姆：力量愤怒 damage_counters_on_self ×20；纯真火焰 170 白板。
- 盖诺赛克特：ACE消除器（passive_static lock_play/ace_spec + holder_has_tool，
  task 069 WP5 落地口径，本测试验证真实文件挂载后的五门类锁行为）；磁力爆破 100 白板。
- 电电虫：电电充能（双 attach_energy own_deck 节点：草≤2 / 雷≤2 各自 up-to，
  逐张挂起任意分配附着；两节点各自内建重洗 = 洗牌 2 次 vs 原文 1 次，偏差已在
  cards/电电虫.yml 注释声明并报主会话核销）。

blocked 未写 7 张（缺词/缺形态，见主会话报告）：可达鸭 / 咕咕 / N的达摩狒狒 /
N的索罗亚克ex / 铁臂膀ex / 铁斑叶ex / 电蜘蛛。
"""

from pathlib import Path

from helpers import energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.state import AttackDef, CardDef, CardInstance

CARDS_DIR = Path(__file__).parent.parent / "cards"

MIRAIDON_DOC = load_card_doc(CARDS_DIR / "密勒顿ex.yml")
RESHIRAM_DOC = load_card_doc(CARDS_DIR / "N的莱希拉姆.yml")
GENESECT_DOC = load_card_doc(CARDS_DIR / "盖诺赛克特.yml")
JOLTIK_DOC = load_card_doc(CARDS_DIR / "电电虫.yml")


# ── 夹具（test_dsl_cards_t29.py 同型）─────────────────────────────────


def mon_card(
    name: str, *, hp: int = 500, energy_type: str | None = None, stage: int = 0,
    attacks: tuple = (), owner: str | None = None, has_ability: bool = False,
    evolves_from: str | None = None, retreat: int = 1, rule_box: str | None = None,
) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=stage, attacks=attacks, energy_type=energy_type,
        owner=owner, has_ability=has_ability, evolves_from=evolves_from,
        retreat_cost=retreat, rule_box=rule_box,
    )


def trainer(name: str, subtype: str, *, is_ace_spec: bool = False) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype=subtype, is_ace_spec=is_ace_spec)


def board(
    *, p0_active=None, p0_bench: tuple = (), p0_hand=None, p0_deck=None,
    p1_active=None, p1_bench: tuple = (), p1_hand=None,
    stadium: CardInstance | None = None, turn: int = 2, current: int = 0,
    effects: dict,
) -> GameEngine:
    """main 阶段局面：双方场上/手牌/牌库与公共竞技场可调。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": p0_active if p0_active is not None else in_play(1, mon_card("战斗兽")),
        "bench": p0_bench,
    })
    if p0_hand is not None:
        p0 = p0.model_copy(update={"hand": p0_hand})
    if p0_deck is not None:
        p0 = p0.model_copy(update={"deck": p0_deck})
    p1 = state.players[1].model_copy(update={
        "active": p1_active if p1_active is not None
        else in_play(2, mon_card("硬兽", hp=500)),
        "bench": p1_bench,
    })
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
    update: dict[str, object] = {
        "players": (p0, p1), "turn": turn, "current_player": current,
    }
    if stadium is not None:
        update["stadium"] = stadium
        update["stadium_owner"] = 0
    e = engine_at(state.model_copy(update=update))
    e.card_effects = effects
    return e


def ability_iids(e: GameEngine, player: int = 0) -> list[int]:
    return [a.iid for a in e.legal_actions(player) if a.kind == "use_ability"]


def attack_kinds(e: GameEngine, player: int = 0) -> list[int]:
    return [a.attack_index for a in e.legal_actions(player) if a.kind == "attack"]


def iids_of(e: GameEngine, player: int, kind: str) -> list[int]:
    return [a.iid for a in e.legal_actions(player) if a.kind == kind]


def prim_results(e: GameEngine, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


# ── 密勒顿ex（串联装置检索铺场 / 光子引爆 lock_attack）───────────────────


def miraidon() -> CardDef:
    return mon_card(
        "密勒顿ex", hp=220, energy_type="雷", rule_box="ex", has_ability=True,
        attacks=(AttackDef(name="光子引爆", cost=("雷", "雷", "无"), damage=None),),
    )


def miraidon_deck() -> tuple:
    return (
        inst(300, mon_card("雷小兽甲", hp=60, energy_type="雷")),   # 命中：雷基础
        inst(301, mon_card("火小兽", hp=60, energy_type="火")),     # 非雷排除
        inst(302, mon_card("雷一阶", hp=90, energy_type="雷", stage=1)),  # 1阶排除
        inst(303, mon_card("雷小兽乙", hp=60, energy_type="雷")),   # 命中
        inst(304, energy("基本雷能量", "雷")),                      # 能量排除
        inst(305, mon_card("雷小兽丙", hp=60, energy_type="雷")),   # 命中（留库）
    )


def miraidon_ability_engine(*, bench: tuple = (), deck=None) -> GameEngine:
    return board(
        p0_active=in_play(1, miraidon()),
        p0_bench=bench,
        p0_deck=deck if deck is not None else miraidon_deck(),
        effects={"密勒顿ex": MIRAIDON_DOC},
    )


def test_密勒顿ex_串联装置_检索至多2张雷基础入备战() -> None:
    """发动后检索池仅【雷】属性【基础】（火/1阶/能量排除），选 2 张直放备战区
    （登记当回合登场）+ 重洗，牌库 = 原库 − 选中；once_per_turn 本只当回合不可再用。"""
    e = miraidon_ability_engine(bench=(in_play(70, miraidon()),))
    assert ability_iids(e) == [1, 70]
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.pool == "own_deck" and pc.pool_iids == (300, 303, 305)
    assert pc.min_choose == 0 and pc.max_choose == 2
    e.apply(0, Action(kind="choose", choices=(300, 303)))
    p0 = e.state.players[0]
    assert [m.current.iid for m in p0.bench] == [70, 300, 303]
    assert {300, 303} <= p0.entered_play_this_turn
    assert sorted(c.iid for c in p0.deck) == [301, 302, 304, 305]
    assert any(ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"
               for ev in e.events)
    assert e.state.phase == "main" and e.state.current_player == 0
    assert ability_iids(e) == [70]  # once_per_turn：本只已用，备战那只仍可


def test_密勒顿ex_串联装置_备战满或牌库无匹配不枚举() -> None:
    """可行性门：备战区满（5 只）/ 牌库无【雷】基础 → 特性不枚举。"""
    full = tuple(in_play(70 + i, mon_card(f"备战{i}")) for i in range(5))
    e = miraidon_ability_engine(bench=full)
    assert ability_iids(e) == []
    e2 = miraidon_ability_engine(deck=(inst(310, mon_card("火小兽", energy_type="火")),))
    assert ability_iids(e2) == []


def miraidon_attack_engine() -> GameEngine:
    mon = in_play(1, miraidon(), 0).model_copy(update={
        "attached_energy": (inst(9001, energy("基本雷能量", "雷")),
                            inst(9002, energy("基本雷能量", "雷")),
                            inst(9003, energy()))})
    return board(p0_active=mon, effects={"密勒顿ex": MIRAIDON_DOC})


def test_密勒顿ex_光子引爆_220加下个自己回合锁定() -> None:
    """光子引爆 220 + lock_attack：turn 2 使用 → turn 3 锁定不枚举 → turn 4 解禁。"""
    e = miraidon_attack_engine()
    assert attack_kinds(e) == [0]
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 220
    assert e.state.players[0].active.attack_locks == ("光子引爆",)
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 3
    assert attack_kinds(e) == []  # 锁定（本卡仅单招式）
    e.apply(0, Action(kind="end_turn"))
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 4
    assert attack_kinds(e) == [0]  # 解禁


# ── N的莱希拉姆（力量愤怒 ×20 计数 / 纯真火焰 170 白板）────────────────────


def reshiram() -> CardDef:
    return mon_card(
        "N的莱希拉姆", hp=130, energy_type="龙", retreat=2,
        attacks=(
            AttackDef(name="力量愤怒", cost=("火", "雷"), damage=None),
            AttackDef(name="纯真火焰", cost=("火", "火", "雷", "无"), damage=170),
        ),
    )


def reshiram_engine(*, self_damage: int = 0) -> GameEngine:
    mon = in_play(1, reshiram(), 0).model_copy(update={
        "attached_energy": (inst(9001, energy("基本火能量", "火")),
                            inst(9002, energy("基本雷能量", "雷"))),
        "damage": self_damage})
    return board(p0_active=mon, effects={"N的莱希拉姆": RESHIRAM_DOC})


def test_N的莱希拉姆_力量愤怒_自身指示物乘20() -> None:
    """身上 3 个伤害指示物（30 伤害）→ 力量愤怒 3×20=60；0 指示物 → 0 伤害。"""
    e = reshiram_engine(self_damage=30)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 60
    assert e.state.phase == "main" and e.state.current_player == 1
    e0 = reshiram_engine()
    e0.apply(0, Action(kind="attack", attack_index=0))
    assert e0.state.players[1].active.damage == 0


def test_N的莱希拉姆_纯真火焰_170白板() -> None:
    """纯真火焰无效果文：引擎白板伤害 170，DSL 不绑定（无 effect_primitive 事件）。"""
    mon = in_play(1, reshiram(), 0).model_copy(update={
        "attached_energy": (inst(9001, energy("基本火能量", "火")),
                            inst(9002, energy("基本火能量", "火")),
                            inst(9003, energy("基本雷能量", "雷")),
                            inst(9004, energy()))})
    e = board(p0_active=mon, effects={"N的莱希拉姆": RESHIRAM_DOC})
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 170
    assert not [ev for ev in e.events if ev.kind == "effect_primitive"]


# ── 盖诺赛克特（ACE消除器五门类锁 / 磁力爆破 100 白板）─────────────────────


ACE_ITEM_DOC = parse_card_doc("""
card:
  name_group: ACE物品
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")

NORMAL_ITEM_DOC = parse_card_doc("""
card:
  name_group: 普通物品
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")

ACE_SUPPORTER_DOC = parse_card_doc("""
card:
  name_group: ACE支援者
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 2}
""")

SUPPRESS_STADIUM_DOC = parse_card_doc("""
card:
  name_group: 测试塔
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_ability, args: {types: [钢]}}
""")


def genesect() -> CardDef:
    return mon_card(
        "盖诺赛克特", hp=110, energy_type="钢", has_ability=True, retreat=2,
        attacks=(AttackDef(name="磁力爆破", cost=("钢", "无", "无"), damage=100),),
    )


def ace_hand() -> tuple:
    return (
        inst(50, trainer("ACE物品", "物品", is_ace_spec=True)),
        inst(51, trainer("普通物品", "物品")),
        inst(52, trainer("ACE支援者", "支援者", is_ace_spec=True)),
        inst(53, trainer("ACE竞技场", "竞技场", is_ace_spec=True)),
        inst(54, trainer("ACE道具", "宝可梦道具", is_ace_spec=True)),
        inst(55, CardDef(card_id="stub-ACE能量", name="ACE能量", supertype="energy",
                         energy_type="火", is_basic_energy=False, is_ace_spec=True)),
    )


ACE_EFFECTS = {
    "盖诺赛克特": GENESECT_DOC, "ACE物品": ACE_ITEM_DOC,
    "普通物品": NORMAL_ITEM_DOC, "ACE支援者": ACE_SUPPORTER_DOC,
}


def genesect_engine(*, with_tool: bool = True, stadium: CardInstance | None = None,
                    extra_effects: dict | None = None) -> GameEngine:
    """p1 备战区盖诺赛克特（可选持道具）；p0 手牌 = ACE 五门类 + 普通物品。"""
    holder = in_play(80, genesect())
    if with_tool:
        holder = holder.model_copy(update={
            "attached_tool": inst(91, trainer("望远镜", "宝可梦道具"))})
    return board(
        p1_bench=(holder,), p0_hand=ace_hand(), stadium=stadium,
        effects={**ACE_EFFECTS, **(extra_effects or {})},
    )


def assert_ace_all_locked(e: GameEngine) -> None:
    """五门类 ACE 全部不枚举（D-069-2 广义口径）。"""
    assert 50 not in iids_of(e, 0, "play_trainer")   # ACE 物品
    assert 52 not in iids_of(e, 0, "play_trainer")   # ACE 支援者
    assert 53 not in iids_of(e, 0, "play_stadium")   # ACE 竞技场
    assert 54 not in iids_of(e, 0, "attach_tool")    # ACE 道具附着
    assert 55 not in iids_of(e, 0, "attach_energy")  # ACE 能量附着


def assert_ace_all_free(e: GameEngine) -> None:
    assert 50 in iids_of(e, 0, "play_trainer")
    assert 51 in iids_of(e, 0, "play_trainer")  # 非 ACE 物品本就不受锁影响
    assert 52 in iids_of(e, 0, "play_trainer")
    assert 53 in iids_of(e, 0, "play_stadium")
    assert 54 in iids_of(e, 0, "attach_tool")
    assert 55 in iids_of(e, 0, "attach_energy")


def test_盖诺赛克特_ACE消除器_持道具锁对手五门类() -> None:
    """盖诺赛克特持道具在对手场 → 我方 ACE 物品/支援者/竞技场/道具附着/能量附着
    全锁；非 ACE 物品照常。"""
    e = genesect_engine()
    assert_ace_all_locked(e)
    assert 51 in iids_of(e, 0, "play_trainer")


def test_盖诺赛克特_ACE消除器_无道具不锁() -> None:
    """holder_has_tool 条件：身上无「宝可梦道具」→ 不锁。"""
    e = genesect_engine(with_tool=False)
    assert_ace_all_free(e)


def test_盖诺赛克特_ACE消除器_特性被消除即解锁() -> None:
    """suppress_ability（测试塔 types=[钢]，盖诺赛克特为【钢】）→ 宝可梦卡来源
    声明失效，ACE 五门类恢复可打出（task 029 D-029-1 守卫落点④）。"""
    e = genesect_engine(
        stadium=inst(399, trainer("测试塔", "竞技场")),
        extra_effects={"测试塔": SUPPRESS_STADIUM_DOC},
    )
    assert_ace_all_free(e)


def test_盖诺赛克特_磁力爆破_100白板() -> None:
    """磁力爆破无效果文：引擎白板伤害 100，DSL 不绑定（无 effect_primitive 事件）。"""
    mon = in_play(1, genesect(), 0).model_copy(update={
        "attached_energy": (inst(9001, energy("基本钢能量", "钢")),
                            inst(9002, energy()), inst(9003, energy()))})
    e = board(p0_active=mon, effects={"盖诺赛克特": GENESECT_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 100
    assert not [ev for ev in e.events if ev.kind == "effect_primitive"]


# ── 电电虫（电电充能：草/雷各至多 2 张任意附着）────────────────────────────


def joltik() -> CardDef:
    return mon_card(
        "电电虫", hp=30, energy_type="雷",
        attacks=(AttackDef(name="电电充能", cost=("无",), damage=None),),
    )


def joltik_engine(*, deck: tuple | None = None) -> GameEngine:
    """p0 战斗场电电虫（1 雷能量付【无】费）+ 备战兽；牌库草/雷能量各 2 + 杂牌。"""
    mon = in_play(1, joltik(), 0).model_copy(update={
        "attached_energy": (inst(9001, energy("基本雷能量", "雷")),)})
    return board(
        p0_active=mon,
        p0_bench=(in_play(70, mon_card("备战兽")),),
        p0_deck=deck if deck is not None else (
            inst(300, energy("基本草能量", "草")),
            inst(301, energy("基本草能量", "草")),
            inst(302, energy("基本雷能量", "雷")),
            inst(303, energy("基本雷能量", "雷")),
            inst(310, mon_card("库怪")),
            inst(311, energy("基本火能量", "火")),
        ),
        effects={"电电虫": JOLTIK_DOC},
    )


def test_电电虫_电电充能_草雷各至多2张任意附着() -> None:
    """节点1 草能量池（≤2）→ 逐张选目标（300→备战兽，301→电电虫）；节点2 雷能量池
    （≤2，池按重洗后牌库序）→ 303→备战兽；牌库 = 原库 − 3 张，两节点各报重洗。"""
    e = joltik_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.pool == "own_deck" and pc.pool_iids == (300, 301)
    assert pc.min_choose == 0 and pc.max_choose == 2
    e.apply(0, Action(kind="choose", choices=(300, 301)))
    e.apply(0, Action(kind="choose", choices=(70,)))  # 草① → 备战兽
    e.apply(0, Action(kind="choose", choices=(1,)))   # 草② → 电电虫
    assert e.state.phase == "choice"
    pc2 = e.state.pending_choice
    assert pc2.pool == "own_deck" and set(pc2.pool_iids) == {302, 303}
    e.apply(0, Action(kind="choose", choices=(303,)))
    e.apply(0, Action(kind="choose", choices=(70,)))  # 雷① → 备战兽
    assert e.state.phase == "main" and e.state.current_player == 1
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [9001, 301]
    assert [c.iid for c in p0.bench[0].attached_energy] == [300, 303]
    assert sorted(c.iid for c in p0.deck) == [302, 310, 311]
    results = prim_results(e, "attach_energy")
    assert len(results) == 2
    assert results[0]["attached"] == 2 and results[0]["shuffled"] is True
    assert results[1]["attached"] == 1 and results[1]["shuffled"] is True


def test_电电虫_电电充能_选0仍重洗() -> None:
    """双侧各选 0 张 → 不附着、不进目标选择，重洗依然成立（池非空挂起口径）。"""
    e = joltik_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=()))  # 草选 0
    e.apply(0, Action(kind="choose", choices=()))  # 雷选 0
    assert e.state.phase == "main" and e.state.current_player == 1
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [9001]
    assert p0.bench[0].attached_energy == ()
    assert sorted(c.iid for c in p0.deck) == [300, 301, 302, 303, 310, 311]
    results = prim_results(e, "attach_energy")
    assert [r["attached"] for r in results] == [0, 0]
    assert all(r["shuffled"] for r in results)


def test_电电虫_电电充能_牌库无草能量_雷侧照常() -> None:
    """牌库无草能量：节点1 池空不挂起（仅重洗），节点2 雷侧照常检索附着。"""
    e = joltik_engine(deck=(
        inst(302, energy("基本雷能量", "雷")),
        inst(310, mon_card("库怪")),
    ))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"
    assert e.state.pending_choice.pool_iids == (302,)
    e.apply(0, Action(kind="choose", choices=(302,)))
    e.apply(0, Action(kind="choose", choices=(1,)))  # 雷① → 电电虫
    assert e.state.phase == "main" and e.state.current_player == 1
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [9001, 302]
    assert [c.iid for c in p0.deck] == [310]
    results = prim_results(e, "attach_energy")
    assert [r["attached"] for r in results] == [0, 1]
    assert all(r["shuffled"] for r in results)
