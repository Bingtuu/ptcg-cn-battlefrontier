# task 156：bfsim prep——备赛编排器测试

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from battlefrontier.engine.state import CardDef
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

    (tmp_path / "cards").mkdir()
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

    # fake 装载：60 基本能量（全部豁免，strict 通过）
    from helpers import energy

    def fake_prepare(defn, db_path, **kw):
        deck = [energy()] * 60
        return SimpleNamespace(deck_a=list(deck), deck_b=list(deck),
                               warnings=[], data_version="dv1")

    monkeypatch.setattr(prep_mod, "prepare_experiment", fake_prepare)

    # fake 跑批：完整种子域全 a 胜（mod 亦然 → 0 翻转，判读门 False 但全链路通）
    def fake_execute(prep_exp, defn, results_path, **kw):
        db = ResultsDB(results_path)
        eid = db.start_experiment(name=defn.name, definition_yaml="",
                                  code_version="t", data_version="dv1")
        for seed in range(defn.seed_start, defn.seed_start + defn.games):
            db.record_game(eid, seed=seed, first_player=0,
                           result=SimpleNamespace(winner=0, is_draw=False,
                                                  turns=5, events_hash="h",
                                                  events=[]),
                           deck_a_id="a", deck_b_id="b")
        db.finish_experiment(eid)
        db.close()
        return eid

    monkeypatch.setattr(prep_mod, "execute_experiment", fake_execute)

    report_path = run_prep(cfg, db_path=str(tmp_path / "up.db"),
                           results_path=results_path, field_out=field_out,
                           out_dir=out_dir, workers=1, cards_dir=tmp_path / "cards")

    text = Path(report_path).read_text(encoding="utf-8")
    assert "登顶率" in text                    # 限定语头注
    assert "甲" in text                        # field-pick 节
    assert "全正" in text                      # 判读节（batch 模式走真 mod_check，门行落盘）
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
    monkeypatch.setattr(prep_mod, "prepare_experiment",
                        lambda *a, **k: called.append("prep") or None)
    monkeypatch.setattr(prep_mod, "execute_experiment",
                        lambda *a, **k: called.append("run") or 0)

    report_path = run_prep(cfg, db_path=str(tmp_path / "up.db"),
                           results_path=tmp_path / "res.db",
                           field_out=tmp_path / "field.json",
                           out_dir=tmp_path / "out", pick_only=True)
    assert called == []                       # 零对局、零装载
    text = Path(report_path).read_text(encoding="utf-8")
    assert "甲" in text
    assert "全正" not in text                 # 无判读节


# ── task 157：装载告警段 / strict 覆盖率门槛 / batch.json 批次登记 ─────

TRAINER_NODOC = CardDef(card_id="stub-博士的研究", name="博士的研究",
                        supertype="trainer")


def _patch_field_export(monkeypatch):
    import battlefrontier.runner.prep as prep_mod

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


def _fake_run_prepare_execute(monkeypatch, *, warnings=(), b_deck=None):
    """假装载 + 假跑批（完整种子域全 a 胜、status=done）。
    返回 execute 调用清单（门断言用：拒绝开跑时必须为空）。"""
    from helpers import energy

    import battlefrontier.runner.prep as prep_mod
    from battlefrontier.runner.results_db import ResultsDB

    calls: dict[str, list[str]] = {"execute": []}

    def fake_prepare(defn, db_path, **kw):
        deck = [energy()] * 60
        return SimpleNamespace(deck_a=list(deck), deck_b=list(b_deck or deck),
                               warnings=list(warnings), data_version="dv1")

    def fake_execute(prep_exp, defn, results_path, **kw):
        calls["execute"].append(defn.name)
        db = ResultsDB(results_path)
        eid = db.start_experiment(name=defn.name, definition_yaml="",
                                  code_version="t", data_version="dv1")
        for seed in range(defn.seed_start, defn.seed_start + defn.games):
            db.record_game(eid, seed=seed, first_player=0,
                           result=SimpleNamespace(winner=0, is_draw=False,
                                                  turns=5, events_hash="h",
                                                  events=[]),
                           deck_a_id="a", deck_b_id="b")
        db.finish_experiment(eid)
        db.close()
        return eid

    monkeypatch.setattr(prep_mod, "prepare_experiment", fake_prepare)
    monkeypatch.setattr(prep_mod, "execute_experiment", fake_execute)
    return calls


def _run_prep_kwargs(tmp_path):
    return {"db_path": str(tmp_path / "up.db"), "results_path": tmp_path / "res.db",
            "field_out": tmp_path / "field.json", "out_dir": tmp_path / "out",
            "cards_dir": tmp_path / "cards"}


def test_run_prep_装载告警段与batch登记(tmp_path, monkeypatch):
    """装载告警逐实验进报告；改表判读登记 batch.json（ID 批次 + 预期种子全集
    + 两臂版本 + 池 sha256），供 mod-check 批次模式取数。"""
    _patch_field_export(monkeypatch)
    calls = _fake_run_prepare_execute(monkeypatch, warnings=["vanilla 异文本按无效果结算"])
    (tmp_path / "cards").mkdir()
    cfg = load_prep_cfg(_write_cfg(tmp_path))

    report_path = run_prep(cfg, **_run_prep_kwargs(tmp_path))

    text = Path(report_path).read_text(encoding="utf-8")
    assert "装载告警" in text
    assert "vanilla 异文本按无效果结算" in text
    assert calls["execute"]                       # 放行开跑

    batch = json.loads((tmp_path / "out" / "batch.json").read_text(encoding="utf-8"))
    assert batch["expected_seeds"] == [650000, 650008]   # 来自实验定义
    assert batch["games"] == 8 and batch["seed_start"] == 650000
    assert batch["entry"] == "报名"
    assert batch["code_version"]                  # 非空（git sha 或 unknown）
    assert batch["data_version"] == "dv1"
    assert len(batch["pool_sha256"]) == 64
    assert set(batch["slugs"]) == {"alpha-a", "beta-b"}
    for arms in batch["slugs"].values():
        assert set(arms) == {"base_id", "mod_id"}


def test_run_prep_strict默认开_无文档卡拒绝零局(tmp_path, monkeypatch):
    """默认 strict：对手侧（db 臂同样过闸）含无文档非基本能量卡 → 拒绝开跑，
    零局落库，违规逐条指明卡组侧与卡名。"""
    _patch_field_export(monkeypatch)
    calls = _fake_run_prepare_execute(monkeypatch, b_deck=[TRAINER_NODOC] * 60)
    (tmp_path / "cards").mkdir()
    cfg = load_prep_cfg(_write_cfg(tmp_path))

    with pytest.raises(ValueError, match="strict") as ei:
        run_prep(cfg, **_run_prep_kwargs(tmp_path))
    assert calls["execute"] == []                 # 零局跑批
    msg = str(ei.value)
    assert "博士的研究" in msg and "卡组 b" in msg


def test_run_prep_逃生口_降级声明与放行(tmp_path, monkeypatch):
    """--no-strict-coverage（cfg strict_coverage: false 同口径）：放行开跑，
    报告头注声明降级 + 违规清单如实落装载告警段。"""
    _patch_field_export(monkeypatch)
    calls = _fake_run_prepare_execute(monkeypatch, b_deck=[TRAINER_NODOC] * 60)
    (tmp_path / "cards").mkdir()
    p = _write_cfg(tmp_path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    raw["strict_coverage"] = False
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    cfg = load_prep_cfg(p)
    assert cfg.strict_coverage is False

    report_path = run_prep(cfg, **_run_prep_kwargs(tmp_path))
    assert calls["execute"]                       # 逃生口放行
    text = Path(report_path).read_text(encoding="utf-8")
    assert "显式关闭" in text                      # 头注降级声明
    assert "博士的研究" in text                    # 违规如实披露


# ── task 158：证据包（inputs/ + verdict.json/csv + 复算三元组）────────

def test_run_prep_证据包落盘(tmp_path, monkeypatch):
    """改表判读产物 = 可离线追溯制品目录：inputs/（定义副本 + 卡表内容+sha256
    + 场快照副本 + 矩阵快照身份）+ verdict.json/csv + 报告头注复算三元组。"""
    _patch_field_export(monkeypatch)
    _fake_run_prepare_execute(monkeypatch)
    (tmp_path / "cards").mkdir()
    cfg = load_prep_cfg(_write_cfg(tmp_path))

    report_path = run_prep(cfg, **_run_prep_kwargs(tmp_path),
                           prep_source=_write_cfg(tmp_path))
    out_dir = tmp_path / "out"

    # inputs/：定义副本 + 改表 decklist 内容副本 + 场快照副本 + 卡表身份
    inputs = out_dir / "inputs"
    assert (inputs / "prep.yml").is_file()
    mod_copy = inputs / "mod.deck.txt"
    assert mod_copy.is_file()
    assert mod_copy.read_text(encoding="utf-8") == "1 卡甲\n"
    field_copy = inputs / "field-snap.json"
    assert field_copy.is_file()
    assert json.loads(field_copy.read_text(encoding="utf-8"))["meta"]["as_of"]
    decks = json.loads((inputs / "decks.json").read_text(encoding="utf-8"))
    assert decks["base"] == {"deck_id": "src:3"}            # 基线 deck_id
    assert decks["mod"]["file"] == "mod.deck.txt"
    assert len(decks["mod"]["sha256"]) == 64
    manifest = json.loads((inputs / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["mod.deck.txt"] == decks["mod"]["sha256"]  # 自含 hash
    assert manifest["prep.yml"]                         # 定义副本 hash
    assert manifest["matrix_snap"]["path"].endswith("snap.json")
    assert len(manifest["matrix_snap"]["sha256"]) == 64

    # verdict.json：逐格 + 四门 + 复算三元组
    verdict = json.loads((out_dir / "verdict.json").read_text(encoding="utf-8"))
    assert verdict["meta"]["definition_sha256"] == manifest["prep.yml"]
    assert verdict["meta"]["code_version"]
    assert verdict["meta"]["data_version"] == "dv1"
    assert len(verdict["cells"]) == 2                        # 2 对手
    alpha = next(c for c in verdict["cells"] if c["slug"] == "alpha-a")
    assert alpha["base_wr"] == pytest.approx(1.0) and alpha["mod_wr"] == pytest.approx(1.0)
    assert verdict["gates"] == {"all_positive": False, "all_significant": False,
                                "zero_giveback": True, "complete": True}
    assert verdict["delta_pp"] == pytest.approx(0.0)

    # verdict.csv：表头 + 逐格行
    csv_text = (out_dir / "verdict.csv").read_text(encoding="utf-8")
    lines = [l for l in csv_text.strip().splitlines() if l]
    assert lines[0].startswith("slug,opponent,")
    assert len(lines) == 3                                   # 表头 + 2 格

    # 报告头注回显复算三元组
    report = Path(report_path).read_text(encoding="utf-8")
    assert "复算三元组" in report
    assert manifest["prep.yml"][:12] in report
    assert "dv1" in report


def test_run_prep_卡表篡改可发现(tmp_path, monkeypatch):
    """证据包自含 hash：卡表文件事后被改 → 重算 hash 与证据包不一致（可发现）。"""
    import hashlib

    _patch_field_export(monkeypatch)
    _fake_run_prepare_execute(monkeypatch)
    (tmp_path / "cards").mkdir()
    cfg = load_prep_cfg(_write_cfg(tmp_path))
    run_prep(cfg, **_run_prep_kwargs(tmp_path), prep_source=_write_cfg(tmp_path))

    mod_file = tmp_path / "mod.deck.txt"
    mod_file.write_text("1 卡乙\n", encoding="utf-8")     # 事后篡改
    manifest = json.loads(
        (tmp_path / "out" / "inputs" / "manifest.json").read_text(encoding="utf-8"))
    now = hashlib.sha256(mod_file.read_bytes()).hexdigest()
    assert now != manifest["mod.deck.txt"]                # 篡改被证据包发现


# ── task 160：对手构筑分布（opponent_builds）────────────────────────

def _write_cfg_with_opp_builds(tmp_path, builds: dict[str, list[str]],
                               *, with_mod=True) -> Path:
    """builds: {池内中文名: [额外 decklist 路径, ...]}。"""
    p = _write_cfg(tmp_path, with_mod=with_mod)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    raw["opponent_builds"] = builds
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return p


def test_generate_对手多构筑_双臂展开(tmp_path):
    b2 = tmp_path / "opp-alpha-b2.deck.txt"
    b2.write_text("1 卡乙\n", encoding="utf-8")
    cfg = load_prep_cfg(_write_cfg_with_opp_builds(tmp_path, {"甲": [str(b2)]}))
    pool = cfg.load_pool()
    exps = generate_prep_experiments(cfg, pool)

    assert len(exps) == 6          # 2 臂 × (alpha-a + alpha-a~b2 + beta-b)
    names = {e.name for e in exps}
    assert "prep-test-base-vs-alpha-a~b2" in names
    assert "prep-test-mod-vs-alpha-a~b2" in names
    for e in exps:
        assert e.games == 8 and e.seed_start == 650000   # 同域 = 成对 CRN
        if e.name.endswith("alpha-a~b2"):
            assert e.decks.b.source == "file"
            assert e.decks.b.path.endswith("opp-alpha-b2.deck.txt")
        else:
            assert e.decks.b.source == "db"


def test_generate_对手多构筑_池外名或缺文件拒收(tmp_path):
    b2 = tmp_path / "b2.deck.txt"
    b2.write_text("1 卡乙\n", encoding="utf-8")
    cfg = load_prep_cfg(_write_cfg_with_opp_builds(tmp_path, {"池外": [str(b2)]}))
    with pytest.raises(ValueError, match="不在卡池"):
        generate_prep_experiments(cfg, cfg.load_pool())

    cfg = load_prep_cfg(_write_cfg_with_opp_builds(
        tmp_path, {"甲": [str(tmp_path / "nope.deck.txt")]}))
    with pytest.raises(ValueError, match="不存在"):
        generate_prep_experiments(cfg, cfg.load_pool())


def test_run_prep_对手多构筑_批次与证据包(tmp_path, monkeypatch):
    """opponent_builds 全流程：batch.json 登记 ~bN 臂、判读逐 build 格、
    证据包 decks.json 落对手构筑副本 + sha256。"""
    _patch_field_export(monkeypatch)
    _fake_run_prepare_execute(monkeypatch)
    (tmp_path / "cards").mkdir()
    b2 = tmp_path / "opp-alpha-b2.deck.txt"
    b2.write_text("1 卡乙\n", encoding="utf-8")
    cfg = load_prep_cfg(_write_cfg_with_opp_builds(tmp_path, {"甲": [str(b2)]}))

    report_path = run_prep(cfg, **_run_prep_kwargs(tmp_path),
                           prep_source=_write_cfg_with_opp_builds(
                               tmp_path, {"甲": [str(b2)]}))
    out_dir = tmp_path / "out"

    batch = json.loads((out_dir / "batch.json").read_text(encoding="utf-8"))
    assert set(batch["slugs"]) == {"alpha-a", "alpha-a~b2", "beta-b"}

    decks = json.loads((out_dir / "inputs" / "decks.json").read_text(
        encoding="utf-8"))
    build = decks["opponent_builds"]["alpha-a~b2"]
    assert build["file"] == "opp-alpha-b2.deck.txt"
    assert len(build["sha256"]) == 64
    assert (out_dir / "inputs" / "opp-alpha-b2.deck.txt").is_file()
    manifest = json.loads((out_dir / "inputs" / "manifest.json").read_text(
        encoding="utf-8"))
    assert manifest["opp-alpha-b2.deck.txt"] == build["sha256"]

    verdict = json.loads((out_dir / "verdict.json").read_text(encoding="utf-8"))
    assert len(verdict["cells"]) == 3                    # 逐 build 格
    assert {c["slug"] for c in verdict["cells"]} == {
        "alpha-a", "alpha-a~b2", "beta-b"}

    text = Path(report_path).read_text(encoding="utf-8")
    assert "alpha-a~b2" in text                          # 判读节逐 build 行
    assert "多构筑均值" in text                           # 期望口径声明
