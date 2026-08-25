# task 001 · 项目脚手架与工程基建

- 状态：完成（2026-08-25）
- 关联：PRD §12（技术栈与工程约定）；里程碑 M1 前置

## 目标

建立可开发、可测试的项目骨架，与 db 项目工程约定对齐。

## 验收标准（测试清单）

- [x] `pyproject.toml` 可 `pip install -e .`，包名 `battlefrontier`，`requires-python >= 3.12`
- [x] 依赖声明：pydantic v2、pytest、ruff；`ptcgdb` SDK 以可编辑/本地路径依赖接入（不自带卡牌数据）
- [x] 包结构落位：`battlefrontier/`（engine / dsl / agent / runner / report 五子包占位，各含 `__init__.py`）
- [x] `.gitignore`：`.venv/`、`data/`（结果库不入库）、`__pycache__/`、`dist/`
- [x] 冒烟测试通过：`PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m pytest -q` 全绿（至少 1 个占位测试）
- [x] `.venv/Scripts/ruff.exe check .` 零告警

## 实现要点

- CLI 入口预留 `bfsim`（本 task 只注册 entry point，子命令后续 task 加）
- 不引入 Alembic / SQLModel 等 db 项目明确不用的技术

## 结果与遗留

- **结果**：venv（Python 3.14.6）建好；`pip install -e .` 成功；4 个冒烟测试全绿（版本 / 五子包可导入 / CLI 入口返回 0 / ptcgdb SDK 可导入）；ruff 零告警；`bfsim` 可执行。
- **TDD 记录**：先写 `tests/test_scaffold.py`，RED（`ModuleNotFoundError: No module named 'battlefrontier'`）→ 脚手架 GREEN；ptcgdb 接入同样先 RED（`No module named 'ptcgdb'`）后 GREEN。
- **遗留**：无。`ptcgdb` SDK 已以可编辑路径 `C:/Vibe Project/Pokearena` 接入（venv 内 `pip install -e`，`pyproject.toml` 的 `db` extra 记录该路径）。
