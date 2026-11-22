# task 161 · Grok 二轮评审四项：证据包加固 + base-only 批次化 + family 接线 + 探针内容签名

- 状态：进行中
- 关联：task 158/159/160 加固轮（Grok 二轮 review，Owner 转达 2026-11-22）

## 背景

Grok 二轮 review 四项，采纳判断（Owner 转达时未定，随立项一并拍板）：

1. **证据包同名文件覆盖**（采纳，P0）：task 160 对手多构筑按 `Path(p).name`
   平铺 inputs/，不同目录同名 decklist 互相覆盖，manifest 哈希指向最后写入。
2. **base-only 接入批次协议**（采纳）：无改表臂的分支仍按名称前缀 LIKE 搜库，
   同名重跑混入旧批/旧构筑；也无证据包收尾。
3. **family_size 贯通 prep**（采纳接线 + 集成判读测试）：prep 未透传扫描族
   参数，证据包不记录；subprocess 级 prep E2E **降档不立项**（场数据管道
   sqlite-only，jsonl dist 走不通；现有 run_prep 集成测试已覆盖真 mod_check +
   真证据包链路，缺的是壳不是肉）。
4. **探针内容签名**（采纳降档）：赛事数/日期/版本不变时的纯内容修订（牌表
   更正/归类/权重）现判不出；sig 增合格行内容哈希（best-effort），并明示
   检测能力边界。

## 设计定案

- **D-161-1**：证据包文件一律 `f"{键}__{原名}"` 落 inputs/（键 = mod 或
  `{slug}~bN`，天然唯一）；**开跑前冻结**——run_prep 在 execute 之前捕获
  decklist 字节 + sha256，证据包收尾只消费冻结快照（源文件跑后被改不影响
  本批归档）。
- **D-161-2**：batch.json 两种模式——paired（base_id+mod_id，现行为）/
  base（仅 base_id，无改表臂）；`_base_only_section` 改按登记 ID 取数 +
  status/种子完整性校验（缺/中断 → INCOMPLETE 显式，不出完整结论）；
  前缀 LIKE 读取废弃。`_load_batch_arms` 校验逻辑复用（不另造机制）。
- **D-161-3**：`PrepCfg.family_size: int = 1`（正整数校验同 mod_check），
  run_prep 透传；verdict.json meta 落 family_size + 校正后采纳阈值。
- **D-161-4**：`qualified_content_sha256(db, d_from, d_to)` = 合格行
  (tournament_id, date, static_weight) 排序后 sha256；sig 增 `content_sha256`；
  探针比对（不一致 → backfill「内容签名」）；旧快照无该字段 → fresh 注记
  「计数与版本未变不保证内容未变（无内容签名）」。边界如实：上游牌表更正若
  不触碰 v_tournament_weights 行，哈希不动——检测能力上限明示，不重造信任链。

## 验收标准（测试清单）

- [ ] ① 三份同名不同内容 decklist（mod + 两对手构筑）全部保留、哈希各自正确；
  fake_execute 中途篡改源文件，归档内容 = 开跑前字节。
- [ ] ② 同名先跑多构筑再跑单构筑：base-only 读数只认第二批 ID（旧批零混入）；
  删一局 → INCOMPLETE 显式（不出完整基线结论）。
- [ ] ③ prep family_size=2：同组结果在 =1 显著、=2 校正后不显著，报告与
  verdict.json 一致且 meta 落 family_size；非法值拒收。
- [ ] ④ 同窗改 static_weight 一行（数与日期不变）→ 探针 stale(backfill 内容
  签名)；旧快照（无 content_sha256）→ fresh 带能力边界注记。
- [ ] 存量行为零变化：不带 opponent_builds/family_size 的 prep 定义、带旧
  sig 的快照，输出兼容（既有测试不改动语义）。

## 结果与遗留

2026-11-22 收官：9 新测全绿（三同名 decklist 保留/哈希归属、开跑后源文件
篡改冻结、base-only 同名两批隔离、base-only 缺局 INCOMPLETE、family_size
校正贯通 + 非法拒收、探针内容签名导出/判过期/能力注记），3 处既有测试随
归档命名更新（语义不变），ruff 零告警，全量重跑绿。

- ① `_freeze_inputs`：开跑前冻结，`{键}__{原名}` 落盘（键天然唯一）；
  fake_execute 中途篡改源文件的测试实证归档 = 开跑前字节。
- ② batch.json 增 `mode: paired|base`；`_load_batch_base_arms` 复用
  `_batch_keys` 校验（不另造机制）；base-only 废弃前缀 LIKE 搜库；
  INCOMPLETE 显式不出完整基线结论。
- ③ `PrepCfg.family_size`（ge=1）透传 mod-check；verdict meta 落
  family_size + adopt_alpha；subprocess 级 prep E2E 按立项降档不立项
  （场数据管道 sqlite-only，现有集成测试已覆盖真判读 + 真证据包链路）。
- ④ `qualified_content_sha256`：合格行 (tournament_id, date,
  static_weight) 排序哈希入 sig；同窗纯内容修订判 backfill；旧快照 fresh
  明示「计数与版本未变不保证内容未变」。

遗留（如实）：上游牌表更正若不触碰 v_tournament_weights 行，内容签名
不动——探针注记已明示此能力边界；base 模式 batch.json 两臂版本比对不适用
（单臂只记录不比对，版本纪律由 paired 模式承担）。

Grok 执行建议采纳情况：先修①✅；②③按实际用法补上✅；④收窄承诺✅。
「拿真实报名候选完整走一次备赛流程」= 下一步人工驱动（Owner 拍板卡表后
走 prep 全链路）。

