"""task 045：TuneDef 调优定义（Pydantic 强校验，不猜纪律同 ExperimentDef）。"""

import pytest

from battlefrontier.tune.defn import TuneDef, load_tune

VALID_YAML = """\
name: tune-smoke
pool: config/target-pool.v1.yml
pairs:
  - [沙奈朵, 喷火龙 大比鸟]
  - [沙奈朵, 猛雷鼓 厄诡椪]
games_per_pair: 20
split_seed: 20261011
algorithm: coordinate
max_rounds: 1
noise_threshold: 0.01
"""


def _write(tmp_path, text: str = VALID_YAML):
    p = tmp_path / "tune.yml"
    p.write_text(text, encoding="utf-8")
    return p


def test_合法定义装载(tmp_path):
    defn = load_tune(_write(tmp_path))
    assert defn.name == "tune-smoke"
    assert defn.pool == "config/target-pool.v1.yml"
    assert defn.pairs == [("沙奈朵", "喷火龙 大比鸟"), ("沙奈朵", "猛雷鼓 厄诡椪")]
    assert defn.games_per_pair == 20
    assert defn.split_seed == 20261011
    assert defn.algorithm == "coordinate"
    assert defn.max_rounds == 1
    assert defn.noise_threshold == pytest.approx(0.01)


def test_默认值_正式粗扫配置():
    defn = TuneDef(name="t", pool="p.yml", games_per_pair=100)
    assert defn.split_seed == 0
    assert defn.holdout_size == 12
    assert defn.algorithm == "coordinate"
    assert defn.max_rounds == 3                      # D-T3：最多 3 轮
    assert defn.noise_threshold == pytest.approx(0.01)  # D-T2：默认 1.0pts
    assert defn.pairs is None                        # 缺省 = 全量分层划分


@pytest.mark.parametrize("patch", [
    "bogus_field: 1\n",        # 未知字段（不猜）
    "algorithm: annealing\n",  # 未知算法
    "games_per_pair: 0\n",     # 局数非正
    "games_per_pair: 1001\n",  # 超 CRN 种子区间宽 1000（相邻配对种子会撞）
    "holdout_size: 0\n",       # 划分比例非法
    "max_rounds: 0\n",
    "max_rounds: 4\n",         # D-T3 上限 3 轮
    "noise_threshold: -0.1\n",
])
def test_非法字段_显式报错(tmp_path, patch):
    base = "name: t\npool: p.yml\ngames_per_pair: 20\n"
    with pytest.raises((ValueError, TypeError)):
        load_tune(_write(tmp_path, base + patch))


def test_pairs_非法对_不猜(tmp_path):
    base = "name: t\npool: p.yml\ngames_per_pair: 20\npairs:\n"
    with pytest.raises(ValueError, match="相同"):
        load_tune(_write(tmp_path, base + "  - [沙奈朵, 沙奈朵]\n"))
    with pytest.raises(ValueError, match="重复"):
        load_tune(_write(tmp_path, base + "  - [沙奈朵, 喷火龙 大比鸟]\n"
                                          "  - [喷火龙 大比鸟, 沙奈朵]\n"))


def test_定义非映射_显式报错(tmp_path):
    with pytest.raises(TypeError):
        load_tune(_write(tmp_path, "- 1\n- 2\n"))
