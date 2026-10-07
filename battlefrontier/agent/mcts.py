"""MCTS 搜索核心（task 034 WP2）：多世界 determinized UCT。

- D-034-1 挂接钩子：``bind_engine(engine)`` 注入真实引擎（play_game 驱动循环在
  observe 前 hasattr 探测调用）；读真实状态的唯一用途是喂 determinizer，搜索全程
  在 determinized 克隆上进行，对手手牌/牌库序/奖赏内容不进决策（信息纪律）。
- D-034-4 搜索形态：每决策采样 worlds 个世界，每世界内独立 UCT（UCB1，c=√2）
  跑 iterations 次；跨世界按根行动访问次数聚合，平手取 legal_actions 序靠前者
  （确定性）。每世界树独立，无跨世界共享/缓存。
- D-034-5 Rollout = HeuristicAgent（params 默认，card_effects 透传；未显式传入时
  沿用挂接引擎的 card_effects）双方打到底；终局计分 根玩家胜 1 / 负 0 / 平 0.5；
  ``state.turn >= 根 turn + rollout_turn_cap`` → 0.5。
- D-034-6/7 随机源：全部随机走自带 _rng 单流——世界克隆与逐迭代克隆的 rng 均
  从 _rng 抽整数派生 RandomSource；零墙钟依赖（预算 = 迭代次数）。
- D-039-2（task 039，修订 D-034-9）挂起根部分决定化：根 state.pending_choice
  非 None 时照常 determinize，freeze = pool_iids ∪ payload——挂起候选池与两段式
  已选部分对选择方全已知（原位冻结，非泄漏），残余隐藏区不再携带真值进搜索。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from battlefrontier.agent.determinize import determinize
from battlefrontier.agent.heuristic import HeuristicAgent
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import GameState, VisibleGameState

__all__ = ["Consideration", "MCTSAgent"]

_UCB_C = math.sqrt(2.0)  # UCB1 探索常数（D-034-4）
_SEED_MOD = 2**63  # 派生种子取值域（_rng 抽整数建 RandomSource）


class _Node:
    """单世界搜索树节点（每世界树独立，不跨世界共享，D-034-4）。

    wins 一律按根玩家视角累计；对手节点在 UCB1 选择时取 1 - mean（零和翻边）。
    展开按 legal_actions 序取首个未尝试行动（确定性，不消费随机源）。
    """

    __slots__ = ("children", "player", "untried", "visits", "wins")

    def __init__(self, player: int, untried: list[Action]) -> None:
        self.player = player  # 本节点行动方
        self.untried = untried
        self.children: dict[Action, _Node] = {}
        self.visits = 0
        self.wins = 0.0


def _score(state: GameState, root_player: int) -> float:
    """终局计分（D-034-5）：根玩家胜 1 / 负 0 / 平（含 force_draw）0.5。"""
    if state.winner is None:
        return 0.5
    return 1.0 if state.winner == root_player else 0.0


def _select_action(legal_actions: list[Action], counts: dict[Action, int]) -> Action:
    """跨世界聚合（D-034-4）：根行动访问次数最高者；平手取 legal_actions 序靠前者
    （max 遇平保留先到者，确定性硬规矩）。"""
    return max(legal_actions, key=lambda a: counts.get(a, 0))


@dataclass(frozen=True)
class Consideration:
    """一次 MCTS 搜索的根统计（task 042，D-042-1）：counts 外化，供 play.py
    驱动循环在 observe 返回后追加 mcts_consider 观测事件。

    considered 只含被访问过的根行动（counts 键集），按 visits 降序（counts 插入
    序确定性保证稳定序）；total_visits = Σvisits（≈ worlds × iterations）；
    chosen = 跨世界聚合选中的行动。唯一合法行动早退路径（无搜索）不产生本记录
    （last_consideration 置 None）。
    """

    turn: int
    phase: str
    player: int
    total_visits: int
    considered: tuple[tuple[Action, int], ...]
    chosen: Action


class MCTSAgent:
    """多世界 determinized UCT Agent（PRD §7.3 / task 034）。

    rng：自带独立随机源（对齐 RandomAgent 偏移先例，D-034-7），引擎随机流零消费；
    worlds / iterations 为搜索预算（D-034-6：禁用墙钟）；rollout_turn_cap 为
    rollout 回合上限（相对根 turn，超限按平局 0.5 计，D-034-5）。
    """

    def __init__(
        self,
        rng: RandomSource,
        *,
        worlds: int = 4,
        iterations: int = 100,
        rollout_turn_cap: int = 50,
        card_effects=None,
    ) -> None:
        if worlds < 1:
            raise ValueError(f"worlds 须 ≥1（收到 {worlds}）")
        if iterations < 1:
            raise ValueError(f"iterations 须 ≥1（收到 {iterations}）")
        if rollout_turn_cap < 1:
            raise ValueError(f"rollout_turn_cap 须 ≥1（收到 {rollout_turn_cap}）")
        self._rng = rng
        self.worlds = worlds
        self.iterations = iterations
        self.rollout_turn_cap = rollout_turn_cap
        self._card_effects = card_effects
        self._engine: GameEngine | None = None
        self._rollout_agent: HeuristicAgent | None = None
        # task 042（D-042-1）：最近一次搜索的根统计；play.py 驱动循环 observe
        # 返回后读取并清空（消费式读取防重复记账）。只读 counts，不改搜索行为
        self.last_consideration: Consideration | None = None

    def bind_engine(self, engine: GameEngine) -> None:
        """D-034-1 挂接钩子：驱动循环在 observe 前调用，注入真实引擎引用。"""
        self._engine = engine

    def observe(self, view: VisibleGameState, legal_actions: list[Action]) -> Action:
        if not legal_actions:
            raise ValueError("无合法行动可选")
        if len(legal_actions) == 1:
            # 唯一选择不消费随机源（确定性）；无搜索 → 无根统计（D-042-1 口径）
            self.last_consideration = None
            return legal_actions[0]
        if self._engine is None:
            raise RuntimeError("MCTSAgent 需先经 bind_engine 挂接引擎（D-034-1）")
        engine = self._engine
        root_player = engine.state.current_player
        root_turn = engine.state.turn
        # D-039-2（task 039，修订 D-034-9）：挂起根也决定化——freeze =
        # pool_iids ∪ payload（挂起池对选择方全已知，冻结原位非泄漏），
        # 残余隐藏区（对手手牌/双方牌库序/奖赏）照常重洗；非挂起根 freeze 为空
        pending = engine.state.pending_choice
        freeze: frozenset[int] = (
            frozenset(pending.pool_iids) | frozenset(pending.payload)
            if pending is not None
            else frozenset()
        )
        counts: dict[Action, int] = {}
        for _ in range(self.worlds):
            world_rng = RandomSource(self._rng.randbelow(_SEED_MOD))
            world = engine.clone(rng=world_rng)
            world.state = determinize(world.state, root_player, world_rng, freeze=freeze)
            root = _Node(root_player, world.legal_actions(root_player))
            # 逐迭代克隆用固定种子（determinization 含未来随机性一并钉死）：
            # 同行动路径回放必达同状态，树边行动恒合法；世界内全确定，
            # 采样差异只跨世界（D-034-4 形态的自然延伸）
            iter_seed = self._rng.randbelow(_SEED_MOD)
            for _ in range(self.iterations):
                self._iterate(world, root, root_player, root_turn, iter_seed)
            for action, child in root.children.items():
                counts[action] = counts.get(action, 0) + child.visits
        chosen = _select_action(legal_actions, counts)
        # D-042-1：根统计外化（只读 counts，不消费随机源、不改搜索行为）
        self.last_consideration = Consideration(
            turn=root_turn, phase=engine.state.phase, player=root_player,
            total_visits=sum(counts.values()),
            considered=tuple(sorted(counts.items(), key=lambda kv: -kv[1])),
            chosen=chosen,
        )
        return chosen

    # ── 单次 UCT 迭代（选择 → 展开 → rollout → 回传）────────────────────

    def _iterate(
        self, world: GameEngine, root: _Node, root_player: int, root_turn: int,
        iter_seed: int,
    ) -> None:
        # 每迭代从世界根克隆独立工作引擎；克隆 rng 用世界内固定种子
        # （回放一致性，D-034-7 单流：iter_seed 来自 _rng）
        work = world.clone(rng=RandomSource(iter_seed))
        node = root
        path = [root]
        while work.state.phase != "game_over":
            if node.untried:
                # 展开：未访问子节点优先（D-034-4），按 legal_actions 序取首
                action = node.untried.pop(0)
                work.apply(node.player, action)
                player = work.state.current_player
                child = _Node(player, work.legal_actions(player))
                node.children[action] = child
                path.append(child)
                break  # 展开节点即进入 rollout
            if not node.children:
                break  # 防御：全展开且无子节点（rollout 侧 force_draw 兜底）
            action = self._ucb_select(node, root_player)
            work.apply(node.player, action)
            node = node.children[action]
            path.append(node)
        result = (
            _score(work.state, root_player)
            if work.state.phase == "game_over"
            else self._rollout(work, root_player, root_turn)
        )
        for n in path:
            n.visits += 1
            n.wins += result

    @staticmethod
    def _ucb_select(node: _Node, root_player: int) -> Action:
        """UCB1（c=√2）选子节点；严格大于才更新 → 同分保留先展开者（确定性）。"""
        log_n = math.log(node.visits)
        best_action: Action | None = None
        best_value = -math.inf
        for action, child in node.children.items():
            mean = child.wins / child.visits
            if node.player != root_player:
                mean = 1.0 - mean  # 对手节点零和翻边
            value = mean + _UCB_C * math.sqrt(log_n / child.visits)
            if value > best_value:
                best_value = value
                best_action = action
        assert best_action is not None  # 调用点已保证 children 非空
        return best_action

    # ── Rollout（D-034-5）──────────────────────────────────────────────

    def _heuristic(self) -> HeuristicAgent:
        """rollout 策略（HeuristicAgent，params 默认）；card_effects 透传构造参数，
        未显式传入时沿用挂接引擎的 DSL 库（公开卡面信息，不违反可见视图纪律）。"""
        if self._rollout_agent is None:
            effects = self._card_effects
            if effects is None and self._engine is not None:
                effects = self._engine.card_effects
            self._rollout_agent = HeuristicAgent(card_effects=effects)
        return self._rollout_agent

    def _rollout(self, engine: GameEngine, root_player: int, root_turn: int) -> float:
        """从展开节点双方 HeuristicAgent 打到底（驱动循环仿 runner/play.py）。"""
        agent = self._heuristic()
        while engine.state.phase != "game_over":
            if engine.state.turn >= root_turn + self.rollout_turn_cap:
                return 0.5  # 回合上限按平局计（D-034-5）
            player = engine.state.current_player
            actions = engine.legal_actions(player)
            if not actions:  # 防御：理论上各阶段必有可选项（仿 play_game）
                engine.force_draw(reason="mcts_rollout_no_legal_actions")
                break
            engine.apply(player, agent.observe(engine.state.visible_state(player), actions))
        return _score(engine.state, root_player)
