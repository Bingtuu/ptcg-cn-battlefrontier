# task 156：bfsim prep——备赛编排器测试

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from battlefrontier.runner.experiment import ExperimentDef
from battlefrontier.runner.prep import (
    generate_prep_experiments,
    load_prep_cfg,
    run_prep,
    slugify,
)


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
    p.write_text(yaml.safe_dump(pool, allow_unicode=True), encoding="utf-8")
    return p


def _write_matrix_snap(tmp_path: Path) -> Path:
    cells = []
    for a, b, wr in [("Entry", "Alpha A", 0.5), ("Alpha A", "Entry", 0.5),
                     ("Entry", "Beta B", 0.6), ("Beta B", "Entry", 0.4),
                     ("Alpha A", "Beta B", 0.5), ("Beta B", "Alpha A", 0.5),
                     ("Entry", "Entry", 0.5), ("Alpha A", "Alpha A", 0.5),
                     ("Beta B", "Beta B", 0.5)]:
        cells.append({"a": a, "b": b, "winrate": wr, "n": 10, "source": "sim",
                      "low_confidence": False, "shrunk": False})
    snap = {"schema_version": 1,
            "meta": {"date_from": "2026-09-16", "date_to": "2026-11-14"},
            "cells": cells}
    p = tmp_path / "snap.json"
    p.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return p


def _write_cfg(tmp_path: Path, *, with_mod=True, with_entry=True) -> Path:
    entry = {"archetype": "报名", "deck_id": "src:3"}
    if with_mod:
        mod = tmp_path / "mod.deck.txt"
        mod.write_text("1 卡甲\n", encoding="utf-8")
        entry["modified"] = str(mod)
    cfg = {
        "name": "prep-test",
        "pool": str(_write_pool(tmp_path)),
        "matrix_snap": str(_write_matrix_snap(tmp_path)),
        "field": {"date_from": "2026-11-01", "date_to": "2026-11-15"},
        "games_per_cell": 8,
        "seed_start": 650000,
    }
    if with_entry:
        cfg["entry"] = entry
    p = tmp_path / "prep.yml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return p


def test_slugify_en名压slug():
    assert slugify("Alpha A") == "alpha-a"
    assert slugify("N's Zoroark") == "n-s-zoroark"


def test_cfg_缺entry字段拒收(tmp_path):
    p = _write_cfg(tmp_path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    del raw["entry"]["deck_id"]
    raw["entry"]["modified"] = None
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError):
        load_prep_cfg(p)


def test_generate_成对生成与覆盖(tmp_path):
    cfg = load_prep_cfg(_write_cfg(tmp_path))
    pool = cfg.load_pool()
    exps = generate_prep_experiments(cfg, pool)

    assert len(exps) == 4  # 2 对手 × base/mod
    kinds = {}
    for e in exps:
        parts = e.name.split("-vs-")
        kinds.setdefault(parts[1], []).append(parts[0].replace("prep-test-", ""))
    assert kinds == {"alpha-a": ["base", "mod"], "beta-b": ["base", "mod"]}

    for e in exps:
        assert isinstance(e, ExperimentDef)
        assert e.games == 8
        assert e.seed_start == 650000      # 同域 = 成对 CRN
        if "-mod-vs-" in e.name:
            assert e.decks.a.source == "file"
            assert e.decks.a.path.endswith("mod.deck.txt")
        assert e.decks.b.source == "db"
        assert e.agents.a.type == "heuristic" and e.agents.b.type == "heuristic"
        # 报名卡组恒 a 侧：base 的 a = entry deck_id
        if "-base-vs-" in e.name:
            assert e.decks.a.deck_id == "src:3"


def test_generate_entry_须在池内(tmp_path):
    p = _write_cfg(tmp_path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    raw["entry"]["archetype"] = "池外"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    cfg = load_prep_cfg(p)
    with pytest.raises(ValueError, match="不在卡池"):
        generate_prep_experiments(cfg, cfg.load_pool())


def test_generate_无改表臂_只出base(tmp_path):
    cfg = load_prep_cfg(_write_cfg(tmp_path, with_mod=False))
    exps = generate_prep_experiments(cfg, cfg.load_pool())
    assert len(exps) == 2
    assert all("-base-vs-" in e.name for e in exps)


def test_run_prep_端到端_注入fake跑批(tmp_path, monkeypatch):
    import battlefrontier.runner.prep as prep_mod
    from battlefrontier.runner.results_db import ResultsDB

    cfg = load_prep_cfg(_write_cfg(tmp_path))
    field_out = tmp_path / "field.json"
    results_path = tmp_path / "res.db"
    out_dir = tmp_path / "out"

    # fake 场导出：写同 schema 快照（display_name/value 行）
    def fake_export(db_path, d_from, d_to, out, *, as_of=None):
        from battlefrontier.runner.field_snap import today_iso
        snap = {"meta": {"n_tournaments": 2, "date_to": d_to,
                         "as_of": as_of or today_iso()},
                "data": [{"display_name": "甲", "value": 0.5},
                         {"display_name": "报名", "value": 0.4},
                         {"display_name": "乙", "value": 0.3}]}
        Path(out).write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        return snap

    monkeypatch.setattr(prep_mod, "export_field_snap", fake_export)

    # fake 跑批：每实验 4 局全 a 胜（mod 亦然 → 0 翻转，判读门 False 但全链路通）
    def fake_run(defn, db_path, results_path=..., **kw):
        db = ResultsDB(results_path)
        eid = db.start_experiment(name=defn.name, definition_yaml="",
                                  code_version="t", data_version="t")
        for seed in range(4):
            db.record_game(eid, seed=seed, first_player=0,
                           result=SimpleNamespace(winner=0, is_draw=False,
                                                  turns=5, events_hash="h",
                                                  events=[]),
                           deck_a_id="a", deck_b_id="b")
        db.close()
        return eid

    monkeypatch.setattr(prep_mod, "run_experiment", fake_run)

    report_path = run_prep(cfg, db_path=str(tmp_path / "up.db"),
                           results_path=results_path, field_out=field_out,
                           out_dir=out_dir, workers=1)

    text = Path(report_path).read_text(encoding="utf-8")
    assert "登顶率" in text                    # 限定语头注
    assert "甲" in text                        # field-pick 节
    assert "全正" in text                      # 判读节（走真 mod_check，门行落盘）
    assert "swap-search" in text               # 下一步命令指针
    # 场快照落盘且 meta.as_of 已钉
    snap = json.loads(field_out.read_text(encoding="utf-8"))
    assert snap["meta"]["as_of"] is not None


def test_run_prep_pick_only_零对局(tmp_path, monkeypatch):
    import battlefrontier.runner.prep as prep_mod

    cfg = load_prep_cfg(_write_cfg(tmp_path))
    called: list[str] = []

    def fake_export(db_path, d_from, d_to, out, *, as_of=None):
        Path(out).write_text(json.dumps(
            {"meta": {"date_to": d_to}, "data": [{"display_name": "甲", "value": 1.0}]}),
            encoding="utf-8")
        return {}

    monkeypatch.setattr(prep_mod, "export_field_snap", fake_export)
    monkeypatch.setattr(prep_mod, "run_experiment",
                        lambda *a, **k: called.append("run") or 0)

    report_path = run_prep(cfg, db_path=str(tmp_path / "up.db"),
                           results_path=tmp_path / "res.db",
                           field_out=tmp_path / "field.json",
                           out_dir=tmp_path / "out", pick_only=True)
    assert called == []                       # 零对局
    text = Path(report_path).read_text(encoding="utf-8")
    assert "甲" in text
    assert "全正" not in text                 # 无判读节
