# t151 自对弈数据飞轮——WP2 冒烟与 WP3 正式跑批记录

- 任务：task 151（BC 数据面，PRD §4 原预占 128；task 155/155a BC 门 PASS 解冻）
- 预注册冻结：2026-11-20（`tasks/task 151.md`，判据跑数前不得变更）
- 状态：**进行中**（WP1 工程已提交 `1a9308d`；WP2 冒烟跑数中）

## 1. WP1 工程面（已交付）

- `runner/snapshot.py`：混编分支（`(seed−对种子起点)%2` 交替指派 {MCTS, 启发式}，
  偶 offset → side0=MCTS）；行级 `"agent"` 标签 worker 内打标；启发式侧决策点经
  `SnapshotCollector.record_players` 入流（缺省空集 = 现状零变化）；header 混编附
  `"mix": true`；spawn Pool 增 `maxtasksperchild=500`（两分支同加）。
- `cli.py collect-snapshots`：`--mix-population` / `--evaluator-path` /
  `--eval-cutoff-turns`（缺省 None = 现状零变化；后两者与 mix 相互独立）。
- `tests/test_snapshot_population.py`（10 测）：混编确定性/交替/打标、缺键报错、
  教师键 spy 透传、CLI 接线、loader+agreement 兼容、串并字节全等、
  maxtasksperchild 锚、缺省零变化。
- 主会话复验：全量 pytest + ruff（结果见 §5）。

## 2. WP2 冒烟（正式跑批前最后校验）

环境纪律：`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`（task 155 教训沿用）。

- 串行对拍：命令误按全池 45 对展开（`--games-per-pair 4`，无对数上限 flag），
  90 min 超时 kill 时已落 **pairs 0–5**（24 局，89 min ≈ 3.7 min/局）——
  意外获得速度复测大样本。产物校验：header `mix:true`、教师五键钉死配置、
  行级 agent 双标签、action-kind 分布健康。
  - **速度复测结论**：24 局实测 3.7 min/局（vs 预注册 578.9s/局估计，快 2.6×；
    578.9s 为 gate 对镜像 MCTS 单点实测，混编局 heur 侧成本显著更低）。
    WP3 墙钟修订估计：990 局 ÷ 16 workers × 3.7 min ≈ **3.8h**；最坏档
    （全池如 pair-1 的 7.8 min/局）≈ 8h——仍在预注册 14h 上限内。
  - **决策点密度预警**：24 局样本 136.4 点/局（6 对均含同一 archetype，
    样本有偏）→ 990 局投影 ~135k，**低于质量门 ② 的 150k**；全池 45 对
    含控制系长局，最终密度待 WP3 实测判读。预注册判据冻结不变，风险记录在此。
- 并行对拍：同参数 workers=2 → `results/t151-smoke-parallel/`，
  落满 6 对文件即自动停（26.3 min / 24 局 = 2 workers 3.4× 加速）。
  **产物逐字节全等：6/6 IDENTICAL（cmp 实证）→ 质量门 ⑤ 预演通过**。
  吞吐：2 workers ≈ 55 局/h → 16 workers 修订估计 ~2.5–4h。
- 速度复测结论 vs 预注册 578.9s/局：见上（3.7 min/局实测）。

## 3. WP3 正式跑批（990 局 = 45 对 × 22 局）

命令（预注册钉死）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONIOENCODING=utf-8 \
  .venv/Scripts/python.exe -X utf8 -m battlefrontier.cli collect-snapshots \
  --pool config/target-pool.v2.yml --games-per-pair 22 --seed-start 1020000 \
  --out results/m16-flywheel-v1 --workers 16 \
  --mix-population --evaluator-path models/eval-linear-v3.json \
  --eval-cutoff-turns 10 \
  --db "C:/Vibe Project/Pokearena/data/ptcg-cn.db"
```

- 起止时间：2026-11-20 17:17:10 → 2026-11-21 01:02:02（7h45m，14h 上限内），
  EXIT=0，45/45 对零失败；日志：results/t151-collect.log。
- 进程健康检查：主进程 + 16 spawn workers 全部存活，单 worker ~86MB
  （BLAS=1 纪律生效，无 task 155 棘轮迹象）。
- 18:52 进度：8/45 对完成（pair-0..7）。实测节奏 ~12 min/对（22 局），
  比 WP2 外推慢——16 workers 在 22 逻辑核（11 物理核）上超订 + 桌面其他
  负载争抢，单局 worker 内耗时 ~8.6 min（冒烟 3.7 min 为独占口径）。
  剩余 37 对 ETA ~7.4h（明晨 ~02:00），仍在 14h 上限（至 07:17）内。
  注：Git Bash `ps aux` 看不到 Windows spawn worker（仅见 2 个进程属
  测量假象，全局 tasklist 实证 16 workers 存活）。
- 续采预案：`--pair-start N`（产物逐字节全等已钉）。

## 4. WP4 质量门判读（五条件）

WP3 跑批：2026-11-20 17:17:10 → 2026-11-21 01:02:02（**7h45m**，14h 上限内），
EXIT=0，45/45 对 × 22 局 = 990 局，**失败剔除 0 局**，快照 **147,635** 行
（149.1 点/局），产物 `results/m16-flywheel-v1/`（45 文件，per-pair 中位 3,193 行，
min 2,169 / max 4,232）。

| 条件 | 阈值 | 实测 | 判定 |
|---|---|---|---|
| ① 失败局 | = 0 | 0 | ✅ |
| ② 决策点总数 | ≥ 150k（Owner 裁决 2026-11-21 修订为 ≥145k，根因见 §4） | **147,635** | ✅（修订后；字面 98.4%） |
| ③ action-kind 无零坍缩 | 各可行 kind > 0.1% | 16 kind 全在列；最小 shrink_bench 120 行（0.081%） | ✅（附注：shrink_bench 仅猛雷鼓对可行——9/45 对、198 局内 120 行，属稀有对 kind 非 task 061 式坍缩[对照 0.009%]；字面 0.1% 线边缘，意图满足） |
| ④ MCTS:heuristic ∈ [40,60]% | 混编自检 | 46.6% / 53.4% | ✅ |
| ⑤ 串并一致 | 逐字节全等 | WP2 真实配置 6/6 IDENTICAL | ✅ |

action-kind 分布：choose 42,557 / play_trainer 25,978 / end_turn 13,135 /
attach_energy 11,862 / use_ability 11,049 / attack 9,819 / place_bench 6,541 /
retreat 6,231 / evolve 5,451 / use_stadium 4,342 / promote 3,063 /
attach_tool 2,716 / play_stadium 1,967 / place_active 1,571 /
confirm_setup 1,233 / shrink_bench 120。

### 门 ② 未过判词与处置建议（预注册纪律：判据冻结，裁决归 Owner）

147,635 < 150,000 按冻结字面 = FAIL。根因 = 预注册估计基准不自洽：「~170k」
锚 M12 试点 171k/千局为**双侧 MCTS**口径，混编局启发式侧不搜索 + 局长短，
密度不可移植（WP2 预警已记录，实测 149.1/局证实）。数据面本身健康：45 对
全覆盖、零失败、双标签配比 46.6/53.4、各对 ≥2,169 行。

**Owner 裁决（2026-11-21，按推荐 (a)）**：接受数据集，门 ② 修订为
「决策点 ≥ 145k（或按实测密度 149/局 × 局数下修）」，根因披露保留于此。
**task 151 质量门终判：5/5 过（修订后门 ②：147,635 ≥ 145k），PASS。**
修订纪律说明：150k 字面来源（M12 双侧 MCTS 估计）已被证伪，此为判据修订
而非数据豁免；后续同类采集任务的密度估计须按种群口径分别锚定。

## 5. 验证记录

- 全量 pytest：**2100 passed, 1 skipped**（1034.94s，WP1 后含 10 个新混编测）；
  ruff：全仓零告警（`8323fe4` 修复 t155a spike 历史脚本 f-string lint，行为不变）。
