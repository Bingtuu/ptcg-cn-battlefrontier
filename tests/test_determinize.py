"""task 034 WP1：引擎克隆（D-034-2）+ 隐藏信息 determinizer（D-034-3）验收测试。

D-034-2 快照克隆：state model_copy(deep=True) + 新 RandomSource + 共享
card_effects + 全新 events；克隆独立续跑、不回流原引擎。
D-034-3 Determinization（单观察者）：对手手牌内容 / 双方奖赏内容 / 双方牌库
顺序重采样；可见区（自己手牌、双方场上/弃牌堆、竞技场）逐卡不动；区域计数
与采样池多重集合守恒。
"""

from helpers import basic, energy, engine_at, in_play, inst, main_state, stage1

from battlefrontier.agent.determinize import determinize
from battlefrontier.dsl import parse_card_doc
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


# ── GameEngine.clone（D-034-2）──────────────────────────────────────────


class TestClone:
    def test_clone_independent_apply(self) -> None:
        """克隆独立 apply：原 state 不变、原 events 不增长。"""
        e = engine_at(main_state())
        n_events = len(e.events)
        c = e.clone()
        assert c.events == []  # 全新事件流（模拟事件不回流）
        c.apply(0, Action(kind="end_turn"))
        assert len(e.events) == n_events
        assert e.state == main_state()  # 原状态逐字段不变
        assert c.state != e.state  # 克隆已独立推进（回合权交接）

    def test_clone_shares_effects_and_isolated_rng(self) -> None:
        """card_effects 共享引用（不可变文档）；rng 是独立实例。"""
        e = engine_at(main_state())
        e.card_effects = {"高级球": ULTRA_BALL_DOC}
        c = e.clone()
        assert c.card_effects is e.card_effects
        assert c.rng is not e.rng

    def test_clone_default_rng_usable(self) -> None:
        """未传 rng：克隆自带独立随机源，可正常推进含随机的行动。"""
        e = engine_at(main_state())
        c = e.clone()
        c.apply(0, Action(kind="end_turn"))  # 回合交接 + 对手抽牌
        assert c.state.phase == "main"
        assert c.state.current_player == 1

    def test_clone_pending_choice_resume(self) -> None:
        """挂起态（phase="choice" + pending_choice）克隆：经 choose 正常续跑到底。"""
        state = main_state(p0_extra_hand=(inst(60, item("高级球")),))
        e = engine_at(state)
        e.card_effects = {"高级球": ULTRA_BALL_DOC}
        e.apply(0, Action(kind="play_trainer", iid=60))
        assert e.state.phase == "choice" and e.state.pending_choice is not None
        n_events = len(e.events)

        c = e.clone()
        assert c.state.phase == "choice" and c.state.pending_choice is not None
        # 第一段挂起：手牌选弃 2（唯一组合 50+51）
        c.apply(0, next(a for a in c.legal_actions(0) if a.kind == "choose"))
        assert c.state.phase == "choice"  # 第二段挂起：牌库检索
        pick = next(
            a for a in c.legal_actions(0) if a.kind == "choose" and a.choices == (100,)
        )
        c.apply(0, pick)
        assert c.state.phase == "main" and c.state.pending_choice is None
        assert 100 in [x.iid for x in c.state.players[0].hand]  # 检索入手

        # 原引擎仍停在第一段挂起：pending_choice 原样、事件流不增长
        assert e.state.phase == "choice"
        assert e.state.pending_choice is not None
        assert e.state.pending_choice.cursor == 0
        assert len(e.events) == n_events
        assert 100 not in [x.iid for x in e.state.players[0].hand]

    def test_clone_deep_copy_no_aliasing(self) -> None:
        """深拷贝：克隆推进不会经共享子对象污染原状态（含场上宝可梦嵌套）。"""
        e = engine_at(main_state())
        c = e.clone()
        # 克隆上攻击（写入对手战斗场伤害）
        c.apply(0, Action(kind="attack", attack_index=0))
        assert e.state.players[1].active is not None
        assert e.state.players[1].active.damage == 0  # 原引擎防守方零伤害


# ── determinize（D-034-3）──────────────────────────────────────────────


def _det_state() -> GameState:
    """区域可区分局面：iid 段 手牌 1x/2x、牌库 1xx/4xx、奖赏 2xx/5xx、弃牌 3xx/6xx。"""
    p0 = PlayerState(
        deck=tuple(inst(100 + i, basic(f"草{i}")) for i in range(8)),
        hand=(inst(10, basic("火")), inst(11, energy())),
        prizes=tuple(inst(200 + i, basic(f"奖{i}")) for i in range(6)),
        discard=(inst(300, basic("弃0")),),
        active=in_play(1, basic("场0")),
    )
    p1 = PlayerState(
        deck=tuple(inst(400 + i, basic(f"钢{i}")) for i in range(8)),
        hand=(inst(20, basic("电")), inst(21, basic("水")), inst(22, energy())),
        prizes=tuple(inst(500 + i, basic(f"光{i}")) for i in range(6)),
        discard=(inst(600, basic("弃1")),),
        active=in_play(2, basic("场1")),
        bench=(in_play(3, basic("备1")),),
    )
    return GameState(
        players=(p0, p1), turn=3, current_player=0, phase="main", first_player=0,
    )


def _hidden_signature(state: GameState, player: int = 0) -> tuple:
    """隐藏区指纹：己方 deck 序 + prizes 内容、对手 hand+deck+prizes。"""
    obs, opp = state.players[player], state.players[1 - player]
    return (
        tuple(c.iid for c in obs.deck),
        tuple(c.iid for c in obs.prizes),
        tuple(c.iid for c in opp.hand),
        tuple(c.iid for c in opp.deck),
        tuple(c.iid for c in opp.prizes),
    )


class TestDeterminize:
    def test_zone_counts_conserved(self) -> None:
        """各区计数守恒（双方 hand/deck/prizes/discard/场上全部不变）。"""
        s = _det_state()
        d = determinize(s, 0, RandomSource(7))
        for i in (0, 1):
            for zone in ("hand", "deck", "prizes", "discard", "bench"):
                assert len(getattr(d.players[i], zone)) == len(getattr(s.players[i], zone))

    def test_pool_multiset_conserved(self) -> None:
        """采样池多重集合守恒：各方 hand+deck+prizes 三区 iid 多重集不变。"""
        s = _det_state()
        d = determinize(s, 0, RandomSource(7))
        for i in (0, 1):
            before = sorted(
                c.iid for z in ("hand", "deck", "prizes") for c in getattr(s.players[i], z)
            )
            after = sorted(
                c.iid for z in ("hand", "deck", "prizes") for c in getattr(d.players[i], z)
            )
            assert before == after

    def test_visible_zones_untouched(self) -> None:
        """可见区逐卡不动：己方手牌内容、双方场上/弃牌堆、非区域字段。"""
        s = _det_state()
        d = determinize(s, 0, RandomSource(7))
        assert d.players[0].hand == s.players[0].hand  # 己方手牌已知
        for i in (0, 1):
            assert d.players[i].active == s.players[i].active
            assert d.players[i].bench == s.players[i].bench
            assert d.players[i].discard == s.players[i].discard
        assert d.stadium == s.stadium
        assert (d.turn, d.current_player, d.phase, d.first_player) == (
            s.turn, s.current_player, s.phase, s.first_player,
        )

    def test_hidden_zones_resampled(self) -> None:
        """隐藏区确实被重采样：隐藏指纹与原状态不同。"""
        s = _det_state()
        d = determinize(s, 0, RandomSource(7))
        assert _hidden_signature(d) != _hidden_signature(s)

    def test_same_seed_deterministic(self) -> None:
        """同 rng 种子同输出（种子确定性硬规矩）。"""
        s = _det_state()
        assert determinize(s, 0, RandomSource(7)) == determinize(s, 0, RandomSource(7))

    def test_different_seed_different_shuffle(self) -> None:
        """不同种子产出不同洗序。"""
        s = _det_state()
        sigs = {_hidden_signature(determinize(s, 0, RandomSource(seed))) for seed in range(5)}
        assert len(sigs) > 1

    def test_input_not_mutated(self) -> None:
        """纯函数：入参 state 不被改动。"""
        s = _det_state()
        snapshot = s.model_copy(deep=True)
        determinize(s, 0, RandomSource(7))
        assert s == snapshot

    def test_observer_perspective_symmetric(self) -> None:
        """player=1 视角：p1 手牌保持原样，p0 手牌参与三区合并重洗。"""
        s = _det_state()
        d = determinize(s, 1, RandomSource(7))
        assert d.players[1].hand == s.players[1].hand  # 观察者手牌不动
        assert _hidden_signature(d, 1) != _hidden_signature(s, 1)
        # p0 侧池多重集合守恒（手牌内容可能换入 deck/prizes 的卡）
        before = sorted(
            c.iid for z in ("hand", "deck", "prizes") for c in getattr(s.players[0], z)
        )
        after = sorted(
            c.iid for z in ("hand", "deck", "prizes") for c in getattr(d.players[0], z)
        )
        assert before == after


# ── 冻结集（task 039 WP1，D-039-1）──────────────────────────────────────


def _zone_pos(state: GameState, player: int, iid: int) -> tuple[str, int]:
    """iid 在 (hand, deck, prizes) 中的 (区域, 下标)；不在则断言失败。"""
    p = state.players[player]
    for zone in ("hand", "deck", "prizes"):
        for i, c in enumerate(getattr(p, zone)):
            if c.iid == iid:
                return zone, i
    raise AssertionError(f"iid={iid} 不在 p{player} 的 hand/deck/prizes")


class TestDeterminizeFreeze:
    """D-039-1：freeze 内 iid 保持原区域原位置；非冻结部分照常重洗；
    多重集合守恒与种子确定性不变式保持。"""

    # p0 deck idx2 / prizes idx3；p1 hand idx1 / deck idx5 / prizes idx2
    FREEZE = frozenset({102, 203, 21, 405, 502})

    def test_frozen_cards_stay_in_place(self) -> None:
        """冻结卡原位保持（同区域同下标），跨多个种子均成立。"""
        s = _det_state()
        for seed in range(10):
            d = determinize(s, 0, RandomSource(seed), freeze=self.FREEZE)
            for iid in self.FREEZE:
                owner = 0 if iid in (102, 203) else 1
                assert _zone_pos(d, owner, iid) == _zone_pos(s, owner, iid)

    def test_freeze_multiset_conserved(self) -> None:
        """冻结下采样池多重集合守恒（双方 hand+deck+prizes iid 多重集不变）。"""
        s = _det_state()
        d = determinize(s, 0, RandomSource(7), freeze=self.FREEZE)
        for i in (0, 1):
            before = sorted(
                c.iid for z in ("hand", "deck", "prizes") for c in getattr(s.players[i], z)
            )
            after = sorted(
                c.iid for z in ("hand", "deck", "prizes") for c in getattr(d.players[i], z)
            )
            assert before == after

    def test_freeze_zone_counts_conserved(self) -> None:
        """冻结下各区计数守恒。"""
        s = _det_state()
        d = determinize(s, 0, RandomSource(7), freeze=self.FREEZE)
        for i in (0, 1):
            for zone in ("hand", "deck", "prizes", "discard", "bench"):
                assert len(getattr(d.players[i], zone)) == len(getattr(s.players[i], zone))

    def test_freeze_non_frozen_still_resampled(self) -> None:
        """冻结集之外的重洗仍发生：隐藏指纹与原状态不同。"""
        s = _det_state()
        d = determinize(s, 0, RandomSource(7), freeze=self.FREEZE)
        assert _hidden_signature(d) != _hidden_signature(s)

    def test_freeze_same_seed_deterministic(self) -> None:
        """同 state + 同种子 + 同 freeze → 同输出（种子确定性硬规矩）。"""
        s = _det_state()
        a = determinize(s, 0, RandomSource(7), freeze=self.FREEZE)
        b = determinize(s, 0, RandomSource(7), freeze=self.FREEZE)
        assert a == b

    def test_empty_freeze_matches_default(self) -> None:
        """freeze 为空（显式或默认）→ 与现状行为逐字段一致（非挂起根零变化）。"""
        s = _det_state()
        assert (
            determinize(s, 0, RandomSource(7))
            == determinize(s, 0, RandomSource(7), freeze=frozenset())
        )

    def test_freeze_visible_zones_untouched(self) -> None:
        """冻结下可见区逐卡不动（己方手牌、双方场上/弃牌堆）。"""
        s = _det_state()
        d = determinize(s, 0, RandomSource(7), freeze=self.FREEZE)
        assert d.players[0].hand == s.players[0].hand
        for i in (0, 1):
            assert d.players[i].active == s.players[i].active
            assert d.players[i].bench == s.players[i].bench
            assert d.players[i].discard == s.players[i].discard

    def test_freeze_iid_outside_pool_is_noop(self) -> None:
        """freeze 含不在采样池的 iid（如己方手牌/弃牌堆）→ 无影响。"""
        s = _det_state()
        # 10/11 在 p0 手牌（本就不参与重洗）、300 在 p0 弃牌堆
        a = determinize(s, 0, RandomSource(7), freeze=frozenset({10, 11, 300}))
        b = determinize(s, 0, RandomSource(7))
        assert a == b


# ── setup 期对手场上入池（task 039 WP3，D-039-3）──────────────────────────


def _setup_state() -> GameState:
    """布阵期局面（phase=setup_bench，p0 行动中）：p0 已放战斗场（己方已知），
    p1（对手）已放战斗场 + 1 备战（背面放置 = 隐藏信息）；奖赏尚未设置（为空）。
    p1 池混基础/1 阶/能量/物品，供场上采样有真实分布差异。"""
    p0 = PlayerState(
        deck=tuple(inst(100 + i, basic(f"草{i}")) for i in range(20)),
        hand=(inst(10, basic("火")), inst(11, energy()), inst(12, basic("水"))),
        active=in_play(1, basic("场0")),
        entered_play_this_turn=frozenset({1}),
    )
    p1 = PlayerState(
        deck=tuple(inst(400 + i, basic(f"钢{i}")) for i in range(10))
        + tuple(inst(420 + i, stage1(f"钢一{i}", "钢")) for i in range(4))
        + tuple(inst(430 + i, energy(f"能{i}")) for i in range(6)),
        hand=(
            inst(20, basic("电")),
            inst(21, energy()),
            inst(22, basic("斗")),
            inst(23, item("物品A")),
            inst(24, stage1("电一", "电")),
        ),
        active=in_play(2, basic("场1")),
        bench=(in_play(3, basic("备1")),),
        entered_play_this_turn=frozenset({2, 3}),
    )
    return GameState(
        players=(p0, p1), turn=1, current_player=0, phase="setup_bench", first_player=0,
    )


def _field_iids(p: PlayerState) -> tuple[int, ...]:
    return tuple(
        c.iid for m in ([p.active] if p.active else []) + list(p.bench) for c in m.stack
    )


class TestDeterminizeSetup:
    """D-039-3：setup 期对手场上卡收回采样池，按基础宝可梦子集采样发回原数量。"""

    def test_setup_opponent_field_resampled(self) -> None:
        """对手场上卡跨 world 分布变化（不再恒等于真实布阵 (2,3)）。"""
        s = _setup_state()
        sigs = {
            _field_iids(determinize(s, 0, RandomSource(seed)).players[1])
            for seed in range(10)
        }
        assert len(sigs) > 1  # 跨 world 分布变化（不再恒等于真实布阵 (2,3)）

    def test_setup_field_all_basic_and_count_preserved(self) -> None:
        """发回场上的卡全部为基础宝可梦（supertype=pokemon 且 stage=0），
        场上数量保持（1 战斗场 + 1 备战）。"""
        s = _setup_state()
        for seed in range(10):
            d = determinize(s, 0, RandomSource(seed))
            opp = d.players[1]
            assert opp.active is not None and len(opp.bench) == 1
            for m in (opp.active, *opp.bench):
                assert len(m.stack) == 1
                c = m.current
                assert c.card.supertype == "pokemon" and c.card.stage == 0

    def test_setup_multiset_and_counts_conserved(self) -> None:
        """对手 hand+deck+prizes+场上 合并多重集合守恒；各区/场上计数守恒。"""
        s = _setup_state()
        d = determinize(s, 0, RandomSource(7))
        before = sorted(
            [c.iid for z in ("hand", "deck", "prizes") for c in getattr(s.players[1], z)]
            + list(_field_iids(s.players[1]))
        )
        after = sorted(
            [c.iid for z in ("hand", "deck", "prizes") for c in getattr(d.players[1], z)]
            + list(_field_iids(d.players[1]))
        )
        assert before == after
        opp_s, opp_d = s.players[1], d.players[1]
        assert len(opp_d.hand) == len(opp_s.hand)
        assert len(opp_d.deck) == len(opp_s.deck)
        assert len(opp_d.prizes) == len(opp_s.prizes) == 0
        assert (opp_d.active is not None) + len(opp_d.bench) == 2

    def test_setup_own_side_untouched(self) -> None:
        """己方侧行为不变：手牌/场上逐卡不动，仅 deck+prizes 重洗。"""
        s = _setup_state()
        d = determinize(s, 0, RandomSource(7))
        assert d.players[0].hand == s.players[0].hand
        assert d.players[0].active == s.players[0].active
        assert d.players[0].entered_play_this_turn == frozenset({1})
        assert sorted(c.iid for c in d.players[0].deck) == [
            c.iid for c in s.players[0].deck
        ]

    def test_setup_entered_play_follows_new_field(self) -> None:
        """登场锁定标记随采样后的场上卡走：旧场上 iid 移除、新场上 iid 在位
        （rules-manual §1.1：setup 放置视为刚登场，首回合不可进化）。"""
        s = _setup_state()
        d = determinize(s, 0, RandomSource(7))
        assert d.players[1].entered_play_this_turn == frozenset(
            _field_iids(d.players[1])
        )

    def test_setup_opponent_field_empty_falls_back(self) -> None:
        """对手尚未放置（场上空）：退回普通三区域重洗，不触发场上入池。"""
        s = _setup_state()
        p1 = s.players[1].model_copy(update={
            "active": None, "bench": (), "entered_play_this_turn": frozenset(),
        })
        s = s.model_copy(update={"players": (s.players[0], p1)})
        d = determinize(s, 0, RandomSource(7))
        assert d.players[1].active is None and d.players[1].bench == ()
        before = sorted(
            c.iid for z in ("hand", "deck", "prizes") for c in getattr(s.players[1], z)
        )
        after = sorted(
            c.iid for z in ("hand", "deck", "prizes") for c in getattr(d.players[1], z)
        )
        assert before == after

    def test_setup_same_seed_deterministic(self) -> None:
        """setup 路径同种子同输出（种子确定性硬规矩）。"""
        s = _setup_state()
        assert determinize(s, 0, RandomSource(7)) == determinize(s, 0, RandomSource(7))

    def test_non_setup_phase_field_untouched_contrast(self) -> None:
        """对照：同一局面 phase="main" 时对手场上逐卡不动（非 setup 行为不变）。"""
        s = _setup_state().model_copy(update={"phase": "main"})
        d = determinize(s, 0, RandomSource(7))
        assert d.players[1].active == s.players[1].active
        assert d.players[1].bench == s.players[1].bench
        assert _field_iids(d.players[1]) == (2, 3)
