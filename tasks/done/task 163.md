# task 163 · 备赛全流程实战演练：新场数据下的选卡 → prep → 判读 → 证据包

- 状态：完成
- 关联：task 156（prep 编排）/ 157（批次协议）/ 158（证据包+签名）/ 159（family 校正）/ 160（对手构筑）/ 161（加固轮）；Grok 建议「拿真实候选完整走一次备赛流程」（2026-11-27 Owner 授权主会话自主选卡）

## 背景

上游新数据落地（2026-11-27 实测）：合格赛事窗可推进 11-15 → **11-22**
（19 → 20 场，+1 = 11-22 唯一已加权场；11-21/22 余 12 场已结束未加权，
属 Pokearena 侧待办，不阻塞）。Owner 授权：由主会话自主选择卡组配置，
完整走一遍加固后的备赛流程，产出可移植 README 的流程文档。

## 流程设计（即交付物骨架）

1. **数据就绪**：探针 + 上游合格赛事普查（已完成：20 场 11-01..11-22）
2. **场快照刷新**：`bfsim field-snap --from 2026-11-01 --to 2026-11-22`
3. **field-pick 选卡**：新场快照 × matchup-snap-2026-11-22（池 v2.x 11 套不变，
   矩阵复用）→ 期望胜率 + 登顶率排序 → **选择理由成文**（数据 + 历史判读资产）
4. **prep 全链路**：prep yml（基线臂 + 改表臂，同种子域 CRN 成对，
   strict 覆盖默认开）→ `--workers 16`
5. **mod-check --batch 判读**：COMPLETE 第四门 + 三门 + 池内条件期望
6. **证据包核验**：inputs/ 自含 hash + verdict.json/csv + 复算三元组
7. **流程文档**：`docs/digs/2026-11-27-t163-prep-walkthrough.md`（README 移植源）

## 验收标准

1. field-snap 导出 sig.n_qualified == 20，与上游直查逐位一致
2. field-pick 输出 11 套排序 + 限定语头注；选卡理由成文（含落选者原因）
3. prep 零失败局、装载零告警、strict 覆盖过闸；实验 ID 登记 batch.json
4. mod-check --batch：COMPLETE + 三门判读 + 条件期望落 verdict.json
5. 证据包：inputs/ 卡表副本 + sha256 + field-snap 副本 + manifest 自含
6. dig 流程文档产出（每步命令 + 判读口径 + 决策点）
7. 全量 pytest + ruff 绿（本任务零产品代码改动预期——纯流程演练；
   若暴露缺陷则另立修复）

## 实现要点

- 种子域避让：grep 全部历史 seed_start，选不重叠新区间
- family_size=1（单一预验证改表，非扫描族，诚实口径）
- 选择纪律：field-pick 排序是输入不是判决——结合 sim 口径限定语
  （自对局结果不构成真实胜率预测）与历史 mod-check 资产综合拍板

## 结果与遗留

**全流程七步全部走通，验收 7/7**（2026-11-28 凌晨收官）：

1. 数据就绪：合格赛事 19→20（11-22 +1 场），探针 task 162 修复后正确报 stale
2. 场快照 `results/field-snap-2026-11-27.json`：sig.n_qualified=20 == 上游直查 ✓
3. field-pick（新场 × 复用矩阵）：Dragapult 63.8%/登顶率 100% 三期连续第一；
   **首选 = 多龙巴鲁托 base-only，备选 = 沙奈朵 + t141 两刀改表 paired**，
   理由与落选说明成文（dig §3）
4. prep：60,000 局（20,000 + 40,000）**零失败零平局**，装载告警各 3 条
   vanilla 印刷（合法），strict 覆盖过闸，batch.json 登记
5. mod-check：gardevoir 门 = 全正 ✅ / 全显著 ❌（土龙节节 +1.4pp p=0.2328）/
   零回吐 ✅ / COMPLETE ✅；条件期望 60.3%→64.4%（+4.0pp）；**改表新场头下
   维持成立但强度降一档**（10/10 → 9/10 显著）；dragapult base 池内条件期望
   77.9%（全对手 ≥70.3%）
6. 证据包：两候选 inputs/ 全文件 sha256 重算 == manifest（含 mod 卡表副本、
   field-snap 副本、matrix_snap 引用）；verdict meta 落 family_size/adopt_alpha/
   复算三元组（0d1511149e1f… / c313d4f+dirty / user_version=14）
7. 流程文档 `docs/digs/2026-11-27-t163-prep-walkthrough.md` 全七节落盘
   （README 移植源）；本任务零产品代码改动（yml/md only）

**遗留**：上游 12 场待加权（Pokearena 侧，backfill 探针自动判出）；沙奈朵
vs 纯多龙 36.0% 大劣风险读数不变（报名决策归牌手）；败局解剖/换卡搜索
本轮无触发信号。产物：prep yml ×2（进版本控制）+ dig + results/ 证据包与
结果库（本机）。
