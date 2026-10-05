"""task 034 WP2：MCTS 搜索核心验收测试（D-034-1/4/5/6/7/9）+ task 039 修订。

D-034-4 多世界 determinized UCT：同种子同引擎状态 → 同决策（含连续多决策）；
预算参数生效；跨世界聚合平手取 legal_actions 序靠前者。
D-039-2（修订 D-034-9）挂起根部分决定化：pending_choice 非 None 的根照常
determinize，freeze = pool_iids ∪ payload（已知候选池原位冻结），搜索返回
合法 choose 且 determinized 世界可正常续跑。
收敛性：一手即可斩杀的明显优劣局面，大预算收敛到斩杀。
"""

from pathlib import Path

import pytest
from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.agent.mcts import MCTSAgent, _select_action
from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef, GameState, PlayerState


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品")

ULTRA_BALL_DOC = parse_card_doc("""
card:
  name_group: 高级球
effects:
  - trigger: on_play
    cost:
      - {action: discard, selector: own_hand, choose: 2}
    actions:
      - {action: search_deck, selector: own_deck, filters: [pokemon], choose: 1, destination: hand}
      - {action: shuffle_deck}
""")


def _mcts(seed: int = 7, **kwargs) -> MCTSAgent:
    params = {"worlds": 2, "iterations": 4, **kwargs}
    return MCTSAgent(RandomSource(seed), **params)


# ── 确定性（D-034-6/7：随机源单流；同种子同状态同决策）────────────────────


class TestDeterminism:
    def test_same_seed_same_decision(self) -> None:
        """同种子两个 MCTSAgent 实例对同一引擎状态给出同一决策；返回恒合法。"""
        engine = engine_at(main_state())
        legal = engine.legal_actions(0)
        chosen = []
        for _ in range(2):
            agent = _mcts()
            agent.bind_engine(engine)
            action = agent.observe(engine.state.visible_state(0), legal)
            assert action in legal
            chosen.append(action)
        assert chosen[0] == chosen[1]

    def test_consecutive_decisions_deterministic(self) -> None:
        """多决策连续：两趟同种子驱动同一局面演化，行动序列逐条一致。"""

        def drive() -> list[Action]:
            engine = engine_at(main_state())
            agent = _mcts(seed=11)
            agent.bind_engine(engine)
            seq = []
            for _ in range(6):
                if engine.state.phase == "game_over":
                    break
                player = engine.state.current_player
                legal = engine.legal_actions(player)
                action = agent.observe(engine.state.visible_state(player), legal)
                assert action in legal
                engine.apply(player, action)
                seq.append(action)
            return seq

        assert drive() == drive()

    def test_different_seed_may_still_be_legal(self) -> None:
        """不同种子同样返回合法行动（不强求决策不同，只验不变量）。"""
        engine = engine_at(main_state())
        legal = engine.legal_actions(0)
        for seed in (1, 2, 3):
            agent = _mcts(seed=seed)
            agent.bind_engine(engine)
            assert agent.observe(engine.state.visible_state(0), legal) in legal

    def test_iteration_replay_seed_fixed_per_world(self, monkeypatch) -> None:
        """回放一致性（主会话复核修订）：同世界内逐迭代克隆共用固定种子——
        同行动路径回放必达同状态（掷币等概率事件不使树边行动失真/非法）；
        采样差异只跨世界。"""
        seen: list[int] = []
        real = MCTSAgent._iterate

        def spy(self, world, root, rp, rt, iter_seed):
            seen.append(iter_seed)
            return real(self, world, root, rp, rt, iter_seed)

        monkeypatch.setattr(MCTSAgent, "_iterate", spy)
        engine = engine_at(main_state())
        agent = _mcts(worlds=2, iterations=4)
        agent.bind_engine(engine)
        agent.observe(engine.state.visible_state(0), engine.legal_actions(0))
        assert len(seen) == 8  # 2 世界 × 4 迭代
        assert len(set(seen[:4])) == 1  # 世界 0 内固定
        assert len(set(seen[4:])) == 1  # 世界 1 内固定
        assert seen[0] != seen[4]  # 跨世界不同


# ── 预算参数与聚合（D-034-4/6）────────────────────────────────────────────


class TestBudgetAndAggregation:
    def test_iterations_one_legal(self) -> None:
        """iterations=1（每世界每根行动至多访问一次）路径合法。"""
        engine = engine_at(main_state())
        legal = engine.legal_actions(0)
        agent = _mcts(iterations=1)
        agent.bind_engine(engine)
        assert agent.observe(engine.state.visible_state(0), legal) in legal

    def test_iterations_50_legal(self) -> None:
        """iterations=50 路径合法。"""
        engine = engine_at(main_state())
        legal = engine.legal_actions(0)
        agent = _mcts(worlds=2, iterations=50)
        agent.bind_engine(engine)
        assert agent.observe(engine.state.visible_state(0), legal) in legal

    def test_aggregate_picks_max_visits(self) -> None:
        """跨世界聚合：访问次数最高者胜出。"""
        legal = [Action(kind="end_turn"), Action(kind="attack", attack_index=0)]
        counts = {legal[0]: 3, legal[1]: 7}
        assert _select_action(legal, counts) == legal[1]

    def test_aggregate_tie_prefers_first_legal(self) -> None:
        """聚合平手 → legal_actions 序靠前者（确定性硬规矩）。"""
        legal = [Action(kind="attack", attack_index=0), Action(kind="end_turn")]
        counts = {legal[0]: 5, legal[1]: 5}
        assert _select_action(legal, counts) == legal[0]
        # 未访问行动（counts 缺项）视为 0，不影响有访问者
        assert _select_action(legal, {legal[1]: 1}) == legal[1]


# ── 挂起根部分决定化（task 039 WP2，D-039-2 修订 D-034-9）────────────────


class TestPendingChoiceRoot:
    def _pending_engine(self, stage: str = "cost"):
        """构造 pending_choice 挂起局面（高级球挂起，仿 test_determinize）。

        stage="cost"：cost 段挂起（own_hand 池弃 2）；stage="deck"：完成第一段
        后停在牌库检索挂起（own_deck 池，冻结卡落在己方牌库——freeze 实质生效面）。
        """
        state = main_state(p0_extra_hand=(inst(60, item("高级球")),))
        engine = engine_at(state)
        engine.card_effects = {"高级球": ULTRA_BALL_DOC}
        engine.apply(0, Action(kind="play_trainer", iid=60))
        assert engine.state.phase == "choice" and engine.state.pending_choice is not None
        if stage == "deck":
            engine.apply(0, next(a for a in engine.legal_actions(0) if a.kind == "choose"))
            assert engine.state.phase == "choice"
            assert engine.state.pending_choice.pool == "own_deck"
        return engine

    def test_pending_root_determinizes_with_freeze(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """挂起根也决定化（D-039-2 修订 D-034-9）：每世界恰好一次，
        freeze == pool_iids ∪ payload（已知候选池冻结，残余隐藏区照常重洗）。"""
        calls: list[frozenset[int]] = []
        import battlefrontier.agent.mcts as mcts_mod

        real = mcts_mod.determinize

        def spy(state, player, rng, freeze=frozenset()):
            calls.append(freeze)
            return real(state, player, rng, freeze=freeze)

        monkeypatch.setattr(mcts_mod, "determinize", spy)
        engine = self._pending_engine(stage="deck")
        pc = engine.state.pending_choice
        expected = frozenset(pc.pool_iids) | frozenset(pc.payload)
        assert expected  # own_deck 检索池非空，冻结实质生效
        legal = engine.legal_actions(0)
        assert legal and all(a.kind == "choose" for a in legal)
        agent = _mcts(worlds=3)
        agent.bind_engine(engine)
        action = agent.observe(engine.state.visible_state(0), legal)
        assert action in legal and action.kind == "choose"
        assert calls == [expected] * 3  # 每世界一次，冻结集正确

    def test_normal_root_determinizes_per_world(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """非挂起根：每世界恰好决定化一次，freeze 为空（行为与现状一致）。"""
        calls: list[frozenset[int]] = []
        import battlefrontier.agent.mcts as mcts_mod

        def spy(state, player, rng, freeze=frozenset()):
            calls.append(freeze)
            return state

        monkeypatch.setattr(mcts_mod, "determinize", spy)
        engine = engine_at(main_state())
        legal = engine.legal_actions(0)
        agent = _mcts(worlds=3, iterations=2)
        agent.bind_engine(engine)
        agent.observe(engine.state.visible_state(0), legal)
        assert calls == [frozenset()] * 3

    def test_pending_root_freeze_keeps_pool_recoverable(self) -> None:
        """挂起根 determinize 后 pool_iids 全部原位可恢复（同区域同下标），
        合法选择枚举不变，determinized 世界可正常 choose 续跑。"""
        from battlefrontier.agent.determinize import determinize
        from battlefrontier.dsl.chooser import enumerate_choices

        engine = self._pending_engine(stage="deck")
        pc = engine.state.pending_choice
        freeze = frozenset(pc.pool_iids) | frozenset(pc.payload)
        legal_before = engine.legal_actions(0)
        for seed in range(5):
            d = determinize(engine.state, 0, RandomSource(seed), freeze=freeze)
            deck = d.players[0].deck
            for pos, c in enumerate(deck):
                if c.iid in freeze:
                    # 原位保持：真实牌库同下标即该 iid
                    assert engine.state.players[0].deck[pos].iid == c.iid
            assert {c.iid for c in deck} == {
                c.iid for c in engine.state.players[0].deck
            }  # 牌库多重集合守恒
            assert enumerate_choices(d.pending_choice) == legal_before  # 合法性不破
            # determinized 世界续跑：choose 恢复到底不失败
            w = engine.clone(rng=RandomSource(seed))
            w.state = d
            w.apply(0, legal_before[0])
            assert w.state.pending_choice is None or w.state.phase == "choice"

    def test_pending_root_search_resumes_legally(self) -> None:
        """挂起局面完整搜索（真 determinize、真 rollout），返回合法 choose。"""
        engine = self._pending_engine()
        legal = engine.legal_actions(0)
        agent = _mcts(worlds=2, iterations=6)
        agent.bind_engine(engine)
        action = agent.observe(engine.state.visible_state(0), legal)
        assert action in legal and action.kind == "choose"
        # 搜索不污染真实引擎：挂起帧原样、可正常续跑
        assert engine.state.phase == "choice"
        assert engine.state.pending_choice is not None
        assert engine.state.pending_choice.cursor == 0


# ── 收敛性：一手斩杀局面（D-034-4 搜索有效性）──────────────────────────────


def _lethal_state() -> GameState:
    """p0 一手斩杀 vs 让先即败的尖锐局面：双方战斗场均剩 10 HP（打击 20 可昏厥），
    双方均无后备。p0 攻击 → 昏厥 p1 战斗场（无后备）→ 立即获胜；
    p0 不攻击 → p1 回合攻击昏厥 p0 战斗场（无后备、无手牌可铺）→ p0 必败。
    p0 手牌置空 → 合法行动仅 attack / end_turn，优劣分明（1.0 vs ~0.0）。"""
    s = main_state(p0_active_energies=1, p1_active_energies=1)
    p0 = s.players[0].model_copy(update={
        "active": s.players[0].active.model_copy(update={"damage": 60}),  # hp 70 → 剩 10
        "hand": (),
    })
    p1 = s.players[1].model_copy(update={
        "active": s.players[1].active.model_copy(update={"damage": 60}),
    })
    return s.model_copy(update={"players": (p0, p1)})


class TestConvergence:
    def test_lethal_attack_chosen(self) -> None:
        """明显优劣局面下大预算收敛到斩杀（攻击 = 立即获胜）。"""
        engine = engine_at(_lethal_state())
        legal = engine.legal_actions(0)
        assert any(a.kind == "attack" for a in legal)
        agent = _mcts(worlds=2, iterations=40)
        agent.bind_engine(engine)
        action = agent.observe(engine.state.visible_state(0), legal)
        assert action.kind == "attack"

    def test_lethal_decision_deterministic_across_instances(self) -> None:
        """斩杀局面的同种子双实例决策一致（确定性 + 收敛叠加验证）。"""
        engine = engine_at(_lethal_state())
        legal = engine.legal_actions(0)
        actions = []
        for _ in range(2):
            agent = _mcts(worlds=2, iterations=20)
            agent.bind_engine(engine)
            actions.append(agent.observe(engine.state.visible_state(0), legal))
        assert actions[0] == actions[1] and actions[0].kind == "attack"


# ── 接线（task 034 WP3：bind_engine 钩子 / type=mcts 构建 / 确定性）────────

class TestWiring:
    def test_play_game_binds_and_completes(self) -> None:
        """play_game 驱动循环在 observe 前 bind_engine；白板小预算整局打完。"""
        from helpers import deck60

        from battlefrontier.runner.play import play_game

        agents = [_mcts(worlds=1, iterations=1), _mcts(seed=99, worlds=1, iterations=1)]
        r = play_game(deck60(), deck60(), seed=3, agents=agents)
        assert r.phase == "game_over"
        assert agents[0]._engine is not None and agents[1]._engine is not None

    def test_play_game_same_seed_same_hash(self) -> None:
        """同种子双跑 events_hash 逐局一致（MCTS 决策确定性，硬验收口径）。"""
        from helpers import deck60

        from battlefrontier.runner.play import play_game

        def run() -> str:
            agents = [_mcts(worlds=1, iterations=2), _mcts(seed=99, worlds=1, iterations=2)]
            return play_game(deck60(), deck60(), seed=5, agents=agents).events_hash

        assert run() == run()

    def test_build_agents_mcts_type(self) -> None:
        """实验定义 type=mcts 经 build_agents 构建：params 透传 + rng 独立流。"""
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
                a=AgentCfg(type="mcts", params={"worlds": 2, "iterations": 5}),
                b=AgentCfg(type="heuristic"),
            ),
        )
        agents = build_agents(defn, seed=42)
        assert isinstance(agents[0], MCTSAgent)
        assert agents[0].worlds == 2 and agents[0].iterations == 5
        assert agents[0]._rng is not agents[1].__dict__.get("_rng")


# ── 挂接钩子（D-034-1）─────────────────────────────────────────────────────


class TestBindEngine:
    def test_observe_without_bind_raises(self) -> None:
        """未 bind_engine 且需搜索（>1 合法行动）时明确报错，不静默瞎选。"""
        engine = engine_at(main_state())
        legal = engine.legal_actions(0)
        assert len(legal) > 1
        with pytest.raises(RuntimeError, match="bind_engine"):
            _mcts().observe(engine.state.visible_state(0), legal)

    def test_single_legal_action_shortcuts(self) -> None:
        """唯一合法行动直接返回（不消费随机源、无需 bind_engine）。"""
        agent = _mcts()
        only = Action(kind="end_turn")
        assert agent.observe(None, [only]) == only  # type: ignore[arg-type]


# ── 挂起根端到端：真实 chooser 卡（task 039 WP2 验收 2）────────────────────

PRO_DOC = load_card_doc(Path(__file__).parent.parent / "cards" / "能量输送PRO.yml")


def _pro_pending_engine():
    """能量输送PRO 挂起局面（own_deck any_count+distinct 检索，真实 DSL 文档）。

    牌库混多属性基本能量 + 宝可梦（检索池非空、分桶 >1，冻结实质生效）。
    """
    types = ["草", "火", "水", "雷"]
    deck = tuple(
        inst(100 + i, energy(f"基本{t}能量", t)) for i, t in enumerate(types * 2)
    ) + tuple(inst(120 + i, basic(f"妙蛙种子{i}")) for i in range(6))
    p0 = PlayerState(
        deck=deck,
        hand=(inst(50, basic("小火龙")), inst(60, item("能量输送PRO"))),
        prizes=tuple(inst(200 + i, basic(f"奖{i}")) for i in range(6)),
        active=in_play(1, basic("妙蛙种子"), 1),
    )
    s = main_state().model_copy(update={"players": (p0, main_state().players[1])})
    engine = engine_at(s)
    engine.card_effects = {"能量输送PRO": PRO_DOC}
    engine.apply(0, Action(kind="play_trainer", iid=60))
    assert engine.state.phase == "choice" and engine.state.pending_choice is not None
    assert engine.state.pending_choice.pool == "own_deck"
    return engine


class TestPendingRootRealCard:
    def test_pro_pending_root_search_and_resume(self) -> None:
        """能量输送PRO 挂起根：MCTS 搜索（真 determinize + freeze）返回合法
        choose，恢复后效果结算到底（reveal + shuffle_deck 完成回主阶段）。"""
        engine = _pro_pending_engine()
        pc = engine.state.pending_choice
        legal = engine.legal_actions(0)
        assert legal and all(a.kind == "choose" for a in legal)
        for seed in (3, 5, 7):
            agent = _mcts(seed=seed, worlds=2, iterations=6)
            agent.bind_engine(engine)
            action = agent.observe(engine.state.visible_state(0), legal)
            assert action in legal
            assert set(action.choices) <= set(pc.pool_iids)
        # 真实引擎零污染，选择一个分支续跑到底
        engine.apply(0, legal[-1])
        assert engine.state.phase == "main" and engine.state.pending_choice is None

    def test_pro_full_game_zero_failure(self) -> None:
        """带 能量输送PRO 的 MCTS 对局零失败（挂起根部分决定化全链路冒烟，
        D-039-4）：PRO 先手驱动器保证挂起根在每局出现。"""
        from battlefrontier.runner.play import play_game

        class _ProFirstMCTS(MCTSAgent):
            """手牌可打 能量输送PRO 则直接打出（制造挂起根），否则走 MCTS。"""

            def observe(self, view, legal_actions):
                for c in view.own.hand:
                    if c.card.name == "能量输送PRO":
                        act = next(
                            (a for a in legal_actions
                             if a.kind == "play_trainer" and a.iid == c.iid),
                            None,
                        )
                        if act is not None:
                            return act
                return super().observe(view, legal_actions)

        deck = (
            [basic("妙蛙种子")] * 16 + [basic("小火龙")] * 16
            + [energy("基本草能量", "草")] * 8 + [energy("基本火能量", "火")] * 8
            + [energy("基本水能量", "水")] * 8 + [item("能量输送PRO")] * 4
        )
        assert len(deck) == 60
        saw_pro_choose = False
        for seed in (3, 5, 7):
            agents = [
                _ProFirstMCTS(RandomSource(seed), worlds=1, iterations=2),
                _mcts(seed=seed + 1000, worlds=1, iterations=2),
            ]
            r = play_game(deck, deck, seed=seed, card_effects={"能量输送PRO": PRO_DOC},
                          agents=agents)
            assert r.phase == "game_over"
            saw_pro_choose |= any(
                ev.kind == "choose" and "能量输送PRO" in str(ev.detail.get("effect_id", ""))
                for ev in r.events
            )
        assert saw_pro_choose  # 覆盖断言：至少一局真的走了 PRO 挂起根


# ── 串/并行一致性回归（task 039 验收 4，仿 test_experiment 对拍口径）────────


class TestSerialParallel:
    MCTS_YAML = """
name: mcts-par
games: 4
seed_start: 200
decks:
  a: {source: db, deck_id: "x"}
  b: {source: db, deck_id: "y"}
agents:
  a: {type: mcts, params: {worlds: 1, iterations: 2}}
  b: {type: mcts, params: {worlds: 1, iterations: 2}}
"""

    def test_mcts_experiment_parallel_matches_serial(self, tmp_path) -> None:
        """type=mcts 实验定义：workers=1 vs workers=2 逐局一致（含 setup 期
        对手场上入池后的世界采样——每局决策都从布阵阶段开始）。"""
        from helpers import deck60

        from battlefrontier.runner.experiment import (
            PreparedExperiment,
            execute_experiment,
            load_experiment,
        )
        from battlefrontier.runner.results_db import ResultsDB

        yml = tmp_path / "exp.yml"
        yml.write_text(self.MCTS_YAML, encoding="utf-8")
        defn = load_experiment(yml)
        prep = PreparedExperiment(
            deck_a=deck60(), deck_b=deck60(), card_effects={},
            deck_a_id="stub", deck_b_id="stub", data_version="test")

        def snapshot(db_path, workers: int):
            db = ResultsDB(db_path)
            try:
                exp_id = execute_experiment(
                    prep, defn, db_path, workers=workers,
                    definition_yaml=self.MCTS_YAML)
                return [
                    (g["seed"], g["winner"], g["is_draw"], g["turns"], g["events_hash"])
                    for g in db.games(exp_id)
                ]
            finally:
                db.close()

        serial = snapshot(tmp_path / "s.db", workers=1)
        parallel = snapshot(tmp_path / "p.db", workers=2)
        assert len(serial) == 4
        assert serial == parallel
