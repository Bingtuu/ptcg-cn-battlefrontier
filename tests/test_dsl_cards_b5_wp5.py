"""单卡 DSL 测试（task 026 WP5）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批卡（任意数量弃置×N 伤害族 / modify_attack_cost / 白蕾雅奖赏加成 / until_tails /
bounce attachments=hand / transform）：
- 赛富豪ex（G 标 CSV4C-089 淘金潮等价类 7 印刷）：特性嘉奖硬币（once_per_turn +
  draw 1 + if_self_active 追加 draw 1）+ 淘金潮 50×（discard own_hand any_count）。
- 猛雷鼓ex（H 标 CSV7C-154 等价类 7 印刷）：飞溅咆哮（discard all + draw 6）+
  极雷轰 70×（discard own_attached_energy any_count）。
- 猛雷鼓（H 标 CSV8C-161 落雷风暴等价类 2 印刷）：attached_energy_on_target×30 +
  龙之头击 130 白板。
- 月月熊 赫月ex（H 标 CSV8C-172 等价类 8 印刷）：老练招式（modify_attack_cost
  opponent_taken_prizes）+ 血月 240 + lock_attack。
- 白蕾雅（H 标 CSV9.5C-197 等价类 6 印刷）：on_play opponent_prizes_eq:2 + prize_bonus。
- 索财灵（G 标 CSV4C-063 连掷硬币等价类 3 印刷）：coin_flip until_tails ×20。
- 牡丹（G 标 CSV1C-124 等价类 5 印刷）：bounce basic_pokemon attachments=hand。
- 百变怪（G 标 151C-132 变身启动等价类 4 印刷）：transform + shuffle_deck。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state, stage1

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import AttackDef, CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

GHOLDENGO_DOC = load_card_doc(CARDS_DIR / "赛富豪ex.yml")
RAGINGBOLT_EX_DOC = load_card_doc(CARDS_DIR / "猛雷鼓ex.yml")
RAGINGBOLT_DOC = load_card_doc(CARDS_DIR / "猛雷鼓.yml")
URSALUNA_DOC = load_card_doc(CARDS_DIR / "月月熊 赫月ex.yml")
BRIAR_DOC = load_card_doc(CARDS_DIR / "白蕾雅.yml")
GIMMIGHOUL_DOC = load_card_doc(CARDS_DIR / "索财灵-连掷硬币.yml")
MOMO_DOC = load_card_doc(CARDS_DIR / "牡丹.yml")
DITTO_DOC = load_card_doc(CARDS_DIR / "百变怪-变身启动.yml")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def engine_at_seed(state, seed: int) -> GameEngine:
    e = GameEngine(RandomSource(seed))
    e.state = state
    return e


def deck10() -> tuple:
    """p0 牌库 10 张填充宝可梦（iid 100-109）。"""
    return tuple(inst(100 + i, basic(f"库{chr(19968 + i)}")) for i in range(10))


# ── 赛富豪ex（嘉奖硬币 + 淘金潮 50×）（清单 19）────────────────────────────────


def gholdengo() -> CardDef:
    return CardDef(
        card_id="stub-赛富豪ex", name="赛富豪ex", supertype="pokemon",
        hp=260, stage=1, evolves_from="索财灵", rule_box="ex", energy_type="钢",
        attacks=(AttackDef(name="淘金潮", cost=("钢",), damage=None),),
        retreat_cost=2, weakness="火", resistance="草",
    )


def gholdengo_engine(*, on_bench: bool = False, p0_hand=None, p1_prizes: int = 6,
                     seed: int = 0):
    """main 阶段：p0 赛富豪ex（默认战斗场 iid 1；on_bench 时备战区 iid 70，
    战斗场占位兽 iid 1）。"""
    state = main_state()
    mon = in_play(70 if on_bench else 1, gholdengo())
    update: dict[str, object] = {"deck": deck10()}
    if on_bench:
        update["bench"] = (mon,)
    else:
        update["active"] = mon
    if p0_hand is not None:
        update["hand"] = p0_hand
    p0 = state.players[0].model_copy(update=update)
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("硬兽", hp=500), 1),
        "prizes": state.players[1].prizes[:p1_prizes],
    })
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}), seed)
    e.card_effects = {"赛富豪ex": GHOLDENGO_DOC}
    return e


def test_赛富豪ex_嘉奖硬币_战斗场抽2():
    """特性嘉奖硬币：战斗场发动 → draw 1 + if_self_active 追加 draw 1（共 2 张）。"""
    e = gholdengo_engine()
    e.apply(0, Action(kind="use_ability", iid=1))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51, 100, 101]
    assert e.state.phase == "main" and e.state.current_player == 0


def test_赛富豪ex_嘉奖硬币_备战位抽1():
    """备战位发动：只有基础 draw 1（追加抽的节点门控跳过并落 skipped 事件）。"""
    e = gholdengo_engine(on_bench=True)
    e.apply(0, Action(kind="use_ability", iid=70))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51, 100]
    skipped = [ev for ev in e.events
               if ev.kind == "effect_primitive" and ev.detail.get("result", {}).get("skipped")]
    assert len(skipped) == 1 and skipped[0].detail["params"]["condition"] == "if_self_active"


def test_赛富豪ex_淘金潮_弃3张150():
    """淘金潮：手牌 3 张基本能量全弃 → 150 伤害；非能量留手。"""
    hand = (
        inst(50, energy("钢能量", "钢")), inst(51, energy("火能量", "火")),
        inst(52, energy("草能量", "草")), inst(53, basic("非能量")),
    )
    e = gholdengo_engine(p0_hand=hand)
    active = e.state.players[0].active.model_copy(update={
        "attached_energy": (inst(9001, energy("钢能量", "钢")),),
    })
    e._set_player(0, e.state.players[0].model_copy(update={"active": active}))
    e.apply(0, Action(kind="attack", attack_index=0))
    pc = e.state.pending_choice
    assert pc.pool_iids == (50, 51, 52) and pc.min_choose == 0
    e.apply(0, Action(kind="choose", choices=(50, 51, 52)))
    assert e.state.players[1].active.damage == 150
    assert [c.iid for c in e.state.players[0].hand] == [53]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_赛富豪ex_淘金潮_弃0张伤害0可宣言():
    """淘金潮选 0 张：伤害 0、招式可宣言、回合推进（D-WP5-1）。"""
    e = gholdengo_engine(p0_hand=(inst(50, energy("钢能量", "钢")),))
    active = e.state.players[0].active.model_copy(update={
        "attached_energy": (inst(9001, energy("钢能量", "钢")),),
    })
    e._set_player(0, e.state.players[0].model_copy(update={"active": active}))
    assert Action(kind="attack", attack_index=0) in e.legal_actions(0)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=()))
    assert e.state.players[1].active.damage == 0
    assert e.state.phase == "main" and e.state.current_player == 1


# ── 猛雷鼓ex（飞溅咆哮 + 极雷轰 70×）（清单 20）────────────────────────────────


def ragingbolt_ex() -> CardDef:
    return CardDef(
        card_id="stub-猛雷鼓ex", name="猛雷鼓ex", supertype="pokemon",
        hp=240, stage=0, rule_box="ex", energy_type="龙",
        attacks=(
            AttackDef(name="飞溅咆哮", cost=("无",), damage=None),
            AttackDef(name="极雷轰", cost=("雷", "斗"), damage=None),
        ),
        retreat_cost=3,
    )


def ragingbolt_ex_engine(*, p0_hand=None, p0_bench: tuple = (), energies: tuple = ()):
    """main 阶段：p0 战斗场猛雷鼓ex（iid 1）。"""
    state = main_state()
    active = in_play(1, ragingbolt_ex()).model_copy(update={"attached_energy": energies})
    update: dict[str, object] = {
        "active": active, "bench": p0_bench, "deck": deck10(),
    }
    if p0_hand is not None:
        update["hand"] = p0_hand
    p0 = state.players[0].model_copy(update=update)
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("硬兽", hp=500), 1),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"猛雷鼓ex": RAGINGBOLT_EX_DOC}
    return e


def test_猛雷鼓ex_飞溅咆哮_全弃抽6():
    """飞溅咆哮：手牌全部弃置 → 抽 6 张。"""
    hand = (inst(50, basic("小火龙")), inst(51, energy()), inst(52, item_card("物品甲")))
    e = ragingbolt_ex_engine(p0_hand=hand, energies=(inst(9001, energy()),))
    e.apply(0, Action(kind="attack", attack_index=0))
    p0 = e.state.players[0]
    assert sorted(c.iid for c in p0.discard) == [50, 51, 52]
    assert [c.iid for c in p0.hand] == [100, 101, 102, 103, 104, 105]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_猛雷鼓ex_极雷轰_跨宝可梦弃2张140():
    """极雷轰：场上全体附着能量池（战斗场 2 + 备战 1），跨两只摘 2 张 → 140。"""
    energies = (inst(9001, energy("雷能量", "雷")), inst(9002, energy("斗能量", "斗")))
    bench = in_play(70, basic("备战兽")).model_copy(update={
        "attached_energy": (inst(9070, energy("雷能量", "雷")),),
    })
    e = ragingbolt_ex_engine(energies=energies, p0_bench=(bench,))
    e.apply(0, Action(kind="attack", attack_index=1))
    pc = e.state.pending_choice
    assert pc.pool == "own_attached_energy"
    assert pc.pool_iids == (9001, 9002, 9070)
    e.apply(0, Action(kind="choose", choices=(9002, 9070)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [9001]
    assert p0.bench[0].attached_energy == ()
    assert e.state.players[1].active.damage == 140


def test_猛雷鼓ex_极雷轰_选0伤害0():
    """极雷轰选 0 张：伤害 0、能量保留、回合推进（D-WP5-1）。"""
    energies = (inst(9001, energy("雷能量", "雷")), inst(9002, energy("斗能量", "斗")))
    e = ragingbolt_ex_engine(energies=energies)
    e.apply(0, Action(kind="attack", attack_index=1))
    e.apply(0, Action(kind="choose", choices=()))
    assert e.state.players[1].active.damage == 0
    assert [c.iid for c in e.state.players[0].active.attached_energy] == [9001, 9002]


# ── 猛雷鼓（落雷风暴 + 龙之头击 130）（清单 21）────────────────────────────────


def ragingbolt() -> CardDef:
    return CardDef(
        card_id="stub-猛雷鼓", name="猛雷鼓", supertype="pokemon",
        hp=130, stage=0, energy_type="龙",
        attacks=(
            AttackDef(name="落雷风暴", cost=("雷", "斗"), damage=None),
            AttackDef(name="龙之头击", cost=("雷", "斗", "无"), damage=130),
        ),
        retreat_cost=3,
    )


def ragingbolt_engine(*, p1_active=None, p1_bench: tuple = (), energies: tuple = ()):
    """main 阶段：p0 战斗场猛雷鼓（iid 1）。"""
    state = main_state()
    active = in_play(1, ragingbolt()).model_copy(update={"attached_energy": energies})
    p0 = state.players[0].model_copy(update={"active": active})
    p1 = state.players[1].model_copy(update={
        "active": p1_active if p1_active is not None
        else in_play(2, basic("硬兽", hp=500), 1),
        "bench": p1_bench,
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"猛雷鼓": RAGINGBOLT_DOC}
    return e


def storm_cost() -> tuple:
    return (inst(9001, energy("雷能量", "雷")), inst(9002, energy("斗能量", "斗")))


def test_猛雷鼓_落雷风暴_目标2能60():
    """落雷风暴：对手战斗场 2 能 → 60 伤害（choose=1 选目标）。"""
    p1_active = in_play(2, basic("硬兽", hp=500), 2)
    e = ragingbolt_engine(p1_active=p1_active, energies=storm_cost())
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[1].active.damage == 60


def test_猛雷鼓_落雷风暴_备战目标不计算弱抗():
    """落雷风暴备战目标：弱点命中仍不翻倍（卡面 rule_reference 句 = 引擎贯穿规则）。"""
    weak = CardDef(
        card_id="stub-弱龙兽", name="弱龙兽", supertype="pokemon",
        hp=500, stage=0, weakness="龙",
        attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
    )
    e = ragingbolt_engine(p1_bench=(in_play(70, weak, 3),), energies=storm_cost())
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(70,)))
    assert e.state.players[1].bench[0].damage == 90  # 3×30，不 ×2


def test_猛雷鼓_落雷风暴_目标0能伤害0():
    """落雷风暴：目标无能量 → 伤害 0。"""
    p1_active = in_play(2, basic("硬兽", hp=500), 0)
    e = ragingbolt_engine(p1_active=p1_active, energies=storm_cost())
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[1].active.damage == 0


def test_猛雷鼓_龙之头击_白板130():
    """龙之头击 130：白板伤害招式（无 DSL 绑定），AttackDef.damage 直接结算。"""
    energies = storm_cost() + (inst(9003, energy("雷能量", "雷")),)
    e = ragingbolt_engine(energies=energies)
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 130
    assert e.state.phase == "main" and e.state.current_player == 1


# ── 月月熊 赫月ex（老练招式 + 血月 240 + lock_attack）（清单 22）─────────────────


def ursaluna() -> CardDef:
    return CardDef(
        card_id="stub-月月熊 赫月ex", name="月月熊 赫月ex", supertype="pokemon",
        hp=260, stage=0, rule_box="ex", energy_type="无",
        attacks=(AttackDef(name="血月", cost=("无",) * 5, damage=240),),
        retreat_cost=3, weakness="斗",
    )


def ursaluna_engine(*, energies: tuple, p1_prizes: int):
    """main 阶段：p0 战斗场月月熊 赫月ex（iid 1）；p1 剩余奖赏可调。"""
    state = main_state()
    active = in_play(1, ursaluna()).model_copy(update={"attached_energy": energies})
    p0 = state.players[0].model_copy(update={"active": active})
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("硬兽", hp=500), 1),
        "prizes": state.players[1].prizes[:p1_prizes],
        "bench": (in_play(70, basic("对手备战")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"月月熊 赫月ex": URSALUNA_DOC}
    return e


def test_月月熊赫月ex_老练招式_费用三档():
    """老练招式：对手拿 0/2/5 奖赏 → 血月费用 5/3/0 个【无】（枚举层求值点）。"""
    colorless = lambda n: tuple(inst(9001 + i, energy()) for i in range(n))
    # 拿 0：5 能量可宣言、4 不可
    e = ursaluna_engine(energies=colorless(5), p1_prizes=6)
    assert Action(kind="attack", attack_index=0) in e.legal_actions(0)
    e = ursaluna_engine(energies=colorless(4), p1_prizes=6)
    assert not [a for a in e.legal_actions(0) if a.kind == "attack"]
    # 拿 2：3 能量可宣言
    e = ursaluna_engine(energies=colorless(3), p1_prizes=4)
    assert Action(kind="attack", attack_index=0) in e.legal_actions(0)
    # 拿 5：0 能量可宣言（clamp 下限 0）
    e = ursaluna_engine(energies=(), p1_prizes=1)
    assert Action(kind="attack", attack_index=0) in e.legal_actions(0)


def test_月月熊赫月ex_血月_240加招式锁():
    """血月：240 伤害 + lock_attack——下个自己回合不可宣言，再下个解禁（裁决 2 口径）。"""
    colorless = tuple(inst(9001 + i, energy()) for i in range(5))
    e = ursaluna_engine(energies=colorless, p1_prizes=6)
    e.apply(0, Action(kind="attack", attack_index=0))  # 血月 @turn 2
    assert e.state.players[1].active.damage == 240
    assert e.state.players[0].active.attack_locks == ("血月",)
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 3
    assert not [a for a in e.legal_actions(0) if a.kind == "attack"]  # 锁定
    e.apply(0, Action(kind="end_turn"))
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 4
    assert [a for a in e.legal_actions(0) if a.kind == "attack"]  # 解禁


# ── 白蕾雅（opponent_prizes_eq:2 + 奖赏加成）（清单 23）────────────────────────


def briar_engine(*, p1_prizes: int, attacker: CardDef, p1_active_hp: int = 20):
    """main 阶段：p0 手牌白蕾雅（iid 60，支援者）+ 战斗场攻击者（附 1 能量）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": (inst(60, supporter_card("白蕾雅")),),
        "active": in_play(1, attacker, 1),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("小火龙", hp=p1_active_hp), 1),
        "prizes": state.players[1].prizes[:p1_prizes],
        "bench": (in_play(70, basic("对手备战")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"白蕾雅": BRIAR_DOC}
    return e


def tera_mon(name: str = "太晶兽") -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=130, stage=0, is_tera=True,
        attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
    )


def test_白蕾雅_条件门():
    """对手剩余奖赏 ≠2 → 不可使用；=2 → 可使用（playable condition 门）。"""
    e = briar_engine(p1_prizes=3, attacker=tera_mon())
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer"]
    e2 = briar_engine(p1_prizes=2, attacker=tera_mon())
    assert Action(kind="play_trainer", iid=60) in e2.legal_actions(0)


def test_白蕾雅_太晶招式昏厥拿2():
    """使用后本回合太晶宝可梦招式伤害昏厥对手战斗场 → 拿 2 张（1+1）。"""
    e = briar_engine(p1_prizes=2, attacker=tera_mon())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert len(e.state.players[0].prizes) == 4  # 拿 2 张：6 − 2
    assert len([ev for ev in e.events if ev.kind == "take_prize"]) == 2


def test_白蕾雅_非太晶不加成():
    """非太晶宝可梦招式昏厥 → 不加成（拿 1 张）。"""
    plain = CardDef(
        card_id="stub-凡兽", name="凡兽", supertype="pokemon",
        hp=130, stage=0, attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
    )
    e = briar_engine(p1_prizes=2, attacker=plain)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert len(e.state.players[0].prizes) == 5


def test_白蕾雅_次回合失效():
    """回合级标记：次回合太晶招式昏厥只拿 1 张（turn scoped 清除）。"""
    e = briar_engine(p1_prizes=2, attacker=tera_mon())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="end_turn"))
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 3，标记已清
    e.apply(0, Action(kind="attack", attack_index=0))
    assert len(e.state.players[0].prizes) == 5


# ── 索财灵（连掷硬币 until_tails ×20）（清单 24）────────────────────────────────


def gimmighoul() -> CardDef:
    return CardDef(
        card_id="stub-索财灵", name="索财灵", supertype="pokemon",
        hp=70, stage=0, energy_type="超",
        attacks=(AttackDef(name="连掷硬币", cost=("无",), damage=None),),
        retreat_cost=2, weakness="恶", resistance="斗",
    )


def gimmighoul_engine(seed: int):
    """main 阶段：p0 战斗场索财灵（iid 1，附 1 能量）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, gimmighoul(), 1),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("硬兽", hp=500), 1),
    })
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}), seed)
    e.card_effects = {"索财灵": GIMMIGHOUL_DOC}
    return e


def test_索财灵_连掷硬币_种子锁定序列():
    """seed 2 → 正正正正反（RandomSource 实测）：伤害 4×20=80；同种子复跑一致。"""
    for _ in range(2):
        e = gimmighoul_engine(seed=2)
        e.apply(0, Action(kind="attack", attack_index=0))
        assert e.state.players[1].active.damage == 80
        flip = next(ev for ev in e.events
                    if ev.kind == "effect_primitive"
                    and ev.detail.get("action") == "coin_flip")
        assert flip.detail["result"]["flips"] == [
            "heads", "heads", "heads", "heads", "tails",
        ]


def test_索财灵_连掷硬币_首反0伤害():
    """首掷即反面（seed 1）→ 正面 0 次 → 伤害 0，回合照常推进。"""
    e = gimmighoul_engine(seed=1)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0
    assert e.state.phase == "main" and e.state.current_player == 1


# ── 牡丹（bounce basic_pokemon attachments=hand）（清单 25）─────────────────────


def momo_engine(*, p0_bench: tuple = (), p0_active=None):
    """main 阶段：p0 手牌牡丹（iid 60，支援者）；备战/战斗场可调。"""
    state = main_state(p0_extra_hand=(inst(60, supporter_card("牡丹")),))
    p0 = state.players[0].model_copy(update={"bench": p0_bench})
    if p0_active is not None:
        p0 = p0.model_copy(update={"active": p0_active})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"牡丹": MOMO_DOC}
    return e


def test_牡丹_整叠能量道具回手():
    """牡丹：基础宝可梦整叠 + 附着能量/道具全部回手牌（不弃置）。"""
    bench_mon = in_play(70, basic("回手兽")).model_copy(update={
        "attached_energy": (inst(9070, energy("草能量", "草")),),
        "attached_tool": inst(80, tool_card("测试道具")),
    })
    e = momo_engine(p0_bench=(bench_mon,))
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(70,)))
    p0 = e.state.players[0]
    assert sorted(c.iid for c in p0.hand) == [50, 51, 70, 80, 9070]
    assert [c.iid for c in p0.discard] == [60]  # 仅支援者本体
    assert p0.bench == ()


def test_牡丹_战斗场回手后换上():
    """战斗场目标 bounce → 换上流程 → resume_after_promotes 回主阶段（不变式回归）。"""
    e = momo_engine(p0_bench=(in_play(70, basic("备战兽")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(1,)))  # 回手战斗场（妙蛙种子 stub）
    assert e.state.phase == "promote" and e.state.current_player == 0
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert 1 in [c.iid for c in e.state.players[0].hand]


def test_牡丹_进化体不可选():
    """basic_pokemon 场上过滤器负例：进化体（栈顶 stage≥1）不进选择池。"""
    evolved = in_play(70, basic("底兽")).model_copy(update={
        "stack": (inst(70, basic("底兽")), inst(71, stage1("顶兽", "底兽"))),
    })
    e = momo_engine(p0_bench=(evolved,))
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.pool_iids == (1,)  # 仅战斗场基础可选


# ── 百变怪（变身启动 transform）（清单 26）─────────────────────────────────────


def ditto() -> CardDef:
    return CardDef(
        card_id="stub-百变怪", name="百变怪", supertype="pokemon",
        hp=60, stage=0, energy_type="无",
        attacks=(AttackDef(name="粘粑粑", cost=("无",), damage=10),),
        retreat_cost=1, weakness="斗",
    )


def ditto_deck() -> tuple:
    """牌库：替换兽(100, 基础) + 百变怪(101, not_name 排除) + 顶兽(102, stage1 排除)
    + 填充兽(103, 基础)。"""
    return (
        inst(100, basic("替换兽")), inst(101, ditto()),
        inst(102, stage1("顶兽", "替换兽")), inst(103, basic("填充兽")),
    )


def ditto_engine(*, deck=None, turn: int = 1, on_bench: bool = False):
    """main 阶段：p0 百变怪（默认战斗场 iid 1；on_bench 时备战区）。"""
    state = main_state()
    mon = in_play(70 if on_bench else 1, ditto(), 1)
    update: dict[str, object] = {}
    if on_bench:
        update["bench"] = (mon,)
    else:
        update["active"] = mon
    if deck is not None:
        update["deck"] = deck
    p0 = state.players[0].model_copy(update=update)
    e = engine_at(state.model_copy(update={
        "players": (p0, state.players[1]), "turn": turn,
    }))
    e.card_effects = {"百变怪": DITTO_DOC}
    return e


def test_百变怪_变身启动_全流():
    """变身全流：选替换兽 → 百变怪整叠+附着能量进弃牌区、替换兽入战斗场
    （entered_play 登记）→ 重洗；不触发昏厥/奖赏/换上。"""
    e = ditto_engine(deck=ditto_deck())
    acts = [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    assert acts and acts[0].iid == 1
    e.apply(0, acts[0])
    pc = e.state.pending_choice
    assert pc.pool_iids == (100, 103)  # 百变怪/进化被排除
    e.apply(0, Action(kind="choose", choices=(100,)))
    p0 = e.state.players[0]
    assert p0.active.current.card.name == "替换兽" and p0.active.damage == 0
    assert 100 in p0.entered_play_this_turn
    assert sorted(c.iid for c in p0.discard) == [1, 9010]  # 整叠 + 附着能量
    assert sorted(c.iid for c in p0.deck) == [101, 102, 103]
    assert [c.iid for c in p0.deck] != [101, 102, 103]  # 重洗
    assert not [ev for ev in e.events if ev.kind in ("knockout", "take_prize")]
    assert e.state.phase == "main" and e.state.current_player == 0


def test_百变怪_变身启动_牌库无合法目标_noop重洗():
    """牌库全是百变怪/进化/训练家 → no-op（不挂起、百变怪留场），重洗仍执行。"""
    deck = (inst(100, ditto()), inst(101, stage1("顶兽", "替换兽")),
            inst(102, item_card("物品甲")), inst(103, ditto()))
    e = ditto_engine(deck=deck)
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "main" and e.state.pending_choice is None
    p0 = e.state.players[0]
    assert p0.active.current.card.name == "百变怪"
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103]
    assert [c.iid for c in p0.deck] != [100, 101, 102, 103]


def test_百变怪_变身启动_备战位不发动():
    """self_is_active 门：备战位百变怪特性不枚举。"""
    e = ditto_engine(deck=ditto_deck(), on_bench=True)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


def test_百变怪_变身启动_非首回合不发动():
    """first_own_turn 门：turn==2 特性不枚举。"""
    e = ditto_engine(deck=ditto_deck(), turn=2)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]
