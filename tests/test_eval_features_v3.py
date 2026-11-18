"""task 155 WP1：评估器特征层 v3 验收测试（预注册判据冻结于 tasks/task 155.md）。

v3 动机：task 150 FAIL 归因 = M11 30 维特征层对 v2.x 新机制状态失明 → 扩维
到 560（36 基座 + 4 区 × 131 词表）。本测试覆盖冻结判据：

- `EVAL_V3_BASE_NAMES == FEATURE_NAMES + DISCARD_FEATURE_NAMES`（M11 30 维
  原序 + 弃牌构成 6 维原序，两个既有常量只读复用，D-062-1 纪律）；
- `eval_v3_names(vocab)` 布局：前 36 维 = 基座，其后 = `cid_<区>_<卡名>`，
  区序 = EVAL_V3_ZONES、卡名序 = 传入 vocab 序；
- 4 区计数：own_hand 卡名计数；own_board / opp_board = active+bench 的
  进化栈 + 附着能量 + 附着道具（复用 policy_features._pokemon_cards 口径）；
  stadium = 在场竞技场 one-hot（无场全零）；
- 词表外卡名显式 ValueError（不猜纪律）；
- 对手手牌身份零泄漏：对手手牌内容不可见，词表外卡名在其中不得报错、
  不得出现在任何 cid_ 特征（对手侧只有基座维 opp_hand_count）；
- 纯函数确定性：同一视图两次调用逐位相等、键序钉死；零随机源、零引擎调用。
"""

from __future__ import annotations

import pytest
from helpers import basic, energy, inst, stage1

from battlefrontier.agent import eval_features
from battlefrontier.agent.eval_features import (
    EVAL_V3_BASE_NAMES,
    EVAL_V3_ZONES,
    eval_v3_names,
    feature_vector_v3,
)
from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.agent.policy_features import (
    DISCARD_FEATURE_NAMES,
    _pokemon_cards,
    policy_state_features,
)
from battlefrontier.engine.state import CardDef, GameState, InPlayPokemon, PlayerState

# 词表（刻意非字典序，验证「键序 = 传入 vocab 序」而非隐式排序）；
# 「梦幻」在词表中但局面里不出现（零计数锚）。
VOCAB = ("小火龙", "基本能量", "妙蛙草", "梦幻", "妙蛙种子", "攀岩装备", "神山")

STADIUM_CARD = CardDef(card_id="stub-神山", name="神山", supertype="trainer",
                       trainer_subtype="竞技场")
TOOL_CARD = CardDef(card_id="stub-攀岩装备", name="攀岩装备", supertype="trainer",
                    trainer_subtype="道具")


def _pokemon(stack: tuple, energies: int = 0, tool: CardDef | None = None,
             start_iid: int = 0) -> InPlayPokemon:
    """场上宝可梦夹具：进化栈 + start_iid 起附着能量 + 可选道具。"""
    return InPlayPokemon(
        stack=tuple(inst(start_iid + i, c) for i, c in enumerate(stack)),
        attached_energy=tuple(
            inst(start_iid + 100 + j, energy()) for j in range(energies)),
        attached_tool=inst(start_iid + 200, tool) if tool is not None else None,
    )


def rich_state(stadium: CardDef | None = STADIUM_CARD) -> GameState:
    """main 阶段富局面：进化栈/附着/道具/备战/弃牌/对手手牌秘密卡全覆盖。"""
    own = PlayerState(
        deck=tuple(inst(300 + i, basic("妙蛙种子")) for i in range(5)),
        hand=(inst(50, basic("小火龙")), inst(51, energy()),
              inst(52, basic("妙蛙种子"))),
        discard=(inst(60, energy()),),
        prizes=tuple(inst(200 + i, basic("妙蛙种子")) for i in range(6)),
        active=_pokemon((basic("妙蛙种子"), stage1("妙蛙草", "妙蛙种子")),
                        energies=2, tool=TOOL_CARD, start_iid=1),
        bench=(_pokemon((basic("小火龙"),), energies=1, start_iid=10),),
    )
    opponent = PlayerState(
        deck=tuple(inst(400 + i, basic("小火龙")) for i in range(5)),
        # 对手手牌两张「对手秘密卡」：视图只暴露 hand_count，身份不可见
        hand=(inst(70, basic("对手秘密卡")), inst(71, basic("对手秘密卡"))),
        discard=(inst(80, basic("小火龙")),),
        prizes=tuple(inst(500 + i, basic("小火龙")) for i in range(6)),
        active=_pokemon((basic("小火龙"),), energies=1, start_iid=20),
        bench=(_pokemon((basic("妙蛙种子"),), start_iid=30),),
    )
    return GameState(
        players=(own, opponent), stadium=inst(90, stadium) if stadium else None,
        turn=3, current_player=0, phase="main", first_player=0,
    )


# ── 基座与清单（只读复用锚）────────────────────────────────────


class TestBaseNames:
    def test_基座等于M11原序加弃牌原序(self) -> None:
        assert EVAL_V3_BASE_NAMES == FEATURE_NAMES + DISCARD_FEATURE_NAMES
        assert len(FEATURE_NAMES) == 30  # M11 清单逐键序被入库资产锚定
        assert len(DISCARD_FEATURE_NAMES) == 6
        assert len(EVAL_V3_BASE_NAMES) == 36

    def test_区序钉死(self) -> None:
        assert EVAL_V3_ZONES == ("own_hand", "own_board", "opp_board", "stadium")

    def test_私有函数复用是同一对象(self) -> None:
        # import 私有 _pokemon_cards 复用（口径单一来源），本测试覆盖该 import
        assert eval_features._pokemon_cards is _pokemon_cards


# ── 清单布局 ─────────────────────────────────────────────────


class TestNames:
    def test_布局前36维基座其后按区按词表序(self) -> None:
        names = eval_v3_names(VOCAB)
        assert names[:36] == EVAL_V3_BASE_NAMES
        expected_tail = tuple(
            f"cid_{zone}_{name}"
            for zone in EVAL_V3_ZONES
            for name in VOCAB
        )
        assert names[36:] == expected_tail
        assert len(set(names)) == len(names)  # 无重复键

    def test_布局无重复键防词表重名(self) -> None:
        with pytest.raises(ValueError, match="重复"):
            eval_v3_names(("小火龙", "小火龙"))


# ── 4 区计数口径 ─────────────────────────────────────────────


class TestZoneCounts:
    def test_键序等于清单序(self) -> None:
        view = rich_state().visible_state(0)
        feats = feature_vector_v3(view, VOCAB)
        assert tuple(feats) == eval_v3_names(VOCAB)

    def test_基座36维与policy_state_features逐一相等(self) -> None:
        view = rich_state().visible_state(0)
        feats = feature_vector_v3(view, VOCAB)
        base = policy_state_features(view)
        assert len(base) == 36
        for key, value in base.items():
            assert feats[key] == value

    def test_己方手牌卡名计数(self) -> None:
        view = rich_state().visible_state(0)
        feats = feature_vector_v3(view, VOCAB)
        assert feats["cid_own_hand_小火龙"] == 1.0
        assert feats["cid_own_hand_基本能量"] == 1.0
        assert feats["cid_own_hand_妙蛙种子"] == 1.0
        assert feats["cid_own_hand_妙蛙草"] == 0.0
        assert feats["cid_own_hand_神山"] == 0.0

    def test_己方盘面计数含进化栈附着与道具(self) -> None:
        view = rich_state().visible_state(0)
        feats = feature_vector_v3(view, VOCAB)
        # active 进化栈：妙蛙种子（底）+ 妙蛙草（顶）各 1
        assert feats["cid_own_board_妙蛙种子"] == 1.0
        assert feats["cid_own_board_妙蛙草"] == 1.0
        # 附着能量：active 2 + bench 1 = 3；道具 1；bench 小火龙 1
        assert feats["cid_own_board_基本能量"] == 3.0
        assert feats["cid_own_board_攀岩装备"] == 1.0
        assert feats["cid_own_board_小火龙"] == 1.0
        # 手牌不进盘面区
        assert feats["cid_own_board_梦幻"] == 0.0

    def test_对手盘面计数(self) -> None:
        view = rich_state().visible_state(0)
        feats = feature_vector_v3(view, VOCAB)
        assert feats["cid_opp_board_小火龙"] == 1.0  # active
        assert feats["cid_opp_board_妙蛙种子"] == 1.0  # bench
        assert feats["cid_opp_board_基本能量"] == 1.0  # active 附着
        assert feats["cid_opp_board_攀岩装备"] == 0.0

    def test_竞技场onehot(self) -> None:
        view = rich_state().visible_state(0)
        feats = feature_vector_v3(view, VOCAB)
        assert feats["cid_stadium_神山"] == 1.0
        assert feats["cid_stadium_小火龙"] == 0.0
        # 弃牌（公开区）只进基座 6 维，不进任何 cid_ 区
        assert feats["cid_own_board_基本能量"] == 3.0  # 弃牌能量未被计入

    def test_无竞技场全场零(self) -> None:
        view = rich_state(stadium=None).visible_state(0)
        feats = feature_vector_v3(view, VOCAB)
        assert all(v == 0.0 for k, v in feats.items() if k.startswith("cid_stadium_"))
        assert feats["stadium_in_play"] == 0.0

    def test_词表中但局面未出现的卡全零(self) -> None:
        view = rich_state().visible_state(0)
        feats = feature_vector_v3(view, VOCAB)
        assert all(v == 0.0 for k, v in feats.items() if k.endswith("_梦幻"))


# ── 词表外 / 信息纪律 / 确定性 ───────────────────────────────


class TestDiscipline:
    def test_词表外卡名显式报错(self) -> None:
        state = rich_state()
        p0 = state.players[0].model_copy(
            update={"hand": (inst(99, basic("超梦")),)})
        view = state.model_copy(
            update={"players": (p0, state.players[1])}).visible_state(0)
        with pytest.raises(ValueError, match="词表"):
            feature_vector_v3(view, VOCAB)

    def test_对手手牌身份零泄漏(self) -> None:
        """对手手牌内容视图不可见：秘密卡不得报错、不得出现在任何 cid_ 特征。"""
        view = rich_state().visible_state(0)
        feats = feature_vector_v3(view, VOCAB)  # 「对手秘密卡」不在词表也不报错
        assert not any("对手秘密卡" in k for k in feats)
        # 对手侧只有基座维 opp_hand_count 承载手牌信息
        assert feats["opp_hand_count"] == 2.0
        # 己方视角可见即计数（词表扩入该名后不再词表外）
        own_view = rich_state().visible_state(1)
        own_feats = feature_vector_v3(own_view, VOCAB + ("对手秘密卡",))
        assert own_feats["cid_own_hand_对手秘密卡"] == 2.0

    def test_纯函数确定性逐位相等(self) -> None:
        view = rich_state().visible_state(0)
        first = feature_vector_v3(view, VOCAB)
        second = feature_vector_v3(view, VOCAB)
        assert first == second
        assert all(isinstance(v, float) for v in first.values())
