# task 160 · 对手构筑分布（P1：真实比赛「对手像什么」的结构性缺口）

- 状态：进行中
- 关联：备赛编排线（task 156/157/158/159）；审计清单 P1 第 1 项（2026-11-22）

## 背景

审计缺口①：mod-check 只改自己的表，对手永远是池代表构筑单一列表。真实赛里
同 archetype 有 30 种改表——「我的针对卡到底针对到东西没有」没有答案。
原方案 P1 还含「变体生成器」，立项复核后**砍出本任务**：变体生成与
swap-search（task 130 候选生成 + 两阶段确认档）价值重叠，单独立项收益薄；
本任务把结构性缺口做深做透。

## 设计定案（D-160-1 ~ D-160-4）

- **D-160-1 展开协议**：prep yml 新增 `opponent_builds: {池内中文名: [decklist 路径, ...]}`
  = 该对手的额外构筑（池代表表恒为 build #1，额外表 #2..k，顺序即编号）。
  实验名 `{prep}-{arm}-vs-{slug}`（#1）/ `{prep}-{arm}-vs-{slug}~b{n}`（#n≥2）；
  `~` 不在 slugify 字符集内，天然免碰撞。file 臂走 task 157 已有
  validate_deck 同口径校验。
- **D-160-2 判读聚合（保守语义）**：mod-check 批次模式按登记键取数；
  每 build 一格（slug 带 `~bN` 后缀），**门按全部 build 格判定**
  （全正/零回吐逐 build；全显著逐 build p<α/M）——任何一个 build 回吐即门否，
  防「均值好看、最劣改表崩盘」的采纳陷阱。注册键必须是
  `{池 slug}` ∪ `{池 slug}~bN` 的子集，未知键显式报错（不猜）。
- **D-160-3 期望口径**：场权重按对手（池 slug）不变；对手胜率 =
  **各 build 胜率等权均值**；base_exp/mod_exp = Σ w_opp × mean_build。
  报告逐 build 行落表（build 后缀列），期望行注明「对手多构筑均值口径」。
- **D-160-4 证据包**：decks.json 增 opponent_builds 段（文件副本+sha256），
  manifest 同步登记；verdict cells 逐 build 落盘（schema 只增不改）。

无改表臂（base-only 段）同样支持多构筑：逐 build 行 + 均值期望。

## 验收标准（测试清单）

- [ ] prep 展开：opponent_builds 生成 `{slug}` 与 `{slug}~b2` 双臂（base/mod 各一），
  b 侧为 file 臂；未给 opponent_builds 的存量定义**输出逐字节不变**（零变化纪律）。
- [ ] prep cfg 校验：池外中文名 / 文件不存在 → ValueError（不猜）。
- [ ] mod-check 批次：两 build 批次 → cells 含两格、权重按对手聚合、期望=均值
  手算复现；一门其一 build 回吐 → 全正门 ❌（最劣 build 驱动）。
- [ ] 批次注册未知键（池外 slug~b9）→ 显式报错；前缀模式（非批次）遇 `~bN`
  实验名显式拒绝（不支持，防静默错读）。
- [ ] 证据包：decks.json 含 opponent build 文件副本与 sha256；manifest 登记齐全。
- [ ] base-only 段：多构筑逐 build 行 + 均值期望。

## 实现要点

- `PrepCfg.opponent_builds: dict[str, list[str]] = {}` + validator（池内名存在性
  在 generate 时查池，文件存在性同 entry.modified 口径）。
- `generate_prep_experiments`：对手循环内再循环 builds。
- `_write_batch_json`：slugs 键自然带 `~bN`（现成前缀切分逻辑不动）。
- `mod_check._load_batch_arms`：接受并校验带后缀键；`mod_check_report` 聚合
  （build 格 → 对手权重展开 + 期望均值 + 门逐 build）。
- `_base_only_section` / `_evidence_pack` 同步。

## 结果与遗留

2026-11-22 收官：6 新测全绿（prep 展开 2 + 全流程证据包 1 + 批次聚合 1 +
未知键/前缀拒绝 2），ruff 零告警，全量重跑绿。TDD 过程抓出手算测试锚点
一处笔误（beta 臂 3a/2draw = 0.375 误记 1/3）——实现侧数值经独立复算无误。

- 交付：prep `opponent_builds` 展开（`~bN` 实验名后缀，file 臂走 task 157
  校验）；batch 协议注册键校验 + 逐 build 判读格；保守门（最劣 build 驱动）；
  期望 = 各 build 等权均值（`cell_weights` = 对手场权 / build 数）；
  证据包 decks.json 落对手构筑副本 + sha256；base-only 段同样支持多构筑；
  前缀模式遇 `~bN` 显式拒绝。
- 零变化纪律：未给 opponent_builds 的存量 prep 定义输出逐字节不变
  （既有 36 夹具全兼容）。

遗留：对手构筑的场权重按对手整体计（build 内不区分真实占比——占比数据
上游无供给）；变体生成器砍出本任务（与 swap-search 价值重叠）。

