"""GameState 数据模型（PRD §6.1 / §6.3）。

不可变（frozen Pydantic）+ 可序列化；对局推进一律产出新状态。
卡定义（CardDef）与卡实例（CardInstance）分离：引擎对卡牌内容零硬编码，
白板期卡定义是 stub，M2 起由数据层 + DSL 供给。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


class Supertype(StrEnum):
    POKEMON = "pokemon"
    ENERGY = "energy"
    TRAINER = "trainer"


class SpecialCondition(StrEnum):
    POISONED = "poisoned"
    BURNED = "burned"
    ASLEEP = "asleep"
    PARALYZED = "paralyzed"
    CONFUSED = "confused"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class CardDef(FrozenModel):
    """卡定义（白板期 stub）：只含规则骨架所需字段，效果留空给 DSL。"""

    card_id: str
    name: str
    supertype: Supertype
    hp: int | None = None
    stage: int = 0
    attack_damage: int | None = None
    retreat_cost: int = 0


class CardInstance(FrozenModel):
    """对局内卡实例：iid 局内唯一；同名卡可有多实例。"""

    iid: int
    card: CardDef


class InPlayPokemon(FrozenModel):
    """场上宝可梦：进化链（底→顶，栈顶为当前形态）+ 附着能量 + 伤害 + 特殊状态。"""

    stack: tuple[CardInstance, ...]
    attached_energy: tuple[CardInstance, ...] = ()
    damage: int = 0
    conditions: frozenset[SpecialCondition] = frozenset()

    @property
    def current(self) -> CardInstance:
        return self.stack[-1]


class PlayerState(FrozenModel):
    deck: tuple[CardInstance, ...] = ()
    hand: tuple[CardInstance, ...] = ()
    discard: tuple[CardInstance, ...] = ()
    prizes: tuple[CardInstance, ...] = ()
    active: InPlayPokemon | None = None
    bench: tuple[InPlayPokemon, ...] = ()

    @model_validator(mode="after")
    def _zone_limits(self) -> PlayerState:
        if len(self.bench) > 5:
            raise ValueError("备战区最多 5 只")
        if len(self.prizes) > 6:
            raise ValueError("奖赏卡最多 6 张")
        return self


class VisibleOpponentState(FrozenModel):
    """对手可见视图：手牌/牌库/奖赏只剩数量；弃牌堆与场上公开（PRD §6.3）。"""

    hand_count: int
    deck_count: int
    prizes_count: int
    discard: tuple[CardInstance, ...]
    active: InPlayPokemon | None
    bench: tuple[InPlayPokemon, ...]


class VisibleGameState(FrozenModel):
    """Agent 可见视图：自己全量 + 对手过滤后。"""

    own: PlayerState
    opponent: VisibleOpponentState
    stadium: CardInstance | None
    turn: int
    current_player: int
    phase: str


class GameState(FrozenModel):
    players: tuple[PlayerState, PlayerState]
    stadium: CardInstance | None = None
    turn: int = 1
    current_player: int = 0
    phase: str = "setup"

    def visible_state(self, player: int) -> VisibleGameState:
        opp = self.players[1 - player]
        return VisibleGameState(
            own=self.players[player],
            opponent=VisibleOpponentState(
                hand_count=len(opp.hand),
                deck_count=len(opp.deck),
                prizes_count=len(opp.prizes),
                discard=opp.discard,
                active=opp.active,
                bench=opp.bench,
            ),
            stadium=self.stadium,
            turn=self.turn,
            current_player=self.current_player,
            phase=self.phase,
        )
