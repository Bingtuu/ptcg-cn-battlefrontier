# task 030 · M6 校准基线：matrix 跑批 + 偏差表 + 一期验收

- 状态：完成（2026-10-03，M6 里程碑用户确认达成；D-030-1~5 ✅ 已核）
- 关联：PRD §9/§10/§11（M6）；设计文档 `docs/superpowers/specs/2026-10-03-m6-calibration-design.md`（2026-10-03 用户批准：单 task / 每格 500 局 / matrix 声明式 + calibration 报告）

## 目标

9 套池内 36 个无向配对 × 500 局模拟 matchup 矩阵落库；`bfsim calibration` 产出模拟 vs 真实赛事（EN 对齐段）偏差表；一期验收（硬验收复核 + LLM 管线质量评估 + 二期建议）。

## WP 划分与流程

- **WP1** 映射 + matrix schema + runner 展开 + CLI run 分支（TDD，可子代理）
- **WP2** 速度基准门 → 正式跑批 18,000 局 → 确定性复核（主会话执行）
- **WP3** 偏差表报告 `report/calibration.py` + `bfsim calibration`（TDD，可子代理，与 WP2 并行准备）
- **WP4** 一期验收 + 落账（主会话）

## 设计决议（落 `docs/rules-reference.md` 附录 A，编号 D-030-1~5，🔲 待核）

- **D-030-1 真实侧口径**：`stats_matchup(basis="intl_aligned", date_from="2025-04-11", date_to="2025-08-31", division="master", min_n=30)`——CN 侧对阵数据不存在是硬约束，真实矩阵 = EN 环境对齐段（含 online_open tier coef=0.5）；环境差本身贡献一部分偏差，不设死阈值。
- **D-030-2 镜像剔除两侧一致**：模拟只跑 36 个无向配对（i<j），不打镜像。
- **D-030-3 胜率口径**：分母 = 决定局（平局单列），对齐 `report/winrate.py` 既有口径；真实侧 ties 实测 0。
- **D-030-4 先后手**：种子区间自然均摊，不强制平衡。
- **D-030-5 数据锚点**：偏差表 meta 回显 db 数据版本与口径哈希（name_group_rules_hash / tournament_tiers_hash）+ 窗口 + 代码版本 + 种子区间。

## 实现要点

### WP1-1 池映射（`config/target-pool.v1.yml` + `battlefrontier/data/pool.py`）

池文件每个 deck 条目加 `en_archetype`（已实查 db 全部命中、36 格真实侧最小 n=48 无缺格）：

| CN archetype | en_archetype |
|---|---|
| 沙奈朵 | Gardevoir |
| 喷火龙 大比鸟 | Charizard Pidgeot |
| 猛雷鼓 厄诡椪 | Raging Bolt Ogerpon |
| 多龙巴鲁托 黑夜魔灵 | Dragapult Dusknoir |
| 多龙巴鲁托 喷火龙 | Dragapult Charizard |
| 玛俐的长毛巨魔 雪妖女 | Grimmsnarl Froslass |
| 赛富豪 | Gholdengo |
| 多龙巴鲁托 | Dragapult |
| 赫普的苍响 | Hop's Zacian |

`pool.py`：

```python
class PoolEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    archetype: str = Field(min_length=1)
    en_archetype: str = Field(min_length=1)   # 新增：db EN 对齐段 archetype 名
    wur: float = Field(gt=0)
    n: int = Field(gt=0)
    deck_id: str
    note: str = ""
```

`TargetPool._check` 追加：en_archetype 全表去重（重复 = 映射事故，显式报错）。新增：

```python
def matchup_pairs(self) -> list[tuple["PoolEntry", "PoolEntry"]]:
    """池文件顺序无向对（i<j），镜像不打（D-030-2）。"""
    return [(a, b) for i, a in enumerate(self.decks) for b in self.decks[i + 1:]]
```

### WP1-2 matrix 实验定义（`battlefrontier/runner/experiment.py`）

```python
class MatrixCfg(FrozenModel):
    """matchup 矩阵模式（task 030）：引用卡池文件，展开为全部无向配对子实验。"""
    pool: str                       # target-pool YAML 路径
    games_per_pair: int = Field(gt=0)
```

`ExperimentDef` 改双模式（既有 YAML 零影响——decks/games 照常必填于单实验模式）：

```python
class ExperimentDef(FrozenModel):
    name: str
    games: int | None = Field(default=None, gt=0)
    seed_start: int = 0
    decks: DeckSides | None = None
    agents: AgentSides = Field(default_factory=AgentSides)
    snapshot_date: str | None = None
    variants: list[VariantCfg] = []
    matrix: MatrixCfg | None = None

    @model_validator(mode="after")
    def _check_modes(self) -> "ExperimentDef":
        if self.matrix is not None:
            if self.decks is not None or self.games is not None or self.variants:
                raise ValueError("matrix 模式与 decks/games/variants 互斥（不猜）")
        elif self.decks is None or self.games is None:
            raise ValueError("单实验模式需要 decks + games（不猜）")
        return self
```

展开 + 执行（种子区间连续不重叠、与执行顺序无关）：

```python
def expand_matrix(defn: ExperimentDef, pool: TargetPool) -> list[ExperimentDef]:
    """matrix → 子实验列表：第 k 对（0 起）种子区间
    [seed_start + k*games_per_pair, seed_start + (k+1)*games_per_pair)。"""
    if defn.matrix is None:
        raise ValueError("expand_matrix 需要 matrix 模式实验定义")
    g = defn.matrix.games_per_pair
    return [
        ExperimentDef(
            name=f"{defn.name}::{a.archetype}×{b.archetype}",
            games=g,
            seed_start=defn.seed_start + k * g,
            decks=DeckSides(
                a=DeckSourceCfg(source="db", deck_id=a.deck_id),
                b=DeckSourceCfg(source="db", deck_id=b.deck_id),
            ),
            agents=defn.agents,
            snapshot_date=defn.snapshot_date,
        )
        for k, (a, b) in enumerate(pool.matchup_pairs())
    ]


def run_matrix(defn: ExperimentDef, db_path: str,
               results_path: str | Path = DEFAULT_RESULTS_PATH, *,
               workers: int = 1, cards_dir: str | Path = DEFAULT_CARDS_DIR,
               definition_yaml: str = "") -> tuple[list[int], list[str]]:
    """matrix 模式 prepare + execute 一步走；子实验统一 group_name=defn.name。"""
    from battlefrontier.data.pool import load_target_pool

    if defn.matrix is None:
        raise ValueError("run_matrix 需要 matrix 模式实验定义")
    pool = load_target_pool(defn.matrix.pool)
    ids: list[int] = []
    warnings: list[str] = []
    for sub in expand_matrix(defn, pool):
        prep = prepare_experiment(sub, db_path, cards_dir=cards_dir)
        warnings.extend(f"[{sub.name}] {w}" for w in prep.warnings)
        ids.append(execute_experiment(prep, sub, results_path, workers=workers,
                                      definition_yaml=definition_yaml,
                                      group_name=defn.name))
    return ids, warnings
```

注意：`execute_experiment` / `_summarize` 等既有代码对 `defn.games` 做算术（`seed_start + games - 1`）——matrix 分支不得走到这些路径；`ExperimentDef.games` 改为可选后，逐一检查既有使用点均处于单实验模式（`_cmd_run` 非 matrix 分支、`execute_group`），matrix 子实验自身的 games 非 None。

### WP1-3 结果库访问器（`battlefrontier/runner/results_db.py`）

```python
def experiments_by_group(self, group_name: str) -> list[dict]:
    """group_name 下全部实验（id 升序）——calibration 报告按组取数。"""
    cur = self._conn.execute(
        "SELECT * FROM experiments WHERE group_name=? ORDER BY id", (group_name,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
```

### WP1-4 CLI run 分支（`battlefrontier/cli.py`）

`_cmd_run` 开头（variants 分支之前）：

```python
if defn.matrix is not None:
    from battlefrontier.runner.experiment import run_matrix

    ids, warnings = run_matrix(defn, db_path, args.results, workers=args.workers,
                               cards_dir=args.cards_dir, definition_yaml=definition_yaml)
    for w in warnings:
        print(f"[装载告警] {w}")
    db = ResultsDB(args.results)
    try:
        for exp_id in ids:
            print(_summarize(db, exp_id, db.experiment(exp_id)["name"], defn))
    finally:
        db.close()
    print(f"矩阵完成：{len(ids)} 个配对（结果库 {args.results}）；"
          f"偏差表用 bfsim calibration {args.experiment} --results {args.results}")
    return 0
```

新增示例 `experiments/m6-calibration.example.yml`：

```yaml
# M6 校准基线：9 套池 36 配对 × 500 局（task 030）
# 用法：bfsim run experiments/m6-calibration.example.yml --workers 4 --results results/m6-calibration.db
name: m6-calibration
seed_start: 100000
matrix:
  pool: config/target-pool.v1.yml
  games_per_pair: 500
agents:
  a: {type: heuristic}
  b: {type: heuristic}
```

### WP3 偏差表报告（新建 `battlefrontier/report/calibration.py`）

口径常量（D-030-1，meta 回显用）：

```python
REAL_BASIS = "intl_aligned"
REAL_DATE_FROM = "2025-04-11"
REAL_DATE_TO = "2025-08-31"
REAL_AS_OF = "2026-10-03"   # matchup 统计不做时间衰减；as_of 仅为口径钉住回显
REAL_MIN_N = 30
```

数据结构与主函数（真实侧数据以参数注入——测试不打真库）：

```python
@dataclass(frozen=True)
class CalibrationCell:
    """一个有向格：视角方 archetype vs opponent。"""
    archetype: str          # 池 CN 名（视角方）
    opponent: str
    en_archetype: str
    en_opponent: str
    sim_decided: int
    sim_wins: int           # 视角方胜场
    sim_draws: int
    sim_failed: int
    sim_wr: float
    sim_ci: tuple[float, float]
    real_n: int | None      # 真实侧缺格 = None
    real_wr: float | None
    delta: float | None     # sim_wr - real_wr


@dataclass(frozen=True)
class CalibrationReport:
    group_name: str
    cells: tuple[CalibrationCell, ...]            # 72 有向格，|Δ| 降序（None 排尾）
    weighted_mean_abs_delta: float | None         # 权重 = real_n；无有效格 = None
    ci_coverage: float | None                     # sim CI 覆盖 real_wr 的格占比（双侧有数据格）
    meta: dict                                    # 代码/数据版本、种子区间、真实侧 meta


def calibration_report(db: ResultsDB, defn: ExperimentDef, pool: TargetPool,
                       real_rows: list,            # ptcgdb MatchupStat 列表（注入）
                       real_meta: dict) -> CalibrationReport: ...
```

聚合逻辑：对每个子实验（按名 `f"{defn.name}::{a.archetype}×{b.archetype}"` 匹配 `experiments_by_group`，缺实验显式报错不猜）取 `db.games(exp_id)`——失败局（error 非空）计入 sim_failed 不进分母；决定局 = 完成且非平局；有向格 a→b 胜场 = winner==0 计数，b→a = winner==1 计数；sim_ci 复用 `report/winrate.py::wilson_ci`。真实侧建 `(archetype, opponent) -> row` 字典，缺格 real_n/real_wr/delta = None。汇总：weighted_mean_abs_delta = Σ(|Δ|·real_n)/Σ(real_n)（仅双侧有数据格）；ci_coverage 同分母。

`format_calibration(rep) -> str`：meta 全要素回显（group_name / 种子区间 / 代码+数据版本 / 真实侧窗口+basis+min_n+n_games_used+口径哈希）→ 逐格行 `CN名 vs 对手 | sim WR(CI) n | real WR n | Δ` → 汇总行。

CLI（`cli.py` 新增子命令，参数 = matrix 实验定义路径而非组名——口径常量和池映射单点来源）：

```python
cal_p = sub.add_parser("calibration", help="M6 偏差表：模拟矩阵 vs 真实赛事 matchup（task 030）")
cal_p.add_argument("experiment", help="matrix 实验定义 YAML 路径")
cal_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
cal_p.add_argument("--db", default=None, help="ptcg-cn.db 路径（缺省读本机配置）")
```

```python
def _cmd_calibration(args: argparse.Namespace) -> int:
    from ptcgdb.sdk import open_db
    from battlefrontier.data.pool import load_target_pool
    from battlefrontier.report.calibration import (
        REAL_AS_OF, REAL_BASIS, REAL_DATE_FROM, REAL_DATE_TO, REAL_MIN_N,
        calibration_report, format_calibration)

    defn = load_experiment(args.experiment)
    if defn.matrix is None:
        print("错误：calibration 需要 matrix 模式实验定义")
        return 1
    pool = load_target_pool(defn.matrix.pool)
    sdk = open_db(args.db or load_db_path())
    try:
        real = sdk.stats_matchup(date_from=REAL_DATE_FROM, date_to=REAL_DATE_TO,
                                 as_of=REAL_AS_OF, basis=REAL_BASIS,
                                 division="master", min_n=REAL_MIN_N)
    finally:
        sdk.close()
    db = ResultsDB(args.results)
    try:
        rep = calibration_report(db, defn, pool, real.data, dict(real.meta))
    finally:
        db.close()
    print(format_calibration(rep))
    return 0
```

### WP2 跑批（主会话）

1. **速度基准门**：临时 matrix 定义（games_per_pair=50，限 1 对可先单实验）实测速度 → 推算 18,000 局总耗时；>2 小时回报用户再定 workers/局数。
2. **正式跑批**：`bfsim run experiments/m6-calibration.example.yml --workers 4 --results results/m6-calibration.db`（18,000 局）。
3. **确定性复核**：抽 1 对串行重跑同种子区间 50 局到临时库，SQL 对拍 `games.events_hash` 逐局一致。

### WP4 一期验收（主会话）

1. 全量 `pytest -q` 绿 + `ruff check .` 零告警。
2. LLM 管线质量评估：ad-hoc 聚合 `cards/authoring-log.jsonl`（first_pass 率 / human_edit_lines / gate3 核销 80 + 封存 77 口径），结论 + **二期是否批量铺开建议**（含 Jev 调研结论，见设计文档 §7）写进本任务文档「结果与遗留」。
3. D-030-1~5 落 `docs/rules-reference.md` 附录 A 🔲 待核 → 用户核销。
4. `STATUS.md` 更新（M6 达成待用户确认）+ 本文档归档 `tasks/done/`。

## 验收标准（测试清单）

新建 `tests/test_matrix.py`：

1. `expand_matrix` 配对数与顺序：合成 3 套池 → 3 对，名称 `组名::A×B`、deck_id 对应、种子区间 `[100,102)`/`[102,104)`/`[104,106)`（games_per_pair=2）连续不重叠。
2. 展开确定性：同定义两次展开逐字段相等。
3. 互斥校验：matrix + decks 并存报错；matrix + variants 报错；单实验缺 decks 报错；缺 games 报错。
4. `PoolEntry.en_archetype` 必填（缺失 → ValidationError）；`TargetPool` en_archetype 重复报错。
5. `matchup_pairs` 顺序 = 文件序 i<j。
6. `experiments_by_group`：合成库两种子组各取正确集合、id 升序、未知组空列表。
7. 真实池回归：`load_target_pool("config/target-pool.v1.yml")` 9 条 en_archetype == 上表既定名表。
8. CLI e2e（`@pytest.mark.skipif(not DB_PATH.exists())`，对齐 test_cli.py:31 先例）：合成 3 套池（deck_id 用 mik_moe:644634 等真实卡组）games_per_pair=2 → rc=0、6 局落库、3 实验 group_name 一致、名称含 `::`、`×`。

新建 `tests/test_calibration.py`（真实侧全部注入 fixture，不打真库）：

1. 合成结果库逐格对拍：构造 1 对（2 有向格）已知胜负（如 500 局 300/180/平 15/失败 5）→ sim_wr、CI（wilson_ci 对拍）、delta 手算一致。
2. 平局剔除分母、失败局单列不计。
3. 真实侧缺格 → real_n/real_wr/delta = None，排序排尾不报错。
4. 汇总加权平均 |Δ| 手算对拍；ci_coverage 计算对拍（含 None 排除）。
5. 子实验缺失（组内少一对）→ 显式 ValueError 不猜。
6. `format_calibration` 输出含 meta 全要素（窗口/basis/min_n/数据版本/种子区间）与逐格行。
7. CLI e2e：`calibration` 子命令对合成结果库 + mock SDK 出表 rc=0（SDK 层 monkeypatch 或小口径真库，实现时对齐 test_cli.py 既有模式定）。

## 结果与遗留

**task 030 完成（2026-10-03）**：

- **跑批**：36 配对 × 500 局 = 18,000 局，16 workers 6m15s，失败 12 局（0.067%，全部为同一已知形态 `DslError: damage opponent_active 对手战斗场为空`，集中于喷火龙大比鸟 5 个配对——不猜纪律下显式落库，口径 D-030-3 单列不进分母；是否改 no-op 留二期评估）。装载告警仅波波/索财灵两例既有白名单。
- **确定性复核**：配对 1（沙奈朵×喷火龙大比鸟）串行 500 局 vs 16 进程并行，胜负 280/220/0/0 一致、500/500 events_hash 逐局一致。
- **偏差表**（`bfsim calibration`，72 有向格全有真实侧数据）：**加权平均 |Δ| 13.2%（权重=real_n）/ CI 覆盖率 19.4%（14/72）**——系统性偏差存在，符合 PRD §10.2「不设死阈值、作为迭代依据」定位。结构：①赛富豪模拟侧全面偏弱（vs 苍响 Δ-53.8%（real n=68 小样本）/ vs 沙奈朵 -42.5% / vs 玛俐 -31.4% / vs 多龙喷 -29.2%）——启发式 Agent 对赛富豪轴（金币铺伤）操作不佳为首要嫌疑，归二期 Agent 迭代线索；②猛雷鼓厄诡椪对苍响/玛俐偏弱 ~24-26%；③拟合最佳：沙奈朵×玛俐 Δ0.0%、苍响×玛俐 +0.6%、多龙喷×玛俐 +0.7%。偏差混杂三层因素（heuristic vs 人类 / 同 archetype 不同卡表 / EN-CN 环境差），本期只做基线不归因。
- **一期验收**：全量 928 绿 + ruff 零告警（WP1 919→WP3 928）；确定性如上；主库全程只读（calibration 经 SDK，跑批经 mode=ro）；覆盖 81/81 清零 + 定义库 101 文件维持。
- **LLM 管线评估**（authoring-log 157 条目）：池内批次（批 5–9，42 文件）first_pass 34/42（批 5–8 全 34/34；批 9 严格口径 0/8=闸 2 首跑前测试脚手架修正，YAML 零返工）；gate3 未封存 80/80 全核销、human_edit_lines 累计 0。**二期建议：批量铺开生成式 harness 路线**（质量达标、人工修改量为零）；Jev 类决策模型不引入（生成任务范式不匹配 + 撞种子确定性/无外部依赖硬约束，记观察项，见设计文档 §7）。
- **meta 披露**：跑批期间对 docs/rules-reference.md 的文档编辑使部分子实验 code_version 记 `298ca17+dirty`（文档 dirt、代码不变，偏差表 meta 已如实回显两个版本串）。
- **遗留**：D-030-1~5 附录 A 🔲 待用户核销；M6 里程碑达成待用户确认；赛富豪偏差归因与 Agent 迭代归二期。
