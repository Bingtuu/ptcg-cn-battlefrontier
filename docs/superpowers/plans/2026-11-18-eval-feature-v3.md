# 评估器特征 v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 评估器特征扩维 v3（36 基座 + 4 区 × 131 卡身份 = 560 维），numpy 分块训练路径，资产 format `bf-linear-eval-v3`，采集/训练/判读三连跑批过 task 150 门（v2.x AUC ≥ 0.90）。

**Architecture:** 新模块 `battlefrontier/agent/eval_features.py`（特征层，M11/policy 既有常量只读复用）；`FeatureCollector` 增可选 v3 路径（默认 v1 逐位不变）；数据行紧凑格式（header 钉 feature_names + 位置 float list）；`battlefrontier/learn/train_v3.py` 分块两遍流式 numpy 岭回归；`learn/model.py` format 分派装载/预测。预注册与判据全部冻结在 `tasks/task 155.md`——本计划只含实现步骤，不得改判据。

**Tech Stack:** Python 3.12 / numpy>=2（float64 分块 np.dot）/ pytest / ruff。冻结判读脚本 `.kimi-code/t150_eval_gate.py` 不动。

---

### Task 1: 特征层 v3（`battlefrontier/agent/eval_features.py`）

**Files:**
- Create: `battlefrontier/agent/eval_features.py`
- Test: `tests/test_eval_features_v3.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_eval_features_v3.py —— 骨架（实现期补全全部用例）
from battlefrontier.agent.eval_features import (
    EVAL_V3_BASE_NAMES, EVAL_V3_ZONES, eval_v3_names, feature_vector_v3)

def test_base36_key_order():
    # 基座 36 维 = M11 FEATURE_NAMES 原序 + DISCARD_FEATURE_NAMES 原序
    from battlefrontier.agent.features import FEATURE_NAMES
    from battlefrontier.agent.policy_features import DISCARD_FEATURE_NAMES
    assert EVAL_V3_BASE_NAMES == FEATURE_NAMES + DISCARD_FEATURE_NAMES

def test_names_layout():
    vocab = ("乙:", "甲:")  # 字典序钉死
    names = eval_v3_names(vocab)
    assert names[:36] == list(EVAL_V3_BASE_NAMES)
    assert names[36:] == [f"cid_{z}_{n}" for z in EVAL_V3_ZONES for n in vocab]

def test_zone_counts_and_stadium():
    ...  # 构造 VisibleGameState：己方手牌 2 张同名训练家 → own_hand 区计数 2；
         # 盘面进化栈 + 附着能量 + 道具进 board 区；stadium one-hot；无场全零

def test_oov_raises():
    ...  # 词表外卡名 → ValueError（不猜）

def test_opponent_hand_identity_leak_free():
    ...  # 对手手牌卡名不出现在任何 cid_ 特征（对手手牌只有 count 基座维）

def test_deterministic_pure():
    ...  # 同视图两次调用逐位相等；无随机无引擎调用
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_eval_features_v3.py -q` → ImportError
- [ ] **Step 3: 实现** — 复用 `features.feature_vector`（30 维）+ `policy_features.policy_state_features` 的弃牌 6 维口径 + `_pokemon_cards`；4 区计数置位；词表外 ValueError。
- [ ] **Step 4: 测试绿** — `pytest tests/test_eval_features_v3.py -q`
- [ ] **Step 5: commit** — `task(155): 特征层 v3——36 基座 + 4 区卡身份计数（M11 清单只读复用）`

### Task 2: 采集 v3（header + 位置行 + CLI `--feature-set`）

**Files:**
- Modify: `battlefrontier/agent/collect.py`（`FeatureCollector` 增 `feature_set`/`vocab` 可选参数，默认 None = v1 逐位不变）
- Modify: `battlefrontier/runner/collect.py`（v3 写 header 行 + 位置行；v1 路径不动）
- Modify: `battlefrontier/cli.py`（`collect-features` 增 `--feature-set {v1,v3}` 默认 v1；v3 必填 `--db` 构建词表——复用 `build_card_vocab`）
- Test: `tests/test_collect_v3.py`

- [ ] **Step 1: 失败测试** — v3 文件首行 header（`format == "bf-collect-v3"`，feature_names 与 `eval_v3_names(vocab)` 一致）；数据行 features 为 list 且宽度 == len(feature_names)；`feature_vector_v3` dict → 位置 list → 按 header 还原 dict 逐位相等；header 宽度与行宽度不符 → ValueError；缺省 v1 产出与现网逐字节一致（用既有采集冒烟对拍）。
- [ ] **Step 2: 确认失败 → Step 3: 实现** — `FeatureCollector(feature_set="v3", vocab=...)`：`on_decision` 记位置 list（v1 仍记 dict）；`runner/collect.py` v3 分支先写 header；词表由 CLI 侧 `build_card_vocab(args.pool, db_path)` 算好传入（worker payload 带 vocab，保多进程确定性）。
- [ ] **Step 4: 测试绿 → Step 5: commit** — `task(155): 采集 v3——header 钉清单 + 位置行紧凑格式（默认 v1 零变化）`

### Task 3: 训练 v3（`battlefrontier/learn/train_v3.py`，numpy 分块两遍）

**Files:**
- Create: `battlefrontier/learn/train_v3.py`
- Modify: `battlefrontier/cli.py`（`train-eval` 增 `--feature-set {v1,v3}` 分派；v3 拒绝 v1 数据、v1 拒绝 v3 数据——显式报错）
- Test: `tests/test_train_eval_v3.py`

- [ ] **Step 1: 失败测试** — 小数据（如 3 对 × 20 局 × ≤560 维）分块两遍实现 vs 参考实现（全量 `X.T @ X` / `X.T @ y`，同 λ）`np.allclose(atol=1e-10)`；λ 候选 {0.1,1,10,100,1000,10000} 选择规则（最小验证 MSE、并列小 λ）；meta 必含 card_vocab/zones/rows/games/λ/MSE 全家；死维度警戒沿用；v1 dict 行数据喂 v3 → ValueError。
- [ ] **Step 2: 确认失败 → Step 3: 实现** — 流式读 JSONL（header 取 feature_names 与 meta 词表；chunk=50,000 钉死）；pass 1 分块累加 sum/sumsq → mean/std（常数维 std 置 1）；pass 2 分块标准化后 `np.dot(Xc.T, Xc)` / `np.dot(Xc.T, yc)` 累加；`(XᵀX + λI) w = Xᵀy` 用 `np.linalg.solve`；按局 split / subsample 复用 `learn.train.split_by_game` / `subsample_rows`（行结构兼容：v3 行 features 为 list，需按 header names 取位置索引——在 loader 层一次性转列索引，后续行直接切片）。
- [ ] **Step 4: 测试绿 → Step 5: commit** — `task(155): 训练 v3——numpy 分块两遍流式岭回归（λ 候选扩六档，D3-4 非复算面延续）`

### Task 4: 资产 format 分派（`learn/model.py` v3 装载/预测）

**Files:**
- Modify: `battlefrontier/learn/model.py`（v1 路径逐字不动；新增 `MODEL_FORMAT_V3 = "bf-linear-eval-v3"` 分派）
- Test: `tests/test_model_v3_dispatch.py`

- [ ] **Step 1: 失败测试** — v3 资产 round-trip（save/load/predict 输出 ∈ [0,1]）；v3 meta 缺 card_vocab/zones → ValueError；v3 特征清单以资产为准（不再对 FEATURE_NAMES）；`predict(model, VisibleGameState)` 对 v3 资产走 `feature_vector_v3`；**v1 资产现有全部测试保持绿（回归锚：v1 format 校验路径逐字不变）**。
- [ ] **Step 2: 确认失败 → Step 3: 实现** — `load_model` 按 `payload["format"]` 分派；v3 校验 weights/mean/std 维度 + std 正 + meta 必含 card_vocab（tuple）/zones（tuple）；`predict` 分支：v3 → `feature_vector_v3(view, vocab=tuple(meta["card_vocab"]), zones=tuple(meta["zones"]))`，再按模型 feature_names 顺序取点积（顺序 = 资产内钉死清单）。
- [ ] **Step 4: 测试绿 → Step 5: commit** — `task(155): 资产 v3 分派——bf-linear-eval-v3 装载/预测（v1 路径不动，冻结 gate 脚本调用面兼容）`

### Task 5: 跑批三连 + gate 判读 + 收尾

**Files:**
- Run: `results/m11-v2x-v3data/`（gitignored）、`models/eval-linear-v3.json`（版本控制）
- Docs: `docs/digs/2026-11-18-t155-eval-feature-v3.md`、`CHANGELOG.md`、`STATUS.md`

- [ ] **Step 1: 采集** — `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m battlefrontier.cli collect-features --pool config/target-pool.v2.yml --games-per-pair 1200 --seed-start 960000 --out results/m11-v2x-v3data --workers 16 --feature-set v3 --db "C:/Vibe Project/Pokearena/data/ptcg-cn.db"` → 54,000 局零失败，行数与 m11-v2x-data 同量级（~400 万）落账。
- [ ] **Step 2: 训练** — `... train-eval --data results/m11-v2x-v3data --pool config/target-pool.v2.yml --out models/eval-linear-v3.json --feature-set v3` → 验证 MSE < 基线（健康门）。
- [ ] **Step 3: 判读** — `.venv/Scripts/python.exe -X utf8 .kimi-code/t150_eval_gate.py models/eval-linear-v3.json` → 主门 v2.x AUC ≥ 0.90？对照臂 v1 读数落账。（脚本与协议冻结，exit 0 = PASS）
- [ ] **Step 4: dig 报告** — 判读 + 归因 + 复放命令落 `docs/digs/2026-11-18-t155-eval-feature-v3.md`；PASS → task 150 门重判提案（重新预注册后执行）；FAIL → 停损评审输入。
- [ ] **Step 5: 收尾** — 全量 pytest + ruff；CHANGELOG Unreleased；STATUS 焦点；`git mv tasks/task\ 155.md tasks/done/`；commit `task(155): 评估器特征 v3——跑批判读 <PASS/FAIL>，细节`；push。

## Self-Review 记录

- **规格覆盖**：task 155 预注册六节（特征层/数据格式/数据/训练/资产/判据）→ Task 1–5 逐一对应；FAIL 处置不在实现范围（Owner 裁决项）。
- **占位符**：无 TBD；测试骨架用 `...` 处为示意，实现期按预注册口径补全断言（Task 1 Step 1 已列全部必备用例名）。
- **类型一致**：`feature_vector_v3(view, vocab, zones)` / `eval_v3_names(vocab)` / `EVAL_V3_ZONES` 在 Task 1 定义、Task 2/3/4 调用一致；`cid_<区>_<卡名>` 键名方案贯穿任务书/计划/资产 meta。
