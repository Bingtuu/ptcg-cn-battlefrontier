"""task 042：MCTS 决策分析——根节点访问分布导出（D-042-1~4）。

D-042-1 采集：MCTSAgent.observe 末尾存 last_consideration（根统计）；
play.py 驱动循环读后追加 mcts_consider 事件（随后清空防重复记账）。
唯一选择早退路径（无搜索）→ last_consideration 置 None，不产生事件。
D-042-2 口径：events_hash 排除 mcts_consider（观测事件不进行为校验）；
render 回放显式跳过。
D-042-3 载荷：considered[{action, kind, visits}] + chosen + chosen_visits +
total_visits；action 标签 = kind：可读参数（attack→招式名、trainer→卡名等），
解析失败回退 kind 原文。
D-042-4 报告三件套：按 kind 访问份额 / 归一化熵 top N / 选中份额分桶 × 胜率。
"""

import hashlib
import json

import pytest
from helpers import basic, deck60, engine_at, in_play, inst, main_state

from battlefrontier.agent.mcts import Consideration, MCTSAgent
from battlefrontier.agent.random_agent import RandomAgent
from battlefrontier.cli import main as cli_main
from battlefrontier.engine.actions import Action
from battlefrontier.engine.events import GameEvent
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef
from battlefrontier.report.mcts_analysis import format_mcts_report, mcts_report
from battlefrontier.report.render import render_log
from battlefrontier.runner.play import GameResult, play_game
from battlefrontier.runner.results_db import ResultsDB


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品")


def _mcts(seed: int = 7, **kwargs) -> MCTSAgent:
    params = {"worlds": 2, "iterations": 4, **kwargs}
    return MCTSAgent(RandomSource(seed), **params)


# ── D-042-1 采集：last_consideration ─────────────────────────────────────


class TestCollection:
    def test_observe_records_last_consideration(self) -> None:
        """搜索完成后 last_consideration 记录根统计：turn/phase/player、
        各行动 visits（降序）、total_visits、chosen；chosen = 最高访问。"""
        engine = engine_at(main_state())
        legal = engine.legal_actions(0)
        agent = _mcts()
        agent.bind_engine(engine)
        chosen = agent.observe(engine.state.visible_state(0), legal)
        c = agent.last_consideration
        assert isinstance(c, Consideration)
        assert c.turn == engine.state.turn and c.phase == "main" and c.player == 0
        assert c.total_visits == sum(v for _, v in c.considered)
        assert c.total_visits > 0
        visits = [v for _, v in c.considered]
        assert visits == sorted(visits, reverse=True)  # 降序
        assert c.chosen == chosen
        assert dict(c.considered)[c.chosen] == visits[0]  # chosen 为最高访问

    def test_consideration_does_not_change_search(self) -> None:
        """采集只读 counts：同种子双实例决策一致（搜索行为零变化）。"""
        engine = engine_at(main_state())
        legal = engine.legal_actions(0)
        actions = []
        for _ in range(2):
            agent = _mcts()
            agent.bind_engine(engine)
            actions.append(agent.observe(engine.state.visible_state(0), legal))
        assert actions[0] == actions[1]

    def test_unique_choice_records_none(self) -> None:
        """唯一合法行动早退路径无搜索 → last_consideration 置 None（口径：
        不产生 mcts_consider 事件；无需 bind_engine）。"""
        agent = _mcts()
        only = Action(kind="end_turn")
        assert agent.observe(None, [only]) == only  # type: ignore[arg-type]
        assert agent.last_consideration is None

    def test_consideration_cleared_between_decisions(self) -> None:
        """play_game 读后清空：同一 agent 连续决策不产生重复记账。"""
        agents = [_mcts(worlds=1, iterations=2), _mcts(seed=99, worlds=1, iterations=2)]
        r = play_game(deck60(), deck60(), seed=3, agents=agents)
        assert agents[0].last_consideration is None
        assert agents[1].last_consideration is None
        assert r.phase == "game_over"


# ── D-042-3 事件载荷与行动标签 ───────────────────────────────────────────


class TestEventPayload:
    def test_play_game_emits_mcts_consider(self) -> None:
        """MCTS 对局事件流含 mcts_consider，字段完整（turn/phase 顶层 +
        considered/chosen/chosen_visits/total_visits）。"""
        agents = [_mcts(worlds=1, iterations=2), _mcts(seed=99, worlds=1, iterations=2)]
        r = play_game(deck60(), deck60(), seed=3, agents=agents)
        events = [ev for ev in r.events if ev.kind == "mcts_consider"]
        assert events
        ev = events[0]
        assert ev.turn >= 0 and ev.phase and ev.player in (0, 1)
        d = ev.detail
        assert d["total_visits"] == sum(c["visits"] for c in d["considered"])
        for entry in d["considered"]:
            assert set(entry) == {"action", "kind", "visits"}
        assert d["chosen"] in [c["action"] for c in d["considered"]]
        assert d["chosen_visits"] == max(c["visits"] for c in d["considered"])

    def test_non_mcts_agents_emit_nothing(self) -> None:
        """random 对局零 mcts_consider 事件（无 last_consideration 属性，零开销）。"""
        agents = [RandomAgent(RandomSource(1)), RandomAgent(RandomSource(2))]
        r = play_game(deck60(), deck60(), seed=3, agents=agents)
        assert not any(ev.kind == "mcts_consider" for ev in r.events)


class TestActionLabel:
    """D-042-3 标签解析：attack→招式名、iid→卡名；失败回退 kind 原文。"""

    def test_attack_resolves_move_name(self) -> None:
        from battlefrontier.runner.play import _action_label

        engine = engine_at(main_state())  # p0 战斗场妙蛙种子，招式「打击」
        assert _action_label(engine, 0, Action(kind="attack", attack_index=0)) == "attack：打击"

    def test_iid_actions_resolve_card_name(self) -> None:
        from battlefrontier.runner.play import _action_label

        state = main_state(p0_extra_hand=(inst(60, item("高级球")),))
        engine = engine_at(state)
        assert _action_label(engine, 0, Action(kind="play_trainer", iid=60)) == "play_trainer：高级球"
        # attach_energy 附目标：iid 51 是 p0 手牌能量，战斗场栈顶 iid 1
        label = _action_label(engine, 0, Action(kind="attach_energy", iid=51, target_iid=1))
        assert label == "attach_energy：基本能量→妙蛙种子"

    def test_retreat_resolves_bench_name(self) -> None:
        from battlefrontier.runner.play import _action_label

        s = main_state()
        p0 = s.players[0].model_copy(update={"bench": (in_play(9, basic("喇叭芽")),)})
        engine = engine_at(s.model_copy(update={"players": (p0, s.players[1])}))
        assert _action_label(engine, 0, Action(kind="retreat", bench_index=0)) == "retreat：喇叭芽"

    def test_choose_resolves_choice_names(self) -> None:
        from battlefrontier.runner.play import _action_label

        engine = engine_at(main_state())  # p0 牌库 iid 100.. 妙蛙种子
        label = _action_label(engine, 0, Action(kind="choose", choices=(100, 101)))
        assert label == "choose：妙蛙种子+妙蛙种子"

    def test_fallback_to_kind(self) -> None:
        from battlefrontier.runner.play import _action_label

        engine = engine_at(main_state())
        assert _action_label(engine, 0, Action(kind="end_turn")) == "end_turn"
        # iid 解析失败（不在任何区域）→ 回退 kind 原文（不猜）
        assert _action_label(engine, 0, Action(kind="play_trainer", iid=9999)) == "play_trainer"
        # attack 下标越界 → 回退
        assert _action_label(engine, 0, Action(kind="attack", attack_index=7)) == "attack"

    def test_full_game_labels_readable(self) -> None:
        """端到端：真实对局的 mcts_consider 事件里 attack/play_trainer 类标签带名。"""
        agents = [_mcts(worlds=1, iterations=2), _mcts(seed=99, worlds=1, iterations=2)]
        r = play_game(deck60(), deck60(), seed=3, agents=agents)
        entries = [
            c for ev in r.events if ev.kind == "mcts_consider"
            for c in ev.detail["considered"]
        ]
        attacks = [c for c in entries if c["kind"] == "attack"]
        assert attacks and all("：" in c["action"] for c in attacks)  # 招式名已解析
        assert any(c["action"] == "attack：打击" for c in attacks)


# ── D-042-2 观测口径：events_hash 排除 + render 跳过 ──────────────────────


class TestObservabilityScope:
    def test_events_hash_excludes_mcts_consider(self) -> None:
        """events_hash payload 过滤 mcts_consider（观测事件不进行为校验，
        跨版本可比）；事件本体仍留在事件流落库。"""
        agents = [_mcts(worlds=1, iterations=2), _mcts(seed=99, worlds=1, iterations=2)]
        r = play_game(deck60(), deck60(), seed=5, agents=agents)
        assert any(ev.kind == "mcts_consider" for ev in r.events)  # 确有被过滤事件
        payload = json.dumps(
            [ev.model_dump(mode="json") for ev in r.events if ev.kind != "mcts_consider"],
            ensure_ascii=False, sort_keys=True,
        )
        assert r.events_hash == hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def test_same_seed_same_hash_with_consider_events(self) -> None:
        """同种子双跑 events_hash 逐局一致（采集引入后确定性不破）。"""

        def run() -> str:
            agents = [_mcts(worlds=1, iterations=2), _mcts(seed=99, worlds=1, iterations=2)]
            return play_game(deck60(), deck60(), seed=5, agents=agents).events_hash

        assert run() == run()

    def test_render_skips_mcts_consider(self) -> None:
        """回放显式跳过 mcts_consider（观测事件不渲染，非未知 kind 回退）。"""
        consider = GameEvent(
            seq=0, turn=1, phase="main", player=0, kind="mcts_consider",
            detail={"chosen": "end_turn", "chosen_visits": 3, "total_visits": 4,
                    "considered": [{"action": "end_turn", "kind": "end_turn", "visits": 3}]})
        end = GameEvent(seq=1, turn=1, phase="main", player=0, kind="end_turn", detail={})
        out = render_log([consider, end])
        assert "mcts_consider" not in out
        assert "回合结束" in out


# ── D-042-4 报告三件套（合成事件流）───────────────────────────────────────


def _consider_ev(seq: int, *, player: int = 0, turn: int = 2,
                 chosen_visits: int = 9, other_visits: int = 1) -> GameEvent:
    considered = [
        {"action": "attack：打击", "kind": "attack", "visits": chosen_visits},
        {"action": "end_turn", "kind": "end_turn", "visits": other_visits},
    ]
    return GameEvent(
        seq=seq, turn=turn, phase="main", player=player, kind="mcts_consider",
        detail={"chosen": "attack：打击", "chosen_visits": chosen_visits,
                "total_visits": chosen_visits + other_visits, "considered": considered})


@pytest.fixture()
def synth_db(tmp_path):
    """4 完成局（g1 A胜 / g2 B胜 / g3 平 / g4 B胜无事件）+ 1 失败。

    分桶期望（只统计决定局的 games/wins；decisions 计全部完成局事件）：
    - 果断（>80%）：ev(g1,p0,9/10)、ev(g3,p0,9/10 平局) → decisions 2，
      games 1（g1，p0 胜）→ 胜率 1.0
    - 50-80%：ev(g1,p1,5/10)、ev(g2,p0,6/10) → decisions 2，games 2，
      g1 p1 负 / g2 p0 负 → 胜率 0.0
    - 纠结（<50%）：ev(g2,p1,3/10) → decisions 1，games 1（g2 p1 胜）→ 胜率 1.0
    """
    db = ResultsDB(tmp_path / "r.db")
    exp_id = db.start_experiment(name="mcts-agg", definition_yaml="x",
                                 code_version="v", data_version="d")
    games = [
        (100, 0, [_consider_ev(0, player=0, chosen_visits=9),
                  _consider_ev(1, player=1, chosen_visits=5, other_visits=5)]),
        (101, 1, [_consider_ev(0, player=0, chosen_visits=6, other_visits=4),
                  _consider_ev(1, player=1, chosen_visits=3, other_visits=7)]),
        (102, None, [_consider_ev(0, player=0, chosen_visits=9)]),  # 平局不进分母
        (103, 1, []),  # 无事件完成局
    ]
    for seed, winner, events in games:
        db.record_game(exp_id, seed=seed, first_player=0,
                       result=GameResult(winner=winner, is_draw=winner is None,
                                         turns=10, phase="game_over", events=events),
                       deck_a_id="a", deck_b_id="b")
    db.record_error(exp_id, seed=104, deck_a_id="a", deck_b_id="b", error="x")
    db.finish_experiment(exp_id)
    yield db, exp_id
    db.close()


class TestKindShare:
    def test_visit_share_by_kind(self, synth_db) -> None:
        """① 按 action kind 聚合访问份额 = Σvisits/Σtotal。"""
        db, exp_id = synth_db
        r = mcts_report(db, exp_id)
        assert r.games_analyzed == 4  # 完成局（失败局排除）
        assert r.decision_points == 5
        by_kind = {k.kind: k for k in r.kind_shares}
        # attack 访问 9+5+6+3+9=32 / 总 50；end_turn 1+5+4+7+1=18
        assert by_kind["attack"].visits == 32
        assert by_kind["attack"].share == pytest.approx(0.64)
        assert by_kind["end_turn"].visits == 18
        assert by_kind["end_turn"].share == pytest.approx(0.36)
        assert r.kind_shares[0].kind == "attack"  # 按份额降序


class TestEntropyTop:
    def test_normalized_entropy_ordering(self, synth_db) -> None:
        """② 高熵决策点 top N：均分分布（5/5）归一化熵 1.0 排最前。"""
        db, exp_id = synth_db
        r = mcts_report(db, exp_id)
        assert r.entropy_top
        top = r.entropy_top[0]
        assert top.entropy == pytest.approx(1.0)  # 5/5 均分
        assert top.turn == 2 and top.phase == "main"
        assert dict(top.distribution) == {"attack：打击": 5, "end_turn": 5}
        entropies = [p.entropy for p in r.entropy_top]
        assert entropies == sorted(entropies, reverse=True)


class TestBucketWinrate:
    def test_bucket_stats(self, synth_db) -> None:
        """③ 选中行动访问份额分桶 × 选择方最终胜率（Wilson CI，只统计决定局）。"""
        db, exp_id = synth_db
        r = mcts_report(db, exp_id)
        by_label = {b.label: b for b in r.buckets}
        decisive = by_label["果断（>80%）"]
        assert decisive.decisions == 2 and decisive.games == 1
        assert decisive.wins == 1 and decisive.winrate == 1.0
        mid = by_label["50-80%"]
        assert mid.decisions == 2 and mid.games == 2
        assert mid.wins == 0 and mid.winrate == 0.0
        torn = by_label["纠结（<50%）"]
        assert torn.decisions == 1 and torn.games == 1
        assert torn.wins == 1 and torn.winrate == 1.0
        for b in r.buckets:  # CI 形态合法
            assert 0.0 <= b.ci[0] <= b.ci[1] <= 1.0


class TestFormatAndCli:
    def test_format_renders_sections(self, synth_db) -> None:
        db, exp_id = synth_db
        text = format_mcts_report(mcts_report(db, exp_id))
        assert "访问份额" in text and "高熵决策点" in text and "果断" in text
        assert "attack" in text

    def test_format_empty_report(self, tmp_path) -> None:
        """无 mcts_consider 事件的实验 → 明示（非 MCTS 对局或早于 task 042）。"""
        db = ResultsDB(tmp_path / "e.db")
        exp_id = db.start_experiment(name="plain", definition_yaml="x",
                                     code_version="v", data_version="d")
        db.record_game(exp_id, seed=1, first_player=0,
                       result=GameResult(winner=0, is_draw=False, turns=3,
                                         phase="game_over", events=[]),
                       deck_a_id="a", deck_b_id="b")
        db.finish_experiment(exp_id)
        try:
            text = format_mcts_report(mcts_report(db, exp_id))
        finally:
            db.close()
        assert "无 mcts_consider" in text

    def test_cli_report_mcts_consider(self, synth_db, capsys) -> None:
        """bfsim report <id> --mcts-consider 追加 MCTS 决策分析分节。"""
        db, exp_id = synth_db
        path = db._conn.execute("PRAGMA database_list").fetchone()[2]
        db.close()
        rc = cli_main(["report", str(exp_id), "--results", path, "--mcts-consider"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "MCTS" in out and "访问份额" in out
