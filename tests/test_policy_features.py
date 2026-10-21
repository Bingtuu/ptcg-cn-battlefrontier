"""task 058 · M12 WP2：行动特征化 + 快照→样本转换验收测试（D-M12-1/2）。

- 行动 kind 词表 16 类钉死（core.py 15 种 + chooser「choose」——任务书「15 类」
  系漏计 choose，D-M12-1）；特征键序 = kind one-hot 16 + 数值标量 6 +
  目标关系标志 4（Action 结构化字段无 damage/amount/count，D-M12-2）。
- 快照→样本转换（learn/policy_data.py）：重建 GameState → 行动方 visible view
  特征（信息纪律：与 feature_vector(visible_state) 逐一相等）→ 合法行动逐条
  特征化 → 教师 chosen 在合法列内的下标；教师行动不合法显式报错（不猜）。

task 062 WP1（D-062-1/2/3）：v2 特征层（agent/policy_features.py）——
POLICY_STATE_NAMES = FEATURE_NAMES + 弃牌构成 6 维；policy_action_names =
ACTION_FEATURE_NAMES + 卡身份 one-hot（词表序即键序）；resolve_action_card_names
可见视图反查（iid 不可见跳过，attack/retreat = 己方战斗场）。
"""

from __future__ import annotations

import pytest
from helpers import basic, deck60, energy, in_play, inst, main_state

from battlefrontier.agent.action_features import (
    ACTION_FEATURE_NAMES,
    ACTION_KINDS,
    action_features,
)
from battlefrontier.agent.features import FEATURE_NAMES, feature_vector
from battlefrontier.agent.policy_features import (
    POLICY_STATE_NAMES,
    build_card_vocab,
    policy_action_features,
    policy_action_names,
    policy_state_features,
    resolve_action_card_names,
)
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef, Supertype
from battlefrontier.learn.policy_data import (
    PolicySample,
    load_policy_samples,
    row_to_sample,
)
from battlefrontier.runner.snapshot import (
    SnapshotFile,
    load_snapshot_file,
    run_collect_snapshots,
    snapshot_state,
    teacher_action,
)
from battlefrontier.tune.fitness import PairAssignment, PreparedPair

EXPECTED_KINDS = (
    "attach_energy", "attach_tool", "attack", "choose", "confirm_setup",
    "end_turn", "evolve", "place_active", "place_bench", "play_stadium",
    "play_trainer", "promote", "retreat", "shrink_bench", "use_ability",
    "use_stadium",
)

EXPECTED_ACTION_FEATURES = tuple(f"kind_{k}" for k in EXPECTED_KINDS) + (
    "attack_index",
    "has_iid",
    "has_target_iid",
    "has_bench_index",
    "bench_index",
    "n_choices",
    "target_is_own_active",
    "target_is_own_bench",
    "target_is_opp_active",
    "target_is_opp_bench",
)


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"测试A{index}",
                                  archetype_b=f"测试B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


@pytest.fixture(scope="module")
def snapshot_file(tmp_path_factory) -> SnapshotFile:
    """stub 配对教师（1×2 MCTS）小预算快照（test_agreement 同口径）。"""
    out = tmp_path_factory.mktemp("policy-snapshots")
    (s,) = run_collect_snapshots([_stub_pair(0)], games_per_pair=2,
                                 seed_start=440000, out_dir=out, workers=1,
                                 teacher={"worlds": 1, "iterations": 2,
                                          "rollout_turn_cap": 50})
    assert s.rows > 0
    return load_snapshot_file(out / s.filename)


# ── 行动特征（纯函数）────────────────────────────────────────


class TestActionFeatures:
    def test_kind词表钉死(self) -> None:
        assert ACTION_KINDS == EXPECTED_KINDS

    def test_特征键序钉死(self) -> None:
        assert ACTION_FEATURE_NAMES == EXPECTED_ACTION_FEATURES
        assert len(ACTION_FEATURE_NAMES) == 26
        assert len(set(ACTION_FEATURE_NAMES)) == len(ACTION_FEATURE_NAMES)

    def test_kind_onehot逐类命中(self) -> None:
        view = main_state().visible_state(0)
        for kind in ACTION_KINDS:
            feats = action_features(Action(kind=kind), view)
            assert tuple(feats) == ACTION_FEATURE_NAMES
            assert feats[f"kind_{kind}"] == 1.0
            assert sum(feats[f"kind_{k}"] for k in ACTION_KINDS) == 1.0

    def test_未知kind显式报错(self) -> None:
        with pytest.raises(ValueError, match="未知"):
            action_features(Action(kind="hack"), main_state().visible_state(0))

    def test_数值标量(self) -> None:
        view = main_state().visible_state(0)
        feats = action_features(
            Action(kind="choose", attack_index=1, iid=9, target_iid=2,
                   bench_index=3, choices=(5, 6)), view)
        assert feats["attack_index"] == 1.0
        assert feats["has_iid"] == 1.0
        assert feats["has_target_iid"] == 1.0
        assert feats["has_bench_index"] == 1.0
        assert feats["bench_index"] == 3.0
        assert feats["n_choices"] == 2.0
        empty = action_features(Action(kind="end_turn"), view)
        assert empty["attack_index"] == 0.0
        assert empty["has_iid"] == 0.0
        assert empty["has_target_iid"] == 0.0
        assert empty["has_bench_index"] == 0.0
        assert empty["bench_index"] == 0.0
        assert empty["n_choices"] == 0.0

    def test_目标关系标志(self) -> None:
        """target_iid 经行动方 visible view 解析（信息纪律：只看可见区域）。"""
        state = main_state(p1_bench=(in_play(3, basic("小火龙")),))
        p0 = state.players[0].model_copy(
            update={"bench": (in_play(7, basic("小火龙")),)})
        state = state.model_copy(update={"players": (p0, state.players[1])})
        view = state.visible_state(0)
        # main_state：己方 active iid=1 / 对方 active iid=2 / 对方 bench iid=3 /
        # 己方 bench iid=7
        cases = {1: "target_is_own_active", 7: "target_is_own_bench",
                 2: "target_is_opp_active", 3: "target_is_opp_bench"}
        flags = ("target_is_own_active", "target_is_own_bench",
                 "target_is_opp_active", "target_is_opp_bench")
        for iid, hit in cases.items():
            feats = action_features(Action(kind="attach_tool", iid=50, target_iid=iid),
                                    view)
            for f in flags:
                assert feats[f] == (1.0 if f == hit else 0.0), (iid, f)
        # 无 target / target 不在可见在场区（如手牌 iid）→ 全 0
        for action in (Action(kind="play_trainer", iid=50),
                       Action(kind="attach_tool", iid=50, target_iid=999)):
            feats = action_features(action, view)
            assert all(feats[f] == 0.0 for f in flags)


# ── 快照→样本转换 ────────────────────────────────────────────


class TestRowToSample:
    def test_样本结构与信息纪律(self, snapshot_file) -> None:
        """样本 state 特征与 feature_vector(visible_state) 逐一相等（只用行动方
        可见视图）；行动特征与合法行动逐条对拍；教师下标命中教师行动。"""
        row = next(r for r in snapshot_file.rows if r["phase"] == "main")
        sample = row_to_sample(row, pair_index=0,
                               card_effects=snapshot_file.card_effects())
        assert isinstance(sample, PolicySample)
        state = snapshot_state(row)
        view = state.visible_state(row["player"])
        assert sample.state == feature_vector(view)
        assert tuple(sample.state) == FEATURE_NAMES
        engine = GameEngine(RandomSource(row["seed"]),
                            card_effects=snapshot_file.card_effects())
        engine.state = state
        legal = engine.legal_actions(row["player"])
        assert len(sample.actions) == len(legal) == row["n_legal"]
        for feats, action in zip(sample.actions, legal, strict=True):
            assert feats == action_features(action, view)
            assert tuple(feats) == ACTION_FEATURE_NAMES
        assert legal[sample.teacher_index] == teacher_action(row)
        assert (sample.pair_index, sample.seed) == (0, row["seed"])

    def test_教师行动不在合法列显式报错(self, snapshot_file) -> None:
        row = dict(snapshot_file.rows[0])
        row["action"] = {"kind": "attack", "attack_index": 99}
        row["action_kind"] = "attack"
        with pytest.raises(ValueError, match="不在合法行动列"):
            row_to_sample(row, pair_index=0,
                          card_effects=snapshot_file.card_effects())

    def test_全阶段行可转换(self, snapshot_file) -> None:
        """冒烟全量行（含 choice/setup/promote 阶段）逐行转换不炸。"""
        card_effects = snapshot_file.card_effects()
        for row in snapshot_file.rows:
            sample = row_to_sample(row, pair_index=0, card_effects=card_effects)
            assert 0 <= sample.teacher_index < len(sample.actions)


class TestLoadPolicySamples:
    def test_目录载入(self, snapshot_file, tmp_path) -> None:
        import json

        path = tmp_path / "pair-0-测试Ax测试B.jsonl"
        lines = [{"record": "header", **snapshot_file.header}] + \
            [{**r, "record": "snapshot"} for r in snapshot_file.rows]
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in lines)
            + "\n", encoding="utf-8")
        samples = load_policy_samples(tmp_path)
        assert len(samples) == len(snapshot_file.rows)
        assert all(s.pair_index == 0 for s in samples)
        assert len({s.seed for s in samples}) == 2

    def test_空目录显式报错(self, tmp_path) -> None:
        with pytest.raises(ValueError, match=r"pair-\*\.jsonl"):
            load_policy_samples(tmp_path)


# ── task 062 WP1：v2 特征层（卡身份 one-hot + 弃牌构成）──────

VOCAB = ("博士的研究", "基本能量", "沙奈朵ex")

# stub 卡组全卡名词表（deck60：妙蛙种子/妙蛙草/小火龙/基本能量），v2 样本/训练用
STUB_VOCAB = tuple(sorted({c.name for c in deck60()}))


class TestRowToSampleV2:
    """task 062 WP2b：card_vocab 非 None → v2 特征路径；None → v1 逐位不变。"""

    def test_v2样本键序与教师下标(self, snapshot_file) -> None:
        row = next(r for r in snapshot_file.rows if r["phase"] == "main")
        sample = row_to_sample(row, pair_index=0,
                               card_effects=snapshot_file.card_effects(),
                               card_vocab=STUB_VOCAB)
        state = snapshot_state(row)
        view = state.visible_state(row["player"])
        assert tuple(sample.state) == POLICY_STATE_NAMES
        assert sample.state == policy_state_features(view)
        engine = GameEngine(RandomSource(row["seed"]),
                            card_effects=snapshot_file.card_effects())
        engine.state = state
        legal = engine.legal_actions(row["player"])
        assert len(sample.actions) == len(legal) == row["n_legal"]
        for feats, action in zip(sample.actions, legal, strict=True):
            assert tuple(feats) == policy_action_names(STUB_VOCAB)
            assert feats == policy_action_features(action, view, STUB_VOCAB)
        assert legal[sample.teacher_index] == teacher_action(row)
        assert (sample.pair_index, sample.seed) == (0, row["seed"])

    def test_v1缺省路径逐位不变(self, snapshot_file) -> None:
        """不传 card_vocab → v1 口径；v2 样本共享的 M11 特征段与 v1 逐位一致。"""
        row = snapshot_file.rows[0]
        card_effects = snapshot_file.card_effects()
        v1 = row_to_sample(row, pair_index=0, card_effects=card_effects)
        assert tuple(v1.state) == FEATURE_NAMES
        assert all(tuple(a) == ACTION_FEATURE_NAMES for a in v1.actions)
        v2 = row_to_sample(row, pair_index=0, card_effects=card_effects,
                           card_vocab=STUB_VOCAB)
        assert {k: v2.state[k] for k in FEATURE_NAMES} == v1.state
        for a1, a2 in zip(v1.actions, v2.actions, strict=True):
            assert {k: a2[k] for k in ACTION_FEATURE_NAMES} == a1
        assert v2.teacher_index == v1.teacher_index

    def test_全阶段行v2可转换(self, snapshot_file) -> None:
        """冒烟全量行（含 choice/setup/promote 阶段）v2 路径逐行转换不炸。"""
        card_effects = snapshot_file.card_effects()
        for row in snapshot_file.rows:
            sample = row_to_sample(row, pair_index=0, card_effects=card_effects,
                                   card_vocab=STUB_VOCAB)
            assert 0 <= sample.teacher_index < len(sample.actions)

    def test_load透传card_vocab(self, snapshot_file, tmp_path) -> None:
        import json

        path = tmp_path / "pair-0-测试Ax测试B.jsonl"
        lines = [{"record": "header", **snapshot_file.header}] + \
            [{**r, "record": "snapshot"} for r in snapshot_file.rows]
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in lines)
            + "\n", encoding="utf-8")
        samples = load_policy_samples(tmp_path, card_vocab=STUB_VOCAB)
        assert len(samples) == len(snapshot_file.rows)
        assert all(tuple(s.state) == POLICY_STATE_NAMES for s in samples)
        assert all(tuple(a) == policy_action_names(STUB_VOCAB)
                   for s in samples for a in s.actions)


def _trainer(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype=Supertype.TRAINER)


def _with_discard(state, *, own=(), opp=()):
    p0 = state.players[0].model_copy(update={"discard": own})
    p1 = state.players[1].model_copy(update={"discard": opp})
    return state.model_copy(update={"players": (p0, p1)})


def _hand_with(state, cards):
    p0 = state.players[0].model_copy(
        update={"hand": state.players[0].hand + tuple(cards)})
    return state.model_copy(update={"players": (p0, state.players[1])})


class TestPolicyStateNames:
    def test_键序等于M11清单加弃牌尾序(self) -> None:
        assert POLICY_STATE_NAMES[:30] == FEATURE_NAMES
        assert POLICY_STATE_NAMES[30:] == (
            "own_discard_count", "own_discard_energy_count",
            "own_discard_pokemon_count", "opp_discard_count",
            "opp_discard_energy_count", "opp_discard_pokemon_count")
        assert len(set(POLICY_STATE_NAMES)) == len(POLICY_STATE_NAMES) == 36

    def test_行动键序等于26维加卡身份词表序(self) -> None:
        names = policy_action_names(VOCAB)
        assert names[:26] == ACTION_FEATURE_NAMES
        assert names[26:] == tuple(f"card_{n}" for n in VOCAB)


class TestDiscardComposition:
    def test_双方弃牌分类计数(self) -> None:
        state = _with_discard(
            main_state(),
            own=(inst(600, energy()), inst(601, energy()),
                 inst(602, basic("妙蛙种子")), inst(603, _trainer("博士的研究"))),
            opp=(inst(604, _trainer("宝可梦交替")),))
        view = state.visible_state(0)
        feats = policy_state_features(view)
        assert tuple(feats) == POLICY_STATE_NAMES
        assert feats["own_discard_count"] == 4.0
        assert feats["own_discard_energy_count"] == 2.0
        assert feats["own_discard_pokemon_count"] == 1.0
        assert feats["opp_discard_count"] == 1.0
        assert feats["opp_discard_energy_count"] == 0.0
        assert feats["opp_discard_pokemon_count"] == 0.0
        # M11 特征原样携带
        assert feats["turn_norm"] == pytest.approx(min(view.turn, 50) / 50)
        for name in FEATURE_NAMES:
            assert feats[name] == feature_vector(view)[name]

    def test_键序确定性(self) -> None:
        view = main_state().visible_state(0)
        first, second = policy_state_features(view), policy_state_features(view)
        assert tuple(first) == tuple(second) == POLICY_STATE_NAMES
        assert first == second


class TestResolveActionCardNames:
    def test_use_ability_场上宝可梦栈顶(self) -> None:
        state = main_state()
        poke = in_play(7, basic("沙奈朵ex"))
        p0 = state.players[0].model_copy(update={"bench": (poke,)})
        state = state.model_copy(update={"players": (p0, state.players[1])})
        view = state.visible_state(0)
        assert resolve_action_card_names(
            Action(kind="use_ability", iid=7), view) == ("沙奈朵ex",)

    def test_attack与retreat为己方战斗场(self) -> None:
        view = main_state().visible_state(0)
        for kind in ("attack", "retreat"):
            assert resolve_action_card_names(
                Action(kind=kind), view) == ("妙蛙种子",)

    def test_无战斗场为空(self) -> None:
        state = main_state()
        p0 = state.players[0].model_copy(update={"active": None})
        state = state.model_copy(update={"players": (p0, state.players[1])})
        view = state.visible_state(0)
        assert resolve_action_card_names(Action(kind="attack"), view) == ()

    def test_play_trainer_手牌iid(self) -> None:
        state = _hand_with(main_state(), [inst(52, _trainer("博士的研究"))])
        view = state.visible_state(0)
        assert resolve_action_card_names(
            Action(kind="play_trainer", iid=52), view) == ("博士的研究",)

    def test_choose多iid含不可见跳过(self) -> None:
        state = _hand_with(main_state(), [inst(52, _trainer("博士的研究"))])
        view = state.visible_state(0)
        assert resolve_action_card_names(
            Action(kind="choose", choices=(52, 99999)), view) == ("博士的研究",)

    def _own_bench_view(self, poke) -> object:
        state = main_state()
        p0 = state.players[0].model_copy(update={"bench": (poke,)})
        state = state.model_copy(update={"players": (p0, state.players[1])})
        return state.visible_state(0)

    def test_promote与shrink_bench_备战区索引身份(self) -> None:
        view = self._own_bench_view(in_play(7, basic("沙奈朵ex")))
        for kind in ("promote", "shrink_bench"):
            assert resolve_action_card_names(
                Action(kind=kind, bench_index=0), view) == ("沙奈朵ex",)

    def test_promote越界为空(self) -> None:
        view = self._own_bench_view(in_play(7, basic("沙奈朵ex")))
        for kind in ("promote", "shrink_bench"):
            assert resolve_action_card_names(
                Action(kind=kind, bench_index=5), view) == ()

    def test_shrink_bench_choices反查(self) -> None:
        """引擎实际枚举 shrink_bench 用 choices=(栈顶 iid,)（core.py），走通用 iid 反查。"""
        view = self._own_bench_view(in_play(7, basic("沙奈朵ex")))
        assert resolve_action_card_names(
            Action(kind="shrink_bench", choices=(7,)), view) == ("沙奈朵ex",)

    def test_use_stadium_有场(self) -> None:
        state = main_state().model_copy(
            update={"stadium": inst(700, _trainer("巨大炉灶"))})
        view = state.visible_state(0)
        assert resolve_action_card_names(
            Action(kind="use_stadium"), view) == ("巨大炉灶",)

    def test_use_stadium_无场为空(self) -> None:
        view = main_state().visible_state(0)
        assert resolve_action_card_names(Action(kind="use_stadium"), view) == ()


class TestPolicyActionFeatures:
    def test_onehot命中与键序(self) -> None:
        state = _hand_with(main_state(), [inst(52, _trainer("博士的研究"))])
        view = state.visible_state(0)
        feats = policy_action_features(
            Action(kind="play_trainer", iid=52), view, VOCAB)
        assert tuple(feats) == policy_action_names(VOCAB)
        assert feats["kind_play_trainer"] == 1.0
        assert feats["card_博士的研究"] == 1.0
        assert feats["card_沙奈朵ex"] == 0.0
        assert feats["card_基本能量"] == 0.0

    def test_choose_multi_hot(self) -> None:
        state = _hand_with(main_state(), [
            inst(52, _trainer("博士的研究")), inst(53, energy())])
        view = state.visible_state(0)
        feats = policy_action_features(
            Action(kind="choose", choices=(52, 53)), view, VOCAB)
        assert feats["card_博士的研究"] == 1.0
        assert feats["card_基本能量"] == 1.0
        assert feats["card_沙奈朵ex"] == 0.0

    def test_词表外卡名显式报错(self) -> None:
        view = main_state().visible_state(0)  # 手牌 iid=50 = 小火龙（不在 VOCAB）
        with pytest.raises(ValueError, match="词表"):
            policy_action_features(
                Action(kind="play_trainer", iid=50), view, VOCAB)


class TestBuildCardVocab:
    def test_去重与字典序(self, monkeypatch, tmp_path) -> None:
        pool_yml = tmp_path / "pool.yml"
        pool_yml.write_text(
            "version: 1\nlocked_at: '2026-10-19'\n"
            "query: {window: t, division: t, basis: t, min_n: 1,"
            " n_tournaments: 1, snapshot: t, name_group_rules_hash: t}\n"
            "decks:\n"
            "  - {archetype: 卡组A, en_archetype: deckA, wur: 0.6, n: 10,"
            " deck_id: 'stub:1'}\n"
            "  - {archetype: 卡组B, en_archetype: deckB, wur: 0.5, n: 10,"
            " deck_id: 'stub:2'}\n",
            encoding="utf-8")

        from battlefrontier.agent import policy_features
        from battlefrontier.data.deck import LoadedDeck

        def fake_load_deck(db_path, deck_id):
            cards = {
                "stub:1": [basic("妙蛙种子"), basic("小火龙"), energy()],
                "stub:2": [basic("小火龙"), _trainer("博士的研究")],
            }[deck_id]
            return LoadedDeck(cards=cards)

        monkeypatch.setattr(policy_features, "load_deck", fake_load_deck)
        vocab = build_card_vocab(pool_yml, "dummy.db")
        # 字面量期望序钉死「Python 字典序（Unicode 码点序）」口径
        assert vocab == ("博士的研究", "基本能量", "妙蛙种子", "小火龙")
        assert len(vocab) == len(set(vocab))
