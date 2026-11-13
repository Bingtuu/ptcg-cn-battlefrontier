# task 113 · v2 换卡敏感性首个正式资产（多龙黑夜魔灵 1×3 扫描）

- 状态：待执行（预注册判据已冻结，见 §3；拍板 = 按草案立项 2026-11-13）
- 关联：task 075（换卡报告管道）/ claims register「换卡敏感性」行（有代码无正式资产空档）；零代码变更线
- 规格：`docs/superpowers/specs/2026-11-13-task-113-v2-swap-asset-design.md`

## 目标

用 task 075 已合 main 的冻结换卡管道，产出首个带预注册判据与阴性对照的换卡敏感性正式资产。纯跑批 + 验证任务：不改 `battlefrontier/` 任何代码；如发现管道缺陷，停手另立 task（同 task 112 越界纪律）。

## 选刀（数据驱动，已定）

- 卡组 = **多龙巴鲁托 黑夜魔灵** `mik_moe:676344`（v2 池 WUR #1 = 23.55%、窗口 n=664、52 次出战）。
- 换卡三刀（牌表 60 张 26 种，已只读核验）：

| 刀 | 换出 → 换入 | 预期 |
|---|---|---|
| A 球轴 | 高级球 −1 ← 巢穴球 +1 | 有效应（检索轴微调） |
| B 引擎 | 多龙奇 −1 ← 摔角鹰人 +1 | 有效应（进化线 vs 技师打手取舍） |
| C 阴性对照 | 愿增猿 −1 ← 弗图博士的剧本 +1 | ≈0（1-of 边缘科技位互换，验证 pipeline 噪声底） |

## 协议

- 实验定义：base + 3 variants，各 500 局、同种子区间（CRN 成对，对齐矩阵口径），启发式 agent，16 workers；预期墙钟 1–2 分钟。
- 实验定义文件入版本控制：`experiments/v2-swap-dragapult-dusknoir.example.yml`。
- 跑批命令（模式照 task 075 模板）：

```bash
bfsim run experiments/v2-swap-dragapult-dusknoir.example.yml --workers 16 --results results/v2-swap-dragapult.db
bfsim sensitivity <base_id> <variantA_id> <variantB_id> <variantC_id> --results results/v2-swap-dragapult.db --out results/v2-swap-dragapult
```

## 验收标准（预注册硬指标，全过才收）

1. 4 个实验失败 0；串行=并行 events_hash 抽验过（≥20 局）。
2. 报告包四件齐全：swap.md / swap.html / swap.csv / swap.json + 回放样本；`SIM_INTERPRETATION_NOTE` 限定语自动继承内嵌。
3. **阴性对照（刀 C）|ΔWR| 的 bootstrap CI 覆盖 0**——不覆盖 = pipeline 噪声底可疑，整个资产不收、dig 记录原因。
4. 结论表述只限「同模拟器内敏感性」（= 同模拟器内对比），零真实预测措辞；产物摘要进 `docs/digs/`、STATUS 工作记录。
5. 全程 `ruff check .` 零告警、`pytest -q` 全量绿（应零变化）。

## 实现要点

- 只新增：1 个实验 yml + 结果库 + 报告包 + dig + STATUS/task 文档。不改代码。
- variants 声明照 task 075 模板语法（`swaps: [{side, out, out_count, in, in_count}]`）；换入卡须通过 `load_deck` 合法性（60 张、赛制合法），跑批前 `dsl-check` 不涉及（无新卡定义）。
- 若 `bfsim sensitivity` 多 variant 参数不支持或行为异常 → 停手，缺陷另立 task，不现场改代码。

## 结果与遗留

- **跑批（2026-11-13）**：4×500 局种子 400000..400499 CRN 成对，失败 0/2000，墙钟 33s。baseline 52.2%；A +0.0%（CI −6.2..+6.2）；B −6.2%（CI −12.4..−0.0，p=0.0499）；C 阴性对照 −1.2%（CI −7.4..+5.0，**覆盖 0 ✅**）。
- **门复核 5/5 ✅**：串并 20/20（抽验查询首版漏过滤 experiment_id 一度读数 1/20，过滤后 20/20——dig 已披露）；产物四件经 **task 114** 补 `format_sensitivity` 限定语后内嵌；阴性对照过线；表述限定「同模拟器内敏感性」；全量绿 + ruff 零告警（task 114 后）。
- **释义降级披露**：swapA/B 换入卡（巢穴球/摔角鹰人）解析到 DSL 未覆盖印刷按 vanilla 结算 → A/B 实测为「移除 + 死卡」而非「功能替代」（A=高级球 3→2 零效应；B=多龙奇 4→3 −6.2pp 显著）。dig：`docs/digs/2026-11-13-task113-v2-swap-asset.md`。
- **遗留**：管线缺口候选（swap `in` 印刷不可指定，需 `in_id` 印刷级支持才能跑真功能替代）——待 Owner 拍板另立 task。
