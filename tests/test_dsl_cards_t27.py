"""单卡 DSL 测试（task 027）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批 7 张 C 级卡（机制 = TERA 备战免伤 + provide_energy args.count / holder_stage:N
+ attach_energy own_hand→self + search_deck any_count/distinct 无 split +
place_damage_counters distribute + 计数词 attached_energy_on_both_actives）：
- 不公印章（ACE 物品，2 印刷）：上一个对手回合己方宝可梦昏厥才可用
  （own_ko_during_opponent_turn 条件门）；双方手牌洗回 + 自抽 5 / 对手抽 2。
- 极限腰带（ACE 道具，2 印刷）：招式对对手战斗场「宝可梦【ex】」+50
  （WP7 modify_damage target_rule_box 挂载面直写）。
- 顶尖捕捉器（ACE 物品，4 印刷）：对手备战换入 + 己方备战换入（两段强制换位，
  顺序挂起）。
- 能量输送PRO（ACE 物品，1 印刷）：牌库选任意数量属性互异基本能量 → 展示 →
  入手 → 重洗（search_deck args.{distinct: energy_type, any_count: true} 新形态）。
- 新冲天能量（ACE 特殊能量，2 印刷）：视作 1 个【无】；附着【2阶进化】→
  视作 2 个所有属性（provide_energy args.count=2 + holder_stage:2 分层覆盖）。
- 厄诡椪 碧草面具ex（太晶 ex，10 印刷）：碧草之舞 手牌 1 张基本【草】能量附自身
  + 抽 1（attach_energy own_hand→self 新形态）/ 万叶阵雨 30+双方战斗场能量数×30。
- 多龙巴鲁托ex（太晶 ex，5 印刷）：喷射头击 70 白板 / 幻影潜袭 200 +
  6 个伤害指示物任意方式分配（place_damage_counters distribute 新形态）。
清单 9 闸 1 防回归：不公印章混入异文本类印刷（顶尖捕捉器 CSV7C-180）必须被拦。
"""

from pathlib import Path

import pytest
from helpers import basic, energy, in_play, inst, main_state

from battlefrontier.cli import main as cli_main
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import AttackDef, CardDef, CardInstance

CARDS_DIR = Path(__file__).parent.parent / "cards"
DB_PATH = Path(r"C:/Vibe Project/Pokearena/data/ptcg-cn.db")
needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="本机无 ptcg-cn.db")

STAMP_DOC = load_card_doc(CARDS_DIR / "不公印章.yml")
BELT_DOC = load_card_doc(CARDS_DIR / "极限腰带.yml")
CATCHER_DOC = load_card_doc(CARDS_DIR / "顶尖捕捉器.yml")
PRO_DOC = load_card_doc(CARDS_DIR / "能量输送PRO.yml")
BOOST_DOC = load_card_doc(CARDS_DIR / "新冲天能量.yml")
OGERPON_DOC = load_card_doc(CARDS_DIR / "厄诡椪 碧草面具ex.yml")
DRAGAPULT_DOC = load_card_doc(CARDS_DIR / "多龙巴鲁托ex.yml")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def special_energy(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy",
                   is_basic_energy=False)


def poke(name: str, *, hp: int = 300, stage: int = 0,
         evolves_from: str | None = None, rule_box: str | None = None,
         has_ability: bool = False, is_tera: bool = False,
         energy_type: str | None = None, attacks: tuple = (),
         retreat: int = 1) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon", hp=hp, stage=stage,
        evolves_from=evolves_from, rule_box=rule_box, has_ability=has_ability,
        is_tera=is_tera, energy_type=energy_type, attacks=attacks,
        retreat_cost=retreat,
    )


def engine_at_seed(state, seed: int = 0) -> GameEngine:
    e = GameEngine(RandomSource(seed))
    e.state = state
    return e


def prim_results(e: GameEngine, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action
            and not ev.detail.get("result", {}).get("skipped")]


def play_engine(doc, name: str, *, deck=None, extra_hand: tuple = (),
                p0_bench: tuple = (), p1_active=None, p1_bench: tuple = (),
                p1_hand=None, p0_update: dict | None = None, seed: int = 0):
    """main 阶段：p0 手牌含测试物品卡（iid 60）。"""
    state = main_state(p0_extra_hand=(inst(60, item_card(name)),) + extra_hand)
    p0 = state.players[0].model_copy(update={"bench": p0_bench, **(p0_update or {})})
    if deck is not None:
        p0 = p0.model_copy(update={"deck": deck})
    p1 = state.players[1].model_copy(update={"bench": p1_bench})
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}), seed)
    e.card_effects = {name: doc}
    return e


# ── 不公印章（条件门 + 双方洗回 + 不对称抽牌）─────────────────────────────────


def stamp_engine(*, ko_flag: bool, seed: int = 7) -> GameEngine:
    return play_engine(
        STAMP_DOC, "不公印章", seed=seed,
        p0_update={"own_ko_during_opponent_turn": ko_flag},
        p1_hand=(inst(70, basic("对手手甲")), inst(71, basic("对手手乙"))),
    )


def test_不公印章_条件门_昏厥标记未置位不可使用() -> None:
    """「只有在上一个对手的回合，自己的宝可梦【昏厥】时才可使用」——条件门不满足
    不枚举；置位后可打出。"""
    e = stamp_engine(ko_flag=False)
    assert not [a for a in e.legal_actions(0)
                if a.kind == "play_trainer" and a.iid == 60]
    e = stamp_engine(ko_flag=True)
    assert [a for a in e.legal_actions(0)
            if a.kind == "play_trainer" and a.iid == 60]


def test_不公印章_双方洗回_自抽5对手抽2() -> None:
    """全流：双方手牌各回库重洗 → 自抽 5 / 对手抽 2；卡片全集守恒；本体入弃牌区。"""
    e = stamp_engine(ko_flag=True)
    e.apply(0, Action(kind="play_trainer", iid=60))
    p0, p1 = e.state.players
    # p0：手牌 [50, 51, 60] → 打出 60 入弃牌区，洗回 2 → 库 12 → 抽 5
    assert len(p0.hand) == 5 and len(p0.deck) == 7
    # p1：手牌 [70, 71] 洗回 → 库 12 → 抽 2
    assert len(p1.hand) == 2 and len(p1.deck) == 10
    assert sorted(c.iid for c in (*p0.hand, *p0.deck, *p0.discard)) == [
        50, 51, 60, *range(100, 110)]
    assert sorted(c.iid for c in (*p1.hand, *p1.deck)) == [70, 71, *range(300, 310)]
    res = prim_results(e, "shuffle_hand_into_deck")
    assert [r["shuffled"] for r in res] == [2, 2]
    assert [r["player"] for r in res] == [0, 1]
    draws = prim_results(e, "draw")
    assert [r["drawn"] for r in draws] == [5, 2]
    assert e.state.phase == "main" and e.state.current_player == 0


# ── 极限腰带（道具 modify_damage +50 target_rule_box=ex）──────────────────────


def belt_engine(*, p1_active=None) -> GameEngine:
    """main 阶段：p0 战斗场持有者（iid 1，1 能）带极限腰带（iid 90）。"""
    holder = poke("腰带兽", attacks=(AttackDef(name="打击", cost=("无",), damage=20),))
    state = main_state()
    mon = in_play(1, holder, 1).model_copy(
        update={"attached_tool": inst(90, tool_card("极限腰带"))})
    p0 = state.players[0].model_copy(update={"active": mon})
    p1 = state.players[1]
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"极限腰带": BELT_DOC}
    return e


def test_极限腰带_对ex战斗场加50() -> None:
    e = belt_engine(p1_active=in_play(2, poke("ex兽", rule_box="ex"), 1))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 70  # 20+50


def test_极限腰带_对非ex不加() -> None:
    e = belt_engine()  # p1 战斗场 stub 无规则盒
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20


# ── 顶尖捕捉器（两段强制换位）────────────────────────────────────────────────


def catcher_engine() -> GameEngine:
    return play_engine(
        CATCHER_DOC, "顶尖捕捉器",
        p0_bench=(in_play(70, basic("己方备战")),),
        p1_bench=(in_play(80, basic("对手备战")),),
    )


def test_顶尖捕捉器_先对手后己方两段换位() -> None:
    """语序：先挂起选对手备战换入其战斗场，再挂起选己方备战换入己方战斗场。"""
    e = catcher_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool == "opponent_bench"
    e.apply(0, Action(kind="choose", choices=(80,)))
    p1 = e.state.players[1]
    assert p1.active.current.iid == 80 and p1.bench[0].current.iid == 2
    pc = e.state.pending_choice
    assert pc is not None and pc.pool == "own_bench"
    e.apply(0, Action(kind="choose", choices=(70,)))
    p0 = e.state.players[0]
    assert p0.active.current.iid == 70 and p0.bench[0].current.iid == 1
    assert 60 in [c.iid for c in p0.discard]  # 物品本体入弃牌区
    assert e.state.phase == "main" and e.state.current_player == 0


# ── 能量输送PRO（distinct 互异 + any_count 任意数量）──────────────────────────


def pro_engine() -> GameEngine:
    deck = (
        inst(100, energy("基本火能量", "火")),
        inst(101, energy("基本火能量", "火")),   # 与 100 同属性桶
        inst(102, energy("基本水能量", "水")),
        inst(103, energy("基本草能量", "草")),
        inst(104, basic("路人甲")),
        inst(105, basic("路人乙")),
    )
    return play_engine(PRO_DOC, "能量输送PRO", deck=deck)


def test_能量输送PRO_互异桶枚举_不含同属性双选() -> None:
    """「属性各不相同」：分桶互异枚举——同属性双选（100+101）不可达；
    上限 = 桶数 3（火/水/草）；min=0（「任意数量」可选 0）。"""
    e = pro_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool == "own_deck"
    assert pc.min_choose == 0 and pc.max_choose == 3
    assert pc.pool_iids == (100, 101, 102, 103)  # 非能量不入池
    choices = {tuple(a.choices) for a in e.legal_actions(0) if a.kind == "choose"}
    assert () in choices                       # 选 0 仅重洗
    assert (100, 102, 103) in choices          # 三属性各一可达
    assert not any(100 in c and 101 in c for c in choices)  # 同属性双选不可达


def test_能量输送PRO_选3入手_展示_重洗() -> None:
    e = pro_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(101, 102, 103)))
    p0 = e.state.players[0]
    assert all(i in [c.iid for c in p0.hand] for i in (101, 102, 103))
    assert sorted(c.iid for c in p0.deck) == [100, 104, 105]  # 未选留库（重洗后序由种子定）
    rev = prim_results(e, "reveal")[0]
    assert {101, 102, 103} <= set(rev["iids"])
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


def test_能量输送PRO_选0仅重洗() -> None:
    e = pro_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 104, 105]
    assert sorted(c.iid for c in p0.hand) == [50, 51]  # 手牌仅原有 2 张
    assert prim_results(e, "shuffle_deck")


# ── 新冲天能量（holder_stage 分层 + count=2 彩虹）────────────────────────────


def boost(iid: int) -> CardInstance:
    return inst(iid, special_energy("新冲天能量"))


def boost_board(holder: CardDef) -> GameEngine:
    state = main_state()
    mon = in_play(1, holder, 0).model_copy(update={"attached_energy": (boost(90),)})
    p0 = state.players[0].model_copy(update={"active": mon})
    e = engine_at_seed(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"新冲天能量": BOOST_DOC}
    return e


def attack_kinds(e: GameEngine, player: int = 0) -> list[int]:
    return [a.attack_index for a in e.legal_actions(player) if a.kind == "attack"]


def test_新冲天能量_2阶视作2个所有属性() -> None:
    """附着【2阶进化】：2 彩虹单元可抵【火】【水】（两有色符号）；3 符号费用不够。"""
    stage2 = poke("二阶兽", stage=2, evolves_from="一阶兽",
                  attacks=(AttackDef(name="双色击", cost=("火", "水"), damage=50),))
    assert 0 in attack_kinds(boost_board(stage2))
    stage2_heavy = poke("二阶重兽", stage=2, evolves_from="一阶兽",
                        attacks=(AttackDef(name="三色击", cost=("火", "水", "草"),
                                           damage=50),))
    assert attack_kinds(boost_board(stage2_heavy)) == []


def test_新冲天能量_非2阶视作1个无() -> None:
    """附着非 2 阶：仅 1 个【无】——无色费用可攻，有色费用不可攻。"""
    stage1_colorless = poke("一阶兽", stage=1, evolves_from="基础兽",
                            attacks=(AttackDef(name="打击", cost=("无",), damage=30),))
    assert 0 in attack_kinds(boost_board(stage1_colorless))
    stage1_fire = poke("一阶火兽", stage=1, evolves_from="基础兽",
                       attacks=(AttackDef(name="火击", cost=("火",), damage=30),))
    assert attack_kinds(boost_board(stage1_fire)) == []
    basic_fire = poke("基础火兽", attacks=(AttackDef(name="火击", cost=("火",),
                                           damage=30),))
    assert attack_kinds(boost_board(basic_fire)) == []


# ── 厄诡椪 碧草面具ex（特性手牌附草能 + 万叶阵雨计数伤害）─────────────────────


def ogerpon() -> CardDef:
    return poke("厄诡椪 碧草面具ex", hp=210, rule_box="ex", is_tera=True,
                has_ability=True, energy_type="草",
                attacks=(AttackDef(name="万叶阵雨", cost=("草", "草", "草"),
                                   damage=None),))


def ogerpon_engine(*, extra_hand: tuple = (), p1_active_energies: int = 0) -> GameEngine:
    state = main_state(p0_extra_hand=extra_hand)
    oger = in_play(1, ogerpon(), 0)
    p0 = state.players[0].model_copy(update={"active": oger})
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("硬兽", hp=500), p1_active_energies),
    })
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"厄诡椪 碧草面具ex": OGERPON_DOC}
    return e


def test_厄诡椪_碧草之舞_手牌草能量附自身_抽1() -> None:
    """特性全流：挂起选手牌基本【草】能量（火能量不入池）→ 附到特性持有者自身
    → 抽 1；当回合同名锁。"""
    e = ogerpon_engine(extra_hand=(inst(61, energy("基本草能量", "草")),
                                   inst(62, energy("基本火能量", "火"))))
    e.apply(0, Action(kind="use_ability", iid=1))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool == "own_hand"
    assert pc.pool_iids == (61,)  # 仅基本草能量入池
    e.apply(0, Action(kind="choose", choices=(61,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [61]  # 附到厄诡椪自身
    assert 61 not in [c.iid for c in p0.hand]
    assert 100 in [c.iid for c in p0.hand]  # 抽 1（牌库顶）
    assert len(p0.deck) == 9
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]  # 当回合锁


def test_厄诡椪_碧草之舞_手牌无草能量不可用() -> None:
    """可行性门：手牌无基本【草】能量 → 特性不枚举（无效果不发动）。"""
    e = ogerpon_engine(extra_hand=(inst(61, energy("基本火能量", "火")),))
    assert not [a for a in e.legal_actions(0)
                if a.kind == "use_ability" and a.iid == 1]


def test_厄诡椪_万叶阵雨_双方战斗场能量计数() -> None:
    """30 + 双方战斗宝可梦附着能量总数×30：自身 3 草 + 对手 2 能 → 30+5×30=180。"""
    oger = in_play(1, ogerpon(), 0).model_copy(update={
        "attached_energy": tuple(inst(9010 + i, energy("基本草能量", "草"))
                                 for i in range(3)),
    })
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": oger})
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("硬兽", hp=500), 2),
    })
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"厄诡椪 碧草面具ex": OGERPON_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 180
    assert prim_results(e, "damage")[0]["amount"] == 180


# ── 多龙巴鲁托ex（喷射头击白板 / 幻影潜袭铺伤分配）────────────────────────────


def dragapult() -> CardDef:
    return poke("多龙巴鲁托ex", hp=320, stage=2, evolves_from="多龙奇",
                rule_box="ex", is_tera=True, energy_type="龙", attacks=(
                    AttackDef(name="喷射头击", cost=("无",), damage=70),
                    AttackDef(name="幻影潜袭", cost=("火", "超"), damage=None),
                ))


def dragapult_engine(*, energies: tuple, p1_bench: tuple = ()) -> GameEngine:
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, dragapult(), 0).model_copy(
            update={"attached_energy": energies}),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("硬兽", hp=500), 1),
        "bench": p1_bench,
    })
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"多龙巴鲁托ex": DRAGAPULT_DOC}
    return e


def test_多龙巴鲁托ex_喷射头击_70白板() -> None:
    """喷射头击无效果文：引擎白板伤害结算，DSL 无绑定不重复结算。"""
    e = dragapult_engine(energies=(inst(9001, energy()),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 70
    assert not prim_results(e, "damage")  # 无 DSL damage 节点
    assert e.state.phase == "main" and e.state.current_player == 1


def test_多龙巴鲁托ex_幻影潜袭_200加6指示物任意分配() -> None:
    """主战 200 + 6 指示物逐只挂起分配：集中 4 + 分散 2 混合；统一落点后判昏厥。"""
    e = dragapult_engine(
        energies=(inst(9001, energy("基本火能量", "火")),
                  inst(9002, energy("基本超能量", "超"))),
        p1_bench=(in_play(80, basic("备战甲")), in_play(81, basic("备战乙"))),
    )
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 200
    for iid in (80, 80, 80, 80, 81, 81):  # 集中 4 + 分散 2
        pc = e.state.pending_choice
        assert pc is not None and pc.pool == "opponent_bench"
        e.apply(0, Action(kind="choose", choices=(iid,)))
    p1 = e.state.players[1]
    assert p1.bench[0].damage == 40 and p1.bench[1].damage == 20
    res = prim_results(e, "place_damage_counters")[0]
    assert res["placed"] == 6
    assert res["target_iids"] == [80, 80, 80, 80, 81, 81]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_多龙巴鲁托ex_幻影潜袭_对手无备战_铺伤noop() -> None:
    """对手备战空：主战 200 照常，铺伤段 no-op 不挂起。"""
    e = dragapult_engine(
        energies=(inst(9001, energy("基本火能量", "火")),
                  inst(9002, energy("基本超能量", "超"))),
    )
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 200
    assert e.state.pending_choice is None
    res = prim_results(e, "place_damage_counters")[0]
    assert res["placed"] == 0 and res["reason"] == "no_targets"
    assert e.state.phase == "main" and e.state.current_player == 1


# ── 清单 9：闸 1 防回归（故意取错印刷必被拦）─────────────────────────────────


@needs_db
def test_闸1_不公印章混入异文本印刷被拦_防回归(tmp_path, capsys):
    """不公印章等价类（CSV8C-173 / CSVM2bC-010）混入顶尖捕捉器印刷（CSV7C-180）
    → dsl-check --db 必须 FAIL（归一化 text_raw 不一致）。"""
    src = (CARDS_DIR / "不公印章.yml").read_text(encoding="utf-8")
    assert "card_ids: [CSV8C-173, CSVM2bC-010]" in src
    p = tmp_path / "不公印章.yml"
    p.write_text(src.replace("card_ids: [CSV8C-173, CSVM2bC-010]",
                             "card_ids: [CSV8C-173, CSVM2bC-010, CSV7C-180]", 1),
                 encoding="utf-8")
    rc = cli_main(["dsl-check", str(p), "--db", str(DB_PATH)])
    out = capsys.readouterr().out
    assert rc == 1 and "FAIL" in out and "文本" in out
