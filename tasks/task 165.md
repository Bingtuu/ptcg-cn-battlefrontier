# task 165 · 场数据权重补齐与选卡重跑

- 状态：进行中
- 关联：备赛目标环第 1 步（2026-11-28 Owner 收窄定位：当前场备赛工具）。顺序固定：① 本任务把场权重补齐到可以诚实重跑，或明确停下来等拍板 → ② task 166 在锁定的真实底板上出邻域短清单并按家族记账 → ③ task 167 在本任务之后的底板上做一轮预注册家族对照，然后冻结。若本任务无法赋权，167 可以沿现行 20 场排序继续，但底板必须标成暂定。前置留档：task 162（探针合格口径）/ task 163（窗 11-01..11-22、sig.n_qualified=20）/ task 156（`field-snap` / `field-pick`）。

## 目标

弄清「已有牌表出场、`static_weight` 仍为空」的赛事为什么进不了场快照；只在本仓真能修、且修法不发明权重时才改代码。权重一旦真实落地，或 Owner 书面接受暂定口径之后，用现成命令重跑 `field-snap` 与 `field-pick`，把排序记下来。在这份重跑记录落地之前，不把 `mik_moe:677868`、也不把 task 164 的 ACE 换卡写进报名锁定表。

## 已核对的事实（本仓记录，不是待查假设）

- 合格口径写在 `battlefrontier/runner/field_snap.py` 的 `QUALIFIED_WHERE`：`(division = 'master' OR division IS NULL) AND is_qual = 0 AND is_team = 0 AND basis = 'cn' AND static_weight IS NOT NULL`。`qualified_count`、`qualified_content_sha256`、task 162 之后的 `_LATEST_TOURNAMENT_SQL` 共用这一句。
- 本仓只读这张视图。`results_db.py` 的写入只覆盖实验结果表。AGENTS.md 的数据契约是主库只读。本仓没有计算或回写 `static_weight` 的函数。
- 探针在 task 162 之后对未加权行保持沉默是设计结果：`content_sha256` 只哈希已合格行（task 161 已写明「修订不触碰 `v_tournament_weights` 行则哈希不动」）。未加权新行不改变 `n_qualified`，也不改变内容签名，探针保持 `fresh`（退出码 0）。README §10 第 1 步「探针不动就不跑批」因此不能当成「本周末数据已经齐」。
- 2026-11-27 留档：最新合格日期 = 2026-11-22，该日 1 场 `static_weight=2.107`，窗 2026-11-01..2026-11-22 的 `sig.n_qualified=20`（task 162 真库对账、task 163 §1）。同日文字对未加权条数并不一致：task 163 写「11-21/22 另有 12 场已结束未加权」，task 162 遗留写「~10 条」。本任务以重新只读查询为准，不在文档里把两个旧数字揉成一个。
- 导出调用参数钉在 `STATS_USAGE_KW`（`include_qual=False`、`include_team=False`、`basis=cn`、`min_n=5`、`granularity=archetype`、`usage_basis=decks`）。`min_n=5` 是上游 `stats_usage` 的用量行门槛，与 `qualified_count` 不是同一道过滤。诊断要分别记下「合格赛事数」和「实际进入份额的行」。

## 待核实假设（Owner 2026-11-28 转达；本仓无查询留档，不得写成诊断结论）

执行时对上游 `ptcg-cn.db` 只读核对。核对前下列句子都只是问题单：

- 11-21/22 有 12 场非组队、`is_qual=0`、`static_weight IS NULL`。
- 其中 11 场已有牌表出场（每场 64 张、合计 704 张），但 `participant_count=0`。本仓产品代码与任务文档都没有 `participant_count` 这个列名；先看上游表或视图定义里有没有这一列或等价的选手数字段，没有就记「上游无此列」。
- `mik_moe:3817` 像是已加权场 `3824` 的空预告重复行；`3824` 自身出场不完整（128 名选手、45 行出场）。
- 11-15 有同类形态：6 场未加权但已有出场，合计 384 张牌表。
- 若这 11 场得到真实权重，窗内牌表数会明显上升，field-pick 排序可能移动。

本机工作区没有 `config/battlefrontier.local.yml`，也没有上游库。立项 PR 不跑这些查询。

## 范围外

- 从零生成卡组、遗传或进化模拟赛、重启 BC/RL 或 `value_guide`、无终止的 sim 爬坡。
- 做一套搜索来证明 task 163/164 的结论彼此一致。163 的排序与 164 的 +2.7pp 都是已归档读数，本任务不重跑对局去「验证它们」。
- 发明、插值、抄邻近场或按出场数臆造 `static_weight`。NULL 保持 NULL。
- 放宽 `QUALIFIED_WHERE`，把未加权行算进合格场或内容签名。
- 在重跑记录落地前锁定 `mik_moe:677868` 或「不公印章 → 新冲天能量」。

## 验收标准（测试清单）

诊断与重跑是本任务的交付。代码测试只在「本仓缺陷」那一支才写；停手那一支以诊断文档为验收，不配假权重夹具。

### 诊断（两条路都要）

- [ ] 只读查询留档（命令、库的 `user_version`、查询原文、结果表）：窗内逐 tournament 的日期、`is_qual`、`is_team`、`basis`、`division`、`static_weight`，以及能否连上 `deck_appearances`（task 135 侦察脚本已用过的 `deck_appearances ⋈ tournaments ⋈ decks`）。出场数用 `COUNT(*)` 与 `COUNT(DISTINCT deck_id)` 分开记。
- [ ] 原因归成且只归成一类，并引用查询结果：① 本仓把已经非空的权重丢掉（`STATS_USAGE_KW` 或 `QUALIFIED_WHERE` 与上游 `_base_meta` 不一致）；② 上游视图或 Pokearena 管道没有填写 `static_weight`；③ 填写权重所需的输入缺失（选手数、完整出场等，以库里真实列名为准）；④ 流程未跑（预告行、重复行、半成品场）。归类写进本 task「结果与遗留」，不写进代码注释代替。
- [ ] 诊断文档里没有任何一个由本任务填上的 `static_weight` 数值。

### 本仓真有缺陷时才实现

- [ ] 修复限在「已有非空权重却被本仓参数排除」的范围。回归测试用夹具库：一行合格非空权重必须进入 `qualified_count`；一行 `static_weight IS NULL` 仍不进入计数、不进入内容签名、不把探针打成 `stale`。
- [ ] 不改 `min_n` 的默认值。若 `min_n=5` 使小场进了合格计数却没进份额，诊断里记一笔，改不改门槛另等拍板。

### 权重不能在本仓诚实算出来时（预期路径，除非诊断推翻）

- [ ] 交付 = 诊断文档 + 选项 + 停手。选项只许这三条：
  1. 等上游回填。回填后现有探针的 backfill（`n_qualified` 或 `content_sha256`）会变成 `stale`，再跑下面的重跑命令。本仓零改动。
  2. Owner 书面接受暂定口径：task 167 用现行 20 场排序，底板标注「暂定」。
  3. 另一次拍板才允许做的可选项：探针 detail 增加窗内未加权条数的只读普查（列 tournament_id 与条数，不填权重）。这不是本任务的默认实现。
- [ ] 停手记录出现之前，不跑 field-pick、不改池、不写报名表。

### 重跑（权重已在上游出现，或 Owner 接受暂定口径之后）

- [ ] `bfsim field-snap --from 2026-11-01 --to <合格口径 MAX(date)> --out results/field-snap-<as_of>.json`。`<合格口径 MAX(date)>` 用 `QUALIFIED_WHERE` 的查询结果，不手填一个更晚的日期。
- [ ] 快照 `sig.n_qualified` 与同库 `qualified_count` 一致；`content_sha256` 落盘。暂定口径则沿用 task 163 的窗终点 2026-11-22，并在记录里写「未加权场仍不在快照内」。
- [ ] `bfsim field-pick --field <上一步快照> --pool config/target-pool.v2.yml --matrix-snap results/matchup-snap-2026-11-22.json`。池版本未改则复用这份矩阵，零对局。输出保留现成的限定语头注。
- [ ] 排序相对 task 163 留档（Dragapult 63.8% / 登顶率 100%，窗 11-01..11-22）的位移写成短记：谁升、谁降、代表 `deck_id` 变不变。这份短记是 task 166/167 的底板输入。
- [ ] 全量 pytest 与 ruff 只在有产品代码改动时作为门槛。纯诊断 + 重跑记录不要求为了本任务新跑全库。

## 实现要点

- 诊断查询走只读 URI（`file:…?mode=ro`），与 `swap_search._connect_ro`、`field_snap._sig_data_version` 相同。库路径读本机 `config/battlefrontier.local.yml`，不写进仓库。
- 已知可连的表：`v_tournament_weights`（本仓探针在用）、`deck_appearances` / `tournaments` / `decks` / `deck_cards`（`docs/digs/2026-11-15-t135-scout.py` 与 `docs/digs/2026-11-15-pool-freshness-check.md`）。列对不上就停在「上游无此列」，不换一个看起来像的列继续。
- 重跑只调用已有命令，不新写选卡器。`field-pick` 排的是卡池 archetype，代表牌表仍是 `config/target-pool.v2.yml` 里该行的 `deck_id`（多龙巴鲁托当前行是 `mik_moe:677868`）。重跑若要换代表表，本任务只记录建议，改池另立项。
- 暂定口径下的底板句子固定为：「暂定底板 = 现行 20 场排序下的池代表表；11-21/22 未加权场未入快照。」167 引用这句，不再改写。

## 结果与遗留

未开工。本文件只立项。诊断、可能的本仓修复、field-snap / field-pick 重跑都在 Owner 拍板实现之后。立项时上游 SDK 不在本工作区，权重公式未在本仓出现，因此默认预期是停手路径，而不是在这里补权重。
