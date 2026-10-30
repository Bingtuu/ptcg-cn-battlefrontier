# -*- coding: utf-8 -*-
"""
task 091 Q3 frequency gate (read-only) — mechanism L.

分母: dig 触及负 52 局（touch_loss_seeds）。权威 52。≠52 则停。

机会 L（一局至多计 1）: 同种子引擎重放 A 侧（player 0 / 沙奈朵侧），
存在一次决策同时满足：
  1. 己方奖杯剩余 < 对手奖杯剩余（领先）
  2. 合法 attack 中 `_lethal_attack` 为无（本步无斩杀可取）
  3. 代理实际打出 `use_ability`，且该特性经 `_is_cycle_discard_draw` 判定为交易类循环
  → L 会节流 = would-change

Pass: ≥15/52。不改 heuristic.py。
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"C:\Vibe Project\Pokebattle")
DB = ROOT / "results" / "t086-gard-zoro.db"
SUM = ROOT / "results" / "t088-posttouch-dig-summary.json"
OUT_MD = ROOT / "docs" / "digs" / "2026-10-30-task-091-q3-frequency.md"
OUT_JSON = ROOT / "results" / "t091-q3-frequency.json"
EXP_YAML = ROOT / "experiments" / "t078-gard-zoro.example.yml"
DENOM_EXPECTED = 52
THRESHOLD = 15


@dataclass
class ProbeState:
    opportunity: bool = False
    examples: list = field(default_factory=list)
    # diagnostics (not in 15)
    cycle_ability_plays: int = 0
    leading_decisions: int = 0
    leading_no_lethal_decisions: int = 0
    any_use_ability: int = 0
    leading_cycle_but_lethal: int = 0  # leading + cycle but lethal available


class ProbeHeuristic:
    """包装 HeuristicAgent：只读探测 A 侧，不改决策。"""

    def __init__(self, inner, probe: ProbeState, player_is_a: bool):
        self.inner = inner
        self.probe = probe
        self.player_is_a = player_is_a
        self.params = inner.params
        self.card_effects = inner.card_effects

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def observe(self, view, legal_actions):
        action = self.inner.observe(view, legal_actions)
        if not self.player_is_a:
            return action
        self._maybe_count(view, legal_actions, action)
        return action

    def _is_cycle_action(self, view, action) -> bool:
        from battlefrontier.agent.heuristic import _is_cycle_discard_draw, _mon_by_iid

        if action.kind != "use_ability" or action.iid is None:
            return False
        holder = _mon_by_iid(view, action.iid)
        if holder is None:
            return False
        effect = self.inner._manual_effect(holder.current.card)
        if effect is None:
            return False
        return _is_cycle_discard_draw(effect)

    def _maybe_count(self, view, legal_actions, action):
        by_kind: dict = {}
        for a in legal_actions:
            by_kind.setdefault(a.kind, []).append(a)

        leading = view.own.prizes_count < view.opponent.prizes_count
        if leading:
            self.probe.leading_decisions += 1

        attack_acts = by_kind.get("attack") or []
        lethal = self.inner._lethal_attack(view, attack_acts) if attack_acts else None
        no_lethal = lethal is None
        if leading and no_lethal:
            self.probe.leading_no_lethal_decisions += 1

        if action.kind == "use_ability":
            self.probe.any_use_ability += 1

        is_cycle = self._is_cycle_action(view, action)
        if is_cycle:
            self.probe.cycle_ability_plays += 1

        if leading and is_cycle and not no_lethal:
            self.probe.leading_cycle_but_lethal += 1

        # L would-change: leading + no lethal + actually fired cycle ability
        if leading and no_lethal and is_cycle:
            if not self.probe.opportunity:
                self.probe.opportunity = True
                holder_name = None
                try:
                    from battlefrontier.agent.heuristic import _mon_by_iid
                    holder = _mon_by_iid(view, action.iid)
                    holder_name = holder.current.card.name if holder else None
                except Exception:
                    holder_name = None
                self.probe.examples.append({
                    "own_prizes": view.own.prizes_count,
                    "opp_prizes": view.opponent.prizes_count,
                    "ability_iid": action.iid,
                    "holder": holder_name,
                    "played_kind": action.kind,
                })


def main():
    from battlefrontier.runner.experiment import (
        load_experiment,
        prepare_experiment,
        load_db_path,
        build_agents,
    )
    from battlefrontier.runner.play import play_game

    t0 = time.time()
    summary = json.loads(SUM.read_text(encoding="utf-8"))
    touch_loss = list(summary["touch_loss_seeds"])
    print(json.dumps({
        "touch_loss": len(touch_loss),
        "expected": DENOM_EXPECTED,
    }, ensure_ascii=False))

    db = sqlite3.connect(str(DB))
    eid = db.execute("SELECT id FROM experiments").fetchone()[0]
    code = db.execute(
        "SELECT code_version FROM experiments WHERE id=?", (eid,)
    ).fetchone()[0]
    db.close()

    if len(touch_loss) != DENOM_EXPECTED:
        OUT_JSON.write_text(
            json.dumps({
                "stop": True,
                "denom": len(touch_loss),
                "expected": DENOM_EXPECTED,
                "seeds": touch_loss,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        OUT_MD.write_text(
            f"# task 091 Q3 频数门（只读）\n\n"
            f"> 2026-10-30 Diupi-Yun · `{DB}` · `{code}` · **不改** heuristic\n\n"
            f"## 停\n\n分母 **{len(touch_loss)}** ≠ 权威 **{DENOM_EXPECTED}**。"
            f"种子已写入 `results/t091-q3-frequency.json`。不改门槛、不改启发式。\n",
            encoding="utf-8",
        )
        print("STOP denom mismatch")
        sys.exit(2)

    defn = load_experiment(EXP_YAML)
    prepared = prepare_experiment(defn, load_db_path())
    print(
        "prepared decks",
        prepared.deck_a_id,
        prepared.deck_b_id,
        "warnings",
        len(prepared.warnings),
    )

    results = []
    for i, seed in enumerate(touch_loss):
        probe = ProbeState()
        agents = build_agents(defn, seed, prepared.card_effects)
        agents = [
            ProbeHeuristic(agents[0], probe, player_is_a=True),
            ProbeHeuristic(agents[1], ProbeState(), player_is_a=False),
        ]
        play_game(
            prepared.deck_a,
            prepared.deck_b,
            seed=seed,
            card_effects=prepared.card_effects,
            agents=agents,
        )
        results.append({
            "seed": seed,
            "opportunity": probe.opportunity,
            "examples": probe.examples,
            "cycle_ability_plays": probe.cycle_ability_plays,
            "leading_decisions": probe.leading_decisions,
            "leading_no_lethal_decisions": probe.leading_no_lethal_decisions,
            "any_use_ability": probe.any_use_ability,
            "leading_cycle_but_lethal": probe.leading_cycle_but_lethal,
        })
        if (i + 1) % 5 == 0 or i == 0:
            print(
                f"  replayed {i+1}/{len(touch_loss)} "
                f"opp_so_far={sum(1 for r in results if r['opportunity'])}"
            )

    num_opp = sum(1 for r in results if r["opportunity"])
    games_with_cycle = sum(1 for r in results if r["cycle_ability_plays"] > 0)
    games_leading = sum(1 for r in results if r["leading_decisions"] > 0)
    games_leading_no_lethal = sum(
        1 for r in results if r["leading_no_lethal_decisions"] > 0
    )
    games_ability = sum(1 for r in results if r["any_use_ability"] > 0)
    games_cycle_but_lethal = sum(
        1 for r in results if r["leading_cycle_but_lethal"] > 0
    )
    passed = num_opp >= THRESHOLD

    out = {
        "db": str(DB),
        "code_version_db": code,
        "method": "same-seed engine replay (ProbeHeuristic on A; no heuristic change)",
        "denominator_def": "touch_loss_seeds from dig (权威 52)",
        "denominator": len(touch_loss),
        "opportunity_numerator": num_opp,
        "pass_threshold": THRESHOLD,
        "pass": passed,
        "opp_seeds": [r["seed"] for r in results if r["opportunity"]],
        "examples": [ex for r in results for ex in r["examples"]][:30],
        "diag_games_with_cycle_ability": games_with_cycle,
        "diag_games_with_leading_decision": games_leading,
        "diag_games_leading_no_lethal": games_leading_no_lethal,
        "diag_games_any_use_ability": games_ability,
        "diag_games_leading_cycle_but_lethal": games_cycle_but_lethal,
        "denom_seeds": touch_loss,
        "elapsed_s": round(time.time() - t0, 1),
        "all": results,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    md = []
    md.append("# task 091 Q3 频数门（只读）\n")
    md.append(
        f"> 2026-10-30 Diupi-Yun · `{DB}` · db `{code}` · "
        f"**同种子引擎重放** · **不改** heuristic\n"
    )
    md.append("## 定义\n\n" + (__doc__ or "") + "\n")
    md.append("## 结果（门禁口径 = A 侧领先 × 无斩杀 × 发出循环特性）\n")
    md.append("| 项 | 值 |")
    md.append("|---|---|")
    md.append(f"| 分母（touch_loss = 权威） | **{len(touch_loss)}** |")
    md.append(f"| 机会局 would-change | **{num_opp}/{len(touch_loss)}** |")
    md.append(f"| 有 use_ability 的局 | {games_ability} |")
    md.append(f"| 有循环特性发出的局 | {games_with_cycle} |")
    md.append(f"| 曾处于领先决策的局 | {games_leading} |")
    md.append(f"| 曾领先且无斩杀决策的局 | {games_leading_no_lethal} |")
    md.append(f"| 门槛 | ≥{THRESHOLD}/52 |")
    md.append(f"| **判定** | {'**PASS**' if passed else '**FAIL / 收口**'} |")
    md.append("\n机会种子：" + (", ".join(map(str, out["opp_seeds"])) or "（无）") + "\n")
    md.append("\n### would-change 例\n")
    for ex in out["examples"][:15]:
        md.append(
            f"- prizes A{ex['own_prizes']}/B{ex['opp_prizes']} "
            f"holder={ex['holder']} ability_iid={ex['ability_iid']}"
        )
    md.append("\n## 诊断（非门禁，不算进 15）\n")
    md.append(
        f"- 领先且发出循环、但当时有斩杀可取（L 不节流，因有 lethal）："
        f"**{games_cycle_but_lethal}/52**\n"
    )
    md.append(
        "\n说明：门禁只计「领先 + 无斩杀 + 实际发出循环特性」。"
        "L 实现后这些决策会被节流（would-change）。\n"
    )
    md.append(
        f"\n## 方法\n\n同种子 `play_game` 重放（实验 `{EXP_YAML.name}`，"
        f"启发式默认参数，含 086 `prize_race_gate`）。"
        f"ProbeHeuristic 只读探测 A 侧（player 0），决策不变。"
        f"耗时 {out['elapsed_s']}s。\n"
    )
    md.append(
        "\n## 未做\n\n改 heuristic、写测试、开 TDD、跑 100 局、宣称 30.4%。"
        "M/N 诊断未另计（Q2 锁定只 L）。\n"
    )
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    summary_print = {k: out[k] for k in out if k != "all"}
    print(json.dumps(summary_print, ensure_ascii=False, indent=2))
    print("GATE", "PASS" if passed else "FAIL", f"{num_opp}/{len(touch_loss)}")


if __name__ == "__main__":
    main()