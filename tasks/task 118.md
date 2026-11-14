# task 118 · decklist 印刷级行 + README 备赛三场景食谱

- 状态：进行中
- 关联：task 115（swap in_id 同款缺口的 file 导入路径）/ task 073（name-count 入口）；TDD 小扩，存量行为不变
- 日期：2026-11-14 立项（使用便利性拍板）

## 目标

消除 file 卡表导入的最后一个保真缺口：txt 卡名解析 = `search_cards(limit=1)` 首命中印刷、不可指定，同名多印刷时可能落 DSL 未覆盖印刷按 vanilla 结算（task 113 在 swap 路径实证的同款问题）。补印刷级行语法 + README 备赛三场景食谱（导入卡表 / 假想敌 / 换卡估算）。

## 设计（先定案，TDD 红测照此写）

- **语法**：`N 卡名 [card_id]` 可选印刷后缀（方括号），如 `2 巢穴球 [CSVH1C-043]`；无后缀 = 现状（卡名首命中）。方括号内为 db card_id。
- **校验（不猜，与 task 115 同纪律）**：`[card_id]` 未命中 → ValueError；解析卡名 ≠ 行内卡名 → ValueError。
- **改动面**：`parse_decklist`（返回 (count, name, card_id|None)）+ `_load_decklist_file`（印刷给定时走 `db.get_card`）。其余零改动。

## 验收标准（测试清单）

1. 红测 → 绿：`[card_id]` 命中覆盖印刷（装载无 vanilla 告警、卡内容按指定印刷）。
2. 红测 → 绿：未命中 card_id → ValueError；卡名不一致 → ValueError。
3. 存量测试零改动全绿（无后缀路径行为不变）；全量 pytest 绿 + ruff 零告警。
4. README 新增「备赛三场景食谱」小节：导入卡表 / 假想敌卡表 / 指定替换估算胜率影响，各给可直接复制的命令与 txt/yaml 片段（与 task 113/115/117 实证行为一致）。
5. 实证冒烟：用印刷级 txt 跑 1 局装载验证（ `bfsim run` name-count 模板改印刷行，局数=1）。

## 实现要点

- 只动 decklist 解析/装载 + 测试 + README；不动 CLI 结构、不动 swap/matrix 路径。
- `parse_decklist` 签名变化（三元组）——检查全部调用方同步。

## 结果与遗留

- **TDD（验收 1–3 ✅）**：红测 7 失败 → 实现 `parse_decklist` 三元组（`[card_id]` 后缀解析 + 括号残留报错）+ `_load_decklist_file` 印刷分支（未命中/卡名不一致显式报错，不猜）→ 局部 40 passed + ruff 零告警。存量 2 处解包随签名机械更新（test_ingress_templates，非迁就实现）。
- **食谱（验收 4 ✅）**：README 新增 §5.5「备赛三场景」：导入卡表（含 `[card_id]` 语法）/ 假想敌 / 换卡估算，附功效口径（2,000 局 ±3pp）与读数纪律（阴性对照、1-of 探针化）。
- **冒烟（验收 5 ✅）**：印刷级 txt（`60 基本超能量 [CSVE1C-PSY]`）装载解析正常；对局失败原因为测试牌组无基础宝可梦（与印刷路径无关，符合预期）。
- **遗留**：全量回归 + 提交。
