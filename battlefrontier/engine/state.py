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
    # 太晶标记（对齐 db cards.is_tera，task 026 WP1；own_tera_in_play 等条件用）
    is_tera: bool = False
    # 主人字段（对齐 db cards.owner：「玛俐的」「N 的」等训练家宝可梦归属；
    # db 未覆盖的主人组（如赫普）保持 None——不回落卡名硬推，不猜）
    owner: str | None = None
    # 机制特质标签（对齐 db effect_tags.labels：古代/未来/一击/连击等，db PRD v1.23 契约键）
    labels: tuple[str, ...] = ()


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
    # 攻击冷却锁（task 026 WP4 裁决 2，lock_attack 原语）：被锁招式名 + 锁定施加时的
    # turn（解禁时点见 core._begin_turn；撤退/离场/昏厥清除，进化继承——决议口径待核）
    attack_locks: tuple[str, ...] = ()
    attack_lock_turn: int | None = None
    # 撤退锁（task 026 WP6 沙铃仙人掌 穷追不舍，D-WP6-6）：被锁目标下个自己回合无法撤退
    # （回合结束 core._on_turn_end 解除；进化/离场清除）
    retreat_lock: bool = False

    @property
    def current(self) -> CardInstance:
        return self.stack[-1]


class PendingChoice(FrozenModel):
    """挂起的效果执行（chooser 机制，PRD §5.2）：等待 Agent 选择，恢复信息全在此。

    Effect 树不入状态——恢复时按来源卡身份（card_id；朴素 dict 兼容路径按卡名）
    + effect_index 从 card_effects 重取，cursor 指向扁平步骤（cost 段在前，actions 段在后）。
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
    # 挂起瞬间冻结的 cost 段弃置 iid（task 026 WP4：恢复时重建
    # ctx.cost_discarded_iids，供 recover_from_discard exclude_cost_discarded 池剔除）
    cost_discarded: tuple[int, ...] = ()
    # 挂起瞬间冻结的本效果前序弃置张数（task 026 WP5：恢复时重建
    # ctx.discarded_this_effect，供 damage 的 discarded_this_effect 计数词读取）
    discarded_count: int = 0
    # 有序选择（task 026 WP6 暗码迷的解读 deck_top 去向）：选择顺序即牌顶顺序（FIFO），
    # 枚举层按排列展开（(a,b) 与 (b,a) 是两条合法行动）
    ordered: bool = False
    # 互异约束（task 026 WP6 赤松 distinct=energy_type）：pool_buckets 与 pool_iids
    # 平行（同下标），枚举层仅产出桶值两两互异的子集
    distinct: str = ""
    pool_buckets: tuple[int, ...] = ()
    # 二选一组合约束（task 026 WP6 小刚的发掘 choose_groups）：元素 = (组池 iids,
    # 组内 up-to 上限)；组间互斥（混合不可达），枚举层按组分别展开子集再取并集
    choose_groups: tuple[tuple[tuple[int, ...], int], ...] = ()
    # 完成模式：trainer = 效果完成后本体进弃牌区；ability = 特性不弃置
    completion: str = "trainer"
    # 嵌套帧（task 020 copy_attack）：inner = 内层效果定位（card_id, 卡名, 招式名）
    # ——card_id 供 CardLibrary 精确解析、卡名供朴素 dict 兼容路径与事件展示；
    # 非空时 cursor/payload 属内层；outer_cursor/outer_choice = 外层 copy 节点游标
    # 与已消费的招式选择（内层完成后带 inner_done 标记恢复外层，不重复执行内层）
    inner: tuple[str, str, str] | None = None
    outer_cursor: int = -1
    outer_choice: tuple[int, ...] = ()
    # 挂起瞬间冻结的攻击方栈顶 iid（task 026 WP6 own_ko_by_attack，同 flip/
    # cost_discarded/discarded_count 穿透口径：恢复时重建 ctx.attacker_iid，
    # 供 place_damage_counters 的 opponent_attacker 选择器在恢复后继续读取）
    attacker_iid: int | None = None


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
    # 回合级奖赏加成标记（task 026 WP5 白蕾雅，D-WP5-2 🔲 待核）：本回合自己太晶
    # 宝可梦招式伤害致对手战斗场昏厥时多拿 1 张奖赏；回合结束 _on_turn_end 清除
    extra_prize_tera_ko: bool = False

    @model_validator(mode="after")
    def _zone_limits(self) -> PlayerState:
        if len(self.bench) > 8:
            # 规则上限 5；零之大空洞（task 026 WP6）覆写为 8——构造期守卫取绝对上限
            raise ValueError("备战区最多 8 只（零之大空洞覆写上限）")
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
    # 等待换上的玩家队列（task 026 WP2，FIFO）：效果内昏厥的换上推迟到效果全部结算
    # 完毕后按队列统一进行（D-WP2-1，🔲 待核）；多昏厥按结算顺序入队逐条换上（D-WP2-2）。
    # check_knockouts / ko_self 入队，_do_promote 逐条弹出
    promote_queue: tuple[int, ...] = ()
    # 换上队列清空后的去向（task 026 WP2，D-WP2-4：归并 task 025 的 promote_to_main）：
    # (玩家, 阶段)，本期值恒为 (回合方, "main")——效果致昏厥/bounce 换上后回效果方主阶段
    resume_after_promotes: tuple[int, str] | None = None
    # 待分发的事件触发队列（task 026 WP3，用户裁决 2026-09-07，FIFO）：DSL 进化路径
    # （神奇糖果 skip_stage 等 _apply_evolution zone="hand"）的 own_evolve_from_hand
    # 触发请求入队，效果完成后由 _run_or_suspend 完成路径统一排水（与 promote_queue
    # 同哲学：不在效果执行中嵌套分发）；元素 = (player, card_iid, event)，
    # 排水时来源已不在场上则跳过（离场即失效）
    pending_event_triggers: tuple[tuple[int, int, str], ...] = ()
    # 待分发的昏厥触发队列（task 026 WP6 沙铃仙人掌 炸裂针刺，D-WP6-6，FIFO）：
    # own_ko_by_attack——战斗场受对手招式伤害昏厥时入队，效果完成后统一排水；
    # 元素 = (被昏厥方, 被昏厥宝可梦栈顶 iid, 攻击方栈顶 iid | None（无来源招式
    # 路径不入队——_knockout_one 判 None 跳过）)；排水时来源（已昏厥）
    # 从弃牌区解析，攻击方已离场则效果内 no-op
    pending_ko_triggers: tuple[tuple[int, int, int | None], ...] = ()
    # 备战区失效缩减（task 026 WP6 零之大空洞，D-WP6-2）：bench_shrink 阶段的待缩减
    # 玩家队列（FIFO，双方同缩由旧竞技场持有者先）与缩减完成后的去向
    # （"main"=回出牌方主阶段 / "begin_turn"=换上后开始该方回合）
    bench_shrink_queue: tuple[int, ...] = ()
    bench_shrink_resume: tuple[int, str] | None = None
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
