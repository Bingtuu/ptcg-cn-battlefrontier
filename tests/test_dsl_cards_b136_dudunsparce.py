"""单卡 DSL 测试（task 136 扩批第二轮）：土龙节节——从 cards/ 真实文件装载。

土龙节节（CSV7C-162，H 标，1阶）：特性「逃跑抽取」——自己的回合 1 次，
从自己牌库上方抽取 3 张卡牌；然后将这只宝可梦以及放于其身上的所有卡牌
放回牌库并重洗牌库。引擎落点 = 新原语 bounce_to_deck（自身整叠+附着物
回牌库，非昏厥离场；战斗场来源有备战 → 换上后继续主阶段，无备战 → 判负，
同 bounce 附录 A 决议口径）+ shuffle_deck 节点表达重洗。
招式「大地粉碎」90 伤无附加文本（卡面数据承载，无 DSL 效果）。

同文本等价类 = H 标 3 印刷（CSV7C-162 / CSV9.5C-144 / CSVM2cC-009，
db 归一化 text_raw 实测一致）。G 标 2 印刷（CSV3C-099 / CSV3C-138，
异文本「掘遁闪光」）为另一等价类——本批不入档：helpers.py
KNOWN_MULTI_TEXT_GROUPS 白名单主会话集中管，先挂会撞存量按名注入断言；
见 task 136 报告遗留项。
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.state import AttackDef, CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

DOC = load_card_doc(CARDS_DIR / "土龙节节.yml")


def dudu() -> CardDef:
    return CardDef(
        card_id="stub-土龙节节", name="土龙节节", supertype="pokemon",
        hp=140, stage=1, evolves_from="土龙弟弟",
        attacks=(AttackDef(name="大地粉碎", cost=("无", "无", "无"), damage=90),),
        retreat_cost=3,
    )


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def dudu_engine(*, active, bench=(), deck=(), hand=()):
    """main 阶段 p0 局面：战斗场/备战/牌库/手牌按参数装配，注入真实文档。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": active, "bench": bench,
        "deck": deck or state.players[0].deck,
        "hand": hand or state.players[0].hand,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"土龙节节": DOC}
    return e


def use_ability(e, iid):
    return next(a for a in e.legal_actions(0) if a.kind == "use_ability" and a.iid == iid)


# ── 挂载 ──────────────────────────────────────────────────────────────────────


def test_土龙节节_挂载() -> None:
    """主档 = H 标「逃跑抽取」等价类（池内 CSV7C-162 + 同文本 2 印刷）。"""
    assert DOC.card.card_ids == ("CSV7C-162", "CSV9.5C-144", "CSVM2cC-009")


# ── 逃跑抽取（战斗场使用）────────────────────────────────────────────────────


def test_土龙节节_逃跑抽取_抽3并自身整叠回库重洗() -> None:
    """抽 3 → 自身整叠+能量+道具回库（净库张数不变）→ 重洗 → 战斗场空置换。"""
    active = in_play(10, dudu(), energies=1).model_copy(update={
        "attached_tool": inst(88, tool_card("勇气护符")),
    })
    e = dudu_engine(active=active, bench=(in_play(11, basic("占位兽")),))
    p0 = e.state.players[0]
    deck_n, hand_n = len(p0.deck), len(p0.hand)
    e.apply(0, use_ability(e, 10))
    p0 = e.state.players[0]
    assert len(p0.hand) == hand_n + 3
    assert len(p0.deck) == deck_n - 3 + 3  # 抽 3，回库 = 栈 1 + 能量 1 + 道具 1
    names = [c.card.name for c in p0.deck]
    assert names.count("土龙节节") == 1
    assert names.count("基本能量") == 1  # 回库的原附着能量
    assert names.count("勇气护符") == 1
    assert p0.active is None
    assert e.state.phase == "promote"  # 换上流程（附录 A 决议，同 bounce）
    assert any(ev.kind == "use_ability" for ev in e.events)


def test_土龙节节_逃跑抽取_换上后继续主阶段() -> None:
    """战斗场回库后换上：promote 后 resume 回 main（不抽牌不推进回合）。"""
    active = in_play(10, dudu(), energies=1)
    e = dudu_engine(active=active, bench=(in_play(11, basic("占位兽")),))
    turn_before = e.state.turn
    e.apply(0, use_ability(e, 10))
    promote = next(a for a in e.legal_actions(0) if a.kind == "promote")
    e.apply(0, promote)
    assert e.state.players[0].active.current.card.name == "占位兽"
    assert e.state.phase == "main"
    assert e.state.turn == turn_before


def test_土龙节节_逃跑抽取_唯一宝可梦回库判负() -> None:
    """无备战：战斗场来源回库 → 场上无宝可梦判负（reason=no_pokemon）。"""
    e = dudu_engine(active=in_play(10, dudu(), energies=1))
    e.apply(0, use_ability(e, 10))
    assert e.state.phase == "game_over"
    assert e.state.winner == 1
    over = next(ev for ev in e.events if ev.kind == "game_over")
    assert over.detail["reason"] == "no_pokemon"


# ── 逃跑抽取（备战区使用 / 限次 / 边界）───────────────────────────────────────


def test_土龙节节_逃跑抽取_备战使用不触发换上() -> None:
    """备战区来源：整叠回库，战斗场不动，phase 仍 main。"""
    active = in_play(9, basic("占位兽"))
    bench_mon = in_play(10, dudu(), energies=2)
    e = dudu_engine(active=active, bench=(bench_mon,))
    deck_n = len(e.state.players[0].deck)
    e.apply(0, use_ability(e, 10))
    p0 = e.state.players[0]
    assert len(p0.deck) == deck_n - 3 + 3  # 回库 = 栈 1 + 能量 2
    assert p0.bench == ()
    assert p0.active is not None and p0.active.current.iid == 9
    assert e.state.phase == "main"


def test_土龙节节_逃跑抽取_每回合1次() -> None:
    """limit=once_per_turn：发动后本回合不再枚举该特性。"""
    active = in_play(9, basic("占位兽"))
    bench_mon = in_play(10, dudu())
    e = dudu_engine(active=active, bench=(bench_mon,))
    e.apply(0, use_ability(e, 10))
    again = [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    assert again == []


def test_土龙节节_逃跑抽取_牌库不足3张抽尽即止() -> None:
    """牌库 2 张：抽 2（效果抽空不判负），回库重洗照常。"""
    active = in_play(9, basic("占位兽"))
    bench_mon = in_play(10, dudu())
    deck = tuple(inst(100 + i, basic("库顶兽")) for i in range(2))
    e = dudu_engine(active=active, bench=(bench_mon,), deck=deck)
    hand_n = len(e.state.players[0].hand)
    e.apply(0, use_ability(e, 10))
    p0 = e.state.players[0]
    assert len(p0.hand) == hand_n + 2
    assert len(p0.deck) == 2 - 2 + 1  # 抽 2，回库栈 1
    assert e.state.phase == "main"  # 无判负
