# -*- coding: utf-8 -*-
"""Apply Q3 result into STATUS.md + task 089.md after gate run. Fill PASS/FAIL from JSON."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"C:\Vibe Project\Pokebattle")
j = json.loads((ROOT / "results" / "t089-q3-frequency.json").read_text(encoding="utf-8"))
num = j["opportunity_numerator"]
den = j["denominator"]
passed = j["pass"]
verdict = "PASS" if passed else "FAIL"
seeds = j.get("opp_seeds") or []
seed_str = ", ".join(map(str, seeds[:12])) + ("…" if len(seeds) > 12 else "")

st = ROOT / "STATUS.md"
s = st.read_text(encoding="utf-8")
if passed:
    focus = (
        f"**当前焦点 = task 089 已拍板且 Q3 **PASS {num}/{den}**（2026-10-30 Asia/Shanghai）→ 可开 TDD（本步未开）。**"
        f"机会种子例：{seed_str or '（见 dig）'}。"
        "硬门其余（100 局 B≥34/失败 0；电电虫否决；18000 非完成）待 TDD 后。"
        "不改 `heuristic.py` 直到另开 TDD PR。证据库 `results/t086-gard-zoro.db`。"
    )
    log = f"""### 2026-10-30 task 089：Q3 频数门 PASS → 可开 TDD（未开）

- **口径**：dig 39 局触及负且首触已落后；首触前换上 × 机制 P（would-change）。
- **结果**：**{num}/{den} PASS**（阈值 ≥15/39）。机会种子：{seed_str or '见 dig'}。
- **产物**：`docs/digs/2026-10-30-task-089-q3-frequency.md`；只读脚本 `experiments/t089_q3_frequency.py`。
- **决定**：按硬门可写测试；**本步仍不**改 `heuristic.py`、不开 TDD（Owner 未授权本步实现）。

"""
else:
    focus = (
        f"**当前焦点 = task 089 已拍板且 Q3 **FAIL {num}/{den}**（2026-10-30 Asia/Shanghai）→ **收口**；不开 TDD、不改 `heuristic.py`。**"
        f"机会种子：{seed_str or '（无）'}。"
        "按硬门重设计（不放宽 15/39）。禁 081/`prize_pressure_gate`。不宣称 30.4%。"
        "证据库 `results/t086-gard-zoro.db`（`fc25648`，A69/B31）。"
    )
    log = f"""### 2026-10-30 task 089：Q3 频数门 FAIL → 收口

- **口径**：dig 39 局触及负且首触已落后；首触前换上 × 机制 P（would-change）。
- **结果**：**{num}/{den} FAIL**（阈值 ≥15/39）。机会种子：{seed_str or '（无）'}。
- **产物**：`docs/digs/2026-10-30-task-089-q3-frequency.md`；只读脚本 `experiments/t089_q3_frequency.py`。
- **决定**：按 Owner 硬门收口；**不**开 TDD；**不**改 `heuristic.py`。下一刀重设计。

"""

s2, n = re.subn(
    r"\*\*当前焦点 = task 089.*?(?=\n\n\*\*上一刀|\n\n\*\*task 084|\n\n## )",
    focus + "\n\n",
    s,
    count=1,
    flags=re.S,
)
print("focus n", n)
if f"Q3 频数门 {verdict}" not in s2:
    s2 = s2.replace("## 工作记录\n", "## 工作记录\n\n" + log)
st.write_text(s2, encoding="utf-8")

task = ROOT / "tasks" / "task 089.md"
t = task.read_text(encoding="utf-8")
if passed:
    t = t.replace(
        "- [ ] Q3 计数（Diupi-Yun）：39 局中换上机会 ≥15 才继续；低于则收口；拍板后跑，写回后才允许 TDD",
        f"- [x] Q3 计数（Diupi-Yun）：**{num}/{den} PASS**；见 `docs/digs/2026-10-30-task-089-q3-frequency.md`；本步仍不开 TDD",
    )
else:
    t = t.replace(
        "- [ ] Q3 计数（Diupi-Yun）：39 局中换上机会 ≥15 才继续；低于则收口；拍板后跑，写回后才允许 TDD",
        f"- [x] Q3 计数（Diupi-Yun）：**{num}/{den} FAIL**；见 `docs/digs/2026-10-30-task-089-q3-frequency.md`；**不进入 TDD / 按硬门收口**",
    )
old_res = "拍板已写回。Q3 计数见 `docs/digs/2026-10-30-task-089-q3-frequency.md`（若已生成）。TDD 未开。未改 `heuristic.py`。"
if passed:
    new_res = f"拍板已写回。Q3 计数 **{num}/{den} PASS**（`docs/digs/2026-10-30-task-089-q3-frequency.md`）。按硬门可开 TDD；本步未开。未改 `heuristic.py`。"
else:
    new_res = f"拍板已写回。Q3 计数 **{num}/{den} FAIL**（`docs/digs/2026-10-30-task-089-q3-frequency.md`）。按硬门 **收口 089**：不写测试、不改 `heuristic.py`、不开 TDD。"
t = t.replace(old_res, new_res)
task.write_text(t, encoding="utf-8")
print("STATUS+task updated", verdict, f"{num}/{den}")
