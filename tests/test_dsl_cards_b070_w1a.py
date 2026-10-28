"""单卡 DSL 测试（task 070 WP1a 训练家批 A）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批落地 3 张（其余 5 张 blocked：宝可平板/席蓝/太晶珠 缺卡牌维度过滤器，
莉莉艾的决心 缺节点级条件词，玻璃喇叭 缺 attach_energy multi_target×own_bench
组合——详见 task 070 WP1a 报告）：
- 高级球（30th 再录「…后才可以使用这张卡牌」异文本类，I 标 3 印刷）：
  弃 2 手牌成本 → 检索 1 只宝可梦入手 → 重洗（语义同 高级球.yml，文本类严格拆分）。
- 裁判（30thDC 再录「各将手牌全部放回牌库」异文本类，J 标 1 印刷）：
  双方手牌洗回牌库 → 各抽 4（语义同 裁判-4张.yml）。
- 能量回收（「最多2张」文本类，14 印刷）：弃牌区 ≤2 张基本能量入手（up-to + reveal）。
"""

from pathlib import Path

from helpers import basic, energy, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

ULTRA_30TH_DOC = load_card_doc(CARDS_DIR / "高级球-才可以使用.yml")
JUDGE_30TH_DOC = load_card_doc(CARDS_DIR / "裁判-手牌全部.yml")
ENERGY_RECYCLE_DOC = load_card_doc(CARDS_DIR / "能量回收.yml")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def engine_at_seed(state, seed: int = 0) -> GameEngine:
    e = GameEngine(RandomSource(seed))
    e.state = state
    return e


def prim_results(e: GameEngine, action: str) -> list[dict]:
    """该原语的执行结果事件（跳过被节点级 condition 门控的 skipped 标记事件）。"""
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action
            and not ev.detail.get("result", {}).get("skipped")]


# ── 高级球 30th 再录（弃 2 成本 → 检索宝可梦入手 → 重洗）────────────────────


def ultra30_engine(seed: int = 0) -> GameEngine:
    """main 阶段、p0 手牌含 30th 高级球（iid 60）。默认手牌：小火龙(50)+能量(51)+高级球(60)。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("高级球")),))
    e = engine_at_seed(state, seed)
    e.card_effects = {"高级球": ULTRA_30TH_DOC}
    return e


def test_高级球_30th挂载同文本等价类():
    """装载键 = card_id 精确挂载：30th I 类 3 印刷全收；CSV1C-112 异文本类不混入。"""
    ids = ULTRA_30TH_DOC.card.card_ids
    assert "30thC-101" in ids and "30thDC-030" in ids and "CSVH6C-035" in ids
    assert "CSV1C-112" not in ids


def test_高级球_30th再录_全流程():
    """打出 → 挂起选弃 2（成本）→ 挂起检索 1 只宝可梦 → 入手 + 重洗 + 本体进弃牌区。"""
    e = ultra30_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert [a.choices for a in choices] == [(50, 51)]  # 恰好 2 张，唯一组合
    e.apply(0, choices[0])
    p0 = e.state.players[0]
    assert sorted(c.iid for c in p0.discard) == [50, 51]
    # 再挂起：牌库检索 1 只宝可梦（10 妙蛙种子 iid 100~109 + 可以不找）
    assert e.state.phase == "choice"
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert () in [a.choices for a in choices]  # 检索可以不找（up-to 语义）
    deck_before = len(e.state.players[0].deck)
    e.apply(0, next(a for a in choices if a.choices == (100,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert [c.iid for c in p0.hand] == [100]
    assert sorted(c.iid for c in p0.discard) == [50, 51, 60]  # 本体收尾进弃牌区
    assert len(p0.deck) == deck_before - 1  # 取走 1 张且已洗牌
    kinds = [ev.kind for ev in e.events]
    assert kinds.count("effect_start") == 1 and kinds.count("effect_end") == 1
    assert any(ev.kind == "effect_observe" and ev.detail["anchor"] == "key_search"
               for ev in e.events)


def test_高级球_30th再录_不找仍洗牌():
    """检索选择空集（不找）：效果空结算但仍洗牌（检索后必洗）。"""
    e = ultra30_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose"))
    e.apply(0, next(a for a in e.legal_actions(0)
                    if a.kind == "choose" and a.choices == ()))
    p0 = e.state.players[0]
    assert len(p0.hand) == 0 and len(p0.deck) == 10
    assert len(prim_results(e, "shuffle_deck")) == 1


def test_高级球_30th再录_成本不足不可打出():
    """成本可行性门：除本体外手牌不足 2 张 → 不枚举。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": (inst(60, item_card("高级球")), inst(50, basic("小火龙"))),
    })
    e = engine_at_seed(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"高级球": ULTRA_30TH_DOC}
    assert not [a for a in e.legal_actions(0)
                if a.kind == "play_trainer" and a.iid == 60]


# ── 裁判 30thDC 再录（双方手牌洗回牌库 → 各抽 4）─────────────────────────────


def judge30_engine(seed: int = 7) -> GameEngine:
    """main 阶段、p0 手牌含 30thDC 裁判（iid 60）；对手手牌 2 张 + 牌库 10 张。"""
    state = main_state(p0_extra_hand=(inst(60, supporter_card("裁判")),))
    p1 = state.players[1].model_copy(update={
        "hand": (inst(70, basic("对手手甲")), inst(71, basic("对手手乙"))),
        "deck": tuple(inst(300 + i, basic(f"对手库{i}")) for i in range(10)),
    })
    e = engine_at_seed(state.model_copy(update={"players": (state.players[0], p1)}), seed)
    e.card_effects = {"裁判": JUDGE_30TH_DOC}
    return e


def test_裁判_30thDC挂载同文本等价类():
    """30thDC-037 为「各将手牌全部放回牌库」类唯一 J 标印刷；「各将所有手牌」类不混入。"""
    ids = JUDGE_30TH_DOC.card.card_ids
    assert ids == ("30thDC-037",)
    assert "CSVH1C-051" not in ids


def test_裁判_30thDC再录_双方洗回各抽4():
    """双方手牌各回库重洗 → 各抽 4；打出时裁判已离手（洗回 2 张）；卡片全集守恒。"""
    e = judge30_engine()
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


def test_裁判_30thDC再录_种子确定性():
    """同种子两次运行：双方牌库序逐局一致（重洗走单一随机源）。"""
    orders = []
    for _ in range(2):
        e = judge30_engine()
        e.apply(0, Action(kind="play_trainer", iid=60))
        orders.append((tuple(c.iid for c in e.state.players[0].deck),
                       tuple(c.iid for c in e.state.players[1].deck)))
    assert orders[0] == orders[1]


# ── 能量回收（弃牌区 ≤2 张基本能量入手，up-to + reveal）───────────────────────


def recycle_engine(discard: tuple, seed: int = 0) -> GameEngine:
    """main 阶段、p0 手牌含能量回收（iid 60），弃牌区由参数给定。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("能量回收")),))
    p0 = state.players[0].model_copy(update={"discard": discard})
    e = engine_at_seed(state.model_copy(update={"players": (p0, state.players[1])}), seed)
    e.card_effects = {"能量回收": ENERGY_RECYCLE_DOC}
    return e


def recycle_discard() -> tuple:
    """3 张基本能量（属性各异）+ 1 只宝可梦（应被 basic_energy 过滤）。"""
    return (
        inst(400, energy("基本【火】能量", "火")),
        inst(401, energy("基本【草】能量", "草")),
        inst(402, basic("拉鲁拉丝")),
        inst(403, energy("基本【水】能量", "水")),
    )


def test_能量回收_挂载同文本等价类():
    """「最多2张」类 14 印刷全收（含池内 CSVH1C-034）；「2张」异文本类不混入。"""
    ids = ENERGY_RECYCLE_DOC.card.card_ids
    assert len(ids) == 14 and "CSVH1C-034" in ids
    assert "CSM1DC-230" not in ids  # 「将自己弃牌区中的2张…」类


def test_能量回收_最多2张基本能量入手():
    """选 2 张基本能量入手；宝可梦不进选择池；reveal 落「给对手看过」事件。"""
    e = recycle_engine(recycle_discard())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    choices = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert (400, 401) in choices and (403,) in choices and () in choices  # up-to 0~2
    assert not any(402 in c for c in choices)  # 宝可梦被 basic_energy 过滤
    e.apply(0, next(a for a in e.legal_actions(0)
                    if a.kind == "choose" and a.choices == (400, 401)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert [c.iid for c in p0.hand] == [50, 51, 400, 401]
    assert sorted(c.iid for c in p0.discard) == [60, 402, 403]  # 本体收尾进弃牌区
    res = prim_results(e, "recover_from_discard")
    assert res[0]["found"] == 2 and res[0]["destination"] == "hand"
    assert any(ev.kind == "reveal" for ev in e.events)  # 「给对手看过之后」
    assert any(ev.kind == "effect_observe" and ev.detail["anchor"] == "key_search"
               for ev in e.events)


def test_能量回收_up_to可只拿1张或不拿():
    """「最多2张」= up-to（min_choose=0）：选 1 张 / 空选均合法。"""
    e = recycle_engine(recycle_discard())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0)
                    if a.kind == "choose" and a.choices == (403,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51, 403]
    e2 = recycle_engine(recycle_discard())
    e2.apply(0, Action(kind="play_trainer", iid=60))
    e2.apply(0, next(a for a in e2.legal_actions(0)
                     if a.kind == "choose" and a.choices == ()))
    p0b = e2.state.players[0]
    assert [c.iid for c in p0b.hand] == [50, 51]
    assert prim_results(e2, "recover_from_discard")[0]["found"] == 0


def test_能量回收_弃牌区无基本能量不可打出():
    """可行性门（hand up-to 形式）：弃牌区无匹配基本能量 → 不枚举（无效果不可使用）。"""
    e = recycle_engine((inst(402, basic("拉鲁拉丝")),))
    assert not [a for a in e.legal_actions(0)
                if a.kind == "play_trainer" and a.iid == 60]
