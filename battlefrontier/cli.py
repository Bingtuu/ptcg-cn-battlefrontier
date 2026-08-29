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


def _cmd_run(args: argparse.Namespace) -> int:
    exp_path = Path(args.experiment)
    defn = load_experiment(exp_path)
    definition_yaml = exp_path.read_text(encoding="utf-8")
    db_path = args.db or load_db_path()
    prep = prepare_experiment(defn, db_path, cards_dir=args.cards_dir)
    for w in prep.warnings:
        print(f"[装载告警] {w}")
    exp_id = execute_experiment(prep, defn, args.results, workers=args.workers,
                                definition_yaml=definition_yaml)

    db = ResultsDB(args.results)
    try:
        games = db.games(exp_id)
    finally:
        db.close()
    wins_a = sum(1 for g in games if g["winner"] == 0)
    wins_b = sum(1 for g in games if g["winner"] == 1)
    draws = sum(1 for g in games if g["is_draw"])
    failed = sum(1 for g in games if g["error"])
    print(f"实验 #{exp_id}「{defn.name}」完成：{len(games)} 局 "
          f"A胜 {wins_a} / B胜 {wins_b} / 平 {draws} / 失败 {failed}"
          f"（结果库 {args.results}）")
    print(f"数据版本 {prep.data_version}；种子区间 {defn.seed_start}.."
          f"{defn.seed_start + defn.games - 1}")
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
    args = parser.parse_args(argv)

    if args.cmd == "run":
        return _cmd_run(args)
    print(f"battlefrontier {__import__('battlefrontier').__version__}："
          f"子命令 run 可用（实验定义见 experiments/），其余随里程碑添加")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
