# -*- coding: utf-8 -*-
"""
task 093 Q3 frequency gate (read-only) — mechanism R.

分母: results/t092-gard-zoro-500.db 触及负（有 B 侧暗夜王牌事件且 winner==0）。
权威 236；重算 ≠236 则停。

机会 R（一局至多计 1）: 同种子引擎重放 B 侧（player 1 / N索侧），
在本局第一下 copy_attack 攻击事件之前，存在一次决策同时满足：
  1. 落后：own.prizes_count > opponent.prizes_count
  2. 今天 _decide_main 正返回 attack；can_ko 为假；该招 DSL 是一层
     copy_attack + selector=own_bench_attack；有效伤害为 0
     （via=="copy" 用 best_damage，否则用印面表）
  3. 存在合法 place_bench 基础：临时看成无能量/无伤害在场宝可梦，
     matches_in_play(filters) 且 max(_copied_strike) > 0
  → R 会改打 place_bench = would-change

Pass: ≥15/236。不改 heuristic.py。
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
DB = ROOT / "results" / "t092-gard-zoro-500.db"
OUT_MD = ROOT / "docs" / "digs" / "2026-10-30-task-093-q3-frequency.md"
OUT_JSON = ROOT / "results" / "t093-q3-frequency.json"
EXP_YAML = ROOT / "experiments" / "t092-gard-zoro-500.yml"
ACE = "暗夜王牌"
DENOM_EXPECTED = 236
THRESHOLD = 15


def atk_name(det: dict) -> str | None:
    return det.get("attack") or det.get("name") or det.get("move")


def recount_touch_loss(db_path: Path) -> tuple[list[int], str]:
    """与 092 dig 同口径：触及（B 打出暗夜王牌）且 winner==0。"""
    db = sqlite3.connect(str(db_path))
    eid, code = db.execute(
        "SELECT id, code_version FROM experiments ORDER BY id"
    ).fetchone()
    games = list(
        db.execute(
            "SELECT id, seed, winner, is_draw, error FROM games WHERE experiment_id=?",
            (eid,),
        )
    )
    gids = [g[0] for g in games]
    by: dict[int, list] = {gid: [] for gid, *_ in games}
    CHUNK = 200
    for i in range(0, len(gids), CHUNK):
        chunk = gids[i : i + CHUNK]
        q = (
            f"SELECT game_id, seq, event_json FROM game_events "
            f"WHERE game_id IN ({','.join('?' * len(chunk))}) ORDER BY game_id, seq"
        )
        for gid, seq, ej in db.execute(q, chunk):
            by[gid].append((seq, json.loads(ej)))
    db.close()

    seeds: list[int] = []
    for gid, seed, winner, is_draw, err in games:
        if is_draw or err:
            continue
        evs = by.get(gid) or []
        touched = False
        for _seq, e in evs:
            if e.get("kind") != "attack" or e.get("player") != 1:
                continue
            if atk_name(e.get("detail") or {}) == ACE:
                touched = True
                break
        if touched and winner == 0:
            seeds.append(int(seed))
    seeds.sort()
    return seeds, code


@dataclass
class ProbeState:
    first_copy_done: bool = False
    opportunity: bool = False
    examples: list = field(default_factory=list)
    # per-game diagnostics (non-gate)
    saw_behind_fail: bool = False
    saw_damage_gt0: bool = False
    saw_no_basic: bool = False
    saw_filter_fail: bool = False
    saw_strike_0: bool = False
    copy_swing_before: int = 0
    behind_at_copy_swing: int = 0


class ProbeHeuristic:
    """包装 HeuristicAgent：只读探测 B 侧，不改决策。"""

    def __init__(self, inner, probe: ProbeState, player_is_b: bool):
        self.inner = inner
        self.probe = probe
        self.player_is_b = player_is_b
        self.params = inner.params
        self.card_effects = inner.card_effects

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def observe(self, view, legal_actions):
        action = self.inner.observe(view, legal_actions)
        if not self.player_is_b:
            return action
        before = not self.probe.first_copy_done
        is_copy = self._is_one_layer_copy_attack(view, action)
        if before:
            self._maybe_count(view, legal_actions, action)
        if is_copy and not self.probe.first_copy_done:
            self.probe.first_copy_done = True
        return action

    def _copy_node_for_index(self, view, index: int):
        """返回 (atk, node) 若该招是一层 own_bench_attack copy；否则 None。"""
        from battlefrontier.agent.dsl_estimate import doc_for, find_attack_effect
        from battlefrontier.dsl.interpreter import flatten_steps

        if self.card_effects is None:
            return None
        active = view.own.active
        if active is None:
            return None
        attacks, sources = self.inner._attack_sources(view)
        if not (0 <= index < len(attacks)):
            return None
        atk = attacks[index]
        doc = doc_for(self.card_effects, sources[index])
        if doc is None:
            return None
        effect = find_attack_effect(doc, atk.name)
        if effect is None:
            return None
        node = next(
            (
                step
                for _phase, step in flatten_steps(effect)
                if step.action == "copy_attack"
                and step.selector == "own_bench_attack"
            ),
            None,
        )
        if node is None:
            return None
        return atk, node

    def _is_one_layer_copy_attack(self, view, action) -> bool:
        if action.kind != "attack":
            return False
        return self._copy_node_for_index(view, action.attack_index) is not None

    def _effective_copy_zero(self, view, attack_index: int) -> tuple[bool, dict]:
        """该招是否一层 copy 且有效伤害为 0 且 can_ko 为假。

        返回 (ok, info)。info 含 via/damage/can_ko/is_copy。
        """
        from battlefrontier.engine.core import _energy_satisfied

        info = {
            "is_copy": False,
            "via": None,
            "damage": None,
            "can_ko": None,
            "attack_index": attack_index,
        }
        pair = self._copy_node_for_index(view, attack_index)
        if pair is None:
            return False, info
        info["is_copy"] = True
        atk, node = pair
        active = view.own.active
        if active is None or not _energy_satisfied(active.attached_energy, atk.cost):
            return False, info

        copied = self.inner._one_layer_copy(view, attack_index)
        table = self.inner._attack_table(view)
        if copied is not None:
            damage, ko = copied
            via = "copy"
        else:
            damage, lethal_ok = table[attack_index]
            via = "print"
            # print path KO: mirror lookahead
            opp = view.opponent.active
            rem = self.inner._ko_remaining(view, opp)
            ko = bool(
                lethal_ok
                and rem is not None
                and damage >= rem
            )
        info["via"] = via
        info["damage"] = damage
        info["can_ko"] = ko
        ok = (not ko) and (damage == 0)
        return ok, info

    def _qualifying_place_bench(self, view, legal_actions, node) -> tuple[str, list]:
        """返回 (status, picks)。

        status: opportunity | no_basic | filter_fail | strike_0
        picks: list of {iid,name,strike}
        """
        from battlefrontier.dsl.chooser import matches_in_play
        from battlefrontier.dsl.loader import DslError
        from battlefrontier.engine.state import InPlayPokemon

        place_acts = [a for a in legal_actions if a.kind == "place_bench"]
        if not place_acts:
            return "no_basic", []

        hand = {c.iid: c for c in view.own.hand}
        filters = tuple(node.filters or ())
        matched = []
        strike_pos = []
        for a in place_acts:
            card = hand.get(a.iid)
            if card is None:
                continue
            # 引擎已保证 stage==0 pokemon；再保险
            if getattr(card.card, "stage", None) != 0:
                continue
            temp = InPlayPokemon(stack=(card,))
            try:
                ok = matches_in_play(temp, filters)
            except DslError:
                continue
            if not ok:
                continue
            matched.append(a)
            best = 0
            for idx in range(len(card.card.attacks)):
                dmg, _ko = self.inner._copied_strike(view, temp, idx)
                if dmg > best:
                    best = dmg
            strike_pos.append(
                {
                    "iid": a.iid,
                    "name": card.card.name,
                    "strike": best,
                }
            )

        if not matched:
            return "filter_fail", []
        positive = [p for p in strike_pos if p["strike"] > 0]
        if not positive:
            return "strike_0", strike_pos
        # 多张：伤害高优先，平手 iid 小（与规格一致；本计数只问存在性）
        positive.sort(key=lambda p: (-p["strike"], p["iid"]))
        return "opportunity", positive

    def _maybe_count(self, view, legal_actions, action):
        # 只在「今天正返回 attack」的决策上评估 R 窗口
        if action.kind != "attack":
            return
        pair = self._copy_node_for_index(view, action.attack_index)
        if pair is None:
            return

        self.probe.copy_swing_before += 1
        _atk, node = pair
        behind = view.own.prizes_count > view.opponent.prizes_count
        zero_ok, info = self._effective_copy_zero(view, action.attack_index)

        if not behind:
            self.probe.saw_behind_fail = True
            return
        self.probe.behind_at_copy_swing += 1

        if info["damage"] is not None and info["damage"] > 0:
            self.probe.saw_damage_gt0 = True
            return
        if info.get("can_ko"):
            # can_ko 且 damage 可能为 0 的怪例也排除
            return
        if not zero_ok:
            # 非 copy 付清等
            return

        status, picks = self._qualifying_place_bench(view, legal_actions, node)
        if status == "no_basic":
            self.probe.saw_no_basic = True
            return
        if status == "filter_fail":
            self.probe.saw_filter_fail = True
            return
        if status == "strike_0":
            self.probe.saw_strike_0 = True
            return

        # opportunity
        if not self.probe.opportunity:
            self.probe.opportunity = True
            best = picks[0] if picks else None
            self.probe.examples.append(
                {
                    "own_prizes": view.own.prizes_count,
                    "opp_prizes": view.opponent.prizes_count,
                    "via": info["via"],
                    "damage": info["damage"],
                    "can_ko": info["can_ko"],
                    "attack_index": info["attack_index"],
                    "place_iid": best["iid"] if best else None,
                    "place_name": best["name"] if best else None,
                    "strike": best["strike"] if best else None,
                    "played_kind": action.kind,
                }
            )


def main():
    from battlefrontier.runner.experiment import (
        load_experiment,
        prepare_experiment,
        load_db_path,
        build_agents,
    )
    from battlefrontier.runner.play import play_game

    t0 = time.time()
    if not DB.exists():
        print(f"STOP missing DB {DB}")
        sys.exit(2)

    touch_loss, code = recount_touch_loss(DB)
    print(
        json.dumps(
            {
                "touch_loss": len(touch_loss),
                "expected": DENOM_EXPECTED,
                "code_version_db": code,
            },
            ensure_ascii=False,
        )
    )

    if len(touch_loss) != DENOM_EXPECTED:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(
            json.dumps(
                {
                    "stop": True,
                    "denom": len(touch_loss),
                    "expected": DENOM_EXPECTED,
                    "seeds": touch_loss,
                    "code_version_db": code,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text(
            f"# task 093 Q3 频数门（只读）\n\n"
            f"> 2026-10-30 Diupi-Yun · `{DB}` · `{code}` · **不改** heuristic\n\n"
            f"## 停\n\n分母 **{len(touch_loss)}** ≠ 权威 **{DENOM_EXPECTED}**。"
            f"种子已写入 `results/t093-q3-frequency.json`。不改门槛、不改启发式。\n",
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
        results.append(
            {
                "seed": seed,
                "opportunity": probe.opportunity,
                "examples": probe.examples,
                "first_copy_done": probe.first_copy_done,
                "copy_swing_before": probe.copy_swing_before,
                "behind_at_copy_swing": probe.behind_at_copy_swing,
                "saw_behind_fail": probe.saw_behind_fail,
                "saw_damage_gt0": probe.saw_damage_gt0,
                "saw_no_basic": probe.saw_no_basic,
                "saw_filter_fail": probe.saw_filter_fail,
                "saw_strike_0": probe.saw_strike_0,
            }
        )
        if (i + 1) % 20 == 0 or i == 0:
            print(
                f"  replayed {i+1}/{len(touch_loss)} "
                f"opp_so_far={sum(1 for r in results if r['opportunity'])}"
            )

    num_opp = sum(1 for r in results if r["opportunity"])
    passed = num_opp >= THRESHOLD

    diag = {
        "games_behind_fail": sum(1 for r in results if r["saw_behind_fail"]),
        "games_damage_gt0": sum(1 for r in results if r["saw_damage_gt0"]),
        "games_no_basic": sum(1 for r in results if r["saw_no_basic"]),
        "games_filter_fail": sum(1 for r in results if r["saw_filter_fail"]),
        "games_strike_0": sum(1 for r in results if r["saw_strike_0"]),
        "games_with_copy_swing_before": sum(
            1 for r in results if r["copy_swing_before"] > 0
        ),
        "games_first_copy_seen": sum(1 for r in results if r["first_copy_done"]),
    }

    out = {
        "db": str(DB),
        "code_version_db": code,
        "tip_sha_local_main": None,  # filled by wrapper if known
        "method": (
            "same-seed engine replay (ProbeHeuristic on B; no heuristic change)"
        ),
        "denominator_def": (
            "touch_loss from t092-gard-zoro-500.db "
            "(B played 暗夜王牌 AND winner==0); 权威 236"
        ),
        "denominator": len(touch_loss),
        "opportunity_numerator": num_opp,
        "pass_threshold": THRESHOLD,
        "pass": passed,
        "opp_seeds": [r["seed"] for r in results if r["opportunity"]],
        "examples": [ex for r in results for ex in r["examples"]][:40],
        "diag": diag,
        "denom_seeds": touch_loss,
        "elapsed_s": round(time.time() - t0, 1),
        "all": results,
    }
    # tip sha if git available from cwd
    try:
        import subprocess

        tip = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            text=True,
        ).strip()
        out["tip_sha_local_main"] = tip
    except Exception:
        pass

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = []
    md.append("# task 093 Q3 频数门（只读）\n")
    md.append(
        f"> 2026-10-30 Diupi-Yun · `{DB}` · db `{code}` · tip `{out.get('tip_sha_local_main')}` · "
        f"**同种子引擎重放** · **不改** heuristic\n"
    )
    md.append("## 定义\n\n" + (__doc__ or "") + "\n")
    md.append("## 结果（门禁口径 = B 侧落后 × 零伤一层 copy × 手里有合格供体基础）\n")
    md.append("| 项 | 值 |")
    md.append("|---|---|")
    md.append(f"| 分母（touch_loss = 权威） | **{len(touch_loss)}** |")
    md.append(f"| 机会局 would-change | **{num_opp}/{len(touch_loss)}** |")
    md.append(f"| 门槛 | ≥{THRESHOLD}/236 |")
    md.append(
        f"| **判定** | {'**PASS**' if passed else '**FAIL / 收口**'} |"
    )
    md.append(
        "\n机会种子："
        + (", ".join(map(str, out["opp_seeds"])) or "（无）")
        + "\n"
    )
    md.append("\n### would-change 例\n")
    for ex in out["examples"][:20]:
        md.append(
            f"- prizes B{ex['own_prizes']}/A{ex['opp_prizes']} "
            f"via={ex['via']} dmg={ex['damage']} "
            f"place={ex['place_name']}(iid={ex['place_iid']}) strike={ex['strike']}"
        )
    md.append("\n## 诊断（非门禁，不算进 15）\n")
    md.append(
        f"- 首触前曾有 copy 挥击决策的局：**{diag['games_with_copy_swing_before']}/236**\n"
    )
    md.append(f"- 见到第一下 copy 事件的局：**{diag['games_first_copy_seen']}/236**\n")
    md.append(
        f"- 落后失败（copy 挥击时不落后）：**{diag['games_behind_fail']}/236**\n"
    )
    md.append(f"- 挥击伤害 >0：**{diag['games_damage_gt0']}/236**\n")
    md.append(f"- 手里没有 place_bench 基础：**{diag['games_no_basic']}/236**\n")
    md.append(f"- 过滤不过：**{diag['games_filter_fail']}/236**\n")
    md.append(f"- `_copied_strike` 全 0：**{diag['games_strike_0']}/236**\n")
    md.append(
        "\n说明：门禁只计「落后 + 零伤一层 copy + 合格 place_bench」。"
        "R 实现后这些决策会改打 place_bench（would-change）。"
        "诊断各格可重叠，不自动改成 T/U。\n"
    )
    md.append(
        f"\n## 方法\n\n同种子 `play_game` 重放（实验 `{EXP_YAML.name}`，"
        f"启发式默认参数）。ProbeHeuristic 只读探测 B 侧（player 1），决策不变。"
        f"耗时 {out['elapsed_s']}s。\n"
    )
    md.append(
        "\n## 未做\n\n改 heuristic、写测试、开 TDD、跑 100 局、宣称 30.4%。"
        "T/U 未另计（Q2 锁定只 R）。\n"
    )
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    summary_print = {k: out[k] for k in out if k != "all"}
    print(json.dumps(summary_print, ensure_ascii=False, indent=2))
    print("GATE", "PASS" if passed else "FAIL", f"{num_opp}/{len(touch_loss)}")


if __name__ == "__main__":
    main()
