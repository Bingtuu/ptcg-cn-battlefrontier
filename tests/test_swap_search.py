"""换卡搜索器测试（task 130，设计文档 docs/digs/2026-11-14-deck-swap-search-design.md）。

覆盖（loop 测试方案 §1.130）：槽位分类 / 过滤链（DSL→赛制→60 张结构合法 +
同名多印刷拒绝）/ 两阶段预算分配 / 排序输出 / 多重比较校正 / 限定语头注。
调度与排序用 monkeypatch 假 run_group 喂合成结果库（不跑真实对局）；
候选生成与过滤链对真实 db + 真实 DSL 库做集成断言（tests 惯例，同 test_deckload）。
"""

from __future__ import annotations

import pytest

from battlefrontier.engine.state import Supertype
from battlefrontier.report import SIM_INTERPRETATION_NOTE
from battlefrontier.report.swap_search import (
    PRACTICAL_MIN_DELTA,
    SCREEN_FRAC,
    SEARCH_DISCLAIMER,
    benjamini_hochberg,
    bonferroni,
    build_candidates,
    candidate_in_cards,
    confirm_rows,
    dsl_reject_reason,
    format_swap_search,
    plan_phases,
    run_swap_search,
    slot_of,
    swap_warnings,
)
from battlefrontier.runner.play import GameResult
from battlefrontier.runner.results_db import ResultsDB
from tests.helpers import basic, energy, stage1

DB_PATH = r"C:/Vibe Project/Pokearena/data/ptcg-cn.db"
TERA_EEVEE = "mik_moe:711874"
VS_DRAGAPULT = "mik_moe:711851"

# ── 槽位分类（设计文档 §1.1）──────────────────────────────

def test_slot_classification():
    assert slot_of(energy()) == "基本能量"
    special = energy("喷射能量", "火").model_copy(update={"is_basic_energy": False})
    assert slot_of(special) == "特殊能量"
    assert slot_of(basic("火伊布ex")) == "打手单卡位"
    assert slot_of(stage1("猫头夜鹰", "咕咕")) == "进化线位"
    trainer = basic("宝可平板").model_copy(update={"supertype": Supertype.TRAINER})
    assert slot_of(trainer) == "训练家位"


# ── 过滤链：DSL 关（task 115 纪律，stub 库纯函数）──────────

class _StubLibrary:
    """classify_dsl 只看 __contains__（card_id 挂载）与 by_name（同名文档）。"""

    def __init__(self, covered_ids=(), names=()):
        self._covered = set(covered_ids)
        self._names = set(names)

    def __contains__(self, card_id):
        return card_id in self._covered

    def by_name(self, name):
        return [object()] if name in self._names else []


def test_dsl_reject_covered_passes():
    lib = _StubLibrary(covered_ids={"stub-x"})
    assert dsl_reject_reason(basic("x").model_copy(update={"card_id": "stub-x"}),
                             lib) is None


def test_dsl_reject_vanilla_print_rejected():
    """未覆盖但同名有文档 → 拒绝（vanilla 静默退化风险）。"""
    lib = _StubLibrary(names=["火恐龙"])
    card = basic("火恐龙").model_copy(update={"card_id": "stub-异文本"})
    assert dsl_reject_reason(card, lib) is not None


def test_dsl_reject_basic_energy_exempt():
    lib = _StubLibrary()
    assert dsl_reject_reason(energy(), lib) is None


def test_dsl_reject_pure_vanilla_pokemon_exempt():
    """无特性、全固定伤害的白板宝可梦豁免（task 131 同源口径）。"""
    lib = _StubLibrary()
    assert dsl_reject_reason(basic("波波"), lib) is None


def test_dsl_reject_no_doc_pokemon_rejected():
    lib = _StubLibrary()
    # 有伤害修饰（非纯白板）且无文档 → 拒绝
    from battlefrontier.engine.state import AttackDef

    card = basic("虚构 ex").model_copy(update={
        "attacks": (AttackDef(name="大招", cost=("无",), damage=100,
                              damage_modifier="dx"),)})
    assert dsl_reject_reason(card, lib) is not None


# ── 候选生成 + 过滤链（真实 db + 真实 DSL 库，集成）────────

@pytest.fixture(scope="module")
def tera_eevee_deck():
    from battlefrontier.data.deck import load_deck

    return load_deck(DB_PATH, TERA_EEVEE).cards


def test_candidate_in_cards_top_n_and_include(tera_eevee_deck):
    cards, _warns = candidate_in_cards(DB_PATH, TERA_EEVEE, top_n=8)
    assert 0 < len(cards) <= 8 + 0
    assert len({c.card_id for c in cards}) == len(cards)  # 印刷级去重
    assert all(c.card_id for c in cards)
    # --include 手填（in_id 纪律：印刷 + 卡名一致）
    cards2, _ = candidate_in_cards(
        DB_PATH, TERA_EEVEE, top_n=0, include=("友好宝芬 [CSV7C-177]",))
    assert any(c.name == "友好宝芬" for c in cards2)
    with pytest.raises(ValueError, match="不一致"):
        candidate_in_cards(DB_PATH, TERA_EEVEE, top_n=0,
                           include=("友好宝芬 [CSV7C-178]",))


def test_build_candidates_real_deck(tera_eevee_deck):
    from battlefrontier.dsl.loader import load_card_dir

    lib = load_card_dir("cards")
    in_cards, _ = candidate_in_cards(DB_PATH, TERA_EEVEE, top_n=6)
    cands, drop = build_candidates(tera_eevee_deck, in_cards, DB_PATH, lib)
    assert cands, "真实卡组应有过滤链幸存候选"
    # 每候选都过 validate_deck（60 张/同名≤4/ACE SPEC≤1）——独立复核（移除一张口径）
    from ptcgdb.sdk import open_db

    from battlefrontier.report.swap_search import list_deck_ids_minus_one

    db = open_db(DB_PATH)
    try:
        date = db.snapshots("standard")[-1].effective_from
        for c in cands:
            ids = list_deck_ids_minus_one(tera_eevee_deck, c.out_card.card_id)
            ids.append(c.in_card.card_id)
            assert db.validate_deck(ids, date, "standard").ok
    finally:
        db.close()
    # 拒绝 reason 逐类非空（不猜纪律）
    assert all(reason and n > 0 for reason, n in drop.items())
    # 同名多印刷槽拒绝：711874 咕咕双印刷（CSV9.5C-141 + CSV9C-154）
    assert not any(c.out_card.name == "咕咕" for c in cands)
    assert any("同名多印刷" in r for r in drop)


def test_swap_warnings_soft_not_rejecting(tera_eevee_deck):
    from battlefrontier.dsl.loader import load_card_dir

    lib = load_card_dir("cards")
    in_cards, _ = candidate_in_cards(DB_PATH, TERA_EEVEE, top_n=6)
    cands, _ = build_candidates(tera_eevee_deck, in_cards, DB_PATH, lib)
    cand = cands[0]
    warns = swap_warnings(tera_eevee_deck, cand)
    assert isinstance(warns, list)
    # 换出基本能量 → 能量基底告警可触发（若换出的是能量位）
    energy_cand = next(
        (c for c in cands
         if c.out_card.supertype == Supertype.ENERGY
         and c.out_card.is_basic_energy), None)
    if energy_cand is not None:
        assert any("基本能量" in w for w in
                   swap_warnings(tera_eevee_deck, energy_cand))
    assert all(c.swap.in_id == c.in_card.card_id for c in cands)  # in_id 纪律


# ── 两阶段预算分配（设计文档 §3.1）────────────────────────

def test_plan_phases_default_split():
    plan = plan_phases(120000, n_candidates=99, confirm_top=3)
    assert plan.screen_games == int(120000 * SCREEN_FRAC) // 100 == 720
    assert plan.confirm_games == (120000 - 100 * 720) // 4 == 12000
    assert plan.confirm_top == 3


def test_plan_phases_explicit_override_and_total_check():
    plan = plan_phases(100000, n_candidates=10, confirm_top=2,
                       screen_games=200, confirm_games=500)
    assert plan.screen_games == 200 and plan.confirm_games == 500
    # 超预算拒绝（不静默截断）
    with pytest.raises(ValueError, match="超预算"):
        plan_phases(1000, n_candidates=10, confirm_top=2,
                    screen_games=200, confirm_games=500)
    # 低于下限拒绝
    with pytest.raises(ValueError, match="下限"):
        plan_phases(100000, n_candidates=1000, confirm_top=3)
    with pytest.raises(ValueError, match="下限"):
        plan_phases(3000, n_candidates=1, confirm_top=3,
                    screen_games=60, confirm_games=10)
    with pytest.raises(ValueError, match="不猜"):
        plan_phases(0, n_candidates=1)


# ── 多重比较校正（设计文档 §2.4 参考值对拍）───────────────

def test_bonferroni_caps_at_one():
    assert bonferroni(0.01, 3) == pytest.approx(0.03)
    assert bonferroni(0.4, 5) == 1.0
    assert bonferroni(None, 5) is None


def test_benjamini_hochberg_reference():
    """BH 参考值：p=[0.01,0.04,0.04,0.04] → 全 0.04（m/j 从右累积最小）。"""
    adj = benjamini_hochberg([0.01, 0.04, 0.04, 0.04])
    assert adj == pytest.approx([0.04, 0.04, 0.04, 0.04])
    # None 保留；顺序保持；m = 含 None 的总数
    adj2 = benjamini_hochberg([0.04, None, 0.01])
    assert adj2[1] is None
    # BH 定义 padj_(i) = min_{j≥i} p_(j)·m/j（m=3）：
    # rank1: 0.01×3=0.03；rank2: 0.04×3/2=0.06——min 只从右往左传，
    # rank2 是最大 p，无 j>2 可取 → 保持 0.06（右累积不回流）
    assert adj2[0] == pytest.approx(0.06)
    assert adj2[2] == pytest.approx(0.03)


# ── 排序 + 确认档判定（合成结果库，假 run_group）──────────

def _fake_run_group_factory(tmp_path, effects: dict[str, float]):
    """假 run_group：不落真实对局，按 variant 名映射预设 A 胜率写合成局。

    effects：variant 名 → A 胜率（baseline 名 "" 用 effects["__base__"]）。
    """

    def _fake(defn, db_path, results_path, *, workers=1, cards_dir="cards",
              definition_yaml=""):
        db = ResultsDB(results_path)
        ids = []
        try:
            for variant in [""] + [v.name for v in defn.variants]:
                exp_id = db.start_experiment(
                    name=defn.name, definition_yaml=definition_yaml,
                    code_version="c", data_version="d",
                    group_name=defn.name, variant=variant)
                wr = effects["__base__"] if variant == "" else effects[variant]
                for seed in range(defn.seed_start, defn.seed_start + defn.games):
                    won = (hash((variant, seed)) % 1000) / 1000 < wr
                    res = GameResult(winner=0 if won else 1, is_draw=False,
                                     turns=8, phase="main", first_player=seed % 2)
                    db.record_game(exp_id, seed=seed,
                                   first_player=res.first_player, result=res,
                                   deck_a_id="a", deck_b_id="b")
                db.finish_experiment(exp_id)
                ids.append(exp_id)
        finally:
            db.close()
        return ids, []

    return _fake


def _real_candidates(tmp_path, monkeypatch, top_n=6):
    """真实过滤链候选 + 假执行的搜索（screen/confirm 各 100 局，快速）。

    top_n 取 6：真实 db 下 top-2 高频件（猫头夜鹰/巢穴球）在阵均已 4 张，
    加第 5 张过 4-of 关必拒，top_n=2 会合法地过滤链全灭。
    """
    from battlefrontier.data.deck import load_deck
    from battlefrontier.dsl.loader import load_card_dir

    deck = load_deck(DB_PATH, TERA_EEVEE).cards
    lib = load_card_dir("cards")
    in_cards, _ = candidate_in_cards(DB_PATH, TERA_EEVEE, top_n=top_n)
    cands, drop = build_candidates(deck, in_cards, DB_PATH, lib)
    effects = {"__base__": 0.30}
    for i in range(len(cands)):
        # 预设效应：c000 大正效应，c001 微负，其余零效应
        effects[f"c{i:03d}"] = 0.50 if i == 0 else (0.25 if i == 1 else 0.30)
    monkeypatch.setattr(
        "battlefrontier.report.swap_search.run_group",
        _fake_run_group_factory(tmp_path, effects))
    rep = run_swap_search(
        deck_id=TERA_EEVEE, vs_id=VS_DRAGAPULT, budget=100000,
        db_path=DB_PATH, results_path=tmp_path / "ss.db",
        seed_start=470000, confirm_top=2,
        screen_games=100, confirm_games=100, top_n=top_n)
    return rep, cands, drop


def test_search_two_phase_schedule_and_ranking(tmp_path, monkeypatch):
    rep, cands, _ = _real_candidates(tmp_path, monkeypatch)
    # 两阶段各跑 baseline + variants，id 递增且分组名带 -s1/-s2
    assert len(rep.screen_ids) == 1 + len(rep.candidates)
    assert len(rep.confirm_ids) == 1 + rep.plan.confirm_top
    db = ResultsDB(rep.results_path)
    try:
        s1 = db.experiment(rep.screen_ids[0])
        s2 = db.experiment(rep.confirm_ids[0])
        assert s1["group_name"].endswith("-s1") and s2["group_name"].endswith("-s2")
        # 确认档种子区间与筛选档零重叠（防循环论证）
        g1 = db.games(rep.screen_ids[0])
        g2 = db.games(rep.confirm_ids[0])
        assert max(x["seed"] for x in g1) < min(x["seed"] for x in g2)
    finally:
        db.close()
    # 排序：c000（预设 +20pp 效应）应在筛选档首位、确认档首位
    assert rep.screen_rows[0].candidate.swap.in_id == cands[0].swap.in_id
    assert rep.confirm[0].candidate.swap.in_id == cands[0].swap.in_id
    assert rep.confirm[0].d_wr > 0


def test_confirm_row_knife_gate():
    """候选刀位判定门：CI 不过 0 且 |ΔWR|≥3pp 且 p_bonf<0.05。"""
    from battlefrontier.report.swap_search import SwapCandidate
    from battlefrontier.runner.experiment import SwapCfg

    cand = SwapCandidate(
        out_card=basic("A"), in_card=basic("B"),
        swap=SwapCfg(side="a", out="A", out_count=1, **{"in": "B"},
                     in_count=1, in_id="stub-B"))

    class _Rep:
        def __init__(self, wr, wins, decided):
            self.wr_a = wr
            self.wins_a = wins
            self.decided = decided

    base = _Rep(0.30, 300, 1000)
    big = _Rep(0.30 + PRACTICAL_MIN_DELTA + 0.05, 380, 1000)   # +8pp，CI 应不过 0
    small = _Rep(0.30 + 0.01, 310, 1000)                        # +1pp，低于实际显著性
    rows = confirm_rows(base, [(cand, 1, big), (cand, 2, small)])
    assert rows[0].is_knife is True
    assert rows[1].is_knife is False
    assert rows[0].p_bonf == pytest.approx(min(1.0, rows[0].p * 2))


def test_format_swap_search_qualifier_header(tmp_path, monkeypatch):
    rep, _, drop = _real_candidates(tmp_path, monkeypatch)
    text = format_swap_search(rep)
    # 限定语头注（自对局先验）+ 筛选档不宣称显著禁令
    assert SIM_INTERPRETATION_NOTE in text.splitlines()[1]
    assert SEARCH_DISCLAIMER in text
    # 过滤链拒绝 reason 计数落输出
    for reason, n in drop.items():
        assert f"{reason}：{n}" in text
    # 筛选档排序表与确认档判定表齐
    assert "筛选档排序" in text and "确认档判定" in text
    assert "→" in text  # 刀位方向可读
    # meta 回显（可复算纪律）
    assert TERA_EEVEE in text and VS_DRAGAPULT in text and "种子" in text
    assert text.rstrip().endswith(SIM_INTERPRETATION_NOTE)
