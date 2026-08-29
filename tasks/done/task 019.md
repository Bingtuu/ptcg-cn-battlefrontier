# task 019 · 实验定义 + 正式 Runner + 结果库 + bfsim run（M3 收口）

- 状态：完成
- 关联：PRD §8 实验层（§8.1 实验定义 / §8.2 执行 / §8.3 结果库 FR-10 / §8.4 确定性）/ 里程碑 M3 验收「百局实验端到端跑通落库」

## 目标

把 M3 补完：实验定义 YAML + 正式 Runner（Agent 配置注入、种子分片多进程、增量落库）
+ 结果库三层表（独立 SQLite WAL，主库只读）+ `bfsim run` 子命令，跑通
「沙奈朵镜像 HeuristicAgent vs RandomAgent 百局实验」端到端落库。

`runner/play.py` 保留为引擎验证工具；正式 Runner 新建模块，复用其 play_game
单局循环（task 018 已加 agents 注入）。

## 设计

### 实验定义 YAML（`experiments/*.yml`，Pydantic 强校验）

```yaml
name: gardevoir-mirror
games: 100
seed_start: 1000
decks:
  a: {source: db, deck_id: "mik_moe:644634"}     # db = load_deck；file = 本地 decklist（每行 "N 卡名"）
  b: {source: db, deck_id: "mik_moe:644634"}
agents:
  a: {type: heuristic, params: {}}               # type: random | heuristic；params 覆盖 HeuristicParams
  b: {type: random}
snapshot_date: "2026-08-09"                      # 数据版本锚点（缺省 = 装载时最新快照）
```

### 结果库（独立 SQLite WAL；默认 `results/battlefrontier-results.db`，gitignore）

- `experiments`：id / name / definition_yaml（定义快照原文）/ code_version（git short sha + dirty 标记）/ data_version（快照日期 + db user_version）/ status（running→done/aborted）/ created_at
- `games`：id / experiment_id / seed / first_player / winner / is_draw / turns / events_hash / 双方卡组 id
- `game_events`：game_id / seq / event_json（完整事件流，供回放与 M4 聚合）

关联主库经 card_id / name_group / 快照 id；主库只读（FR-10）。

### 执行

主进程解析实验 → 构建卡组/DSL 文档 → 按种子分片；worker 载荷只传**可序列化配置**
（卡组 dump + agent 配置 dict + 种子），agent 实例在 worker 内重建（不依赖 pickle Agent）。
串行与 workers=N 并行结果逐局一致。每局完成即增量插入 games + game_events。

### CLI

`bfsim run experiments/xxx.yml [--workers N] [--results PATH]`；输出实验 id / 局数 / 胜率速览。
`bfsim` 无参数维持现状占位文案。

## 验收标准（测试清单）

新文件：`battlefrontier/runner/experiment.py`、`battlefrontier/runner/results_db.py`、
`battlefrontier/cli.py` 重写、`experiments/gardevoir-mirror.example.yml`、
`tests/test_experiment.py`（+ 必要时 `tests/test_results_db.py`）。

1. **实验定义 schema**：合法 YAML 加载为不可变对象；缺字段 / 未知 agent type /
   games≤0 / 未知 HeuristicParams 参数名 → 明确报错（不猜）。
2. **卡组解析**：source=db 走 `load_deck`（db 路径来自 `config/battlefrontier.local.yml`，
   快照日期锁定）；source=file 本地 decklist 解析（行格式 `N 卡名`，N>0，经 db 校验展开）；
   两种来源的产物等价（同 60 张 CardDef 序列）。
3. **Agent 构建**：type=random/heuristic + params 覆盖生效（构建出的 HeuristicParams
   字段值与 YAML 一致）。
4. **落库 schema**：三层表按 FR-10 建好（WAL 开启）；experiment 行含定义快照原文 +
   code_version + data_version + 状态流转 running→done。
5. **增量落库**：跑 N 局后 games/game_events 行数正确，每局事件流完整可重取。
6. **确定性硬验收（PRD §8.4）**：同实验定义 + 同种子区间，串行 vs workers=2 并行、
   以及两次独立重跑（各自建新库），games 层 (seed, winner, is_draw, turns, events_hash)
   逐局一致。
7. **CLI 端到端**：`bfsim run <实验.yml>` 全链路（stub 卡组实验，games=4）退出码 0、
   结果库行数正确、stdout 回显实验 id。
8. **M3 里程碑验收**：沙奈朵镜像（heuristic vs random，games=100）实跑落库——
   作为验收命令执行并记录耗时（不进 CI 保速度；CI 用小局数）。
9. `pytest -q` 全绿 + `ruff check .` 零告警。

## 实现要点

- 多进程复用 spawn 上下文（Windows 纪律，对齐 play.py）；worker 入口模块级函数。
- 代码版本：`git rev-parse --short HEAD` + 工作区 dirty 标记；取不到记 "unknown"（不阻塞实验）。
- DSL 文档装载：`load_card_dir("cards")` 后按卡组卡名过滤成 card_effects；
  卡组中无 DSL 的卡按白板处理（现状口径不变）。
- 报告统计口径（Wilson CI 等）属 M4，本 task 只做 stdout 速览（胜/负/平计数）。
- 结果库路径进 .gitignore；示例实验定义提交，本机实验定义不强制。

## 结果与遗留

**完成**（2026-08-29）：`runner/experiment.py` + `runner/results_db.py` + `cli.py` 重写 +
`experiments/gardevoir-mirror.example.yml`；23 新测试，全量 266 绿 + ruff 零告警。

**M3 里程碑验收实跑**：沙奈朵镜像 heuristic vs random 100 局落库
（A胜 63 / B胜 37 / 平 0 / 失败 0；4 workers 约 4.4s——PRD §8.2「2000 局分钟级」达标）；
并行 vs 串行重跑 games 层逐局一致（§8.4 硬验收，真实卡组实测 + stub 卡组 CI 双保险）。

实现中两处口径收敛：

- **失败局容错**：CLI 初测触发 copy_attack 嵌套 chooser 的显式 DslError（task 017 已知遗留）。
  Runner 改为失败局落 `games.error` 列继续实验（不猜纪律：错误显式可见，不掩盖不崩溃），
  worker 返回错误文本而非抛出；本次百局实跑 0 失败。
- `GameResult` 补 `first_player`（§8.3 games 层「先后手」此前未导出）。

遗留：copy_attack 嵌套 chooser（运行时选择的被复制招式）归 task 020 修复，修后应重跑
验收确认失败率归零；Wilson CI/决策聚合/换卡敏感性归 M4。
