"""task 019：bfsim CLI —— run 子命令端到端（PRD §8 / M3「CLI 实验 Runner」）。"""

from pathlib import Path

import pytest

from battlefrontier.cli import main
from battlefrontier.runner.results_db import ResultsDB

DB_PATH = Path(r"C:/Vibe Project/Pokearena/data/ptcg-cn.db")

CLI_YAML = """
name: cli-e2e
games: 2
seed_start: 300
decks:
  a: {source: db, deck_id: "mik_moe:644634"}
  b: {source: db, deck_id: "mik_moe:644634"}
agents:
  a: {type: heuristic}
  b: {type: random}
"""


def test_cli_no_args_placeholder(capsys):
    assert main([]) == 0
    assert "battlefrontier" in capsys.readouterr().out


@pytest.mark.skipif(not DB_PATH.exists(), reason="本机无 ptcg-cn.db")
def test_cli_run_end_to_end(tmp_path, capsys):
    exp = tmp_path / "exp.yml"
    exp.write_text(CLI_YAML, encoding="utf-8")
    results = tmp_path / "results.db"
    rc = main(["run", str(exp), "--results", str(results),
               "--db", str(DB_PATH), "--cards-dir", "cards"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "cli-e2e" in out and "实验" in out
    db = ResultsDB(results)
    try:
        exps = db._conn.execute(
            "SELECT status FROM experiments WHERE name='cli-e2e'").fetchall()
        assert exps == [("done",)]
        exp_id = db._conn.execute(
            "SELECT id FROM experiments WHERE name='cli-e2e'").fetchone()[0]
        assert len(db.games(exp_id)) == 2
    finally:
        db.close()


def _seed_pair(results: Path):
    """造 base/variant 两实验供 sensitivity 子命令冒烟。"""
    from battlefrontier.runner.play import GameResult

    db = ResultsDB(results)
    ids = []
    for variant, wins in (("", 3), ("v1", 1)):
        exp_id = db.start_experiment(name="grp", definition_yaml="y",
                                     code_version="c", data_version="d",
                                     group_name="grp", variant=variant)
        for seed in range(4):
            res = GameResult(winner=0 if seed < wins else 1, is_draw=False,
                             turns=8, phase="main", first_player=0)
            db.record_game(exp_id, seed=seed, first_player=0, result=res,
                           deck_a_id="a", deck_b_id="b")
        db.finish_experiment(exp_id)
        ids.append(exp_id)
    db.close()
    return ids


def test_cli_sensitivity(tmp_path, capsys):
    """task 023：bfsim sensitivity <base> <variant...> 并排 ΔWR 报告。"""
    results = tmp_path / "r.db"
    base_id, var_id = _seed_pair(results)
    rc = main(["sensitivity", str(base_id), str(var_id),
               "--results", str(results)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ΔWR" in out and "v1" in out


def test_cli_sensitivity_bad_id(tmp_path, capsys):
    results = tmp_path / "r.db"
    _seed_pair(results)
    rc = main(["sensitivity", "999", "1", "--results", str(results)])
    assert rc == 1
    assert "错误" in capsys.readouterr().out


# ── task 024：dsl-check（LLM harness 闸 1：schema + 词表校验）──

VALID_CARD_YAML = """\
card:
  name_group: 测试球
  card_ids: [TEST-001]
effects:
  - trigger: on_play
    actions:
      - {action: shuffle_deck}
"""

INVALID_CARD_YAML = """\
card:
  name_group: 测试球
  card_ids: [TEST-001]
effects:
  - trigger: on_play
    actions:
      - {action: 不存在的动作}
"""


def test_cli_dsl_check_valid(tmp_path, capsys):
    p = tmp_path / "ok.yml"
    p.write_text(VALID_CARD_YAML, encoding="utf-8")
    rc = main(["dsl-check", str(p)])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_cli_dsl_check_invalid_vocab(tmp_path, capsys):
    p = tmp_path / "bad.yml"
    p.write_text(INVALID_CARD_YAML, encoding="utf-8")
    rc = main(["dsl-check", str(p)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "bad.yml" in out and "未知" in out


def test_cli_dsl_check_mixed_files(tmp_path, capsys):
    ok = tmp_path / "ok.yml"
    ok.write_text(VALID_CARD_YAML, encoding="utf-8")
    bad = tmp_path / "bad.yml"
    bad.write_text("card: {name_group: x, card_ids: notalist}\n", encoding="utf-8")  # schema 类型错
    rc = main(["dsl-check", str(ok), str(bad)])
    assert rc == 1  # 任一失败即 rc=1，合法文件也照常报告
    out = capsys.readouterr().out
    assert "OK" in out and "bad.yml" in out


# ── task 026 WP0：dsl-check --db（闸 1 装配校验）──────────
# 三项追加校验：① card_id 存在于 db；② 文件内 card_ids 归一化 text_raw 一致；
# ③ 每个 card_id 在最新 standard 合法性快照内。无 --db 行为不变（上方用例覆盖）。

DB_YAML = """\
card:
  name_group: 测试球
  card_ids: [{ids}]
effects:
  - trigger: on_play
    actions:
      - {{action: shuffle_deck}}
"""

needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="本机无 ptcg-cn.db")


def _check_db(tmp_path, ids: str, capsys):
    p = tmp_path / "card.yml"
    p.write_text(DB_YAML.format(ids=ids), encoding="utf-8")
    rc = main(["dsl-check", str(p), "--db", str(DB_PATH)])
    return rc, capsys.readouterr().out


@needs_db
def test_dsl_check_db_未知_card_id_FAIL(tmp_path, capsys):
    rc, out = _check_db(tmp_path, "FAKE-999", capsys)
    assert rc == 1 and "FAIL" in out and "FAKE-999" in out


@needs_db
def test_dsl_check_db_文本不等价_FAIL_列出分歧(tmp_path, capsys):
    # 朋友手册：CSV1C-111「最多2张」 vs CSM1DC-246「2张」——异文本混挂必须拦下
    rc, out = _check_db(tmp_path, "CSV1C-111, CSM1DC-246", capsys)
    assert rc == 1 and "FAIL" in out
    assert "CSV1C-111" in out and "CSM1DC-246" in out


@needs_db
def test_dsl_check_db_退环境印刷_FAIL(tmp_path, capsys):
    # 彷徨夜灵 D 标 CS2.5C-018：不在最新 standard 快照（退环境）
    rc, out = _check_db(tmp_path, "CS2.5C-018", capsys)
    assert rc == 1 and "FAIL" in out and "CS2.5C-018" in out


@needs_db
def test_dsl_check_db_空_card_ids_FAIL(tmp_path, capsys):
    p = tmp_path / "empty.yml"
    p.write_text("card:\n  name_group: 测试球\n  card_ids: []\n"
                 "effects:\n  - trigger: on_play\n"
                 "    actions:\n      - {action: shuffle_deck}\n", encoding="utf-8")
    rc = main(["dsl-check", str(p), "--db", str(DB_PATH)])
    out = capsys.readouterr().out
    assert rc == 1 and "FAIL" in out and "挂载键必填" in out


@needs_db
def test_dsl_check_db_全绿_OK_回显卡名效果数(tmp_path, capsys):
    # 朋友手册 G 标同文本两印刷：存在 + 文本一致 + 快照内合法
    rc, out = _check_db(tmp_path, "CSV1C-111, CSV6C-163", capsys)
    assert rc == 0 and "OK" in out and "测试球" in out and "1 个效果" in out


@needs_db
def test_dsl_check_db_全库扫描全_OK(capsys):
    """审计后定义库全库过闸 1（task 026 WP0 验收 18）。"""
    import glob

    rc = main(["dsl-check", *sorted(glob.glob("cards/*.yml")), "--db", str(DB_PATH)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "FAIL" not in out
