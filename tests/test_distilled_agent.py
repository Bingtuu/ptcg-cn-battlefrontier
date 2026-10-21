"""task 059 · M12 WP3：DistilledAgent 接入验收测试（D-M12-5）。

- DistilledAgent：state 30 维（FEATURE_NAMES）⊕ 每条合法行动 26 维
  （ACTION_FEATURE_NAMES）→ numpy 前向 score = W2·relu(W1·x+b1)+b2 → 掩码
  argmax（ties 取首索引，全程无随机源——蒸馏学生天然确定性）；打分只覆盖
  legal_actions，非法行动永不被选。
- 注册三处逐项实证：AGENT_TYPES 含 distilled / _build_one 显式分支命中
  （policy_path 缺失或装载失败显式报错，不落 RandomAgent 兜底）/
  AgentCfg._check_agent distilled params 白名单（仅 policy_path，str）。
- agreement 重放：cfg 带 type: distilled 走 DistilledAgent 分支，分母口径
  与 M11 v1 一致（run_agreement 同一份 DENOMINATOR_KINDS）。
- 自身确定性：同实验定义同种子区间两跑 (seed, winner, is_draw, turns,
  events_hash) 逐局全等（test_experiment 既有确定性口径）。
- CLI：agreement --policy 端到端 + 与 MCTS 预算 flags 互斥（退出码 1）。
- task 062 WP2c（D-062-4）：特征版本分派——meta.feature_version（缺省 v1）；
  v2 走 POLICY_STATE_NAMES / policy_action_names(card_vocab) 特征（卡身份维度
  真实参与前向，argmax 随身份翻转），v1 路径逐位不变；v2 缺 card_vocab 显式报错。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import deck60, inst, main_state

from battlefrontier.agent.action_features import (
    ACTION_FEATURE_NAMES,
    ACTION_KINDS,
)
from battlefrontier.agent.distilled import DistilledAgent
from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.agent.policy_features import (
    POLICY_STATE_NAMES,
    policy_action_names,
)
from battlefrontier.cli import main as cli_main
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef, Supertype
from battlefrontier.learn.policy_model import (
    PolicyModel,
    load_policy_model,
    save_policy_model,
)
from battlefrontier.runner.agreement import (
    classify_row,
    config_fingerprint,
    run_agreement,
)
from battlefrontier.runner.experiment import (
    AGENT_TYPES,
    AgentCfg,
    PreparedExperiment,
    _build_one,
    execute_experiment,
    load_experiment,
)
from battlefrontier.runner.results_db import ResultsDB
from battlefrontier.runner.snapshot import (
    SnapshotFile,
    load_snapshot_file,
    run_collect_snapshots,
)
from battlefrontier.tune.fitness import PairAssignment, PreparedPair

_IN_DIM = len(FEATURE_NAMES) + len(ACTION_FEATURE_NAMES)  # 56 = 状态 30 + 行动 26


def _toy_model(prefer_kind: str = "attack") -> PolicyModel:
    """玩具打分机：only-kind 偏好——w1 单行只在 kind_<prefer> 位（行动段
    偏移 len(FEATURE_NAMES)）置 1，score = relu(kind_onehot)（b2=0）。"""
    w1_row = [0.0] * _IN_DIM
    w1_row[len(FEATURE_NAMES) + ACTION_KINDS.index(prefer_kind)] = 1.0
    return PolicyModel(
        hidden=1,
        weights={"w1": (tuple(w1_row),), "b1": (0.0,),
                 "w2": ((1.0,),), "b2": (0.0,)},
        meta={"source": "toy"})


def _zero_model() -> PolicyModel:
    """全零打分机：全部行动同分 0.0（ties 口径测试用）。"""
    return PolicyModel(
        hidden=1,
        weights={"w1": (tuple(0.0 for _ in range(_IN_DIM)),), "b1": (0.0,),
                 "w2": ((0.0,),), "b2": (0.0,)},
        meta={"source": "toy-zero"})


def _save_toy(tmp_path, model: PolicyModel | None = None, name: str = "toy.json"):
    path = tmp_path / name
    save_policy_model(model if model is not None else _toy_model(), path)
    return path


def _legal_main() -> list[Action]:
    """合成 main 阶段合法行动列（结构化字段即可，action_features 不查引擎）。"""
    return [
        Action(kind="attach_energy", iid=51, target_iid=1),
        Action(kind="attack", attack_index=0),
        Action(kind="end_turn"),
    ]


# ── 掩码 argmax（DistilledAgent.observe）─────────────────────────


class TestMaskedArgmax:
    def test_偏好行动命中(self) -> None:
        view = main_state().visible_state(0)
        agent = DistilledAgent(_toy_model("attack"))
        legal = _legal_main()
        chosen = agent.observe(view, legal)
        assert chosen == Action(kind="attack", attack_index=0)

    def test_非法行动永不选(self) -> None:
        """打分只覆盖 legal_actions：偏好类（attack）不在合法列时绝不返回它。"""
        view = main_state().visible_state(0)
        agent = DistilledAgent(_toy_model("attack"))
        legal = [Action(kind="attach_energy", iid=51, target_iid=1),
                 Action(kind="end_turn")]
        for _ in range(3):
            chosen = agent.observe(view, legal)
            assert chosen in legal
            assert chosen.kind != "attack"

    def test_返回必在合法列(self) -> None:
        """多种偏好模型下返回值恒为 legal_actions 成员（掩码口径）。"""
        view = main_state().visible_state(0)
        legal = _legal_main()
        for kind in ("attach_energy", "attack", "end_turn"):
            assert DistilledAgent(_toy_model(kind)).observe(view, legal) in legal

    def test_ties取首索引(self) -> None:
        """全零模型全行动同分 → argmax 平手取 legal_actions 序首（确定性）。"""
        view = main_state().visible_state(0)
        legal = _legal_main()
        assert DistilledAgent(_zero_model()).observe(view, legal) == legal[0]

    def test_唯一合法行动早退(self) -> None:
        view = main_state().visible_state(0)
        only = Action(kind="end_turn")
        assert DistilledAgent(_toy_model("attack")).observe(view, [only]) == only

    def test_无合法行动显式报错(self) -> None:
        with pytest.raises(ValueError, match="无合法行动"):
            DistilledAgent(_toy_model()).observe(main_state().visible_state(0), [])

    def test_权重形状不符显式报错(self) -> None:
        """构造侧形状校验（不猜）：w1 列数 ≠ 56 直接拒。"""
        bad = PolicyModel(
            hidden=1,
            weights={"w1": ((1.0, 2.0),), "b1": (0.0,),
                     "w2": ((1.0,),), "b2": (0.0,)},
            meta={})
        with pytest.raises(ValueError, match="形状"):
            DistilledAgent(bad)


class TestObserveDeterminism:
    def test_同模型同view重复observe一致(self) -> None:
        view = main_state().visible_state(0)
        legal = _legal_main()
        agent = DistilledAgent(_toy_model("attach_energy"))
        first = agent.observe(view, legal)
        assert agent.observe(view, legal) == first
        assert DistilledAgent(_toy_model("attach_energy")).observe(view, legal) == first


# ── task 062 WP2c：v2 特征分派 ─────────────────────────────

_V2_VOCAB = ("博士的研究", "宝可梦交替")  # 小词表，字典序钉死
_V2_IN_DIM = len(POLICY_STATE_NAMES) + len(policy_action_names(_V2_VOCAB))


def _trainer(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype=Supertype.TRAINER)


def _v2_identity_model(prefer_card: str) -> PolicyModel:
    """v2 玩具打分机：单行 w1 仅在 card_<prefer_card> 列置 1（行动段偏移
    len(POLICY_STATE_NAMES) + len(ACTION_FEATURE_NAMES)），score = relu(onehot)。"""
    w1_row = [0.0] * _V2_IN_DIM
    w1_row[len(POLICY_STATE_NAMES) + len(ACTION_FEATURE_NAMES)
           + _V2_VOCAB.index(prefer_card)] = 1.0
    return PolicyModel(
        hidden=1,
        weights={"w1": (tuple(w1_row),), "b1": (0.0,),
                 "w2": ((1.0,),), "b2": (0.0,)},
        meta={"feature_version": "v2"},
        card_vocab=_V2_VOCAB)


class TestDistilledV2:
    def test_身份维度真实参与前向(self) -> None:
        """同状态两行动仅卡身份不同（同 kind play_trainer、结构化字段同形）：
        w1 对应 card_* 列权重不同 → argmax 随身份翻转。"""
        state = main_state(p0_extra_hand=(
            inst(52, _trainer("博士的研究")),
            inst(53, _trainer("宝可梦交替"))))
        view = state.visible_state(0)
        legal = [Action(kind="play_trainer", iid=52),
                 Action(kind="play_trainer", iid=53)]
        prefer_a = DistilledAgent(_v2_identity_model("博士的研究"))
        prefer_b = DistilledAgent(_v2_identity_model("宝可梦交替"))
        assert prefer_a.observe(view, legal) == legal[0]
        assert prefer_b.observe(view, legal) == legal[1]

    def test_v2权重形状不符显式报错(self) -> None:
        """v2 输入维度 = 36 + (26 + 词表大小)；w1 列数不符显式报错（不猜）。"""
        bad = PolicyModel(
            hidden=1,
            weights={"w1": (tuple(0.0 for _ in range(_V2_IN_DIM - 1)),),
                     "b1": (0.0,), "w2": ((1.0,),), "b2": (0.0,)},
            meta={"feature_version": "v2"},
            card_vocab=_V2_VOCAB)
        with pytest.raises(ValueError, match="形状"):
            DistilledAgent(bad)

    def test_v2缺card_vocab显式报错(self) -> None:
        """meta feature_version=v2 但 card_vocab=None → ValueError（不猜）。"""
        model = PolicyModel(
            hidden=1,
            weights={"w1": (tuple(0.0 for _ in range(_IN_DIM)),), "b1": (0.0,),
                     "w2": ((1.0,),), "b2": (0.0,)},
            meta={"feature_version": "v2"})
        assert model.card_vocab is None
        with pytest.raises(ValueError, match="card_vocab"):
            DistilledAgent(model)

    def test_v2行动特征每行动只算一次(self, monkeypatch) -> None:
        """性能护栏（task 062 WP4 matrix 实测暴露）：policy_action_features
        调用次数 == len(legal_actions)——曾在 [f(a)[name] for name in names]
        内层循环按 138 个键名重复调用同一纯函数（137 observe 实测 129444 次
        调用、~47ms/observe，matrix 慢 ~10 倍）。"""
        import battlefrontier.agent.distilled as distilled_mod

        calls = 0
        real = distilled_mod.policy_action_features

        def spy(a, view, vocab):
            nonlocal calls
            calls += 1
            return real(a, view, vocab)

        monkeypatch.setattr(distilled_mod, "policy_action_features", spy)
        state = main_state(p0_extra_hand=(
            inst(52, _trainer("博士的研究")),
            inst(53, _trainer("宝可梦交替"))))
        view = state.visible_state(0)
        legal = [Action(kind="play_trainer", iid=52),
                 Action(kind="play_trainer", iid=53)]
        DistilledAgent(_v2_identity_model("博士的研究")).observe(view, legal)
        assert calls == len(legal)

    def test_未知feature_version显式报错(self) -> None:
        model = PolicyModel(
            hidden=1,
            weights={"w1": (tuple(0.0 for _ in range(_IN_DIM)),), "b1": (0.0,),
                     "w2": ((1.0,),), "b2": (0.0,)},
            meta={"feature_version": "v3"})
        with pytest.raises(ValueError, match="feature_version"):
            DistilledAgent(model)


class TestDistilledV1Unchanged:
    def test_v1资产装载后observe不变(self, tmp_path) -> None:
        """v1 玩具模型 save → load（v1 装载路径，card_vocab None）→ observe
        与装载前逐位一致。"""
        model = _toy_model("attack")
        path = tmp_path / "toy-v1.json"
        save_policy_model(model, path)
        loaded = load_policy_model(path)
        assert loaded.card_vocab is None
        view = main_state().visible_state(0)
        legal = _legal_main()
        assert DistilledAgent(loaded).observe(view, legal) \
            == DistilledAgent(model).observe(view, legal) \
            == Action(kind="attack", attack_index=0)

    def test_v1在库资产可装载可推理(self) -> None:
        """models/policy-m12-v1.json（M12 锚 1 资产）装载 + observe 出合法行动。"""
        model = load_policy_model("models/policy-m12-v1.json")
        assert model.card_vocab is None
        agent = DistilledAgent(model)
        legal = _legal_main()
        assert agent.observe(main_state().visible_state(0), legal) in legal


# ── 注册三处（experiment.py）────────────────────────────────────


class TestRegistration:
    def test_AGENT_TYPES含distilled(self) -> None:
        assert "distilled" in AGENT_TYPES

    def test_白名单过验(self) -> None:
        cfg = AgentCfg(type="distilled", params={"policy_path": "models/x.json"})
        assert cfg.params["policy_path"] == "models/x.json"

    def test_未知params报错(self) -> None:
        with pytest.raises(ValueError, match="未知 distilled 参数"):
            AgentCfg(type="distilled",
                     params={"policy_path": "x.json", "worlds": 2})

    def test_缺policy_path报错(self) -> None:
        with pytest.raises(ValueError, match="policy_path"):
            AgentCfg(type="distilled", params={})

    def test_policy_path非str报错(self) -> None:
        with pytest.raises(ValueError, match="policy_path"):
            AgentCfg(type="distilled", params={"policy_path": 5})

    def test_yaml定义过验(self, tmp_path) -> None:
        model_path = _save_toy(tmp_path)
        text = (
            "name: distilled-smoke\ngames: 1\n"
            "decks:\n"
            "  a: {source: file, path: \"decklists/x.txt\"}\n"
            "  b: {source: file, path: \"decklists/x.txt\"}\n"
            f"agents:\n  a: {{type: distilled, params: {{policy_path: "
            f"'{model_path.as_posix()}'}}}}\n"
        )
        p = tmp_path / "exp.yml"
        p.write_text(text, encoding="utf-8")
        defn = load_experiment(p)
        assert defn.agents.a.type == "distilled"
        assert defn.agents.a.params["policy_path"] == model_path.as_posix()

    def test_build_one命中分支(self, tmp_path) -> None:
        model_path = _save_toy(tmp_path)
        cfg = AgentCfg(type="distilled",
                       params={"policy_path": str(model_path)})
        agent = _build_one(cfg, seed=1, offset=1_000_001)
        assert isinstance(agent, DistilledAgent)

    def test_build_one缺policy_path显式报错(self) -> None:
        """防御纵深：绕过 schema 校验（model_construct）直送 _build_one 也显式报错。"""
        cfg = AgentCfg.model_construct(type="distilled", params={})
        with pytest.raises(ValueError, match="policy_path"):
            _build_one(cfg, seed=1, offset=0)

    def test_build_one装载失败显式报错(self, tmp_path) -> None:
        cfg = AgentCfg(type="distilled",
                       params={"policy_path": str(tmp_path / "不存在.json")})
        with pytest.raises(ValueError, match="装载失败"):
            _build_one(cfg, seed=1, offset=0)
        bad = tmp_path / "bad.json"
        bad.write_text('{"format": "wrong"}', encoding="utf-8")
        cfg = AgentCfg(type="distilled", params={"policy_path": str(bad)})
        with pytest.raises(ValueError, match="装载失败"):
            _build_one(cfg, seed=1, offset=0)


# ── agreement distilled 学生分支 ────────────────────────────────


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"测试A{index}",
                                  archetype_b=f"测试B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


@pytest.fixture(scope="module")
def snapshot_file(tmp_path_factory) -> SnapshotFile:
    """stub 配对教师（1×2 MCTS）小预算快照（test_agreement 同口径）。"""
    out = tmp_path_factory.mktemp("distilled-snapshots")
    (s,) = run_collect_snapshots([_stub_pair(0)], games_per_pair=2,
                                 seed_start=460000, out_dir=out, workers=1,
                                 teacher={"worlds": 1, "iterations": 2,
                                          "rollout_turn_cap": 50})
    assert s.rows > 0
    return load_snapshot_file(out / s.filename)


class TestAgreementDistilled:
    def test_distilled学生走run_agreement出报告(self, snapshot_file, tmp_path) -> None:
        model_path = _save_toy(tmp_path)
        student = {"type": "distilled", "policy_path": str(model_path)}
        report = run_agreement(snapshot_file, student)
        assert report["denominator"] > 0
        assert report["config"] == student
        assert report["config_fingerprint"] == config_fingerprint(student)
        assert 0.0 <= report["agreement_rate"] <= 1.0
        assert report["agree"] == sum(1 for d in report["rows"] if d["agree"])

    def test_分母口径与M11v1一致(self, snapshot_file, tmp_path) -> None:
        """分母 = main 阶段 attack/play_trainer/end_turn 行数（run_agreement 同一份
        classify_row）；distilled 学生不改口径。"""
        model_path = _save_toy(tmp_path)
        student = {"type": "distilled", "policy_path": str(model_path)}
        report = run_agreement(snapshot_file, student)
        rows = snapshot_file.rows
        assert report["denominator"] == sum(
            1 for r in rows if classify_row(r) == "denominator")
        ap = report["appendix"]
        assert (report["denominator"] + ap["excluded_non_main"]
                + ap["excluded_other_main"]) == len(rows)

    def test_重放确定性两跑一致(self, snapshot_file, tmp_path) -> None:
        model_path = _save_toy(tmp_path)
        student = {"type": "distilled", "policy_path": str(model_path)}
        assert run_agreement(snapshot_file, student) == \
            run_agreement(snapshot_file, student)

    def test_未知学生type显式报错(self, snapshot_file) -> None:
        with pytest.raises(ValueError, match="未知学生 type"):
            run_agreement(snapshot_file, {"type": "mystery"})

    def test_distilled缺policy_path显式报错(self, snapshot_file) -> None:
        with pytest.raises(ValueError, match="policy_path"):
            run_agreement(snapshot_file, {"type": "distilled"})


# ── distilled 自身确定性（events_hash 两跑全等）───────────────────


def _games_snapshot(db_path, exp_id):
    db = ResultsDB(db_path)
    try:
        return [
            (g["seed"], g["winner"], g["is_draw"], g["turns"], g["events_hash"])
            for g in db.games(exp_id)
        ]
    finally:
        db.close()


class TestSelfDeterminism:
    def test_同种子区间两跑events_hash全等(self, tmp_path) -> None:
        """distilled 双侧镜像（stub 卡组 + 玩具模型）：同定义同种子区间两次独立
        重跑 games 层逐局一致（test_experiment §8.4 同口径）。"""
        model_path = _save_toy(tmp_path)
        yaml_text = (
            "name: distilled-det\ngames: 2\nseed_start: 470000\n"
            "decks:\n"
            "  a: {source: file, path: \"decklists/x.txt\"}\n"
            "  b: {source: file, path: \"decklists/x.txt\"}\n"
            "agents:\n"
            f"  a: {{type: distilled, params: {{policy_path: "
            f"'{model_path.as_posix()}'}}}}\n"
            f"  b: {{type: distilled, params: {{policy_path: "
            f"'{model_path.as_posix()}'}}}}\n"
        )
        p = tmp_path / "exp.yml"
        p.write_text(yaml_text, encoding="utf-8")
        defn = load_experiment(p)
        prep = PreparedExperiment(
            deck_a=deck60(), deck_b=deck60(), card_effects={},
            deck_a_id="stub", deck_b_id="stub", data_version="test")
        snap_a = _games_snapshot(
            tmp_path / "a.db", execute_experiment(prep, defn, tmp_path / "a.db",
                                                  definition_yaml=yaml_text))
        snap_b = _games_snapshot(
            tmp_path / "b.db", execute_experiment(prep, defn, tmp_path / "b.db",
                                                  definition_yaml=yaml_text))
        assert len(snap_a) == 2 and snap_a == snap_b
        # 有效性自查：无失败局（error 行 hash 为空会让对拍假绿）
        assert all(h for *_rest, h in snap_a)


# ── CLI --policy 端到端 ─────────────────────────────────────────


class TestCli:
    def _write_snapshot(self, snapshot_file, tmp_path):
        snap_path = tmp_path / "snap.jsonl"
        rows = [{"record": "header", **snapshot_file.header}] + \
            [{**r, "record": "snapshot"} for r in snapshot_file.rows]
        snap_path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
            + "\n", encoding="utf-8")
        return snap_path

    def test_agreement_cli_policy端到端(self, snapshot_file, tmp_path) -> None:
        snap_path = self._write_snapshot(snapshot_file, tmp_path)
        model_path = _save_toy(tmp_path)
        out = tmp_path / "report.json"
        rc = cli_main(["agreement", str(snap_path),
                       "--policy", str(model_path), "--output", str(out)])
        assert rc == 0
        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["denominator"] > 0
        assert report["config"] == {"type": "distilled",
                                    "policy_path": str(model_path)}

    def test_policy与MCTS预算互斥(self, snapshot_file, tmp_path) -> None:
        snap_path = self._write_snapshot(snapshot_file, tmp_path)
        model_path = _save_toy(tmp_path)
        for extra in (["--worlds", "1"], ["--iterations", "2"],
                      ["--rollout-turn-cap", "30"], ["--eval-cutoff-turns", "5"],
                      ["--evaluator", str(model_path)]):
            rc = cli_main(["agreement", str(snap_path),
                           "--policy", str(model_path), *extra])
            assert rc == 1, extra

    def test_无policy缺MCTS预算显式报错(self, snapshot_file, tmp_path) -> None:
        snap_path = self._write_snapshot(snapshot_file, tmp_path)
        rc = cli_main(["agreement", str(snap_path)])
        assert rc == 1
        rc = cli_main(["agreement", str(snap_path), "--worlds", "1"])
        assert rc == 1

    _SMOKE_MODEL = Path("results/policy-smoke-task058.json")

    @pytest.mark.skipif(not _SMOKE_MODEL.exists(), reason="本机无 task 058 冒烟模型")
    def test_冒烟资产对拍(self, snapshot_file, tmp_path) -> None:
        """task 058 冒烟模型（results/policy-smoke-task058.json，hidden 16）经
        load_policy_model 装载 + DistilledAgent 重放 stub 快照出报告。"""
        smoke = load_policy_model(self._SMOKE_MODEL)
        assert smoke.hidden == 16
        student = {"type": "distilled", "policy_path": str(self._SMOKE_MODEL)}
        report = run_agreement(snapshot_file, student)
        assert report["denominator"] > 0
