# task 079 · 能量贴到再贴一张就付清的目标

- 状态：实现已进 PR（单测绿）。Q4 = 否，Task 2b 未做。100 局云端跳过（无 `ptcg-cn.db`）
- 关联：规格 D-078-6、Q4；计划 Task 2（不是 Task 2b）；077 的 `_energy_role`；078 已合入 main `30d8d352`
- 依赖：单测不依赖 078。本机 100 局要在 078 已落地的默认开关上跑，否则附着变化和撤退变化拆不开。对照是 078 默认开（A92/B8），不是全关

## 目标

手牌里这一张能量，优先贴到「贴上之后有一招从付不起变成付得起、且那招有效伤害最高」的宝可梦。战斗场小招已经能打、大招还差两张以上，备战差一张就能打时，能量给备战。

这是对「能量常堆在莱希拉姆」的假说 F：`_pick_energy_attach` 今天只要战斗场还有任何没付清的印面招式，就继续喂战斗场。莱希拉姆这个名字不进代码。纯真火焰是【火】【火】【雷】【无】，力量愤怒是【火】【雷】（`cards/N的莱希拉姆.yml`）。

## 验收标准（测试清单）

`tests/test_heuristic_energy_target.py`（计划 Task 2 有完整草稿）：

- [x] 战斗场：1 费 20 伤已付清，4 费 170 伤未付清。备战：2 费 120 伤、已附 1。手牌 1 张无色。默认开关 → `attach_energy` 的 `target_iid` 是备战
- [x] 同一局面 `energy_target_gate=False` → `target_iid` 是战斗场
- [x] 手牌弹药型且战斗场已能打（D-032-5，抄 `tests/test_agent_dsl_estimate.py` 的夹具）→ `_pick_energy_attach` 仍返回 None
- [x] `tests/test_heuristic_ability_gate.py` 与 `tests/test_agent_dsl_estimate.py` 断言不改
- [x] `energy_target_gate` 不进 tune 的 10 维

Q4 默认否，下面这条**不要写**，除非规格改成要读：

- [ ] （仅 Q4 = 是）印面 5【无】、`modify_attack_cost` 的 `value: opponent_taken_prizes`、对手已拿 2 奖、身上 3 能 → 视为已付清，能量去点亮差一张的备战。卡名用 stub，招式名与 `args.attack` 对齐即可。不调用 `GameEngine._effective_attack_cost`

本机 100 局：复用 `experiments/t078-gard-zoro.example.yml`（078 创建）。对照 078 默认开的那次，不是对照全关。

- `attach_energy.detail.target` 里高费用第二招的宝可梦占比下降（方向）
- 暗夜王牌、血月的局触及率相对 078 那次上升（血月若没动，记下来，不要在 Q4 未批时改减费去凑）
- 失败局 0
- 胜率写实

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t079-gard-zoro.db
bfsim report <id> --results results/t079-gard-zoro.db --decisions
```

云端无库则跳过，结果节写明。

## 实现要点

- 新字段 `energy_target_gate: bool = True`
- 复用 `_mon_energy_role` / `_energy_role`（077）。`0` 表示贴一张就付清
- 伤害与弱点口径见计划 Task 2 Step 3。打分用的视图不写回引擎
- 没有任何 `enable` 目标时，函数余下部分保持今天的 `needs_energy`（战斗场优先，否则最高 `pokemon_score` 的未就绪备战）
- 第一刀不读 `modify_attack_cost`，不读 `provide_energy`（D-WP8-5）

## 结果与遗留

- **拍板**：Q4 = 否。不读血月 / `modify_attack_cost`，不做计划 Task 2b。`pokemon_score` 公式不动，`tests/test_features.py` 期望未改。零卡名例外。费用继续印面 `_energy_satisfied` / `_energy_role`（D-WP8-5），不读 `provide_energy`。不改 DSL / 引擎。不跑矩阵
- **实现**：`HeuristicParams.energy_target_gate = True`，不进 tune（`len(search_space())==10`，`test_tune_space.py` 的 `bool_fields` 含该字段）。`_pick_energy_attach` 在现有「手牌弹药且战斗场已能打 → None」之后：开关开且存在 `_mon_energy_role==0` 的目标时，按 `_newly_enabled_damage` 最高、战斗场优先、iid 升序选 `target_iid`。没有 enable 目标时，`needs_energy` 语义不变。`_newly_enabled_damage` 只取 `enable` 招式；`estimate_attack_damage` 为 None 时用印面伤害；弱点 ×2 / 抗性用该宝可梦 `energy_type`，打分视图是 `_view_as_active` 副本，不写回引擎
- **红→绿**：实现前 `test_attach_to_bench_that_becomes_ready_not_active_second_attack` 实际 `target_iid==1`；`energy_target_gate=False` 因字段不存在 `TypeError`；手牌弹药测试在实现前已通过（旧行为）。实现后上述三条与 `test_agent_dsl_estimate.py` / `test_heuristic_ability_gate.py` / `test_heuristic_board_gate.py` / `test_tune_space.py` / `test_features.py` 同批绿，`ruff check .` 零告警。077 / 078 旧断言未改
- **本机 100 局**：云端无 `ptcg-cn.db`，**跳过 `bfsim`**。父代理在 Diupi-Yun 跑（对照 078 默认开 A92/B8，不是全关）。结构看 `attach_energy.detail.target`、暗夜王牌 / 血月局触及率；失败必须 0；胜率写实。本刀单独不要求进 60–75%（三刀叠完才算，D-078-9）

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t079-gard-zoro.db
bfsim report <id> --results results/t079-gard-zoro.db --decisions
```

- 080 的复制目标与复燃计数不在本任务。矩阵 / 索罗亚克整行 / 500 局不在本任务。代理不合并
