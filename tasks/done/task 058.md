# task 058 · M12 WP2 状态-行动特征化 + torch 训练管线

- 状态：完成
- 关联：task 056 拍板定案（torch dev-only + numpy runtime + 训练非复算面）；
  task 057 教师快照产线（bf-m11-snapshot-v1，冒烟 984 点/5 局全类别）；
  接入面摸底 `.kimi-code/m12-decision-prep.md` §4
- 开发口径：大批次实现走「子代理 TDD + 主会话独立复验」惯例；
  开发期用冒烟数据（results/m12-teacher-smoke/）+ 合成小样本，不等试点全量

## 设计（D-M12-x，本任务书定稿）

- **样本**：快照行（完整 GameState + 结构化 chosen Action）→ 重建
  VisibleGameState（行动方视角，守信息纪律）→ (state, action) 对
- **特征**：状态 30 维复用 `agent/features.py` FEATURE_NAMES（零改动）；
  行动侧特征 `ACTION_FEATURE_NAMES`（新增）：kind 15 类 one-hot +
  数值标量（damage/amount/count/目标关系标志，从 Action 结构化字段抽取，
  引擎零硬编码——不解析 DSL 语义，只读 Action 对象字段）
- **模型**：MLP 打分机（state ⊕ action → 标量 logit），合法行动掩码
  softmax + 教师硬标签交叉熵（试点硬标签；软标签缺口见 task 057 遗留）
- **资产**：新 format `bf-distilled-policy-v1` JSON（权重嵌套列表 + 特征
  词表 + meta：种子/数据版本/码版本/训练超参；D3-4 进版本控制）；
  训练非复算面（torch 随机源不锁），资产落盘即锁定
- **CLI**：`bfsim train-policy --data <快照目录> --out <模型JSON>`
  [--epochs --lr --hidden --split-seed ...]（缺省全钉死写 meta）
- **分层**：torch import 仅限 `learn/train_policy.py`（runtime 路径零
  torch，task 056 防回流基准）；推理前向（numpy）属 WP3

## 验收标准

1. TDD：特征抽取（state⊕action 向量维度/键序锁定）、快照→样本转换
   （信息纪律：只用行动方 visible view）、模型资产 save/load 往返、
   CLI 端到端小样本（冒烟数据子集可训出资产）——全部 pytest 绿
2. 资产 format 强校验（format id / 词表键序 / 维度），装载失败显式报错
3. 训练冒烟：冒烟数据（984 点）训 1 epoch 不炸，holdout argmax 准确率
   落 meta（试点数据小，只看管线通，不看指标）
4. runtime 路径零 torch import 复核（grep）+ 全量 pytest 绿 + ruff 零告警
5. STATUS.md 落账 + 归档

## 结果与遗留

- **状态：完成（2026-10-18）**
- **新增**：`agent/action_features.py`（ACTION_KINDS 16 类词表 + ACTION_FEATURE_NAMES
  26 维 + `action_features` 纯函数）/ `learn/policy_data.py`（快照→样本转换 +
  目录载入，torch-free）/ `learn/policy_model.py`（bf-distilled-policy-v1 资产
  读写 + 强校验）/ `learn/train_policy.py`（torch MLP 训练器，唯一 torch import
  位）/ CLI `bfsim train-policy`；`learn/__init__.py` 增 policy_model 导出
- **设计决策**：
  - **D-M12-1** kind 词表 16 类（core.py 15 种 + chooser「choose」——任务书草稿
    「15 类」系漏计 choose；choice 阶段占冒烟样本 278/984 = 28%，排除会丢掉该
    阶段全部监督信号），字母序钉死，词表外 kind 显式报错
  - **D-M12-2** 行动数值标量口径：引擎 Action 结构化字段仅 kind/iid/target_iid/
    bench_index/attack_index/choices，无 damage/amount/count（招式伤害在卡面
    AttackDef，属 DSL 语义，引擎零硬编码纪律不入行动特征）→ 标量 = attack_index /
    has_iid / has_target_iid / has_bench_index / bench_index / n_choices +
    目标关系标志 4 个（target_iid 经行动方 visible view 可见在场区解析，
    含进化栈/附着能量/道具 iid；不在可见区全 0）
  - **D-M12-3** MLP 结构缺省：输入 56（状态 30 + 行动 26）→ 隐藏 64 + ReLU →
    标量 logit；合法行动掩码 softmax + 教师硬标签 NLL；全批量 Adam；缺省
    epochs 100 / lr 1e-3 / hidden 64 / split_seed 20261018 全钉死写 meta
  - **D-M12-4** 资产 bf-distilled-policy-v1：权重嵌套列表 w1/b1/w2/b2 + 双特征
    词表（键序钉死校验）+ hidden + meta（含 torch_version / holdout argmax
    准确率）；训练非复算面（D3-4，torch.manual_seed(split_seed) 仅锚定初始化），
    落盘位级确定（sort_keys/indent=2/UTF-8）
- **验收**：新增测试 23（test_policy_features.py 11 + test_policy_train.py 12）
  全绿；全量 pytest 1275 绿 + ruff 零告警；torch import grep 复核仅
  `learn/train_policy.py`；冒烟训练（results/m12-teacher-smoke 984 点/5 局，
  1 epoch hidden 16）产物 `results/policy-smoke-task058.json`——
  holdout argmax 准确率 0.5455（220 点）/ 训练 0.4202 / 损失 1.797 落 meta
- **主会话独立复验（2026-10-18）**：复跑 ruff 零告警 + torch/numpy grep 实证
  （torch 仅 learn/train_policy.py，battlefrontier/ 全域零 numpy）+ 冻结面
  git diff（tracked 仅 STATUS.md / cli.py +67 纯增量 / learn/__init__.py，
  engine/agent(runner/report 既有文件零改动）+ 亲跑冒烟训练 CLI（2 epochs
  hidden 16，holdout 0.5455 与子代理自报一致）+ pyproject 分层实证（runtime
  numpy≥2 / dev torch）。两处任务书勘误呈报（D-M12-1 词表 16 类 / D-M12-2
  Action 无伤害字段）**裁定成立**：choose 占样本 28% 不可丢；引擎零硬编码
  纪律优先于任务书示例
- **遗留**：WP3 numpy 推理前向 + Agent type `distilled` 注册（接入面摸底
  `.kimi-code/m12-decision-prep.md` §4）；软标签/分布蒸馏缺口（Consideration
  分布未入快照行）仍挂 task 057 遗留；正式 10³ 试点数据训练待 task 057 产线收口；
  **性能风险**：全批量逐样本构图（_score_batch Python 循环 + 单 loss 汇总
  backward），试点 ~20 万点 × 100 epochs 可能小时级——task 060 正式训练前
  需评估（mini-batch 化 / 减 epochs / 子采样，改则动训练器 TDD 先行）
  **→ 已解决**（2026-10-18，task 060 前置：向量化重写，见 task 060 任务书
  范围 0；实测 0.216s/epoch@984 点，提速 ~200×，等价性测试含梯度
  allclose(atol 1e-5)）
