# task 038：code review 修复包——缓存契约 + 静默失败族

来源：全库 code review（2026-10 月，6 组并行 + 主会话复核）报告。本 task 打包修复
「立即修」+「静默失败族」共 6 项（报告编号 #1 #5 #6 #7 #9 #10）。设计级项
（MCTS 信息泄漏 #2/#3、DSL 确定性对拍 #11）与 flip_heads_count 穿透（#4）不在本 task。

## 设计决议

- **D-038-1（#1 legal_actions 缓存契约）**：`legal_actions` 两条返回路径都返回
  `list(...)` 副本，缓存槽内部 list 永不外露。调用方变异返回值不影响引擎。
- **D-038-2（#5 args 键名白名单）**：每个原语在 primitives.py 注册处声明接受的
  args 键集合（如 `PRIMITIVE_ARGS: dict[str, frozenset[str]]`），loader 装载期
  校验未知键 → DslError 响亮报错（对齐「未知词不猜」纪律）。白名单必须覆盖
  现有 101 个卡文件全部用法（验收：`bfsim dsl-check cards/*.yml --db` 全过）。
- **D-038-3（#6 Effect.attack 校验）**：两级——①loader 级：`attack` 非 None
  时 `trigger` 必须为 `on_attack`，否则装载报错；②闸 1 --db 级（cli.py
  dsl-check）：on_attack 效果的 attack 名必须在 card_id 对应卡面招式名集合内，
  打错即报错（不再静默退化为白板）。
- **D-038-4（#7 中断语义 + 报告告警）**：`execute_experiment` 兜底改
  `except BaseException` → `finish_experiment(status="aborted")` 后 re-raise
  （KeyboardInterrupt 不再永挂 running）。报告命令（report/sensitivity/
  calibration）对 status != 完成态的实验在输出中打印告警行——**告警不排除
  数据**（查看部分结果是合法用途，静默才是 bug）。
- **D-038-5（#9 sensitivity meta）**：`format_sensitivity` 双侧回显（baseline +
  每个 variant 的种子区间/代码版本/数据版本/局数）；版本或种子区间不一致时
  输出告警行（不硬错——跨版本对比是合法用途，但不许静默）。
- **D-038-6（#10 calibration 重跑去重）**：组内同名子实验 >1 套时
  `calibration_report` 抛 ValueError 并列出重复名（「不猜」口径，与缺子实验
  同级；项目惯例重跑用新库文件，不破坏现有工作流）。

## 验收标准

1. 契约测试：调用方对 `legal_actions` 返回值 `pop`/排序后，同状态再枚举结果
   完整且引擎行为不变。
2. args 白名单：拼错键（如 `upto`）的 DSL 装载即 DslError；
   `dsl-check cards/*.yml --db` 101 文件全过（白名单无漏键）。
3. attack 校验：非 on_attack 带 attack → 装载报错；on_attack 招式名打错 →
   `dsl-check --db` 报错。
4. 中断：注入 KeyboardInterrupt → 实验 status=aborted 落库；报告命令对
   aborted/running 实验输出告警行（有测试）。
5. sensitivity：双侧 meta 回显；版本/种子不一致告警（有测试）。
6. calibration：同名重复子实验 → ValueError（有测试）。
7. 全量 pytest 绿 + ruff 零告警。
