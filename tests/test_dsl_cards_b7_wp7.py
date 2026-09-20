"""单卡 DSL 测试（task 026 WP7b）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批 15 张 B 级卡（机制 = WP7a 宝可梦检查 / 伤害修正泛化 / 8 项小原语）：
- 化朗镇（I 标 1 印刷）：竞技场来源 modify_damage +30（holder_owner:赫普，双方生效）。
- 古玉鱼（G 标 4 印刷）：闪焰生成 attach_energy own_discard up-to 2 单目标 /
  嫉妒业火 50 + if_own_ko_by_attack_during_opponent_turn 门控追加 90。
- 咕咕（H 标 2 印刷）：三刺击 coin_flip times:3 × flip_heads_count（清单 21）。
- 喷火龙ex（G 标 10 印刷）：烈炎支配 own_evolve_from_hand + attach_energy own_deck
  up-to 3 任意分配 / 燃烧黑暗 180+opponent_taken_prizes×30。
- 大比鸟ex（G 标 6 印刷）：音速搜索 once_per_turn_shared 同名锁（清单 22）/
  狂风呼啸 120 + discard_stadium。
- 小火龙（G 标 5 印刷）：烧光 discard_stadium / 吐火 30 白板。
- 火箭队的惊吓炸弹（I 标 1 印刷）：掷币正面→对手 1 只 2 指示物 / 反面→自己战斗场 2 指示物。
- 爬地翅（G 标 3 印刷）：踏平 mill 1 / 烫伤怒涛 120 + 自伤 90 + 灼伤。
- 空手道王的修炼（H 标 7 印刷）：回合级 modify_damage +40 target_rule_box=ex。
- 裁判（31 印刷）：双方手牌洗回牌库 + 各抽 4。
- 谢米（I 标 2 印刷）：花之纱幔 protection opponent_attack_damage_to_bench
  （no_rule_box 收敛受保护目标）/ 踢飞 30 白板。
- 赫普的卡比兽（I 标 1 印刷）：慷慨 aura +30（同名去重）/ 强劲压制 140 + 自伤 80。
- 赫普的讲究头带（I 标 1 印刷）：modify_damage +30 + modify_attack_cost -1【无】。
- 野餐篮（G 标 4 印刷）：heal all_pokemon_both 30。
- 雪妖女（H 标 10 印刷）：冻结帷幕 pokemon_check 铺伤（has_ability + not_name 收敛）/
  冰霜粉碎 60 白板。
清单 25：故意取错印刷被闸 1 拦下（防回归）。
"""

from pathlib import Path

import pytest
from helpers import basic, energy, in_play, inst, main_state

from battlefrontier.cli import main as cli_main
from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import AttackDef, CardDef, SpecialCondition

CARDS_DIR = Path(__file__).parent.parent / "cards"
DB_PATH = Path(r"C:/Vibe Project/Pokearena/data/ptcg-cn.db")
needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="本机无 ptcg-cn.db")

TOWN_DOC = load_card_doc(CARDS_DIR / "化朗镇.yml")
CHIYU_DOC = load_card_doc(CARDS_DIR / "古玉鱼-嫉妒业火.yml")
HOOTHOOT_DOC = load_card_doc(CARDS_DIR / "咕咕-三刺击.yml")
CHARIZARD_DOC = load_card_doc(CARDS_DIR / "喷火龙ex-烈炎支配.yml")
PIDGEOT_DOC = load_card_doc(CARDS_DIR / "大比鸟ex.yml")
CHARMANDER_DOC = load_card_doc(CARDS_DIR / "小火龙-烧光.yml")
BOMB_DOC = load_card_doc(CARDS_DIR / "火箭队的惊吓炸弹.yml")
SLITHER_DOC = load_card_doc(CARDS_DIR / "爬地翅-烫伤怒涛.yml")
KARATE_DOC = load_card_doc(CARDS_DIR / "空手道王的修炼.yml")
JUDGE_DOC = load_card_doc(CARDS_DIR / "裁判-4张.yml")
SHAYMIN_DOC = load_card_doc(CARDS_DIR / "谢米-花之纱幔.yml")
SNORLAX_DOC = load_card_doc(CARDS_DIR / "赫普的卡比兽.yml")
BAND_DOC = load_card_doc(CARDS_DIR / "赫普的讲究头带.yml")
PICNIC_DOC = load_card_doc(CARDS_DIR / "野餐篮.yml")
FROSLASS_DOC = load_card_doc(CARDS_DIR / "雪妖女-冻结帷幕.yml")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def stadium_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="竞技场")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def poke(name: str, *, hp: int = 200, stage: int = 0, evolves_from: str | None = None,
         owner: str | None = None, rule_box: str | None = None,
         has_ability: bool = False, energy_type: str | None = None,
         attacks: tuple = (), retreat: int = 1, labels: tuple = ()) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon", hp=hp, stage=stage,
        evolves_from=evolves_from, owner=owner, rule_box=rule_box,
        has_ability=has_ability, energy_type=energy_type, attacks=attacks,
        retreat_cost=retreat, labels=labels,
    )


def hit(damage: int = 20, cost: tuple = ("无",)) -> AttackDef:
    return AttackDef(name="打击", cost=cost, damage=damage)


def hop_mon(name: str = "赫普兽", *, damage: int = 20, cost: tuple = ("无",)) -> CardDef:
    return poke(name, owner="赫普", attacks=(AttackDef(name="打击", cost=cost, damage=damage),))


def ex_mon(name: str = "ex兽", hp: int = 300) -> CardDef:
    return poke(name, hp=hp, rule_box="ex", attacks=(hit(20),))


def engine_at_seed(state, seed: int = 0) -> GameEngine:
    e = GameEngine(RandomSource(seed))
    e.state = state
    return e


def prim_results(e, action: str) -> list[dict]:
    """该原语的执行结果事件（跳过被节点级 condition 门控的 skipped 标记事件）。"""
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action
            and not ev.detail.get("result", {}).get("skipped")]


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


def play_engine(doc, name: str, *, kind="item", deck=None, extra_hand: tuple = (),
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


# ── 化朗镇（竞技场来源 modify_damage +30，holder_owner:赫普）────────────────────


def town_engine(*, p0_active=None, p1_active=None, current: int = 0, turn: int = 3,
                with_stadium: bool = True):
    """main 阶段：场上挂化朗镇（iid 399，持有者 p0），真实卡文档。"""
    state = main_state()
    p0, p1 = state.players
    if p0_active is not None:
        p0 = p0.model_copy(update={"active": p0_active})
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    e = engine_at_seed(state.model_copy(update={
        "players": (p0, p1), "current_player": current, "turn": turn,
        "stadium": inst(399, stadium_card("化朗镇")) if with_stadium else None,
        "stadium_owner": 0 if with_stadium else None,
    }))
    e.card_effects = {"化朗镇": TOWN_DOC}
    return e


def test_化朗镇_赫普宝可梦招式加30():
    """化朗镇在场：「赫普的宝可梦」招式对对手战斗场 20+30=50（事件锚点 attack.damage）。"""
    e = town_engine(p0_active=in_play(1, hop_mon(), 1))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50
    atk = next(ev for ev in e.events if ev.kind == "attack")
    assert atk.detail["damage"] == 50


def test_化朗镇_非赫普宝可梦不加():
    e = town_engine(p0_active=in_play(1, basic("路人兽", damage=20, cost=1), 1))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20


def test_化朗镇_双方生效_离场失效():
    """「双方…的宝可梦」：对手方赫普宝可梦同样 +30；竞技场离场即失效。"""
    e = town_engine(p1_active=in_play(2, hop_mon("赫普乙"), 1), current=1)
    e.apply(1, Action(kind="attack", attack_index=0))
    assert e.state.players[0].active.damage == 50
    e2 = town_engine(p0_active=in_play(1, hop_mon(), 1), with_stadium=False)
    e2.apply(0, Action(kind="attack", attack_index=0))
    assert e2.state.players[1].active.damage == 20


# ── 古玉鱼（闪焰生成 attach own_discard / 嫉妒业火门控 +90）────────────────────


def chi_yu() -> CardDef:
    return poke("古玉鱼", hp=120, energy_type="火", attacks=(
        AttackDef(name="闪焰生成", cost=("火",), damage=None),
        AttackDef(name="嫉妒业火", cost=("火", "火"), damage=None),
    ))


def chiyu_engine(*, discard: tuple = (), p0_bench: tuple = (), energies: int = 1,
                 marker: bool = False):
    e = attack_engine(CHIYU_DOC, chi_yu(),
                      p0_energies=tuple(
                          inst(9000 + i, energy("火能量", "火")) for i in range(energies)),
                      p0_bench=p0_bench)
    update: dict = {}
    if discard:
        update["discard"] = discard
    if marker:
        update["own_ko_by_attack_during_opponent_turn"] = True
    if update:
        p0 = e.state.players[0].model_copy(update=update)
        e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    return e


def test_古玉鱼_闪焰生成_最多2张附1只():
    """闪焰生成：弃牌池收窄为基本火能量（水能量不进池），选 2 张 → 单目标全附。"""
    discard = (inst(400, energy("基本【火】能量", "火")),
               inst(401, energy("基本【火】能量", "火")),
               inst(402, energy("基本【水】能量", "水")))
    e = chiyu_engine(discard=discard, p0_bench=(in_play(70, basic("备战兽")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    pc = e.state.pending_choice
    assert pc.pool == "own_discard" and pc.min_choose == 0 and pc.max_choose == 2
    assert set(pc.pool_iids) == {400, 401}
    e.apply(0, Action(kind="choose", choices=(400, 401)))
    pc2 = e.state.pending_choice
    assert pc2.pool == "own_pokemon_in_play"  # 「附着于自己的1只宝可梦身上」
    e.apply(0, Action(kind="choose", choices=(70,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.bench[0].attached_energy] == [400, 401]
    assert [c.iid for c in p0.discard] == [402]
    assert prim_results(e, "attach_energy")[0]["attached"] == 2
    assert e.state.phase == "main" and e.state.current_player == 1


def test_古玉鱼_闪焰生成_选0与空池noop():
    """「最多2张」选 0 → 不附着；弃牌区无基本火能量 → 池空 no-op 不挂起。"""
    e = chiyu_engine(discard=(inst(400, energy("基本【火】能量", "火")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=()))
    assert [c.iid for c in e.state.players[0].discard] == [400]
    assert prim_results(e, "attach_energy")[0]["attached"] == 0
    assert e.state.phase == "main" and e.state.current_player == 1
    e2 = chiyu_engine(discard=(inst(402, energy("基本【水】能量", "水")),))
    e2.apply(0, Action(kind="attack", attack_index=0))
    assert e2.state.pending_choice is None
    assert prim_results(e2, "attach_energy")[0]["attached"] == 0
    assert e2.state.phase == "main" and e2.state.current_player == 1


def test_古玉鱼_嫉妒业火_基准50():
    """无「上一对手回合自己宝可梦因招式伤害昏厥」标记 → 仅基准 50，追加节点跳过。"""
    e = chiyu_engine(energies=2)
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 50
    assert [r["final"] for r in prim_results(e, "damage")] == [50]


def test_古玉鱼_嫉妒业火_标记生效追加90():
    """标记置位 → 50+90=140（两条 damage 原语事件）。"""
    e = chiyu_engine(energies=2, marker=True)
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 140
    assert [r["final"] for r in prim_results(e, "damage")] == [50, 90]


def test_古玉鱼_嫉妒业火_备战被狙击昏厥次回合140():
    """F1 复核返工全流：上一对手回合备战宝可梦被招式伤害狙击昏厥（卡面
    「自己的宝可梦【昏厥】」无战斗场限定）→ 标记置位，次回合嫉妒业火 50+90。"""
    state = main_state()
    sniper = poke("狙击兽",
                  attacks=(AttackDef(name="狙击", cost=("无",), damage=None),))
    p0 = state.players[0].model_copy(update={"active": in_play(1, sniper, 1)})
    fish_active = in_play(2, chi_yu()).model_copy(update={
        "attached_energy": (inst(9021, energy("火能量", "火")),
                            inst(9022, energy("火能量", "火"))),
    })
    p1 = state.players[1].model_copy(update={
        "active": fish_active,
        "bench": (in_play(80, basic("脆皮备战", hp=30)),),
    })
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"狙击兽": SNIPE_DOC, "古玉鱼": CHIYU_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))  # 狙击备战脆皮（50 ≥ 30 → 昏厥）
    assert e.state.players[1].bench == ()
    assert e.state.players[1].own_ko_by_attack_during_opponent_turn is True
    assert e.state.phase == "main" and e.state.current_player == 1  # 回合权移交
    e.apply(1, Action(kind="attack", attack_index=1))  # 嫉妒业火
    assert e.state.players[0].active.damage == 140
    # 嫉妒业火两跳均落 p0 战斗场（iid 1）；狙击那跳落备战 iid 80，按目标过滤剔除
    assert [r["final"] for r in prim_results(e, "damage")
            if r["target_iid"] == 1] == [50, 90]


# ── 咕咕（三刺击 coin_flip times:3 × flip_heads_count）（清单 21）───────────────


def hoothoot() -> CardDef:
    return poke("咕咕", hp=60,
                attacks=(AttackDef(name="三刺击", cost=("无",), damage=None),))


def test_咕咕_三刺击_掷币计数伤害():
    """掷 3 次硬币，伤害 = 正面次数×10（事件锚点 coin_flip.flips / damage.final）。"""
    e = attack_engine(HOOTHOOT_DOC, hoothoot(), p0_energies=(inst(9001, energy()),), seed=5)
    e.apply(0, Action(kind="attack", attack_index=0))
    flip = prim_results(e, "coin_flip")[0]
    assert len(flip["flips"]) == 3
    assert flip["heads"] == sum(f == "heads" for f in flip["flips"])
    assert e.state.players[1].active.damage == flip["heads"] * 10
    assert prim_results(e, "damage")[0]["final"] == flip["heads"] * 10


def test_咕咕_三刺击_种子确定性():
    """同种子两次运行：掷币序列与伤害逐局一致。"""
    runs = []
    for _ in range(2):
        e = attack_engine(HOOTHOOT_DOC, hoothoot(),
                          p0_energies=(inst(9001, energy()),), seed=9)
        e.apply(0, Action(kind="attack", attack_index=0))
        runs.append((tuple(prim_results(e, "coin_flip")[0]["flips"]),
                     e.state.players[1].active.damage))
    assert runs[0] == runs[1]


# ── 喷火龙ex（烈炎支配 own_deck 附着 / 燃烧黑暗奖赏计数）────────────────────────


def charizard_ex() -> CardDef:
    return poke("喷火龙ex", hp=330, stage=2, evolves_from="火恐龙", rule_box="ex",
                energy_type="火",
                attacks=(AttackDef(name="燃烧黑暗", cost=("火", "火"), damage=None),))


def charmeleon() -> CardDef:
    return poke("火恐龙", hp=100, stage=1, evolves_from="小火龙", energy_type="火",
                attacks=(hit(30),))


def charizard_engine(deck: tuple):
    """main 阶段：p0 战斗场火恐龙（iid 1）+ 备战（iid 70），手牌喷火龙ex（iid 60）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, charmeleon()),
        "bench": (in_play(70, basic("备战兽")),),
        "hand": (inst(60, charizard_ex()),),
        "deck": deck,
    })
    e = engine_at_seed(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"喷火龙ex": CHARIZARD_DOC}
    return e


def test_喷火龙ex_烈炎支配_最多3张任意分配():
    """手牌进化触发：牌库池收窄为基本火能量，选 3 张 → 逐张选目标（2 战斗场 + 1 备战），
    重洗执行（原语内建）；非能量卡不进池。"""
    deck = (inst(100, energy("基本【火】能量", "火")),
            inst(101, energy("基本【火】能量", "火")),
            inst(102, energy("基本【火】能量", "火")),
            inst(103, basic("库甲")), inst(104, basic("库乙")))
    e = charizard_engine(deck)
    e.apply(0, Action(kind="evolve", iid=60, target_iid=1))
    assert any(ev.kind == "trigger_on_event"
               and ev.detail.get("event") == "own_evolve_from_hand" for ev in e.events)
    pc = e.state.pending_choice
    assert pc.pool == "own_deck" and pc.min_choose == 0 and pc.max_choose == 3
    assert set(pc.pool_iids) == {100, 101, 102}
    e.apply(0, Action(kind="choose", choices=(100, 101, 102)))
    # 目标选择池 = 自己场上宝可梦（进化后战斗场栈顶 iid=60）
    e.apply(0, Action(kind="choose", choices=(60,)))
    e.apply(0, Action(kind="choose", choices=(70,)))
    e.apply(0, Action(kind="choose", choices=(60,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [100, 102]
    assert [c.iid for c in p0.bench[0].attached_energy] == [101]
    assert sorted(c.iid for c in p0.deck) == [103, 104]
    res = prim_results(e, "attach_energy")[0]
    assert res["attached"] == 3 and res["shuffled"] is True
    assert e.state.phase == "main" and e.state.current_player == 0


def test_喷火龙ex_烈炎支配_牌库无火能仅重洗():
    """池空 → 不挂起、仅重洗（「最多3张」尽力而为）。"""
    deck = tuple(inst(100 + i, basic(f"库{i}")) for i in range(3))
    e = charizard_engine(deck)
    e.apply(0, Action(kind="evolve", iid=60, target_iid=1))
    assert e.state.pending_choice is None
    res = prim_results(e, "attach_energy")[0]
    assert res["attached"] == 0 and res["shuffled"] is True
    assert len(e.state.players[0].deck) == 3
    assert e.state.phase == "main" and e.state.current_player == 0


def test_喷火龙ex_燃烧黑暗_对手已拿0奖基准180():
    e = attack_engine(CHARIZARD_DOC, charizard_ex(),
                      p0_energies=(inst(9001, energy("火能量", "火")),
                                   inst(9002, energy("火能量", "火"))))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 180


def test_喷火龙ex_燃烧黑暗_对手已拿2奖加60():
    """燃烧黑暗 180+：追加 = 对手已拿奖赏 ×30（2 张 → 240）。"""
    e = attack_engine(CHARIZARD_DOC, charizard_ex(),
                      p0_energies=(inst(9001, energy("火能量", "火")),
                                   inst(9002, energy("火能量", "火"))))
    p1 = e.state.players[1].model_copy(update={"prizes": e.state.players[1].prizes[:4]})
    e.state = e.state.model_copy(update={"players": (e.state.players[0], p1)})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 240


# ── 大比鸟ex（音速搜索同名锁 / 狂风呼啸弃竞技场）───────────────────────────────


def pidgeot_ex() -> CardDef:
    return poke("大比鸟ex", hp=280, stage=2, evolves_from="比比鸟", rule_box="ex",
                attacks=(AttackDef(name="狂风呼啸", cost=("无", "无"), damage=None),))


def pidgeot_engine(*, bench_second: bool = True):
    """main 阶段：p0 战斗场大比鸟ex（iid 1，附 2 能）± 备战第二只（iid 80）。"""
    state = main_state()
    bench = (in_play(80, pidgeot_ex()),) if bench_second else ()
    p0 = state.players[0].model_copy(update={"active": in_play(1, pidgeot_ex(), 2),
                                             "bench": bench})
    e = engine_at_seed(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"大比鸟ex": PIDGEOT_DOC}
    return e


def test_大比鸟ex_音速搜索_任意检索1张():
    e = pidgeot_engine()
    e.apply(0, Action(kind="use_ability", iid=1))
    pc = e.state.pending_choice
    assert pc.pool == "own_deck" and pc.max_choose == 1
    e.apply(0, Action(kind="choose", choices=(103,)))
    p0 = e.state.players[0]
    assert 103 in [c.iid for c in p0.hand]
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


def test_大比鸟ex_音速搜索_同名锁两只当回合限1次():
    """清单 22：「已经使用了其他的「音速搜索」」= once_per_turn_shared——两只同场
    当回合只能用 1 次；下回合解禁。"""
    e = pidgeot_engine()
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(100,)))
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]  # 两只全锁
    e.apply(0, Action(kind="end_turn"))
    e.apply(1, Action(kind="end_turn"))
    acts = [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    assert {a.iid for a in acts} == {1, 80}


def test_大比鸟ex_狂风呼啸_120弃竞技场():
    """狂风呼啸 120 + 场上竞技场入其持有者（p1）弃牌区（D-WP7-6 满足即执行）。"""
    e = attack_engine(PIDGEOT_DOC, pidgeot_ex(),
                      p0_energies=(inst(9001, energy()), inst(9002, energy())))
    e.state = e.state.model_copy(update={
        "stadium": inst(399, stadium_card("老竞技场")), "stadium_owner": 1})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 120
    assert e.state.stadium is None
    assert 399 in [c.iid for c in e.state.players[1].discard]
    assert prim_results(e, "discard_stadium")[0]["discarded"] == "老竞技场"


def test_大比鸟ex_狂风呼啸_无竞技场noop():
    e = attack_engine(PIDGEOT_DOC, pidgeot_ex(),
                      p0_energies=(inst(9001, energy()), inst(9002, energy())))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 120
    assert prim_results(e, "discard_stadium")[0]["discarded"] is None
    assert e.state.phase == "main" and e.state.current_player == 1


# ── 小火龙（烧光 discard_stadium / 吐火白板）───────────────────────────────────


def charmander() -> CardDef:
    return poke("小火龙", hp=70, energy_type="火", attacks=(
        AttackDef(name="烧光", cost=("火",), damage=None),
        AttackDef(name="吐火", cost=("火", "火"), damage=30),
    ))


def test_小火龙_烧光_弃竞技场无伤害():
    """烧光：无伤害招式，强制弃场上竞技场（入其持有者弃牌区）。"""
    e = attack_engine(CHARMANDER_DOC, charmander(),
                      p0_energies=(inst(9001, energy("火能量", "火")),))
    e.state = e.state.model_copy(update={
        "stadium": inst(399, stadium_card("老竞技场")), "stadium_owner": 0})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0
    assert e.state.stadium is None
    assert 399 in [c.iid for c in e.state.players[0].discard]
    assert prim_results(e, "discard_stadium")[0]["discarded"] == "老竞技场"


def test_小火龙_烧光_无竞技场noop_吐火白板30():
    e = attack_engine(CHARMANDER_DOC, charmander(),
                      p0_energies=(inst(9001, energy("火能量", "火")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert prim_results(e, "discard_stadium")[0]["discarded"] is None
    assert e.state.phase == "main" and e.state.current_player == 1
    e2 = attack_engine(CHARMANDER_DOC, charmander(),
                       p0_energies=(inst(9001, energy("火能量", "火")),
                                    inst(9002, energy("火能量", "火"))))
    e2.apply(0, Action(kind="attack", attack_index=1))
    assert e2.state.players[1].active.damage == 30  # 吐火 30 无 DSL 绑定，白板结算


# ── 火箭队的惊吓炸弹（掷币分支铺伤）────────────────────────────────────────────


def _bomb_run(seed: int):
    e = play_engine(BOMB_DOC, "火箭队的惊吓炸弹", kind="item", seed=seed,
                    p1_bench=(in_play(80, basic("对手备战")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    return e, prim_results(e, "coin_flip")[0]["flips"][0]


def _bomb_seed(want: str):
    for seed in range(100):
        e, flip = _bomb_run(seed)
        if flip == want:
            return e
    raise AssertionError(f"100 个种子内未出现 {want}")


def test_火箭队的惊吓炸弹_正面_对手1只2指示物():
    """正面：挂起选对手 1 只宝可梦放 2 个指示物（掷币结果冻结穿透恢复）。"""
    e = _bomb_seed("heads")
    pc = e.state.pending_choice
    assert pc is not None and pc.pool == "opponent_pokemon_any"
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 20
    assert e.state.players[0].active.damage == 0  # 反面分支跳过
    res = prim_results(e, "place_damage_counters")
    assert len(res) == 1 and res[0]["counters_each"] == 2
    assert 60 in [c.iid for c in e.state.players[0].discard]  # 物品本体入弃牌区
    assert e.state.phase == "main" and e.state.current_player == 0


def test_火箭队的惊吓炸弹_反面_自己战斗场2指示物():
    """反面：正面分支（choose）跳过不挂起，自己战斗场放 2 个指示物。"""
    e = _bomb_seed("tails")
    assert e.state.pending_choice is None
    assert e.state.players[0].active.damage == 20
    assert e.state.players[1].active.damage == 0
    assert e.state.players[1].bench[0].damage == 0
    assert e.state.phase == "main" and e.state.current_player == 0


# ── 爬地翅（踏平 mill / 烫伤怒涛自伤+灼伤）─────────────────────────────────────


def slither() -> CardDef:
    return poke("爬地翅", hp=140, energy_type="斗", labels=("古代",), attacks=(
        AttackDef(name="踏平", cost=("斗",), damage=None),
        AttackDef(name="烫伤怒涛", cost=("斗", "斗"), damage=None),
    ))


def test_爬地翅_踏平_磨对手牌库顶1张():
    deck = (inst(300, basic("顶卡")), inst(301, basic("次卡")), inst(302, basic("底卡")))
    e = attack_engine(SLITHER_DOC, slither(),
                      p0_energies=(inst(9001, energy("斗能量", "斗")),), p1_deck=deck)
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    # 回合权移交后对手回合开始抽 1（301 入手），牌库剩 [302]；牌顶 300 已入弃牌区
    assert [c.iid for c in p1.deck] == [302]
    assert [c.iid for c in p1.discard] == [300]
    assert 301 in [c.iid for c in p1.hand]
    res = prim_results(e, "mill")[0]
    assert res["milled"] == 1 and res["iids"] == [300]


def test_爬地翅_烫伤怒涛_120自伤90灼伤():
    """烫伤怒涛：对手战斗场 120；自身固定 90（效果文伤害，不吃修正）；对手灼伤。"""
    e = attack_engine(SLITHER_DOC, slither(),
                      p0_energies=(inst(9001, energy("斗能量", "斗")),
                                   inst(9002, energy("斗能量", "斗"))))
    e.apply(0, Action(kind="attack", attack_index=1))
    # 灼伤在攻击方回合结束的宝可梦检查立即结算：+20 后掷币（正面恢复反面保持）
    assert e.state.players[1].active.damage == 140  # 120 + 检查阶段灼伤 20
    burn = [ev for ev in e.events
            if ev.kind == "check_status" and ev.detail.get("status") == "burned"]
    assert len(burn) == 1 and burn[0].detail["damage"] == 20
    expected = frozenset() if burn[0].detail["recovered"] else {SpecialCondition.BURNED}
    assert e.state.players[1].active.conditions == expected
    assert e.state.players[0].active.damage == 90  # 自伤固定值不吃修正
    self_dmg = next(r for r in prim_results(e, "damage") if r["target_iid"] == 1)
    assert self_dmg["final"] == 90 and self_dmg["damage_mod"] == 0


# ── 空手道王的修炼（回合级 modify_damage +40 target_rule_box=ex）────────────────

KARATE = "空手道王的修炼"


def test_空手道王的修炼_本回合对ex加40():
    e = play_engine(KARATE_DOC, KARATE, kind="supporter",
                    p1_active=in_play(2, ex_mon(), 1))
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.players[0].turn_damage_mods == ((40, "ex"),)
    assert prim_results(e, "modify_damage")[0] == {"amount": 40, "target_rule_box": "ex"}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 60  # 20+40


def test_空手道王的修炼_对非ex不加():
    e = play_engine(KARATE_DOC, KARATE, kind="supporter")  # p1 战斗场无规则盒
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20


def test_空手道王的修炼_回合结束清除():
    """「在这个回合」：持有者回合结束清除，下回合不再加成。"""
    e = play_engine(KARATE_DOC, KARATE, kind="supporter")
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[0].turn_damage_mods == ()
    e.apply(1, Action(kind="end_turn"))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20


# ── 裁判（双方手牌洗回牌库 + 各抽 4）──────────────────────────────────────────


def judge_engine(seed: int = 7):
    p1 = main_state().players[1]  # 占位（结构对齐）
    state = main_state(p0_extra_hand=(inst(60, supporter_card("裁判")),))
    p1 = state.players[1].model_copy(update={
        "hand": (inst(70, basic("对手手甲")), inst(71, basic("对手手乙"))),
        "deck": tuple(inst(300 + i, basic(f"对手库{i}")) for i in range(10)),
    })
    e = engine_at_seed(state.model_copy(update={"players": (state.players[0], p1)}), seed)
    e.card_effects = {"裁判": JUDGE_DOC}
    return e


def test_裁判_双方洗回各抽4():
    """双方手牌各回库重洗 → 各抽 4；打出时裁判已离手（洗回 2 张）；卡片全集守恒。"""
    e = judge_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    p0, p1 = e.state.players
    assert len(p0.hand) == 4 and len(p0.deck) == 8
    assert len(p1.hand) == 4 and len(p1.deck) == 8
    assert sorted(c.iid for c in (*p0.hand, *p0.deck, *p0.discard)) == [
        50, 51, 60, *range(100, 110)]
    assert sorted(c.iid for c in (*p1.hand, *p1.deck)) == [70, 71, *range(300, 310)]
    res = prim_results(e, "shuffle_hand_into_deck")
    assert [r["shuffled"] for r in res] == [2, 2]
    assert [r["player"] for r in res] == [0, 1]
    assert e.state.phase == "main" and e.state.current_player == 0


def test_裁判_种子确定性():
    """同种子两次运行：双方牌库序逐局一致（重洗走单一随机源）。"""
    orders = []
    for _ in range(2):
        e = judge_engine()
        e.apply(0, Action(kind="play_trainer", iid=60))
        orders.append((tuple(c.iid for c in e.state.players[0].deck),
                       tuple(c.iid for c in e.state.players[1].deck)))
    assert orders[0] == orders[1]


# ── 谢米（花之纱幔 protection opponent_attack_damage_to_bench）─────────────────

SNIPE_DOC = parse_card_doc("""
card:
  name_group: 狙击兽
effects:
  - trigger: on_attack
    attack: 狙击
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 50}}
""")


def shaymin() -> CardDef:
    return poke("谢米", hp=70, has_ability=True,
                attacks=(AttackDef(name="踢飞", cost=("无", "无"), damage=30),))


def shaymin_engine(*, p1_bench: tuple):
    e = attack_engine(SNIPE_DOC, poke("狙击兽", attacks=(
        AttackDef(name="狙击", cost=("无",), damage=None),)),
        p0_energies=(inst(9001, energy()),),
        p1_bench=p1_bench, extra_effects={"谢米": SHAYMIN_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    return e


def test_谢米_花之纱幔_备战无规则盒免疫招式伤害():
    e = shaymin_engine(p1_bench=(in_play(80, shaymin()), in_play(81, basic("无规则备战"))))
    e.apply(0, Action(kind="choose", choices=(81,)))
    assert e.state.players[1].bench[1].damage == 0
    res = prim_results(e, "damage")[0]
    assert res["protected"] is True and res["final"] == 0


def test_谢米_花之纱幔_规则盒与战斗场不保护_离场失效():
    # 规则盒备战宝可梦不保护（no_rule_box 收敛）
    e = shaymin_engine(p1_bench=(in_play(80, shaymin()), in_play(82, ex_mon("ex备战"))))
    e.apply(0, Action(kind="choose", choices=(82,)))
    assert e.state.players[1].bench[1].damage == 50
    # 战斗场不保护（作用面=备战区）
    e2 = shaymin_engine(p1_bench=(in_play(80, shaymin()),))
    e2.apply(0, Action(kind="choose", choices=(2,)))
    assert e2.state.players[1].active.damage == 50
    # 谢米离场即失效
    e3 = shaymin_engine(p1_bench=(in_play(81, basic("无规则备战")),))
    e3.apply(0, Action(kind="choose", choices=(81,)))
    assert e3.state.players[1].bench[0].damage == 50


def test_谢米_踢飞白板30():
    e = attack_engine(SHAYMIN_DOC, shaymin(),
                      p0_energies=(inst(9001, energy()), inst(9002, energy())))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 30


# ── 赫普的卡比兽（慷慨 aura / 强劲压制自伤）────────────────────────────────────


def snorlax() -> CardDef:
    return poke("赫普的卡比兽", hp=160, owner="赫普", has_ability=True,
                attacks=(AttackDef(name="强劲压制", cost=("无", "无", "无"), damage=None),))


def test_赫普的卡比兽_慷慨_赫普招式加30():
    e = attack_engine(None, hop_mon(), p0_energies=(inst(9001, energy()),),
                      p0_bench=(in_play(80, snorlax()),),
                      extra_effects={"赫普的卡比兽": SNORLAX_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50  # 20+30


def test_赫普的卡比兽_慷慨_同名不重复_非赫普不加():
    """「无论拥有这个特性的宝可梦有多少只，这个效果都不会重复」= 同名去重只加一次。"""
    e = attack_engine(None, hop_mon(), p0_energies=(inst(9001, energy()),),
                      p0_bench=(in_play(80, snorlax()), in_play(81, snorlax())),
                      extra_effects={"赫普的卡比兽": SNORLAX_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50  # 两只卡比兽只 +30 一次
    e2 = attack_engine(None, basic("路人兽", damage=20, cost=1),
                       p0_energies=(inst(9001, energy()),),
                       p0_bench=(in_play(80, snorlax()),),
                       extra_effects={"赫普的卡比兽": SNORLAX_DOC})
    e2.apply(0, Action(kind="attack", attack_index=0))
    assert e2.state.players[1].active.damage == 20


def test_赫普的卡比兽_强劲压制_140自伤80_自身吃慷慨():
    """强劲压制 140 + 自伤 80；持有者是「赫普的宝可梦」，自身 aura 同样生效（170）。"""
    e = attack_engine(SNORLAX_DOC, snorlax(),
                      p0_energies=tuple(inst(9001 + i, energy()) for i in range(3)))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 170  # 140+30
    assert e.state.players[0].active.damage == 80  # 自伤固定值不吃修正


# ── 赫普的讲究头带（modify_damage +30 + modify_attack_cost -1【无】）─────────────


def band_engine(*, holder: CardDef, energies: int):
    """main 阶段：p0 战斗场持有者（iid 1）带讲究头带（iid 90）。"""
    state = main_state()
    mon = in_play(1, holder, energies)
    mon = mon.model_copy(update={"attached_tool": inst(90, tool_card("赫普的讲究头带"))})
    p0 = state.players[0].model_copy(update={"active": mon})
    e = engine_at_seed(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"赫普的讲究头带": BAND_DOC}
    return e


def test_赫普的讲究头带_减费加伤():
    """费用 2【无】→ 减 1 后 1 能可宣言（枚举门接通）；伤害 20+30=50。"""
    e = band_engine(holder=hop_mon(cost=("无", "无")), energies=1)
    acts = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert len(acts) == 1
    e.apply(0, acts[0])
    assert e.state.players[1].active.damage == 50


def test_赫普的讲究头带_非赫普持有者不生效():
    holder = poke("路人兽", attacks=(AttackDef(name="打击", cost=("无", "无"), damage=20),))
    e = band_engine(holder=holder, energies=1)
    assert not [a for a in e.legal_actions(0) if a.kind == "attack"]  # 费用不减
    e2 = band_engine(holder=holder, energies=2)
    e2.apply(0, Action(kind="attack", attack_index=0))
    assert e2.state.players[1].active.damage == 20  # 伤害不加


# ── 野餐篮（heal all_pokemon_both 30）─────────────────────────────────────────


def test_野餐篮_双方全场各回30_满血noop():
    """双方所有宝可梦各回复 30（去 3 个指示物，不超过已有伤害；满血 no-op 照常）。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("野餐篮")),))
    p0 = state.players[0].model_copy(update={
        "active": state.players[0].active.model_copy(update={"damage": 50}),
        "bench": (in_play(70, basic("伤备战")).model_copy(update={"damage": 20}),
                  in_play(71, basic("满血备战"))),
    })
    p1 = state.players[1].model_copy(update={
        "active": state.players[1].active.model_copy(update={"damage": 20}),
        "bench": (in_play(80, basic("对手伤")).model_copy(update={"damage": 40}),),
    })
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"野餐篮": PICNIC_DOC}
    e.apply(0, Action(kind="play_trainer", iid=60))
    p0, p1 = e.state.players
    assert p0.active.damage == 20  # 50-30
    assert p0.bench[0].damage == 0  # 20→0（不超过已有伤害）
    assert p0.bench[1].damage == 0  # 满血 no-op
    assert p1.active.damage == 0
    assert p1.bench[0].damage == 10  # 40-30
    assert prim_results(e, "heal")[0]["healed"] == 100  # 30+20+20+30
    assert e.state.phase == "main" and e.state.current_player == 0


# ── 雪妖女（冻结帷幕 pokemon_check 铺伤 / 冰霜粉碎白板）─────────────────────────


def froslass() -> CardDef:
    return poke("雪妖女", hp=90, stage=1, evolves_from="雪童子", has_ability=True,
                attacks=(AttackDef(name="冰霜粉碎", cost=("水", "无"), damage=60),))


def ability_mon(name: str, hp: int = 200) -> CardDef:
    return poke(name, hp=hp, has_ability=True, attacks=(hit(20),))


def froslass_engine(*, p0_bench: tuple, p1_bench: tuple = ()):
    """main 阶段：双方战斗场各 1 只特性宝可梦，备战区可调。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, ability_mon("特性甲")), "bench": p0_bench})
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, ability_mon("特性乙")), "bench": p1_bench})
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"雪妖女": FROSLASS_DOC}
    return e


def _check_triggers(e) -> list:
    return [ev for ev in e.events
            if ev.kind == "trigger_on_event" and ev.detail.get("event") == "pokemon_check"]


def test_雪妖女_冻结帷幕_检查时双方特性宝可梦各1指示物():
    """回合结束检查：双方拥有特性的宝可梦（除雪妖女）各放 1 个指示物；
    无特性宝可梦不放；检查完毕后进入下一回合。"""
    e = froslass_engine(p0_bench=(in_play(80, froslass()), in_play(81, basic("无特性丁"))),
                        p1_bench=(in_play(82, basic("无特性丙")),))
    e.apply(0, Action(kind="end_turn"))
    assert len(_check_triggers(e)) == 1
    p0, p1 = e.state.players
    assert p0.active.damage == 10
    assert p1.active.damage == 10
    assert p0.bench[0].damage == 0  # 雪妖女自身除外（not_name:雪妖女）
    assert p0.bench[1].damage == 0 and p1.bench[0].damage == 0  # 无特性不放
    res = prim_results(e, "place_damage_counters")[0]
    assert res["placed"] == 2 and res["counters_each"] == 1
    assert e.state.phase == "main" and e.state.current_player == 1


def test_雪妖女_冻结帷幕_多只各触发():
    """多只雪妖女在场各触发各结算（原文无「不重复」注，无同名锁）。"""
    e = froslass_engine(p0_bench=(in_play(80, froslass()),),
                        p1_bench=(in_play(83, froslass()),))
    e.apply(0, Action(kind="end_turn"))
    assert len(_check_triggers(e)) == 2
    assert e.state.players[0].active.damage == 20
    assert e.state.players[1].active.damage == 20


def test_雪妖女_离场不触发_冰霜粉碎白板60():
    e = froslass_engine(p0_bench=(in_play(81, basic("无特性丁")),))
    e.apply(0, Action(kind="end_turn"))
    assert not _check_triggers(e)
    assert e.state.players[0].active.damage == 0
    assert e.state.players[1].active.damage == 0
    e2 = attack_engine(FROSLASS_DOC, froslass(),
                       p0_energies=(inst(9001, energy("水能量", "水")),
                                    inst(9002, energy())))
    e2.apply(0, Action(kind="attack", attack_index=0))
    assert e2.state.players[1].active.damage == 60


# ── 清单 25：故意取错印刷被闸 1 拦下（防回归）──────────────────────────────────


@needs_db
def test_闸1_故意取错印刷被拦_防回归(tmp_path, capsys):
    """池内文本类混入异文本印刷 → dsl-check --db 必须 FAIL（归一化 text_raw 不一致）。"""
    cases = [
        ("古玉鱼-嫉妒业火.yml", "CSVH5C-009]", "CSVH5C-009, CSV7C-050]"),
        ("小火龙-烧光.yml", "CSVM1aC-001]", "CSVM1aC-001, CSV5C-014]"),
    ]
    for fname, old, new in cases:
        src = (CARDS_DIR / fname).read_text(encoding="utf-8")
        assert old in src, fname
        p = tmp_path / fname
        p.write_text(src.replace(old, new, 1), encoding="utf-8")
        rc = cli_main(["dsl-check", str(p), "--db", str(DB_PATH)])
        out = capsys.readouterr().out
        assert rc == 1 and "FAIL" in out and "文本" in out, fname
