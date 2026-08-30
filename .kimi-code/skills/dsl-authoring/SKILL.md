---
name: dsl-authoring
description: Use when 编写或修改 cards/ 下的卡牌 DSL 定义（YAML 效果文件）、为缺口卡写单卡测试、或需要按 LLM 辅助编写管线（PRD §5.5）的三道验收闸流程交付新卡时。
---

# DSL 卡牌编写（LLM 辅助管线 harness）

本 skill 是 PRD §5.5 的固定 harness：输入装配 → YAML 草稿 → 三道验收闸 → 质量数据记录。
执行者通常是会话内 agent（可分子代理并行，每子代理一卡）。**违反字面流程即违反设计意图。**

## 输入装配（固定顺序，每卡必做）

1. **db 取卡**（只读）：`ptcgdb.sdk.open_db`（路径读 `config/battlefrontier.local.yml` 的
   `db.sqlite_path`）→ `search_cards(name=卡名)` → `get_card(card_id)`，
   取 `text_raw` 原文 + `effect_tags` + `sentences` 句级标签（**排除 `rule_reference` 句**，task 009 约定）。
   运行环境：Windows，Python 用 `.venv/Scripts/python.exe -X utf8`，`PYTHONIOENCODING=utf-8`。
2. **读契约**：`battlefrontier/dsl/schema.py`（字段结构）+ `battlefrontier/dsl/vocabularies.yml`（开放词表）。
3. **读规范**：本文件「编写规范」节。
4. **找样例**：同机制既有卡作参考（检索类→`cards/高级球.yml`；特性→`cards/沙奈朵ex.yml`；招式效果→`cards/吉雉鸡ex.yml`）。

## 输出契约（每卡两件，缺一不可）

- `cards/<name_group>.yml`：文件名 = name_group；**注释格式约定**（与库内既有卡一致）：
  文件头 `# 卡名（card_id，卡种）` + `# text_raw 原文：「…」`（整段引用，不改写、不做
  术语规范化——原文保真红线）；effect 上方注释写实现注记（如 observe 锚点说明）。
  `card_ids` 填 db 实际 id。
- 单卡单元测试：写入 `tests/test_dsl_cards.py`（按批次分节注释），测试**必须从 `cards/` 真实文件装载**（`load_card_doc`），用 `tests/helpers.py` 的 stub 引擎驱动效果全链路（含 chooser 选择）。**测试函数名含中文卡名**（`test_<卡名>_...`）——闸 2 用 `pytest -k <卡名>` 过滤，拼音命名会匹配不上（task 024 自验踩过）。

## 样例速查（同机制参考）

- 检索入手：`cards/高级球.yml`；检索直放备战区：`cards/巢穴球.yml`
- 特性：`cards/沙奈朵ex.yml`；招式效果：`cards/吉雉鸡ex.yml`；复制招式：`cards/梦幻ex.yml`

## 词表与扩展路径（重要，闸 1 有盲点）

闸 1（dsl-check）只校验六段词表：actions / selectors / counters / destinations / triggers /
limits。**filters、observe、condition、args 键不在词表文件里，闸 1 不校验**——它们注册在
代码里：filters → `dsl/chooser.py::_match_one`（含 `evolves_from:<名>` 参数化前缀模式）、
condition → 解释器 `_CONDITIONS` 注册表。自造过滤器词能过闸 1、到运行时才 DslError，
**filters 正确性靠闸 2 单卡测试兜底**。

缺词时的扩展路径：
- 六段词表内的词 → 加 `dsl/vocabularies.yml` 并在交付说明里写明（零代码）；
- filters / condition / 新 args 键 → **是代码改动**：停止 DSL 编写，上报主会话/用户立项
  （在 `docs/m5-coverage-plan.md` 标 `blocked:<缺什么>`），由引擎侧注册后解锁。
  禁止在 YAML 里自造未注册词。

## 三道验收闸（全过才入库）

1. `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m battlefrontier.cli dsl-check cards/<卡>.yml` → rc=0。
2. `pytest tests/test_dsl_cards.py -k <卡名>` 全绿。
3. **人工核销**：提交用户确认。用户确认前日志 `gate3=false`，卡不算入库完成。

## 质量数据（每卡必记，PRD §10.3 决策依据）

每卡向 `cards/authoring-log.jsonl` 追加一行（JSONL，不落卡牌文本）：

```json
{"date":"2026-08-30","card":"卡名","card_id":"CSVxC-000","author":"llm","batch":1,
 "gate1":true,"gate2":true,"gate3":false,"first_pass":true,"human_edit_lines":null,"notes":""}
```

- `first_pass` = 闸 1+2 首次提交即过 且 人工零修改。
- `human_edit_lines`：核销时以 `git diff --numstat` 辅助估；未核销填 null。
- 草稿没过闸重写过的，`first_pass=false` 并在 notes 记失败原因关键词。

## 硬性纪律（红线）

- **不猜**：缺词按「词表与扩展路径」节走；现有原语表达不了的效果 → 在
  `docs/m5-coverage-plan.md` 把该卡标 `blocked:<缺什么>`，**不降级乱写**。
- **级别初判不可尽信**：m5-coverage-plan 的 A/B/C 是 effect_tags 归并初判。装配阶段
  必须逐句核对 text_raw 与 filters/condition 注册表（`_match_one` / `_CONDITIONS`），
  不一致以上述不猜纪律处理。
- 检索类关键决策声明 `observe:` 锚点（决策聚合报告依赖，task 022 口径）。
- 术语只用简中官方用词（昏厥/奖赏卡/备战区）；规则语义先查 ptcg-rules skill 指引的文档。
- 注释只引原文与实现注记；机制取舍写进测试或覆盖计划文档，不写进卡片注释。

## Red Flags — 停止并重来

- 凭记忆写效果，没从 db 取 `text_raw`
- 测试里内联 YAML 副本而不是装载真实文件
- 词表缺词就在 YAML 里自造
- 跳过闸 1 直接跑 pytest
- 未报用户就降级改写效果语义
