# -*- coding: utf-8 -*-
"""
task 090 Q3 frequency gate (read-only) — mechanism S.

分母: 088 的「触及负且首触未转化」——与 experiments/t088_q3_frequency.py 同口径
  从 touch_loss_seeds 重算；权威 40。≠40 则停。

机会 S（一局至多计 1）: 同种子引擎重放，存在一次决策同时满足：
  1. 本局第一下暗夜攻击事件之前
  2. 该次决策按今天 _decide_main 优先级会走到支援者档，且合法支援者含
     DSL {action: switch, selector: opponent_bench}
  3. 前瞻 via=="copy" 且 best_damage>0 且 can_ko 为假
  4. 按今天 pokemon_score（平手 iid 小）这张 switch 的目标剩余 HP ≤ best_damage
     （备战不计弱点/抗性）
  5. 代理实际没有打这张 switch（would-change）

Pass: ≥15/40。不改 heuristic.py。
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
OUT_MD = ROOT / "docs" / "digs" / "2026-10-30-task-090-q3-frequency.md"
OUT_JSON = ROOT / "results" / "t090-q3-frequency.json"
EXP_YAML = ROOT / "experiments" / "t078-gard-zoro.example.yml"
ACE = "暗夜王牌"
DENOM_EXPECTED = 40
THRESHOLD = 15


def _is_switch_opp_bench(agent, card) -> bool:
    """支援者/训练家 DSL 是否含 switch + opponent_bench（读文档，不写卡名）。"""
    from battlefrontier.agent.dsl_estimate import doc_for
    from battlefrontier.dsl.interpreter import flatten_steps

    if agent.card_effects is None:
        return False
    doc = doc_for(agent.card_effects, card)
    if doc is None:
        return False
    for effect in doc.effects:
        if effect.trigger != "on_play":
            continue
        for _phase, node in flatten_steps(effect):
            if getattr(node, "action", None) != "switch":
                continue
            sel = getattr(node, "selector", None) or (node.args or {}).get("selector")
            if sel == "opponent_bench":
                return True
    return False


def _score_winner_bench(agent, view):
    """今天 _pick_choose 在 opponent_bench 池上的赢家（无挂起帧时的 pokemon_score 路径）。"""
    from battlefrontier.agent.heuristic import pokemon_score

    bench = list(view.opponent.bench or ())
    if not bench:
        return None
    # mirror: min(acts, key=lambda a: (-score(a), a.choices)) with choices=(iid,)
    return min(
        bench,
        key=lambda m: (-pokemon_score(m, agent.params), (m.current.iid,)),
    )


def _remaining(agent, view, mon) -> int | None:
    return agent._ko_remaining(view, mon)


def _would_reach_supporters(agent, view, by_kind: dict) -> list:
    """复刻 _decide_main 优先级，返回走到支援者档时的支援者 action 列表；否则 []."""
    from battlefrontier.agent.heuristic import pokemon_score
    from battlefrontier.agent.dsl_estimate import card_has_draw

    hand = {c.iid: c for c in view.own.hand}
    deck_low = agent._deck_low(view)
    if agent.params.use_abilities and (acts := by_kind.get("use_ability")):
        picked = agent._pick_ability(view, acts)
        if picked is not None:
            return []
    if by_kind.get("evolve"):
        return []
    if acts := by_kind.get("attach_energy"):
        picked = agent._pick_energy_attach(view, acts)
        if picked is not None:
            return []
    if acts := by_kind.get("attack"):
        lethal = agent._lethal_attack(view, acts)
        if lethal is not None:
            return []
    if agent.params.attach_tools and by_kind.get("attach_tool"):
        return []
    if agent.params.retreat_when_powerless and (acts := by_kind.get("retreat")):
        picked = agent._pick_retreat(view, acts)
        if picked is not None:
            return []
    if agent.params.play_items:
        items = [
            a for a in by_kind.get("play_trainer", [])
            if hand[a.iid].card.trainer_subtype == "物品"
        ]
        if deck_low:
            items = [
                a for a in items
                if not card_has_draw(hand[a.iid].card, agent.card_effects)
            ]
        if items:
            return []
    if not agent.params.play_supporters:
        return []
    supporters = [
        a for a in by_kind.get("play_trainer", [])
        if hand[a.iid].card.trainer_subtype == "支援者"
    ]
    if deck_low:
        supporters = [
            a for a in supporters
            if not card_has_draw(hand[a.iid].card, agent.card_effects)
        ]
    return supporters


@dataclass
class ProbeState:
    first_ace_done: bool = False
    # gate
    opportunity: bool = False
    examples: list = field(default_factory=list)
    # diagnostics (not in 15)
    score_miss: bool = False  # bench has KO-able but score winner isn\'t
    score_miss_examples: list = field(default_factory=list)
    post_opportunity: bool = False
    supporter_decisions_before: int = 0
    switch_legal_before: int = 0


class ProbeHeuristic:
    """包装 HeuristicAgent：只读探测，不改决策。"""

    def __init__(self, inner, probe: ProbeState, player_is_b: bool):
        self.inner = inner
        self.probe = probe
        self.player_is_b = player_is_b
        # proxy attrs HeuristicAgent needs externally
        self.params = inner.params
        self.card_effects = inner.card_effects

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def observe(self, view, legal_actions):
        action = self.inner.observe(view, legal_actions)
        if not self.player_is_b:
            return action

        by_kind: dict = {}
        for a in legal_actions:
            by_kind.setdefault(a.kind, []).append(a)

        # detect first ace on the action we are about to play
        is_ace = False
        if action.kind == "attack":
            # attack name from active\'s attack index
            atk_name = None
            try:
                active = view.own.active
                if active is not None and action.attack_index is not None:
                    attacks = active.current.card.attacks
                    # may include tool attacks; use inner helper if available
                    atks, _ = self.inner._attack_sources(view)
                    if 0 <= action.attack_index < len(atks):
                        atk_name = atks[action.attack_index].name
            except Exception:
                atk_name = None
            if atk_name == ACE:
                is_ace = True

        before = not self.probe.first_ace_done
        self._maybe_count(view, by_kind, action, before=before)

        if is_ace and not self.probe.first_ace_done:
            self.probe.first_ace_done = True
        return action

    def _maybe_count(self, view, by_kind, action, *, before: bool):
        from battlefrontier.agent.heuristic import pokemon_score

        supporters = _would_reach_supporters(self.inner, view, by_kind)
        if not supporters:
            return
        if before:
            self.probe.supporter_decisions_before += 1

        hand = {c.iid: c for c in view.own.hand}
        switch_acts = [
            a for a in supporters
            if _is_switch_opp_bench(self.inner, hand[a.iid].card)
        ]
        if not switch_acts:
            return
        if before:
            self.probe.switch_legal_before += 1

        look = self.inner._ko_prize_lookahead(view)
        dmg = look.best_damage or 0
        cond_look = look.via == "copy" and dmg > 0 and not look.can_ko

        bench = list(view.opponent.bench or ())
        # diagnostic: any KO-able on bench vs score winner
        koable = []
        for m in bench:
            rem = _remaining(self.inner, view, m)
            if rem is not None and rem <= dmg and dmg > 0:
                koable.append(m)

        winner = _score_winner_bench(self.inner, view)
        winner_rem = _remaining(self.inner, view, winner) if winner else None
        score_is_ko = (
            winner is not None
            and winner_rem is not None
            and dmg > 0
            and winner_rem <= dmg
        )

        if cond_look and koable and winner is not None and not score_is_ko:
            if before and not self.probe.score_miss:
                self.probe.score_miss = True
                self.probe.score_miss_examples.append({
                    "dmg": dmg,
                    "winner": winner.current.card.name if winner else None,
                    "winner_rem": winner_rem,
                    "koable": [
                        (m.current.card.name, _remaining(self.inner, view, m))
                        for m in koable
                    ],
                })

        # S pick: among switch cards (min iid), first whose score-winner is KO-able
        s_pick = None
        if cond_look and score_is_ko:
            s_pick = min(switch_acts, key=lambda a: a.iid)

        if s_pick is None:
            return

        played = (
            action.kind == "play_trainer"
            and action.iid == s_pick.iid
        )
        would_change = not played
        ex = {
            "dmg": dmg,
            "via": look.via,
            "can_ko": look.can_ko,
            "winner": winner.current.card.name if winner else None,
            "winner_rem": winner_rem,
            "switch_iid": s_pick.iid,
            "switch_name": hand[s_pick.iid].card.name,
            "played_kind": action.kind,
            "played_iid": getattr(action, "iid", None),
            "would_change": would_change,
        }
        if before:
            if would_change and not self.probe.opportunity:
                self.probe.opportunity = True
                self.probe.examples.append(ex)
        else:
            if would_change and not self.probe.post_opportunity:
                self.probe.post_opportunity = True


def recompute_denom(db_path: Path, touch_loss: list[int]) -> list[int]:
    """与 088 同口径：触及负且首触未转化。"""
    db = sqlite3.connect(str(db_path))
    eid = db.execute("SELECT id FROM experiments").fetchone()[0]
    games = {
        s: (gid, w)
        for gid, s, w in db.execute(
            "SELECT id, seed, winner FROM games WHERE experiment_id=?", (eid,)
        )
    }
    out = []
    for seed in touch_loss:
        if seed not in games:
            continue
        gid, _ = games[seed]
        evs = [
            (seq, json.loads(ej))
            for seq, ej in db.execute(
                "SELECT seq, event_json FROM game_events WHERE game_id=? ORDER BY seq",
                (gid,),
            )
        ]
        first_i = None
        for i, (seq, e) in enumerate(evs):
            if (
                e.get("kind") == "attack"
                and e.get("player") == 1
                and (e.get("detail") or {}).get("attack") == ACE
            ):
                # also accept detail.name as attack name fallback
                first_i = i
                break
            det = e.get("detail") or {}
            if (
                e.get("kind") == "attack"
                and e.get("player") == 1
                and (det.get("attack") or det.get("name") or det.get("move")) == ACE
            ):
                first_i = i
                break
        if first_i is None:
            # try alternate: attack field at top
            for i, (seq, e) in enumerate(evs):
                if e.get("kind") != "attack" or e.get("player") != 1:
                    continue
                det = e.get("detail") or {}
                an = det.get("attack") or det.get("name") or det.get("move") or e.get("attack")
                if an == ACE:
                    first_i = i
                    break
        if first_i is None:
            continue
        converted = False
        for j in range(first_i + 1, len(evs)):
            e = evs[j][1]
            if e.get("kind") == "knockout" and e.get("player") == 0:
                converted = True
                break
            if e.get("kind") == "take_prize" and e.get("player") == 1:
                converted = True
                break
            if e.get("kind") == "end_turn" and e.get("player") == 1:
                break
            if e.get("kind") == "attack" and e.get("player") == 0:
                break
        if not converted:
            out.append(seed)
    db.close()
    return out


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
    touch_loss = summary["touch_loss_seeds"]
    denom_seeds = recompute_denom(DB, touch_loss)
    print(json.dumps({
        "touch_loss": len(touch_loss),
        "denom": len(denom_seeds),
        "expected": DENOM_EXPECTED,
    }, ensure_ascii=False))

    db = sqlite3.connect(str(DB))
    eid = db.execute("SELECT id FROM experiments").fetchone()[0]
    code = db.execute(
        "SELECT code_version FROM experiments WHERE id=?", (eid,)
    ).fetchone()[0]
    db.close()

    if len(denom_seeds) != DENOM_EXPECTED:
        OUT_JSON.write_text(
            json.dumps({
                "stop": True,
                "denom": len(denom_seeds),
                "expected": DENOM_EXPECTED,
                "seeds": denom_seeds,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        OUT_MD.write_text(
            f"# task 090 Q3 频数门（只读）\n\n"
            f"> 2026-10-30 Diupi-Yun · `{DB}` · `{code}` · **不改** heuristic\n\n"
            f"## 停\n\n重算分母 **{len(denom_seeds)}** ≠ 权威 **{DENOM_EXPECTED}**。"
            f"种子已写入 `results/t090-q3-frequency.json`。不改阈值、不改启发式。\n",
            encoding="utf-8",
        )
        print("STOP denom mismatch")
        sys.exit(2)

    defn = load_experiment(EXP_YAML)
    prepared = prepare_experiment(defn, load_db_path())
    print("prepared decks", prepared.deck_a_id, prepared.deck_b_id, "warnings", len(prepared.warnings))

    results = []
    for i, seed in enumerate(denom_seeds):
        probe = ProbeState()
        agents = build_agents(defn, seed, prepared.card_effects)
        # wrap both to keep types; only B probes
        agents = [
            ProbeHeuristic(agents[0], ProbeState(), player_is_b=False),
            ProbeHeuristic(agents[1], probe, player_is_b=True),
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
            "score_miss": probe.score_miss,
            "score_miss_examples": probe.score_miss_examples,
            "post_opportunity": probe.post_opportunity,
            "supporter_decisions_before": probe.supporter_decisions_before,
            "switch_legal_before": probe.switch_legal_before,
            "saw_first_ace": probe.first_ace_done,
        })
        if (i + 1) % 5 == 0 or i == 0:
            print(f"  replayed {i+1}/{len(denom_seeds)} opp_so_far={sum(1 for r in results if r['opportunity'])}")

    num_opp = sum(1 for r in results if r["opportunity"])
    num_score_miss = sum(1 for r in results if r["score_miss"])
    num_post = sum(1 for r in results if r["post_opportunity"])
    num_sup = sum(1 for r in results if r["supporter_decisions_before"] > 0)
    num_sw = sum(1 for r in results if r["switch_legal_before"] > 0)
    saw_ace = sum(1 for r in results if r["saw_first_ace"])
    passed = num_opp >= THRESHOLD

    out = {
        "db": str(DB),
        "code_version_db": code,
        "method": "same-seed engine replay (ProbeHeuristic; no heuristic change)",
        "denominator_def": "touch_loss & first-ace no KO/prize (088口径)",
        "denominator": len(denom_seeds),
        "opportunity_numerator": num_opp,
        "pass_threshold": THRESHOLD,
        "pass": passed,
        "opp_seeds": [r["seed"] for r in results if r["opportunity"]],
        "examples": [ex for r in results for ex in r["examples"]][:20],
        "diag_score_miss_n": num_score_miss,
        "diag_score_miss_seeds": [r["seed"] for r in results if r["score_miss"]][:20],
        "diag_posttouch_would_change_n": num_post,
        "diag_posttouch_seeds": [r["seed"] for r in results if r["post_opportunity"]][:20],
        "games_with_supporter_before": num_sup,
        "games_with_switch_legal_before": num_sw,
        "games_saw_first_ace_in_replay": saw_ace,
        "denom_seeds": denom_seeds,
        "elapsed_s": round(time.time() - t0, 1),
        "all": results,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    md = []
    md.append("# task 090 Q3 频数门（只读）\n")
    md.append(
        f"> 2026-10-30 Diupi-Yun · `{DB}` · db `{code}` · "
        f"**同种子引擎重放** · **不改** heuristic\n"
    )
    md.append("## 定义\n\n" + (__doc__ or "") + "\n")
    md.append("## 结果（门禁口径 = 首触前支援者 × 机制 S）\n")
    md.append("| 项 | 值 |")
    md.append("|---|---|")
    md.append(f"| 分母（重算 = 权威） | **{len(denom_seeds)}** |")
    md.append(f"| 机会局 would-change | **{num_opp}/{len(denom_seeds)}** |")
    md.append(f"| 首触前走到支援者的局 | {num_sup} |")
    md.append(f"| 首触前合法含 switch 支援者的局 | {num_sw} |")
    md.append(f"| 重放见到第一下暗夜的局 | {saw_ace} |")
    md.append(f"| 阈值 | ≥{THRESHOLD}/40 |")
    md.append(f"| **判定** | {'**PASS**' if passed else '**FAIL / 收口**'} |")
    md.append("\n机会种子：" + (", ".join(map(str, out["opp_seeds"])) or "（无）") + "\n")
    md.append("\n### would-change 例\n")
    for ex in out["examples"][:12]:
        md.append(
            f"- dmg={ex['dmg']} via={ex['via']} winner={ex['winner']}(rem={ex['winner_rem']}) "
            f"switch={ex['switch_name']}#{ex['switch_iid']} "
            f"played={ex['played_kind']}#{ex['played_iid']}"
        )
    md.append("\n## 诊断（非门禁，不算进 15）\n")
    md.append(
        f"- 备战有人剩余 HP ≤ dmg，但 pokemon_score 赢家不是那只：**{num_score_miss}/40** "
        f"种子 {out['diag_score_miss_seeds']}\n"
    )
    md.append(
        f"- 第一下**之后**仍满足 2–5 的 would-change：**{num_post}/40** "
        f"种子 {out['diag_posttouch_seeds']}\n"
    )
    md.append(
        "\n说明：门禁只计首触前；若诊断列远大于门禁列，实现窗口比「首触前」宽，"
        "TDD 前先改规格。\n"
    )
    md.append(
        f"\n## 方法\n\n同种子 `play_game` 重放（实验 `{EXP_YAML.name}`，"
        f"启发式默认参数，含 086 `prize_race_gate`）。"
        f"ProbeHeuristic 只读探测，决策仍是今天的 `min(iid)` 支援者。"
        f"耗时 {out['elapsed_s']}s。\n"
    )
    md.append(
        "\n## 未做\n\n改 heuristic、写测试、开 TDD、跑 100 局、宣称 30.4%。"
        "H/Y 诊断未另计（Q2 锁定只 S）。\n"
    )
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    summary_print = {k: out[k] for k in out if k != "all"}
    print(json.dumps(summary_print, ensure_ascii=False, indent=2))
    print("GATE", "PASS" if passed else "FAIL", f"{num_opp}/{len(denom_seeds)}")


if __name__ == "__main__":
    main()
