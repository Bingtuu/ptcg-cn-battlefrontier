"""单卡 DSL 测试（task 029 卡牌批）：从 cards/ 真实文件装载（load_card_doc），
stub 引擎驱动效果全链路（含 chooser 挂起选择）。

本批 8 张（持续 lock/suppression 体系 + C 级收尾）：
- 含羞苞：痒痒花粉 10 + lock_play 物品锁（对手下回合物品不枚举）。
- 巨钳螳螂-惩罚巨钳：10+对手场上特性宝可梦数×50（opponent_ability_pokemon_count）；
  居合劈 70 白板。
- 旋转洛托姆-风扇呼唤：ability_manual + once_per_turn_shared + first_own_turn，
  检索 ≤3 张 HP≤100【无】宝可梦 + reveal + 重洗；突击登陆 70（stadium_in_play
  招式失败门）。
- 火箭队的监视塔：suppress_ability（双方场上【无】宝可梦特性全消，枚举门 +
  离场恢复）。
- 玛俐的长毛巨魔ex：庞克泵感（own_evolve_from_hand + attach_energy own_deck
  distribute，≤5 基本恶能量任意分配于玛俐的宝可梦）；暗影子弹 180 + 备战狙击 30。
- 赫普的苍响ex：刹那斩 30 + 备战狙击 30；英勇之刃 240 + lock_attack 冷却。
- 阻碍之塔：suppress_tool（道具 modify_hp 失效，有效 HP 回落）。
- 黑夜魔灵-咒怨炸弹：ko_self + 13 个伤害指示物（彷徨夜灵同构）；影子束缚 150 +
  lock_retreat（沙铃仙人掌同构）。
"""

from pathlib import Path

from helpers import energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.state import AttackDef, CardDef, CardInstance

CARDS_DIR = Path(__file__).parent.parent / "cards"

BUDEW_DOC = load_card_doc(CARDS_DIR / "含羞苞.yml")
SCIZOR_DOC = load_card_doc(CARDS_DIR / "巨钳螳螂-惩罚巨钳.yml")
ROTOM_DOC = load_card_doc(CARDS_DIR / "旋转洛托姆-风扇呼唤.yml")
WATCHTOWER_DOC = load_card_doc(CARDS_DIR / "火箭队的监视塔.yml")
GRIMMSNARL_DOC = load_card_doc(CARDS_DIR / "玛俐的长毛巨魔ex.yml")
ZACIAN_DOC = load_card_doc(CARDS_DIR / "赫普的苍响ex.yml")
BLOCKER_DOC = load_card_doc(CARDS_DIR / "阻碍之塔.yml")
DUSKNOIR_DOC = load_card_doc(CARDS_DIR / "黑夜魔灵-咒怨炸弹.yml")


# ── 夹具 ─────────────────────────────────────────────────────────────


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


def trainer(name: str, subtype: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype=subtype)


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


def play_trainer_iids(e: GameEngine, player: int) -> list[int]:
    return [a.iid for a in e.legal_actions(player) if a.kind == "play_trainer"]


def attack_kinds(e: GameEngine, player: int = 0) -> list[int]:
    return [a.attack_index for a in e.legal_actions(player) if a.kind == "attack"]


def prim_results(e: GameEngine, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


# ── 含羞苞（痒痒花粉：damage 10 + lock_play 物品锁）─────────────────────

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


def budew() -> CardDef:
    return mon_card("含羞苞", hp=30, energy_type="草", attacks=(
        AttackDef(name="痒痒花粉", cost=(), damage=None),))


def budew_engine() -> GameEngine:
    """p0 含羞苞攻击位（0 费招式）；p1 手牌 = 物品/支援者。"""
    return board(
        p0_active=in_play(1, budew()),
        p1_hand=(inst(60, trainer("测试物品", "物品")),
                 inst(61, trainer("测试支援者", "支援者"))),
        effects={"含羞苞": BUDEW_DOC, "测试物品": ITEM_DOC, "测试支援者": SUPPORTER_DOC},
    )


def test_含羞苞_痒痒花粉_伤害10加对手物品锁() -> None:
    """攻击后：对手战斗场 10 伤害 + 物品锁标记；对手下回合物品不枚举（枚举门），
    支援者照常。"""
    e = budew_engine()
    e.apply(0, Action(kind="attack", attack_index=0))  # turn 2，p0 攻击
    assert e.state.players[1].active.damage == 10
    assert e.state.players[1].item_lock_mark == (2, 0)  # (施加时 turn, 施加方)
    assert e.state.phase == "main" and e.state.current_player == 1
    iids = play_trainer_iids(e, 1)
    assert 60 not in iids  # 物品被锁
    assert 61 in iids      # 支援者照常


def test_含羞苞_物品锁_隔一回合恢复() -> None:
    """被锁回合结束解除：再下个自己回合物品重新可打出。"""
    e = budew_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert 60 not in play_trainer_iids(e, 1)
    e.apply(1, Action(kind="end_turn"))  # p1 被锁回合结束 → 解除
    assert e.state.players[1].item_lock_mark is None
    e.apply(0, Action(kind="end_turn"))  # → p1 下回合
    assert 60 in play_trainer_iids(e, 1)


# ── 巨钳螳螂（惩罚巨钳 ×50 计数 / 居合劈 70 白板）──────────────────────


def scizor() -> CardDef:
    return mon_card(
        "巨钳螳螂", hp=140, energy_type="钢", stage=1, evolves_from="飞天螳螂",
        attacks=(
            AttackDef(name="惩罚巨钳", cost=("钢",), damage=None),
            AttackDef(name="居合劈", cost=("钢", "钢"), damage=70),
        ),
    )


def steel_energies(base_iid: int, n: int) -> tuple:
    return tuple(inst(base_iid + i, energy("基本钢能量", "钢")) for i in range(n))


def scizor_engine(p1_active, p1_bench: tuple = ()) -> GameEngine:
    return board(
        p0_active=in_play(1, scizor(), 0).model_copy(
            update={"attached_energy": steel_energies(9001, 2)}),
        p1_active=p1_active, p1_bench=p1_bench,
        effects={"巨钳螳螂": SCIZOR_DOC},
    )


def test_巨钳螳螂_惩罚巨钳_特性0只10_2只110() -> None:
    """对手场上拥有特性的宝可梦 0/2 只 → 10+0 / 10+2×50=110。"""
    plain = mon_card("白板兽", hp=500)
    gifted = mon_card("特性兽", hp=500, has_ability=True)
    e0 = scizor_engine(in_play(2, plain))
    e0.apply(0, Action(kind="attack", attack_index=0))
    assert e0.state.players[1].active.damage == 10
    e2 = scizor_engine(in_play(2, gifted), (in_play(80, gifted), in_play(81, plain)))
    e2.apply(0, Action(kind="attack", attack_index=0))
    assert e2.state.players[1].active.damage == 110


def test_巨钳螳螂_居合劈_70白板() -> None:
    """居合劈无效果文：引擎白板伤害 70，DSL 不绑定（无 effect_primitive 事件）。"""
    e = scizor_engine(in_play(2, mon_card("硬兽", hp=500)))
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 70
    assert not [ev for ev in e.events if ev.kind == "effect_primitive"]


# ── 旋转洛托姆（风扇呼唤检索 / 突击登陆竞技场门）─────────────────────────


def rotom() -> CardDef:
    return mon_card("旋转洛托姆", hp=70, has_ability=True, attacks=(
        AttackDef(name="突击登陆", cost=("无",), damage=None),))


def rotom_deck() -> tuple:
    return (
        inst(300, mon_card("无色小兽", hp=80, energy_type="无")),   # 命中
        inst(301, mon_card("无色大兽", hp=120, energy_type="无")),  # HP>100 排除
        inst(302, mon_card("超能小兽", hp=50, energy_type="超")),   # 超属性排除
        inst(303, energy("基本恶能量", "恶")),
        inst(310, energy()), inst(311, energy()), inst(312, energy()),
    )


def rotom_ability_engine(*, turn: int = 1, second: bool = False) -> GameEngine:
    """p0 战斗场旋转洛托姆（iid 1）；second=True 时备战再放 1 只（iid 70）。"""
    return board(
        p0_active=in_play(1, rotom()),
        p0_bench=(in_play(70, rotom()),) if second else (),
        p0_deck=rotom_deck(),
        turn=turn,
        effects={"旋转洛托姆": ROTOM_DOC},
    )


def test_旋转洛托姆_风扇呼唤_首回合检索_同名共享锁() -> None:
    """首回合两只均枚举；发动后检索池仅【无】且 HP≤100（超属性/HP>100 排除），
    入手 + reveal 事件 + 重洗；同名共享锁生效（第二只本回合不可用）。"""
    e = rotom_ability_engine(second=True)
    assert sorted(ability_iids(e)) == [1, 70]
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "choice"
    assert e.state.pending_choice.pool_iids == (300,)  # 检索过滤
    e.apply(0, Action(kind="choose", choices=(300,)))
    p0 = e.state.players[0]
    assert 300 in [c.iid for c in p0.hand]
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert reveal.detail["iids"] == [300] and reveal.detail["names"] == ["无色小兽"]
    assert any(ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"
               for ev in e.events)
    assert sorted(c.iid for c in p0.deck) == [301, 302, 303, 310, 311, 312]
    assert e.state.phase == "main" and e.state.current_player == 0
    assert ability_iids(e) == []  # once_per_turn_shared：同名共享锁


def test_旋转洛托姆_风扇呼唤_非首回合不可用() -> None:
    """first_own_turn 门：turn==2 特性不枚举。"""
    e = rotom_ability_engine(turn=2, second=True)
    assert ability_iids(e) == []


def rotom_attack_engine(*, with_stadium: bool) -> GameEngine:
    return board(
        p0_active=in_play(1, rotom(), 1),
        stadium=inst(399, trainer("普通场", "竞技场")) if with_stadium else None,
        effects={"旋转洛托姆": ROTOM_DOC},
    )


def test_旋转洛托姆_突击登陆_无竞技场招式失败() -> None:
    """场上无竞技场：condition stadium_in_play 不满足 → 招式失败（不结算、
    攻击机会消耗、回合移交，古月鸟口径）。"""
    e = rotom_attack_engine(with_stadium=False)
    e.apply(0, Action(kind="attack", attack_index=0))
    attack_ev = next(ev for ev in e.events if ev.kind == "attack")
    assert attack_ev.detail["failed"] is True
    assert attack_ev.detail["condition"] == "stadium_in_play"
    assert e.state.players[1].active.damage == 0
    assert e.state.phase == "main" and e.state.current_player == 1


def test_旋转洛托姆_突击登陆_有竞技场70() -> None:
    """场上有竞技场：条件满足，招式正常 70。"""
    e = rotom_attack_engine(with_stadium=True)
    e.apply(0, Action(kind="attack", attack_index=0))
    attack_ev = next(ev for ev in e.events if ev.kind == "attack")
    assert "failed" not in attack_ev.detail
    assert e.state.players[1].active.damage == 70


# ── 火箭队的监视塔（suppress_ability：【无】特性消除）────────────────────


def ability_doc(name: str):
    return parse_card_doc(f"""
card:
  name_group: {name}
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {{action: draw, count: 1}}
""")


def watchtower() -> CardInstance:
    return inst(399, trainer("火箭队的监视塔", "竞技场"))


def test_火箭队的监视塔_无属性特性消除() -> None:
    """监视塔在场：双方【无】宝可梦 ability_manual 不枚举（对手侧同口径）；
    非【无】（超属性）照常。"""
    colorless = mon_card("特性兽", energy_type="无", has_ability=True)
    psychic = mon_card("超特性兽", energy_type="超", has_ability=True)
    fx = {"火箭队的监视塔": WATCHTOWER_DOC, "特性兽": ability_doc("特性兽"),
          "超特性兽": ability_doc("超特性兽")}
    plain = board(p0_active=in_play(1, colorless), effects=fx)
    assert ability_iids(plain) == [1]  # 无塔：正常枚举
    e = board(p0_active=in_play(1, colorless), stadium=watchtower(), effects=fx)
    assert ability_iids(e) == []  # 【无】被消除
    e1 = board(p0_active=in_play(1, colorless),
               p1_active=in_play(2, colorless),
               stadium=watchtower(), current=1, effects=fx)
    assert ability_iids(e1, 1) == []  # 对手侧同口径
    e2 = board(p0_active=in_play(1, psychic), stadium=watchtower(), effects=fx)
    assert ability_iids(e2) == [1]  # 非【无】不受影响


def test_火箭队的监视塔_离场恢复() -> None:
    """竞技场被顶掉即恢复：stub 引擎层面验证 DSL 声明被守卫读取（求值点实时读）。"""
    colorless = mon_card("特性兽", energy_type="无", has_ability=True)
    fx = {"火箭队的监视塔": WATCHTOWER_DOC, "特性兽": ability_doc("特性兽")}
    e = board(
        p0_active=in_play(1, colorless),
        p0_hand=(inst(60, trainer("普通场", "竞技场")),),
        stadium=watchtower(), effects=fx)
    assert ability_iids(e) == []
    e.apply(0, Action(kind="play_stadium", iid=60))  # 顶掉监视塔
    assert e.state.stadium.card.name == "普通场"
    assert ability_iids(e) == [1]  # 恢复
    assert 399 in [c.iid for c in e.state.players[0].discard]  # 旧场入弃牌区


# ── 玛俐的长毛巨魔ex（庞克泵感 distribute / 暗影子弹备战狙击）─────────────


def grimmsnarl() -> CardDef:
    return mon_card(
        "玛俐的长毛巨魔ex", hp=320, energy_type="恶", stage=2,
        evolves_from="玛俐的捣蛋小妖", owner="玛俐", rule_box="ex",
        attacks=(AttackDef(name="暗影子弹", cost=("恶", "恶"), damage=None),),
    )


def dark_deck(n_dark: int = 5) -> tuple:
    darks = tuple(inst(300 + i, energy("基本恶能量", "恶")) for i in range(n_dark))
    fillers = (inst(400, energy("基本草能量", "草")), inst(401, mon_card("库宝可梦")))
    return darks + fillers


def punk_engine(*, deck=None, p0_bench=None) -> GameEngine:
    """p0 战斗场玛俐的捣蛋小妖（可进化），手牌长毛巨魔（iid 60）。"""
    return board(
        p0_active=in_play(1, mon_card("玛俐的捣蛋小妖", hp=100, stage=1, owner="玛俐")),
        p0_bench=p0_bench if p0_bench is not None else (
            in_play(70, mon_card("玛俐备战", owner="玛俐")),
            in_play(71, mon_card("外人备战")),
        ),
        p0_hand=(inst(60, grimmsnarl()),),
        p0_deck=deck if deck is not None else dark_deck(),
        effects={"玛俐的长毛巨魔ex": GRIMMSNARL_DOC},
    )


def test_玛俐的长毛巨魔ex_庞克泵感_进化触发_集中附着() -> None:
    """从手牌进化触发：选 3 张基本恶能量全给长毛巨魔（集中）；先统一重洗再逐张
    摘下附着，牌库 = 原库 − 3 张。"""
    e = punk_engine()
    e.apply(0, Action(kind="evolve", iid=60, target_iid=1))
    assert e.state.phase == "choice"  # 段1：选能量
    trig = next(ev for ev in e.events if ev.kind == "trigger_on_event")
    assert trig.detail["event"] == "own_evolve_from_hand"
    e.apply(0, Action(kind="choose", choices=(300, 301, 302)))
    for _ in range(3):
        assert e.state.phase == "choice"
        e.apply(0, Action(kind="choose", choices=(60,)))  # 逐张都给长毛巨魔
    assert e.state.phase == "main" and e.state.current_player == 0
    p0 = e.state.players[0]
    assert len(p0.active.attached_energy) == 3
    assert all(c.card.energy_type == "恶" for c in p0.active.attached_energy)
    assert sorted(c.iid for c in p0.deck) == [303, 304, 400, 401]  # 重洗后集合
    result = prim_results(e, "attach_energy")[0]
    assert result["attached"] == 3 and result["shuffled"] is True


def test_玛俐的长毛巨魔ex_庞克泵感_分散附着_仅玛俐可选() -> None:
    """分散多只：2 张分别给玛俐备战与长毛巨魔；非玛俐宝可梦（外人备战）不入目标池。"""
    e = punk_engine()
    e.apply(0, Action(kind="evolve", iid=60, target_iid=1))
    e.apply(0, Action(kind="choose", choices=(300, 301)))
    pc = e.state.pending_choice  # 段2 首轮：目标池仅玛俐的宝可梦
    assert pc is not None and set(pc.pool_iids) == {60, 70}  # 外人备战(71)不入池
    e.apply(0, Action(kind="choose", choices=(70,)))
    e.apply(0, Action(kind="choose", choices=(60,)))
    p0 = e.state.players[0]
    assert len(p0.active.attached_energy) == 1
    assert len(p0.bench[0].attached_energy) == 1
    assert len(p0.bench[1].attached_energy) == 0


def test_玛俐的长毛巨魔ex_庞克泵感_选0仍重洗() -> None:
    """选 0 张 → no-op 仍重洗（D-WP5-1 口径）：不挂段2，牌库集合不变。"""
    e = punk_engine()
    e.apply(0, Action(kind="evolve", iid=60, target_iid=1))
    assert e.state.phase == "choice"
    e.apply(0, Action(kind="choose", choices=()))
    assert e.state.phase == "main" and e.state.current_player == 0
    p0 = e.state.players[0]
    assert len(p0.active.attached_energy) == 0
    assert sorted(c.iid for c in p0.deck) == [300, 301, 302, 303, 304, 400, 401]
    result = prim_results(e, "attach_energy")[0]
    assert result["attached"] == 0 and result["shuffled"] is True


def grimmsnarl_attack_engine(p1_bench: tuple) -> GameEngine:
    return board(
        p0_active=in_play(1, grimmsnarl(), 0).model_copy(update={
            "attached_energy": (inst(9001, energy("基本恶能量", "恶")),
                                inst(9002, energy("基本恶能量", "恶")))}),
        p1_bench=p1_bench,
        effects={"玛俐的长毛巨魔ex": GRIMMSNARL_DOC},
    )


def test_玛俐的长毛巨魔ex_暗影子弹_180加备战30() -> None:
    """主战 180 + 选 1 只备战 30；备战空 → 狙击 no-op、主战照算。"""
    e = grimmsnarl_attack_engine((in_play(80, mon_card("对手备战", hp=500)),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 180
    assert e.state.phase == "choice"
    assert e.state.pending_choice.pool == "opponent_bench"
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 30
    assert e.state.phase == "main" and e.state.current_player == 1
    e2 = grimmsnarl_attack_engine(())
    e2.apply(0, Action(kind="attack", attack_index=0))
    assert e2.state.players[1].active.damage == 180
    assert e2.state.phase == "main" and e2.state.current_player == 1  # 无挂起


# ── 赫普的苍响ex（刹那斩备战狙击 / 英勇之刃 lock_attack 冷却）─────────────


def zacian() -> CardDef:
    return mon_card(
        "赫普的苍响ex", hp=230, energy_type="钢", owner="赫普", rule_box="ex",
        attacks=(
            AttackDef(name="刹那斩", cost=("无",), damage=None),
            AttackDef(name="英勇之刃", cost=("钢", "钢", "钢", "无"), damage=None),
        ),
    )


def zacian_engine(*, p1_bench: tuple = (), energies: tuple) -> GameEngine:
    return board(
        p0_active=in_play(1, zacian(), 0).model_copy(
            update={"attached_energy": energies}),
        p1_bench=p1_bench,
        effects={"赫普的苍响ex": ZACIAN_DOC},
    )


def test_赫普的苍响ex_刹那斩_30加备战30() -> None:
    """主战 30 + 选 1 只备战 30；备战空 → 狙击 no-op、主战照算。"""
    one_energy = (inst(9001, energy()),)
    e = zacian_engine(p1_bench=(in_play(80, mon_card("对手备战", hp=500)),),
                      energies=one_energy)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 30
    assert e.state.phase == "choice"
    assert e.state.pending_choice.pool == "opponent_bench"
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 30
    assert e.state.phase == "main" and e.state.current_player == 1
    e2 = zacian_engine(energies=one_energy)
    e2.apply(0, Action(kind="attack", attack_index=0))
    assert e2.state.players[1].active.damage == 30
    assert e2.state.phase == "main" and e2.state.current_player == 1  # 无挂起


def test_赫普的苍响ex_英勇之刃_240加冷却() -> None:
    """英勇之刃 240 + lock_attack：N 回合使用 → N+1 锁定（刹那斩照常）→ N+2 解禁。"""
    energies = steel_energies(9001, 3) + (inst(9004, energy()),)
    e = zacian_engine(energies=energies)
    assert attack_kinds(e) == [0, 1]
    e.apply(0, Action(kind="attack", attack_index=1))  # 英勇之刃 @turn 2
    assert e.state.players[1].active.damage == 240
    assert e.state.players[0].active.attack_locks == ("英勇之刃",)
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 3
    assert attack_kinds(e) == [0]  # 英勇之刃锁定，刹那斩照常
    e.apply(0, Action(kind="end_turn"))
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 4
    assert attack_kinds(e) == [0, 1]  # 解禁


# ── 阻碍之塔（suppress_tool：道具 modify_hp 失效）─────────────────────────

HP_TOOL_DOC = parse_card_doc("""
card:
  name_group: 护符
effects:
  - trigger: passive_static
    actions:
      - {action: modify_hp, args: {amount: 50}}
""")


def blocker() -> CardInstance:
    return inst(399, trainer("阻碍之塔", "竞技场"))


def charm_holder() -> object:
    return in_play(1, mon_card("持符兽", hp=100)).model_copy(
        update={"attached_tool": inst(90, trainer("护符", "宝可梦道具"))})


def test_阻碍之塔_道具modify_hp失效_有效HP回落() -> None:
    """阻碍之塔在场：道具 HP+50 失效（有效 HP 100+50 → 100）；顶掉即恢复。"""
    fx = {"阻碍之塔": BLOCKER_DOC, "护符": HP_TOOL_DOC}
    plain = board(p0_active=charm_holder(), effects=fx)
    assert plain._effective_hp(plain.state.players[0].active, 0) == 150  # 无塔：加成生效
    e = board(p0_active=charm_holder(), stadium=blocker(), effects=fx)
    assert e._effective_hp(e.state.players[0].active, 0) == 100  # 有效 HP 回落
    e2 = board(
        p0_active=charm_holder(),
        p0_hand=(inst(60, trainer("普通场", "竞技场")),),
        stadium=blocker(), effects=fx)
    assert e2._effective_hp(e2.state.players[0].active, 0) == 100
    e2.apply(0, Action(kind="play_stadium", iid=60))  # 顶掉阻碍之塔
    assert e2._effective_hp(e2.state.players[0].active, 0) == 150  # 恢复


# ── 黑夜魔灵（咒怨炸弹 ko_self + 13 指示物 / 影子束缚 lock_retreat）─────────


def dusknoir() -> CardDef:
    return mon_card(
        "黑夜魔灵", hp=160, energy_type="超", stage=2, evolves_from="彷徨夜灵",
        has_ability=True, retreat=3,
        attacks=(AttackDef(name="影子束缚", cost=("超", "超", "无"), damage=None),),
    )


def test_黑夜魔灵_咒怨炸弹_自爆放13指示物() -> None:
    """备战位发动：整叠进弃牌区、对手立即拿 1 张奖赏（语序保真：先昏厥后放
    指示物）；挂起选对手 1 只放 13 个伤害指示物（130 伤害）。"""
    e = board(p0_bench=(in_play(70, dusknoir()),),
              effects={"黑夜魔灵": DUSKNOIR_DOC})
    abilities = [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    assert [a.iid for a in abilities] == [70]
    e.apply(0, abilities[0])
    assert e.state.phase == "choice"
    assert e.state.players[0].bench == ()  # 已昏厥离场
    assert [c.card.name for c in e.state.players[0].discard] == ["黑夜魔灵"]
    assert len(e.state.players[1].hand) == 1  # 对手已拿 1 张奖赏
    ko = next(ev for ev in e.events if ev.kind == "knockout")
    assert ko.detail["name"] == "黑夜魔灵"
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[1].active.damage == 130  # 13 个指示物
    assert e.state.phase == "main" and e.state.current_player == 0


def test_黑夜魔灵_影子束缚_150加撤退锁() -> None:
    """影子束缚 150 + lock_retreat：目标下个自己回合撤退不枚举；其回合结束解除，
    再下回合解禁。"""
    energies = (inst(9001, energy("基本超能量", "超")),
                inst(9002, energy("基本超能量", "超")),
                inst(9003, energy()))
    e = board(
        p0_active=in_play(1, dusknoir(), 0).model_copy(
            update={"attached_energy": energies}),
        p1_active=in_play(2, mon_card("逃跑兽", hp=500, retreat=1), 1),  # 1 可供撤退
        p1_bench=(in_play(80, mon_card("对手备战")),),
        effects={"黑夜魔灵": DUSKNOIR_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 150
    assert e.state.players[1].active.retreat_lock is True
    assert e.state.phase == "main" and e.state.current_player == 1
    assert not [a for a in e.legal_actions(1) if a.kind == "retreat"]  # 锁定
    e.apply(1, Action(kind="end_turn"))  # p1 回合结束 → 解除
    assert e.state.players[1].active.retreat_lock is False
    e.apply(0, Action(kind="end_turn"))  # → p1 下回合
    assert [a for a in e.legal_actions(1) if a.kind == "retreat"]  # 解禁
