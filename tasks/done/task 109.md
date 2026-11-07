# task 109 · M12 残留盲区触发式闭环——诊断预检（零行为改动）

日期：2026-11-07 · 类型：诊断预检（只读分析，不改 Agent/DSL/引擎）· 分支：`task/t109-blindspot`
goal：M12 残留盲区触发式闭环（2026-11-07 用户拍板启动）

## 动机

M12 残留盲区 backlog 三项：**use_ability 使用质量 / play_stadium / end_turn**。
task 066 已证伪「批量重训 / per-kind 重加权」路线（剂量-响应单调、锚 2 恶化），
用户拍板**触发式处理**：观察到具体错决策才修。触发 = 本任务的诊断预检。

## 数据源（全部既有资产，零新对局 / 零 MCTS）

| 库 | 内容 |
|---|---|
| `results/m14-{drag-zoro,drag-joltik,char-grim}-mcts.db` | 各 100 局 2×50 MCTS 教师对局，共 300 局、55k `mcts_consider` 决策点 |
| `results/m14-*-heuristic.db` | 同种子启发式自对局（对照轴） |

margin 口径（task 099 遗留 tooling 纪律）：`chosen_visits − max(other visits) ≥ 10` 才算
教师强信号（099 实证 margin 中位 2/100，不过滤 = 噪声主导）。

## 双证据流协议（逐盲区独立判定）

对盲区 kind K ∈ {use_ability, play_stadium, end_turn}：

- **Stream A（教师强信号存在性，只读 mcts 库）**：K 行动被教师以 margin ≥10 选择的
  决策点；统计覆盖局数、回合分布、这些局的教师方胜率 vs 该库总体胜率（lift）。
- **Stream B（启发式冷落度，只读 heuristic 库 + mcts 库对比）**：启发式对局中 K 类
  行动的事件频数/局 vs 教师对局中 K 类 chosen 频数/局（近似利用率比）。

**预注册判定门（见数据前冻结）**：

- **有实证（开修复 task）**：Stream A ≥15 局有 margin≥10 的 K 选择 **且** 这些局教师
  胜率 ≥ 总体 +10pp（信号与胜利同向）；**且** Stream B 启发式利用率 < 教师 1/3
  （冷落成立）。三者全过 → 修复 task 立项（挖掘到的具体行动样本作为刀口输入，
  修复 task 自带独立 Q3 频数门，不沿用本预检结果免检）。
- **关闭定性**：任一不过 → 按 099/066 先例写回 STATUS：A 不过 = 「教师信号噪声
  主导」；B 不过 = 「启发式并未冷落，低一致率是 kind 上限问题」（同 end_turn
  33.6% 天花板先例）。

## 硬门

1. 本任务**零 Agent/DSL/引擎/报告层改动**；纯只读分析。
2. 不整包重训、不重开蒸馏特征线（066 拍板维持）。
3. 判定门按上表执行，不事后挪门；证据（逐点样本 + 汇总 JSON）落 `results/t109-*`。
4. 三个盲区独立判决，互不用对方结果挪门。

## 交付物

- `.kimi-code/t109_blindspot_precheck.py`（可复现诊断脚本）
- `results/t109-blindspot-precheck.json`（逐盲区双证据流汇总 + 样本）
- 判决写回 STATUS 焦点链；有实证的盲区另开修复 task（文档先行）
- `tasks/done/task 109.md` 归档

## 结果（2026-11-07 跑批）

预注册判定门执行结果（汇总 `results/t109-blindspot-precheck.json`）：

| 盲区 | 强信号点 / 覆盖局 | 点作者胜率 | lift | 启发式/教师利用率 | 判决 |
|---|---|---|---|---|---|
| use_ability | 746 / 354 | 40.5% | **−8.5pp** | 0.68 / 0.91 / 0.70 | CLOSE_noise_dominated |
| play_stadium | 108 / 101 | 45.4% | −4.1pp | 0.69 / 0.54 / 0.69 | CLOSE_noise_dominated |
| end_turn | 2518 / 577 | 49.1% | 0.0 | 0.29 / 0.38 / 0.39 | CLOSE_noise_dominated |

- 三盲区 A 流全不过（lift 均 < +10pp；use_ability 甚至**反向**——教师强信号特性
  使用更多出现在败方侧，照抄该信号会把启发式推向与胜利负相关的决策）。
- use_ability / play_stadium 同时 B 流不过（启发式利用率 ≈ 教师的 68–91%，
  不存在冷落）；end_turn 冷落成立（≈1/3）但教师信号本身零胜负信息——与 task 066
  「end_turn 低上限 kind（天花板 33.6%）」独立互证。
- **M12 残留盲区 backlog 清零**。按 066 拍板纪律：不重训、不重开特征线、
  零 Agent/DSL/引擎改动。

## 明确不做

不改任何代码行为；不跑新模拟；不做跨盲区合并判定；不宣称修复价值（效度线已钉死，
本线服务的是**内部决策真实度**，即产品定位「对局模拟 + 决策分析」的交付质量）。
