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


class AttackDef(FrozenModel):
    """招式定义（rules-manual §6）：成本为能量属性符号列表（"无"=无色，任意属性可抵）。

    damage=None 表示纯效果招式，效果文本走 DSL on_attack（task 009+）；
    白板期只枚举有伤害的招式。
    """

    name: str
    cost: tuple[str, ...] = ()
    damage: int | None = None
    # 伤害修饰符（开放字符串：+/- /× 等，对齐 db damage_modifier；白板结算忽略，DSL 结算时用）
    damage_modifier: str | None = None


class CardDef(FrozenModel):
    """卡定义：规则骨架所需字段（属性/招式/弱点抗性/规则盒），效果留空给 DSL。"""

    card_id: str
    name: str
    supertype: Supertype
    hp: int | None = None
    stage: int = 0
    evolves_from: str | None = None
    # 进化链标识（db evolution_chain_id；跳阶进化的同链判定用，如神奇糖果。
    # 链拓扑是数据不是规则——引擎不硬编码任何卡名/链关系）
    evolution_chain: str | None = None
    # 宝可梦属性 / 能量卡属性（开放字符串，对齐 db 词表；rules-manual §1.1/§1.2）
    energy_type: str | None = None
    # 基本能量标记（对齐 db is_basic_energy；撤退/效果过滤器用，如「基本能量」回收）
    is_basic_energy: bool = False
    attacks: tuple[AttackDef, ...] = ()
    retreat_cost: int = 0
    # 弱点/抗性属性（rules-manual §6：弱点 ×2 / 抗性 -30）
    weakness: str | None = None
    resistance: str | None = None
    # 规则盒标记（开放字符串：ex/V/VSTAR/VMAX/光辉…，rules-manual §1.4）→ 昏厥奖赏张数
    rule_box: str | None = None
    # 训练家卡子类（开放字符串：物品/支援者/竞技场/宝可梦道具）；M2 起随效果落地扩字段
    trainer_subtype: str | None = None
    # ACE SPEC 标记（对齐 db is_ace_spec；规则：每卡组限 1 张 ACE SPEC，rules-reference 附录 A）
    is_ace_spec: bool = False


class CardInstance(FrozenModel):
    """对局内卡实例：iid 局内唯一；同名卡可有多实例。"""

    iid: int
    card: CardDef


class InPlayPokemon(FrozenModel):
    """场上宝可梦：进化链（底→顶，栈顶为当前形态）+ 附着能量 + 伤害 + 特殊状态。"""

    stack: tuple[CardInstance, ...]
    attached_energy: tuple[CardInstance, ...] = ()
    # 宝可梦道具（rules-manual §5：每只限 1 个；昏厥随整叠进弃牌区）
    attached_tool: CardInstance | None = None
    damage: int = 0
    conditions: frozenset[SpecialCondition] = frozenset()

    @property
    def current(self) -> CardInstance:
        return self.stack[-1]


class PendingChoice(FrozenModel):
    """挂起的效果执行（chooser 机制，PRD §5.2）：等待 Agent 选择，恢复信息全在此。

    Effect 树不入状态——恢复时按 (source.card.name, effect_index) 从 card_effects
    重取，cursor 指向扁平步骤（cost 段在前，actions 段在后）。
    pool/filters/min~max/destination 供合法选择枚举，无需重跑原语。
    """

    player: int
    source: CardInstance
    effect_index: int
    cursor: int
    pool: str                              # own_hand / own_deck / own_discard / own_pokemon_in_play
    filters: tuple[str, ...] = ()
    min_choose: int = 0
    max_choose: int = 1
    destination: str | None = None
    # 挂起瞬间解析冻结的候选池（choice 阶段状态不变，池不会漂移）
    pool_iids: tuple[int, ...] = ()
    # 同节点两段式选择的中间结果（task 011，如 attach_energy 已选的能量 iids）
    payload: tuple[int, ...] = ()
    # 挂起瞬间冻结的掷币结果（task 025 节点级门控穿透：恢复时重建 ctx.last_flip）
    flip_result: bool | None = None
    # 完成模式：trainer = 效果完成后本体进弃牌区；ability = 特性不弃置
    completion: str = "trainer"
    # 嵌套帧（task 020 copy_attack）：inner = 内层效果定位（DSL 文档卡名, 招式名），
    # 非空时 cursor/payload 属内层；outer_cursor/outer_choice = 外层 copy 节点游标
    # 与已消费的招式选择（内层完成后带 inner_done 标记恢复外层，不重复执行内层）
    inner: tuple[str, str] | None = None
    outer_cursor: int = -1
    outer_choice: tuple[int, ...] = ()


class PlayerState(FrozenModel):
    deck: tuple[CardInstance, ...] = ()
    hand: tuple[CardInstance, ...] = ()
    discard: tuple[CardInstance, ...] = ()
    prizes: tuple[CardInstance, ...] = ()
    active: InPlayPokemon | None = None
    bench: tuple[InPlayPokemon, ...] = ()
    # 每回合规则标记（回合结束重置）：能量附着 / 支援者 / 撤退 / 登场 / 已进化（存场上宝可梦栈顶 iid）
    energy_attached_this_turn: bool = False
    supporter_played_this_turn: bool = False
    retreated_this_turn: bool = False
    entered_play_this_turn: frozenset[int] = frozenset()
    evolved_this_turn: frozenset[int] = frozenset()
    # 特性限次（task 011）：once_per_turn 按栈顶 iid；once_per_turn_shared 按卡名（如「化危为吉」）
    abilities_used_this_turn: frozenset[int] = frozenset()
    shared_abilities_used_this_turn: frozenset[str] = frozenset()
    # 跨回合标记（task 017）：「上一个对手的回合」内我方宝可梦被昏厥（化危为吉条件）；
    # 昏厥发生时 owner != current_player 置位，我方回合结束清除
    own_ko_during_opponent_turn: bool = False
    # 竞技场（task 017）：每回合限打出 1 张 / stadium_grant 行动每回合 1 次
    stadium_played_this_turn: bool = False
    stadium_used_this_turn: bool = False

    @model_validator(mode="after")
    def _zone_limits(self) -> PlayerState:
        if len(self.bench) > 5:
            raise ValueError("备战区最多 5 只")
        if len(self.prizes) > 6:
            raise ValueError("奖赏卡最多 6 张")
        return self


class VisibleOpponentState(FrozenModel):
    """对手可见视图：手牌/牌库/奖赏只剩数量；弃牌堆与场上公开（PRD §6.3）。

    布阵阶段（setup）双方宝可梦背面放置：active/bench 内容隐藏，
    只公开已放置数量 face_down_pokemon（rules-reference §1）。
    """

    hand_count: int
    deck_count: int
    prizes_count: int
    discard: tuple[CardInstance, ...]
    active: InPlayPokemon | None
    bench: tuple[InPlayPokemon, ...]
    face_down_pokemon: int = 0


class VisibleSelfState(FrozenModel):
    """自己可见视图：手牌/弃牌堆/场上全量 + 回合规则标记；

    牌库顺序与奖赏卡内容对 Agent 隐藏（PRD §6.3：牌库对引擎确定、对 Agent 隐藏；
    奖赏卡背面放置，双方均不可见内容，只余数量）。
    """

    hand: tuple[CardInstance, ...]
    deck_count: int
    prizes_count: int
    discard: tuple[CardInstance, ...]
    active: InPlayPokemon | None
    bench: tuple[InPlayPokemon, ...]
    energy_attached_this_turn: bool
    supporter_played_this_turn: bool
    retreated_this_turn: bool
    entered_play_this_turn: frozenset[int]
    evolved_this_turn: frozenset[int]
    abilities_used_this_turn: frozenset[int]
    shared_abilities_used_this_turn: frozenset[str]
    stadium_played_this_turn: bool
    stadium_used_this_turn: bool


class VisibleGameState(FrozenModel):
    """Agent 可见视图：自己侧隐藏牌库顺序/奖赏卡内容 + 对手侧隐藏手牌/牌库/奖赏内容。

    pending_pool：chooser 挂起时向选择方揭示的检索池内容（仅当池在非公开区域，
    如牌库检索——rules-manual §3：检索时选择方可查看牌库选卡；对手视图恒 None）。
    """

    own: VisibleSelfState
    opponent: VisibleOpponentState
    stadium: CardInstance | None
    turn: int
    current_player: int
    phase: str
    pending_pool: tuple[CardInstance, ...] | None = None


class GameState(FrozenModel):
    players: tuple[PlayerState, PlayerState]
    stadium: CardInstance | None = None
    turn: int = 1
    current_player: int = 0
    phase: str = "setup"
    first_player: int = 0
    winner: int | None = None
    is_draw: bool = False
    pending_choice: PendingChoice | None = None
    # 换上后回合权归属（默认 None = 换上方回合，普通昏厥语义）；
    # 混乱反面自我昏厥时置为对手（攻击已消耗，D1 决议 task 013），_do_promote 读后清零
    turn_after_promote: int | None = None
    # 主阶段内换上标记（task 025 bounce：效果致战斗场空置时置位）——
    # 换上后回 main 继续当前回合（不推进回合、不抽牌），_do_promote 读后清零
    promote_to_main: bool = False
    # 竞技场放置方（task 017：旧竞技场被替换时进其放置方弃牌区，rules-manual §5）
    stadium_owner: int | None = None

    def visible_state(self, player: int) -> VisibleGameState:
        own = self.players[player]
        opp = self.players[1 - player]
        face_down = self.phase in ("setup_active", "setup_bench")
        # chooser 挂起：仅向选择方揭示非公开区域（牌库）的检索池内容
        pending_pool = None
        pc = self.pending_choice
        if pc is not None and pc.player == player and pc.pool == "own_deck":
            by_iid = {c.iid: c for c in own.deck}
            pending_pool = tuple(by_iid[i] for i in pc.pool_iids)
        return VisibleGameState(
            own=VisibleSelfState(
                hand=own.hand,
                deck_count=len(own.deck),
                prizes_count=len(own.prizes),
                discard=own.discard,
                active=own.active,
                bench=own.bench,
                energy_attached_this_turn=own.energy_attached_this_turn,
                supporter_played_this_turn=own.supporter_played_this_turn,
                retreated_this_turn=own.retreated_this_turn,
                entered_play_this_turn=own.entered_play_this_turn,
                evolved_this_turn=own.evolved_this_turn,
                abilities_used_this_turn=own.abilities_used_this_turn,
                shared_abilities_used_this_turn=own.shared_abilities_used_this_turn,
                stadium_played_this_turn=own.stadium_played_this_turn,
                stadium_used_this_turn=own.stadium_used_this_turn,
            ),
            opponent=VisibleOpponentState(
                hand_count=len(opp.hand),
                deck_count=len(opp.deck),
                prizes_count=len(opp.prizes),
                discard=opp.discard,
                active=None if face_down else opp.active,
                bench=() if face_down else opp.bench,
                face_down_pokemon=(
                    (1 if opp.active else 0) + len(opp.bench) if face_down else 0
                ),
            ),
            stadium=self.stadium,
            turn=self.turn,
            current_player=self.current_player,
            phase=self.phase,
            pending_pool=pending_pool,
        )
