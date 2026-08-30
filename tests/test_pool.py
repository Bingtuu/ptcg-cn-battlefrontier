"""task 024：目标卡组池锁定资产（config/target-pool.v1.yml）loader 强校验。"""

from __future__ import annotations

import pytest

from battlefrontier.data.pool import TargetPool, load_target_pool


def test_load_real_pool():
    pool = load_target_pool("config/target-pool.v1.yml")
    assert isinstance(pool, TargetPool)
    assert len(pool.decks) == 9
    assert pool.decks[0].archetype == "沙奈朵"
    assert pool.decks[0].deck_id == "mik_moe:644634"
    assert pool.query["window"] == "2026-05-30..2026-08-28"
    assert pool.query["snapshot"] == "standard-2026-07-16"
    # WUR 降序
    wurs = [d.wur for d in pool.decks]
    assert wurs == sorted(wurs, reverse=True)


@pytest.mark.parametrize("bad, match", [
    # 缺口径字段
    ({"version": 1, "locked_at": "x", "query": {"window": "w"},
      "decks": [{"archetype": "a", "wur": 0.1, "n": 5, "deck_id": "s:1"}]}, "query"),
    # deck_id 格式错
    ({"version": 1, "locked_at": "x",
      "query": {"window": "w", "division": "master", "basis": "cn", "min_n": 5,
                "n_tournaments": 6, "snapshot": "s", "name_group_rules_hash": "h"},
      "decks": [{"archetype": "a", "wur": 0.1, "n": 5, "deck_id": "bad"}]}, "deck_id"),
    # 卡组为空
    ({"version": 1, "locked_at": "x",
      "query": {"window": "w", "division": "master", "basis": "cn", "min_n": 5,
                "n_tournaments": 6, "snapshot": "s", "name_group_rules_hash": "h"},
      "decks": []}, "decks"),
    # WUR 非降序
    ({"version": 1, "locked_at": "x",
      "query": {"window": "w", "division": "master", "basis": "cn", "min_n": 5,
                "n_tournaments": 6, "snapshot": "s", "name_group_rules_hash": "h"},
      "decks": [{"archetype": "a", "wur": 0.1, "n": 5, "deck_id": "s:1"},
                {"archetype": "b", "wur": 0.2, "n": 5, "deck_id": "s:2"}]}, "降序"),
])
def test_malformed_pool(tmp_path, bad, match):
    import yaml

    p = tmp_path / "pool.yml"
    p.write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_target_pool(p)
