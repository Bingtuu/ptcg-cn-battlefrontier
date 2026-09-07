"""CLI 入口（bfsim）：实验 Runner 子命令随里程碑逐个添加（task 019: run）。"""

from __future__ import annotations

import argparse
from pathlib import Path

from battlefrontier.runner.experiment import (
    DEFAULT_CARDS_DIR,
    DEFAULT_RESULTS_PATH,
    execute_experiment,
    load_db_path,
    load_experiment,
    prepare_experiment,
)
from battlefrontier.runner.results_db import ResultsDB


def _summarize(db: ResultsDB, exp_id: int, label: str, defn) -> str:
    games = db.games(exp_id)
    wins_a = sum(1 for g in games if g["winner"] == 0)
    wins_b = sum(1 for g in games if g["winner"] == 1)
    draws = sum(1 for g in games if g["is_draw"])
    failed = sum(1 for g in games if g["error"])
    return (f"实验 #{exp_id}「{label}」完成：{len(games)} 局 "
            f"A胜 {wins_a} / B胜 {wins_b} / 平 {draws} / 失败 {failed}")


def _cmd_run(args: argparse.Namespace) -> int:
    from battlefrontier.runner.experiment import run_group

    exp_path = Path(args.experiment)
    defn = load_experiment(exp_path)
    definition_yaml = exp_path.read_text(encoding="utf-8")
    db_path = args.db or load_db_path()
    if defn.variants:
        # 换卡敏感性分组（task 023）：baseline + variants 同种子区间依次跑
        ids, warnings = run_group(defn, db_path, args.results, workers=args.workers,
                                  cards_dir=args.cards_dir,
                                  definition_yaml=definition_yaml)
        for w in warnings:
            print(f"[装载告警] {w}")
        db = ResultsDB(args.results)
        try:
            labels = ["baseline"] + [v.name for v in defn.variants]
            for exp_id, label in zip(ids, labels, strict=True):
                print(_summarize(db, exp_id, f"{defn.name}/{label}", defn))
        finally:
            db.close()
        print(f"分组完成（结果库 {args.results}）："
              f"敏感性报告用 bfsim sensitivity {ids[0]} "
              + " ".join(str(i) for i in ids[1:]))
        print(f"数据版本锁定见各实验行；种子区间 {defn.seed_start}.."
              f"{defn.seed_start + defn.games - 1}（各组相同，配对可比）")
        return 0

    prep = prepare_experiment(defn, db_path, cards_dir=args.cards_dir)
    for w in prep.warnings:
        print(f"[装载告警] {w}")
    exp_id = execute_experiment(prep, defn, args.results, workers=args.workers,
                                definition_yaml=definition_yaml)

    db = ResultsDB(args.results)
    try:
        print(_summarize(db, exp_id, defn.name, defn) + f"（结果库 {args.results}）")
    finally:
        db.close()
    print(f"数据版本 {prep.data_version}；种子区间 {defn.seed_start}.."
          f"{defn.seed_start + defn.games - 1}")
    return 0


def _cmd_sensitivity(args: argparse.Namespace) -> int:
    from battlefrontier.report.sensitivity import (
        format_sensitivity,
        sensitivity_report,
    )

    db = ResultsDB(args.results)
    try:
        try:
            rep = sensitivity_report(db, args.base_id, args.variant_ids)
        except ValueError as e:
            print(f"错误：{e}")
            return 1
        print(format_sensitivity(rep))
    finally:
        db.close()
    return 0


def _check_doc_against_db(doc, db, legal_ids: frozenset, snapshot_id: str) -> None:
    """闸 1 装配校验（task 026 WP0，--db 时启用）；失败抛 DslError 列明原因。

    ① card_ids 非空（挂载键必填）且全部存在于 db；② 文件内所有 card_ids 的
    归一化 text_raw（去全部空白）完全一致（不一致列出分歧 card_id 分组）；
    ③ 每个 card_id 在最新 standard 合法性快照（LegalityPool，含再录合法）内。
    """
    from battlefrontier.dsl.loader import DslError

    if not doc.card.card_ids:
        raise DslError("card_ids 为空——挂载键必填（装载键 = card_id 精确挂载）")
    texts: dict[str, str] = {}
    marks: dict[str, str] = {}
    for cid in doc.card.card_ids:
        card = db.get_card(cid)
        if card is None:
            raise DslError(f"未知 card_id '{cid}'（db 无此印刷）")
        texts[cid] = "".join(card.text_raw.split())
        marks[cid] = card.regulation_mark
    distinct = set(texts.values())
    if len(distinct) > 1:
        groups: dict[str, list[str]] = {}
        for cid, t in texts.items():
            groups.setdefault(t, []).append(cid)
        detail = " / ".join(str(sorted(g)) for g in groups.values())
        raise DslError(
            f"文件内 card_ids 归一化 text_raw 不一致（{len(distinct)} 个文本等价类："
            f"{detail}）——（卡名+文本）等价类须严格拆分")
    illegal = [f"{cid}（{marks[cid]} 标）" for cid in doc.card.card_ids
               if cid not in legal_ids]
    if illegal:
        raise DslError(
            f"印刷不在最新 standard 合法性快照 {snapshot_id}（退环境/未收录）："
            + "、".join(illegal))


def _cmd_dsl_check(args: argparse.Namespace) -> int:
    """LLM harness 闸 1（task 024）：DSL 文件 schema + 词表校验；
    --db 追加装配校验（task 026：card_id 存在 / 文本等价类一致 / 赛制合法）。"""
    from battlefrontier.dsl.loader import DslError, load_card_doc

    db = None
    legal_ids: frozenset = frozenset()
    snapshot_id = ""
    if args.db:
        from ptcgdb.sdk import open_db

        db = open_db(args.db)
        try:
            snapshots = db.snapshots("standard")
            if not snapshots:
                print(f"错误：{args.db} 无 standard 合法性快照")
                return 1
            latest = snapshots[-1]
            snapshot_id = latest.snapshot_id
            legal_ids = db.legal_at(latest.effective_from, "standard").card_ids
        except Exception:
            db.close()
            raise

    failed = 0
    try:
        for file in args.files:
            try:
                doc = load_card_doc(file)
                if db is not None:
                    _check_doc_against_db(doc, db, legal_ids, snapshot_id)
            except (DslError, OSError) as e:
                failed += 1
                print(f"[FAIL] {file}: {e}")
            else:
                print(f"[OK] {file}（{doc.card.name_group}，{len(doc.effects)} 个效果）")
    finally:
        if db is not None:
            db.close()
    return 1 if failed else 0


def _cmd_report(args: argparse.Namespace) -> int:
    from battlefrontier.report.winrate import format_report, winrate_report

    db = ResultsDB(args.results)
    try:
        try:
            report = winrate_report(db, args.experiment_id)
        except ValueError as e:
            print(f"错误：{e}")
            return 1
        print(format_report(report))
        if args.decisions:
            from battlefrontier.report.decisions import (
                decision_report,
                format_decisions,
            )

            print(format_decisions(decision_report(db, args.experiment_id)))
    finally:
        db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bfsim")
    sub = parser.add_subparsers(dest="cmd")
    run_p = sub.add_parser("run", help="按实验定义 YAML 跑实验并落结果库")
    run_p.add_argument("experiment", help="实验定义 YAML 路径")
    run_p.add_argument("--workers", type=int, default=1, help="多进程 worker 数（默认串行）")
    run_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    run_p.add_argument("--db", default=None,
                       help="ptcg-cn.db 路径（缺省读 config/battlefrontier.local.yml）")
    run_p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR, help="DSL 定义库目录")
    rep_p = sub.add_parser("report", help="胜率报告（Wilson 95%% CI + 先后手拆分）")
    rep_p.add_argument("experiment_id", type=int, help="实验 id")
    rep_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    rep_p.add_argument("--decisions", action="store_true", help="追加决策聚合分节")
    sen_p = sub.add_parser("sensitivity",
                           help="换卡敏感性：baseline vs variants 并排 ΔWR + 显著性检验")
    sen_p.add_argument("base_id", type=int, help="baseline 实验 id")
    sen_p.add_argument("variant_ids", type=int, nargs="+", help="variant 实验 id 列表")
    sen_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    chk_p = sub.add_parser("dsl-check", help="DSL 文件校验（schema + 词表；LLM harness 闸 1）")
    chk_p.add_argument("files", nargs="+", help="DSL YAML 路径（可多个）")
    chk_p.add_argument("--db", default=None,
                       help="ptcg-cn.db 路径：追加装配校验（card_id 存在性 / "
                            "文本等价类一致 / 最新 standard 赛制合法，task 026）")
    args = parser.parse_args(argv)

    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "report":
        return _cmd_report(args)
    if args.cmd == "sensitivity":
        return _cmd_sensitivity(args)
    if args.cmd == "dsl-check":
        return _cmd_dsl_check(args)
    print(f"battlefrontier {__import__('battlefrontier').__version__}："
          f"子命令 run 可用（实验定义见 experiments/），其余随里程碑添加")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
