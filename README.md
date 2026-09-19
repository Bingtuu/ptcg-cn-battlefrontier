# BattleFrontier（对战开拓区）

> AI 宝可梦卡牌（PTCG 简中环境）对战模拟与卡组强度测试引擎

**BattleFrontier** 让两个 AI 选手在完整的简中 PTCG 规则下自动对战，通过大规模模拟对局回答三类问题：

- **强度**：卡组 A 对抗卡组 B 的胜率是多少？（附置信区间与先后手拆分）
- **策略**：某卡组在某对阵下的最优打法是什么？（从对局决策数据中聚合产出）
- **敏感性**：换掉卡组里的几张卡，胜率变化显著吗？

## 快速开始

### 1. 安装

要求 Python 3.12+：

```bash
git clone <本仓库地址>
cd Pokebattle
pip install -e .
```

安装后获得命令行工具 `bfsim`。

### 2. 准备卡牌数据

本项目不自带卡牌数据，需要搭配数据项目 [ptcg-cn-db](https://github.com/Bingtuu/ptcg-cn-db) 使用：

```bash
# 安装数据层 SDK（指向你本机的 ptcg-cn-db 检出）
pip install -e "C:/path/to/ptcg-cn-db"

# 复制配置模板，填写本机的卡牌数据库路径
cp config/battlefrontier.example.yml config/battlefrontier.local.yml
```

`battlefrontier.local.yml` 已被 gitignore，支持 SQLite 直读或 JSONL 导出目录两种数据源。

### 3. 跑第一个实验

实验用一个 YAML 文件定义——对阵双方、AI 类型、局数、随机种子：

```yaml
# my-first-match.yml
name: my-first-match
games: 100            # 对局数
seed_start: 1000      # 随机种子起点（同种子可完整复现每一局）
decks:
  a: {source: db, deck_id: "mik_moe:644634"}   # 数据层中的赛事卡组 id
  b: {source: db, deck_id: "mik_moe:650353"}
agents:
  a: {type: heuristic}   # 启发式 AI（内置）
  b: {type: random}      # 随机 AI（内置，常用作对照）
```

运行（`--workers` 开启多进程并行，结果与串行逐局一致）：

```bash
bfsim run my-first-match.yml --workers 4
```

```
实验 #1「my-first-match」完成：100 局 A胜 65 / B胜 35 / 平 0 / 失败 0（结果库 results/battlefrontier-results.db）
数据版本 2026-07-16 (user_version=13)；种子区间 1000..1099
```

更多示例见 `experiments/` 目录。

### 4. 查看报告

```bash
bfsim report 1              # 1 = 实验 id（run 完成时会打印）
bfsim report 1 --decisions  # 追加「关键决策聚合」分节：每张卡的选择分布与对应胜率
```

```
实验 #1「my-first-match」胜率报告
meta：种子区间 1000..1099 / 代码 d084e13 / 数据 2026-07-16 / 局数 100
完成 100 局（决定局 100，平 0，失败 0），平均回合 10.4
A 胜 65 / B 胜 35 —— A 胜率 65.0%（Wilson 95% CI 55.3%..73.6%，分母=决定局）
先攻时 A 胜率 70.7%（CI 57.7%..81.5%）
后攻时 A 胜率 61.0%（CI 44.5%..75.4%）
```

### 5. 换卡敏感性分析

在实验定义里加 `variants`，一次跑出 baseline 与若干变体（同种子区间配对可比）：

```yaml
variants:
  # 对照组：A 方 2 反击捕捉器 → 2 巢穴球（卡组保持 60 张）
  - name: swap-catcher-to-nestball
    swaps:
      - {side: a, out: 反击捕捉器, out_count: 2, in: 巢穴球, in_count: 2}
```

```bash
bfsim run with-variants.yml --workers 4        # 自动依次跑 baseline + 各变体
bfsim sensitivity 1 2                          # baseline vs 变体并排对比
```

报告给出每个变体的胜率变化（ΔWR）、95% 置信区间与显著性检验（两比例 z 检验）。

### 6. 校验卡牌定义

每张有效果的卡牌由 `cards/` 下一个 YAML 文件定义（引擎不认识任何具体卡牌，全部行为由数据驱动）。新增或修改卡牌定义后校验：

```bash
bfsim dsl-check cards/博士的研究.yml            # 结构与词法校验
bfsim dsl-check cards/*.yml --db <卡牌数据库>   # 追加校验：卡牌存在、文本一致、赛制合法
```

## 设计理念

- **卡牌效果即数据**：每张卡做什么全部写在 YAML 里，由解释器执行；规则引擎只负责回合流程、伤害、胜负等骨架，对卡牌内容零硬编码。
- **完全可复现**：所有随机（洗牌、掷币、抽牌）走单一随机源——同一个实验定义 + 同一段种子，重跑结果逐局一致，并行与串行一致。
- **AI 接口统一**：`observe(可见状态, 合法行动) -> 行动`。合法行动由引擎枚举，AI 永远不会违规操作；启发式、蒙特卡洛树搜索（规划中）、强化学习（远期）可互换、可混编对照。
- **结果独立存放**：模拟结果写入独立的 SQLite 结果库，卡牌数据库始终只读。

## 项目状态

🚧 开发中。已可用：完整规则引擎、卡牌效果定义库（68 份定义，覆盖当前竞技环境 9 套主流卡组）、启发式与随机 AI、批量实验运行器、胜率/决策/敏感性报告。进行中：继续扩充卡牌覆盖。详细进展见 [STATUS.md](STATUS.md)，设计文档见 [PRD](docs/superpowers/specs/2026-08-25-battlefrontier-prd-design.md)，规则依据见 [rules-manual](docs/rules-manual.md)（简中官方规则整理）。

## ⚖️ 合规声明

本项目与 Nintendo、The Pokémon Company、宝可梦（上海）**无任何隶属或背书关系**。卡面文本与卡牌数据版权归宝可梦（上海）/ The Pokémon Company 所有；本项目不采集、不存储、不分发卡图与卡牌数据，仅限本地研究与工具自用。

## 📄 License

代码与文档基于 MIT License 发布（卡牌数据版权见上方声明，不在许可范围内）。
