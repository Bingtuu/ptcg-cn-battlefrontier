"""换卡敏感性：variants 实验定义 + 分组执行测试（task 023，PRD §9）。"""

from __future__ import annotations

import pytest
from helpers import deck60

from battlefrontier.runner.experiment import (
    ExperimentDef,
    apply_swaps,
    execute_group,
    load_experiment,
)
from battlefrontier.runner.results_db import ResultsDB

VALID_YAML = """\
name: swap-test
games: 2
seed_start: 100
decks:
  a: {source: file, path: "decklists/x.txt"}
  b: {source: file, path: "decklists/x.txt"}
variants:
  - name: v1
    swaps:
      - {side: a, out: 妙蛙种子, out_count: 2, in: 小火龙, in_count: 2}
"""


def _write(tmp_path, text: str = VALID_YAML):
    p = tmp_path / "exp.yml"
    p.write_text(text, encoding="utf-8")
    return p


# ── 定义校验（不猜：显式报错）─────────────────────────────

def test_load_with_variants(tmp_path):
    defn = load_experiment(_write(tmp_path))
    assert defn.variants[0].name == "v1"
    swap = defn.variants[0].swaps[0]
    assert swap.side == "a" and swap.out == "妙蛙种子" and swap.out_count == 2
    assert swap.in_ == "小火龙" and swap.in_count == 2


def test_no_variants_default_empty(tmp_path):
    text = "\n".join(VALID_YAML.splitlines()[:6]) + "\n"
    defn = load_experiment(_write(tmp_path, text))
    assert defn.variants == []


@pytest.mark.parametrize("bad", [
    # Σout != Σin（卡组不再是 60）
    VALID_YAML.replace("in_count: 2", "in_count: 1"),
    # variant 重名
    VALID_YAML + "  - name: v1\n    swaps:\n"
                 "      - {side: a, out: 小火龙, out_count: 1, in: 妙蛙种子, in_count: 1}\n",
    # 未知 side
    VALID_YAML.replace("side: a", "side: c"),
    # swaps 空列表
    VALID_YAML.replace("    swaps:\n"
                       "      - {side: a, out: 妙蛙种子, out_count: 2, in: 小火龙, in_count: 2}\n",
                       "    swaps: []\n"),
])
def test_invalid_variants(tmp_path, bad):
    with pytest.raises(ValueError):
        load_experiment(_write(tmp_path, bad))


# ── apply_swaps（纯函数，stub 卡组可测）────────────────────

def test_apply_swaps_changes_counts():
    deck = deck60()
    defn = load_experiment_from_text()
    swap = defn.variants[0].swaps[0]
    in_card = next(c for c in deck if c.name == "小火龙")
    new_deck = apply_swaps(deck, [swap], {"小火龙": in_card})
    assert len(new_deck) == 60
    assert sum(1 for c in new_deck if c.name == "妙蛙种子") == 18
    assert sum(1 for c in new_deck if c.name == "小火龙") == 22


def load_experiment_from_text():
    return ExperimentDef.model_validate({
        "name": "t", "games": 1,
        "decks": {"a": {"source": "file", "path": "x"},
                  "b": {"source": "file", "path": "x"}},
        "variants": [{"name": "v1", "swaps": [
            {"side": "a", "out": "妙蛙种子", "out_count": 2,
             "in": "小火龙", "in_count": 2}]}],
    })


def test_apply_swaps_insufficient_out():
    defn = load_experiment_from_text()
    swap = defn.variants[0].swaps[0].model_copy(update={"out_count": 25})
    with pytest.raises(ValueError, match="存量不足"):
        apply_swaps(deck60(), [swap], {})


def test_apply_swaps_unknown_in_card():
    defn = load_experiment_from_text()
    with pytest.raises(ValueError, match="未解析"):
        apply_swaps(deck60(), defn.variants[0].swaps, {})


# ── 分组执行（同种子区间配对 + 确定性 + meta）──────────────

def _preps() -> list:
    from battlefrontier.runner.experiment import PreparedExperiment

    defn = load_experiment_from_text()
    base = deck60()
    in_card = next(c for c in base if c.name == "小火龙")
    variant_deck = apply_swaps(base, defn.variants[0].swaps, {"小火龙": in_card})
    mk = lambda da, db, aid, bid: PreparedExperiment(
        deck_a=da, deck_b=db, card_effects={},
        deck_a_id=aid, deck_b_id=bid, data_version="test")
    return [mk(base, base, "stub", "stub"),
            mk(variant_deck, base, "stub [variant:v1]", "stub")]


def _snapshots(db_path, exp_ids):
    db = ResultsDB(db_path)
    try:
        return [[(g["seed"], g["winner"], g["is_draw"], g["turns"], g["events_hash"],
                  g["deck_a_id"]) for g in db.games(e)] for e in exp_ids]
    finally:
        db.close()


def test_execute_group_paired_and_deterministic(tmp_path):
    defn = load_experiment_from_text().model_copy(update={"games": 4})
    ids_a = execute_group(defn, _preps(), tmp_path / "a.db", definition_yaml="y")
    ids_b = execute_group(defn, _preps(), tmp_path / "b.db", definition_yaml="y")
    assert len(ids_a) == 2  # [baseline, v1]
    snap_a, snap_b = _snapshots(tmp_path / "a.db", ids_a), _snapshots(tmp_path / "b.db", ids_b)
    assert snap_a == snap_b  # 同定义同种子区间重跑逐局一致
    # 配对：两组实验同种子区间
    assert [s[0] for s in snap_a[0]] == [s[0] for s in snap_a[1]]
    # variant 组 A 卡组已换（deck id 标注落 games 行）
    assert snap_a[1][0][-1] == "stub [variant:v1]"


def test_execute_group_experiment_meta(tmp_path):
    defn = load_experiment_from_text().model_copy(update={"name": "grp", "games": 1})
    ids = execute_group(defn, _preps(), tmp_path / "m.db", definition_yaml="y")
    db = ResultsDB(tmp_path / "m.db")
    try:
        base, var = db.experiment(ids[0]), db.experiment(ids[1])
    finally:
        db.close()
    assert base["group_name"] == "grp" and base["variant"] == ""
    assert var["group_name"] == "grp" and var["variant"] == "v1"
