"""task 127：league_report——按 group_name 回收细胞、BT-MLE 评级、
成对胜率矩阵、meta + 限定语头注。手工灌库（test_paired 惯例），error 局剔除。
"""

import pytest
import yaml

from battlefrontier.report import SIM_INTERPRETATION_NOTE
from battlefrontier.report.league import league_report
from battlefrontier.runner.results_db import ResultsDB


def _cell_yaml(a_id, b_id, deck_index=0, sha="abc123"):
    return yaml.safe_dump(
        {"experiment": {"name": "x"}, "league": {
            "agents": {"a": a_id, "b": b_id},
            "deck_index": deck_index, "registry_sha256": sha}})


def _fill_league(db_path):
    """3 agent 循环优势链：A>B 4:0，B>C 4:0，A>C 2:2（平）+ 1 局 error 噪声。"""
    db = ResultsDB(db_path)
    try:
        spec = [("A", "B", [(0, 0)] * 4),
                ("B", "C", [(0, 0)] * 4),
                ("A", "C", [(0, 0), (1, 0), (0, 0), (1, 0)])]
        for a_id, b_id, outcomes in spec:
            exp_id = db.start_experiment(
                name="lg-c000", definition_yaml=_cell_yaml(a_id, b_id),
                code_version="test", data_version="test",
                group_name="lg", variant=f"{a_id}-vs-{b_id}")
            from battlefrontier.runner.play import GameResult
            for i, (w, fp) in enumerate(outcomes):
                db.record_game(
                    exp_id, seed=100 + i, first_player=fp,
                    result=GameResult(winner=w, is_draw=False, turns=10, phase="main",
                                      first_player=fp, events=[], events_hash="h"),
                    deck_a_id="stub", deck_b_id="stub")
            # 噪声：不属于任何 league 元段/失败局必须被剔除
            db.record_error(exp_id, seed=200, deck_a_id="s", deck_b_id="s",
                            error="boom")
        # 别的联赛名不得混入
        other = db.start_experiment(
            name="other", definition_yaml=_cell_yaml("A", "B"),
            code_version="t", data_version="t", group_name="other-lg")
        from battlefrontier.runner.play import GameResult
        db.record_game(other, seed=1, first_player=0,
                       result=GameResult(winner=0, is_draw=False, turns=5, phase="main",
                                         first_player=0, events=[], events_hash="h"),
                       deck_a_id="s", deck_b_id="s")
        return db_path
    finally:
        db.close()


def test_report_rating_order_and_matrix(tmp_path):
    _fill_league(tmp_path / "x.db")
    rep = league_report(tmp_path / "x.db", "lg")
    # 链 A>B>C → 排序 A 最高 C 最低
    assert [r.agent for r in rep.ratings] == ["A", "B", "C"]
    assert rep.ratings[0].log_strength > rep.ratings[1].log_strength > rep.ratings[2].log_strength
    # 矩阵：A vs B = 4/4，A vs C = 2/4（双向合并后仍是这些数）
    m = rep.matrix
    assert m[("A", "B")].wins == 4 and m[("A", "B")].games == 4
    assert m[("A", "C")].wins == 2 and m[("A", "C")].games == 4
    # error 局未计入
    assert m[("A", "B")].games + m[("B", "C")].games + m[("A", "C")].games == 12
    # 其他联赛不混入（矩阵双向键均须落在 lg 的 agent 对内）
    pairs = {("A", "B"), ("B", "A"), ("B", "C"), ("C", "B"), ("A", "C"), ("C", "A")}
    assert all(k in pairs for k in m)


def test_report_meta_and_disclaimer(tmp_path):
    _fill_league(tmp_path / "x.db")
    rep = league_report(tmp_path / "x.db", "lg")
    text = rep.format_text()
    assert SIM_INTERPRETATION_NOTE in text
    assert "abc123" in text          # registry sha256 回显
    assert "lg" in text
    for agent in ("A", "B", "C"):
        assert agent in text


def test_report_unknown_league_raises(tmp_path):
    _fill_league(tmp_path / "x.db")
    with pytest.raises(ValueError, match="nonexistent"):
        league_report(tmp_path / "x.db", "nonexistent")
