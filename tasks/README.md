# tasks/ — 任务工作循环

每个开发任务一个文档，命名 `task NNN.md`（NNN 三位递增，如 `task 001.md`）。完工后移入 `tasks/done/`。

## 流程（每个 task 必走）

1. **读设计文档**：先读 PRD（`docs/superpowers/specs/`）与 `STATUS.md`，确认任务边界与相关决策记录
2. **设计 TDD**：在 task 文档中写出验收标准与测试清单（先测试后实现）
3. **开发**：按 TDD 红→绿循环实现
4. **测试**：`pytest -q` 全绿 + `ruff check .` 通过
5. **收尾**：更新 `STATUS.md`（当前阶段 / 里程碑 / 工作记录），task 文档标注完成状态后归档 `tasks/done/`

## task 文档模板

```markdown
# task NNN · <标题>

- 状态：进行中 / 完成
- 关联：PRD 章节 / 里程碑 M?

## 目标
## 验收标准（测试清单）
## 实现要点
## 结果与遗留
```

提交信息前缀：`task(NNN):`（对齐 db 项目惯例）。
