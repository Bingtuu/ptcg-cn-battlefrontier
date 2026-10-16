"""task 050 WP1：M11 数据产线（D-M11-1）——collector 钩子 + runner/collect + CLI。

验收口径见 `tasks/task 050.md`：collector=None 默认零变化（events_hash 回归）/
main 阶段决策点逐条记录（turn/player/特征/action 结构）/ 标签三态（胜 1/平 0.5/负 0）/
collector 不消费随机源（同种子有无 collector 两跑 events_hash 全等）/ 失败局剔除计数 /
产线串并一致（workers=1 vs 2 产物逐行一致）/ 种子区间（pair i → [S+i×N, +N)）/
端到端小预算（2 对 × 8 局 stub + 真实池 CLI 冒烟）。
"""

import json
from pathlib import Path

import pytest
import yaml
from helpers import deck60, energy, main_state

from battlefrontier.agent.collect import FeatureCollector
from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.agent.heuristic import HeuristicAgent
from battlefrontier.cli import main as cli_main
from battlefrontier.engine.actions import Action
from battlefrontier.runner.collect import (
    _run_one_collect,
    collect_seed_range,
    pair_filename,
    run_collect,
)
from battlefrontier.runner.experiment import _unique_docs
from battlefrontier.runner.play import play_game
from battlefrontier.tune.fitness import PairAssignment, PreparedPair


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"测试A{index}",
                                  archetype_b=f"测试B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


def _heuristic_mirror(seed: int, collector=None):
    return play_game(deck60(), deck60(), seed=seed,
                     agents=[HeuristicAgent(), HeuristicAgent()],
                     collector=collector)


class _CountingHeuristic(HeuristicAgent):
    """统计 main 阶段 observe 调用次数（决策点计数对拍用）。"""

    def __init__(self) -> None:
        super().__init__()
        self.main_calls = 0

    def observe(self, view, legal_actions):
        if view.phase == "main":
            self.main_calls += 1
        return super().observe(view, legal_actions)


# ── collector 钩子 ────────────────────────────────────────

def test_collector_None默认_行为零变化():
    """不传 collector（默认路径）与显式 collector=None：产物无采集行，hash 不变。"""
    a = _heuristic_mirror(11)
    b = _heuristic_mirror(11, collector=None)
    assert a.events_hash == b.events_hash
    assert (a.winner, a.is_draw, a.turns) == (b.winner, b.is_draw, b.turns)
    assert a.collected_rows is None and b.collected_rows is None


def test_collector_不消费随机源_同种子hash全等():
    """同种子有无 collector 两跑：events_hash 逐值全等（采集对行为零影响）。"""
    plain = _heuristic_mirror(13)
    collected = _heuristic_mirror(13, collector=FeatureCollector())
    assert plain.events_hash == collected.events_hash
    assert (plain.winner, plain.is_draw, plain.turns) == \
        (collected.winner, collected.is_draw, collected.turns)
    assert collected.collected_rows is not None and collected.collected_rows


def test_main阶段决策点_逐条记录与结构():
    """采集行数 == 双方 main 阶段 observe 调用总数；行结构 = turn/player/特征/action/label。"""
    agents = [_CountingHeuristic(), _CountingHeuristic()]
    collector = FeatureCollector()
    result = play_game(deck60(), deck60(), seed=17, agents=agents, collector=collector)
    rows = result.collected_rows
    assert rows is not None
    assert len(rows) == agents[0].main_calls + agents[1].main_calls
    assert len(rows) > 0
    for row in rows:
        assert set(row) == {"turn", "player", "features", "action", "label"}
        assert isinstance(row["turn"], int) and row["turn"] >= 1
        assert row["player"] in (0, 1)
        assert tuple(row["features"]) == FEATURE_NAMES
        assert isinstance(row["action"], dict) and isinstance(row["action"]["kind"], str)
        assert row["label"] in (0.0, 0.5, 1.0)
    # 标签与结局一致（白板镜像一般分胜负）
    if not result.is_draw:
        assert all(r["label"] == (1.0 if r["player"] == result.winner else 0.0)
                   for r in rows)


def test_标签三态_胜平负():
    """行动方视角：胜 1 / 平 0.5 / 负 0；非 main 阶段决策不记录。"""
    view = main_state().visible_state(0)
    choice_view = main_state().model_copy(update={"phase": "choice"}).visible_state(0)
    act = Action(kind="end_turn")

    c = FeatureCollector()
    c.on_decision(choice_view, 0, Action(kind="choose", choices=(1,)))  # 非 main 不记
    c.on_decision(view, 0, act)
    c.on_decision(view, 1, act)
    assert [r["label"] for r in c.finish(winner=0, is_draw=False)] == [1.0, 0.0]
    assert [r["player"] for r in c.finish(winner=0, is_draw=False)] == [0, 1]
    assert all(r["label"] == 0.5 for r in c.finish(winner=None, is_draw=True))


def test_finish_无胜非平_显式报错():
    """winner=None 且非平局 = 异常结局（不猜纪律）。"""
    c = FeatureCollector()
    c.on_decision(main_state().visible_state(0), 0, Action(kind="end_turn"))
    with pytest.raises(ValueError, match="结局"):
        c.finish(winner=None, is_draw=False)


# ── worker ────────────────────────────────────────────────

def _collect_payload(seed: int, pair_index: int = 0, deck_a=None) -> dict:
    pair = _stub_pair(pair_index)
    return {
        "deck_a": [c.model_dump(mode="json") for c in (deck_a or pair.deck_a)],
        "deck_b": [c.model_dump(mode="json") for c in pair.deck_b],
        "card_effects": [d.model_dump(mode="json")
                         for d in _unique_docs(pair.card_effects.values())],
        "seed": seed,
        "pair_index": pair_index,
    }


def test_worker_正常局_返回行与种子():
    seed, pair_index, rows, error = _run_one_collect(_collect_payload(310000))
    assert error is None and rows is not None and rows
    assert seed == 310000 and pair_index == 0
    assert all(r["seed"] == 310000 and r["pair_index"] == 0 for r in rows)


def test_worker_失败局_剔除并上报():
    """非法卡组（无基础宝可梦）→ rows=None + 错误文本（不抛出、不猜）。"""
    _seed, _idx, rows, error = _run_one_collect(
        _collect_payload(310001, deck_a=[energy()] * 60))
    assert rows is None and error is not None
    assert "基础宝可梦" in error


# ── 批量驱动 ──────────────────────────────────────────────

def test_种子区间_pair_i区间():
    """pair i → [seed_start + i×games_per_pair, +games_per_pair)（matrix 惯例）。"""
    assert collect_seed_range(0, 10, 300000) == range(300000, 300010)
    assert collect_seed_range(3, 10, 300000) == range(300030, 300040)


def test_pair文件名_无路径非法字符():
    assert pair_filename(0, "喷火龙 大比鸟", "多龙巴鲁托 黑夜魔灵") == \
        "pair-0-喷火龙_大比鸟x多龙巴鲁托_黑夜魔灵.jsonl"
    name = pair_filename(1, 'a/b\\c:d*e?f"g<h>i|j', "x")
    assert not any(ch in name for ch in '\\/:*?"<>| ')


def test_run_collect_串并一致_产物逐行相同(tmp_path):
    """workers=1 vs 2：同参数两跑，配对文件名与文件字节逐一全等。"""
    prepared = [_stub_pair(0), _stub_pair(1)]
    out_serial, out_parallel = tmp_path / "serial", tmp_path / "parallel"
    s = run_collect(prepared, games_per_pair=8, seed_start=310000,
                    out_dir=out_serial, workers=1)
    p = run_collect(prepared, games_per_pair=8, seed_start=310000,
                    out_dir=out_parallel, workers=2)
    assert [x.filename for x in s] == [x.filename for x in p]
    for xs, xp in zip(s, p, strict=True):
        assert (xs.games, xs.rows, xs.failed) == (xp.games, xp.rows, xp.failed) == (8, xs.rows, 0)
        assert (out_serial / xs.filename).read_bytes() == \
            (out_parallel / xp.filename).read_bytes()


def test_run_collect_种子区间与行结构(tmp_path):
    prepared = [_stub_pair(0), _stub_pair(1)]
    out = tmp_path / "out"
    summaries = run_collect(prepared, games_per_pair=10, seed_start=310000,
                            out_dir=out, workers=1)
    assert [x.filename for x in summaries] == [
        "pair-0-测试A0x测试B0.jsonl", "pair-1-测试A1x测试B1.jsonl"]
    for summary in summaries:
        lines = (out / summary.filename).read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
        assert len(rows) == summary.rows
        lo, hi = 310000 + summary.pair_index * 10, 310000 + (summary.pair_index + 1) * 10
        for row in rows:
            assert row["pair_index"] == summary.pair_index
            assert lo <= row["seed"] < hi
            # 落盘 JSON 经 sort_keys（tune 轨迹惯例）——键集合对拍，键序以
            # FEATURE_NAMES 为准（内存侧 collector 行保序，训练时按清单重排）
            assert set(row["features"]) == set(FEATURE_NAMES)
            assert set(row) == {"pair_index", "seed", "turn", "player",
                                "features", "action", "label"}
            # 行内禁止非确定量（无墙钟/时间戳字段）
            assert not any("time" in k or "wall" in k for k in row)


def test_run_collect_失败局剔除计数(tmp_path):
    """坏配对全部失败：文件仍落盘（0 行），failed 计数上报。"""
    bad = PreparedPair(
        assignment=PairAssignment(index=0, archetype_a="坏", archetype_b="好",
                                  deck_id_a="stub:bad", deck_id_b="stub:b"),
        deck_a=[energy()] * 60, deck_b=deck60(), card_effects={}, warnings=())
    (summary,) = run_collect([bad], games_per_pair=3, seed_start=310000,
                             out_dir=tmp_path / "out", workers=1)
    assert (summary.games, summary.rows, summary.failed) == (3, 0, 3)
    assert (tmp_path / "out" / summary.filename).read_text(encoding="utf-8") == ""


def test_run_collect_确定性_同参两跑字节全等(tmp_path):
    prepared = [_stub_pair(0)]
    a = tmp_path / "a"
    b = tmp_path / "b"
    run_collect(prepared, games_per_pair=6, seed_start=310000, out_dir=a, workers=1)
    run_collect(prepared, games_per_pair=6, seed_start=310000, out_dir=b, workers=1)
    assert (a / "pair-0-测试A0x测试B0.jsonl").read_bytes() == \
        (b / "pair-0-测试A0x测试B0.jsonl").read_bytes()


# ── CLI 端到端（真实池冒烟，无本机 db 时跳过）──────────────

_DB_PATH = Path("C:/Vibe Project/Pokearena/data/ptcg-cn.db")


@pytest.mark.skipif(not _DB_PATH.exists(), reason="本机无 ptcg-cn.db")
def test_cli_collect_features_真实池端到端(tmp_path):
    """target-pool.v1 前三个 archetype（3 配对）× 2 局：3 个 JSONL + schema 校验。"""
    full = yaml.safe_load(Path("config/target-pool.v1.yml").read_text(encoding="utf-8"))
    mini = dict(full, decks=full["decks"][:3])
    pool_path = tmp_path / "pool.yml"
    pool_path.write_text(yaml.safe_dump(mini, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "m11"
    rc = cli_main(["collect-features", "--pool", str(pool_path),
                   "--games-per-pair", "2", "--seed-start", "320000",
                   "--out", str(out), "--workers", "1", "--db", str(_DB_PATH)])
    assert rc == 0
    files = sorted(out.glob("pair-*.jsonl"))
    assert len(files) == 3  # 3 个 archetype → 3 个无向配对
    total_rows = 0
    for f in files:
        rows = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        total_rows += len(rows)
        for row in rows:
            assert set(row) == {"pair_index", "seed", "turn", "player",
                                "features", "action", "label"}
            assert set(row["features"]) == set(FEATURE_NAMES)
            assert row["label"] in (0.0, 0.5, 1.0)
    assert total_rows > 0
