"""task 072：v2 池矩阵实验定义展开（不连库、不跑局）。"""

from battlefrontier.data.pool import load_target_pool
from battlefrontier.runner.experiment import expand_matrix, load_experiment


def test_v2_pool_matrix_is_36_pairs_of_500() -> None:
    defn = load_experiment("experiments/v2-calibration.example.yml")
    assert defn.matrix is not None
    pool = load_target_pool(defn.matrix.pool)
    assert len(pool.decks) == 9
    subs = expand_matrix(defn, pool)
    assert len(subs) == 36
    assert subs[0].games == 500
    assert subs[0].decks is not None
    assert subs[0].decks.a.source == "db"
    assert subs[0].decks.a.deck_id.startswith("mik_moe:")
    assert subs[0].seed_start == 200000
    assert subs[1].seed_start == 200500
    names = " ".join(s.name for s in subs)
    assert "v2-calibration::" in subs[0].name
    assert "N的索罗亚克" in names
    assert "电电虫Box" in names


def test_v2_smoke_matrix_is_one_game_per_pair() -> None:
    defn = load_experiment("experiments/v2-calibration-smoke.example.yml")
    pool = load_target_pool(defn.matrix.pool)
    subs = expand_matrix(defn, pool)
    assert len(subs) == 36
    assert all(s.games == 1 for s in subs)
    assert subs[0].seed_start == 900000
    assert subs[35].seed_start == 900035
    seeds = [s.seed_start for s in subs]
    assert seeds == sorted(seeds)
    assert len(set(seeds)) == 36
