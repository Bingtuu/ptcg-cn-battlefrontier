"""task 002：随机源 RandomSource 测试（PRD §6.3 种子确定性）。"""

from battlefrontier.engine.rng import RandomSource


def test_same_seed_same_shuffle_sequence() -> None:
    cards = tuple(range(60))
    a, b = RandomSource(42), RandomSource(42)
    assert a.shuffle(cards) == b.shuffle(cards)
    assert a.shuffle(cards) == b.shuffle(cards)


def test_same_seed_same_coin_flips() -> None:
    a, b = RandomSource(7), RandomSource(7)
    assert [a.flip_coin() for _ in range(20)] == [b.flip_coin() for _ in range(20)]


def test_different_seed_different_result() -> None:
    cards = tuple(range(60))
    assert RandomSource(1).shuffle(cards) != RandomSource(2).shuffle(cards)


def test_snapshot_restore_continues_same_sequence() -> None:
    a = RandomSource(99)
    before = [a.flip_coin() for _ in range(5)]
    snap = a.snapshot()
    continued = [a.flip_coin() for _ in range(5)]

    b = RandomSource(99)
    assert [b.flip_coin() for _ in range(5)] == before
    b.restore(snap)
    assert [b.flip_coin() for _ in range(5)] == continued


def test_shuffle_returns_tuple_and_keeps_source() -> None:
    cards = (1, 2, 3)
    out = RandomSource(0).shuffle(cards)
    assert isinstance(out, tuple) and sorted(out) == [1, 2, 3]
    assert cards == (1, 2, 3)


def test_randbelow_deterministic_and_bounded() -> None:
    a, b = RandomSource(5), RandomSource(5)
    seq_a = [a.randbelow(10) for _ in range(50)]
    seq_b = [b.randbelow(10) for _ in range(50)]
    assert seq_a == seq_b
    assert all(0 <= x < 10 for x in seq_a)
