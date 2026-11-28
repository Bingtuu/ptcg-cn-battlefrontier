# task 166 · 锁底板后的邻域短清单与家族记账

- 状态：进行中
- 关联：备赛目标环第 2 步（2026-11-28 Owner 收窄定位：当前场备赛工具）。顺序固定：① task 165 场权重与 field-snap / field-pick 重跑 → ② 本任务在已经锁定的真实底板上自动出邻域短清单，并把 `family_size` 设成候选数 → ③ task 167 用这份清单（若当时已落地）做一轮预注册家族对照，然后冻结。若 165 停在暂定口径，底板仍可用，短清单头注照抄 165 的「暂定」句。本任务不证明 163/164 彼此一致。

## 目标

field-pick 锁定一张真实代表牌表之后，一条命令列出它的邻域短清单：同 archetype、合格场窗里其他真实牌表上反复出现的印刷级一换一（含 ACE 槽对换），再加上 Owner 点名的 tech。清单只是候选。随后每份 prep 定义带上同一个 `family_size = 候选数`，使多次 `mod-check` 成为一族，而不是各自 α=0.05。命令到写出清单和 prep 骨架为止，不开对局，不采纳任何 sim 正号。

## 已有能力（核对过；下面只写缺口）

- `bfsim swap-search`（`battlefrontier/report/swap_search.py` 的 `run_swap_search`）必填 `--deck`、`--vs`、`--budget`，调用后进入筛选档 + 确认档，会对局。没有零对局的列表模式。
- `candidate_in_cards` 取同 `archetype_name`、`fetched_at DESC LIMIT 50` 的牌表，按 `card_id` 出现的卡组数排 top-N。这是「邻近表里常见的牌」，不是「相对锁定底板的张数差恰好为一进一出」。163 没测「新冲天能量 vs 不公印章」，是因为那次走 field-pick + 代表表 base-only，这条差没有被列出来。本任务把「列出来」补上，仍然不自动开测、不自动采纳。
- `--include "卡名 [card_id]"` 把一张牌注入搜索空间，换出槽仍要搜索去配，并且会花预算。Owner 点名的「A −1 / B +1」需要单独的槽，指定两侧印刷。
- 印刷级换入已有：`SwapCfg.in_id`（task 115）。换出侧 `SwapCfg.out` 仍是卡名，同名多印刷整槽拒绝。短清单的产物用 task 164 那种 `N 卡名 [card_id]` 文件，交给现成的 `entry.modified`，不走名字级 swap。
- `PrepCfg.family_size`（默认 1，task 161）透传到一次 `mod_check_report`。`mod-check --family-size`（task 159）只把全显著门改成 Bonferroni α/M，逐格 p 仍是原值。prep 一次只有一个 `entry.modified`，`batch.json` 只有一条 mod 臂。多候选今天要手写多份 yml；漏写同一个 M 就会退化成多次独立 α=0.05。
- 过滤链可复用：`dsl_reject_reason`、`validate_deck`（60 张 / 同名 ≤4 / ACE SPEC ≤1）、`load_deck`。

## 范围外

- 从零生成卡组、遗传或进化模拟赛、重启 BC/RL 或 `value_guide`、无终止的 sim 爬坡。
- 调用 `run_swap_search`，或给短清单接筛选档 / 确认档 / `--budget`。
- 读到正的 Δ 之后改底板、把 sim 胜者当成下一轮短清单的 base、或在过门表上再叠一张牌。下一轮要换底板，必须回到一张真实牌表重新锁定。
- 多卡组合差（对称差超过一进一出）、跨 archetype 高频牌、用 `fetched_at LIMIT 50` 悄悄代替合格场窗。
- 新的多重比较公式。BH 仍留在 swap-search 的大空间扫描里。
- 把 N 个候选塞进同一个 `batch.json`（现有批次协议没有多 mod 臂）。

## 设计定案

- **D-166-1 短清单，不搜索。** 新的只读函数放在 `swap_search.py`（或它旁边的同层模块），CLI 挂在现有 `swap-search` 上：`--list-only`。此模式下 `--vs` 与 `--budget` 不再必填，处理函数直接拒绝二者同时出现。不带 `--list-only` 的旧命令参数与行为不变。
- **D-166-2 差的定义。** 底板与每一张对照表都做成 `card_id → count`（`deck_cards.count`，印刷级）。保留的差满足：两侧计数对称差的绝对值和为 2，且恰好一个 `card_id` −1、另一个 +1。两侧 `is_ace_spec` 都为真时，`kind=ace-slot`，否则 `kind=print-diff`。ACE 槽不是额外配额，只是这种一换一的标签。差了 ACE 又差了别的牌，整张对照表丢弃，不把它收成「只换 ACE」。
- **D-166-3 频率。** 一张对照表计 1，按 `deck_id` 去重，不按出场行累加。`n_lists < 2` 的差不进入短清单（只出现一次不算「反复出现」）。按 `n_lists` 降序、`card_id` 升序，默认最多 5 条，`--top-k` 上限 8；超出的只报告条数，不写出候选。没有重复差时，清单可以只有 Owner tech，这是正常结果。
- **D-166-4 对照总体。** 合格场窗由调用方传入（165 的窗）。查询沿用已有侦察口径并加上权重过滤：`deck_appearances ⋈ tournaments ⋈ decks ⋈ deck_cards ⋈ v_tournament_weights`，`archetype_name` 与底板相同、`deck_id` 排除底板、日期在窗内、`rank > 0`、`decks.mapping_status='full'`（与 `docs/digs/2026-11-15-t135-scout.py` 一致），权重侧条件与 `QUALIFIED_WHERE` 一致（`basis=cn`、master 或 NULL、`is_qual=0`、`is_team=0`、`static_weight IS NOT NULL`）。`shortlist.md` 头注写明这两条过滤。若 165 的只读查询表明 `rank = 0` 仍是真实出场而不是无效行，再改过滤并改测试，不在实现时静默放宽。任一表或列不存在则 `ValueError`，不退回 `fetched_at LIMIT 50`。
- **D-166-5 Owner tech。** 重复参数 `--tech`，格式 `换出 [out_id] → 换入 [in_id]`，两侧都是印刷。校验：`get_card` 命中、换出印刷确在底板且张数 ≥1、换入走 `dsl_reject_reason`、换后列表走 `validate_deck`。失败即 `ValueError`（不猜）。与已有差完全相同则合并为一行，`kind` 同时记下 `owner-tech`，家族只计一次。点名 tech 不受 `n_lists ≥ 2` 与 top-k 限制，但计入 `family_size`。
- **D-166-6 家族记账。** `family_size = 写出的候选数`（去重后）。每个候选一份 60 行 decklist（`N 卡名 [card_id]`，排序稳定）。`--pool` 必填：底板 `archetype_name` 必须等于池内某一行的 `archetype`，否则 `ValueError`（短清单只服务 field-pick 锁定的池内套）。`--seed-start` 缺省时不写 yml，只写清单，此时 `--matrix-snap` 不必给。给出 `--seed-start` 时 `--matrix-snap` 必填，并按候选写出 prep yml 骨架：`entry.deck_id` = 底板，`entry.modified` = 该 decklist，`entry.archetype` 取池内中文名，`field` 用本次窗，`games_per_cell: 2000`，`agents: heuristic`，每份 `family_size` 相同。种子按每候选 2000 个顺延（第 i 个起点 = `seed_start + i * 2000`），不调用 `run_prep`。种子是否与历史重叠由调用方 `grep`，函数不读 `experiments/`。
- **D-166-7 不采纳。** 清单与 yml 头注固定一句：「候选清单。过门也只是实战候选，不改底板。」输出里没有胜率、p 值或「采纳」字段。

## CLI 与输出

```text
bfsim swap-search --deck <deck_id> --list-only \
  --field-from <YYYY-MM-DD> --field-to <YYYY-MM-DD> \
  --pool config/target-pool.v2.yml \
  [--top-k 5] \
  [--tech "粉碎之锤 [30thDC-029] → 老大的指令 [30thDC-039]"] \
  [--seed-start N --matrix-snap <matchup-snap.json>] \
  [--out results/shortlist-<deck_id 的末段>/]
```

`--list-only` 时 `--field-from`、`--field-to`、`--pool` 必填；`--matrix-snap` 与 `--seed-start` 同进同退。`--db` 与 `--cards-dir` 沿用现有缺省。

目录内：

- `shortlist.json`：`base_deck_id`、`archetype`、`window`、`population.n_lists`、`population.source`、`family_size`、`candidates[]`。每条候选含 `id`、`kind`（`print-diff` / `ace-slot` / `owner-tech`，合并时为数组）、`out`、`in`（各有 `name`、`card_id`、`count_delta`）、`n_lists`、`decklist` 相对路径。
- `shortlist.md`：同一内容的人读表，首行是 D-166-7 的头注，加上场快照限定语不在此重复发明——yml 仍交给 prep，prep 报告自带 `QUALIFIER_HEADER`。
- `candidates/<id>.deck.txt`：60 行印刷级牌表。
- 仅当传入 `--seed-start`：`prep/<id>.yml`，可被现有 `load_prep_cfg` 读入。

`population.source` 写死为上述连接说明，方便 167 核对清单是不是同一窗。

## 验收标准（测试清单）

先写测试再实现。夹具用临时 sqlite，表只建查询真正读到的列。

- [ ] `--list-only` 不调用 `run_swap_search` / `execute_experiment`（monkeypatch 后断言未调用），不创建结果库。
- [ ] 三张同 archetype 对照表里，两张相对底板是同一印刷一换一、一张是别的一换一：前者 `n_lists=2` 入选，后者 `n_lists=1` 不入选。同一 `deck_id` 两行出场只计 1。
- [ ] 两侧都是 ACE SPEC 的一换一，`kind` 含 `ace-slot`。底板与对照表还差第三张牌时，不产出「只换 ACE」的候选。
- [ ] 对照表里高频、但底板张数相同的牌不入选（挡住 `candidate_in_cards` 那种「常见牌」误当差）。
- [ ] `--tech` 指向不在 top-k 里的一换一：仍入选，`family_size` 把它算进去；与已有差相同则不增加条数。
- [ ] 换入印刷无 DSL 且非豁免、ACE SPEC 变成 2 张、`out_id` 不在底板、card_id 不存在：各自 `ValueError`，不写半份清单。
- [ ] 合格权重过滤：`static_weight IS NULL` 的场上的对照表不进入 `population.n_lists`。缺表时 `ValueError`，输出里不出现 `LIMIT 50` 的退路。底板 archetype 不在 `--pool` 内时 `ValueError`。
- [ ] top-k：6 个 `n_lists≥2` 的差、默认参数只写 5 条，json 另有 `omitted` 计数；`--top-k 9` 拒绝（上限 8）。
- [ ] `--seed-start 780000` 且两条候选：两份 yml 的 `seed_start` 为 780000 与 782000，`games_per_cell` 都是 2000，`family_size` 都是 2，`load_prep_cfg` 通过。不传 `--seed-start` 时目录里没有 yml；只传 `--seed-start` 不传 `--matrix-snap` 则 `ValueError`。
- [ ] 旧命令：不带 `--list-only` 时缺 `--vs` 或缺 `--budget` 仍失败；现有 `tests/test_swap_search.py` 不改断言语义。
- [ ] 清单 json 无胜率键；md 含「候选清单。过门也只是实战候选，不改底板。」
- [ ] 全量 pytest 绿，ruff 零告警。

## 实现要点

- argparse 上 `--vs` / `--budget` 改为非 `required=True`，必填检查放进 `_cmd_swap_search`：`--list-only` 与这两个参数互斥；否则二者仍必填。
- decklist 行格式与 `experiments/t164-dragapult-neoupper.deck.txt` 一致，便于 `entry.modified` 直接引用。测试不依赖那份真实牌表。
- 166 不跑 165 的重跑，也不替 167 填写具体底板。函数的底板参数是调用方已经锁定的 `deck_id`。
- 默认输出在 `results/` 下（不进版本控制）。167 真要开跑时，再把当时选用的 decklist 与 yml 抄进 `experiments/`。

## 结果与遗留

未开工。本文件只立项。实现与测试在 Owner 拍板之后。167 若先于本任务开跑，按 167 的「166 未落地」条款只带 Owner 点名的两刀，不在这里预填多龙的差。
