# task 131 · 跑前 DSL 覆盖率门槛

- 状态：完成
- 关联：备赛 P0（2026-11-14 goal loop）；`bfsim check-deck`（task 119）升级

## 目标

把「跑前体检」从「用户想起来才跑」升级为**实验跑批的显式门槛**：`bfsim run` 装载卡组后、开跑前输出 DSL 覆盖率报告（有文档 / vanilla 异文本 / 无文档三张清单 + 占比），默认 `--strict-coverage` 时存在「影响语义的无文档卡」即拒绝开跑；非 strict 默认放行但告警更醒目。堵住今天实测的漏洞：冠军表带无文档卡照样跑，对手强度被静默扭曲。

## 验收标准（测试清单）

1. `bfsim run` 开跑前对每个参赛卡组输出覆盖率报告（stdout 一段，含总张数、三态计数与卡名清单）；
2. `--strict-coverage`：存在无文档非基本能量卡 → 非零退出、零局跑批、报错指明卡组与卡名；全覆盖 → 正常开跑；
3. 基本能量豁免（无文档属正常，引擎原生支持）；"vanilla 异文本"（同名有文档、本印刷未覆盖，装载告警已有）单独归类，不触发 strict 拒绝；
4. 覆盖判定复用 check-deck 同一判定逻辑（不许两套口径分叉；如 check-deck 逻辑在 CLI 层内联，下沉为 report/check 层共用函数）；
5. 既有实验（v2 池 134 份定义全覆盖）在 strict 下全部照常跑通——回归证明；
6. 全量 pytest 绿 + ruff 零告警；零 Agent/DSL/引擎行为变更（装载/判定层只加不改）；README 使用节补一行。

## 实现要点

- 判定源：`cards/` 定义库装载键 = card_id；现有装载告警逻辑在 runner 装载路径（今天跑批日志可见「[装载告警] … 按无效果结算」）。
- 建议形态：`battlefrontier/report/`（或 runner）新增 `coverage.py`，CLI run 子命令接入；check-deck 改调同一函数。
- strict 判定白名单：基本能量（db `is_basic_energy` 或卡名匹配基本能量）+ vanilla 异文本。

## 结果与遗留

- 状态：收官（2026-11-14）。TDD：红测 `tests/test_coverage_gate.py`（12 用例：三态判定 / 豁免边界 / 报告格式 / run_coverages 单实验+matrix 去重桩 / CLI 三态端到端 / v2 池回归）→ 实现 → 绿。
- 新增 `battlefrontier/runner/coverage.py`：`classify_dsl`（与 check-deck 同源，deck_check 改调本函数，验收 4）+ `side_coverage` / `run_coverages`（单实验 a/b、variants 各变体、matrix 按池去重）+ `format_coverage` / `strict_violations`。CLI `run` 装载后开跑前打印报告；`--strict-coverage` 存在无文档非豁免卡 → 退出 1、零局跑批、逐条指明卡组侧与卡名；非 strict 有阻断卡时逐条 `[覆盖率告警]`（更醒目）放行。README 使用节补一行。
- **豁免口径定案（超出 task 文面，依据目标段「影响语义的无文档卡」+ 实测证据）**：无文档卡三分——基本能量豁免（验收 3 文面）/ 纯白板豁免（**新增**：宝可梦、无特性、全部招式固定伤害，`damage_modifier` 为空——引擎按 db 招式原生结算语义无损；训练家/能量卡不走此豁免，其效果即文档本身）/ 其余阻断 strict。实测 v2 池 7/9 套含无文档纯白板底座（多龙梅西亚、拉鲁拉丝、N的索罗亚、比比鸟 151C-017、玛俐的诈唬魔、N的火红不倒翁，均已逐张核 db 文本纯固定伤害），若按「无文档非能量即拒」字面口径 strict 在 v2 池寸步难行——与验收 5 矛盾，故纯白板豁免是让验收 2/3/5 同时成立的唯一自洽读法；另火伊布套有 1 张 vanilla 异文本 波波（CSV4C-099），按验收 3 不触发 strict。如需更严口径（无文档即拒），删掉 `_is_pure_vanilla` 分支即可，但 v2 池需先补 7 张 DSL 文档。
- 回归：v2 池 9 套判定零阻断（`test_v2池卡组_strict口径全覆盖`）；`tests/test_coverage_gate.py` + `tests/test_deck_check.py` + `tests/test_cli.py` 共 32 用例全绿（本任务相关面）；ruff 零告警。未跑全量 pytest（主会话占用，按子任务纪律）。
- 行为边界：装载/判定层只加不改——experiment.py 零改动、既有「[装载告警]」文案不动；报告与门槛在 CLI 层接入，Agent/DSL/引擎零变更。matrix/variants 走 run_coverages 时会重复一次 prepare（纯装载只读，无游戏、无副作用）。
- 遗留：① 全量 pytest 待主会话空闲时复核；② 7 张纯白板底座卡可选补 DSL 文档（走 dsl-authoring 三道闸，当前 vanilla 结算已语义无损，非缺口）；③ `bfsim tune` / `collect-snapshots` 等非 run 跑批入口未接门槛（task 范围外，如需统一可后续复用 `run_coverages`）。
