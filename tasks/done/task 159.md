# task 159 · 判读诚实度 P0：扫描族多重比较校正 + Bo3/赛制口径解析换算

- 状态：进行中
- 关联：备赛编排线（task 156/157/158）强化轮；docs/claims-register.md 守则 1（sim 口径限定语保持）

## 背景

2026-11-22 备赛线自我审计（Owner 三问 → 工程清单）定案两件 P0：

1. **多重比较护栏**：swap-search 已有 Bonferroni/BH 校正（设计文档 §2.3/2.4 预注册），
   但 prep/mod-check 线的典型姿势是**一次扫 M 个候选改表批、采纳任何过三门者**——
   M 个报告的 OR 决策会假阳性通胀，当前报告层完全无感知。采纳纪律的统计诚实缺口。
2. **Bo1/Bo3 口径**：现有判读全部单局口径；瑞士轮 Bo1 与淘汰赛 Bo3 的赛制结构不同，
   牌手真正关心的是「比赛胜率」与「几轮几胜出线期望」。解析换算即可，零模拟成本。

## 目标

- mod-check 支持扫描族声明：跨候选判读的采纳阈值做 Bonferroni 校正并显式落报告头。
- 报告层新增赛制口径解析换算：单局 p → Bo3 比赛胜率 → 瑞士轮出线概率。

## 验收标准（测试清单）

### ① 扫描族校正

- [ ] `mod_check_report(..., family_size=M)`：`all_significant` 门按 α/M 判（构造
  p 值恰跨 α 与 α/M 的格，M=1 过门 / M=10 不过门，逐位断言）。
- [ ] `format_mod_check` 头注明示「扫描族规模 M=N，Bonferroni 校正后采纳阈值 α'=…」；
  M=1 时不出现校正注（旧行为逐字节兼容）。
- [ ] `family_size` 非正整数 → ValueError（纪律：不猜）。
- [ ] CLI `mod-check --family-size N` 透传；缺省 1（现有调用零变化）。

### ② Bo3/赛制换算

- [ ] 新模块 `battlefrontier/report/match_odds.py`：
  - `bo3_match_prob(p) = p²(3−2p)`（p=0.5→0.5、p=1→1、p=0→0 逐位断言 +
    p=0.6 已知值解析断言）。
  - `cut_prob(p, rounds, min_wins)` = 二项尾概率 P(X≥min_wins)，rounds=6/min_wins=4
    已知值断言（手算对照）。
- [ ] `format_mod_check` 在条件期望行后追加赛制段：基线/改表的 Bo3 换算 +
  「6 轮需≥4 胜」出线概率（基线 vs 改表），带简化口径注（无 tiebreak、Bo3 单局
  独立同 p 假设），限定语不丢（仍是 sim 口径数字的解析翻译，不构成真实预测）。

## 实现要点

- `mod_check_report` 增参 `family_size: int = 1`；校正 alpha 仅作用于
  `all_significant` 门与头注，逐格 p 仍显示原始值（判读信息不丢）。
- Bonferroni（α/M）而非 BH：候选数 M 小（典型 2–10），且 OR 采纳决策要的是
  强族控制；BH 留给 swap-search 的大空间扫描（已有）。
- 赛制换算纯函数落 `match_odds.py`，format_mod_check 消费；不进 verdict.json
  schema（解析派生量，verdict 保持事实层）。
- CLI：`--family-size`（help 注明「本次扫描族候选改表批数，缺省 1 无校正」）。

## 结果与遗留

2026-11-22 收官：8 新测全绿（match_odds 3 + family_size 门/头注/非法值 3 +
赛制段落报告 1 + 既有 21 夹具全兼容），ruff 零告警，全量重跑绿。

- `battlefrontier/report/match_odds.py`：`bo3_match_prob`（p²(3−2p)）/
  `cut_prob`（二项尾）/`format_match_odds`（基线/改表两栏 + 简化口径与
  sim 限定语）；纯解析派生，不进 verdict.json schema（事实层 vs 派生层分离）。
- `mod_check_report(family_size=M)`：全显著门 Bonferroni α/M；逐格 p 原始值
  不丢；`family_size` 非正整数显式 ValueError；`ModReport.family_size=1`
  缺省（旧调用零变化）。
- CLI `mod-check --family-size N`（缺省 1 无校正，help 注明纪律）。
- 选择 Bonferroni 而非 BH：候选数 M 小（2–10）且为跨批 OR 采纳的强族控制，
  BH 留给 swap-search 大空间扫描（其模块已自带两列校正）。

遗留：赛制段 rounds/min_wins 暂钉 6/4 默认值（CLI 未暴露参数，Simplification
注记已落文本）；如未来要 Bo3 主赛制赛事再参数化。

