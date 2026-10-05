# task 039：MCTS 信息泄漏修复——带冻结集的部分 determinize

来源：全库 code review R3 组 Important #2/#3（主会话已读码复核成立）。两条泄漏同属
「determinize 隐藏区模型覆盖不全」：

- **#2 挂起根泄漏**（agent/mcts.py:110-117）：`pending_choice` 非 None 时
  `determinize_root=False`，世界克隆携带真实对手手牌/双方牌库序/奖赏进搜索，
  rollout 按真实 topdeck 与奖赏内容结算 = 系统性泄漏（D-034-9 只论证了选择池
  已知，未覆盖残余隐藏区）。
- **#3 布阵期泄漏**（agent/determinize.py:8-10）：「场上=可见区逐卡不动」前提在
  setup 阶段不成立——`state.py:334` 已有判定 `face_down = phase in
  ("setup_active","setup_bench")`，对手布阵是隐藏信息却被当真值结算，且对手
  采样池漏掉已放置的卡（多重集合与选择方信息态不一致）。

## 设计决议

- **D-039-1（冻结集机制）**：`determinize(state, player, rng, freeze=frozenset())`
  ——冻结 iid 的卡保持原区域原位置（位置语义保留：own_deck 检视池在牌顶 N 张，
  挂起期间不漂移），其余隐藏区照常重洗切回。实现 = 每区域 mask 冻结位 → 洗非
  冻结部分 → 原位回填。多重集合守恒不变式保持。
- **D-039-2（挂起根改部分 determinize）**：mcts.py 不再跳过——挂起根调用
  `determinize(..., freeze=pool_iids ∪ payload)`。信息论依据：pool 取值仅
  own_hand/own_deck/own_discard/own_pokemon_in_play 四类（state.py:131），候选
  池在挂起瞬间对选择方全已知（选择事件必须展示候选），冻结非泄漏；payload
  （两段式选择已选部分，task 011）同理已知。
- **D-039-3（setup 期对手场上卡入池）**：phase ∈ {setup_active, setup_bench}
  且对手场上非空时，对手场上卡收回采样池（与 hand+deck+prizes 合并），先按
  「基础宝可梦」子集采样发回场上原数量（约束：setup 只能放基础宝可梦；池含
  真实多重集合故基础数必然够），剩余重洗按原区域大小切回 hand/deck/prizes。
  己方场上/手牌已知不动。revealed 记忆不建模的 D-034-3 口径不变。
- **D-039-4（口径分界）**：修复改变搜索行为——M8c/M10 历史 MCTS 数字带旧口径
  （泄漏只让 MCTS 偏强，修复后归因结论方向更硬，不重跑全量）；task 文档与
  STATUS.md 标注分界。修复后跑一次小局数冒烟确认零崩溃。

## 验收标准

1. freeze 集原位保持 + 非冻结区多重集合守恒（同种子同输出）。
2. 挂起根 determinize 后 pool_iids/payload 全部原位可恢复，choice 合法性不破
   （带 chooser 卡的 MCTS 端到端对局零失败——如能量输送PRO/暗码迷的解读）。
3. setup 期对手场上卡跨 world 分布变化（不再恒等于真实布阵）且均为基础宝可
   梦；非 setup 期行为不变。
4. 串/并行一致性回归（小局数对拍）+ 全量 pytest 绿 + ruff 零告警。
5. determinize 模块 docstring 与 tasks/done/task 034.md 的 D-034-9 表述同步
   （注明 task 039 修订）。
