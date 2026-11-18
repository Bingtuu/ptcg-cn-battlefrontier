"""task 127：联赛注册表 schema（LeagueDef）。

校验纪律：≥2 agents 且 id 唯一；≥1 deck；seed_stride ≥ games_per_cell；
agent type/params 白名单「不猜」校验直接继承 AgentCfg。
"""

import pytest

from battlefrontier.runner.league import load_league

VALID_YAML = """
name: league-smoke
seed_start: 800000
seed_stride: 1000
games_per_cell: 20
decks:
  - {source: db, deck_id: "mik_moe:644634"}
agents:
  - {id: heuristic-base, type: heuristic}
  - {id: mcts-2x50, type: mcts, params: {worlds: 2, iterations: 50}}
"""


def _write(tmp_path, text: str = VALID_YAML):
    p = tmp_path / "league.yml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_valid(tmp_path):
    lg = load_league(_write(tmp_path))
    assert lg.name == "league-smoke"
    assert lg.seed_start == 800000 and lg.seed_stride == 1000
    assert lg.games_per_cell == 20
    assert len(lg.decks) == 1 and lg.decks[0].deck_id == "mik_moe:644634"
    assert [a.id for a in lg.agents] == ["heuristic-base", "mcts-2x50"]
    assert lg.agents[1].cfg.type == "mcts"
    assert lg.agents[1].cfg.params == {"worlds": 2, "iterations": 50}


def test_agent_id_unique(tmp_path):
    bad = VALID_YAML.replace(
        "- {id: mcts-2x50, type: mcts, params: {worlds: 2, iterations: 50}}",
        "- {id: heuristic-base, type: random}")
    with pytest.raises(ValueError, match="唯一"):
        load_league(_write(tmp_path, bad))


def test_at_least_two_agents(tmp_path):
    bad = VALID_YAML.split("  - {id: mcts-2x50")[0]  # 砍掉第二个 agent
    with pytest.raises(ValueError, match="2"):
        load_league(_write(tmp_path, bad))


def test_at_least_one_deck(tmp_path):
    bad = VALID_YAML.replace("decks:\n  - {source: db, deck_id: \"mik_moe:644634\"}\n",
                             "decks: []\n")
    with pytest.raises(ValueError, match="deck"):
        load_league(_write(tmp_path, bad))


def test_seed_stride_must_cover_games(tmp_path):
    bad = VALID_YAML.replace("seed_stride: 1000", "seed_stride: 10")
    with pytest.raises(ValueError, match="stride"):
        load_league(_write(tmp_path, bad))


@pytest.mark.parametrize("bad_agent", [
    "- {id: x1, type: minimax}",                          # 未知 type
    "- {id: x1, type: mcts, params: {time_limit: 5}}",    # mcts 未知参数（不猜）
    "- {id: x1, type: heuristic, params: {w_hindsight: 1}}",  # heuristic 未知参数
    "- {type: random}",                                    # 缺 id
])
def test_agent_cfg_inherits_whitelist(tmp_path, bad_agent):
    bad = (VALID_YAML
           .replace("- {id: heuristic-base, type: heuristic}", bad_agent)
           .replace("- {id: mcts-2x50, type: mcts, params: {worlds: 2, iterations: 50}}",
                    "- {id: x2, type: random}"))
    with pytest.raises((ValueError, TypeError)):
        load_league(_write(tmp_path, bad))
