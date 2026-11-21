# task 156 · 备赛流程编排命令化（bfsim prep + field-snap 就绪探针）

- 状态：进行中
- 关联：Owner 2026-11-22 规划（备赛工具线收尾三件之 ①②③）；task 123/125（field-pick/matchup-snap）；task 141/152（成对改表核对协议——本会话脚本产品化）；task 112（t105 哨兵——探针口径同族）

## 目标

把「服务一场高级赛」的 5 步散命令清单（场刷新 → matchup 快照 → field-pick → 报名卡组同种子成对核对 → 败局解剖/换卡搜索）沉淀为可重复执行的产品命令，纪律进代码、不靠记忆：

1. **`bfsim field-snap`**：场快照导出（上游 stats_usage 钉口径调用产品化，t152_field_refresh.py 同款 meta 逐键）+ `--probe` 就绪探针（上游最新赛事日期 vs 现有快照窗口，回答「现在刷新能不能拿到新场」——Owner 规划 ③）。
2. **`bfsim mod-check`**：改表成对判读命令化（t152_gard_verdict.py 泛化）——同种子成对 McNemar 逐格 Δ + 场权重条件期望 + 种子缺口/回吐显式诊断 + 全正全显著门。
3. **`bfsim prep`**：编排器——prep yml 一次驱动 场刷新 → field-pick →（可选）报名卡组 × 池内全对手成对跑批 → 统一报告 md（限定语头注 + 各节 + 下一步命令指针）。

## 验收标准（测试清单，先测试后实现）

### field-snap
- [ ] 导出：stub stats_usage 固定 rows → 落 JSON 含 meta（as_of 钉运行日）+ data 行，`{"meta":…, "data":[…]}` 结构与 `results/field-snap-2026-11-21.json` 同 schema；调用参数与 t152 探针逐键一致（scope/division/tiers/include_qual/include_team/basis/min_n/granularity/usage_basis）
- [ ] `--probe` 三分支：无既有快照（报「无基线」）；上游 MAX(date) ≤ 窗终点（FRESH，退出码 0）；上游 MAX(date) > 窗终点（STALE + 落后天数，退出码 3）
- [ ] probe 查询口径：`v_tournament_weights` basis='cn' AND (division='master' OR NULL) 的 MAX(date)（与 stats_usage 导出同赛区口径，不猜）

### mod-check
- [ ] 合成结果库：2 对手 × base/mod 各 4 局，手算可验——配对翻转 3/4 → 双侧二项 p=0.5；胜率=胜/ n（平局计入 n 不计胜）；逐格 Δpp 正确
- [ ] 场权重：快照份额池内归一且剔除报名卡组自身；条件期望 = Σ w×格胜率
- [ ] 纪律：种子缺口（base 有 mod 无）逐格显式列出；error 局显式报错不静默；前缀下无配对实验 = 显式报错
- [ ] 报告含全正 / 全显著（α=0.05 可配）/ 零回吐 三个门布尔 + 限定语头注

### prep
- [ ] yml 强校验：pool/matrix_snap/field 窗/entry（archetype+deck_id 或 modified decklist）/games_per_cell/seed_start 缺失即拒（不猜）
- [ ] 实验生成：池内除报名卡组外每对手两实验（base/mod），同名后缀配对、**同 seed_start + 同 games = 成对 CRN**；报名卡组恒为 a 侧；实验名 `{prep名}-base-vs-{slug}` / `-mod-vs-`
- [ ] slug = en_archetype 小写非字母数字压 '-'（池 en 名唯一已由池校验器保证）
- [ ] stage 接线可注入（field 导出/fp 计算/跑批函数可替换）→ 冒烟：fake 跑批写合成库 → 统一报告 md 落盘，含限定语头注 + field 节 + pick 节 + 判读节 + 下一步命令节
- [ ] `--pick-only`：只跑场刷新 + field-pick（零对局）

### 全局
- [ ] 全量 pytest 绿 + ruff 零告警；既有行为零变化（纯新增命令 + 3 个新模块）
- [ ] `experiments/prep.example.yml` 示例（沙奈朵口径，种子域 650000——与全部历史域不重叠）
- [ ] README 常用命令段登记三条新命令

## 实现要点

- `battlefrontier/runner/field_snap.py`：`export_field_snap(db_path, date_from, date_to, out)` / `probe_field_freshness(db_path, snap_path|None)`（返回 (status, detail) 二元组，CLI 层定退出码）
- `battlefrontier/report/mod_check.py`：纯函数核（`mod_check(cells, field_share, alpha)`）+ sqlite 读取（experiments/games 按名前缀分组；与 t152 判读脚本同表同口径）；配对 p = 无连续校正双侧二项（与 t152 脚本同式）
- `battlefrontier/runner/prep.py`：`PrepCfg` frozen pydantic + `generate_prep_experiments(cfg, pool)` + `run_prep(cfg, injectables…)`；报告 = 分节字符串拼合，限定语头注复用 `field_pick.QUALIFIER_HEADER` + 补「改表增益 = sim 口径」「登顶率 ≠ 夺冠概率」两行
- CLI：`field-snap` / `mod-check` / `prep` 三个子命令，错误打印 + 退出码 1（probe 的 STALE=3 是刻意例外，注释说明）
- 纪律声明：prep 只编排不改任何 Agent/DSL/引擎行为；跑批走既有 `run_experiment`（严格覆盖率闸可用 `--strict-coverage` 透传）

## 结果与遗留

- 状态：**完成（2026-11-22）**——三件交付全部落地，18 新测绿（field-snap 5 / mod-check 6 / prep 7），ruff 零告警，真库回测逐位一致
- **真库回测（t152 沙奈朵 40,000 局库）**：mod-check 逐格数字与 t152_gard_verdict 脚本逐位一致（10/10 格胜率/Δ/p，如赛富豪纯格 74.3→77.5 p=0.0171），三门全过（全正/全显著/零回吐）
- **条件期望口径修订（有意差异，非 bug）**：mod-check = 池内归一（权重和=1，60.0%→65.5%，Δ+5.5pp）；t152 会话脚本把池外份额静默摊薄（47.1%→51.4%，+4.3pp）。两口径 Δ 方向/判定一致，新口径语义更干净（「条件于对手在池内」）
- **probe 首跑即命中**：上游 2026-11-22 已有新赛事（超出 11-15 窗终点）→ 提示场窗可推进（单新场是否过 min_n=5 由导出时上游出口决定）
- **命名纪律**：mod-check 只认 slugify(en_archetype) 后缀（池驱动）；t152 库的 4 个别名 slug（grimmsnarl 等）已按新约定回测时临时改名验证——后续成对跑批一律由 prep 生成实验名，不再有手工命名
- 遗留：① 归档顺带清掉 t152_gard_verdict.py 3 个 ruff 历史告警；② **场就绪探针值守已建**（2026-11-22，cron 每周二 10:24，id `01M7ZNBTCJ8SP1YQMNT7KZ4X92`，与 t105 哨兵 10:17 同班——cron 不跨会话存活，同 task 112 已知限制，值守随会话重建）
