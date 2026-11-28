# 备赛全流程实战演练（task 163，2026-11-27）

> 新场数据（合格赛事 19→20，窗推进至 11-22）下，由主会话自主完成一次完整备赛：
> 数据就绪 → 场快照 → field-pick 选卡 → prep 成对跑批 → mod-check 判读 → 证据包。
> 本文 = README「备赛流程」节的移植源。所有数字可原样复算（命令 + 种子域 + 证据包 hash 全留档）。

## 0. 前提与纪律

- 模拟胜率 = **自对局结果，不构成真实胜率预测**（claims register 守则 1）；
  field-pick / prep 报告全部自带限定语头注。
- 备赛口径钉死启发式 agent（`agents: heuristic`）；改表采纳走 mod-check 门，
  不凭单场感觉。
- 种子域纪律：每次 prep 选与全部历史不重叠的 `seed_start` 区间
  （`grep -rhoE "seed_start: [0-9]+" experiments/ | sort -u` 查重）。

## 1. 数据就绪检查

```bash
bfsim field-snap --probe --snap results/field-snap-2026-11-21.json
```

探针（task 162 起）按**合格口径**报上游最新赛事：未加权/组队/资格赛不触发
误报。本日状态：`stale — 上游最新合格赛事 2026-11-22 已超出快照窗终点
2026-11-15`（exit=3）→ 场窗可推进。

上游直查对账（合格口径 = master + 非组队 + 非 qual + static_weight 非空）：
11-01..11-22 共 **20 场**合格（旧窗 19 + 11-22 新增 1）；11-21/22 另有 12 场
已结束未加权（上游加权管道滞后，Pokearena 侧事项，不阻塞）。

## 2. 场快照刷新

```bash
bfsim field-snap --from 2026-11-01 --to 2026-11-22 --out results/field-snap-2026-11-27.json
```

产物 meta 自含签名：`sig = {window, n_qualified: 20, data_version, content_sha256}`——
`n_qualified` 与上游直查逐位一致（验收点）。快照落 `results/`，不进版本控制。

## 3. field-pick 选卡

```bash
bfsim field-pick --field results/field-snap-2026-11-27.json \
  --pool config/target-pool.v2.yml \
  --matrix-snap results/matchup-snap-2026-11-22.json
```

池版本不变（v2.x 11 套）→ 矩阵快照复用，零对局。新场排序（蒙特卡洛 n=1000）：

| 卡组 | 期望胜率 | 登顶率 | 真实格贡献 |
|---|---:|---:|---:|
| Dragapult（多龙巴鲁托） | **63.8%** | **100%** | 53% |
| Gardevoir（沙奈朵） | 59.2% | 0% | 0% |
| Dragapult Dusknoir | 55.0% | 0% | 41% |
| N's Zoroark | 54.0% | 0% | 59% |
| 其余 7 套 | ≤53.5% | 0% | — |

（工具同时告警：field 窗与 intl matchup 窗错位 46 天 >28——排序结论强度下调一档。）

### 选卡决策（主会话拍板，理由成文）

**首选 = 多龙巴鲁托（mik_moe:677868，base-only）**：
- field-pick 期望胜率第一（63.8%）且登顶率 100%；
- 三期场刷新（11-15 / 11-21 / 11-27）连续第一（61.4%→64.1%→63.8%），排序稳健；
- 真实格贡献 53%（矩阵近半权重有国际真实对局参照）；
- 无预验证改表资产 → 走 task 161 的 base-only 批次协议。

**备选 = 沙奈朵（mik_moe:711854 + task 141 两刀改表，base+mod 成对）**：
- field-pick 稳定第二（三期 56.4%→59.4%→59.2%）；
- 唯一带预验证改表资产的候选（task 152：+5.5pp 池内条件期望、10/10 格全正
  全显著、零回吐）——新场头下须复核改表是否维持成立；
- 已知风险：对首选多龙巴鲁托大劣（task 152 读数 38.0%），若比赛中多龙
  占比继续走高须重新权衡。

**落选说明**：Dragapult Dusknoir / N's Zoroark 期望胜率差第一档 4pp+；
其余 7 套 ≤53.5% 不构成竞争。

## 4. prep 全链路

两个 prep 定义（`experiments/t163-prep-dragapult.yml` /
`t163-prep-gardevoir.yml`），要点：

- `field` 窗与第 2 节一致（11-01..11-22）；`matrix_snap` 复用；
- `games_per_cell: 2000`（2,000 局口径 CI 半宽 ≈ ±3pp，task 117 定标）；
- 种子域不重叠：dragapult 750000..751999；gardevoir 760000..761999
  （base/mod 两臂同域 = 成对 CRN）；
- `family_size: 1`（单一预注册改表，非扫描族——task 159 诚实口径）；
- strict 覆盖率默认开（task 157：无文档非基本能量卡拒绝开跑）。

```bash
bfsim prep experiments/t163-prep-dragapult.yml --workers 16   # 10 对手 × 2000 = 20,000 局
bfsim prep experiments/t163-prep-gardevoir.yml --workers 16   # 10 对手 × 2000 × 2 臂 = 40,000 局
```

（跑批 2026-11-27 23:59 启动，27 分钟完成：dragapult 10 实验 20,000 局 +
gardevoir 20 实验 40,000 局，**60,000 局零失败零平局**；装载告警各 3 条
vanilla 异文本印刷（合法不视为错误）；strict 覆盖过闸。）

## 5. mod-check 判读 + 证据包

prep 自动登记 `batch.json`（paired/base 模式 + 预期种子全集 + 版本），
判读结果落 `verdict.json/csv` + 统一报告 `report.md`。

### 首选：多龙巴鲁托 base-only（`results/prep-prep-t163-dragapult/`）

池内条件期望 **77.9%**；逐对手 70.3%（vs 沙奈朵）～ 90.0%（vs 赛富豪
土龙节节），无一下 70%。base-only 模式不出判读门（无改表臂），
读数用途 = 名单级确认 field-pick 排序。

### 备选：沙奈朵 base+mod 成对（`results/prep-prep-t163-gardevoir/`）

| 对手 | 基线 | 改表 | Δpp | 配对 p |
|---|---:|---:|---:|---:|
| 多龙巴鲁托 黑夜魔灵 | 54.9% | 58.9% | +3.9 | 0.0085 |
| 电电虫Box | 66.5% | 70.3% | +3.8 | 0.0091 |
| 玛俐的长毛巨魔 雪妖女 | 49.1% | 53.6% | +4.5 | 0.0010 |
| 赛富豪 | 73.4% | 77.2% | +3.8 | 0.0037 |
| 赛富豪 土龙节节 | 84.0% | 85.4% | +1.4 | 0.2328 |
| 猛雷鼓 厄诡椪 | 65.0% | 68.8% | +3.8 | 0.0069 |
| 喷火龙 大比鸟 | 49.5% | 54.6% | +5.2 | 0.0005 |
| N的索罗亚克 | 59.8% | 64.6% | +4.9 | 0.0012 |
| 多龙巴鲁托 | 32.2% | 36.0% | +3.8 | 0.0072 |
| 火伊布 猫头夜鹰 | 72.5% | 77.5% | +4.9 | 0.0002 |

- 池内条件期望：基线 60.3% / 改表 64.4%（**Δ +4.0pp**）
- 赛制换算：Bo3 65.3%→70.9%；6 轮 ≥4 胜出线 55.1%→63.4%（简化口径）
- **门（α=0.05，family_size=1）：全正 ✅ / 全显著 ❌ / 零回吐 ✅ / COMPLETE ✅**

**判读**：新场头下改表 10/10 格全正、零回吐，方向与 task 152（11-15 场头）
一致；但全显著门未过——赛富豪土龙节节格 +1.4pp（p=0.2328）不显著
（该格基线已 84%，改表边际天然小）。结论 = **维持成立但强度降一档**
（11-15 场头 10/10 全显著 → 11-22 场头 9/10）；既有采纳不被推翻，
亦不构成本轮「新采纳」证据。对纯多龙 36.0% 仍大劣的风险读数不变。

**证据包核验**：两候选 inputs/ 全文件 sha256 重算 == manifest 登记
（prep.yml / decks.json / field-snap 副本 / mod 卡表副本 / matrix_snap 引用），
verdict meta 落 family_size + adopt_alpha + 批次 sha256。

## 6. 复算指引

复算三元组（verdict meta 回显）：实验定义 sha256=`0d1511149e1f…` /
代码版本 `c313d4f+dirty` / 数据版本 `2026-09-16 (user_version=14)`。
证据包目录（`results/prep-prep-t163-*/`）整体拷走即可凭 manifest 追溯
每个数字来源；结果库 `results/prep-prep-t163-*.db`（本机，gitignore）。

复跑命令序列 = 本文 §1–§4 五条命令 + 两个 prep yml（进版本控制）。
种子域：750000..751999（dragapult）/ 760000..761999（gardevoir 两臂 CRN）。

## 7. 遗留

- 上游 11-21/22 余 12 场已结束未加权（Pokearena 侧）；加权落地后探针
  backfill 判出 → 重跑 §1–§4 即得新场头判读。
- 沙奈朵 vs 纯多龙大劣（36.0%）：若比赛环境多龙占比继续走高，首选
  多龙巴鲁托、放弃沙奈朵备选的权重应上调——归牌手拍板。
- 败局解剖 / 换卡搜索（报告「下一步」节命令）本轮未触发：首选无改表
  需求信号，备选改表已预验证。
