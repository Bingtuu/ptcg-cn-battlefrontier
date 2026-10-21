# 蒸馏特征 v2（卡身份 + 弃牌构成）实施计划 — task 062

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 task 061 诊断出的特征盲区（零卡面身份/零弃牌构成 → use_ability 不可分、特性引擎卡组崩盘），特征升 v2、资产升 bf-distilled-policy-v2、现有 171k 快照重训并复测锚 1 分 kind / 锚 2 matrix。

**Architecture:** 新模块 `agent/policy_features.py` 承载 v2 特征（不动 M11 钉死的 FEATURE_NAMES / ACTION_FEATURE_NAMES）；资产 format 按字段分派 v1/v2 装载（v1 资产保持可读）；训练零新采集（同快照、同超参、同 split_seed）。

**Tech Stack:** Python 3.12+ / pydantic v2 / numpy（runtime）/ torch（dev-only，仅 learn/train_policy.py）/ pytest / ruff。

**权威设计：** `docs/superpowers/specs/2026-10-19-distilled-features-v2-design.md`（D-062-1~5，用户已批准）

**环境口径（Windows Git Bash）：**
- Python：`.venv/Scripts/python.exe`（脚本一律 `PYTHONIOENCODING=utf-8 ... -X utf8`）
- 测试：`PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m pytest -q`
- Lint：`.venv/Scripts/ruff.exe check .`
- CLI：`bfsim` 等价 `.venv/Scripts/python.exe -X utf8 -m battlefrontier.cli`

---

### Task 0: 任务书落账

**Files:**
- Create: `tasks/task 062.md`

- [ ] **Step 1: 写任务书**

内容（状态：进行中；关联 task 060/061 + 设计文档路径；范围 = 本计划 Task 1–7；
验收标准逐条抄设计文档「验收标准」5 条）。

- [ ] **Step 2: Commit**

```bash
git add "tasks/task 062.md"
git commit -m "task 062 立项：蒸馏特征 v2（卡身份+弃牌构成）任务书"
```

---

### Task 1: `agent/policy_features.py` — v2 特征层 + 卡词表

**Files:**
- Create: `battlefrontier/agent/policy_features.py`
- Test: `tests/test_policy_features.py`

口径钉死（设计 D-062-1/2/3）：
- `POLICY_STATE_NAMES` = FEATURE_NAMES（30）+ 固定 6 维弃牌构成：
  `own_discard_count / own_discard_energy_count / own_discard_pokemon_count /
  opp_discard_count / opp_discard_energy_count / opp_discard_pokemon_count`
  （弃牌堆公开：view.own.discard / view.opponent.discard 均可见；
  分类走 `c.card.supertype == Supertype.ENERGY / POKEMON`）
- `policy_action_names(card_vocab)` = ACTION_FEATURE_NAMES（26）+
  `tuple(f"card_{n}" for n in card_vocab)`（112 维，词表序即键序）
- `build_card_vocab(pool_path, db_path)`：`load_target_pool` → 每条
  `load_deck(db_path, entry.deck_id)` → 全部 CardDef.name 去重排序（字典序）
- 身份解析 `resolve_action_card_names(action, view)`：
  - `attack` / `retreat`（无 iid）→ `(view.own.active.current.card.name,)`（无战斗场 = 空）
  - 其余：`action.iid` + `action.choices` 各 iid → iid→名映射反查
    （映射源：own.hand / 双方 active+bench 的 stack+attached_energy+attached_tool /
    双方 discard / view.pending_pool）
  - iid 不在映射 = 跳过（身份不可见，非报错）
- `policy_action_features(action, view, card_vocab)`：`action_features(action, view)`
  + one-hot（choose 多 iid 命中 = multi-hot 置 1）；解析出的名不在词表 →
  `ValueError`（词表外不猜）
- `policy_state_features(view)`：`feature_vector(view)` + 6 维

- [ ] **Step 1: 写失败测试 `tests/test_policy_features.py`**

```python
"""task 062 WP1：v2 特征层（卡身份 one-hot + 弃牌构成）。"""
import pytest

from battlefrontier.agent.action_features import ACTION_FEATURE_NAMES
from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.agent.policy_features import (
    POLICY_STATE_NAMES,
    build_card_vocab,
    policy_action_features,
    policy_action_names,
    policy_state_features,
    resolve_action_card_names,
)
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import Supertype
from tests.helpers import ...  # 复用现有 fixture 构造器（见 tests/helpers.py 既有卡/状态构造）

VOCAB = ("沙奈朵ex", "基本超能量", "博士的研究")


def _mk_card(name, supertype=Supertype.POKEMON, **kw):
    ...  # 参照 tests/helpers.py 既有 CardDef 构造惯例


def test_state_names_order():
    assert POLICY_STATE_NAMES[:30] == FEATURE_NAMES
    assert POLICY_STATE_NAMES[30:] == (
        "own_discard_count", "own_discard_energy_count", "own_discard_pokemon_count",
        "opp_discard_count", "opp_discard_energy_count", "opp_discard_pokemon_count")


def test_action_names_order():
    names = policy_action_names(VOCAB)
    assert names[:26] == ACTION_FEATURE_NAMES
    assert names[26:] == ("card_沙奈朵ex", "card_基本超能量", "card_博士的研究")
    # 注：词表序 = 传入序；构建侧 build_card_vocab 保证字典序


def test_discard_composition():
    # 构造 view：己方弃牌 2 能量 + 1 宝可梦，对方弃牌 1 训练家
    ...
    feats = policy_state_features(view)
    assert feats["own_discard_count"] == 3.0
    assert feats["own_discard_energy_count"] == 2.0
    assert feats["own_discard_pokemon_count"] == 1.0
    assert feats["opp_discard_count"] == 1.0
    assert feats["opp_discard_energy_count"] == 0.0
    # M11 特征原样携带
    assert feats["turn_norm"] == pytest.approx(min(view.turn, 50) / 50)


def test_resolve_use_ability_field_iid():
    # use_ability iid = 场上沙奈朵ex stack 顶 iid → 解析出 "沙奈朵ex"
    ...
    assert resolve_action_card_names(
        Action(kind="use_ability", iid=poke_iid), view) == ("沙奈朵ex",)


def test_resolve_attack_is_own_active():
    ...  # Action(kind="attack", attack_index=0) → (己方战斗场卡名,)


def test_resolve_choose_multihot_and_hidden_iid_skipped():
    # choose choices=(手牌 iid, 不可见 iid) → 只解析可见者
    ...
    names = resolve_action_card_names(Action(kind="choose", choices=(iid_seen, 99999)), view)
    assert names == ("博士的研究",)


def test_policy_action_features_onehot_and_vocab_guard():
    feats = policy_action_features(Action(kind="play_trainer", iid=hand_iid), view, VOCAB)
    assert feats["card_博士的研究"] == 1.0
    assert feats["card_沙奈朵ex"] == 0.0
    assert feats["kind_play_trainer"] == 1.0
    with pytest.raises(ValueError, match="词表"):
        policy_action_features(Action(kind="play_trainer", iid=unknown_card_iid), view, VOCAB)


def test_build_card_vocab(tmp_path):
    # 词表构建走 pool yml + db——用合成小 pool + 合成 db 或 mock load_deck；
    # 断言：去重 + 字典序 + 名称来自 CardDef.name
    ...
```

（fixture 细节以实现时 tests/helpers.py 既有构造器为准；上面每个 `...` 处
必须先落成真实构造代码再跑红。）

- [ ] **Step 2: 跑红**

Run: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m pytest tests/test_policy_features.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `battlefrontier/agent/policy_features.py`**

完整实现上述五个公开函数 + 模块 docstring（口径引用 D-062-1/2/3；
纯函数零引擎调用零随机源纪律声明）。

- [ ] **Step 4: 跑绿 + 全量回归**

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m pytest -q
.venv/Scripts/ruff.exe check .
```
Expected: 全绿（基线 1304+ + 新增）、ruff 零告警

- [ ] **Step 5: Commit**

```bash
git add battlefrontier/agent/policy_features.py tests/test_policy_features.py
git commit -m "task 062 WP1: v2 特征层（卡身份 one-hot 112 维词表 + 弃牌构成 6 维）"
```

---

### Task 2: `learn/policy_model.py` — 资产 v2（format 分派 + card_vocab）

**Files:**
- Modify: `battlefrontier/learn/policy_model.py`
- Test: `tests/test_policy_model.py`

- [ ] **Step 1: 写失败测试**

```python
def test_v2_roundtrip(tmp_path):
    model = PolicyModel(hidden=2, weights={...174 维形状...},
                        meta={"feature_version": "v2"},
                        card_vocab=("沙奈朵ex", "基本超能量"))  # 测试用小词表+对应形状
    save_policy_model(model, tmp_path / "m.json")
    loaded = load_policy_model(tmp_path / "m.json")
    assert loaded.card_vocab == model.card_vocab


def test_v1_asset_still_loads():
    # models/policy-m12-v1.json（已入库资产）按 v1 路径装载成功
    model = load_policy_model("models/policy-m12-v1.json")
    assert model.card_vocab is None


def test_v2_missing_vocab_rejected(tmp_path):
    ...  # format=v2 但无 card_vocab 字段 → ValueError（不猜）


def test_v2_feature_names_mismatch_rejected(tmp_path):
    ...  # state/action_feature_names 与 policy_features 清单不符 → ValueError
```

- [ ] **Step 2: 跑红** `pytest tests/test_policy_model.py -q` → FAIL

- [ ] **Step 3: 实现**

- `POLICY_FORMAT_V2 = "bf-distilled-policy-v2"`；`PolicyModel` 增
  `card_vocab: tuple[str, ...] | None = None`
- `save_policy_model`：`card_vocab` 非 None → format=v2，词表清单 =
  `POLICY_STATE_NAMES` / `policy_action_names(model.card_vocab)`，payload 增
  `card_vocab`；None → v1 旧路径原样
- `load_policy_model`：按 payload["format"] 分派——v1 走现有校验原样；
  v2 校验 card_vocab 非空 + 双清单与 `policy_features` 推导逐一相等 +
  权重形状 in_dim = 36 + len(policy_action_names(vocab))；meta 必须 dict 不变

- [ ] **Step 4: 跑绿 + 全量 + ruff**

- [ ] **Step 5: Commit** `git add battlefrontier/learn/policy_model.py tests/test_policy_model.py && git commit -m "task 062 WP2a: 策略资产 bf-distilled-policy-v2（format 分派，v1 保持可装载）"`

---

### Task 3: `learn/policy_data.py` + `learn/train_policy.py` — v2 样本与训练接入

**Files:**
- Modify: `battlefrontier/learn/policy_data.py`
- Modify: `battlefrontier/learn/train_policy.py`
- Test: `tests/test_policy_data.py`、`tests/test_train_policy.py`

- [ ] **Step 1: 写失败测试**

```python
def test_row_to_sample_v2_keys():
    # 合成快照行（沿用现有 fixture）+ VOCAB → 样本 state 键序 == POLICY_STATE_NAMES、
    # actions 每条键序 == policy_action_names(VOCAB)、教师下标不变
    ...


def test_train_policy_v2_meta_and_vocab(tmp_path):
    model = train_policy(samples, epochs=2, state_names=POLICY_STATE_NAMES,
                         action_names=policy_action_names(VOCAB), card_vocab=VOCAB)
    assert model.meta["feature_version"] == "v2"
    assert model.card_vocab == VOCAB
    # 形状：w1 行宽 = 36 + len(policy_action_names(VOCAB))
    assert all(len(r) == 36 + len(policy_action_names(VOCAB)) for r in model.weights["w1"])


def test_train_policy_v1_path_unchanged():
    # 不传 state_names/action_names → 旧 56 维口径 + meta feature_version 缺省 "v1"
    ...
```

- [ ] **Step 2: 跑红**

- [ ] **Step 3: 实现**

- `policy_data.row_to_sample(row, *, pair_index, card_effects, card_vocab=None)`：
  None → 旧特征路径（v1 回归不变）；非 None → `policy_state_features` /
  `policy_action_features(..., card_vocab)`
- `load_policy_samples(data_dir, card_vocab=None)` 透传
- `train_policy(..., state_names=None, action_names=None, card_vocab=None)`：
  缺省 = v1（FEATURE_NAMES / ACTION_FEATURE_NAMES，行为逐位不变）；
  v2 时 `_flatten_samples` 用传入键序（去 56 硬编码：`_INPUT_DIM` 改为
  `len(state_names) + len(action_names)`）；meta 增 `feature_version`
  （"v1"/"v2"），v2 时 `PolicyModel(..., card_vocab=card_vocab)`

- [ ] **Step 4: 跑绿 + 全量 + ruff**

- [ ] **Step 5: Commit** `git add battlefrontier/learn/policy_data.py battlefrontier/learn/train_policy.py tests/test_policy_data.py tests/test_train_policy.py && git commit -m "task 062 WP2b: 训练管线 v2 特征接入（v1 路径逐位不变）"`

---

### Task 4: `agent/distilled.py` — 推理 v2 分派

**Files:**
- Modify: `battlefrontier/agent/distilled.py`
- Test: `tests/test_distilled_agent.py`

- [ ] **Step 1: 写失败测试**

```python
def test_distilled_v2_forward_shape_and_identity_effect():
    # 合成 v2 小模型（小词表）：同状态两行动仅卡身份不同，
    # w1 中对应 card_* 列权重不同 → argmax 随身份翻转（钉死身份维度真实参与前向）
    ...


def test_distilled_v1_model_unchanged():
    # 既有 v1 资产装载 + observe 行为不变（现有测试原样绿即覆盖，此处显式补一例）
    ...


def test_distilled_v2_missing_vocab_rejected():
    # meta feature_version=v2 但 card_vocab=None → ValueError（不猜）
    ...
```

- [ ] **Step 2: 跑红**

- [ ] **Step 3: 实现**

- `DistilledAgent.__init__`：`version = model.meta.get("feature_version", "v1")`；
  v2 要求 `model.card_vocab` 非 None（否则 ValueError）；`_IN_DIM` 按版本推导
- `observe`：v2 路径用 `policy_state_features` / `policy_action_features(a, view, self._vocab)`
  按键序拼行；v1 路径原样；打分/掩码 argmax/ties 口径不变
- `runner/experiment.py` / `runner/agreement.py` 零改动（构造签名不变；
  仅更新 experiment.py:99/260 报错文案 "bf-distilled-policy-v1" →
  "bf-distilled-policy-v1/v2"）

- [ ] **Step 4: 跑绿 + 全量 + ruff + v1 资产冒烟**（既有 agreement CLI 冒烟
  快照重跑，v1 数字逐字节不变）

- [ ] **Step 5: Commit** `git add battlefrontier/agent/distilled.py battlefrontier/runner/experiment.py tests/test_distilled_agent.py && git commit -m "task 062 WP2c: DistilledAgent v2 特征分派（v1 行为不变）"`

---

### Task 5: CLI `train-policy` v2 接线 + 冒烟

**Files:**
- Modify: `battlefrontier/cli.py:358-402`（_cmd_train_policy）与 `:655-672`（argparse）
- Test: `tests/test_cli_train_policy.py`（既有文件扩展）

- [ ] **Step 1: 写失败测试**：`--pool` 提供时产出 v2 资产（meta feature_version="v2"、
  card_vocab 非空、shape 174 维口径随测试词表）；不提供时 v1 旧行为不变

- [ ] **Step 2: 跑红**

- [ ] **Step 3: 实现**：`--pool` 提供 → `build_card_vocab(pool_yml, load_db_path())`
  → `load_policy_samples(data, card_vocab=vocab)` → `train_policy(...,
  state_names=POLICY_STATE_NAMES, action_names=policy_action_names(vocab),
  card_vocab=vocab)`；打印追加词表大小；help 文案更新

- [ ] **Step 4: 跑绿 + 冒烟**：

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m battlefrontier.cli train-policy \
  --data results/m12-teacher-smoke --pool config/target-pool.v1.yml \
  --out results/policy-v2-smoke.json --epochs 2
```
Expected: 训练完成打印 + 词表 112 + meta feature_version=v2

- [ ] **Step 5: Commit** `git add battlefrontier/cli.py tests/test_cli_train_policy.py && git commit -m "task 062 WP2d: train-policy --pool 触发 v2 特征训练"`

---

### Task 6: WP3 正式重训 + 分 kind 一致率复测（主会话跑批）

- [ ] **Step 1: 正式训练 + double-run 确定性**

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m battlefrontier.cli train-policy \
  --data results/m12-teacher-pilot --pool config/target-pool.v1.yml \
  --out models/policy-m12-v2.json
# double-run：同命令第二跑出 /tmp 路径，sha256 逐字节比对
```
Expected: holdout argmax ≥ v1（0.4222）量级如实落账；double-run 全等

- [ ] **Step 2: 分 kind 一致率重放**：36 个快照文件逐跑
  `bfsim agreement <file> --policy models/policy-m12-v2.json`，
  聚合脚本（落 `.kimi-code/m12-task062-agreement-by-kind.py`，从各 pair JSON
  rows 按 teacher_kind 聚合）输出全 16 类一致率
- **终止判据**：use_ability 一致率 ≥ 18%（v1 全类均值 36.5% 的一半）。
  达不到 = 特征假设证伪，停止 WP4 回呈报，不硬推

- [ ] **Step 3: 价值损失复测**：`.kimi-code/m12-task061-d2.py` 改用
  `POLICY_PATH = "models/policy-m12-v2.json"` 重跑 v1 分母 + use_ability 分母，
  与 v1 数字对照落账

- [ ] **Step 4: Commit 资产**（D3-4）：

```bash
git add models/policy-m12-v2.json
git commit -m "task 062 WP3: policy-m12-v2 资产（特征 v2 重训，double-run 全等；分 kind 一致率实测）"
```

---

### Task 7: WP4 matrix 复测 + 确定性 + 呈报（主会话跑批）

- [ ] **Step 1: 实验定义**：`experiments/m12-distilled-matrix-v2.example.yml`
  ——复制 m12-distilled-matrix.example.yml，policy_path 改 v2，
  **seed_start 700000 不变**（同种子锚 = 与 v1 matrix CRN 成对可比），
  name 改 m12-distilled-matrix-v2，头注口径说明

- [ ] **Step 2: 跑批**

```bash
bfsim run experiments/m12-distilled-matrix-v2.example.yml --workers 18 --results results/m12-distilled-matrix-v2.db
bfsim calibration experiments/m12-distilled-matrix-v2.example.yml --results results/m12-distilled-matrix-v2.db
```
验收口径：加权 |Δ| 第一门槛 ≤13.2%（启发式 M6 基线）；对照 9.7% 如实落账

- [ ] **Step 3: 机制计数复核**：task 061 D4 的 sqlite 查询对 v2 库重跑
  （全局 use_ability 次/局 ≥5；沙奈朵对局精神拥抱 ≥0.8/局；局均回合回落）

- [ ] **Step 4: 确定性**：distilled 镜像同种子两跑逐局全等（events_hash，
  小样 10 局 det-check，task 060 同口径）

- [ ] **Step 5: 全量回归 + ruff + 落账**：STATUS.md / tasks/task 062.md 归档
  tasks/done/；M12 终判呈报（锚 1 分 kind / 锚 2 复量 / 锚 3 墙钟实测 +
  task 061 根因闭环证据链）→ **用户拍板点**

---

## Self-Review 记录

- 规格覆盖：D-062-1（Task 1）/ D-062-2（Task 1 Step 3 + Task 5）/
  D-062-3（Task 1）/ D-062-4（Task 2/3/4）/ D-062-5（Task 6 同快照同超参）✓
- 验收标准 5 条 → Task 6 Step 2/3、Task 7 Step 2/3/4/5 ✓
- 类型一致：`build_card_vocab` / `policy_action_names(card_vocab)` /
  `POLICY_STATE_NAMES` / `PolicyModel.card_vocab` / `row_to_sample(..., card_vocab)`
  / `train_policy(..., state_names, action_names, card_vocab)` 全文一致 ✓
- 冻结面纪律：FEATURE_NAMES / ACTION_FEATURE_NAMES 常量不动（M11 资产锚）✓
