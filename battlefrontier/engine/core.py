"""规则引擎核心：阶段机 + 合法行动枚举 + 白板推进（PRD §6.2 / §6.4）。

规则事实源：PTCG 简中官方规则书 + 官方 Q&A，逐条在代码注释标注出处。
白板范围：不执行任何卡面效果，宝可梦只有 HP / 固定伤害招式 / 撤退费用。
"""

from __future__ import annotations

from battlefrontier.engine.actions import Action, IllegalActionError
from battlefrontier.engine.events import GameEvent
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    CardDef,
    CardInstance,
    GameState,
    InPlayPokemon,
    PlayerState,
    Supertype,
)


class GameEngine:
    """持有随机源与事件流；状态本身不可变，apply/new_game 产出新 GameState。"""

    def __init__(self, rng: RandomSource) -> None:
        self.rng = rng
        self.events: list[GameEvent] = []
        self.state: GameState

    # ── 事件 ─────────────────────────────────────────────

    def _emit(self, kind: str, player: int | None = None, **detail: object) -> None:
        self.events.append(
            GameEvent(
                seq=len(self.events),
                turn=self.state.turn,
                phase=self.state.phase,
                player=player,
                kind=kind,
                detail=detail,
            )
        )

    # ── 开局（规则书「游戏的准备」）─────────────────────────

    def new_game(self, deck_a: list[CardDef], deck_b: list[CardDef]) -> GameState:
        """掷币定先后手 → 洗牌 → 起手 7 → mulligan → 奖赏 6 → 布阵。

        【规则出处·游戏准备】掷币胜方先攻（白板简化：胜方固定先攻，
        让先选择权留待 Agent 层）；双方起手 7 张，无基础宝可梦须展示手牌、
        洗回重抽（mulligan），对手可按 mulligan 次数抽牌（白板自动化，
        选择权留待 Agent 层）；奖赏卡 6 张。
        """
        self.events = []
        decks: list[tuple[CardInstance, ...]] = []
        for cards in (deck_a, deck_b):
            base = len(decks) * 10000  # 双方实例 id 区间隔离
            instances = tuple(CardInstance(iid=base + i, card=c) for i, c in enumerate(cards))
            decks.append(self.rng.shuffle(instances))

        first = 0 if self.rng.flip_coin() else 1
        players = [PlayerState(deck=decks[0]), PlayerState(deck=decks[1])]
        self.state = GameState(
            players=(players[0], players[1]), turn=0, current_player=0,
            phase="setup", first_player=first,
        )
        self._emit("coin_flip", None, first_player=first)

        # 起手 7 + mulligan（规则书·游戏准备）
        hands: list[tuple[CardInstance, ...]] = []
        mulligan_counts = [0, 0]
        for idx in range(2):
            deck, hand = players[idx].deck[:7], ()
            hand = players[idx].deck[:7]
            deck = players[idx].deck[7:]
            while not any(c.card.supertype == Supertype.POKEMON and c.card.stage == 0 for c in hand):
                mulligan_counts[idx] += 1
                self._emit("mulligan", idx)
                deck = self.rng.shuffle(deck + hand)
                hand, deck = deck[:7], deck[7:]
            hands.append(hand)
            players[idx] = players[idx].model_copy(update={"deck": deck, "hand": hand})

        # 对手按 mulligan 次数抽牌（白板自动化：默认抽）
        for idx in range(2):
            bonus = mulligan_counts[1 - idx]
            if bonus:
                p = players[idx]
                players[idx] = p.model_copy(update={
                    "hand": p.hand + p.deck[:bonus],
                    "deck": p.deck[bonus:],
                })
                self._emit("mulligan_bonus_draw", idx, count=bonus)

        # 奖赏卡 6 张（规则书·游戏准备）
        for idx in range(2):
            p = players[idx]
            players[idx] = p.model_copy(update={
                "prizes": p.deck[:6],
                "deck": p.deck[6:],
            })
        self.state = self.state.model_copy(update={"players": (players[0], players[1])})
        self._emit("setup_ready", None)
        self.state = self.state.model_copy(update={"phase": "setup_active", "current_player": 0})
        return self.state

    # ── 合法行动枚举（PRD §6.2）────────────────────────────

    def legal_actions(self, player: int) -> list[Action]:
        s = self.state
        if s.phase == "game_over" or player != s.current_player:
            return []
        p = s.players[player]
        if s.phase == "setup_active":
            return [
                Action(kind="place_active", iid=c.iid)
                for c in p.hand
                if c.card.supertype == Supertype.POKEMON and c.card.stage == 0
            ]
        if s.phase == "setup_bench":
            actions = [
                Action(kind="place_bench", iid=c.iid)
                for c in p.hand
                if c.card.supertype == Supertype.POKEMON and c.card.stage == 0
            ] if len(p.bench) < 5 else []
            return actions + [Action(kind="confirm_setup")]
        if s.phase == "promote":
            # 【规则书·昏厥】战斗场昏厥后须从备战区换上 1 只
            return [Action(kind="promote", bench_index=i) for i in range(len(p.bench))]
        if s.phase == "main":
            return self._main_actions(player)
        return []

    def _main_actions(self, player: int) -> list[Action]:
        s = self.state
        p = s.players[player]
        actions: list[Action] = []
        in_play: list[InPlayPokemon] = ([p.active] if p.active else []) + list(p.bench)

        # 进化：每只每回合限 1 次；登场/已进化当回合不可再进化（规则书·进化）
        for c in p.hand:
            if c.card.supertype == Supertype.POKEMON and c.card.stage >= 1:
                for t in in_play:
                    top = t.current
                    if (
                        c.card.evolves_from == top.card.name
                        and top.iid not in p.entered_play_this_turn
                        and top.iid not in p.evolved_this_turn
                    ):
                        actions.append(Action(kind="evolve", iid=c.iid, target_iid=top.iid))

        # 能量：每回合限附着 1 张（规则书·能量）
        if not p.energy_attached_this_turn:
            for c in p.hand:
                if c.card.supertype == Supertype.ENERGY:
                    for t in in_play:
                        actions.append(
                            Action(kind="attach_energy", iid=c.iid, target_iid=t.current.iid)
                        )

        # 撤退：弃撤退费用数量的能量，与备战区对换（规则书·撤退）
        if (
            p.active
            and p.bench
            and len(p.active.attached_energy) >= p.active.current.card.retreat_cost
        ):
            for i in range(len(p.bench)):
                actions.append(Action(kind="retreat", bench_index=i))

        # 攻击：能量足够；先攻方第一回合不能攻击（规则书·回合的进行）
        first_turn_ban = s.turn == 1 and player == s.first_player
        if (
            p.active
            and p.active.current.card.attack_damage is not None
            and len(p.active.attached_energy) >= p.active.current.card.attack_cost
            and not first_turn_ban
        ):
            actions.append(Action(kind="attack"))

        actions.append(Action(kind="end_turn"))
        return actions

    # ── 推进 ─────────────────────────────────────────────

    def apply(self, player: int, action: Action) -> GameState:
        legal = self.legal_actions(player)
        if action not in legal:
            raise IllegalActionError(f"{action} 不在合法行动列表中")
        handler = getattr(self, f"_do_{action.kind}")
        handler(player, action)
        return self.state

    def _set_player(self, idx: int, p: PlayerState) -> None:
        players = list(self.state.players)
        players[idx] = p
        self.state = self.state.model_copy(update={"players": (players[0], players[1])})

    def _take_from_hand(self, p: PlayerState, iid: int) -> tuple[PlayerState, CardInstance]:
        card = next(c for c in p.hand if c.iid == iid)
        return p.model_copy(update={"hand": tuple(c for c in p.hand if c.iid != iid)}), card

    def _do_place_active(self, player: int, action: Action) -> None:
        """【规则出处·游戏准备】起手必须选择 1 只基础宝可梦放战斗场。"""
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        active = InPlayPokemon(stack=(card,))
        self._set_player(player, p.model_copy(update={
            "active": active,
            "entered_play_this_turn": p.entered_play_this_turn | {card.iid},
        }))
        self._emit("place_active", player, iid=card.iid, name=card.card.name)
        self.state = self.state.model_copy(update={"phase": "setup_bench"})

    def _do_place_bench(self, player: int, action: Action) -> None:
        """【规则出处·游戏准备】备战区可放任意只基础宝可梦（≤5）。"""
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        self._set_player(player, p.model_copy(update={
            "bench": p.bench + (InPlayPokemon(stack=(card,)),),
            "entered_play_this_turn": p.entered_play_this_turn | {card.iid},
        }))
        self._emit("place_bench", player, iid=card.iid, name=card.card.name)

    def _do_confirm_setup(self, player: int, action: Action) -> None:
        if player == 0:
            self.state = self.state.model_copy(update={"phase": "setup_active", "current_player": 1})
        else:
            self._begin_turn(self.state.first_player, first_turn=True)

    # ── 主阶段行动（规则书「回合的进行」）────────────────────

    def _find_in_play(self, p: PlayerState, top_iid: int) -> tuple[str, int, InPlayPokemon]:
        """按栈顶 iid 定位场上宝可梦：返回 (位置, bench 下标, 对象)。"""
        if p.active and p.active.current.iid == top_iid:
            return "active", -1, p.active
        for i, b in enumerate(p.bench):
            if b.current.iid == top_iid:
                return "bench", i, b
        raise IllegalActionError(f"场上不存在栈顶 iid={top_iid} 的宝可梦")

    def _replace_in_play(self, p: PlayerState, slot: str, idx: int, new: InPlayPokemon) -> PlayerState:
        if slot == "active":
            return p.model_copy(update={"active": new})
        bench = list(p.bench)
        bench[idx] = new
        return p.model_copy(update={"bench": tuple(bench)})

    def _do_evolve(self, player: int, action: Action) -> None:
        """【规则书·进化】手牌进化卡覆盖到对应宝可梦上，特殊状态恢复，伤害保留。"""
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        slot, idx, target = self._find_in_play(p, action.target_iid)  # type: ignore[arg-type]
        evolved = target.model_copy(update={
            "stack": target.stack + (card,),
            "conditions": frozenset(),
        })
        p = self._replace_in_play(p, slot, idx, evolved)
        self._set_player(player, p.model_copy(update={
            "evolved_this_turn": p.evolved_this_turn | {card.iid},
        }))
        self._emit("evolve", player, iid=card.iid, name=card.card.name, onto=target.current.card.name)

    def _do_attach_energy(self, player: int, action: Action) -> None:
        """【规则书·能量】每回合限 1 张，从手牌附着到场上宝可梦。"""
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        slot, idx, target = self._find_in_play(p, action.target_iid)  # type: ignore[arg-type]
        p = self._replace_in_play(p, slot, idx, target.model_copy(update={
            "attached_energy": target.attached_energy + (card,),
        }))
        self._set_player(player, p.model_copy(update={"energy_attached_this_turn": True}))
        self._emit("attach_energy", player, iid=card.iid, target=target.current.card.name)

    def _do_retreat(self, player: int, action: Action) -> None:
        """【规则书·撤退】弃撤退费用数量的能量，与备战区对换，撤退方特殊状态恢复。"""
        p = self.state.players[player]
        active = p.active
        cost = active.current.card.retreat_cost
        discarded = active.attached_energy[:cost]
        retreated = active.model_copy(update={
            "attached_energy": active.attached_energy[cost:],
            "conditions": frozenset(),
        })
        new_active = p.bench[action.bench_index]  # type: ignore[index]
        bench = list(p.bench)
        bench[action.bench_index] = retreated  # type: ignore[index]
        self._set_player(player, p.model_copy(update={
            "active": new_active,
            "bench": tuple(bench),
            "discard": p.discard + discarded,
        }))
        self._emit("retreat", player, out=retreated.current.card.name,
                   into=new_active.current.card.name, paid=cost)

    def _do_attack(self, player: int, action: Action) -> None:
        """【规则书·招式】固定伤害（白板）；攻击后回合结束。昏厥结算见 _resolve_knockout。"""
        s = self.state
        atk = s.players[player].active
        dmg = atk.current.card.attack_damage
        defender = 1 - player
        d = s.players[defender]
        target = d.active.model_copy(update={"damage": d.active.damage + dmg})
        self._set_player(defender, d.model_copy(update={"active": target}))
        self._emit("attack", player, name=atk.current.card.name, damage=dmg,
                   target=target.current.card.name)
        if self._resolve_knockout(attacker=player, defender=defender):
            return  # 游戏已结束或等待换上
        self._begin_turn(defender)

    def _resolve_knockout(self, attacker: int, defender: int) -> bool:
        """昏厥判定：返回 True 表示攻击方回合不再正常结束（终局或待换上）。

        【规则书·昏厥/胜负】伤害 ≥ HP 昏厥 → 整叠（进化链+能量）进弃牌堆，
        对手拿 1 张奖赏卡；拿完 6 张奖赏卡立即获胜；无备战区可换上判负。
        """
        d = self.state.players[defender]
        active = d.active
        if active.damage < (active.current.card.hp or 0):
            return False
        knocked = active.stack + active.attached_energy
        self._set_player(defender, d.model_copy(update={
            "active": None, "discard": d.discard + knocked,
        }))
        self._emit("knockout", defender, name=active.current.card.name)

        a = self.state.players[attacker]
        if a.prizes:
            self._set_player(attacker, a.model_copy(update={
                "hand": a.hand + a.prizes[:1], "prizes": a.prizes[1:],
            }))
            self._emit("take_prize", attacker, left=len(self.state.players[attacker].prizes))
        if not self.state.players[attacker].prizes:
            self._game_over(winner=attacker, reason="prizes")
            return True
        d = self.state.players[defender]
        if not d.bench:
            self._game_over(winner=attacker, reason="no_pokemon")
            return True
        self.state = self.state.model_copy(update={
            "phase": "promote", "current_player": defender,
        })
        return True

    def _do_promote(self, player: int, action: Action) -> None:
        p = self.state.players[player]
        new_active = p.bench[action.bench_index]  # type: ignore[index]
        bench = p.bench[: action.bench_index] + p.bench[action.bench_index + 1 :]  # type: ignore[index]
        self._set_player(player, p.model_copy(update={"active": new_active, "bench": bench}))
        self._emit("promote", player, name=new_active.current.card.name)
        self._begin_turn(player)

    def _do_end_turn(self, player: int, action: Action) -> None:
        self._emit("end_turn", player)
        self._begin_turn(1 - player)

    def _begin_turn(self, player: int, first_turn: bool = False) -> None:
        """回合开始：重置回合标记 → 抽牌（牌库空判负，规则书·胜负判定）。"""
        turn = 1 if first_turn else self.state.turn + (1 if player == self.state.first_player else 0)
        p = self.state.players[player]
        p = p.model_copy(update={
            "energy_attached_this_turn": False,
            "entered_play_this_turn": frozenset(),
            "evolved_this_turn": frozenset(),
        })
        self._set_player(player, p)
        self.state = self.state.model_copy(update={
            "turn": turn, "current_player": player, "phase": "draw",
        })
        if not p.deck:
            self._emit("deck_out", player)
            self._game_over(winner=1 - player, reason="deck_out")
            return
        p = self.state.players[player]
        self._set_player(player, p.model_copy(update={
            "hand": p.hand + p.deck[:1], "deck": p.deck[1:],
        }))
        self._emit("draw", player, iid=p.deck[0].iid, name=p.deck[0].card.name)
        self.state = self.state.model_copy(update={"phase": "main"})

    def _game_over(self, winner: int | None, reason: str, is_draw: bool = False) -> None:
        self.state = self.state.model_copy(update={
            "phase": "game_over", "winner": winner, "is_draw": is_draw,
        })
        self._emit("game_over", winner, reason=reason, is_draw=is_draw)
