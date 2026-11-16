"""task 126：MCTS value_guide 接入验收测试（D-M15-1）。

树内 value 引导（PRD §3 M15 接入点 = UCT 子节点选择公式加 value 项）：
V 展开时一次性求值缓存（root 视角，对手节点翻边同 mean 口径）/ 加权 value_guide_weight
（默认 0.5，验收钉死）/ value_guide=true 必填 evaluator_path（不猜）/ weight=0 = 永不
触发路径（行为门钉零臂：同种子开/关 events_hash 逐局全等）/ 选择阶段零评估器调用
（v_raw 缓存）/ 零随机源消耗。模型资产用 save_model 造玩具模型，不依赖正式资产。

既有 MCTS 测试零改动（只加不改，task 126 验收 5）。
"""

from pathlib import Path

import pytest
from helpers import deck60, engine_at, main_state

from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.agent.mcts import MCTSAgent, _Node
from battlefrontier.engine.actions import Action
from battlefrontier.engine.rng import RandomSource
from battlefrontier.learn.model import LinearModel, save_model

_N = len(FEATURE_NAMES)


def _toy_model(path, intercept: float = 0.7) -> str:
    """零权重 + 固定截距的玩具线性评估器（predict 恒返回 intercept）。"""
    model = LinearModel(
        feature_names=FEATURE_NAMES,
        weights=tuple([0.0] * _N + [intercept]),
        mean=tuple(0.0 for _ in range(_N)),
        std=tuple(1.0 for _ in range(_N)),
        meta={"source": "toy", "purpose": "task126-test"},
    )
    save_model(model, path)
    return str(path)


@pytest.fixture()
def toy_evaluator(tmp_path) -> str:
    return _toy_model(tmp_path / "toy.json", intercept=0.7)


def _agent(seed: int = 7, **kwargs) -> MCTSAgent:
    params = {"worlds": 2, "iterations": 4, **kwargs}
    return MCTSAgent(RandomSource(seed), **params)


def _mk_action(tag: str) -> Action:
    """测试专用 Action 实例（_ucb_select 不读 Action 内容，只需可哈希/可比较）。"""
    return Action(kind=f"test_{tag}")


def _mk_node(player: int, visits: int, wins: float, v_raw=None) -> _Node:
    node = _Node(player, [])
    node.visits = visits
    node.wins = wins
    node.v_raw = v_raw
    return node


# ── 接线语义（D-M15-1）────────────────────────────────────────


class TestGuideWiring:
    def test_value_guide无评估器_显式报错(self) -> None:
        with pytest.raises(ValueError, match="evaluator_path"):
            _agent(value_guide=True)

    def test_weight为负_显式报错(self, toy_evaluator) -> None:
        with pytest.raises(ValueError, match="value_guide_weight"):
            _agent(value_guide=True, value_guide_weight=-0.1,
                   evaluator_path=toy_evaluator)

    def test_默认关_零变化(self, toy_evaluator) -> None:
        """默认 value_guide=False：构造不报错、不装载也可（无 evaluator 时）。"""
        agent = _agent()
        assert agent.value_guide is False
        assert agent.value_guide_weight == 0.5

    def test_ucb选择含value项_同访问同均值选V高者(self, toy_evaluator) -> None:
        """两个孩子 visits/wins 相同（exploration 与 mean 相同）→ 选 v_raw 高者。"""
        agent = _agent(value_guide=True, value_guide_weight=0.5,
                       evaluator_path=toy_evaluator)
        parent = _mk_node(player=0, visits=100, wins=50.0)
        a_low, a_high = _mk_action("low"), _mk_action("high")
        parent.children[a_low] = _mk_node(1, 10, 5.0, v_raw=0.2)
        parent.children[a_high] = _mk_node(1, 10, 5.0, v_raw=0.8)
        assert agent._ucb_select(parent, root_player=0) == a_high

    def test_value项加权生效(self, toy_evaluator) -> None:
        """weight=0.5 时 0.6 的 V 差可翻转 0.05 的 mean 差（(0.8-0.2)*0.5=0.3 > 0.05）。"""
        agent = _agent(value_guide=True, value_guide_weight=0.5,
                       evaluator_path=toy_evaluator)
        parent = _mk_node(player=0, visits=100, wins=50.0)
        a_mean, a_guide = _mk_action("mean"), _mk_action("guide")
        # mean 差 0.05（5.5/10 vs 5.0/10），guide 差 0.3
        parent.children[a_mean] = _mk_node(1, 10, 5.5, v_raw=0.2)
        parent.children[a_guide] = _mk_node(1, 10, 5.0, v_raw=0.8)
        assert agent._ucb_select(parent, root_player=0) == a_guide

    def test_对手节点value项翻边(self, toy_evaluator) -> None:
        """node.player ≠ root_player：guide 项同 mean 取 1−v（对 root 坏 = 对 mover 好）。"""
        agent = _agent(value_guide=True, value_guide_weight=0.5,
                       evaluator_path=toy_evaluator)
        parent = _mk_node(player=1, visits=100, wins=50.0)  # 对手节点
        a_low, a_high = _mk_action("low"), _mk_action("high")
        # root 视角 v_raw：0.2 / 0.8；对手节点翻边后 0.8 / 0.2 → 选 v_raw 低者
        parent.children[a_low] = _mk_node(0, 10, 5.0, v_raw=0.2)
        parent.children[a_high] = _mk_node(0, 10, 5.0, v_raw=0.8)
        assert agent._ucb_select(parent, root_player=0) == a_low

    def test_weight为零_不触发value项(self, toy_evaluator) -> None:
        """weight=0：选择退回纯 UCB（v_raw 差异无影响）。"""
        agent = _agent(value_guide=True, value_guide_weight=0.0,
                       evaluator_path=toy_evaluator)
        parent = _mk_node(player=0, visits=100, wins=50.0)
        a_first, a_second = _mk_action("first"), _mk_action("second")
        parent.children[a_first] = _mk_node(1, 10, 5.0, v_raw=0.9)
        parent.children[a_second] = _mk_node(1, 10, 5.0, v_raw=0.1)
        # 同 mean 同 exploration：严格大于才更新 → 保留先展开者
        assert agent._ucb_select(parent, root_player=0) == a_first

    def test_vraw缺失_贡献为零(self, toy_evaluator) -> None:
        """v_raw=None（guide 关闭段/未求值）value 项贡献为零：与 v_raw=0.0
        完全等价（同分 → 严格大于保留先展开者）。"""
        agent = _agent(value_guide=True, value_guide_weight=0.5,
                       evaluator_path=toy_evaluator)
        parent = _mk_node(player=0, visits=100, wins=50.0)
        a_first, a_second = _mk_action("first"), _mk_action("second")
        parent.children[a_first] = _mk_node(1, 10, 5.0, v_raw=None)
        parent.children[a_second] = _mk_node(1, 10, 5.0, v_raw=0.0)
        assert agent._ucb_select(parent, root_player=0) == a_first

    def test_展开时求值缓存_选择阶段零评估器调用(self, toy_evaluator,
                                               monkeypatch) -> None:
        """V 只在 expansion 求一次：选择阶段 predict 不被调用（v_raw 缓存纪律）。"""
        engine = engine_at(main_state())
        agent = _agent(worlds=1, iterations=8, value_guide=True,
                       value_guide_weight=0.5, evaluator_path=toy_evaluator)
        agent.bind_engine(engine)
        calls = {"n": 0}
        real_predict = agent._evaluator_predict

        def spy(view):
            calls["n"] += 1
            return real_predict(view)

        monkeypatch.setattr(agent, "_evaluator_predict", spy)
        legal = engine.legal_actions(0)
        agent.observe(engine.state.visible_state(0), legal)
        # 每展开节点恰好一次求值；选择/回传阶段零调用（迭代数 > 展开数 ⇒ 若未缓存
        # 调用数会随迭代数增长；此处上限断言 = 调用数 ≤ 节点展开数 ≤ 迭代数）
        assert 0 < calls["n"] <= 8

    def test_求值零随机源消耗(self, toy_evaluator, monkeypatch) -> None:
        """expansion 求值纯函数：引擎 rng 不变；weight=0 臂与关闭臂的
        agent _rng 消耗流逐值一致（guide 不引入任何随机源消费）。"""
        engine = engine_at(main_state())
        engine_rng = engine.rng.snapshot()
        agent_off = _agent(worlds=1, iterations=6)
        agent_zero = _agent(worlds=1, iterations=6, value_guide=True,
                            value_guide_weight=0.0,
                            evaluator_path=toy_evaluator)
        agent_off.bind_engine(engine)
        agent_zero.bind_engine(engine)
        legal = engine.legal_actions(0)
        a_off = agent_off.observe(engine.state.visible_state(0), legal)
        a_zero = agent_zero.observe(engine.state.visible_state(0), legal)
        assert engine.rng.snapshot() == engine_rng  # 引擎随机源零消费
        assert agent_zero._rng.snapshot() == agent_off._rng.snapshot()
        assert a_zero == a_off  # 钉零臂与关闭臂决策一致

    def test_observe端到端_引导配置搜索合法(self, toy_evaluator) -> None:
        engine = engine_at(main_state())
        agent = _agent(worlds=2, iterations=6, value_guide=True,
                       value_guide_weight=0.5, evaluator_path=toy_evaluator)
        agent.bind_engine(engine)
        legal = engine.legal_actions(0)
        assert agent.observe(engine.state.visible_state(0), legal) in legal


# ── 行为门（预注册口径：weight=0 vs off，events_hash 逐局全等）───────────────


class TestBehaviorGate:
    def test_weight零臂与关闭_逐局events_hash全等(self, tmp_path,
                                                  toy_evaluator) -> None:
        from battlefrontier.runner.experiment import (
            PreparedExperiment,
            execute_experiment,
            load_experiment,
        )
        from battlefrontier.runner.results_db import ResultsDB

        evaluator_posix = Path(toy_evaluator).as_posix()

        def run_yaml(params_yaml: str, db_name: str):
            yaml_text = f"""
name: vg-behavior
games: 2
seed_start: 950
decks:
  a: {{source: db, deck_id: "x"}}
  b: {{source: db, deck_id: "y"}}
agents:
  a: {{type: mcts, params: {params_yaml}}}
  b: {{type: heuristic}}
"""
            yml = tmp_path / f"{db_name}.yml"
            yml.write_text(yaml_text, encoding="utf-8")
            defn = load_experiment(yml)
            prep = PreparedExperiment(
                deck_a=deck60(), deck_b=deck60(), card_effects={},
                deck_a_id="stub", deck_b_id="stub", data_version="test")
            db_path = tmp_path / f"{db_name}.db"
            db = ResultsDB(db_path)
            try:
                exp_id = execute_experiment(
                    prep, defn, db_path, workers=1, definition_yaml=yaml_text)
                return [(g["seed"], g["winner"], g["is_draw"], g["turns"],
                         g["events_hash"]) for g in db.games(exp_id)]
            finally:
                db.close()

        off = run_yaml('{worlds: 1, iterations: 3}', "off")
        zero = run_yaml(
            f'{{worlds: 1, iterations: 3, value_guide: true, value_guide_weight: 0.0,'
            f' evaluator_path: "{evaluator_posix}"}}', "zero")
        assert zero == off

    def test_权重零_展开不求值(self, toy_evaluator, monkeypatch) -> None:
        """weight=0 是「永不触发路径」：expansion 也不调用 predict。"""
        engine = engine_at(main_state())
        agent = _agent(worlds=1, iterations=6, value_guide=True,
                       value_guide_weight=0.0, evaluator_path=toy_evaluator)
        agent.bind_engine(engine)
        calls = {"n": 0}
        real_predict = agent._evaluator_predict

        def spy(view):
            calls["n"] += 1
            return real_predict(view)

        monkeypatch.setattr(agent, "_evaluator_predict", spy)
        agent.observe(engine.state.visible_state(0), engine.legal_actions(0))
        assert calls["n"] == 0
        assert agent.last_consideration is not None


# ── 实验定义透传（experiment.py 词表白名单同步，task 126 验收 4）─────────────


class TestExperimentPassthrough:
    def test_value_guide参数_透传(self, toy_evaluator) -> None:
        from battlefrontier.runner.experiment import (
            AgentCfg,
            AgentSides,
            ExperimentDef,
            build_agents,
        )

        defn = ExperimentDef(
            name="t", games=1,
            decks={"a": {"source": "db", "deck_id": "x"},
                   "b": {"source": "db", "deck_id": "y"}},
            agents=AgentSides(
                a=AgentCfg(type="mcts", params={
                    "worlds": 2, "iterations": 5, "value_guide": True,
                    "value_guide_weight": 0.25, "evaluator_path": toy_evaluator}),
                b=AgentCfg(type="heuristic"),
            ),
        )
        agents = build_agents(defn, seed=42)
        assert isinstance(agents[0], MCTSAgent)
        assert agents[0].value_guide is True
        assert agents[0].value_guide_weight == 0.25
        assert agents[0]._evaluator is not None

    def test_value_guide词表外键_仍拒绝(self) -> None:
        from battlefrontier.runner.experiment import AgentCfg

        with pytest.raises(ValueError, match="未知 MCTS 参数"):
            AgentCfg(type="mcts", params={"value_guide bogus": 1})
