"""task 155 WP2：采集 v3（D-062-1 纪律延续）——header 钉清单 + 位置行紧凑格式。

验收口径见 `tasks/task 155.md`：v3 文件首行 header（type/format/feature_names，
词表随池钉进文件自包含）；数据行 features 为位置对齐 float list（560 维 dict
键名重复落盘 ≈ 50GB+，位置格式压到 ~1/4）；header 宽度与数据行宽度不符显式
ValueError（不猜）；`--feature-set` 缺省 v1 行为逐位不变（v1 回归锚，与
tests/test_collect.py 既有锚互补）；串并一致（workers=1 vs 2 字节全等）。

词表口径 = `build_card_vocab`（卡池卡组卡名去重 + 字典序）；stub 词表手工
给出 deck60 全部卡名（妙蛙种子/妙蛙草/小火龙/基本能量），与 v3 特征层
词表外 ValueError 纪律对齐。
"""

import json
from pathlib import Path

import pytest
import yaml
from helpers import deck60, main_state

from battlefrontier.agent.collect import FeatureCollector
from battlefrontier.agent.eval_features import eval_v3_names, feature_vector_v3
from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.cli import main as cli_main
from battlefrontier.engine.actions import Action
from battlefrontier.runner.collect import (
    _run_one_collect,
    read_collect_v3,
    run_collect,
)
from battlefrontier.runner.experiment import _unique_docs
from battlefrontier.tune.fitness import PairAssignment, PreparedPair

_STUB_VOCAB = tuple(sorted({"妙蛙种子", "妙蛙草", "小火龙", "基本能量"}))


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"测试A{index}",
                                  archetype_b=f"测试B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


def _collect_payload(seed: int, pair_index: int = 0, *, v3: bool = False) -> dict:
    pair = _stub_pair(pair_index)
    payload = {
        "deck_a": [c.model_dump(mode="json") for c in pair.deck_a],
        "deck_b": [c.model_dump(mode="json") for c in pair.deck_b],
        "card_effects": [d.model_dump(mode="json")
                         for d in _unique_docs(pair.card_effects.values())],
        "seed": seed,
        "pair_index": pair_index,
    }
    if v3:
        payload["feature_set"] = "v3"
        payload["card_vocab"] = list(_STUB_VOCAB)
    return payload


# ── collector v3 单局 ─────────────────────────────────────

def test_collector_v3_位置行宽度与round_trip():
    """v3 行 features = 位置 list（宽度 = len(eval_v3_names(vocab))）；
    按 header 名序还原 dict 与 feature_vector_v3 逐位相等。"""
    view = main_state().visible_state(0)
    c = FeatureCollector(feature_set="v3", card_vocab=_STUB_VOCAB)
    c.on_decision(view, 0, Action(kind="end_turn"))
    (row,) = c.finish(winner=0, is_draw=False)
    names = eval_v3_names(_STUB_VOCAB)
    assert set(row) == {"turn", "player", "features", "action", "label"}
    assert isinstance(row["features"], list)
    assert len(row["features"]) == len(names)
    assert all(isinstance(v, float) for v in row["features"])
    restored = dict(zip(names, row["features"], strict=True))
    assert restored == feature_vector_v3(view, _STUB_VOCAB)


def test_collector_v3_行结构其余字段与v1一致():
    """turn/player/action/label 结构与 v1 完全相同（只 features 表示变）。"""
    view = main_state().visible_state(0)
    act = Action(kind="end_turn")
    v1 = FeatureCollector()
    v3 = FeatureCollector(feature_set="v3", card_vocab=_STUB_VOCAB)
    for c in (v1, v3):
        c.on_decision(view, 0, act)
        c.on_decision(view, 1, act)
    r1, r3 = v1.finish(winner=0, is_draw=False), v3.finish(winner=0, is_draw=False)
    assert len(r1) == len(r3) == 2
    for a, b in zip(r1, r3, strict=True):
        assert (a["turn"], a["player"], a["action"], a["label"]) == \
            (b["turn"], b["player"], b["action"], b["label"])


def test_collector_非法feature_set_显式报错():
    with pytest.raises(ValueError, match="feature_set"):
        FeatureCollector(feature_set="v2")


def test_collector_v3缺词表_显式报错():
    with pytest.raises(ValueError, match="card_vocab"):
        FeatureCollector(feature_set="v3")


def test_collector_v1默认与显式v1_逐位一致():
    """缺省 = 显式 v1（传了 card_vocab 也忽略）：行逐位全等、features 为 dict。"""
    view = main_state().visible_state(0)
    act = Action(kind="end_turn")
    collectors = [FeatureCollector(),
                  FeatureCollector(feature_set="v1"),
                  FeatureCollector(feature_set="v1", card_vocab=_STUB_VOCAB)]
    for c in collectors:
        c.on_decision(view, 0, act)
    rows = [c.finish(winner=1, is_draw=False) for c in collectors]
    assert rows[0] == rows[1] == rows[2]
    assert tuple(rows[0][0]["features"]) == FEATURE_NAMES


# ── worker ────────────────────────────────────────────────

def test_worker_v3_payload_位置行():
    _seed, _idx, rows, error = _run_one_collect(_collect_payload(310000, v3=True))
    assert error is None and rows
    names = eval_v3_names(_STUB_VOCAB)
    for row in rows:
        assert isinstance(row["features"], list)
        assert len(row["features"]) == len(names)


def test_worker_v1_payload_字典行不变():
    """payload 不带 feature_set：v1 字典行（既有行为逐位不变）。"""
    _seed, _idx, rows, error = _run_one_collect(_collect_payload(310000))
    assert error is None and rows
    assert all(tuple(r["features"]) == FEATURE_NAMES for r in rows)


# ── 批量驱动：header + 位置行 + 宽度校验 ──────────────────

def test_run_collect_v3_header行钉清单(tmp_path):
    """首行 = {"type":"header","format":"bf-collect-v3","feature_names":[...]}，
    feature_names 与 eval_v3_names(vocab) 逐一相等；数据行宽度对齐。"""
    (summary,) = run_collect([_stub_pair(0)], games_per_pair=2, seed_start=310000,
                             out_dir=tmp_path / "out", workers=1,
                             feature_set="v3", card_vocab=_STUB_VOCAB)
    lines = (tmp_path / "out" / summary.filename).read_text(
        encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    assert header["type"] == "header"
    assert header["format"] == "bf-collect-v3"
    assert header["feature_names"] == list(eval_v3_names(_STUB_VOCAB))
    names = header["feature_names"]
    rows = [json.loads(line) for line in lines[1:] if line.strip()]
    assert len(rows) == summary.rows > 0
    for row in rows:
        assert set(row) == {"pair_index", "seed", "turn", "player",
                            "features", "action", "label"}
        assert isinstance(row["features"], list)
        assert len(row["features"]) == len(names)
        # 位置行还原 dict：键序 = header 名序（round-trip 自包含）
        restored = dict(zip(names, row["features"], strict=True))
        assert tuple(restored) == eval_v3_names(_STUB_VOCAB)


def test_run_collect_v3_首行即header_无额外字节锚(tmp_path):
    """v3 文件首行必须可 json 解析为 header（不存在前置空行/字节）。"""
    (summary,) = run_collect([_stub_pair(0)], games_per_pair=1, seed_start=310000,
                             out_dir=tmp_path / "out", workers=1,
                             feature_set="v3", card_vocab=_STUB_VOCAB)
    raw = (tmp_path / "out" / summary.filename).read_bytes()
    first_newline = raw.index(b"\n")
    header = json.loads(raw[:first_newline].decode("utf-8"))
    assert header["type"] == "header" and header["format"] == "bf-collect-v3"


def test_read_collect_v3_宽度不符_显式报错(tmp_path):
    """数据行 features 宽度 ≠ header 名数：显式 ValueError（不猜）。"""
    (summary,) = run_collect([_stub_pair(0)], games_per_pair=1, seed_start=310000,
                             out_dir=tmp_path / "out", workers=1,
                             feature_set="v3", card_vocab=_STUB_VOCAB)
    path = tmp_path / "out" / summary.filename
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    lines[1]["features"] = lines[1]["features"][:-1]  # 篡改：宽度 -1
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                            for r in lines), encoding="utf-8")
    with pytest.raises(ValueError, match="宽度"):
        read_collect_v3(path)


def test_read_collect_v3_非header首行_显式报错(tmp_path):
    """v1 文件（无 header）喂 v3 读取：显式 ValueError（不猜，不臆造名序）。"""
    (summary,) = run_collect([_stub_pair(0)], games_per_pair=1, seed_start=310000,
                             out_dir=tmp_path / "out", workers=1)
    with pytest.raises(ValueError, match="header"):
        read_collect_v3(tmp_path / "out" / summary.filename)


def test_run_collect_v3_串并一致_字节全等(tmp_path):
    prepared = [_stub_pair(0), _stub_pair(1)]
    s = run_collect(prepared, games_per_pair=4, seed_start=310000,
                    out_dir=tmp_path / "serial", workers=1,
                    feature_set="v3", card_vocab=_STUB_VOCAB)
    p = run_collect(prepared, games_per_pair=4, seed_start=310000,
                    out_dir=tmp_path / "parallel", workers=2,
                    feature_set="v3", card_vocab=_STUB_VOCAB)
    assert [x.filename for x in s] == [x.filename for x in p]
    for xs, xp in zip(s, p, strict=True):
        assert (xs.games, xs.rows, xs.failed) == (xp.games, xp.rows, xp.failed)
        assert (tmp_path / "serial" / xs.filename).read_bytes() == \
            (tmp_path / "parallel" / xp.filename).read_bytes()


# ── v1 回归锚（缺省路径逐位不变）──────────────────────────

def test_v1回归锚_缺省无header且字典行(tmp_path):
    """不传 feature_set：文件无 header 行（首行即数据行），features 为 dict。"""
    (summary,) = run_collect([_stub_pair(0)], games_per_pair=2, seed_start=310000,
                             out_dir=tmp_path / "out", workers=1)
    lines = (tmp_path / "out" / summary.filename).read_text(
        encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert "type" not in first  # 首行是数据行，不是 header
    rows = [json.loads(line) for line in lines if line.strip()]
    # 落盘经 sort_keys（既有惯例）：键序按文件序，键集合对齐 FEATURE_NAMES
    assert all(set(r["features"]) == set(FEATURE_NAMES) for r in rows)


def test_v1回归锚_缺省与显式v1_字节全等(tmp_path):
    """缺省 run_collect 与显式 feature_set="v1"（带 vocab）产物逐字节一致。"""
    prepared = [_stub_pair(0)]
    run_collect(prepared, games_per_pair=4, seed_start=310000,
                out_dir=tmp_path / "default", workers=1)
    run_collect(prepared, games_per_pair=4, seed_start=310000,
                out_dir=tmp_path / "explicit", workers=1,
                feature_set="v1", card_vocab=_STUB_VOCAB)
    name = "pair-0-测试A0x测试B0.jsonl"
    assert (tmp_path / "default" / name).read_bytes() == \
        (tmp_path / "explicit" / name).read_bytes()


def test_run_collect_非法feature_set_显式报错(tmp_path):
    with pytest.raises(ValueError, match="feature_set"):
        run_collect([_stub_pair(0)], games_per_pair=1, seed_start=310000,
                    out_dir=tmp_path / "out", feature_set="v2")
    with pytest.raises(ValueError, match="card_vocab"):
        run_collect([_stub_pair(0)], games_per_pair=1, seed_start=310000,
                    out_dir=tmp_path / "out", feature_set="v3")


# ── CLI ───────────────────────────────────────────────────

def test_cli_collect_features_v3缺db_显式报错(tmp_path):
    """v3 词表构建依赖 db：缺 --db 退出码 1（不静默回落 local 配置）。"""
    rc = cli_main(["collect-features", "--pool", "no-such-pool.yml",
                   "--games-per-pair", "1", "--seed-start", "310000",
                   "--out", str(tmp_path / "out"), "--workers", "1",
                   "--feature-set", "v3"])  # 无 --db
    assert rc == 1


_DB_PATH = Path("C:/Vibe Project/Pokearena/data/ptcg-cn.db")


@pytest.mark.skipif(not _DB_PATH.exists(), reason="本机无 ptcg-cn.db")
def test_cli_collect_features_v3端到端(tmp_path, capsys):
    """mini 池 3 配对 × 2 局 --feature-set v3：首行 header + 词表落账打印。"""
    from battlefrontier.agent.policy_features import build_card_vocab

    full = yaml.safe_load(Path("config/target-pool.v2.yml").read_text(encoding="utf-8"))
    mini = dict(full, decks=full["decks"][:3])
    pool_path = tmp_path / "pool.yml"
    pool_path.write_text(yaml.safe_dump(mini, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "v3"
    rc = cli_main(["collect-features", "--pool", str(pool_path),
                   "--games-per-pair", "2", "--seed-start", "320000",
                   "--out", str(out), "--workers", "1", "--db", str(_DB_PATH),
                   "--feature-set", "v3"])
    assert rc == 0
    vocab = build_card_vocab(pool_path, str(_DB_PATH))
    names = eval_v3_names(vocab)
    files = sorted(out.glob("pair-*.jsonl"))
    assert len(files) == 3
    total = 0
    for f in files:
        lines = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        assert lines[0]["type"] == "header"
        assert lines[0]["format"] == "bf-collect-v3"
        assert lines[0]["feature_names"] == list(names)
        for row in lines[1:]:
            assert isinstance(row["features"], list)
            assert len(row["features"]) == len(names)
        total += len(lines) - 1
    assert total > 0
    printed = capsys.readouterr().out
    assert str(len(vocab)) in printed and vocab[0] in printed
