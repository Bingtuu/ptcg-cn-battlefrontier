# task 087 · 非斩杀 setup 时序

> **进展（2026-10-30）**：TDD 绿 + 100 局已回写（相对 A69 **持平**；关 086 对照零差）。Owner 拍板 **A：不合** PR #17；086 保留。PR #17 closed。不宣称 30.4%。

> 文档已拍板（2026-10-30 整包按本文建议）。不改 `heuristic.py`。不得破坏 084 Q2=C。

- 状态：**Owner A 不合**（2026-10-30）；TDD 绿 + 100 局 **持平**；关 086 零差；PR #17 **closed / 未合并**（https://github.com/Bingtuu/ptcg-cn-battlefrontier/pull/17）；086 保留于 main `cd67311`；不宣称矩阵闭环 / 30.4%
- 关联：规格 `docs/superpowers/specs/2026-10-30-task-087-nonlethal-setup-timing-design.md`；计划 `docs/superpowers/plans/2026-10-30-task-087-nonlethal-setup-timing.md`；一页纸 `docs/superpowers/specs/2026-10-30-post-085-baseline-and-next-knives.md`
- 依赖：085 已合入；084 Q2=C；083/085 路径可见；081 搁置
- 对外中文名：非斩杀 setup 时序
- 姊妹：task 086（可任序、独立开关）

## 目标

复制/王牌已付清但 `can_ko` 为假时，若窄 `_setup_value`（启用能量 / 检索使下回合可 KO / 治疗扛斩杀）严格大于芯片挥砍，则先 setup；`can_ko` 永不 defer。

## 本文建议（待 Owner 拍板列勾选）

| ID | 建议 |
|---|---|
| Q1 | **087 · 非斩杀 setup 时序** |
| Q2 | **永不 defer** can_ko |
| Q3 | **B**：setup>`chip` 则先 setup，否则跳过零价值后挥砍 |
| Q4 | `_setup_value` = **E+S+H** |
| Q5 | `setup_before_chip_gate: bool = True`，不进 tune |
| Q6 | 启用前提：路径已付清可见（不要求落后） |
| Q7 | 100 局相对 A69；不宣称 30.4% |
| Q8 | 与 086 可任序、独立开关 |
| Q9 | 冻结与禁止全维持 |
| Q10 | 本 PR 停文档 |

## 验收清单

- [x] 规格 + 计划 + 本 task + STATUS + 一页纸
- [x] Owner 勾选 Q 表（2026-10-30 整包按建议）
- [x] 单测 `tests/test_heuristic_setup_before_chip.py`（TDD 绿）
- [x] `test_copy_ko_attacks_before_supporter` 绿且断言未改
- [x] 一百局对照 A69（Diupi-Yun；`results/t087-gard-zoro.db`；种子 `208000..208099`；A**68**/B32 / 失败 0；B prizes **15** / deck_out 4 / no_pokemon 13；暗夜王牌 **281/80**；触及后 B WR **36.2%**；相对 A69 **持平**；no086 对照 `results/t087-no086-gard-zoro.db` 同数）
- [x] 无 `prize_pressure_gate`；无卡名；100 局写回未改 `heuristic.py`（仅 checkout）

## 明确不做

推迟斩杀、081、宽泛任意抽牌当 setup、改 `pokemon_score`、宣称 30.4%。**Owner A：不合 PR #17**；100 局已回写（持平）；关 086 零差；不跑同格 500 / 18000；**不回退** main 上的 086；下一刀残差待拍板。

## 100 局结果（Diupi-Yun；PR #17 closed / Owner A 不合）

### Step A — 087 ON（含 main 默认 086 ON）

- **命令**：`.venv\Scripts\bfsim.exe run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t087-gard-zoro.db`
- **代码**：`9bdbe0c93a1afa094a60210e42cb013225e21e0f`（分支 `cursor/task-087-setup-before-chip-tdd`）
- **硬指标**：100 局失败 **0**；A**68** / B**32** = **68.0% / 32.0%**；种子 `208000..208099`
- **B 胜因**：prizes **15** / deck_out 4 / no_pokemon 13
- **暗夜王牌**：次数 **281** / 触及局 **80** / 触及后 B WR **36.2%**（29/80）
- **对照**：post-085/t086 同格 100 局 A69/B31、B prizes 16、暗夜王牌 293/80、触及后 35.0%
- **相对 A69 种子翻转**：5 局（208013/094/096 → B；208064/088 → A），净 A −1
- **方向读（相对 A69，Q7）**：**持平**。A% 69→68（±1 噪声，未形成向 60–70% 的明确位移）；B prizes 15≤16；触及后 36.2% 仅 +1.2pp（28→29/80）。不宣称 30.4%。

### Step B — 087 ON + 086 消融（`prize_race_gate: false`）

- **原因**：Step A 判 **持平**（不符合「明确有效」），按 Owner 要求做不合 086 对照。
- **关法**：实验 YAML `experiments/t087-no086-gard-zoro.yml`，两侧 agent `params: {prize_race_gate: false, setup_before_chip_gate: true}`（复用 `t078-gard-zoro-off.yml` 的 params 门控写法；**未改** `heuristic.py`）。
- **命令**：`.venv\Scripts\bfsim.exe run experiments/t087-no086-gard-zoro.yml --workers 8 --results results/t087-no086-gard-zoro.db`
- **硬指标**：失败 **0**；A**68** / B**32**；B prizes **15** / deck_out 4 / no_pokemon 13；暗夜王牌 **281/80**；触及后 **36.2%**（29/80）
- **与 Step A**：种子级 **0 翻转**（数字完全相同）→ 本 100 种子上 086 对 087 无增量；相对 A69 的 −1 净翻转全部来自 087。

### 未做

- 合并 PR #17；回退 main 086；同格 500；18000；改 `heuristic.py`（除 checkout）。

## Owner 拍板（2026-10-30 chat）

- **A**：不合 PR #17（`setup_before_chip_gate` 不进 main）。
- **保留 086**：不回退 PR #16 / `prize_race_gate`（main `cd67311`）。
- **证据**：087 ON+086 ON = A68/B32 持平 vs A69；087 ON+086 OFF = 同数 / 0 种子翻转。
- **下一刀**：残差待拍板（不发明新 task 号、本回合不实现）。
