"""task 123：field_pick 选卡器测试（四期 PRD M14）。

实现先于测试落盘（主会话直写，TDD 顺序偏差如实披露于 task 文档）；
测试按预注册判据逐项对拍：期望胜率手算复现 / 蒙特卡洛钉种子复现 /
缺格与双源优先级 / 限定语头注。
"""

from __future__ import annotations

import json

import pytest

from battlefrontier.report.field_pick import (
    QUALIFIER_HEADER,
    MatchupCell,
    assemble_matrix,
    expected_winrate,
    field_pick,
    format_field_pick,
    load_field_distribution,
)

POOL = ["A", "B", "C"]


def _sim_cells():
    return [
        MatchupCell("A", "B", 0.6, n=500, source="sim"),
        MatchupCell("B", "A", 0.4, n=500, source="sim"),
        MatchupCell("A", "C", 0.7, n=500, source="sim"),
        MatchupCell("C", "A", 0.3, n=500, source="sim"),
        MatchupCell("B", "C", 0.5, n=500, source="sim"),
        MatchupCell("C", "B", 0.5, n=500, source="sim"),
    ]


def test_expected_winrate_手算复现():
    matrix = assemble_matrix([], _sim_cells(), POOL)
    field = {"A": 0.5, "B": 0.3, "C": 0.2}
    # v0.3 口径：源缺镜像按 50% 默认计入
    # A: .5*.5(镜像默认) + .3*.6 + .2*.7 = .57
    assert expected_winrate("A", field, matrix) == pytest.approx(0.57)
    # B: .3*.5(镜像默认) + .5*.4 + .2*.5 = .45
    assert expected_winrate("B", field, matrix) == pytest.approx(0.45)


def test_field_distribution_归一化(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"decks": [
        {"display_name": "A", "value": 2.0}, {"display_name": "B", "value": 1.0},
    ]}), encoding="utf-8")
    share = load_field_distribution(p)
    assert share == {"A": pytest.approx(2 / 3), "B": pytest.approx(1 / 3)}


def test_缺格占位_low_confidence():
    matrix = assemble_matrix([], _sim_cells(), POOL + ["D"])
    assert matrix[("D", "A")].source == "missing"
    assert matrix[("D", "A")].wr_a == 0.5


def test_intl_优先于_sim():
    sim = [MatchupCell("A", "B", 0.6, n=500, source="sim")]
    intl = [MatchupCell("A", "B", 0.55, n=40, source="intl")]
    matrix = assemble_matrix(intl, sim, ["A", "B"])
    assert matrix[("A", "B")].source == "intl"
    assert matrix[("A", "B")].wr_a == 0.55
    assert matrix[("B", "A")].wr_a == pytest.approx(0.45)


def test_蒙特卡洛_钉种子可复现():
    matrix = assemble_matrix([], _sim_cells(), POOL)
    field = {"A": 0.5, "B": 0.3, "C": 0.2}
    r1 = field_pick(field, matrix, POOL, n_sim=200, seed=7)
    r2 = field_pick(field, matrix, POOL, n_sim=200, seed=7)
    r3 = field_pick(field, matrix, POOL, n_sim=200, seed=8)
    assert r1.rows == r2.rows  # 同种子同输出
    assert r1.rows != r3.rows  # 不同种子不同抽样
    assert abs(sum(r["top1_rate"] for r in r1.rows) - 1.0) < 1e-9
    # A 期望最高（.32 > B .30），登顶率应最高
    top = max(r1.rows, key=lambda r: r["exp_wr"])
    assert top["deck"] == "A" and top["top1_rate"] > 0.5


def test_format_含限定语与排序():
    matrix = assemble_matrix([], _sim_cells(), POOL)
    rep = field_pick({"A": 0.5, "B": 0.3, "C": 0.2}, matrix, POOL, n_sim=50)
    text = format_field_pick(rep)
    assert text.startswith(QUALIFIER_HEADER[:20])
    assert "同模拟器内" in text and "弱参照" in text
    data_rows = [l for l in text.splitlines() if " | " in l and "卡组" not in l]
    assert data_rows[0].startswith("A |")  # 排序第一
    assert "真实格贡献" in text


# ── task 123 修订测试（M14 review A1/A2/C2）────────────────

def test_小样本真实格收缩():
    """n<20 的 intl 格向 50% 收缩（(n·wr+K·0.5)/(n+K)），n≥20 原样。"""
    from battlefrontier.report.field_pick import shrink_intl_cell

    small = shrink_intl_cell(MatchupCell("A", "B", 0.9, n=10, source="intl"))
    assert small.shrunk and small.wr_a == pytest.approx((10 * 0.9 + 10) / 30)
    big = shrink_intl_cell(MatchupCell("A", "B", 0.9, n=20, source="intl"))
    assert not big.shrunk and big.wr_a == 0.9
    sim = shrink_intl_cell(MatchupCell("A", "B", 0.9, n=5, source="sim"))
    assert not sim.shrunk  # 只收缩真实格


def test_intl_成对一致_覆盖_sim_反向():
    sim = [MatchupCell("A", "B", 0.6, n=500, source="sim"),
           MatchupCell("B", "A", 0.41, n=500, source="sim")]
    intl = [MatchupCell("A", "B", 0.55, n=40, source="intl")]
    matrix = assemble_matrix(intl, sim, ["A", "B"])
    assert matrix[("B", "A")].source == "intl"  # 不再滞留 sim
    assert matrix[("B", "A")].wr_a == pytest.approx(0.45)


def test_镜像纳入_期望胜率():
    """镜像格（源提供）纳入期望，且源数据优先于 50% 默认。"""
    cells = _sim_cells() + [MatchupCell("A", "A", 0.55, n=500, source="sim")]
    matrix = assemble_matrix([], cells, POOL)
    field = {"A": 0.5, "B": 0.3, "C": 0.2}
    # A: .5*.55(源镜像) + .3*.6 + .2*.7 = .595
    assert expected_winrate("A", field, matrix) == pytest.approx(0.595)


# ── task 140（v0.3 口径：源缺镜像按 50% 默认计入）────────────

def test_镜像默认50pct_补格与源优先():
    """源缺对角 → (d,d)=0.5 source='mirror'；源提供对角 → 源数据优先。"""
    matrix = assemble_matrix([], _sim_cells(), POOL)
    for d in POOL:
        cell = matrix[(d, d)]
        assert cell.wr_a == 0.5 and cell.source == "mirror" and cell.n == 0
    # 源提供对角（如未来 sim 偏差包含镜像格）不被默认覆盖
    cells = _sim_cells() + [MatchupCell("B", "B", 0.62, n=500, source="sim")]
    matrix2 = assemble_matrix([], cells, POOL)
    assert matrix2[("B", "B")].wr_a == 0.62 and matrix2[("B", "B")].source == "sim"


def test_镜像默认_高份额构筑受益回归():
    """Owner gate review 裁决机制固化：高份额构筑的镜像 50% 不再被丢弃。

    field A=.7 B=.3。剔除口径下 A 期望仅 .3×.40=.12（七成份额被丢弃）；
    默认 50% 后 A 期望 = .7×.5 + .3×.40 = .47——+.35 镜像项回正即机制锚点。
    """
    sim = [MatchupCell("A", "B", 0.40, n=500, source="sim"),
           MatchupCell("B", "A", 0.60, n=500, source="sim")]
    matrix = assemble_matrix([], sim, ["A", "B"])
    field = {"A": 0.7, "B": 0.3}
    exp_a = expected_winrate("A", field, matrix)
    exp_b = expected_winrate("B", field, matrix)
    assert exp_a == pytest.approx(0.7 * 0.5 + 0.3 * 0.40)
    assert exp_b == pytest.approx(0.3 * 0.5 + 0.7 * 0.60)
    assert exp_a - 0.3 * 0.40 == pytest.approx(0.35)  # 镜像项在场


def test_镜像默认_不污染来源构成():
    """source='mirror' 不计入真实格贡献 / 缺格 share / 缺格格数。"""
    matrix = assemble_matrix([], _sim_cells(), POOL)
    rep = field_pick({"A": 0.5, "B": 0.3, "C": 0.2}, matrix, POOL, n_sim=20)
    assert rep.n_low_conf_cells == 0
    for r in rep.rows:
        assert r["low_conf_cells"] == 0 and not r["data_poor"]
        # 真实格贡献：全 sim 场为 0（镜像格不混入）
        assert r["intl_value_share"] == 0.0


def test_来源构成与数据不足标注():
    sim = _sim_cells()
    intl = [MatchupCell("A", "B", 0.55, n=40, source="intl")]
    matrix = assemble_matrix(intl, sim, POOL + ["D"])
    # D 完全无数据 → 缺格 share=1.0 ≥0.2 → data_poor
    rep = field_pick({"A": 0.5, "B": 0.3, "C": 0.2, "D": 1e-9},
                     matrix, POOL + ["D"], n_sim=20)
    row_d = next(r for r in rep.rows if r["deck"] == "D")
    assert row_d["data_poor"] and row_d["missing_share"] > 0.2
    row_a = next(r for r in rep.rows if r["deck"] == "A")
    assert 0.0 < row_a["intl_value_share"] < 1.0  # 混合来源可分解
    assert "⚠数据不足" in format_field_pick(rep)
