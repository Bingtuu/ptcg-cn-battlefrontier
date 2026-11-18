# task 155 过线判读 — 评估器特征 v3（2026-11-19）

## 判决：待判读（训练/gate 跑批中，本文件先行落根因链）

## 动机与预注册回顾

task 150 FAIL（v2.x AUC 0.6743 < 0.90，in-distribution 重训 ΔAUC=−0.001）→ 归因 = 30 维特征层对 v2.x 新机制状态失明。Owner 裁决选项 A：特征 v3 立项（本任务）。预注册（tasks/task 155.md，2026-11-18 冻结）：

- 特征 v3 = 36 基座（M11 30 维 + 弃牌 6 维，只读复用）+ 4 区 × 131 词卡身份 = **560 维**；信息纪律（对手手牌身份零泄漏）有专项测试。
- 数据：与 task 150 同种子同局流（54,000 局 / seed 960000+），单变量 = 特征层。
- 训练：numpy float64 分块（50k 行）两遍流式；λ 候选六档 {0.1,1,10,100,1000,10000}。
- 主门：冻结脚本 `.kimi-code/t150_eval_gate.py` 不动，v2.x 对决（711854 沙奈朵 × 676344 多龙巴鲁托黑夜魔灵，20 局 seed 800000..800019）**AUC ≥ 0.90**；健康门 = 验证 MSE < 常数基线；对照臂（非门）= v1 对决读数（v2 资产参照 0.9659）。

## 采集根因链（5 次失败 → 第 6 次成功，如实记录）

v1 时代（task 150）同架构跑 54,000 局无恙；v3 把「行内存体积」抬了一个数量级，三连隐性上限连环引爆：

1. **第 1/3 次（~29 min 崩）**：旧 `run_collect` 把全批 54,000 局结果累积在主进程再统一写盘。v3 行 ≈ 20KB Python 对象（560 个独立 float 对象）× ~400 万行 ≈ 80GB 量级 → worker pickled 结果时 MemoryError。日志里醒目的 `concurrent send_bytes() calls are not supported` 是**清理期 terminate 竞态的次生噪音**（`_terminate_pool` 写哨兵与 `_handle_tasks` 并发写同一 named pipe），一度误导排查方向。
   **修复**（`58dfe5c`）：imap 结果逐条流式落盘（45 个 per-pair writer 提前打开），主进程内存 O(单局)；产物字节与累积版逐字节一致（既有字节锚测试绿）；中途异常保留已完成行（新回归测试锚）。异常路径吞清理期次生错误后重抛原始异常。
2. **第 4 次（2h 超时挂死）**：主进程 `_handle_results` 线程在读结果时 MemoryError，**线程静默死亡 → imap 永久等待**。实证 payload 仅 40KB（全批管道流量 2GB）——排除任务载荷。39/45 对完成（~46,800 局），吞吐健康（~30 min 走完全程 87%），纯粹内存天花板。
   **修复**：`Pool(maxtasksperchild=500)`（worker 回收定界地址空间棘轮，spawn worker 大对象 churn 不向 Windows 归还提交）。
3. **第 5 次（4h 超时）**：系统级提交耗尽——日志出现成排 `OpenBLAS error: Memory allocation still failed`，worker 重生时连 pydantic 都 import 不起（MemoryError），`_handle_workers` 线程再死于 `DuplicateHandle` 拒绝访问 → 挂死。
   **归因实测**：31.5GB 物理 + 19.5GB pagefile（提交上限 ~51GB）；**worker 经 `runner/experiment → agent/distilled` 传递性载入 numpy + OpenBLAS，每 worker 默认 22 BLAS 线程**，16 workers × 22 线程的缓冲 + 基线 = 压垮提交额度。
   **修复**：`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`（spawn 子进程继承）+ workers 16→12。
4. **第 6 次（成功）**：24.6 min，54,000 局零失败，**4,073,978 行**（+45 header，与 task 150 v1 数据行数逐一相等 = 同局流验证），12GB。

教训：并行产线的失败模式会叠层（应用层累积 → 运行时棘轮 → 第三方库默认配置），表层异常（send_bytes 竞态）经常不是根因。

## 口径与复放

- 采集：`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/Scripts/python.exe -X utf8 -m battlefrontier.cli collect-features --pool config/target-pool.v2.yml --games-per-pair 1200 --seed-start 960000 --out results/m11-v2x-v3data --workers 12 --feature-set v3 --db "C:/Vibe Project/Pokearena/data/ptcg-cn.db"`（第六次成功命令；日志 results/t155-collect.log）
- 训练：`.venv/Scripts/python.exe -X utf8 -m battlefrontier.cli train-eval --data results/m11-v2x-v3data --pool config/target-pool.v2.yml --out models/eval-linear-v3.json --feature-set v3`
- 判读：`.venv/Scripts/python.exe -X utf8 .kimi-code/t150_eval_gate.py models/eval-linear-v3.json`（t145/t150 冻结脚本不动；exit 0 = PASS）

## 判读（2026-11-19）：主门 FAIL——v2.x AUC 0.7571 < 0.90（特征 v3 有实益但不构成过线）

| 资产 | v2.x 对决（711854×676344，n=1782，冻结脚本原样） | v1 对决（对照臂） |
|---|---|---|
| eval-linear-v1（参照） | 0.6755 | 0.9718 |
| eval-linear-v2（task 150） | 0.6743 | 0.9659 |
| **eval-linear-v3（本任务）** | **0.7571**（极差 0.9302，输出活性健康） | **不可比**——v3 词表锚定 v2.x，v1 池卡名（'博士的研究'）触发词表外 ValueError（不猜纪律按设计拦截跨池预测；冻结脚本无防护，对照臂以崩溃告终，如实记录） |

训练健康：λ=10000（候选上限——如实记录，预注册纪律禁止跑数后扩档重扫）；验证 MSE 0.1758 vs 基线 0.2500（显著优于基线，无死维度警戒）；54,000 局 / 4,073,978 行 / 零失败。

**结论**：特征 v3 把 v2.x AUC 从 0.6743 抬到 0.7571（+0.083，方向证实 task 150 归因成立——特征层确实是瓶颈之一），但 560 维线性评估器距离 0.90 门仍有 0.14 差距。λ 顶到预注册候选上限提示正则尺度仍在收紧方向，但**按预注册 FAIL 处置执行：不续命、不重扫**，转 Owner 停损评审。

**FAIL 处置（预注册条款）**：回 M16 BC 停损评审（Owner 裁决）；task 151/152 维持冻结；v1/v2 资产保持可装载（v1 底板继续用 v1 资产）；eval-linear-v3.json 如实入库（训练健康、相对 v2 资产 +0.083 AUC，非废物资产，但 v2.x 底板仍未过门）。

**给 Owner 的决策输入（不预设立场）**：
1. **选项 A'：非线性评估器**（梯度提升树/小型 MLP）——0.7571 的线性天花板暗示交互项缺失（卡身份 × 局面因子交互），task 062 policy 线同款教训曾靠换模型类解决；成本 = 新训练管线 + 推理开销进 MCTS。
2. **选项 B：教师去评估器化**（task 150 dig 既有选项，BC 教师弃 eval 截断，成本 ×N）。
3. **选项 C：M16 延期**，BC 线挂起。
4. 若选 A'，λ 顶候选上限 + 对照臂不可比两条如实数据点一并带入新预注册。
