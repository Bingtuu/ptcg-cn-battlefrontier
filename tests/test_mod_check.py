# task 156：bfsim mod-check——改表成对判读测试（t152_gard_verdict 泛化）

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from battlefrontier.report.mod_check import (
    format_mod_check,
    mod_check_report,
    paired_flip_p,
)
from battlefrontier.runner.results_db import ResultsDB


def _result(winner, draw=False):
    return SimpleNamespace(winner=winner, is_draw=draw, turns=10,
                           events_hash="h", events=[])


def _start(db: ResultsDB, name: str, *, code_version: str = "t",
           data_version: str = "t") -> int:
    return db.start_experiment(name=name, definition_yaml="", code_version=code_version,
                               data_version=data_version)


def _record(db: ResultsDB, exp_id: int, outcomes: dict[int, str]) -> None:
    """outcomes: seed -> 'a'|'b'|'draw'（a = 报名卡组侧）。"""
    for seed in sorted(outcomes):
        o = outcomes[seed]
        if o == "draw":
            db.record_game(exp_id, seed=seed, first_player=0,
                           result=_result(None, draw=True),
                           deck_a_id="entry", deck_b_id="opp")
        else:
            db.record_game(exp_id, seed=seed, first_player=0,
                           result=_result(0 if o == "a" else 1),
                           deck_a_id="entry", deck_b_id="opp")


def _write_field(tmp_path: Path) -> Path:
    snap = {"meta": {"date_to": "2026-11-15"},
            "data": [
                {"display_name": "报名", "value": 0.4},
                {"display_name": "甲", "value": 0.5},
                {"display_name": "乙", "value": 0.3},
                {"display_name": "池外构筑", "value": 0.9},
            ]}
    p = tmp_path / "field.json"
    p.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return p


def _write_pool(tmp_path: Path) -> Path:
    pool = {
        "version": 2, "locked_at": "2026-11-22",
        "query": {"granularity": "archetype", "window": "w", "division": "master",
                  "basis": "cn", "min_n": 5, "n_tournaments": 1,
                  "snapshot": "s", "name_group_rules_hash": "h"},
        "decks": [
            {"archetype": "甲", "en_archetype": "Alpha A", "wur": 0.5, "n": 10,
             "deck_id": "src:1"},
            {"archetype": "报名", "en_archetype": "Entry", "wur": 0.4, "n": 10,
             "deck_id": "src:3"},
            {"archetype": "乙", "en_archetype": "Beta B", "wur": 0.3, "n": 10,
             "deck_id": "src:2"},
        ],
    }
    p = tmp_path / "pool.yml"
    import yaml
    p.write_text(yaml.safe_dump(pool, allow_unicode=True), encoding="utf-8")
    return p


def _build_db(tmp_path: Path) -> str:
    """alpha：base 4/8、mod 8/8（4 翻转全正向 → 手算 p=0.125）；
    beta：base=mod（含 1 平局）→ 0 翻转 p=1.0。"""
    db = ResultsDB(tmp_path / "res.db")
    alpha_base = {1: "a", 2: "a", 3: "b", 4: "b", 5: "a", 6: "a", 7: "b", 8: "b"}
    alpha_mod = {s: "a" for s in range(1, 9)}
    beta_base = {1: "a", 2: "b", 3: "draw"}
    beta_mod = {1: "a", 2: "b", 3: "draw"}
    for name, outcomes in [
        ("t-base-vs-alpha-a", alpha_base), ("t-mod-vs-alpha-a", alpha_mod),
        ("t-base-vs-beta-b", beta_base), ("t-mod-vs-beta-b", beta_mod),
    ]:
        _record(db, _start(db, name), outcomes)
    db.close()
    return str(tmp_path / "res.db")


def test_paired_flip_p_手算():
    # n=4 全正向翻转：P(X≥4)=1/16，双侧 = 0.125
    assert paired_flip_p(4, 0) == pytest.approx(0.125)
    # n=0 → p=1（无翻转不显著）
    assert paired_flip_p(0, 0) == 1.0
    # 对称翻转 → p=1
    assert paired_flip_p(2, 2) == 1.0


def test_mod_check_逐格与期望_手算复现(tmp_path):
    db_path = _build_db(tmp_path)
    rep = mod_check_report(db_path, base_prefix="t-base-vs-",
                           mod_prefix="t-mod-vs-", field_path=_write_field(tmp_path),
                           pool_path=_write_pool(tmp_path), entry="报名")

    alpha = next(c for c in rep.cells if c.slug == "alpha-a")
    assert alpha.base_wr == pytest.approx(0.5)      # 4/8
    assert alpha.mod_wr == pytest.approx(1.0)
    assert alpha.delta_pp == pytest.approx(50.0)
    assert alpha.p == pytest.approx(0.125)          # 4 翻转全正向
    assert alpha.flips == 4

    beta = next(c for c in rep.cells if c.slug == "beta-b")
    assert beta.base_wr == pytest.approx(1 / 3)     # 平局计入 n 不计胜
    assert beta.mod_wr == pytest.approx(1 / 3)
    assert beta.p == 1.0
    assert beta.flips == 0

    # 场权重：池内 {甲 .5, 乙 .3} 归一（报名 .4 剔除、池外构筑剔除）
    # base_exp = .5*5/8 + (1/3)*3/8 = 0.4375；mod_exp = 1*5/8 + (1/3)*3/8 = 0.75
    assert rep.weights == pytest.approx({"alpha-a": 5 / 8, "beta-b": 3 / 8})
    assert rep.base_exp == pytest.approx(0.4375)
    assert rep.mod_exp == pytest.approx(0.75)
    assert rep.delta_pp == pytest.approx(31.25)

    # 门：beta Δ=0 → 非全正；alpha p=0.125 → 非全显著；无回吐
    assert rep.all_positive is False
    assert rep.all_significant is False
    assert rep.zero_giveback is True
    assert rep.seed_gaps == {}


def test_mod_check_种子缺口显式列出(tmp_path):
    db_path = _build_db(tmp_path)
    con = sqlite3.connect(db_path)
    # 删掉 alpha mod 的 seed=8（AND 行 = base 胜 mod 负的配对缺口）
    exp = con.execute("SELECT id FROM experiments WHERE name='t-mod-vs-alpha-a'").fetchone()[0]
    con.execute("DELETE FROM games WHERE experiment_id=? AND seed=8", (exp,))
    con.commit()
    con.close()

    rep = mod_check_report(db_path, base_prefix="t-base-vs-",
                           mod_prefix="t-mod-vs-", field_path=_write_field(tmp_path),
                           pool_path=_write_pool(tmp_path), entry="报名")
    assert rep.seed_gaps == {"alpha-a": 1}
    assert "alpha-a" in format_mod_check(rep)


def test_mod_check_无配对实验报错(tmp_path):
    db = ResultsDB(tmp_path / "empty.db")
    _record(db, _start(db, "t-base-vs-alpha-a"), {1: "a"})
    db.close()
    with pytest.raises(ValueError, match="无配对"):
        mod_check_report(str(tmp_path / "empty.db"), base_prefix="t-base-vs-",
                         mod_prefix="t-mod-vs-",
                         field_path=_write_field(tmp_path),
                         pool_path=_write_pool(tmp_path), entry="报名")


def test_mod_check_error局报错不静默(tmp_path):
    db = ResultsDB(tmp_path / "err.db")
    eid = _start(db, "t-mod-vs-alpha-a")
    db.record_error(eid, seed=1, deck_a_id="entry", deck_b_id="opp", error="boom")
    db.close()
    with pytest.raises(ValueError, match="error"):
        mod_check_report(str(tmp_path / "err.db"), base_prefix="t-base-vs-",
                         mod_prefix="t-mod-vs-",
                         field_path=_write_field(tmp_path),
                         pool_path=_write_pool(tmp_path), entry="报名")


def test_format_含限定语与门(tmp_path):
    db_path = _build_db(tmp_path)
    rep = mod_check_report(db_path, base_prefix="t-base-vs-",
                           mod_prefix="t-mod-vs-", field_path=_write_field(tmp_path),
                           pool_path=_write_pool(tmp_path), entry="报名")
    text = format_mod_check(rep)
    assert "登顶率" in text                # 复用 field-pick 限定语
    assert "模拟器内" in text              # sim 口径声明
    assert "全正" in text and "显著" in text


# ── task 157：batch 批次模式（按 ID 取数 + complete 第四门）─────────

def _build_db_with_ids(tmp_path: Path) -> tuple[str, dict[str, dict[str, int]]]:
    """COMPLETE 批次：alpha base 4/8、mod 8/8（p=0.125）；beta 两臂同赛果
    （2a/3b/3draw，含 1 平局在种子 3）→ 0 翻转 p=1.0。status=done，
    返回 {slug: {base_id, mod_id}}。"""
    db = ResultsDB(tmp_path / "res.db")
    alpha_base = {1: "a", 2: "a", 3: "b", 4: "b", 5: "a", 6: "a", 7: "b", 8: "b"}
    alpha_mod = {s: "a" for s in range(1, 9)}
    beta_base = {1: "a", 2: "b", 3: "draw", 4: "a", 5: "b",
                 6: "draw", 7: "a", 8: "b"}
    beta_mod = dict(beta_base)
    ids: dict[str, dict[str, int]] = {}
    for slug, base, mod in [("alpha-a", alpha_base, alpha_mod),
                            ("beta-b", beta_base, beta_mod)]:
        eb = _start(db, f"t-base-vs-{slug}")
        _record(db, eb, base)
        db.finish_experiment(eb)
        em = _start(db, f"t-mod-vs-{slug}")
        _record(db, em, mod)
        db.finish_experiment(em)
        ids[slug] = {"base_id": eb, "mod_id": em}
    db.close()
    return str(tmp_path / "res.db"), ids


def _write_batch(tmp_path: Path, ids: dict[str, dict[str, int]],
                 *, seed_start: int = 1, games: int = 8) -> Path:
    batch = {
        "entry": "报名", "games": games, "seed_start": seed_start,
        "expected_seeds": [seed_start, seed_start + games],
        "code_version": "t", "data_version": "t",
        "pool_sha256": "0" * 64,
        "slugs": ids,
    }
    p = tmp_path / "batch.json"
    p.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
    return p


def _batch_report(db_path, batch_path, tmp_path):
    return mod_check_report(db_path, batch=batch_path,
                            field_path=_write_field(tmp_path),
                            pool_path=_write_pool(tmp_path), entry="报名")


def test_batch_手算复现与complete门(tmp_path):
    """COMPLETE 下与手算一致：批次模式按登记 ID 取数，三门可判。"""
    db_path, ids = _build_db_with_ids(tmp_path)
    rep = _batch_report(db_path, _write_batch(tmp_path, ids), tmp_path)

    assert rep.complete is True
    alpha = next(c for c in rep.cells if c.slug == "alpha-a")
    assert alpha.base_wr == pytest.approx(0.5) and alpha.mod_wr == pytest.approx(1.0)
    assert alpha.p == pytest.approx(0.125)
    assert rep.weights == pytest.approx({"alpha-a": 5 / 8, "beta-b": 3 / 8})
    assert rep.delta_pp == pytest.approx(31.25)
    assert rep.all_positive is False and rep.all_significant is False
    assert rep.zero_giveback is True

    text = format_mod_check(rep)
    assert "不可判定" not in text


def test_batch_同名两轮_只取登记批次(tmp_path):
    """同 prep 名跑两轮：第一轮数据（同名实验）零混入，判读只认第二轮 ID。"""
    # 第一轮：全部 b 胜（若混入则 alpha mod_wr != 1.0）
    db = ResultsDB(tmp_path / "res.db")
    for name in ["t-base-vs-alpha-a", "t-mod-vs-alpha-a",
                 "t-base-vs-beta-b", "t-mod-vs-beta-b"]:
        _record(db, _start(db, name), {1: "b", 2: "b"})
    db.close()
    db_path, ids = _build_db_with_ids(tmp_path)

    rep = _batch_report(db_path, _write_batch(tmp_path, ids), tmp_path)
    alpha = next(c for c in rep.cells if c.slug == "alpha-a")
    assert alpha.n_base == 8 and alpha.n_mod == 8   # 只有第二轮的 8 局
    assert alpha.mod_wr == pytest.approx(1.0)
    assert rep.complete is True


def test_batch_缺种子_INCOMPLETE_门不可判定(tmp_path):
    db_path, ids = _build_db_with_ids(tmp_path)
    con = sqlite3.connect(db_path)
    exp = con.execute("SELECT id FROM experiments WHERE name='t-mod-vs-alpha-a'").fetchone()[0]
    con.execute("DELETE FROM games WHERE experiment_id=? AND seed=8", (exp,))
    con.commit()
    con.close()

    rep = _batch_report(db_path, _write_batch(tmp_path, ids), tmp_path)
    assert rep.complete is False
    assert rep.all_positive is False and rep.all_significant is False
    assert rep.zero_giveback is False          # 三门不置 ✅
    text = format_mod_check(rep)
    assert "不可判定" in text
    assert "INCOMPLETE" in text


def test_batch_重复种子_显式报错(tmp_path):
    db_path, ids = _build_db_with_ids(tmp_path)
    con = sqlite3.connect(db_path)
    exp = con.execute("SELECT id FROM experiments WHERE name='t-mod-vs-alpha-a'").fetchone()[0]
    con.execute(
        "INSERT INTO games (experiment_id, seed, first_player, winner, is_draw,"
        " turns, events_hash, deck_a_id, deck_b_id) VALUES (?, 8, 0, 0, 0, 5, 'h', 'a', 'b')",
        (exp,))
    con.commit()
    con.close()

    with pytest.raises(ValueError, match="重复"):
        _batch_report(db_path, _write_batch(tmp_path, ids), tmp_path)


def test_batch_跨版本_显式报错(tmp_path):
    db_path, ids = _build_db_with_ids(tmp_path)
    con = sqlite3.connect(db_path)
    exp = con.execute("SELECT id FROM experiments WHERE name='t-mod-vs-alpha-a'").fetchone()[0]
    con.execute("UPDATE experiments SET code_version='OTHER' WHERE id=?", (exp,))
    con.commit()
    con.close()

    with pytest.raises(ValueError, match="版本"):
        _batch_report(db_path, _write_batch(tmp_path, ids), tmp_path)


def test_batch_半途中断_INCOMPLETE(tmp_path):
    db_path, ids = _build_db_with_ids(tmp_path)
    con = sqlite3.connect(db_path)
    exp = con.execute("SELECT id FROM experiments WHERE name='t-mod-vs-alpha-a'").fetchone()[0]
    con.execute("UPDATE experiments SET status='running' WHERE id=?", (exp,))
    con.commit()
    con.close()

    rep = _batch_report(db_path, _write_batch(tmp_path, ids), tmp_path)
    assert rep.complete is False
    assert "不可判定" in format_mod_check(rep)


def test_batch_缺登记slug_显式报错(tmp_path):
    db_path, ids = _build_db_with_ids(tmp_path)
    del ids["beta-b"]
    with pytest.raises(ValueError, match="登记"):
        _batch_report(db_path, _write_batch(tmp_path, ids), tmp_path)


def test_batch_与前缀参数互斥(tmp_path):
    db_path, ids = _build_db_with_ids(tmp_path)
    with pytest.raises(ValueError, match="互斥"):
        mod_check_report(db_path, batch=_write_batch(tmp_path, ids),
                         base_prefix="t-base-vs-",
                         field_path=_write_field(tmp_path),
                         pool_path=_write_pool(tmp_path), entry="报名")
