"""task 046 WP1：top-3 复评 + 双门槛 holdout 验证 + 敏感性报告（D-046-1/2）。

重建/选择/聚合全部为纯函数单测（合成轨迹行，不打真局）；run_verify 与 CLI
端到端走 stub execute 注入（按向量内容返回可控 fitness），复评不打真局。
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from battlefrontier.cli import main
from battlefrontier.tune.fitness import EvalResult
from battlefrontier.tune.search import DimTrial, coordinate_descent
from battlefrontier.tune.space import default_vector, search_space
from battlefrontier.tune.verify import (
    CandidateEval,
    ReconstructedSearch,
    gate_verdict,
    reconstruct_search,
    run_verify,
    select_final,
    sensitivity_rows,
    top_candidates,
)

SPACE = search_space()
BASE = default_vector()
DIM = {d.name: d for d in SPACE}


def _row(vector, score):
    """合成轨迹行（reconstruct 只读 vector/score 两键，对齐 trajectory_row 协议）。"""
    return {"vector": dict(vector), "score": score}


def _sweep_rows(current, cur, dim_name, best=None):
    """单 sweep 试投行（grid 序、跳过当前值）：best=(value, score) 指定某点得分，其余 = cur。"""
    dim = DIM[dim_name]
    rows = []
    for p in dim.grid:
        if p == current[dim.name]:
            continue
        vec = dict(current)
        vec[dim.name] = p
        score = best[1] if best and p == best[0] else cur
        rows.append(_row(vec, score))
    return rows


def _capture_run(evaluate, noise_threshold=0.01, max_rounds=3):
    """用真实坐标下降生成轨迹行（与 run_tune 写盘协议同构），返回 (rows, SearchResult)。"""
    rows = []

    def capture(vec):
        score = evaluate(vec)
        rows.append(_row(vec, score))
        return score

    result = coordinate_descent(capture, space=SPACE, start=dict(BASE),
                                noise_threshold=noise_threshold, max_rounds=max_rounds)
    return rows, result


def _recon_with(trials):
    return ReconstructedSearch(
        baseline_vector=dict(BASE), baseline_fitness=0.5,
        best_vector=dict(BASE), best_fitness=0.5,
        trials=tuple(trials), n_evaluations=1 + len(trials), rounds_run=1, space=SPACE)


# ── reconstruct_search：合法轨迹 ──────────────────────────

def test_重建_基线单行():
    recon = reconstruct_search([_row(BASE, 0.5)], noise_threshold=0.01)
    assert recon.baseline_vector == BASE
    assert recon.baseline_fitness == 0.5
    assert recon.best_vector == BASE and recon.best_fitness == 0.5
    assert recon.trials == ()
    assert recon.n_evaluations == 1 and recon.rounds_run == 0


def test_重建_与坐标下降等价_两轮采纳与拒绝():
    """第 1 轮 w_hp/w_damage 采纳、第 2 轮整轮无改进——重建结果与搜索器逐字段一致。"""
    def evaluate(vec):
        score = 0.5
        if vec["w_hp"] == DIM["w_hp"].grid[-1]:       # 4.0
            score += 0.03
        if vec["w_damage"] == DIM["w_damage"].grid[-1]:  # 20.0
            score += 0.02
        return score

    rows, result = _capture_run(evaluate)
    recon = reconstruct_search(rows, noise_threshold=0.01)
    assert recon.baseline_vector == BASE
    assert recon.baseline_fitness == result.baseline_fitness
    assert recon.best_vector == result.best_vector
    assert recon.best_fitness == result.best_fitness
    assert recon.n_evaluations == result.n_evaluations == len(rows)
    assert recon.rounds_run == result.rounds_run == 2
    assert recon.trials == result.trials
    adopted = [(t.dim, t.value, t.round) for t in recon.trials if t.adopted]
    assert adopted == [("w_hp", 4.0, 1), ("w_damage", 20.0, 1)]


def test_重建_第二轮采纳_当前值不入试投():
    """第 2 轮继续改进（维间交互：w_hp=2.0 仅在 w_damage=20.0 已采纳后更优）：
    已采纳值跳过试投（sweep 序列随 current 收缩）。"""
    def evaluate(vec):
        score = 0.5
        if vec["w_hp"] == 4.0:
            score += 0.03
        if vec["w_damage"] == 20.0:
            score += 0.02
        if vec["w_hp"] == 2.0 and vec["w_damage"] == 20.0:
            score += 0.05
        return score

    rows, result = _capture_run(evaluate)
    recon = reconstruct_search(rows, noise_threshold=0.01)
    assert recon.trials == result.trials
    assert recon.rounds_run == result.rounds_run == 3
    adopted = [(t.dim, t.value, t.round) for t in recon.trials if t.adopted]
    assert adopted == [("w_hp", 4.0, 1), ("w_damage", 20.0, 1), ("w_hp", 2.0, 2)]
    assert recon.best_vector["w_hp"] == 2.0
    # 第 2 轮 w_hp sweep 不试当前值 4.0
    r2_hp = [t.value for t in recon.trials if t.round == 2 and t.dim == "w_hp"]
    assert 4.0 not in r2_hp


def test_重建_噪声门槛边界_恰等不采纳():
    """Δ == 噪声门槛不采纳（严格大于才采纳；0.75-0.5=0.25 二进制精确）。"""
    current = dict(BASE)
    rows = [_row(current, 0.5)]
    rows += _sweep_rows(current, 0.5, "w_hp", best=(4.0, 0.75))
    for dim in SPACE[1:]:
        rows += _sweep_rows(current, 0.5, dim.name)
    recon = reconstruct_search(rows, noise_threshold=0.25)
    assert recon.best_vector == BASE
    assert not any(t.adopted for t in recon.trials)
    hp_best = next(t for t in recon.trials if t.dim == "w_hp" and t.value == 4.0)
    assert hp_best.delta == pytest.approx(0.25)


# ── reconstruct_search：篡改族（不猜，显式报错）─────────────

def test_重建_空轨迹报错():
    with pytest.raises(ValueError, match="轨迹为空"):
        reconstruct_search([], noise_threshold=0.01)


def test_重建_篡改_基线缺维报错():
    bad = {k: v for k, v in BASE.items() if k != "w_hp"}
    with pytest.raises(ValueError, match="缺维"):
        reconstruct_search([_row(bad, 0.5)], noise_threshold=0.01)


def test_重建_篡改_行键集合不符报错_带行号():
    bad = dict(BASE)
    bad["bogus"] = 1
    rows = [_row(BASE, 0.5), _row(bad, 0.5)]
    with pytest.raises(ValueError, match="第 1 行.*未知维"):
        reconstruct_search(rows, noise_threshold=0.01)


def test_重建_篡改_零维差异报错():
    rows = [_row(BASE, 0.5), _row(BASE, 0.5)]
    with pytest.raises(ValueError, match="第 1 行.*差异维数"):
        reconstruct_search(rows, noise_threshold=0.01)


def test_重建_篡改_两维差异报错_带行号():
    rows = [_row(BASE, 0.5)]
    rows += _sweep_rows(dict(BASE), 0.5, "w_hp")       # 完整 w_hp sweep（rows 1..5）
    bad = dict(BASE)
    bad["w_hp"] = 4.0
    bad["w_damage"] = 10.0
    rows.append(_row(bad, 0.6))                         # 第 6 行：两维同时变更
    with pytest.raises(ValueError, match="第 6 行.*差异维数.*2"):
        reconstruct_search(rows, noise_threshold=0.01)


def test_重建_篡改_试投值不在网格报错():
    vec = dict(BASE)
    vec["w_hp"] = 12345.0
    rows = [_row(BASE, 0.5), _row(vec, 0.6)]
    with pytest.raises(ValueError, match="网格"):
        reconstruct_search(rows, noise_threshold=0.01)


def test_重建_篡改_扫维顺序不符报错():
    rows = [_row(BASE, 0.5)]
    rows += _sweep_rows(dict(BASE), 0.5, "w_damage")  # 首 sweep 应为 w_hp
    with pytest.raises(ValueError, match="顺序"):
        reconstruct_search(rows, noise_threshold=0.01)


def test_重建_篡改_sweep漏点报错():
    rows = [_row(BASE, 0.5)]
    rows += _sweep_rows(dict(BASE), 0.5, "w_hp")[:-1]  # 漏掉最后一个网格点
    rows += _sweep_rows(dict(BASE), 0.5, "w_damage")   # 换维触发上一 sweep 结算
    with pytest.raises(ValueError, match="试投序列"):
        reconstruct_search(rows, noise_threshold=0.01)


def test_重建_篡改_轮次截断报错():
    current = dict(BASE)
    rows = [_row(current, 0.5)]
    for dim in SPACE[:5]:  # 只扫 5 维 = 非完整轮
        rows += _sweep_rows(current, 0.5, dim.name)
    with pytest.raises(ValueError, match="截断"):
        reconstruct_search(rows, noise_threshold=0.01)


# ── top_candidates ───────────────────────────────────────

def test_top_candidates_同向量去重保留先见():
    trials = [
        DimTrial(round=1, dim="w_hp", value=4.0, fitness=0.53, delta=0.03, adopted=True),
        DimTrial(round=1, dim="w_damage", value=20.0, fitness=0.55, delta=0.02, adopted=True),
        DimTrial(round=2, dim="w_hp", value=1.0, fitness=0.60, delta=0.05, adopted=True),
        DimTrial(round=2, dim="w_hp", value=4.0, fitness=0.65, delta=0.05, adopted=True),
    ]
    # waypoint：V1={w_hp:4}@0.53，V2={w_hp:4,w_damage:20}@0.55，
    #           V3={w_hp:1,w_damage:20}@0.60，V4 向量同 V2 → 去重保留先见
    cands = top_candidates(_recon_with(trials), k=5)
    assert [(c.vector["w_hp"], c.vector["w_damage"], c.search_fitness) for c in cands] == [
        (1.0, 20.0, 0.60), (4.0, 20.0, 0.55), (4.0, 5.0, 0.53)]


def test_top_candidates_降序_tie_先见序():
    trials = [
        DimTrial(round=1, dim="w_hp", value=4.0, fitness=0.55, delta=0.05, adopted=True),
        DimTrial(round=1, dim="w_damage", value=20.0, fitness=0.60, delta=0.05, adopted=True),
        DimTrial(round=2, dim="w_hp", value=2.0, fitness=0.60, delta=0.00, adopted=True),
    ]
    cands = top_candidates(_recon_with(trials))
    assert [c.search_fitness for c in cands] == [0.60, 0.60, 0.55]
    assert cands[0].vector["w_hp"] == 4.0   # 同分先见（V2）在前
    assert cands[1].vector["w_hp"] == 2.0


def test_top_candidates_k截断():
    trials = [
        DimTrial(round=1, dim="w_hp", value=4.0, fitness=0.51, delta=0.01, adopted=True),
        DimTrial(round=1, dim="w_damage", value=20.0, fitness=0.52, delta=0.01, adopted=True),
        DimTrial(round=1, dim="w_retreat", value=-40.0, fitness=0.53, delta=0.01,
                 adopted=True),
        DimTrial(round=1, dim="w_board", value=4.0, fitness=0.54, delta=0.01, adopted=True),
    ]
    cands = top_candidates(_recon_with(trials), k=3)
    assert len(cands) == 3
    assert [c.search_fitness for c in cands] == [0.54, 0.53, 0.52]


def test_top_candidates_零采纳_空表():
    recon = _recon_with([
        DimTrial(round=1, dim="w_hp", value=4.0, fitness=0.50, delta=0.0, adopted=False)])
    assert top_candidates(recon) == []


# ── gate_verdict（D-046-1 双门槛）──────────────────────────

@pytest.mark.parametrize(("train", "holdout", "expected"), [
    (0.5, 0.5, False),      # 训练须严格 >0.5
    (0.5, 0.9, False),
    (0.51, 0.49, False),    # holdout 须 ≥0.5
    (0.51, 0.5, True),      # holdout 含平过线
    (0.6, 0.7, True),
    (0.5000001, 0.5, True),
])
def test_gate_verdict_边界组合(train, holdout, expected):
    assert gate_verdict(train, holdout) is expected


# ── select_final ─────────────────────────────────────────

def _ce(cid, train, holdout):
    return CandidateEval(candidate_id=cid, vector=dict(BASE), search_fitness=0.5,
                         train_winrate=train, holdout_winrate=holdout,
                         passed=gate_verdict(train, holdout))


def test_select_final_holdout最高者胜():
    verdict = select_final([_ce(1, 0.60, 0.55), _ce(2, 0.55, 0.60)])
    assert verdict.final is not None and verdict.final.candidate_id == 2


def test_select_final_tie_holdout_取训练高():
    verdict = select_final([_ce(1, 0.60, 0.55), _ce(2, 0.65, 0.55)])
    assert verdict.final.candidate_id == 2


def test_select_final_tie双全等_取先见序():
    verdict = select_final([_ce(1, 0.60, 0.55), _ce(2, 0.60, 0.55)])
    assert verdict.final.candidate_id == 1


def test_select_final_未过线者不参与选择():
    """c1 holdout 0.99 但训练未过线——不选；c2 恰好双过线（holdout 含平）中选。"""
    verdict = select_final([_ce(1, 0.45, 0.99), _ce(2, 0.55, 0.50)])
    assert verdict.final.candidate_id == 2
    assert len(verdict.passed) == 1


def test_select_final_零过线_默认参数即局部最优():
    verdict = select_final([_ce(1, 0.50, 0.99), _ce(2, 0.60, 0.49)])
    assert verdict.final is None
    assert "默认参数即局部最优" in verdict.reason
    assert verdict.passed == ()


# ── sensitivity_rows ─────────────────────────────────────

def test_敏感性_逐维聚合与输出序确定():
    trials = (
        DimTrial(round=1, dim="w_hp", value=0.0, fitness=0.49, delta=-0.01, adopted=False),
        DimTrial(round=1, dim="w_hp", value=4.0, fitness=0.53, delta=0.03, adopted=True),
        DimTrial(round=2, dim="w_hp", value=0.0, fitness=0.51, delta=-0.02, adopted=False),
        DimTrial(round=1, dim="w_damage", value=10.0, fitness=0.52, delta=0.02,
                 adopted=True),
    )
    recon = ReconstructedSearch(
        baseline_vector=dict(BASE), baseline_fitness=0.5,
        best_vector=dict(BASE), best_fitness=0.55,
        trials=trials, n_evaluations=5, rounds_run=2, space=SPACE)
    rows = sensitivity_rows(recon)
    # 输出序 = space 维序 → grid 序（含从未试投的网格值）
    expected_order = [(d.name, v) for d in SPACE for v in d.grid]
    assert [(r.dim, r.value) for r in rows] == expected_order
    by = {(r.dim, r.value): r for r in rows}
    r = by[("w_hp", 0.0)]
    assert r.best_delta == pytest.approx(-0.01)  # 两轮取最佳（max）
    assert r.n_trials == 2 and r.rounds == (1, 2)
    r = by[("w_hp", 4.0)]
    assert r.best_delta == pytest.approx(0.03) and r.n_trials == 1 and r.rounds == (1,)
    r = by[("w_hp", 0.25)]  # 从未试投
    assert r.best_delta is None and r.n_trials == 0 and r.rounds == ()
    # 确定性：同输入两次调用全等
    assert sensitivity_rows(recon) == rows


# ── run_verify（stub execute 注入，不打真局）────────────────

TRAIN_SENTINEL = ["train-prepared"]
HOLDOUT_SENTINEL = ["holdout-prepared"]


def _adopt_hp_rows():
    """w_hp=4.0 第 1 轮采纳的合法轨迹（其余全平）。"""
    def evaluate(vec):
        return 0.53 if vec["w_hp"] == 4.0 else 0.5

    rows, _ = _capture_run(evaluate)
    return rows


def _stub_execute(train_fitness, holdout_fitness, calls):
    """按 prepared 哨兵区分训练/holdout，按向量返回可控 fitness。"""
    def stub(prepared, vector, games, *, workers=1):
        calls.append({"prepared": prepared, "vector": dict(vector),
                      "games": games, "workers": workers})
        fitness = train_fitness if prepared == TRAIN_SENTINEL else holdout_fitness
        return EvalResult(vector=dict(vector), fitness=fitness, pairs=(), wall_seconds=0.0)
    return stub


def test_run_verify_过线_采纳候选():
    rows = _adopt_hp_rows()
    calls = []
    result = run_verify(rows=rows, noise_threshold=0.01,
                        train_prepared=TRAIN_SENTINEL,
                        holdout_prepared=HOLDOUT_SENTINEL,
                        games=500, execute=_stub_execute(0.60, 0.55, calls), workers=4)
    assert len(result.candidates) == 1
    cand = result.candidates[0]
    assert cand.vector["w_hp"] == 4.0 and cand.passed is True
    assert (cand.train_winrate, cand.holdout_winrate) == (0.60, 0.55)
    assert result.verdict.final == cand
    assert result.games == 500
    # 训练/holdout 各复评一次，局数与 workers 透传
    assert [(c["prepared"], c["games"], c["workers"]) for c in calls] == [
        (TRAIN_SENTINEL, 500, 4), (HOLDOUT_SENTINEL, 500, 4)]


def test_run_verify_不过线_默认即局部最优():
    rows = _adopt_hp_rows()
    result = run_verify(rows=rows, noise_threshold=0.01,
                        train_prepared=TRAIN_SENTINEL,
                        holdout_prepared=HOLDOUT_SENTINEL,
                        games=500, execute=_stub_execute(0.60, 0.49, []))
    assert result.verdict.final is None
    assert "默认参数即局部最优" in result.verdict.reason
    assert result.candidates[0].passed is False  # holdout 0.49 < 0.5


def test_run_verify_零采纳_无候选_不调execute():
    current = dict(BASE)
    rows = [_row(current, 0.5)]
    for dim in SPACE:
        rows += _sweep_rows(current, 0.5, dim.name)
    calls = []
    result = run_verify(rows=rows, noise_threshold=0.01,
                        train_prepared=TRAIN_SENTINEL,
                        holdout_prepared=HOLDOUT_SENTINEL,
                        games=500, execute=_stub_execute(0.9, 0.9, calls))
    assert result.candidates == () and result.verdict.final is None
    assert calls == []


def test_run_verify_holdout为空_显式报错():
    with pytest.raises(ValueError, match="holdout"):
        run_verify(rows=_adopt_hp_rows(), noise_threshold=0.01,
                   train_prepared=TRAIN_SENTINEL, holdout_prepared=[],
                   games=500, execute=_stub_execute(0.6, 0.6, []))


# ── CLI：bfsim tune-verify ────────────────────────────────

POOL_PATH = Path(__file__).resolve().parent.parent / "config" / "target-pool.v1.yml"


def _write_defn(tmp_path, *, name, pairs=None):
    text = (f"name: {name}\npool: {POOL_PATH.as_posix()}\n"
            f"games_per_pair: 20\nsplit_seed: 20261011\nmax_rounds: 1\n")
    if pairs:
        text += "pairs:\n" + "".join(f"  - [{a}, {b}]\n" for a, b in pairs)
    p = tmp_path / f"{name}.yml"
    p.write_text(text, encoding="utf-8")
    return p


def test_cli_tune_verify_子命令注册_缺定义参数报错():
    with pytest.raises(SystemExit):
        main(["tune-verify"])


def test_cli_tune_verify_pairs模式无holdout_显式报错(tmp_path, capsys):
    defn = _write_defn(tmp_path, name="tv-noholdout",
                       pairs=[("沙奈朵", "喷火龙 大比鸟")])
    traj = tmp_path / "t.jsonl"
    traj.write_text(json.dumps(_row(BASE, 0.5)) + "\n", encoding="utf-8")
    rc = main(["tune-verify", str(defn), "--trajectory", str(traj), "--db", "dummy"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "错误" in out and "holdout" in out


def test_cli_tune_verify_端到端_stub评估_缺省路径推导(tmp_path, capsys, monkeypatch):
    """全量划分（真实池 YAML，无 db 依赖）+ stub prepare/execute：默认轨迹/输出路径
    推导、候选打印、最终判定、敏感性表、结果 JSON 落盘。"""
    import battlefrontier.tune.fitness as fitness_mod
    import battlefrontier.tune.verify as verify_mod

    monkeypatch.chdir(tmp_path)
    defn = _write_defn(tmp_path, name="tv-e2e")

    def fake_prepare(assignments, db_path, cards_dir="cards"):
        return [SimpleNamespace(assignment=a) for a in assignments]

    calls = []

    def stub_execute(prepared, vector, games, *, workers=1):
        side = "train" if len(prepared) == 24 else "holdout"
        calls.append({"side": side, "vector": dict(vector), "games": games})
        fitness = 0.60 if side == "train" else 0.55
        return EvalResult(vector=dict(vector), fitness=fitness, pairs=(), wall_seconds=0.0)

    monkeypatch.setattr(fitness_mod, "prepare_pairs", fake_prepare)
    monkeypatch.setattr(verify_mod, "execute_plan", stub_execute)

    # 缺省轨迹路径 results/tune-<name>.jsonl（cwd 已切 tmp_path）
    traj_dir = tmp_path / "results"
    traj_dir.mkdir()
    rows = _adopt_hp_rows()
    (traj_dir / "tune-tv-e2e.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    rc = main(["tune-verify", str(defn), "--db", "dummy"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "候选 #1" in out and "w_hp" in out
    assert "最终判定" in out and "采纳" in out
    assert "敏感性" in out
    # 缺省输出路径 results/tune-<name>-verify.json
    out_json = traj_dir / "tune-tv-e2e-verify.json"
    assert out_json.exists()
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["name"] == "tv-e2e"
    assert report["games_per_pair"] == 500     # --games 缺省 500（D-046-4）
    assert report["split_seed"] == 20261011
    assert report["verdict"]["adopted"] is True
    assert report["verdict"]["vector"]["w_hp"] == 4.0
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["train_winrate"] == 0.60
    assert report["candidates"][0]["holdout_winrate"] == 0.55
    assert report["candidates"][0]["passed"] is True
    assert len(report["sensitivity"]) == sum(len(d.grid) for d in SPACE)
    # 复评调用：候选 ×（训练+holdout），games=500 透传
    assert [(c["side"], c["games"]) for c in calls] == [("train", 500), ("holdout", 500)]
