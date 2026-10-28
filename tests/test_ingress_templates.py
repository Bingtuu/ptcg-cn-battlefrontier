"""task 073：三种卡组入口的复制即可跑模板（不连库、不跑局）。"""

from pathlib import Path

from battlefrontier.data.pool import load_target_pool
from battlefrontier.runner.experiment import load_experiment, parse_decklist


def test_three_ingress_templates_load() -> None:
    deck = load_experiment("experiments/templates/deck-id.example.yml")
    assert deck.decks is not None
    assert deck.decks.a.source == "db"
    assert deck.decks.a.deck_id == "mik_moe:676344"
    assert deck.decks.b.deck_id == "mik_moe:687339"
    assert deck.games == 1

    pooled = load_experiment("experiments/templates/pool-yaml.example.yml")
    assert pooled.matrix is not None
    assert pooled.matrix.pool.endswith("target-pool.v2.yml")
    assert pooled.matrix.games_per_pair == 1
    assert len(load_target_pool(pooled.matrix.pool).decks) == 9

    named = load_experiment("experiments/templates/name-count.example.yml")
    assert named.decks is not None
    assert named.decks.a.source == "file"
    assert named.decks.b.path == named.decks.a.path
    text = Path(named.decks.a.path).read_text(encoding="utf-8")
    assert parse_decklist(text)[0] == (4, "沙奈朵ex")
    assert sum(n for n, _ in parse_decklist(text)) != 60
