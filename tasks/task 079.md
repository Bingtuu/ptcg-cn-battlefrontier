# task 079 · 能量贴到再贴一张就付清的目标

- 状态：规划（待 owner review；本文件不授权改 `heuristic.py`）
- 关联：规格 D-078-6、Q4；计划 Task 2（Task 2b 仅 Q4 = 要读减费时做）；077 的 `_energy_role`
- 依赖：单测不依赖 078。本机 100 局要在 078 已落地的默认开关上跑，否则附着变化和撤退变化拆不开

## 目标

手牌里这一张能量，优先贴到「贴上之后有一招从付不起变成付得起、且那招有效伤害最高」的宝可梦。战斗场小招已经能打、大招还差两张以上，备战差一张就能打时，能量给备战。

这是对「能量常堆在莱希拉姆」的假说 F：`_pick_energy_attach` 今天只要战斗场还有任何没付清的印面招式，就继续喂战斗场。莱希拉姆这个名字不进代码。纯真火焰是【火】【火】【雷】【无】，力量愤怒是【火】【雷】（`cards/N的莱希拉姆.yml`）。

## 验收标准（测试清单）

`tests/test_heuristic_energy_target.py`（计划 Task 2 有完整草稿）：

- [ ] 战斗场：1 费 20 伤已付清，4 费 170 伤未付清。备战：2 费 120 伤、已附 1。手牌 1 张无色。默认开关 → `attach_energy` 的 `target_iid` 是备战
- [ ] 同一局面 `energy_target_gate=False` → `target_iid` 是战斗场
- [ ] 手牌弹药型且战斗场已能打（D-032-5，抄 `tests/test_agent_dsl_estimate.py` 的夹具）→ `_pick_energy_attach` 仍返回 None
- [ ] `tests/test_heuristic_ability_gate.py` 与 `tests/test_agent_dsl_estimate.py` 断言不改
- [ ] `energy_target_gate` 不进 tune 的 10 维

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

- 未实现
- 080 的复制目标与复燃计数不在本任务
- 矩阵不在本任务
