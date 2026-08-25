# task 001 · 项目脚手架与工程基建

- 状态：未开始
- 关联：PRD §12（技术栈与工程约定）；里程碑 M1 前置

## 目标

建立可开发、可测试的项目骨架，与 db 项目工程约定对齐。

## 验收标准（测试清单）

- [ ] `pyproject.toml` 可 `pip install -e .`，包名 `battlefrontier`，`requires-python >= 3.12`
- [ ] 依赖声明：pydantic v2、pytest、ruff；`ptcgdb` SDK 以可编辑/本地路径依赖接入（不自带卡牌数据）
- [ ] 包结构落位：`battlefrontier/`（engine / dsl / agent / runner / report 五子包占位，各含 `__init__.py`）
- [ ] `.gitignore`：`.venv/`、`data/`（结果库不入库）、`__pycache__/`、`dist/`
- [ ] 冒烟测试通过：`PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m pytest -q` 全绿（至少 1 个占位测试）
- [ ] `.venv/Scripts/ruff.exe check .` 零告警

## 实现要点

- CLI 入口预留 `bfsim`（本 task 只注册 entry point，子命令后续 task 加）
- 不引入 Alembic / SQLModel 等 db 项目明确不用的技术

## 结果与遗留

（完工后填写）
