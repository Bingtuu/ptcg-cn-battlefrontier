"""task 045：评估协议（D-T2）——配对分层划分 / CRN 种子派生 / 批量跑局与聚合。

聚合口径单测全部用注入的 GameOutcome，不打真局；串并一致性与搜索级确定性
用 stub 卡组（tests/helpers deck60）走真实 play_game 小预算验证。
"""

import dataclasses

import pytest
from helpers import deck60

from battlefrontier.data.pool import PoolEntry, TargetPool
from battlefrontier.tune.fitness import (
    GameOutcome,
    PairAssignment,
    PairSplit,
    PreparedPair,
    aggregate,
    check_coverage,
    execute_plan,
    pair_seed_range,
    select_pairs,
    split_pairs,
)
from battlefrontier.tune.space import default_vector

QUERY = {k: "x" for k in ("window", "division", "basis", "min_n", "n_tournaments",
                          "snapshot", "name_group_rules_hash")}


def _pool9() -> TargetPool:
    return TargetPool(version=1, locked_at="t", query=dict(QUERY), decks=[
        PoolEntry(archetype=f"宝{i}", en_archetype=f"E{i}", wur=1.0 - i * 0.01,
                  n=10, deck_id=f"mik_moe:{i}")
        for i in range(9)])


# ── 配对分层划分 ─────────────────────────────────────────

def test_划分确定性_同种子同划分():
    pool = _pool9()
    s1 = split_pairs(pool, split_seed=12345, holdout_size=12)
    s2 = split_pairs(pool, split_seed=12345, holdout_size=12)
    assert s1 == s2
    assert len(s1.train) == 24 and len(s1.holdout) == 12
    # 36 无向配对全覆盖且不重复
    idx = sorted(p.index for p in (*s1.train, *s1.holdout))
    assert idx == list(range(36))
    # 配对内容来自池（index 与 matchup_pairs 序一致）
    pairs = pool.matchup_pairs()
    for p in (*s1.train, *s1.holdout):
        a, b = pairs[p.index]
        assert (p.archetype_a, p.archetype_b) == (a.archetype, b.archetype)
        assert (p.deck_id_a, p.deck_id_b) == (a.deck_id, b.deck_id)


def test_划分分层覆盖_九_archetype_双侧():
    """9 个 archetype 在训练集与 holdout 各自至少出现于一个配对（不满足显式报错）。"""
    pool = _pool9()
    split = split_pairs(pool, split_seed=12345, holdout_size=12)
    names = {d.archetype for d in pool.decks}
    for side in (split.train, split.holdout):
        covered = {p.archetype_a for p in side} | {p.archetype_b for p in side}
        assert covered == names


def test_check_coverage_缺侧显式报错():
    a = PairAssignment(0, "宝0", "宝1", "mik_moe:0", "mik_moe:1")
    b = PairAssignment(1, "宝0", "宝2", "mik_moe:0", "mik_moe:2")
    c = PairAssignment(2, "宝1", "宝2", "mik_moe:1", "mik_moe:2")
    # train 全覆盖，holdout 缺 宝1
    with pytest.raises(ValueError, match="宝1"):
        check_coverage(PairSplit(train=(a, c), holdout=(b,)), {"宝0", "宝1", "宝2"})
    # holdout 全覆盖，train 缺 宝2
    with pytest.raises(ValueError, match="宝2"):
        check_coverage(PairSplit(train=(a,), holdout=(b, c)), {"宝0", "宝1", "宝2"})


@pytest.mark.parametrize("holdout", [0, 4, 32, 36, 40])
def test_划分比例非法_显式报错(holdout):
    """holdout 须 ≥1 且两侧配对数 ×2 足以覆盖 9 archetype（4×2=8<9 / 32→train 4 同理）。"""
    with pytest.raises(ValueError):
        split_pairs(_pool9(), split_seed=1, holdout_size=holdout)


def test_显式配子集_冒烟模式():
    """pairs 显式指定（冒烟/调试）：train=所选（池序），holdout 空，index 保留池序锚点。"""
    pool = _pool9()
    split = select_pairs(pool, [("宝2", "宝5"), ("宝0", "宝1")])
    assert split.holdout == ()
    assert [p.index for p in split.train] == [0, 17]  # 池序：(0,1)=0；(2,5)=8+7+(5-3)=17
    assert [(p.archetype_a, p.archetype_b) for p in split.train] == [
        ("宝0", "宝1"), ("宝2", "宝5")]


def test_显式配子集_未知_archetype_不猜():
    pool = _pool9()
    with pytest.raises(ValueError, match="不存在"):
        select_pairs(pool, [("宝0", "不存在的卡组")])


def test_显式配子集_同archetype对_不猜():
    pool = _pool9()
    with pytest.raises(ValueError):
        select_pairs(pool, [("宝0", "宝0")])


# ── CRN 种子派生 ─────────────────────────────────────────

def test_CRN_种子派生():
    """pair i → 种子区间 [200000+i×1000, +N)，跨候选同区间（同一配对同一种子）。"""
    assert pair_seed_range(0, 100) == range(200000, 200100)
    assert pair_seed_range(3, 100) == range(203000, 203100)
    assert pair_seed_range(35, 20) == range(235000, 235020)
    # 跨候选：同一 pair 同一 N 区间恒定（CRN 由派生函数纯函数性保证）
    assert pair_seed_range(3, 100) == pair_seed_range(3, 100)
    # 相邻配对区间不重叠（N ≤ 1000 保障）
    assert pair_seed_range(0, 1000).stop == pair_seed_range(1, 1).start


def test_种子派生_N超区间宽_不猜():
    with pytest.raises(ValueError, match="1000"):
        pair_seed_range(0, 1001)


# ── 聚合口径（注入模拟结果，不打真局）─────────────────────

def _assignments() -> tuple[PairAssignment, PairAssignment]:
    return (
        PairAssignment(index=0, archetype_a="宝0", archetype_b="宝1",
                       deck_id_a="mik_moe:0", deck_id_b="mik_moe:1"),
        PairAssignment(index=5, archetype_a="宝0", archetype_b="宝5",
                       deck_id_a="mik_moe:0", deck_id_b="mik_moe:5"),
    )


def _outcome(pair_index: int, seed: int, winner, is_draw=False, failed=False) -> GameOutcome:
    return GameOutcome(pair_index=pair_index, seed=seed, winner=winner,
                       is_draw=is_draw, failed=failed)


def _outcomes_10(pair_index: int, results: list) -> list[GameOutcome]:
    """results: 每局 winner 标记（0=A 胜 / 1=B 胜 / "draw" / "fail"）。"""
    out = []
    for j, r in enumerate(results):
        seed = pair_seed_range(pair_index, 10)[j]
        if r == "draw":
            out.append(_outcome(pair_index, seed, None, is_draw=True))
        elif r == "fail":
            out.append(_outcome(pair_index, seed, None, failed=True))
        else:
            out.append(_outcome(pair_index, seed, r))
    return out


def test_聚合口径_分母决定局_平局失败剔除():
    pairs = _assignments()
    vec = default_vector()
    # pair 0：6 A胜 / 2 B胜 / 1 平 / 1 失败 → decided 8，wr = 6/8
    # pair 5：5 A胜 / 5 B胜 → wr = 0.5
    outcomes = (
        _outcomes_10(0, [0, 0, 0, 0, 0, 0, 1, 1, "draw", "fail"])
        + _outcomes_10(5, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    )
    result = aggregate(vec, pairs, games_per_pair=10, outcomes=outcomes,
                       wall_seconds=1.5)
    assert result.vector == vec
    assert result.wall_seconds == 1.5
    p0, p5 = result.pairs
    assert p0.pair_index == 0 and p0.games == 10
    assert (p0.decided, p0.wins_a, p0.draws, p0.failed) == (8, 6, 1, 1)
    assert p0.winrate == pytest.approx(6 / 8)
    assert (p0.seed_start, p0.seed_end) == (200000, 200009)
    assert (p5.seed_start, p5.seed_end) == (205000, 205009)
    assert p5.winrate == pytest.approx(0.5)
    # fitness = 训练集平均胜率（各配对简单平均）
    assert result.fitness == pytest.approx((6 / 8 + 0.5) / 2)


def test_聚合_全平局_pair_胜率0_不除零():
    """decided=0 时胜率记 0.0（对齐 report/winrate 口径）。"""
    pairs = _assignments()
    outcomes = _outcomes_10(0, ["draw"] * 10) + _outcomes_10(5, [0] * 10)
    result = aggregate(default_vector(), pairs, 10, outcomes, 0.0)
    assert result.pairs[0].decided == 0 and result.pairs[0].winrate == 0.0
    assert result.fitness == pytest.approx((0.0 + 1.0) / 2)


def test_聚合_局数不齐或种子错位_显式报错():
    pairs = _assignments()
    full = _outcomes_10(0, [0] * 10) + _outcomes_10(5, [0] * 10)
    with pytest.raises(ValueError, match="缺局"):
        aggregate(default_vector(), pairs, 10, full[1:], 0.0)       # 少一局
    with pytest.raises(ValueError, match="多局"):
        aggregate(default_vector(), pairs, 10, full + [full[0]], 0.0)  # 多一局
    bad = [dataclasses.replace(o, seed=o.seed + 7) for o in full]      # 种子错位
    with pytest.raises(ValueError, match="种子"):
        aggregate(default_vector(), pairs, 10, bad, 0.0)


# ── 批量跑局：串并一致（stub 卡组真实 play_game，小预算）────

def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"A{index}",
                                  archetype_b=f"B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


def _strip_wall(result):
    return dataclasses.replace(result, wall_seconds=0.0)


def test_execute_plan_串并一致_workers4_vs_1():
    """worker 内按同一种子重建 Agent：workers=4 与 workers=1 结果逐字段一致。"""
    prepared = [_stub_pair(0), _stub_pair(5)]
    vec = default_vector()
    vec["w_damage"] = 10.0
    serial = execute_plan(prepared, vec, games_per_pair=6, workers=1)
    parallel = execute_plan(prepared, vec, games_per_pair=6, workers=4)
    assert _strip_wall(serial) == _strip_wall(parallel)
    # 有效性自查：无失败局（放任不管对拍假绿）
    assert all(p.failed == 0 for p in serial.pairs)
    assert all(p.games == 6 for p in serial.pairs)


def test_execute_plan_候选在A侧_默认在B侧():
    """镜像参数下 A/B 同策略：胜率应落在 [0,1]（口径烟测，钉死侧位接线）。"""
    prepared = [_stub_pair(0)]
    result = execute_plan(prepared, default_vector(), games_per_pair=4, workers=1)
    assert 0.0 <= result.fitness <= 1.0
    assert result.pairs[0].wins_a + result.pairs[0].draws <= 4
