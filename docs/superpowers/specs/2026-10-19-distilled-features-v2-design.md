# 蒸馏特征 v2 设计：卡身份 + 弃牌构成（task 062）

- 日期：2026-10-19；状态：已批准（用户）
- 上游：task 060（M12 三锚实测，锚 2 ❌ 16.7%）→ task 061 根因诊断
  （`.kimi-code/m12-task061-diag-report.md`）；PRD 三期 §3.2 M12
- 一句话：锚 2 失败根因 = 学生特征零卡面身份/零弃牌构成导致 use_ability
  类决策特征不可分（一致率 0.009%）；本设计在不新采集数据的前提下补特征、
  升资产 v2、重训复测。

## D-062-1 特征扩展独立于 M11 清单（不动 FEATURE_NAMES / ACTION_FEATURE_NAMES）

M11 资产 eval-linear-v1 装载时逐一键序校验 FEATURE_NAMES（model.py:60），
bf-distilled-policy-v1 同构钉死双清单（policy_model.py:69-74）。扩展共享清单
会砸既有资产装载 → v2 特征**独立成册**：

- 新模块 `agent/policy_features.py`：
  - `POLICY_STATE_FEATURES` = FEATURE_NAMES（30）+ 弃牌构成 6 维：
    own/opp ×（discard_count / discard_energy_count / discard_pokemon_count）。
    弃牌堆为公开区域（双方可见），守信息纪律
  - `POLICY_ACTION_FEATURES` = ACTION_FEATURE_NAMES（26）+ 卡身份 one-hot
    112 维（键名 `card_<名>`，词表序 = 字典序钉死）
- 输入维度 = 36 + 138 = 174；hidden 64 不变

## D-062-2 卡身份词表 = 卡池 v1 group_key 全集

- 词表构建：卡池 v1 九套代表卡组 60 张 group_key 去重排序（实测 112 个，
  2026-10-19 经 SDK 实测）；训练侧从 `config/target-pool.v1.yml` + db 构建，
  **钉进资产 meta（card_vocab 字段）**，装载逐一校验全等
- 词表外卡名 = 显式报错不猜（学习线锚定卡池 v1，D3-5；池变更须重训新资产）
- 身份粒度 = group_key（卡名级）：同名多文本严格拆分（火恐龙等）在策略
  学习层面无区分必要，合并为一维

## D-062-3 行动→卡名解析口径（可见视图反查，信息纪律）

- `use_ability` / `play_trainer` / `evolve` / `attach_tool` 等带 iid 的行动：
  iid → 可见视图反查（己方手牌 / 双方场上含进化栈与附着 /
  pending_choice 选择池）
- `attack` / `retreat`（无 iid）：身份 = 己方战斗场卡
- `choose`：choices 多 iid → multi-hot（选中卡名各置 1）
- 解析失败（iid 不在可见区）= 112 维全零（如实表达「身份不可见」，
  非报错——对手手牌相关行动合法地不可见）
- 解析纯函数零引擎调用，与 action_features 同纪律

## D-062-4 资产 format 升 bf-distilled-policy-v2，v1 保留可装载

- `learn/policy_model.py`：POLICY_FORMAT_V2 = "bf-distilled-policy-v2"；
  资产增 card_vocab / state_feature_names / action_feature_names 按 v2 清单
  校验；`load_policy_model` 按 format 字段分派 v1/v2 装载路径（v1 资产
  models/policy-m12-v1.json 为 M12 锚 1 复算锚，须保持可读）
- v2 资产的 PolicyModel 增 card_vocab 字段（v1 为 None）
- 训练侧 `learn/policy_data.py` / `learn/train_policy.py`：特征维度从词表
  推导（去 56 硬编码）；meta 增 feature_version="v2" + card_vocab 锚
- 推理侧 `agent/distilled.py`：按模型 feature_version 分派特征化
  （v1 = 旧 56 维路径原样保留；v2 = policy_features 路径）

## D-062-5 训练零新采集

同一 task 057 试点快照（171219 点 / 1005 局）、同超参（100 epochs /
lr 1e-3 / hidden 64 / split_seed 20261018）、同按局 80/20 划分重训。
产物 models/policy-m12-v2.json 进版本控制（D3-4）。

## 验收标准（task 062）

1. **分 kind 一致率**（锚 1 工具链重放，全 16 类分母）：use_ability
   0.009% → **≥18%**（全类均值 36.5% 的一半；达不到 = 特征假设证伪，
   终止回呈报）；attack 类价值损失均值收敛（task 061 D2 口径复跑）
2. **matrix 复测**（distilled×distilled，种子 700000 起 500 局/对）：
   第一门槛加权 |Δ| ≤ 13.2%（不劣于启发式 M6 基线）；对照 9.7%（M10
   口径）如实落账；全局特性使用率 ≥5 次/局（教师口径 ~11）
3. **确定性**：训练 double-run 逐字节全等；distilled 镜像同种子两跑
   逐局全等（events_hash）
4. **回归**：全量 pytest 绿 + ruff 零告警；M11 资产装载/推理路径零变化
   （eval-linear-v1 与 policy-m12-v1 装载测试原样全绿）
5. **落账**：STATUS.md / tasks/task 062.md / 本设计决议若修订同步

## 工作包

- WP1 特征层 + 词表构建（policy_features.py，TDD）
- WP2 资产 v2 + 训练/推理接入（policy_model / policy_data / train_policy /
  distilled，TDD）
- WP3 重训 + 分 kind 一致率复测（跑批，~13min 训练 + 一致率重放）
- WP4 matrix 复测 + 锚 2 复量 + M12 终判呈报（跑批 ~17min + 报告）

## 已知近似与边界

- eval-linear-v1 价值损失口径噪声大（MSE 0.206，训练分布 = 启发式自对局），
  仅作聚合形态参考，不作硬门槛
- 卡身份只解「哪张卡」，不解「该卡此时该做什么」的完整语义——若 WP3 后
  use_ability 拉起但锚 2 仍不达 9.7%，后续杠杆 = 10⁴ 采集（信号已修前提
  下才立项）/ 软标签（须补采带 visits 快照）/ 目标卡身份扩展
- 目标卡（target_iid）身份 v2 不做（YAGNI；ablation 显示需要再加）
