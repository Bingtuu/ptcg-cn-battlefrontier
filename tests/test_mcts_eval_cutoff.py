"""task 052 WP3：MCTS rollout 浅截断接入验收测试（D-M11-4）。

截断语义（K>0 且评估器已装载 → turn >= root_turn + K 返回评估值）/ 视角映射
（root==行动方→V，≠→1−V）/ K ≥ cap 时 0.5 兜底先行（与纯 cap 对拍一致）/
默认禁用零变化 / 装载失败显式报错 / 评估调用零随机源消耗。

模型资产一律用 save_model 造玩具模型（零权重 + 固定截距），不依赖正式
models/eval-linear-v1.json（后台训练中，内容待定）。
"""

from pathlib import Path

import pytest
from helpers import deck60, engine_at, main_state

from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.agent.mcts import MCTSAgent
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
        meta={"source": "toy", "purpose": "task052-test"},
    )
    save_model(model, path)
    return str(path)


@pytest.fixture()
def toy_evaluator(tmp_path) -> str:
    return _toy_model(tmp_path / "toy.json", intercept=0.7)


def _agent(seed: int = 7, **kwargs) -> MCTSAgent:
    params = {"worlds": 2, "iterations": 4, **kwargs}
    return MCTSAgent(RandomSource(seed), **params)


# ── 截断语义与视角映射（D-M11-4）────────────────────────────


class TestCutoffSemantics:
    def test_截断返回评估值_root等于行动方(self, toy_evaluator) -> None:
        """K=1、state.turn == root_turn + K → 立即截断，root==行动方 → 返回 V=0.7。"""
        engine = engine_at(main_state())  # turn=2, current_player=0
        agent = _agent(eval_cutoff_turns=1, evaluator_path=toy_evaluator)
        work = engine.clone(rng=RandomSource(0))
        v = agent._rollout(work, root_player=0, root_turn=1)
        assert v == 0.7
        assert work.state.turn == 2  # 未行任何一步（截断先行）

    def test_视角映射_root不等于行动方(self, toy_evaluator) -> None:
        """root_player ≠ 截断时刻行动方 → 返回 1−V。"""
        engine = engine_at(main_state())  # turn=2, current_player=0
        agent = _agent(eval_cutoff_turns=1, evaluator_path=toy_evaluator)
        v = agent._rollout(engine.clone(rng=RandomSource(0)), root_player=1, root_turn=1)
        assert v == pytest.approx(1.0 - 0.7)

    def test_截断在行过K回合后触发(self, toy_evaluator) -> None:
        """turn < root_turn + K 时不截断（正常 rollout）；行过后触发。

        turn 是轮计数（双方各行动完一轮 +1）：root_turn == state.turn、K=1 时
        首轮双方行动不截断，进入下一轮（turn=3，行动方回到 root=0）→ 截断，
        root==行动方 → 返回 V=0.7。
        """
        engine = engine_at(main_state())
        agent = _agent(eval_cutoff_turns=1, evaluator_path=toy_evaluator)
        work = engine.clone(rng=RandomSource(0))
        v = agent._rollout(work, root_player=0, root_turn=2)
        assert v == pytest.approx(0.7)
        assert work.state.turn == 3  # 确实行过了一轮才截断（非首轮即截）

    def test_K大于等于cap_与纯cap对拍一致(self, toy_evaluator) -> None:
        """K ≥ rollout_turn_cap：0.5 兜底先行，评估器永不触发——与无评估器的
        纯 cap agent 逐 rollout 结果一致。"""
        engine = engine_at(main_state())
        plain = _agent(rollout_turn_cap=4)
        cutoff = _agent(rollout_turn_cap=4, eval_cutoff_turns=10,
                        evaluator_path=toy_evaluator)
        for root_turn in (2, 1, 0):  # 含「已超 cap」与「行过 cap」两种形态
            v_plain = plain._rollout(engine.clone(rng=RandomSource(11)), 0, root_turn)
            v_cut = cutoff._rollout(engine.clone(rng=RandomSource(11)), 0, root_turn)
            assert v_plain == v_cut

    def test_默认禁用零变化_装载但K为0(self, toy_evaluator) -> None:
        """K=0（默认）即使装载评估器也不截断：与无评估器 rollout 逐一致。"""
        engine = engine_at(main_state())
        plain = _agent()
        loaded = _agent(evaluator_path=toy_evaluator)  # K=0 默认
        for root_turn in (2, 0):
            v_plain = plain._rollout(engine.clone(rng=RandomSource(3)), 0, root_turn)
            v_loaded = loaded._rollout(engine.clone(rng=RandomSource(3)), 0, root_turn)
            assert v_plain == v_loaded

    def test_评估调用零随机源消耗(self, toy_evaluator) -> None:
        """截断求值是纯函数：引擎 rng 与 agent 自带 _rng 状态逐值不变。"""
        engine = engine_at(main_state())
        agent = _agent(eval_cutoff_turns=1, evaluator_path=toy_evaluator)
        work = engine.clone(rng=RandomSource(0))
        rng_state = work.rng.snapshot()
        agent_rng_state = agent._rng.snapshot()
        agent._rollout(work, root_player=0, root_turn=1)
        assert work.rng.snapshot() == rng_state
        assert agent._rng.snapshot() == agent_rng_state

    def test_observe端到端_截断配置搜索合法(self, toy_evaluator) -> None:
        """截断配置完整搜索（determinize + rollout 截断）返回合法行动。"""
        engine = engine_at(main_state())
        legal = engine.legal_actions(0)
        agent = _agent(worlds=2, iterations=6, eval_cutoff_turns=5,
                       evaluator_path=toy_evaluator)
        agent.bind_engine(engine)
        assert agent.observe(engine.state.visible_state(0), legal) in legal


# ── 不猜纪律：装载/参数校验 ─────────────────────────────────


class TestLoadingDiscipline:
    def test_K大于0无评估器路径_显式报错(self) -> None:
        with pytest.raises(ValueError, match="evaluator_path"):
            _agent(eval_cutoff_turns=5)

    def test_评估器文件不存在_显式报错(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            _agent(evaluator_path=str(tmp_path / "nope.json"))

    def test_特征清单不符_显式报错(self, tmp_path) -> None:
        """模型特征清单与 FEATURE_NAMES 不符 → load_model 既有校验报错（不猜）。"""
        model = LinearModel(
            feature_names=("bogus",) + FEATURE_NAMES[1:],
            weights=tuple(0.0 for _ in range(_N + 1)),
            mean=tuple(0.0 for _ in range(_N)),
            std=tuple(1.0 for _ in range(_N)),
            meta={"source": "toy"},
        )
        bad = tmp_path / "bad.json"
        save_model(model, bad)
        with pytest.raises(ValueError, match="特征清单"):
            _agent(evaluator_path=str(bad))

    def test_K为负_显式报错(self, toy_evaluator) -> None:
        with pytest.raises(ValueError, match="eval_cutoff_turns"):
            _agent(eval_cutoff_turns=-1, evaluator_path=toy_evaluator)


# ── 实验定义透传（experiment.py，对齐 card_effects 先例）────────────────────


class TestExperimentPassthrough:
    def test_mcts_params_透传截断参数(self, toy_evaluator) -> None:
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
                    "worlds": 2, "iterations": 5, "eval_cutoff_turns": 10,
                    "evaluator_path": toy_evaluator}),
                b=AgentCfg(type="heuristic"),
            ),
        )
        agents = build_agents(defn, seed=42)
        assert isinstance(agents[0], MCTSAgent)
        assert agents[0].eval_cutoff_turns == 10
        assert agents[0]._evaluator is not None

    def test_mcts_params_未知键仍拒绝(self) -> None:
        from battlefrontier.runner.experiment import AgentCfg

        with pytest.raises(ValueError, match="未知 MCTS 参数"):
            AgentCfg(type="mcts", params={"bogus": 1})

    def test_mcts实验_串并一致_截断配置(self, tmp_path, toy_evaluator) -> None:
        """截断配置实验定义：workers=1 vs 2 逐局一致（确定性回归）。"""
        from battlefrontier.runner.experiment import (
            PreparedExperiment,
            execute_experiment,
            load_experiment,
        )
        from battlefrontier.runner.results_db import ResultsDB

        evaluator_posix = Path(toy_evaluator).as_posix()  # YAML 内反斜杠是转义符
        yaml_text = f"""
name: mcts-cutoff
games: 2
seed_start: 900
decks:
  a: {{source: db, deck_id: "x"}}
  b: {{source: db, deck_id: "y"}}
agents:
  a: {{type: mcts, params: {{worlds: 1, iterations: 2, eval_cutoff_turns: 5,
       evaluator_path: "{evaluator_posix}"}}}}
  b: {{type: mcts, params: {{worlds: 1, iterations: 2}}}}
"""
        yml = tmp_path / "exp.yml"
        yml.write_text(yaml_text, encoding="utf-8")
        defn = load_experiment(yml)
        prep = PreparedExperiment(
            deck_a=deck60(), deck_b=deck60(), card_effects={},
            deck_a_id="stub", deck_b_id="stub", data_version="test")

        def snapshot(db_path, workers: int):
            db = ResultsDB(db_path)
            try:
                exp_id = execute_experiment(
                    prep, defn, db_path, workers=workers, definition_yaml=yaml_text)
                return [(g["seed"], g["winner"], g["is_draw"], g["turns"],
                         g["events_hash"]) for g in db.games(exp_id)]
            finally:
                db.close()

        assert snapshot(tmp_path / "s.db", 1) == snapshot(tmp_path / "p.db", 2)
