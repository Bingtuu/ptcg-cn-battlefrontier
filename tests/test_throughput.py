"""task 149：吞吐决策点 spike——BC 训练最低需求 vs R2 实测产能判定。

判据预注册（task 149 设计段）：需求 = 1M 决策点/轮 + 50k 局 rollout/轮；
三态判定 = 决策点日产能 ≥3M 且 局日产能 ≥300k → "r2"；否则 "r1_spike"
（估期 ≤6 周门由 Owner 侧评估）/"kill" 由 decide_r2 纯函数给出。
"""

import pytest
from helpers import deck60

from battlefrontier.runner.experiment import PreparedExperiment
from battlefrontier.runner.throughput import (
    ProbeResult,
    decide_r2,
    probe_throughput,
)


def _stub_prep():
    return PreparedExperiment(
        deck_a=deck60(), deck_b=deck60(), card_effects={},
        deck_a_id="stub", deck_b_id="stub", data_version="test")


def test_probe_result_internal_consistency(tmp_path):
    r = probe_throughput("heuristic", games=6, workers=1, seed_start=900000,
                         prep=_stub_prep(), results_path=tmp_path / "p.db")
    assert r.games_completed == 6
    assert r.decisions_per_game > 0
    assert r.wall_s > 0
    assert r.games_per_s > 0
    assert r.decisions_per_s == pytest.approx(
        r.games_per_s * r.decisions_per_game)


def test_probe_decisions_counted_exactly(tmp_path):
    """串行 pass 决策点计数 = 每局两 agent observe 调用数之和（下限 = 2×回合数）。"""
    r = probe_throughput("random", games=4, workers=1, seed_start=910000,
                         prep=_stub_prep(), results_path=tmp_path / "p.db")
    assert r.decisions_total >= 2 * r.turns_total
    assert r.decisions_total == int(r.decisions_per_game * r.games_completed)


def test_probe_parallel_completes_all_games(tmp_path):
    r = probe_throughput("random", games=8, workers=2, seed_start=920000,
                         prep=_stub_prep(), results_path=tmp_path / "p.db")
    assert r.games_completed == 8
    assert r.workers == 2


def test_probe_distilled_requires_policy_path(tmp_path):
    with pytest.raises(ValueError, match="policy_path"):
        probe_throughput("distilled", games=2, workers=1, seed_start=930000,
                         prep=_stub_prep(), results_path=tmp_path / "p.db")


def test_decide_r2_thresholds():
    req = {"decisions_per_day": 3_000_000, "games_per_day": 300_000}
    # 双过线 → r2
    assert decide_r2(ProbeResult("heuristic", 1, 1, 1.0, 100.0, 0.01, 100.0,
                                 100, 100, 10), req) == "r2"
    # 双不足 → r1_spike
    assert decide_r2(ProbeResult("heuristic", 1, 1, 1.0, 1.0, 1.0, 5.0,
                                 5, 5, 1), req) == "r1_spike"
    # 决策点够但局产能不足（双门槛取严）→ r1_spike
    assert decide_r2(ProbeResult("heuristic", 1, 1, 1.0, 3.0, 0.33, 100.0,
                                 300, 3, 1), req) == "r1_spike"


def test_probe_result_fields():
    r = ProbeResult(agent_type="heuristic", games=10, workers=1, wall_s=2.0,
                    games_per_s=5.0, sec_per_game=0.2, decisions_per_game=40.0,
                    decisions_total=400, turns_total=300, games_completed=10)
    assert r.decisions_per_s == pytest.approx(200.0)
    assert r.decisions_per_day == pytest.approx(200.0 * 86400)
    assert r.games_per_day == pytest.approx(5.0 * 86400)


def test_net_forward_probe_real_asset():
    """真 policy 资产微基准：输出含 µs/次 与前向速率，输入维 = w1 列数。"""
    from pathlib import Path

    from battlefrontier.learn.policy_model import load_policy_model
    from battlefrontier.runner.throughput import net_forward_probe

    path = Path(__file__).parent.parent / "models" / "policy-m12-v2.json"
    out = net_forward_probe(path, n=200)
    model = load_policy_model(path)
    dim = len(model.weights["w1"][0])
    assert f"{dim} 维输入" in out
    assert "µs/次" in out
