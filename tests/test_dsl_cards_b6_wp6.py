"""单卡 DSL 测试（task 026 WP6）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批卡（hand_disrupt / bench_size 覆写 / choose_groups / distinct+split /
deck_top 有序 / own_ko_by_attack+lock_retreat / protection / devolve+学习器载体）：
- 雪童子（H 标 CSV7C-057 惊吓等价类 2 印刷）：惊吓 20 + hand_disrupt（随机选→
  reveal→回对手库重洗）。
- 零之大空洞（H 标 5 印刷）：bench_size 8 覆写 + 失效自选缩减（bench_shrink）。
- 小刚的发掘（I 标 5 印刷）：search choose_groups 二选一（基础 up-to 2 ∪ 进化 up-to 1）。
- 赤松（H 标 6 印刷）：distinct=energy_type + split=hand_attach 拆分去向。
- 暗码迷的解读（H 标 6 印刷）：deck_top ordered 有序回顶（选择顺序 FIFO）。
- 沙铃仙人掌（I 标 2 印刷）：own_ko_by_attack 炸裂针刺 + 穷追不舍 lock_retreat。
- 火恐龙-大字爆炎（G 标 3 印刷）：discard own_attached_energy choose=1 + damage 90。
- 火恐龙-闪焰之幕（G 标 4 印刷）：protection opponent_attack_effects。
- 招式学习器 退化（G 标 4 印刷）：grant_attack discard_at_turn_end + devolve。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state, stage1

from battlefrontier.dsl import ExecutionContext, run_effect
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    InPlayPokemon,
    SpecialCondition,
)

CARDS_DIR = Path(__file__).parent.parent / "cards"

SNOWLUNT_DOC = load_card_doc(CARDS_DIR / "雪童子.yml")
HOLE_DOC = load_card_doc(CARDS_DIR / "零之大空洞.yml")
BROCK_DOC = load_card_doc(CARDS_DIR / "小刚的发掘.yml")
AKAMATSU_DOC = load_card_doc(CARDS_DIR / "赤松.yml")
CIPHER_DOC = load_card_doc(CARDS_DIR / "暗码迷的解读.yml")
CACTUS_DOC = load_card_doc(CARDS_DIR / "沙铃仙人掌.yml")
BLAZE_DOC = load_card_doc(CARDS_DIR / "火恐龙-大字爆炎.yml")
VEIL_DOC = load_card_doc(CARDS_DIR / "火恐龙-闪焰之幕.yml")
LEARNER_DOC = load_card_doc(CARDS_DIR / "招式学习器 退化.yml")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def stadium_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="竞技场")


def tool_card(name: str, attacks: tuple = ()) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具", attacks=attacks)


def stage2(name: str, evolves_from: str, hp: int = 100) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=hp, stage=2, evolves_from=evolves_from,
                   attacks=(AttackDef(name="打击", cost=("无",), damage=40),))


def stacked(*cards, damage: int = 0, conditions=frozenset()) -> InPlayPokemon:
    return InPlayPokemon(stack=tuple(cards), damage=damage, conditions=conditions)


def engine_at_seed(state, seed: int) -> GameEngine:
    e = GameEngine(RandomSource(seed))
    e.state = state
    return e


def prim_results(e, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


def attack_engine(doc, attacker: CardDef, *, p0_bench=(), p0_energies=(),
                  p1_active=None, p1_bench=(), p1_hand=None, p1_deck=None,
                  seed: int = 0, turn: int = 2, extra_effects: dict | None = None):
    """main 阶段：p0 战斗场攻击者（iid 1），p1 战斗场/手牌/牌库可调。"""
    state = main_state()
    active = in_play(1, attacker)
    if p0_energies:
        active = active.model_copy(update={"attached_energy": p0_energies})
    p0 = state.players[0].model_copy(update={"active": active, "bench": p0_bench})
    p1 = state.players[1].model_copy(update={
        "bench": p1_bench,
        "active": in_play(2, basic("硬兽", hp=500), 1),
    })
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
    if p1_deck is not None:
        p1 = p1.model_copy(update={"deck": p1_deck})
    e = engine_at_seed(state.model_copy(update={
        "players": (p0, p1), "turn": turn,
    }), seed)
    e.card_effects = {attacker.name: doc, **(extra_effects or {})}
    return e


def play_engine(doc, name: str, *, kind="supporter", deck=None, extra_hand: tuple = (),
                p0_bench: tuple = (), p1_active=None, p1_bench: tuple = (), seed: int = 0):
    """main 阶段：p0 手牌含测试训练家卡（iid 60）。"""
    card_fn = item_card if kind == "item" else supporter_card
    state = main_state(p0_extra_hand=(inst(60, card_fn(name)),) + extra_hand)
    p0 = state.players[0].model_copy(update={"bench": p0_bench})
    if deck is not None:
        p0 = p0.model_copy(update={"deck": deck})
    p1 = state.players[1].model_copy(update={"bench": p1_bench})
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}), seed)
    e.card_effects = {name: doc}
    return e


# ── 雪童子（惊吓 hand_disrupt）（清单 19）──────────────────────────────────────


def snowlunt() -> CardDef:
    return CardDef(
        card_id="stub-雪童子", name="雪童子", supertype="pokemon",
        hp=60, stage=0, energy_type="水", weakness="钢", retreat_cost=1,
        attacks=(AttackDef(name="惊吓", cost=("水", "无"), damage=None),),
    )


def snow_energies() -> tuple:
    return (inst(9001, energy("水能量", "水")), inst(9002, energy("水能量", "水")))


def test_雪童子_惊吓_全流与种子复现():
    """惊吓：伤害 20 + 随机选对手 1 张手牌（reveal 事件）→ 回对手牌库重洗；
    同种子复跑扰乱对象与对手牌库序逐局一致。"""
    hand = (inst(50, basic("对手甲")), inst(51, basic("对手乙")), inst(52, energy()))
    deck = tuple(inst(300 + i, basic(f"对手库{i}")) for i in range(5))
    runs = []
    for _ in range(2):
        e = attack_engine(SNOWLUNT_DOC, snowlunt(), p0_energies=snow_energies(),
                          p1_hand=hand, p1_deck=deck, seed=7)
        e.apply(0, Action(kind="attack", attack_index=0))
        p1 = e.state.players[1]
        assert p1.active.damage == 20  # 伤害照算
        reveal = next(ev for ev in e.events if ev.kind == "reveal")
        disrupted = reveal.detail["iids"][0]
        assert disrupted in (50, 51, 52)  # 随机对象来自对手手牌
        # 扰乱 −1 手 +1 库，对手回合开始抽 1 抵消：hand/deck 总数不变、合集不变
        assert len(p1.hand) == 3 and len(p1.deck) == 5
        assert sorted(c.iid for c in (*p1.hand, *p1.deck)) == [
            50, 51, 52, 300, 301, 302, 303, 304,
        ]
        assert e.state.phase == "main" and e.state.current_player == 1
        runs.append((disrupted, tuple(c.iid for c in p1.deck)))
    assert runs[0] == runs[1]  # 种子确定性


def test_雪童子_惊吓_对手空手noop伤害照算():
    """对手空手 → 扰乱 no-op（empty_hand，无 reveal），伤害 20 照算（D-WP6-1）。"""
    e = attack_engine(SNOWLUNT_DOC, snowlunt(), p0_energies=snow_energies(),
                      p1_hand=())
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
    assert not [ev for ev in e.events if ev.kind == "reveal"]
    assert prim_results(e, "hand_disrupt") == [{"disrupted": 0, "reason": "empty_hand"}]
    assert e.state.phase == "main" and e.state.current_player == 1


# ── 零之大空洞（bench_size 覆写 + 失效缩减）（清单 20）─────────────────────────


def tera_mon(name: str = "太晶兽", hp: int = 130) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, is_tera=True,
        attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
    )


def bench_mons(start: int, n: int) -> tuple:
    return tuple(in_play(start + i, basic(f"备战{start + i}")) for i in range(n))


def hole_engine(*, p0_active=None, p0_bench: tuple = (), p0_hand=None,
                p1_active=None, p1_bench: tuple = (), p1_hand=None,
                owner: int = 0, current: int = 0, turn: int = 3):
    """main 阶段：场上挂零之大空洞（iid 399，默认持有者 p0），真实卡文档。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={"bench": p0_bench})
    if p0_active is not None:
        p0 = p0.model_copy(update={"active": p0_active})
    if p0_hand is not None:
        p0 = p0.model_copy(update={"hand": p0_hand})
    p1 = state.players[1].model_copy(update={"bench": p1_bench})
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
    e = engine_at(state.model_copy(update={
        "players": (p0, p1), "current_player": current, "turn": turn,
        "stadium": inst(399, stadium_card("零之大空洞")), "stadium_owner": owner,
    }))
    e.card_effects = {"零之大空洞": HOLE_DOC}
    return e


def test_零之大空洞_太晶在场备战8上限():
    """太晶在场 + 零之大空洞 → 备战区手动放置放到 8 只（第 9 只不枚举）。"""
    e = hole_engine(p0_active=in_play(1, tera_mon()),
                    p0_bench=bench_mons(70, 5),
                    p0_hand=tuple(inst(50 + i, basic(f"手{i}")) for i in range(4)))
    for _ in range(3):
        acts = [a for a in e.legal_actions(0) if a.kind == "place_bench"]
        assert acts
        e.apply(0, acts[0])
    assert len(e.state.players[0].bench) == 8
    assert not [a for a in e.legal_actions(0) if a.kind == "place_bench"]


def test_零之大空洞_失效自选缩减无奖赏():
    """竞技场被顶 → 超容方（持有者）bench_shrink 自选弃至 5：整叠进弃牌、
    非昏厥无奖赏、完成后回出牌方主阶段。"""
    e = hole_engine(p0_active=in_play(1, tera_mon()),
                    p0_bench=bench_mons(70, 6),
                    p1_hand=(inst(90, stadium_card("新竞技场")),),
                    current=1, owner=0)
    e.apply(1, Action(kind="play_stadium", iid=90))
    assert e.state.phase == "bench_shrink" and e.state.current_player == 0
    acts = e.legal_actions(0)
    assert {a.kind for a in acts} == {"shrink_bench"}
    assert {a.choices for a in acts} == {(i,) for i in range(70, 76)}
    e.apply(0, Action(kind="shrink_bench", choices=(72,)))
    p0 = e.state.players[0]
    assert [b.current.iid for b in p0.bench] == [70, 71, 73, 74, 75]
    assert 72 in [c.iid for c in p0.discard]
    assert 399 in [c.iid for c in p0.discard]  # 旧竞技场进持有者弃牌区
    assert not [ev for ev in e.events if ev.kind == "take_prize"]  # 缩减非昏厥无奖赏
    assert any(ev.kind == "bench_shrink" for ev in e.events)
    assert e.state.phase == "main" and e.state.current_player == 1  # 回出牌方主阶段


def test_零之大空洞_双方同缩持有者先():
    """双方同时超容 →（旧）竞技场持有者先执行缩减（原文「由这张卡牌的持有者开始执行」）。"""
    e = hole_engine(p0_active=in_play(1, tera_mon()),
                    p0_bench=bench_mons(70, 6),
                    p1_active=in_play(2, tera_mon("对手太晶")),
                    p1_bench=bench_mons(80, 6),
                    p1_hand=(inst(90, stadium_card("新竞技场")),),
                    current=1, owner=0)
    e.apply(1, Action(kind="play_stadium", iid=90))
    assert e.state.bench_shrink_queue == (0, 1)  # 持有者 p0 先
    assert e.state.phase == "bench_shrink" and e.state.current_player == 0
    e.apply(0, Action(kind="shrink_bench", choices=(70,)))
    assert e.state.phase == "bench_shrink" and e.state.current_player == 1
    e.apply(1, Action(kind="shrink_bench", choices=(80,)))
    assert e.state.phase == "main" and e.state.current_player == 1
    assert len(e.state.players[0].bench) == 5
    assert len(e.state.players[1].bench) == 5


# ── 小刚的发掘（search choose_groups 二选一）（清单 21）────────────────────────


def brock_deck() -> tuple:
    return (
        inst(100, basic("基甲")), inst(101, basic("基乙")),
        inst(102, stage1("进甲", "基甲")), inst(103, stage1("进乙", "基乙")),
        inst(104, item_card("物品甲")), inst(105, energy()),
    )


def brock_engine(deck=None):
    return play_engine(BROCK_DOC, "小刚的发掘",
                       deck=deck if deck is not None else brock_deck())


def test_小刚的发掘_枚举互斥():
    """枚举 = 基础子集（0-2 张）∪ 进化单选（0-1 张），混合不可达（「或」互斥）。"""
    e = brock_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.pool_iids == (100, 101, 102, 103)  # 训练家/能量不进池
    choices = {a.choices for a in e.legal_actions(0)}
    assert choices == {(), (100,), (101,), (100, 101), (102,), (103,)}


def test_小刚的发掘_基础upto2全流():
    """选 2 张基础 → 入手 + reveal（给对手看过）+ 重洗，回主阶段。"""
    e = brock_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(100, 101)))
    p0 = e.state.players[0]
    assert {100, 101} <= {c.iid for c in p0.hand}
    assert sorted(c.iid for c in p0.deck) == [102, 103, 104, 105]
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert {100, 101} <= set(reveal.detail["iids"])
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


def test_小刚的发掘_进化upto1():
    """进化分支：选 1 张进化宝可梦入手（基础不可同选，互斥由枚举保证）。"""
    e = brock_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(103,)))
    p0 = e.state.players[0]
    assert 103 in [c.iid for c in p0.hand]
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 104, 105]
    assert e.state.phase == "main" and e.state.current_player == 0


def test_小刚的发掘_空选仍重洗():
    """选 0（「最多」可以不找）→ no-op，重洗仍执行。"""
    e = brock_engine()
    hand_before = tuple(c.iid for c in e.state.players[0].hand)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert tuple(c.iid for c in p0.hand) == tuple(i for i in hand_before if i != 60)
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 104, 105]
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


# ── 赤松（distinct=energy_type + split=hand_attach）（清单 22）─────────────────


def aka_deck() -> tuple:
    return (
        inst(100, energy("火能量", "火")), inst(101, energy("水能量", "水")),
        inst(102, energy("草能量", "草")), inst(103, energy("火能量二", "火")),
        inst(104, basic("宝可梦甲")),
    )


def aka_engine(deck=None, **kw):
    return play_engine(AKAMATSU_DOC, "赤松",
                       deck=deck if deck is not None else aka_deck(), **kw)


def test_赤松_双属性选满拆分():
    """选 2 张属性互异能量（同属性对不可达）→ 段2 选 1 入手 → 段3 剩余附着。"""
    e = aka_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    choices = {a.choices for a in e.legal_actions(0)}
    assert (100, 103) not in choices  # 同属性对（皆火）排除
    assert (100, 101) in choices and (101, 102) in choices
    e.apply(0, Action(kind="choose", choices=(100, 101)))  # 火 + 水
    pc2 = e.state.pending_choice
    assert pc2.pool_iids == (100, 101) and pc2.min_choose == 1 and pc2.max_choose == 1
    e.apply(0, Action(kind="choose", choices=(101,)))  # 水入手
    assert 101 in [c.iid for c in e.state.players[0].hand]
    pc3 = e.state.pending_choice
    assert pc3.pool == "own_pokemon_in_play" and pc3.min_choose == 1
    e.apply(0, Action(kind="choose", choices=(1,)))  # 剩余（火）附着战斗场
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [9010, 100]
    assert sorted(c.iid for c in p0.deck) == [102, 103, 104]
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert 101 in reveal.detail["iids"]
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


def test_赤松_单属性收缩为1():
    """用户补充场景（D-WP6-4）：牌库仅单属性能量 → 可选上限收缩 1，
    选 1 张直接入手，无段2/段3，重洗执行。"""
    deck = (inst(100, energy("火能量", "火")), inst(103, energy("火能量二", "火")),
            inst(104, basic("宝可梦甲")))
    e = aka_engine(deck=deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.max_choose == 1  # 单桶收缩
    choices = {a.choices for a in e.legal_actions(0)}
    assert choices == {(), (100,), (103,)}
    e.apply(0, Action(kind="choose", choices=(103,)))
    p0 = e.state.players[0]
    assert 103 in [c.iid for c in p0.hand]
    assert e.state.pending_choice is None  # 无后续段
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


def test_赤松_空选仍重洗():
    """选 0 → 全 no-op（无段2/段3），重洗仍执行。"""
    e = aka_engine()
    hand_before = tuple(c.iid for c in e.state.players[0].hand)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert tuple(c.iid for c in p0.hand) == tuple(i for i in hand_before if i != 60)
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 104]
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


# ── 暗码迷的解读（deck_top 有序去向）（清单 23）────────────────────────────────


def cipher_engine(deck=None, seed: int = 0):
    d = deck if deck is not None else tuple(
        inst(100 + i, basic(f"库{i}")) for i in range(10)
    )
    return play_engine(CIPHER_DOC, "暗码迷的解读", deck=d, seed=seed)


def test_暗码迷的解读_选2有序回顶_余库重洗():
    """选择顺序即牌顶 FIFO：(103,101) → deck[0]=103, deck[1]=101；逆序 (101,103)
    是另一合法行动；余库集合不变且本节点内重洗（同种子复跑牌序一致）。"""
    orders = []
    for _ in range(2):
        e = cipher_engine()
        e.apply(0, Action(kind="play_trainer", iid=60))
        acts = e.legal_actions(0)
        assert Action(kind="choose", choices=(103, 101)) in acts
        assert Action(kind="choose", choices=(101, 103)) in acts  # 有序：两者皆合法
        e.apply(0, Action(kind="choose", choices=(103, 101)))
        deck = e.state.players[0].deck
        assert (deck[0].iid, deck[1].iid) == (103, 101)
        assert len(deck) == 10
        assert sorted(c.iid for c in deck[2:]) == [100, 102, 104, 105, 106, 107, 108, 109]
        orders.append(tuple(c.iid for c in deck))
    assert orders[0] == orders[1]  # 余库重洗走单一随机源


def test_暗码迷的解读_选0仅重洗():
    """选 0 → 仅整库重洗（「剩余的牌库重洗」空选依然成立），牌顶无置入。"""
    orders = []
    for _ in range(2):
        e = cipher_engine()
        e.apply(0, Action(kind="play_trainer", iid=60))
        e.apply(0, Action(kind="choose", choices=()))
        deck = e.state.players[0].deck
        assert len(deck) == 10
        assert sorted(c.iid for c in deck) == list(range(100, 110))
        orders.append(tuple(c.iid for c in deck))
        assert e.state.phase == "main" and e.state.current_player == 0
    assert orders[0] == orders[1]


def test_暗码迷的解读_牌库不足收缩():
    """牌库仅 1 张 → max 收缩 1；选 1 张置回牌顶（等价原位）。"""
    e = cipher_engine(deck=(inst(100, basic("独卡")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    choices = {a.choices for a in e.legal_actions(0)}
    assert choices == {(), (100,)}
    e.apply(0, Action(kind="choose", choices=(100,)))
    assert [c.iid for c in e.state.players[0].deck] == [100]


# ── 沙铃仙人掌（炸裂针刺 own_ko_by_attack + 穷追不舍 lock_retreat）（清单 24）───


def cactus(hp: int = 110) -> CardDef:
    return CardDef(
        card_id="stub-沙铃仙人掌", name="沙铃仙人掌", supertype="pokemon",
        hp=hp, stage=0, energy_type="草", weakness="火", retreat_cost=2,
        attacks=(AttackDef(name="穷追不舍", cost=("无",), damage=None),),
    )


def test_沙铃仙人掌_炸裂针刺_受招式伤害昏厥触发():
    """战斗场受对手招式伤害昏厥 → 触发，攻击方 +6 指示物（60）；换上后进其回合。"""
    e = attack_engine(None, basic("攻击兽", hp=200, damage=100, cost=1),
                      p0_energies=(inst(9001, energy()),),
                      p1_active=in_play(2, cactus(hp=50)),
                      p1_bench=(in_play(80, basic("对手备战")),),
                      extra_effects={"沙铃仙人掌": CACTUS_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert any(ev.kind == "trigger_on_event"
               and ev.detail.get("event") == "own_ko_by_attack" for ev in e.events)
    assert e.state.players[0].active.damage == 60  # 针刺反噬
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 1


def test_沙铃仙人掌_炸裂针刺_效果指示物致昏厥不触发():
    """反例：物品效果指示物致昏厥（非招式伤害路径）→ 不触发。"""
    from battlefrontier.dsl import parse_card_doc

    counters_doc = parse_card_doc("""
card:
  name_group: 测试指示物
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 5}}
""")
    e = play_engine(counters_doc, "测试指示物", kind="item",
                    p1_active=in_play(2, cactus(hp=50)),
                    p1_bench=(in_play(80, basic("对手备战")),))
    e.card_effects["沙铃仙人掌"] = CACTUS_DOC
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(2,)))  # 50 伤害 KO 战斗场
    assert not [ev for ev in e.events
                if ev.kind == "trigger_on_event"
                and ev.detail.get("event") == "own_ko_by_attack"]
    assert e.state.players[0].active.damage == 0  # 无针刺反噬
    assert e.state.phase == "promote" and e.state.current_player == 1


def test_沙铃仙人掌_炸裂针刺_攻击方已离场noop():
    """触发排水时攻击方已离场（前序 ko_self）→ 针刺 no-op（attacker_gone）。"""
    from battlefrontier.dsl import parse_card_doc

    suicide_doc = parse_card_doc("""
card:
  name_group: 自爆兽
effects:
  - trigger: on_attack
    attack: 自爆
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 100}}
      - {action: ko_self, selector: self}
""")
    attacker = CardDef(
        card_id="stub-自爆兽", name="自爆兽", supertype="pokemon",
        hp=200, stage=0, attacks=(AttackDef(name="自爆", cost=("无",), damage=None),),
    )
    e = attack_engine(suicide_doc, attacker, p0_energies=(inst(9001, energy()),),
                      p0_bench=(in_play(70, basic("己方备战")),),
                      p1_active=in_play(2, cactus(hp=50)),
                      p1_bench=(in_play(80, basic("对手备战")),),
                      extra_effects={"沙铃仙人掌": CACTUS_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert any(ev.kind == "trigger_on_event"
               and ev.detail.get("event") == "own_ko_by_attack" for ev in e.events)
    results = prim_results(e, "place_damage_counters")
    assert results and results[0]["placed"] == 0
    assert results[0]["reason"] == "attacker_gone"


def test_沙铃仙人掌_穷追不舍_撤退锁门控与解除():
    """穷追不舍：伤害 20 + 目标撤退锁——下个其回合撤退不枚举；其回合结束解除，
    再下回合解禁。"""
    p1_active = in_play(2, basic("逃跑兽", retreat=1), 1)  # 附 1 能，撤退费 1
    e = attack_engine(CACTUS_DOC, cactus(), p0_energies=(inst(9001, energy()),),
                      p1_active=p1_active, p1_bench=(in_play(80, basic("对手备战")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20  # 伤害照算
    assert e.state.players[1].active.retreat_lock is True
    assert e.state.phase == "main" and e.state.current_player == 1
    assert not [a for a in e.legal_actions(1) if a.kind == "retreat"]  # 锁定
    e.apply(1, Action(kind="end_turn"))  # p1 回合结束 → 解除
    assert e.state.players[1].active.retreat_lock is False
    e.apply(0, Action(kind="end_turn"))  # → p1 下回合
    assert [a for a in e.legal_actions(1) if a.kind == "retreat"]  # 解禁


# ── 火恐龙-大字爆炎（discard own_attached_energy choose=1）（清单 25）───────────


def charmeleon_blaze() -> CardDef:
    return CardDef(
        card_id="stub-火恐龙", name="火恐龙", supertype="pokemon",
        hp=100, stage=1, evolves_from="小火龙", energy_type="火",
        weakness="水", retreat_cost=2,
        attacks=(
            AttackDef(name="烈焰", cost=("火",), damage=20),
            AttackDef(name="大字爆炎", cost=("火", "火", "火"), damage=None),
        ),
    )


def test_火恐龙_大字爆炎_弃1能90():
    """大字爆炎：伤害 90 + 弃置池收窄为来源自身附着能量（choose=1，
    备战区能量不进池）；弃 1 张进弃牌区。"""
    energies = tuple(inst(9001 + i, energy("火能量", "火")) for i in range(3))
    bench = in_play(70, basic("备战兽")).model_copy(update={
        "attached_energy": (inst(9070, energy("火能量", "火")),),
    })
    e = attack_engine(BLAZE_DOC, charmeleon_blaze(), p0_energies=energies,
                      p0_bench=(bench,))
    e.apply(0, Action(kind="attack", attack_index=1))
    pc = e.state.pending_choice
    assert pc.pool == "own_attached_energy"
    assert pc.pool_iids == (9001, 9002, 9003)  # 备战 9070 经 exclude 剔除
    e.apply(0, Action(kind="choose", choices=(9002,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [9001, 9003]
    assert [c.iid for c in p0.bench[0].attached_energy] == [9070]  # 备战能量不动
    assert 9002 in [c.iid for c in p0.discard]
    assert e.state.players[1].active.damage == 90
    assert e.state.phase == "main" and e.state.current_player == 1


def test_火恐龙_大字爆炎_无能量效果noop伤害照算():
    """来源无附着能量 → 弃置 no-op（discarded=0 不挂起），伤害 90 照算（宣言裁决）。"""
    e = attack_engine(BLAZE_DOC, charmeleon_blaze())  # 无能量（直跑绕过能量枚举门）
    ctx = ExecutionContext(engine=e, player=0,
                           source=e.state.players[0].active.current,
                           effect_id="test", trigger="on_attack")
    run_effect(ctx, BLAZE_DOC.effects[0])
    assert e.state.players[1].active.damage == 90
    assert e.state.pending_choice is None
    results = prim_results(e, "discard")
    assert results[0]["discarded"] == 0


# ── 火恐龙-闪焰之幕（protection opponent_attack_effects）（清单 25）─────────────


def charmeleon_veil() -> CardDef:
    return CardDef(
        card_id="stub-火恐龙", name="火恐龙", supertype="pokemon",
        hp=90, stage=1, evolves_from="小火龙", energy_type="火",
        attacks=(AttackDef(name="烈焰", cost=("火", "火"), damage=50),),
    )


def test_火恐龙_闪焰之幕_免疫对手招式附加效果():
    """闪焰之幕：对手招式附加效果（撤退锁）对持有者不适用；伤害本体不免疫
    （20 照算）。攻击方 = 沙铃仙人掌 穷追不舍（真实卡文档互验）。"""
    p1_active = in_play(2, charmeleon_veil(), 2)  # 附 2 能（撤退费 2 可付）
    e = attack_engine(CACTUS_DOC, cactus(), p0_energies=(inst(9001, energy()),),
                      p1_active=p1_active, p1_bench=(in_play(80, basic("对手备战")),),
                      extra_effects={"火恐龙": VEIL_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    assert p1.active.damage == 20  # 伤害照算
    assert p1.active.retreat_lock is False  # 撤退锁被免疫
    results = prim_results(e, "lock_retreat")
    assert results[0] == {"locked": False, "reason": "protected"}
    assert [a for a in e.legal_actions(1) if a.kind == "retreat"]  # 未锁可撤退


def test_火恐龙_闪焰之幕_免疫招式指示物():
    """对手招式伤害指示物被免疫（skipped_protected）；招式伤害本体 10 照算。"""
    from battlefrontier.dsl import parse_card_doc

    needle_doc = parse_card_doc("""
card:
  name_group: 针雨兽
effects:
  - trigger: on_attack
    attack: 针雨
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 10}}
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 3}}
""")
    attacker = CardDef(
        card_id="stub-针雨兽", name="针雨兽", supertype="pokemon",
        hp=200, stage=0, attacks=(AttackDef(name="针雨", cost=("无",), damage=None),),
    )
    e = attack_engine(needle_doc, attacker, p0_energies=(inst(9001, energy()),),
                      p1_active=in_play(2, charmeleon_veil()),
                      p1_bench=(in_play(80, basic("对手备战")),),
                      extra_effects={"火恐龙": VEIL_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(2,)))  # 指示物指战斗场
    p1 = e.state.players[1]
    assert p1.active.damage == 10  # 仅招式伤害；3 指示物被免疫
    results = prim_results(e, "place_damage_counters")
    assert results[0]["placed"] == 0
    assert results[0]["skipped_protected"] == [2]


# ── 招式学习器 退化（grant_attack + devolve）（清单 26）─────────────────────────


def learner() -> CardDef:
    return tool_card("招式学习器 退化",
                     attacks=(AttackDef(name="退化", cost=("无",), damage=None),))


def learner_engine(*, holder_energy: int = 1, holder_card=None, p1_active=None,
                   p1_bench: tuple = ()):
    """main 阶段：p0 战斗场持有者（iid 1）带学习器（iid 90）。"""
    holder = in_play(1, holder_card or basic("妙蛙种子"), holder_energy)
    holder = holder.model_copy(update={"attached_tool": inst(90, learner())})
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": holder})
    p1 = state.players[1]
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    if p1_bench:
        p1 = p1.model_copy(update={"bench": p1_bench})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"招式学习器 退化": LEARNER_DOC}
    return e


def test_招式学习器退化_附着后持有者可宣言():
    """学习器附着后授予招式「退化」接自身招式后（attack_index 1）；
    费用校验走既有路径（能量不足不枚举）。"""
    e = learner_engine(holder_energy=1)
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert [a.attack_index for a in attacks] == [0, 1]  # 0=打击（自身） 1=退化（授予）
    e = learner_engine(holder_energy=0)
    assert [a for a in e.legal_actions(0) if a.kind == "attack"] == []


def test_招式学习器退化_持有者回合结束自弃():
    """「将在自己的回合结束时被放于弃牌区」：宣言退化（对手无进化 no-op）后
    回合结束，学习器进弃牌区，回合权移交。"""
    e = learner_engine(p1_bench=(in_play(80, basic("对手备战")),))
    e.apply(0, Action(kind="attack", attack_index=1))
    assert prim_results(e, "devolve")[0]["devolved"] == 0  # 无进化 no-op
    p0 = e.state.players[0]
    assert p0.active.attached_tool is None
    assert 90 in [c.iid for c in p0.discard]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_招式学习器退化_devolve全场退化():
    """对手全场各退栈顶 1 张回其手牌；二段只退 1 张；伤害保留、特殊状态恢复、
    未进化不动；能量不动；学习器自弃。"""
    active = stacked(inst(2, basic("底甲", hp=70)), inst(20, stage1("顶甲", "底甲", hp=90)),
                     damage=30, conditions=frozenset({SpecialCondition.POISONED}))
    bench_two = stacked(inst(70, basic("底乙", hp=60)), inst(71, stage1("中乙", "底乙", hp=80)),
                        inst(72, stage2("顶乙", "中乙", hp=100)))
    bench_two = bench_two.model_copy(update={
        "attached_energy": (inst(9070, energy()),),
    })
    bench_plain = in_play(80, basic("底丙"))
    e = learner_engine(p1_active=active, p1_bench=(bench_two, bench_plain))
    e.apply(0, Action(kind="attack", attack_index=1))
    p1 = e.state.players[1]
    assert [c.iid for c in p1.active.stack] == [2]  # 退 1 张
    assert p1.active.damage == 30  # 伤害保留
    assert p1.active.conditions == frozenset()  # 状态恢复
    assert [c.iid for c in p1.bench[0].stack] == [70, 71]  # 二段只退栈顶 1 张
    assert [c.iid for c in p1.bench[0].attached_energy] == [9070]  # 能量不动
    assert [c.iid for c in p1.bench[1].stack] == [80]  # 未进化不动
    assert [c.iid for c in p1.hand] == [20, 72, 300]  # 退化回手 + 对手回合开始抽 1
    assert prim_results(e, "devolve")[0]["devolved"] == 2
    assert 90 in [c.iid for c in e.state.players[0].discard]  # 学习器自弃
    assert e.state.phase == "main" and e.state.current_player == 1


def test_招式学习器退化_HP超限昏厥():
    """退化后新 HP 上限 < 已有伤害 → 昏厥/拿奖/换上走既有 check_knockouts。"""
    active = stacked(inst(2, basic("底甲", hp=70)), inst(20, stage1("顶甲", "底甲", hp=90)),
                     damage=80)
    e = learner_engine(p1_active=active, p1_bench=(in_play(80, basic("对手备战")),))
    e.apply(0, Action(kind="attack", attack_index=1))
    assert any(ev.kind == "knockout" for ev in e.events)
    assert len(e.state.players[0].prizes) == 5  # 攻击方拿 1 奖
    assert 20 in [c.iid for c in e.state.players[1].hand]  # 退化卡先回手
    assert 2 in [c.iid for c in e.state.players[1].discard]  # 退化后整叠进弃牌
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 1
