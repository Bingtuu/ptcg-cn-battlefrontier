# task 134 · DSL 印刷补挂批（vanilla 异文本清零）

- 状态：验收全过（2026-11-15 收口，待主会话归档 tasks/done/）
- 关联：task 131 覆盖率门槛的已知漏洞修复（vanilla 异文本 = 同名有文档但本印刷未挂载，静默无效果）

## 目标

2026-11-15 扫描发现 **238 个印刷** 处于「同名有 DSL 文档、文本归一化与文档一致、GHIJ 赛制合法、但 card_ids 未挂载」状态——装载时按无效果结算，是静默数据缺陷（今日冠军表的 咕咕 CSV9.5C-141 / 能量转移 CSVH6C-031 即因此丢效果）。本任务把这 238 个印刷按等价类补挂进既有文件（同文本等价类允许并挂，task 026 决议），跑闸 1 全量验证。

## 验收标准（测试清单）

1. 补挂后 `bfsim dsl-check cards/*.yml --db <db>` 全库 rc=0（闸 1 会逐文件校验归一化 text_raw 一致 + 赛制合法，天然兜底错挂）；
2. 复扫 = 0：同一扫描脚本（task 134 结果段附）再跑，「同文本+合法+未挂载」集合为空；
3. 零效果语义变更：只动 `card_ids` 列表，effects 段零改动（git diff 逐文件人工可核）；
4. DSL 库份数不变（136 份，无新文件）；
5. task 131 覆盖率冒烟：今日冠军表（experiments/t1114-*.yml）重扫，vanilla 异文本计数归 0（无文档类不变）。

## 结果与遗留

**状态：验收全过（2026-11-15 收口）**。主会话拍板两张真异文本印刷走拆分文件后，五条验收全部达成。

**实施**：

1. **补挂批**：37 个既有 yml 补挂 259 个印刷（复扫口径忠实实现，含 `SVP-NaN52~56` 等 db 侧真实 active 印刷；与任务书预设的 238 差 21 = 「高级球」整组，见遗留①）。只动 `card_ids`（单行文件单行追加、折行文件仅末行追加，既有行零改写），effects/注释零改动。
2. **拆分档×2**（原验收第 4 条「份数不变」按主会话新指令让位，库 136→138）：
   - `cards/咕咕-不眠.yml`（CSV9.5C-141）：「不眠」= 新声明式原语 `status_immunity`（args.status=asleep）——词表 + PRIMITIVE_ARGS 白名单 + 引擎 `_status_immunity` 落点守卫（engine/core.py，仿 protection 模式；任何来源的睡眠施加均不适用，特性消除监视塔时失效；接入点 = apply_status 原语）。「撞击 20」白板引擎结算，无 DSL 绑定。
   - `cards/能量转移-H6.yml`（CSVH6C-031）：H6 异文本等价类（多两个「的」），效果语义同主类（两段式 move_energy）。
3. **配套测试**：新增 `tests/test_dsl_cards_t134.py`（装配/招式来源拦截/训练家来源拦截/对照组/H6 全流共 5 测）；`tests/helpers.py` KNOWN_MULTI_TEXT_GROUPS 加「能量转移」；`tests/test_items.py::test_card_library_seventeen` 改双文档断言；`tests/test_loader_cardid.py::test_prepare_experiment_真实卡组_按_card_id_挂载` 的「不多挂」不变量随等价类并挂口径修订（keys ⊆ 全库且为真子集；used 侧覆盖由覆盖回归测试 + task 131 门槛持有）。

**验收数字清单**：

1. **闸 1**：`dsl-check cards/*.yml --db` **rc=0，138/138 全 [OK]**（输出尾部：`[OK] cards/高级球.yml（高级球，1 个效果）` / `[OK] cards/黑夜魔灵-咒怨炸弹.yml（黑夜魔灵，2 个效果）`；新档 `[OK] cards/咕咕-不眠.yml（咕咕，1 个效果）`、`[OK] cards/能量转移-H6.yml（能量转移，1 个效果）`）。
2. **复扫 = 0**：脚本重跑 `TOTAL_CANDIDATES=0`（全文附下）。
3. **diff 纪律**：程序化核验 37 个修改文件全部新增行落在 card_ids 块内（bad_lines=0）；新增文件仅 2 个拆分档。
4. **冒烟（t1114-tera-eevee-vs-joltik）**：卡组 a **vanilla 异文本 0**（覆盖 51→53，咕咕 CSV9.5C-141 / 能量转移 CSVH6C-031 已覆盖）、卡组 b vanilla 0；按预期因太乐巴戈斯ex（CSV9C-175）无文档阻断 exit 1（零局跑批）。
5. **全量 pytest**：**1785 passed, 0 failed**（438s；新增 6 测：t134 单卡 5 + loader 断言修订后原测不变）。
6. **ruff**：全库零告警。

**遗留**：

- **① 259 vs 238**：差值恰为「高级球」整组 21（含 db 编号解析缺陷产生的 SVP-NaN52~56 五张，均 active/G 标/同文本，闸 1 确认合法）。已挂载集合 = 任务书口径的忠实超集，不影响正确性；若主会话要核对其 238 扫描脚本对高级球组的过滤逻辑可另行复查。
- **② PRD/CHANGELOG 同步**：`status_immunity` 新原语 + 引擎守卫属 DSL 语义增量，按工作规矩应回填 PRD（三期）与 CHANGELOG（Added 段）——文档动作留主会话收口时一并处理。
- **③ 不眠守卫范围**：现接 apply_status 唯一施加落点（库内无其他睡眠施加路径）；未来新增状态施加原语/落点须评估接入（同 protection「守卫清单」惯例，已在 core.py docstring 标注）。

**复扫脚本**（`_scan_t134.py`，验收第 2 条同源脚本）：

```python
import glob, re, sqlite3, sys, yaml
DB = "C:/Vibe Project/Pokearena/data/ptcg-cn.db"
LEGAL = ("G", "H", "I", "J")
norm = lambda s: re.sub(r"\s+", "", s or "")
con = sqlite3.connect(DB); cur = con.cursor()
total = 0
for path in sorted(glob.glob("cards/*.yml")):
    card = yaml.safe_load(open(path, encoding="utf-8"))["card"]
    mounted = set(card.get("card_ids") or [])
    texts = set()
    for cid in mounted:
        row = cur.execute("SELECT text_raw FROM cards WHERE card_id=?", (cid,)).fetchone()
        if row: texts.add(norm(row[0]))
    for cid, text_raw, mark in cur.execute(
            "SELECT card_id, text_raw, regulation_mark FROM cards "
            "WHERE status='active' AND name_full=?", (card["name_group"],)):
        if cid not in mounted and norm(text_raw) in texts and mark in LEGAL:
            total += 1; print(f"{path}: {cid}")
print(f"TOTAL_CANDIDATES={total}")  # 挂载后重跑输出 0
```
