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
    if defn.matrix is not None:
        from battlefrontier.runner.experiment import run_matrix

        ids, warnings = run_matrix(defn, db_path, args.results, workers=args.workers,
                                   cards_dir=args.cards_dir,
                                   definition_yaml=definition_yaml)
        for w in warnings:
            print(f"[装载告警] {w}")
        db = ResultsDB(args.results)
        try:
            for exp_id in ids:
                print(_summarize(db, exp_id, db.experiment(exp_id)["name"], defn))
        finally:
            db.close()
        print(f"矩阵完成：{len(ids)} 个配对（结果库 {args.results}）；"
              f"偏差表用 bfsim calibration {args.experiment} --results {args.results}")
        return 0
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


def _cmd_calibration(args: argparse.Namespace) -> int:
    """M6 偏差表（task 030 WP3）：matrix 实验定义 → 结果库子实验 vs 真实赛事 matchup。"""
    from ptcgdb.sdk import open_db

    from battlefrontier.data.pool import load_target_pool
    from battlefrontier.report.calibration import (
        REAL_AS_OF,
        REAL_BASIS,
        REAL_DATE_FROM,
        REAL_DATE_TO,
        REAL_MIN_N,
        calibration_report,
        format_calibration,
    )

    defn = load_experiment(args.experiment)
    if defn.matrix is None:
        print("错误：calibration 需要 matrix 模式实验定义")
        return 1
    pool = load_target_pool(defn.matrix.pool)
    sdk = open_db(args.db or load_db_path())
    try:
        real = sdk.stats_matchup(date_from=REAL_DATE_FROM, date_to=REAL_DATE_TO,
                                 as_of=REAL_AS_OF, basis=REAL_BASIS,
                                 division="master", min_n=REAL_MIN_N)
    finally:
        sdk.close()
    db = ResultsDB(args.results)
    try:
        rep = calibration_report(db, defn, pool, real.data, dict(real.meta))
    finally:
        db.close()
    print(format_calibration(rep))
    return 0


def _check_doc_against_db(doc, db, legal_ids: frozenset, snapshot_id: str) -> None:
    """闸 1 装配校验（task 026 WP0，--db 时启用）；失败抛 DslError 列明原因。

    ① card_ids 非空（挂载键必填）且全部存在于 db；② 文件内所有 card_ids 的
    归一化 text_raw（去全部空白）完全一致（不一致列出分歧 card_id 分组）；
    ③ 每个 card_id 在最新 standard 合法性快照（LegalityPool，含再录合法）内；
    ④ on_attack 效果的 attack 绑定名 ∈ 卡面招式名集合 ∪ 本文件 grant_attack
    声明授予的招式名（task 038，D-038-3②：打错招式名不再静默退化为白板）。
    """
    from battlefrontier.dsl.loader import DslError

    if not doc.card.card_ids:
        raise DslError("card_ids 为空——挂载键必填（装载键 = card_id 精确挂载）")
    texts: dict[str, str] = {}
    marks: dict[str, str] = {}
    attack_names: set[str] = set()
    for cid in doc.card.card_ids:
        card = db.get_card(cid)
        if card is None:
            raise DslError(f"未知 card_id '{cid}'（db 无此印刷）")
        texts[cid] = "".join(card.text_raw.split())
        marks[cid] = card.regulation_mark
        attack_names.update(a.name for a in (card.attacks or ()))
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
    # 本文件 grant_attack 声明授予的招式名同样合法（招式学习器「进化/退化」：
    # 道具卡面无招式，招式由 DSL 声明授予持有宝可梦）
    granted = {
        node.args["attack"]
        for eff in doc.effects for node in (*eff.cost, *eff.actions)
        if node.action == "grant_attack" and node.args.get("attack")
    }
    for effect in doc.effects:
        if (
            effect.trigger == "on_attack" and effect.attack is not None
            and effect.attack not in attack_names | granted
        ):
            raise DslError(
                f"on_attack 招式绑定 '{effect.attack}' 不在卡面招式集合"
                f" {sorted(attack_names)}（打错不猜——绑定落空会静默退化为白板；"
                f"grant_attack 授予招式须与本文件声明一致 {sorted(granted) or '（无）'}）"
            )


def _cmd_tune(args: argparse.Namespace) -> int:
    """启发式参数自调优（task 045，D-T1~T4）：坐标下降 + 轨迹 JSONL（不落结果库）。"""
    from battlefrontier.tune import load_tune, run_tune

    defn_path = Path(args.definition)
    defn = load_tune(defn_path)
    db_path = args.db or load_db_path()
    output = args.output or f"results/tune-{defn.name}.jsonl"
    result, split = run_tune(defn, db_path, workers=args.workers,
                             cards_dir=args.cards_dir, output_path=output,
                             progress=print)
    print(f"调优「{defn.name}」完成：训练 {len(split.train)} 对 / "
          f"holdout {len(split.holdout)} 对 × {defn.games_per_pair} 局")
    print(f"基线 fitness {result.baseline_fitness:.4f} → 最优 {result.best_fitness:.4f}"
          f"（Δ {result.best_fitness - result.baseline_fitness:+.4f}，"
          f"{result.rounds_run} 轮 / {result.n_evaluations} 次评估，{result.stop_reason}）")
    adopted = [(t.dim, t.value) for t in result.trials if t.adopted]
    print(f"采纳: {adopted if adopted else '（无——默认参数即局部最优）'}")
    print(f"轨迹: {output}")
    return 0


def _cmd_tune_verify(args: argparse.Namespace) -> int:
    """top-3 复评 + 双门槛 holdout 验证 + 敏感性报告（task 046，D-046-1/2/4）。

    轨迹 JSONL 重建搜索（不新增 summary 文件）→ top-3 候选在训练+holdout 各
    复评 games 局/对（CRN 种子派生不变）→ 双门槛裁决 → 结果 JSON 落盘。
    """
    import json

    from battlefrontier.data.pool import load_target_pool
    from battlefrontier.tune import load_tune
    from battlefrontier.tune.fitness import prepare_pairs, select_pairs, split_pairs
    from battlefrontier.tune.trajectory import read_trajectory
    from battlefrontier.tune.verify import (
        format_verify,
        run_verify,
        verify_projection,
    )

    defn = load_tune(Path(args.definition))
    db_path = args.db or load_db_path()
    trajectory = args.trajectory or f"results/tune-{defn.name}.jsonl"
    output = args.output or f"results/tune-{defn.name}-verify.json"
    try:
        rows = read_trajectory(trajectory)
        pool = load_target_pool(defn.pool)
        if defn.pairs is not None:
            split = select_pairs(pool, defn.pairs)
        else:
            split = split_pairs(pool, defn.split_seed, defn.holdout_size)
        if not split.holdout:
            raise ValueError(
                "holdout 配对集为空（不猜）：pairs 显式子集模式无 holdout，"
                "D-046-1 双门槛验证需要划分出 holdout——请用全量划分的调优定义重跑")
        prepared_all = prepare_pairs([*split.train, *split.holdout], db_path,
                                     args.cards_dir)
        train_idx = {p.index for p in split.train}
        train_prepared = [p for p in prepared_all if p.assignment.index in train_idx]
        holdout_prepared = [p for p in prepared_all
                            if p.assignment.index not in train_idx]
        result = run_verify(rows=rows, noise_threshold=defn.noise_threshold,
                            train_prepared=train_prepared,
                            holdout_prepared=holdout_prepared,
                            games=args.games, workers=args.workers, progress=print)
    except (ValueError, OSError) as e:
        print(f"错误：{e}")
        return 1
    print(f"调优「{defn.name}」：训练 {len(split.train)} 对 / holdout "
          f"{len(split.holdout)} 对 × 复评 {args.games} 局/对"
          f"（轨迹 {trajectory}，{len(rows)} 次评估）")
    print(format_verify(result, name=defn.name))
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(verify_projection(result, name=defn.name,
                                     split_seed=defn.split_seed),
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"结果 JSON: {output}")
    return 0


def _cmd_dsl_check(args: argparse.Namespace) -> int:
    """LLM harness 闸 1（task 024）：DSL 文件 schema + 词表校验；
    --db 追加装配校验（task 026：card_id 存在 / 文本等价类一致 / 赛制合法；
    task 038：on_attack 招式绑定名命中卡面招式）。"""
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
        if args.mcts_consider:
            from battlefrontier.report.mcts_analysis import (
                format_mcts_report,
                mcts_report,
            )

            print(format_mcts_report(mcts_report(db, args.experiment_id)))
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
    rep_p.add_argument("--mcts-consider", action="store_true",
                       help="追加 MCTS 决策分析分节（task 042：访问份额/高熵决策点/分桶胜率）")
    sen_p = sub.add_parser("sensitivity",
                           help="换卡敏感性：baseline vs variants 并排 ΔWR + 显著性检验")
    sen_p.add_argument("base_id", type=int, help="baseline 实验 id")
    sen_p.add_argument("variant_ids", type=int, nargs="+", help="variant 实验 id 列表")
    sen_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    cal_p = sub.add_parser("calibration",
                           help="M6 偏差表：模拟矩阵 vs 真实赛事 matchup（task 030）")
    cal_p.add_argument("experiment", help="matrix 实验定义 YAML 路径")
    cal_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    cal_p.add_argument("--db", default=None, help="ptcg-cn.db 路径（缺省读本机配置）")
    chk_p = sub.add_parser("dsl-check", help="DSL 文件校验（schema + 词表；LLM harness 闸 1）")
    chk_p.add_argument("files", nargs="+", help="DSL YAML 路径（可多个）")
    chk_p.add_argument("--db", default=None,
                       help="ptcg-cn.db 路径：追加装配校验（card_id 存在性 / "
                            "文本等价类一致 / 最新 standard 赛制合法，task 026）")
    tune_p = sub.add_parser("tune", help="启发式参数自调优（task 045：坐标下降 + 轨迹 JSONL）")
    tune_p.add_argument("definition", help="调优定义 YAML 路径")
    tune_p.add_argument("--workers", type=int, default=1, help="多进程 worker 数（默认串行）")
    tune_p.add_argument("--output", default=None,
                        help="轨迹 JSONL 路径（缺省 results/tune-<name>.jsonl）")
    tune_p.add_argument("--db", default=None,
                        help="ptcg-cn.db 路径（缺省读 config/battlefrontier.local.yml）")
    tune_p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR, help="DSL 定义库目录")
    tv_p = sub.add_parser(
        "tune-verify",
        help="top-3 复评 + 双门槛 holdout 验证 + 敏感性报告（task 046，D-046-1/2）")
    tv_p.add_argument("definition", help="调优定义 YAML 路径（与 tune 跑批同一份）")
    tv_p.add_argument("--workers", type=int, default=1, help="多进程 worker 数（默认串行）")
    tv_p.add_argument("--trajectory", default=None,
                      help="轨迹 JSONL 路径（缺省 results/tune-<name>.jsonl）")
    tv_p.add_argument("--games", type=int, default=500,
                      help="复评每配对局数（默认 500，D-046-4）")
    tv_p.add_argument("--db", default=None,
                      help="ptcg-cn.db 路径（缺省读 config/battlefrontier.local.yml）")
    tv_p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR, help="DSL 定义库目录")
    tv_p.add_argument("--output", default=None,
                      help="结果 JSON 路径（缺省 results/tune-<name>-verify.json）")
    args = parser.parse_args(argv)

    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "report":
        return _cmd_report(args)
    if args.cmd == "sensitivity":
        return _cmd_sensitivity(args)
    if args.cmd == "calibration":
        return _cmd_calibration(args)
    if args.cmd == "dsl-check":
        return _cmd_dsl_check(args)
    if args.cmd == "tune":
        return _cmd_tune(args)
    if args.cmd == "tune-verify":
        return _cmd_tune_verify(args)
    print(f"battlefrontier {__import__('battlefrontier').__version__}："
          f"子命令 run 可用（实验定义见 experiments/），其余随里程碑添加")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
