"""测试共用 fixture 助手：stub 卡定义与引擎驱动。"""

import json
from pathlib import Path

from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    GameState,
    InPlayPokemon,
    PlayerState,
)

# ── task 158：jsonl dist 最小 fixture（E2E 后端，spike 实证字段全集）────

def _jsonl_card(card_id: str, name: str, energy_type: str, damage: int) -> dict:
    """最小合法 CardSchema 行（ptcgdb CardSchema 必填域全集，spike 逐字段钉过）。"""
    return {
        "card_id": card_id, "set_id": "TST", "number": card_id[-3:],
        "number_display": card_id[-3:], "name_full": name, "species": name,
        "owner": "", "card_type": "pokemon", "regulation_mark": "A",
        "rarity": "", "stage": "基础", "hp": 70, "types": [energy_type],
        "evolves_from_text": None, "evolves_from_id": None,
        "evolution_chain_id": None, "rule_box_type": None, "has_rule_box": False,
        "is_tera": False, "union_position": None, "deck_limit": 4,
        "prize_cards": 1, "is_ace_spec": False,
        "abilities": [], "is_basic_energy": False,
        "attacks": [{"name": "打击", "cost": [{"type": energy_type, "count": 1}],
                     "damage_base": damage, "damage_modifier": None,
                     "effect_text": ""}],
        "weakness": None, "resistance": None, "retreat_cost": 1,
        "trainer_subtype": None, "provides": None, "effect_tags": [],
        "name_en": "", "name_ja": "", "name_zh_tw": "",
        "source": "test", "fetched_at": "2026-01-01", "status": "active",
        "text_raw": "",
    }


def _jsonl_energy(card_id: str, name: str, energy_type: str) -> dict:
    card = _jsonl_card(card_id, name, energy_type, 0)
    card.update(card_type="energy", stage=None, hp=None, types=[],
                retreat_cost=None, prize_cards=0, attacks=[],
                provides=[energy_type], is_basic_energy=True)
    return card


def write_jsonl_dist(dist: Path, cards: list[dict]) -> Path:
    """写最小 jsonl dist 导出目录（manifest/cards/sets/relations/legality）。"""
    dist = Path(dist)
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "manifest.json").write_text(json.dumps({"schema_version": 99}),
                                        encoding="utf-8")
    (dist / "cards.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in cards),
        encoding="utf-8")
    (dist / "sets.jsonl").write_text(json.dumps({
        "set_id": "TST", "name_zh": "测试扩展", "era": "test",
        "release_date": "2020-01-01", "regulation_mark": "A",
        "expected_count": len(cards), "expected_secret_count": 0,
        "card_face_total": len(cards), "source": "test",
        "fetched_at": "2026-01-01"}, ensure_ascii=False), encoding="utf-8")
    (dist / "relations.jsonl").write_text("", encoding="utf-8")
    energy_types = sorted({c["types"][0] for c in cards if c["card_type"] == "pokemon"}
                          | {p for c in cards for p in (c["provides"] or [])})
    (dist / "legality.json").write_text(json.dumps({"data": {
        "snapshots": [{
            "snapshot_id": "std-test", "format": "standard",
            "effective_from": "2020-01-01", "effective_to": None,
            "allowed_marks": ["A"],
            "allowed_basic_energy_types": energy_types,
            "whitelist_cards": [], "banned_cards": [], "mark_overrides": [],
            "latest_text_overrides": {}, "source_url": "",
            "created_at": "2026-01-01"}],
        "errata": []}}, ensure_ascii=False), encoding="utf-8")
    return dist


def make_e2e_dist(tmp_path) -> Path:
    """E2E 用 4 宝可梦 + 1 基本能量最小库（每种 ≤4 上限内可组 60 张）。"""
    return write_jsonl_dist(Path(tmp_path) / "dist", [
        _jsonl_card("TST-001", "测试苗蛙", "草", 20),
        _jsonl_card("TST-002", "测试火蜥", "火", 30),
        _jsonl_card("TST-003", "测试水鱼", "水", 20),
        _jsonl_card("TST-004", "测试雷鼠", "雷", 30),
        _jsonl_energy("TST-101", "基本草能量", "草"),
    ])


def e2e_decklist() -> str:
    """60 张合法 decklist（4 同名上限内；印刷级行）。"""
    return ("4 测试苗蛙 [TST-001]\n4 测试火蜥 [TST-002]\n"
            "4 测试水鱼 [TST-003]\n4 测试雷鼠 [TST-004]\n44 基本草能量 [TST-101]\n")


def _attacks(damage: int | None, cost: int) -> tuple[AttackDef, ...]:
    """白板 stub：单个固定伤害招式，成本为 cost 个无色能量。"""
    if damage is None:
        return ()
    return (AttackDef(name="打击", cost=("无",) * cost, damage=damage),)


def basic(name: str, hp: int = 70, damage: int = 20, cost: int = 1, retreat: int = 1) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, attacks=_attacks(damage, cost), retreat_cost=retreat,
    )


def stage1(name: str, evolves_from: str, hp: int = 90, damage: int = 40, cost: int = 2) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=1, evolves_from=evolves_from, attacks=_attacks(damage, cost),
    )


def energy(name: str = "基本能量", energy_type: str | None = None) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="energy",
        energy_type=energy_type, is_basic_energy=True,
    )


def deck60() -> list[CardDef]:
    return (
        [basic("妙蛙种子")] * 20
        + [stage1("妙蛙草", "妙蛙种子")] * 4
        + [basic("小火龙")] * 20
        + [energy()] * 16
    )


def new_game(seed: int = 42, deck: list[CardDef] | None = None) -> GameEngine:
    d = deck if deck is not None else deck60()
    engine = GameEngine(RandomSource(seed))
    engine.new_game(d, d)
    return engine


def finish_setup(engine: GameEngine) -> None:
    """双方各放 1 战斗场 + 确认（跳过备战区选择）。"""
    for player in (0, 1):
        act = next(a for a in engine.legal_actions(player) if a.kind == "place_active")
        engine.apply(player, act)
        confirm = next(a for a in engine.legal_actions(player) if a.kind == "confirm_setup")
        engine.apply(player, confirm)


def inst(iid: int, card: CardDef) -> CardInstance:
    return CardInstance(iid=iid, card=card)


def effects_by_name(library) -> dict:
    """CardLibrary → 卡名键朴素 dict：stub 卡（card_id=stub-*）注入的兼容路径。

    引擎对朴素 dict 按卡名解析（task 026 WP0）；同名多文档时按名注入有歧义，直接报错。
    例外（task 026 WP6）：「火恐龙」同文本等价类拆分文件（大字爆炎/闪焰之幕，
    与索财灵/百变怪拆分同例）保留 name_group=火恐龙——stub 对局用不到该名，
    真实卡组走 card_id 挂载；已知白名单内的重复组跳过按名注入，其余重复仍报错
    （防错挂守卫不放宽）。task 070 WP1a 追加：高级球/裁判（30th 同效果异文本
    再录拆分，D-070-3 预期同组多文档）。task 071：咕咕（三刺击 / 寂静之翼）同名异文本。
    task 134：能量转移（主类 / H6 异文本类）。
    task 139：索财灵（连掷硬币 / 小使者）/ 雪童子（惊吓 / 冰砾）。
    """
    KNOWN_MULTI_TEXT_GROUPS = {"火恐龙", "高级球", "裁判", "咕咕", "能量转移", "能量回收", "气球", "索财灵", "雪童子", "反击捕捉器"}
    docs = list({id(d): d for d in library.values()}.values())
    names = [d.card.name_group for d in docs]
    dupes = {n for n in names if names.count(n) > 1}
    assert dupes <= KNOWN_MULTI_TEXT_GROUPS, (
        f"同名多文档无法按名注入（应改用 card_id 挂载）: {sorted(dupes)}"
    )
    return {d.card.name_group: d for d in docs if d.card.name_group not in dupes}


def doc_of(library, name: str):
    """CardLibrary 中该卡名的唯一文档（0 或 >1 均为装配口径事故，直接报错）。"""
    docs = library.by_name(name)
    assert len(docs) == 1, f"{name} 文档数 {len(docs)}（应为 1）"
    return docs[0]


def in_play(iid: int, card: CardDef, energies: int = 0) -> InPlayPokemon:
    return InPlayPokemon(
        stack=(inst(iid, card),),
        attached_energy=tuple(inst(9000 + iid * 10 + j, energy()) for j in range(energies)),
    )


def main_state(
    p0_active_energies: int = 1,
    p1_active_energies: int = 1,
    p0_extra_hand: tuple[CardInstance, ...] = (),
    p1_bench: tuple[InPlayPokemon, ...] = (),
) -> GameState:
    """直接构造 main 阶段局面（绕过开局，战斗/主阶段规则测试用）。"""
    a0 = in_play(1, basic("妙蛙种子"), p0_active_energies)
    a1 = in_play(2, basic("小火龙"), p1_active_energies)
    p0 = PlayerState(
        deck=tuple(inst(100 + i, basic("妙蛙种子")) for i in range(10)),
        hand=(inst(50, basic("小火龙")), inst(51, energy())) + p0_extra_hand,
        prizes=tuple(inst(200 + i, basic("妙蛙种子")) for i in range(6)),
        active=a0,
    )
    p1 = PlayerState(
        deck=tuple(inst(300 + i, basic("小火龙")) for i in range(10)),
        prizes=tuple(inst(400 + i, basic("小火龙")) for i in range(6)),
        active=a1,
        bench=p1_bench,
    )
    return GameState(
        players=(p0, p1), turn=2, current_player=0, phase="main", first_player=0,
    )


def engine_at(state: GameState) -> GameEngine:
    e = GameEngine(RandomSource(0))
    e.state = state
    return e
