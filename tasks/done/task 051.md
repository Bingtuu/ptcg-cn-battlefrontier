# task 051 · M11 WP2：训练器 + 模型资产 + 推理接口

- 状态：进行中
- 关联：M11 设计文档 D-M11-3（岭回归闭式解）/ D-M11-2（特征清单）；task 050 WP1（数据产线）

## 目标

`battlefrontier/learn/`：岭回归训练器（numpy 闭式解，位级确定）+ 模型资产 JSON
（D3-4 进版本控制）+ 推理接口（`predict(view) -> [0,1]`，WP3 接入用）。

## 验收标准（测试清单）

1. **训练确定性**：同数据同代码两跑模型资产逐字节一致（git 版本字段除外——
   若含则对拍时排除）；岭回归闭式解（无迭代随机源）
2. **按局划分**：(pair_index, seed) 为局 id，80/20 训练/验证划分，同局样本不跨集
   （测试断言无交集）；split_seed 钉死进模型 meta
3. **λ 选定**：候选 {0.1, 1, 10, 100} 按验证集 MSE 选定，选择过程确定性
4. **死维度警戒**：验证集 MSE 必须优于常数基线（均值预测器）MSE，否则显式告警
   字段 + 退出码区分（不强行过验收——设计文档 §5 风险口径）
5. **推理接口**：`load_model` + `predict(view)`：特征键序强制校验（模型清单 vs
   FEATURE_NAMES 不符显式报错不猜）→ 标准化 → 点积 → clamp [0,1]
6. 全量 pytest 绿 + ruff 零告警

## 实现要点

- 子代理 TDD + 主会话独立复验
- 模型资产：`models/eval-linear-v1.json`（meta：数据种子区间 / 局数 / 配对数 /
  代码版本 / 卡池 / split_seed / λ / 训练+验证 MSE / 常数基线 MSE）
- CLI：`bfsim train-eval --data results/m11-data --out models/eval-linear-v1.json`
- 正式训练待 WP1 跑批产物到位后由主会话执行

## 追加裁决（2026-10-16 主会话，auto 模式记录，用户可覆议）

- **D-051-1 按局行数上限（确定性子采样）**：正式数据实产 744 万行（每局 ~74 决策点，
  远超设计文档 D-M11-1 的 ~15–20 个估算），纯 Python 全量训练内存/时长不可行。
  设计文档明示「150–200 万样本对线性族充足」→ `train-eval` 增
  `--max-rows-per-game 20`（~2.0M 行，正落设计估算区间）+ `--subsample-seed`，
  按局确定性随机抽样（`random.Random(pair_index×1e6 + seed + subsample_seed)`，
  保原序），缺省 None = 全量行为不变；meta 落账 rows_total / max_rows_per_game /
  subsample_seed（可复算）。标签为局级常量，按局抽行对线性族信息损失小。
- **D-051-2 正规方程上三角优化**：`_ridge_fit` 只累加上三角再镜像（每元素求和次序
  不变，确定性保持），测试内置全量累计参考实现逐位对拍。

## 结果与遗留

- **交付**：`battlefrontier/learn/`（train.py 岭回归闭式解——环境无 numpy 纯 Python
  高斯消元部分主元，位级确定；model.py 资产 JSON `bf-linear-eval-v1` + 双入口
  predict，键序不符显式报错）；CLI `bfsim train-eval`；tests/test_learn_train.py
  38 测 + test_learn_model.py 12 测
- **正式训练（2026-10-16）**：`bfsim train-eval --data results/m11-data --out
  models/eval-linear-v1.json --pool config/target-pool.v1.yml --max-rows-per-game 20`
  → 100,792 局（80633 训练 / 20159 验证，split_seed 20261016）/ 1,977,774 行
  （总 744 万按局抽 ≤20，subsample_seed 20261017）；λ=0.1 选定；**验证 MSE
  0.20564 < 常数基线 0.24685（解释方差 ~16.7%，死维度警戒未触发，warning=null）**；
  训练 MSE 0.20609（训练/验证紧贴，无过拟合迹象）；模型资产
  `models/eval-linear-v1.json` 进版本控制（D3-4）
- **特征重要性**（|权重| 前列）：deck_diff 0.0695 / prize_diff −0.0686 / opp_stage2
  −0.0635 / own_stage1 0.0560 / opp_bench −0.0535 / energy_ready_diff 0.0512
  （face_down_pokemon 常数维度权重精确 0——std 置 1 防除零路径实证）
- **复验**：主会话亲自复跑 pytest 1216 绿 + ruff 零告警；冻结面（tune/、task 050
  文件）git diff 实证干净
- **遗留**：无。学习信号明确（A+B 组特征即可解释 ~17% 结局方差），WP3 接入具备
  前提；分布漂移风险留 M11 报告联动佐证（设计文档 §5）
