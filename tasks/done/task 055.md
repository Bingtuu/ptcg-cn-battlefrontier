# task 055 · M11 锚2 满预算验证格：2×50 K=10 双侧 MCTS+评估器

- 状态：进行中
- 关联：task 054 分解结论（双学生格 -10.6pts 全部来自预算减半 2×50→2×25，
  评估器净效应 0.0pts）；2026-10-18 用户拍板选项 B（补跑满预算验证格，
  证据链闭环后 M11 终判）+ 锚 1 相对口径确认（相对教师自一致率天花板，
  选档 2×25 K=10 两格均值 100.2% ≥ 0.85 → 达成）

## 背景

task 054 在 2×25 低预算档证明评估器净效应为零（118/118 完全对称，
χ²=0.00），但「预算充足档（2×50 K=10）评估器净效应是否亦为零」仍是
外推。本任务直接跑满预算验证格：双侧 MCTS 2×50 + eval_cutoff_turns=10
（eval-linear-v1），与基准 m11-postfix.db exp 1（双侧 MCTS 2×50 K=0
纯搜索，62.0%）同种子区间 CRN 对齐，直接测满预算档评估器净效应。

## 跑批步骤

1. 实验定义 `experiments/m11-gholdengo-gardevoir-fullbudget-2x50k10.example.yml`：
   双侧 MCTS worlds=2 iterations=50 eval_cutoff_turns=10
   evaluator_path=models/eval-linear-v1.json；decks a=沙奈朵(mik_moe:644634)
   b=赛富豪(mik_moe:655513)；games 500；seed_start 102500
   （与基准/消融/学生格同区间，CRN 对齐）
2. 后台跑批：`bfsim run <yml> --workers 16 --results results/m11-fullbudget.db`
   （timeout 6h；预估 4–5h）
3. CI 分析：`bash .kimi-code/m11-anchor2-ci.sh results/m11-fullbudget.db 1
   results/m11-postfix.db 1 "post-fix基准62.0%"`（Wilson + CRN 成对 +
   McNemar）；关注净效应 CI 是否覆盖 0
4. 报告 `docs/m11-learned-evaluator-report.md` §4 锚 2 段补满预算格一行
   → M11 里程碑终判呈报用户（拍板点）

## 验收标准

1. 跑批 500/500 零失败；experiment meta 回显当前 code_version / 数据版本 /
   种子区间（102500..102999）
2. CI 分析双口径（独立 Wilson + CRN 成对 McNemar）落 `.kimi-code/` 结果档
3. 报告 §4 锚 2 段补满预算格一行 + 终判依据更新
4. 零代码变更（纯跑批任务）；全量 pytest 绿 + ruff 零告警复核
5. M11 里程碑终判呈报用户（拍板点不变）

## 结果与遗留

- 跑批 500/500 零失败（2026-10-18 06:15 本地完成，墙钟 ~4.5h @16 workers，
  6h 超时线内）；meta 回显 code_version=bf65bd5+dirty（= c7bb588 引擎零差异，
  diff 仅实验 yml + task 档）、数据版本 2026-09-16 (user_version=13)、
  种子 102500..102999，与基准 CRN 全对齐（公共种子 500/500）
- **满预算验证格结果**：赛富豪侧（学生 2×50 K=10 + eval-linear-v1）胜
  332/500 = **66.4%**，Wilson CI95 [0.6215, 0.7040]；基准 62.0%（310/500，
  m11-postfix.db exp 1）贴边不在学生 CI 内（方向为学生更高）。
  **CRN 成对复核**：不一致对 210（学生多赢 116 / 多输 94），成对差 +0.0440，
  CI95 [-0.0128, +0.1008] **覆盖 0**，McNemar χ²=2.30（p≈0.13）——
  满预算档评估器净效应与 0 相容，task 054 低预算档结论（净效应 0.0pts）
  外推成立
- 局均长佐证：满预算学生 20.8 ≈ 基准 21.2（预算复原后对局形态复原；
  2×25 档 19.4/19.6 确为预算效应，与评估器无关）
- **锚 2 终判**：按「同预算评估器净效应」口径**达成**——双学生格 -10.6pts
  全部来自预算减半（搜索预算问题），学得评估器本身在两档预算下均零失真。
  报告 §4 锚 2 段已补满预算格 bullet + 终判段重写；锚 1 段更新为
  「相对口径达成（2026-10-18 用户拍板确认）」
- pytest 1252 全绿 + ruff 零告警复核通过（纯跑批零代码变更，基线不变）
- 分析数据：`.kimi-code/m11-task055-results.md`（CI 输出 + 局均长 + meta）
- 遗留：选档 2×25 K=10 的降本用法须带「预算-胜率权衡」注记（降本档在慢速
  双侧格胜率代价 -10.6pts 属预算效应）；M11 里程碑终判呈报 + M12 立项
  （torch 依赖开口裁决）随本任务归档一并呈报用户
