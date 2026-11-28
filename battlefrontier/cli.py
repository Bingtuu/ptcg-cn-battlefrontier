"""CLI 入口（bfsim）：实验 Runner 子命令随里程碑逐个添加（task 019: run）。"""

from __future__ import annotations

import argparse
from pathlib import Path

from battlefrontier.runner.experiment import (
    DEFAULT_CARDS_DIR,
    DEFAULT_RESULTS_PATH,
    _code_version,
    execute_experiment,
    load_db_path,
    load_experiment,
    prepare_experiment,
)
from battlefrontier.runner.results_db import ResultsDB


def _cmd_swap_search(args: argparse.Namespace) -> int:
    """task 130：换卡搜索器（单卡替换扫描 + 筛选→确认两阶段 + 排序输出）。

    方法论设计文档 docs/digs/2026-11-14-deck-swap-search-design.md；
    输出带「自对局先验」限定语头注；零 Agent/DSL/引擎行为变更。
    """
    from battlefrontier.report.swap_search import (
        format_swap_search,
        run_swap_search,
    )

    db_path = args.db or load_db_path()
    stem = (f"swap-search-{args.deck.split(':')[-1]}"
            f"-vs-{args.vs_deck.split(':')[-1]}")
    results = args.results or str(Path("results") / f"{stem}.db")
    try:
        rep = run_swap_search(
            deck_id=args.deck, vs_id=args.vs_deck, budget=args.budget,
            db_path=db_path, results_path=results,
            seed_start=args.seed_start, confirm_top=args.confirm_top,
            screen_games=args.screen_games, confirm_games=args.confirm_games,
            top_n=args.top_n, include=tuple(args.include),
            workers=args.workers, cards_dir=args.cards_dir)
    except ValueError as e:
        print(f"[swap-search 失败] {e}")
        return 1
    print(format_swap_search(rep))
    return 0


def _cmd_check_deck(args: argparse.Namespace) -> int:
    """task 119：卡表预检（跑前体检，零跑批）。错误打印并退出码 1。"""
    from battlefrontier.runner.deck_check import check_decklist, format_deck_check

    db_path = args.db or load_db_path()
    try:
        rep = check_decklist(db_path, args.decklist, cards_dir=args.cards_dir)
    except (ValueError, OSError) as e:
        print(f"[预检失败] {e}")
        return 1
    print(format_deck_check(rep))
    return 0


def _cmd_probe_throughput(args: argparse.Namespace) -> int:
    """task 149：吞吐决策点 spike 探针（BC 训练最低需求 vs R2 实测产能）。

    默认 stub 卡组零 db 冒烟；--deck-id 走真实装配（真实卡表口径）。
    判定门槛预注册冻结（task 149 设计段）。
    """
    import tempfile

    from battlefrontier.runner.throughput import (
        BC_REQUIREMENT,
        decide_r2,
        format_probe,
        probe_throughput,
        stub_prep,
    )

    if args.deck_id:
        from battlefrontier.runner.experiment import prepare_experiment
        from battlefrontier.runner.throughput import probe_defn as _probe_defn
        defn = _probe_defn(args.agent, games=args.games, seed_start=args.seed_start,
                           policy_path=args.policy, deck_id=args.deck_id)
        prep = prepare_experiment(defn, args.db or load_db_path())
    else:
        prep = stub_prep()
    with tempfile.TemporaryDirectory() as td:
        try:
            result = probe_throughput(
                args.agent, games=args.games, workers=args.workers,
                seed_start=args.seed_start, prep=prep,
                results_path=Path(td) / "probe.db", policy_path=args.policy)
        except ValueError as e:
            print(f"[probe 失败] {e}")
            return 1
    decision = decide_r2(result, BC_REQUIREMENT)
    print(format_probe(result, decision))
    if args.net_forward and args.policy:
        from battlefrontier.runner.throughput import net_forward_probe
        print(net_forward_probe(args.policy, n=args.net_forward))
    return 0


def _cmd_league(args: argparse.Namespace) -> int:
    """task 127：agent 种群联赛（BC 路线评估面前置）。

    跑+报一体：`bfsim league <registry.yml> --results db [--workers N]`；
    纯报告：`bfsim league --report <league名> --results db`。
    评级主估计子 BT-MLE（task 148 教训：禁固定大步长顺序 Elo）。
    """
    from battlefrontier.report.league import league_report
    from battlefrontier.runner.league import load_league, run_league

    if args.report:
        rep = league_report(args.results, args.report)
        print(rep.format_text())
        return 0
    if not args.registry:
        print("[league 失败] 缺注册表路径（或改用 --report <league名> 纯报告模式）")
        return 1
    lg = load_league(args.registry)
    db_path = args.db or load_db_path()
    try:
        run_league(lg, db_path, args.results, workers=args.workers,
                   cards_dir=args.cards_dir, registry_path=args.registry)
        rep = league_report(args.results, lg.name)
    except (ValueError, OSError) as e:
        print(f"[league 失败] {e}")
        return 1
    print(rep.format_text())
    return 0


def _cmd_field_pick(args: argparse.Namespace) -> int:
    """task 123：metamages 式选卡器（四期 PRD M14）。

    field 快照（CN 使用率）× matchup 三层矩阵（intl 真实 / sim 同口径 / 缺格
    占位）→ 期望胜率排序 + 蒙特卡洛排序稳定性。全程限定语头注。
    task 125：intl 格装配下沉共享函数；--matrix-snap 直接读快照格。
    """
    import json as _json

    from battlefrontier.data.pool import load_target_pool
    from battlefrontier.report.field_pick import (
        adapt_field_share,
        assemble_matrix,
        field_pick,
        format_field_pick,
        intl_cells_from_db,
        load_field_snapshot,
        load_matrix_snapshot,
        pool_name_maps,
        sim_cells_from_pack,
        window_gap_days,
    )

    pool = load_target_pool(args.pool)
    cn_to_en, en_names = pool_name_maps(pool)
    share_raw, snap_meta = load_field_snapshot(args.field)
    share = adapt_field_share(share_raw, cn_to_en)

    if args.matrix_snap and (args.intl_db or args.sim_pack):
        print("[输入冲突] --matrix-snap 与 --intl-db/--sim-pack 互斥"
              "（快照格即最终矩阵，不二次装配）")
        return 1

    intl_cells = []
    intl_meta: dict = {}
    if args.matrix_snap:
        snap_cells, snap_cells_meta = load_matrix_snapshot(args.matrix_snap)
        # 快照格走 sim 层入矩阵：收缩/成对一致/缺格占位导出时已定稿，
        # assemble_matrix 对 sim 层不二次收缩
        matrix = assemble_matrix([], snap_cells, en_names)
        intl_meta = {"date_from": snap_cells_meta.get("date_from"),
                     "date_to": snap_cells_meta.get("date_to")}
    else:
        if args.intl_db:
            intl_cells = intl_cells_from_db(args.intl_db, en_names,
                                            args.from_date, args.to_date)
            intl_meta = {"date_from": args.from_date,
                         "date_to": args.to_date}
        sim_cells = []
        if args.sim_pack:
            pack = _json.loads(Path(args.sim_pack).read_text(encoding="utf-8"))
            sim_cells = sim_cells_from_pack(pack.get("cells", []), cn_to_en)
        matrix = assemble_matrix(intl_cells, sim_cells, en_names)

    rep = field_pick(share, matrix, en_names, n_sim=args.n_sim, seed=args.seed)
    gap = window_gap_days(snap_meta, intl_meta) if intl_meta else None
    if gap is not None and gap > 28:
        print(f"[告警] field 快照与 intl matchup 窗口错位 {gap} 天（>28），"
              "meta 漂移可能使排序失真——建议对齐窗口或下调结论强度")
    print(format_field_pick(rep))
    return 0


def _cmd_matchup_snap(args: argparse.Namespace) -> int:
    """task 125：导出 field-pick 可读的 matchup 矩阵快照 JSON（M14 gate 操作包）。

    intl 真实格（n 门槛收缩 + low_confidence 标注）+ 窗口时点元数据 +
    限定语头注；格值与 assemble_matrix 逐格一致（共享装配函数）。
    """
    import json as _json

    from battlefrontier.data.pool import load_target_pool
    from battlefrontier.report.field_pick import (
        QUALIFIER_HEADER,
        export_matchup_snapshot,
        intl_cells_from_db,
        pool_name_maps,
        sim_cells_from_pack,
    )

    pool = load_target_pool(args.pool)
    cn_to_en, en_names = pool_name_maps(pool)
    intl_cells = intl_cells_from_db(args.intl_db, en_names,
                                    args.from_date, args.to_date)
    sim_cells = []
    if args.sim_pack:
        pack = _json.loads(Path(args.sim_pack).read_text(encoding="utf-8"))
        sim_cells = sim_cells_from_pack(pack.get("cells", []), cn_to_en)
    snap = export_matchup_snapshot(
        intl_cells, sim_cells, en_names,
        {"date_from": args.from_date, "date_to": args.to_date,
         "basis": "intl_aligned", "division": "master",
         "data_version": pool.version, "qualifier": QUALIFIER_HEADER})
    Path(args.out).write_text(
        _json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    n_low = sum(1 for c in snap["cells"] if c["low_confidence"])
    print(f"快照 {args.out}：{len(snap['cells'])} 格"
          f"（intl {len(intl_cells)} 对主格 / sim {len(sim_cells)} 格 / "
          f"low_confidence {n_low} 格）；窗口 {args.from_date}..{args.to_date}")
    return 0


def _summarize(db: ResultsDB, exp_id: int, label: str, defn) -> str:
    games = db.games(exp_id)
    wins_a = sum(1 for g in games if g["winner"] == 0)
    wins_b = sum(1 for g in games if g["winner"] == 1)
    draws = sum(1 for g in games if g["is_draw"])
    failed = sum(1 for g in games if g["error"])
    return (f"实验 #{exp_id}「{label}」完成：{len(games)} 局 "
            f"A胜 {wins_a} / B胜 {wins_b} / 平 {draws} / 失败 {failed}")


def _cmd_field_snap(args: argparse.Namespace) -> int:
    """task 156：场快照导出 + 就绪探针。

    导出：--from/--to/--out 必给（上游 stats_usage 钉口径，见 runner/field_snap）。
    探针（--probe）：上游最新合格赛事日期 vs --snap 窗口终点；退出码 0 = 新鲜，
    3 = 有新数据或无基线（建议刷新/建档）——刻意区别于通用错误码 1。
    """
    from battlefrontier.runner.field_snap import (
        export_field_snap,
        probe_field_freshness,
    )

    db_path = args.db or load_db_path()
    if args.probe:
        status, detail = probe_field_freshness(db_path, args.snap)
        print(f"[{status}] {detail}")
        return 0 if status == "fresh" else 3
    if not (args.from_date and args.to_date and args.out):
        print("[field-snap 失败] 导出模式需要 --from/--to/--out（或改用 --probe）")
        return 1
    snap = export_field_snap(db_path, args.from_date, args.to_date, args.out)
    print(f"快照 {args.out}：{len(snap['data'])} 行，窗 "
          f"{args.from_date}..{args.to_date}，as_of {snap['meta'].get('as_of')}")
    return 0


def _cmd_mod_check(args: argparse.Namespace) -> int:
    """task 156：改表成对判读（同种子 CRN 配对，纪律见 report/mod_check）。

    task 157：--batch 批次模式（prep 登记的实验 ID + 完整性第四门）；
    --base-prefix/--mod-prefix 前缀模式保留（非批次模式，仅一次性干净库）。
    """
    from battlefrontier.report.mod_check import format_mod_check, mod_check_report

    try:
        rep = mod_check_report(args.results, base_prefix=args.base_prefix,
                               mod_prefix=args.mod_prefix, batch=args.batch,
                               field_path=args.field,
                               pool_path=args.pool, entry=args.entry,
                               alpha=args.alpha, family_size=args.family_size)
    except (ValueError, OSError) as e:
        print(f"[mod-check 失败] {e}")
        return 1
    print(format_mod_check(rep, alpha=args.alpha))
    return 0


def _cmd_prep(args: argparse.Namespace) -> int:
    """task 156：备赛编排器——场刷新 → field-pick → 成对核对 → 统一报告。"""
    from battlefrontier.runner.prep import load_prep_cfg, run_prep

    try:
        cfg = load_prep_cfg(args.prep)
    except (ValueError, TypeError, OSError) as e:
        print(f"[prep 失败] {e}")
        return 1
    db_path = args.db or load_db_path()
    results = args.results or str(Path("results") / f"prep-{cfg.name}.db")
    strict = False if args.no_strict_coverage else None
    try:
        report_path = run_prep(cfg, db_path=db_path, results_path=results,
                               field_out=args.field_out, out_dir=args.out_dir,
                               workers=args.workers, pick_only=args.pick_only,
                               strict_coverage=strict,
                               prep_source=args.prep)
    except (ValueError, OSError) as e:
        print(f"[prep 失败] {e}")
        return 1
    print(f"备赛报告落盘：{report_path}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from battlefrontier.runner.coverage import (
        format_coverage,
        run_coverages,
        strict_violations,
    )
    from battlefrontier.runner.experiment import run_group

    exp_path = Path(args.experiment)
    defn = load_experiment(exp_path)
    definition_yaml = exp_path.read_text(encoding="utf-8")
    db_path = args.db or load_db_path()

    # task 131：跑前 DSL 覆盖率报告 + strict 门槛（装载后、开跑前；strict 拒绝 = 零局跑批）
    covers = run_coverages(defn, db_path, cards_dir=args.cards_dir)
    print(format_coverage(covers))
    violations = strict_violations(covers)
    if args.strict_coverage:
        if violations:
            for v in violations:
                print(f"[strict-coverage] {v}")
            print("[strict-coverage] 存在无文档非基本能量卡，拒绝开跑（零局跑批）")
            return 1
        print("[strict-coverage] 通过：参赛卡组 DSL 全覆盖（基本能量豁免不计）")
    elif violations:
        for v in violations:
            print(f"[覆盖率告警] {v}（按无效果结算，对手强度可能被静默扭曲）")

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


def _cmd_pairings(args: argparse.Namespace) -> int:
    """池内 archetype 的真实逐桌对阵对照（task 073）。只读，不跑模拟。"""
    from battlefrontier.data.pairings import pairing_contrast
    from battlefrontier.data.pool import load_target_pool
    from battlefrontier.report.calibration import (
        REAL_BASIS,
        REAL_DATE_FROM,
        REAL_DATE_TO,
    )
    from battlefrontier.report.pairing_pack import (
        format_pairing_contrast,
        write_pairing_pack,
    )

    pool = load_target_pool(args.pool)
    names = [d.en_archetype for d in pool.decks]
    db_path = args.db or load_db_path()
    try:
        rep = pairing_contrast(
            db_path, names,
            date_from=args.date_from or REAL_DATE_FROM,
            date_to=args.date_to or REAL_DATE_TO,
            basis=args.basis or REAL_BASIS,
            division=args.division,
            sample_limit=args.sample_limit,
        )
    except ValueError as e:
        print(f"错误：{e}")
        return 1
    text = format_pairing_contrast(rep)
    stem = Path(args.pool).stem
    out_dir = Path(args.out) if args.out else Path("results") / f"{stem}-pairings"
    paths = write_pairing_pack(out_dir, rep)
    print(text)
    print("对阵包：" + " ".join(str(p) for p in paths.values()))
    return 0


def _cmd_sensitivity(args: argparse.Namespace) -> int:
    from battlefrontier.report.sensitivity import (
        format_sensitivity,
        sensitivity_report,
    )
    from battlefrontier.report.swap_pack import swap_replays, write_swap_pack

    db = ResultsDB(args.results)
    try:
        try:
            rep = sensitivity_report(db, args.base_id, args.variant_ids)
        except ValueError as e:
            print(f"错误：{e}")
            return 1
        replays = swap_replays(db, rep, args.replay_sample)
        text = format_sensitivity(rep)
        out_dir = (Path(args.out) if args.out
                   else Path("results") / f"sensitivity-{args.base_id}")
        paths = write_swap_pack(out_dir, rep, replays)
        print(text)
        print("换卡包：" + " ".join(str(p) for p in paths.values()))
    finally:
        db.close()
    return 0


def _cmd_calibration_split(args: argparse.Namespace, defn, pool) -> int:
    """M13：显式赛事切分；真实侧只读 raw 对阵，复用同一校准报告。"""
    from dataclasses import replace

    import yaml

    from battlefrontier.data.pairings import pairing_contrast
    from battlefrontier.data.validation import tournament_time_split
    from battlefrontier.report.calibration import (
        REAL_MIN_N,
        calibration_report,
        format_calibration,
    )
    from battlefrontier.report.deviation_pack import write_deviation_pack
    from battlefrontier.report.validation import write_validation_manifest

    protocol_path = Path(args.validation_protocol or "config/m13-validation-v1.yml")
    real_db_path = args.db or load_db_path()
    try:
        protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
        if protocol.get("method") != args.tournament_split:
            raise ValueError("协议 method 与 --tournament-split 不一致")
        if float(protocol["development_fraction"]) != 0.7:
            raise ValueError("time-70-30 协议 development_fraction 必须为 0.7")
        real = protocol["real"]
        split = tournament_time_split(
            real_db_path,
            date_from=real["date_from"], date_to=real["date_to"],
            basis=real["basis"], division=real.get("division", "master"),
            development_fraction=float(protocol["development_fraction"]),
        )
        for key in (
            "tournament_count", "development_count", "validation_count",
            "development_last", "validation_first",
        ):
            if split.meta[key] != protocol[key]:
                raise ValueError(
                    f"协议{key}={protocol[key]!r} 与实际 {split.meta[key]!r} 不一致"
                )
        contrasts = {
            "full": pairing_contrast(
                real_db_path, [d.en_archetype for d in pool.decks],
                date_from=real["date_from"], date_to=real["date_to"],
                basis=real["basis"], division=real.get("division", "master"),
                sample_limit=0,
            ),
            "development": pairing_contrast(
                real_db_path, [d.en_archetype for d in pool.decks],
                date_from=real["date_from"], date_to=real["date_to"],
                basis=real["basis"], division=real.get("division", "master"),
                sample_limit=0, tournament_ids=split.development_ids,
            ),
            "validation": pairing_contrast(
                real_db_path, [d.en_archetype for d in pool.decks],
                date_from=real["date_from"], date_to=real["date_to"],
                basis=real["basis"], division=real.get("division", "master"),
                sample_limit=0, tournament_ids=split.validation_ids,
            ),
        }
        reports = {}
        db = ResultsDB(args.results)
        try:
            for name, contrast in contrasts.items():
                real_meta = {
                    "date_from": real["date_from"], "date_to": real["date_to"],
                    "basis": real["basis"], "division": real.get("division", "master"),
                    "min_n": REAL_MIN_N, "n_tournaments": (
                        split.meta["tournament_count"] if name == "full"
                        else split.meta[f"{name}_count"]
                    ),
                    "n_games_used": sum(c.n for c in contrast.cells) // 2,
                    "scope": "pool_raw_pairings",
                }
                rep = calibration_report(db, defn, pool, list(contrast.cells), real_meta)
                reports[name] = replace(rep, meta={
                    **rep.meta,
                    "validation_split": args.tournament_split,
                    "validation_limitation": protocol.get(
                        "validation_limitation",
                        "真实全量聚合此前已查看；此划分仅从 M13 起冻结为前瞻验证，"
                        "并非绝对未见 holdout。",
                    ),
                })
        finally:
            db.close()
    except (KeyError, TypeError, ValueError, OSError) as e:
        print(f"错误：赛事切分协议或数据无效：{e}")
        return 1

    out_dir = Path(args.out) if args.out else Path("results") / f"{defn.name}-validation"
    paths = []
    report_paths = {}
    for name, rep in reports.items():
        written = write_deviation_pack(out_dir / name, rep)
        report_paths[name] = written
        paths.extend(written.values())
    manifest = write_validation_manifest(
        out_dir,
        protocol={
            **protocol,
            "actual_split": split.meta,
            "report_code_version": _code_version(),
        },
        reports=reports,
        artifacts={
            "experiment": args.experiment,
            "results": args.results,
            "real_db": real_db_path,
        },
        report_paths=report_paths,
    )
    print(format_calibration(reports["full"]))
    print("偏差包：" + " ".join(str(p) for p in [*paths, manifest]))
    return 0


def _cmd_calibration(args: argparse.Namespace) -> int:
    """M6 偏差表（task 030 WP3）：matrix 实验定义 → 结果库子实验 vs 真实赛事 matchup。"""
    from battlefrontier.data.backend import open_backend
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
    from battlefrontier.report.deviation_pack import write_deviation_pack

    defn = load_experiment(args.experiment)
    if defn.matrix is None:
        print("错误：calibration 需要 matrix 模式实验定义")
        return 1
    pool = load_target_pool(defn.matrix.pool)
    if args.tournament_split:
        return _cmd_calibration_split(args, defn, pool)
    sdk = open_backend(args.db or load_db_path())
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
    text = format_calibration(rep)
    out_dir = Path(args.out) if args.out else Path("results") / f"{defn.name}-deviation"
    paths = write_deviation_pack(out_dir, rep)
    print(text)
    print("偏差包：" + " ".join(str(p) for p in paths.values()))
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


def _cmd_collect_features(args: argparse.Namespace) -> int:
    """M11 数据产线（task 050 WP1，D-M11-1）：卡池全部配对 × 种子区间采集特征 JSONL。

    落 <out>/pair-<index>-<名A>x<名B>.jsonl（不落结果库，D-T4 先例）；
    失败局剔除并计数上报。正式跑批口径：36 对 × 2800 局 @seed-start 300000。
    task 155 WP2：--feature-set v3 走紧凑格式（文件首行 header 钉 feature_names、
    数据行 features 为位置 list）；词表 = build_card_vocab(pool, db)（CLI 侧算好
    透传，多进程确定性），词表长 + 首末词随 meta 打印落账；v3 必须显式 --db。
    """
    from battlefrontier.runner.collect import run_collect_pool

    card_vocab: tuple[str, ...] | None = None
    if args.feature_set == "v3":
        if args.db is None:
            print("错误：--feature-set v3 必须显式提供 --db（词表构建需要，不猜）")
            return 1
        from battlefrontier.agent.policy_features import build_card_vocab

        card_vocab = build_card_vocab(args.pool, str(args.db))
        print(f"特征集 v3：词表 {len(card_vocab)} 词"
              f"（首 {card_vocab[0]!r} / 末 {card_vocab[-1]!r}）")
    db_path = args.db or load_db_path()
    summaries, warnings = run_collect_pool(
        args.pool, db_path, games_per_pair=args.games_per_pair,
        seed_start=args.seed_start, out_dir=args.out,
        workers=args.workers, cards_dir=args.cards_dir,
        feature_set=args.feature_set, card_vocab=card_vocab)
    for w in warnings:
        print(f"[装载告警] {w}")
    total_rows = sum(s.rows for s in summaries)
    total_failed = sum(s.failed for s in summaries)
    for s in summaries:
        print(f"[{s.pair_index:2d}] {s.archetype_a}×{s.archetype_b}：{s.filename} — "
              f"{s.games} 局 / {s.rows} 行 / 失败剔除 {s.failed}")
    print(f"采集完成：{len(summaries)} 个配对 × {args.games_per_pair} 局，"
          f"共 {total_rows} 行，失败剔除 {total_failed} 局"
          f"（feature_set {args.feature_set}，目录 {args.out}）")
    return 0


def _cmd_train_eval(args: argparse.Namespace) -> int:
    """M11 WP2（task 051，D-M11-3）：collect-features 产物 → 岭回归闭式解训练 → 模型资产 JSON。

    死维度警戒（设计文档 §5）：验证集 MSE 不优于常数基线 → 退出码 2（模型照常产出，
    如实落账不强行失败）；数据错误 → 退出码 1。
    task 155 WP3：--feature-set v3 分派 learn.train_v3（分块两遍流式，λ 候选六档）；
    缺省 v1 现状逐位不变。互斥校验（不猜）：v1 拒绝 v3 数据、v3 拒绝 v1 数据，
    均显式 ValueError → 退出码 1。
    """
    if args.feature_set == "v3":
        return _cmd_train_eval_v3(args)
    from battlefrontier.learn import (
        DEFAULT_SPLIT_SEED,
        DEFAULT_SUBSAMPLE_SEED,
        load_dataset,
        save_model,
        train_model,
    )

    try:
        rows = load_dataset(args.data)
        model = train_model(
            rows,
            split_seed=args.split_seed if args.split_seed is not None
            else DEFAULT_SPLIT_SEED,
            code_version=args.code_version or _code_version(),
            pool=args.pool,
            max_rows_per_game=args.max_rows_per_game,
            subsample_seed=args.subsample_seed if args.subsample_seed is not None
            else DEFAULT_SUBSAMPLE_SEED)
    except (ValueError, OSError) as e:
        print(f"错误：{e}")
        return 1
    save_model(model, args.out)
    m = model.meta
    sample_note = (f"，按局抽样 ≤{m['max_rows_per_game']} 行（subsample_seed "
                   f"{m['subsample_seed']}）" if m["max_rows_per_game"] is not None
                   else "")
    print(f"训练完成：{m['rows']} 行（总 {m['rows_total']} 行{sample_note}）/ "
          f"{m['games']} 局 / {m['pairs']} 配对"
          f"（种子区间 {m['seed_min']}..{m['seed_max']}，split_seed {m['split_seed']}，"
          f"训练 {m['train_games']} 局 / 验证 {m['val_games']} 局）")
    print(f"λ = {m['lambda']}（候选 {{0.1, 1, 10, 100}} 按验证集 MSE 选定）；"
          f"训练 MSE {m['train_mse']:.6f} / 验证 MSE {m['val_mse']:.6f} / "
          f"常数基线 MSE {m['baseline_mse']:.6f}")
    print(f"模型资产: {args.out}")
    if m["warning"]:
        print(f"[死维度警戒] {m['warning']}")
        return 2
    return 0


def _cmd_train_eval_v3(args: argparse.Namespace) -> int:
    """task 155 WP3：v3 采集产物 → 分块两遍流式岭回归训练 → bf-linear-eval-v3 资产。

    口径与 v1 逐字段对齐（按局划分 / split_seed / 按局抽样 / 死维度警戒），
    λ 候选六档 {0.1, 1, 10, 100, 1000, 10000}（预注册：维数 30→560 改变
    XᵀX 尺度）；退出码同 v1（数据错误 1 / 死维度警戒 2）。
    """
    from battlefrontier.learn import (
        DEFAULT_SPLIT_SEED,
        DEFAULT_SUBSAMPLE_SEED,
        LAMBDAS_V3,
        MODEL_FORMAT_V3,
        save_model,
        train_model_v3,
    )

    try:
        model = train_model_v3(
            args.data,
            split_seed=args.split_seed if args.split_seed is not None
            else DEFAULT_SPLIT_SEED,
            code_version=args.code_version or _code_version(),
            pool=args.pool,
            max_rows_per_game=args.max_rows_per_game,
            subsample_seed=args.subsample_seed if args.subsample_seed is not None
            else DEFAULT_SUBSAMPLE_SEED)
    except (ValueError, OSError) as e:
        print(f"错误：{e}")
        return 1
    save_model(model, args.out, model_format=MODEL_FORMAT_V3)
    m = model.meta
    sample_note = (f"，按局抽样 ≤{m['max_rows_per_game']} 行（subsample_seed "
                   f"{m['subsample_seed']}）" if m["max_rows_per_game"] is not None
                   else "")
    print(f"训练完成（feature_set v3，词表 {len(m['card_vocab'])} 词 / 区 "
          f"{'、'.join(m['zones'])}）：{m['rows']} 行（总 {m['rows_total']} 行"
          f"{sample_note}）/ {m['games']} 局 / {m['pairs']} 配对"
          f"（种子区间 {m['seed_min']}..{m['seed_max']}，split_seed {m['split_seed']}，"
          f"训练 {m['train_games']} 局 / 验证 {m['val_games']} 局）")
    print(f"λ = {m['lambda']}（候选 {set(LAMBDAS_V3)} 按验证集 MSE 选定，并列取小 λ）；"
          f"训练 MSE {m['train_mse']:.6f} / 验证 MSE {m['val_mse']:.6f} / "
          f"常数基线 MSE {m['baseline_mse']:.6f}")
    print(f"模型资产: {args.out}")
    if m["warning"]:
        print(f"[死维度警戒] {m['warning']}")
        return 2
    return 0


def _cmd_train_policy(args: argparse.Namespace) -> int:
    """M12 WP2（task 058，D-M12-3/4）：教师快照目录 → MLP 策略打分机蒸馏训练 → 资产 JSON。

    torch dev-only（训练非复算面 D3-4）；缺省超参全钉死写 meta；holdout argmax
    准确率落 meta；数据错误 → 退出码 1。
    task 062 WP2d（D-062-2/4）：提供 --pool 时构建卡身份词表触发 v2 特征训练
    （资产 bf-distilled-policy-v2）；不提供 = v1 旧行为逐位不变。
    task 066 WP1（D-066-1/2/3）：--weight-scheme kind-weights-v1 时按
    learn.sample_weights 出逐样本权重（kind 映射 + ceiling 双投票 join，
    缺票/对不上显式报错）；缺省 none = 现状逐位全等。
    """
    from battlefrontier.learn.policy_data import load_policy_samples
    from battlefrontier.learn.policy_model import save_policy_model
    from battlefrontier.learn.train_policy import (
        DEFAULT_EPOCHS,
        DEFAULT_HIDDEN,
        DEFAULT_LR,
        DEFAULT_SPLIT_SEED,
        train_policy,
    )

    try:
        card_vocab = None
        state_names = None
        action_names = None
        if args.pool is not None:
            from battlefrontier.agent.policy_features import (
                POLICY_STATE_NAMES,
                build_card_vocab,
                policy_action_names,
            )

            card_vocab = build_card_vocab(args.pool, load_db_path())
            state_names = POLICY_STATE_NAMES
            action_names = policy_action_names(card_vocab)
        samples = load_policy_samples(args.data, card_vocab=card_vocab)
        sample_weights = None
        weight_scheme = None
        if args.weight_scheme != "none":
            from battlefrontier.learn.sample_weights import (
                compute_sample_weights,
            )

            sample_weights, weight_scheme = compute_sample_weights(
                args.data, scheme=args.weight_scheme,
                ceiling_dir=args.ceiling_dir)
        model = train_policy(
            samples,
            epochs=args.epochs if args.epochs is not None else DEFAULT_EPOCHS,
            lr=args.lr if args.lr is not None else DEFAULT_LR,
            hidden=args.hidden if args.hidden is not None else DEFAULT_HIDDEN,
            split_seed=args.split_seed if args.split_seed is not None
            else DEFAULT_SPLIT_SEED,
            code_version=args.code_version or _code_version(),
            pool=args.pool,
            state_names=state_names, action_names=action_names,
            card_vocab=card_vocab,
            sample_weights=sample_weights, weight_scheme=weight_scheme)
    except (ValueError, OSError) as e:
        print(f"错误：{e}")
        return 1
    save_policy_model(model, args.out)
    m = model.meta
    print(f"训练完成：{m['rows']} 决策点 / {m['games']} 局 / {m['pairs']} 配对"
          f"（种子区间 {m['seed_min']}..{m['seed_max']}，split_seed {m['split_seed']}，"
          f"训练 {m['train_games']} 局 {m['train_rows']} 点 / holdout "
          f"{m['val_games']} 局 {m['val_rows']} 点）")
    val_acc = (f"{m['val_argmax_accuracy']:.4f}"
               if m["val_argmax_accuracy"] is not None else "N/A")
    print(f"epochs {m['epochs']} / lr {m['lr']} / hidden {m['hidden']}"
          f"（torch {m['torch_version']}）；训练损失 {m['train_loss']:.6f}；"
          f"argmax 准确率 训练 {m['train_argmax_accuracy']:.4f} / holdout {val_acc}")
    if card_vocab is not None:
        print(f"特征版本 v2：卡身份词表 {len(card_vocab)} 张（卡池 {args.pool}）")
    if weight_scheme is not None:
        print(f"样本权重方案 {weight_scheme['name']}（kind 权重 "
              f"{weight_scheme['kind_weights']}；end_turn 双投票不一致 "
              f"×{weight_scheme['end_turn_unstable_weight']}："
              f"{weight_scheme['end_turn_unstable_points']}/"
              f"{weight_scheme['end_turn_points']} 点降权，ceiling "
              f"{weight_scheme['ceiling_dir']}）")
    print(f"模型资产: {args.out}")
    if m["warning"]:
        print(f"[告警] {m['warning']}")
    return 0


def _cmd_collect_snapshots(args: argparse.Namespace) -> int:
    """M11 一致率快照采集（task 052 WP3，D-M11-5）：教师（MCTS）配置跑卡池配对，
    决策点快照（序列化 GameState + 教师结构化 Action）落 <out>/pair-*.jsonl。

    不落结果库（D-T4 先例）；失败局剔除并计数上报。快照是数据资产——评估侧
    （agreement）可换受测配置重放同一份快照。逐对增量落盘（对完成即写，
    中途 kill 只损失未完成对）；--pair-start N 断点续采（跳过前 N 对，
    种子映射不变）。
    """
    from battlefrontier.runner.snapshot import run_collect_snapshots_pool

    if args.pair_start < 0:
        print(f"错误：--pair-start {args.pair_start} 非法（须 ≥ 0，不猜）")
        return 1
    db_path = args.db or load_db_path()
    teacher = {"worlds": args.worlds, "iterations": args.iterations,
               "rollout_turn_cap": args.rollout_turn_cap}
    # task 151 WP1：评估器 / 浅截断键仅在提供时注入（缺省 None = 现状零变化；
    # 与 --mix-population 相互独立，不强制绑定）
    if args.evaluator_path is not None:
        teacher["evaluator_path"] = args.evaluator_path
    if args.eval_cutoff_turns is not None:
        teacher["eval_cutoff_turns"] = args.eval_cutoff_turns
    try:
        summaries, warnings = run_collect_snapshots_pool(
            args.pool, db_path, games_per_pair=args.games_per_pair,
            seed_start=args.seed_start, out_dir=args.out,
            workers=args.workers, cards_dir=args.cards_dir, teacher=teacher,
            pair_start=args.pair_start, mix=args.mix_population)
    except (ValueError, OSError) as e:
        print(f"错误：{e}")
        return 1
    for w in warnings:
        print(f"[装载告警] {w}")
    total_rows = sum(s.rows for s in summaries)
    total_failed = sum(s.failed for s in summaries)
    for s in summaries:
        print(f"[{s.pair_index:2d}] {s.archetype_a}×{s.archetype_b}：{s.filename} — "
              f"{s.games} 局 / {s.rows} 快照 / 失败剔除 {s.failed}")
    print(f"采集完成：{len(summaries)} 个配对 × {args.games_per_pair} 局（教师 "
          f"{args.worlds}×{args.iterations} cap {args.rollout_turn_cap}），"
          f"共 {total_rows} 快照，失败剔除 {total_failed} 局（目录 {args.out}）")
    if args.mix_population:
        print("混编种群：MCTS×Heuristic 按 (seed−对种子起点)%2 交替指派"
              "（行级 agent 标签，header mix=true）")
    return 0


def _cmd_agreement(args: argparse.Namespace) -> int:
    """M11 决策一致率评估（task 052 WP3，D-M11-5）：快照文件 × 受测配置重放比对。

    学生两类：MCTS（--worlds/--iterations 等预算 flags）或 distilled
    （task 059，D-M12-5：--policy 指定 bf-distilled-policy-v1 模型资产）——
    两者互斥，混用显式报错退出码 1（不猜）。
    学生种子按（配置指纹 + 快照序号）确定性派生，钉死进报告；--output 落
    完整 JSON（含逐行明细），缺省只打印摘要。
    """
    import json

    from battlefrontier.runner.agreement import agreement_report, run_agreement_file

    if args.policy is not None:
        # task 059（D-M12-5）：--policy 与 MCTS 预算 flags 互斥（缺省 None 以区分
        # 「未传」与「传了缺省值」，互斥判定零歧义）
        mcts_flags = [flag for flag, value in (
            ("--worlds", args.worlds), ("--iterations", args.iterations),
            ("--rollout-turn-cap", args.rollout_turn_cap),
            ("--eval-cutoff-turns", args.eval_cutoff_turns),
            ("--evaluator", args.evaluator)) if value is not None]
        if mcts_flags:
            print(f"错误：--policy（distilled 学生）与 MCTS 预算 flags 互斥（不猜）："
                  f"{'、'.join(mcts_flags)}")
            return 1
        student = {"type": "distilled", "policy_path": args.policy}
    else:
        if args.worlds is None or args.iterations is None:
            print("错误：MCTS 学生需要 --worlds 与 --iterations"
                  "（distilled 学生改用 --policy 指定模型资产）")
            return 1
        if (args.eval_cutoff_turns or 0) > 0 and args.evaluator is None:
            print("错误：--eval-cutoff-turns > 0 需要 --evaluator 指定评估器资产（不猜）")
            return 1
        student = {"worlds": args.worlds, "iterations": args.iterations,
                   "rollout_turn_cap": args.rollout_turn_cap
                   if args.rollout_turn_cap is not None else 50,
                   "eval_cutoff_turns": args.eval_cutoff_turns or 0}
        if args.evaluator is not None:
            student["evaluator_path"] = args.evaluator
    try:
        report = run_agreement_file(args.snapshots, student)
    except (ValueError, OSError) as e:
        print(f"错误：{e}")
        return 1
    print(f"快照 {args.snapshots}")
    print(agreement_report(report))
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"报告 JSON: {args.output}")
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
        from battlefrontier.data.backend import open_backend

        db = open_backend(args.db)
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
        from battlefrontier.report.battle_log import (
            battle_log_report,
            format_game_summaries,
            format_main_actions,
            write_battle_log_pack,
        )

        log = battle_log_report(
            db, args.experiment_id, sample_n=args.replay_sample,
        )
        print(format_game_summaries(log))
        print(format_main_actions(log))
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
        if args.autopsy:
            from battlefrontier.report.autopsy import (
                autopsy_report,
                format_autopsy,
                write_autopsy_packs,
            )

            autopsy = autopsy_report(db, args.experiment_id,
                                     sample_n=args.autopsy_sample)
            autopsy_dir = (Path(args.out) / "autopsy" if args.out
                           else Path("results") / f"report-{args.experiment_id}-autopsy")
            autopsy_paths = write_autopsy_packs(autopsy_dir, autopsy, db)
            print(format_autopsy(autopsy, autopsy_paths))
        out_dir = (Path(args.out) if args.out
                   else Path("results") / f"report-{args.experiment_id}-log")
        paths = write_battle_log_pack(out_dir, log)
        print("对局包：" + " ".join(str(p) for p in paths.values()))
    finally:
        db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bfsim")
    sub = parser.add_subparsers(dest="cmd")
    chk_deck_p = sub.add_parser("check-deck", help="卡表预检（跑前体检，零跑批；task 119）")
    chk_deck_p.add_argument("decklist", help="decklist txt 路径（每行「N 卡名 [card_id]」）")
    chk_deck_p.add_argument("--db", default=None,
                            help="ptcg-cn.db 路径（缺省读 config/battlefrontier.local.yml）")
    chk_deck_p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR, help="DSL 定义库目录")
    lg_p = sub.add_parser("league",
                          help="agent 种群联赛（task 127）：CRN 双向配对 + BT-MLE 评级")
    lg_p.add_argument("registry", nargs="?", default=None,
                      help="联赛注册表 yml（纯报告模式可缺省）")
    lg_p.add_argument("--report", default=None,
                      help="纯报告模式：按联赛名从结果库回收已跑细胞出报告")
    lg_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    lg_p.add_argument("--db", default=None,
                      help="ptcg-cn.db 路径（缺省读 config/battlefrontier.local.yml）")
    lg_p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR, help="DSL 定义库目录")
    lg_p.add_argument("--workers", type=int, default=1, help="多进程 worker 数（默认串行）")
    pt_p = sub.add_parser("probe-throughput",
                          help="吞吐决策点 spike 探针（task 149）：BC 需求 vs R2 实测产能")
    pt_p.add_argument("--agent", choices=["heuristic", "random", "distilled"],
                      default="heuristic", help="对局 agent 类型（默认 heuristic）")
    pt_p.add_argument("--games", type=int, default=200, help="计时局数（默认 200）")
    pt_p.add_argument("--workers", type=int, default=16, help="并行 worker 数（默认 16）")
    pt_p.add_argument("--seed-start", type=int, default=900000, help="种子起点")
    pt_p.add_argument("--policy", default=None, help="distilled 资产路径（distilled 必填）")
    pt_p.add_argument("--deck-id", default=None,
                      help="真实卡组 deck_id（缺省 = 内置 stub 冒烟口径）")
    pt_p.add_argument("--db", default=None,
                      help="ptcg-cn.db 路径（--deck-id 真实装配时必需；缺省读 local.yml）")
    pt_p.add_argument("--net-forward", type=int, default=0, metavar="N",
                      help="附测 policy 纯 numpy 前向微基准 N 次（需 --policy）")
    ss_p = sub.add_parser("swap-search",
                          help="换卡搜索器（task 130）：单卡替换扫描 + 筛选→确认两阶段 + 排序输出")
    ss_p.add_argument("--deck", required=True, help="被优化卡组 deck_id（换出侧）")
    ss_p.add_argument("--vs", dest="vs_deck", required=True, help="对手卡组 deck_id")
    ss_p.add_argument("--budget", type=int, required=True,
                      help="总预算（局）：60%% 筛选档 + 40%% 确认档（设计文档 §3.1）")
    ss_p.add_argument("--confirm-top", type=int, default=3, help="确认档候选数（默认 3）")
    ss_p.add_argument("--screen-games", type=int, default=None,
                      help="筛选档局数/格（缺省按预算推导，下限 60）")
    ss_p.add_argument("--confirm-games", type=int, default=None,
                      help="确认档局数/格（缺省按预算推导，下限 100；正式档 2000）")
    ss_p.add_argument("--top-n", type=int, default=12,
                      help="候选源：同 archetype 邻近卡组高频单卡 top-N（默认 12）")
    ss_p.add_argument("--include", action="append", default=[],
                      help="额外换入候选「卡名 [card_id]」可多次（败因触发件手填）")
    ss_p.add_argument("--seed-start", type=int, default=470000, help="种子锚点（筛选档）")
    ss_p.add_argument("--results", default=None,
                      help="结果库路径（默认 results/swap-search-<deck>-<vs>.db）")
    ss_p.add_argument("--db", default=None,
                      help="ptcg-cn.db 路径（缺省读 config/battlefrontier.local.yml）")
    ss_p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR, help="DSL 定义库目录")
    ss_p.add_argument("--workers", type=int, default=1, help="多进程 worker 数（默认串行）")
    fp_p = sub.add_parser("field-pick", help="选卡参考：field 分布 × matchup 矩阵（task 123，四期 M14）")
    fp_p.add_argument("--field", required=True, help="field 快照 JSON（CN 使用率，ptcgdb stats usage 出口）")
    fp_p.add_argument("--pool", required=True, help="卡池 YAML（CN↔en 名映射源）")
    fp_p.add_argument("--intl-db", default=None, help="上游 db 路径（intl matchup 格来源；缺省只用 sim/缺格）")
    fp_p.add_argument("--from", dest="from_date", default="2026-09-16", help="intl 窗起点")
    fp_p.add_argument("--to", dest="to_date", default="2026-11-14", help="intl 窗终点（含）")
    fp_p.add_argument("--sim-pack", default=None, help="偏差包 deviation.json（sim matchup 格来源）")
    fp_p.add_argument("--matrix-snap", default=None,
                      help="matchup 快照 JSON（task 125 matchup-snap 出口；与 --intl-db/--sim-pack 互斥）")
    fp_p.add_argument("--n-sim", type=int, default=1000, help="field 蒙特卡洛次数（默认 1000）")
    fp_p.add_argument("--seed", type=int, default=123, help="蒙特卡洛种子（默认 123）")
    ms_p = sub.add_parser("matchup-snap",
                          help="导出 field-pick 可读的 matchup 矩阵快照 JSON（task 125，M14 gate 操作包）")
    ms_p.add_argument("--pool", required=True, help="卡池 YAML（CN↔en 名映射源 + data_version）")
    ms_p.add_argument("--intl-db", required=True, help="上游 db 路径（intl matchup 格来源）")
    ms_p.add_argument("--from", dest="from_date", default="2026-09-16", help="intl 窗起点")
    ms_p.add_argument("--to", dest="to_date", default="2026-11-14", help="intl 窗终点（含）")
    ms_p.add_argument("--sim-pack", default=None, help="偏差包 deviation.json（可选，sim 格一并入快照）")
    ms_p.add_argument("--out", required=True, help="快照 JSON 输出路径")
    fsn_p = sub.add_parser("field-snap",
                           help="场快照导出 + 就绪探针（task 156，备赛线）")
    fsn_p.add_argument("--db", default=None,
                       help="上游 ptcg-cn.db 路径（缺省读 config/battlefrontier.local.yml）")
    fsn_p.add_argument("--from", dest="from_date", default=None, help="窗起点（导出必填）")
    fsn_p.add_argument("--to", dest="to_date", default=None, help="窗终点含（导出必填）")
    fsn_p.add_argument("--out", default=None, help="快照 JSON 输出路径（导出必填）")
    fsn_p.add_argument("--probe", action="store_true",
                       help="就绪探针：上游最新合格赛事 vs 快照窗终点（退出码 0=新鲜 / 3=有新数据）")
    fsn_p.add_argument("--snap", default=None, help="探针对比的既有快照路径")
    mc_p = sub.add_parser("mod-check", help="改表成对判读（task 156：同种子 CRN 逐格 Δ+门；task 157：--batch 批次模式）")
    mc_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    mc_p.add_argument("--batch", default=None,
                      help="prep 登记的批次 JSON（task 157：按实验 ID 取数 + 完整性第四门；"
                           "与 --base-prefix/--mod-prefix 互斥）")
    mc_p.add_argument("--base-prefix", default=None,
                      help="基线臂实验名前缀（非批次模式，仅一次性干净库）")
    mc_p.add_argument("--mod-prefix", default=None,
                      help="改表臂实验名前缀（非批次模式，仅一次性干净库）")
    mc_p.add_argument("--field", required=True, help="field 快照 JSON（权重来源）")
    mc_p.add_argument("--pool", required=True, help="卡池 YAML（slug↔对手映射）")
    mc_p.add_argument("--entry", required=True, help="报名卡组池内中文名（权重剔除自身）")
    mc_p.add_argument("--alpha", type=float, default=0.05, help="显著性水准（默认 0.05）")
    mc_p.add_argument("--family-size", dest="family_size", type=int, default=1,
                      help="扫描族候选改表批数 M（task 159：跨批 OR 采纳的 "
                           "Bonferroni 校正 α/M，缺省 1 无校正）")
    pr_p = sub.add_parser("prep",
                          help="备赛编排器（task 156）：场刷新→field-pick→成对核对→统一报告")
    pr_p.add_argument("prep", help="prep 定义 yml 路径（示例 experiments/prep.example.yml）")
    pr_p.add_argument("--db", default=None,
                      help="上游数据后端（缺省读 config/battlefrontier.local.yml）："
                           "ptcg-cn.db 文件 = sqlite ∥ dist 目录 = jsonl 导出")
    pr_p.add_argument("--results", default=None,
                      help="结果库路径（默认 results/prep-<name>.db）")
    pr_p.add_argument("--field-out", default=None, help="场快照输出路径（默认 results/ 下自动命名）")
    pr_p.add_argument("--out-dir", default=None, help="报告目录（默认 results/prep-<name>/）")
    pr_p.add_argument("--workers", type=int, default=1, help="多进程 worker 数（默认串行）")
    pr_p.add_argument("--pick-only", action="store_true",
                      help="只跑场刷新 + field-pick（零对局）")
    pr_p.add_argument("--no-strict-coverage", action="store_true",
                      help="显式关闭跑前 strict 覆盖率门槛（task 157：报告头注声明降级，"
                           "违规如实落装载告警段）")
    run_p = sub.add_parser("run", help="按实验定义 YAML 跑实验并落结果库")
    run_p.add_argument("experiment", help="实验定义 YAML 路径")
    run_p.add_argument("--workers", type=int, default=1, help="多进程 worker 数（默认串行）")
    run_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    run_p.add_argument("--db", default=None,
                       help="上游数据后端（缺省读 config/battlefrontier.local.yml）："
                            "ptcg-cn.db 文件 = sqlite ∥ dist 目录 = jsonl 导出")
    run_p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR, help="DSL 定义库目录")
    run_p.add_argument("--strict-coverage", action="store_true",
                       help="跑前 DSL 覆盖率门槛（task 131）：存在无文档非基本能量卡即拒绝开跑")
    rep_p = sub.add_parser("report", help="胜率报告（Wilson 95%% CI + 先后手拆分）")
    rep_p.add_argument("experiment_id", type=int, help="实验 id")
    rep_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    rep_p.add_argument("--decisions", action="store_true", help="追加决策聚合分节")
    rep_p.add_argument("--mcts-consider", action="store_true",
                       help="追加 MCTS 决策分析分节（task 042：访问份额/高熵决策点/分桶胜率）")
    rep_p.add_argument(
        "--replay-sample", type=int, default=3,
        help="抽样回放局数（默认 3，完成局按种子升序；0 表示不写回放正文）",
    )
    rep_p.add_argument("--autopsy", action="store_true",
                       help="追加败局解剖分节（task 124：终局类型 × 死亡回合分桶 + 抽样回放）")
    rep_p.add_argument("--autopsy-sample", type=int, default=1,
                       help="败局解剖每桶抽样局数（默认 1，按种子升序）")
    rep_p.add_argument(
        "--out", default=None,
        help="对局包目录（默认 results/report-<id>-log）：md/html/csv/json",
    )
    sen_p = sub.add_parser("sensitivity",
                           help="换卡敏感性：baseline vs variants 并排 ΔWR + 显著性检验")
    sen_p.add_argument("base_id", type=int, help="baseline 实验 id")
    sen_p.add_argument("variant_ids", type=int, nargs="+", help="variant 实验 id 列表")
    sen_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    sen_p.add_argument(
        "--replay-sample", type=int, default=2,
        help="换卡前后各抽几局回放（默认 2；0 表示不写回放正文）",
    )
    sen_p.add_argument(
        "--out", default=None,
        help="换卡包目录（默认 results/sensitivity-<base_id>）：md/html/csv/json/svg",
    )
    cal_p = sub.add_parser("calibration",
                           help="M6 偏差表：模拟矩阵 vs 真实赛事 matchup（task 030）")
    cal_p.add_argument("experiment", help="matrix 实验定义 YAML 路径")
    cal_p.add_argument("--results", default=DEFAULT_RESULTS_PATH, help="结果库路径")
    cal_p.add_argument("--db", default=None, help="ptcg-cn.db 路径（缺省读本机配置）")
    cal_p.add_argument(
        "--out", default=None,
        help="偏差包目录（默认 results/<实验名>-deviation）：同时写 md/html/csv/json",
    )
    cal_p.add_argument(
        "--tournament-split", choices=("time-70-30",), default=None,
        help="M13：显式按赛事时间切分 full/development/validation 报告",
    )
    cal_p.add_argument(
        "--validation-protocol", default=None,
        help="切分协议 YAML（默认 config/m13-validation-v1.yml）",
    )
    pr_p = sub.add_parser(
        "pairings",
        help="只读拉取池内 archetype 的真实逐桌对阵（task 073，对照用，不是浏览）",
    )
    pr_p.add_argument("--pool", required=True, help="目标卡组池 YAML（用其中 en_archetype）")
    pr_p.add_argument("--db", default=None, help="ptcg-cn.db 路径（缺省读本机配置）")
    pr_p.add_argument("--date-from", default=None, help="窗口起（默认与 calibration 相同）")
    pr_p.add_argument("--date-to", default=None, help="窗口止（默认与 calibration 相同）")
    pr_p.add_argument("--basis", default=None, help="默认 intl_aligned，与 calibration 相同")
    pr_p.add_argument("--division", default="master", help="赛区（默认 master；NULL 赛区也保留）")
    pr_p.add_argument("--sample-limit", type=int, default=20, help="原始行抽样上限（不是分母）")
    pr_p.add_argument(
        "--out", default=None,
        help="对阵包目录（默认 results/<池文件名>-pairings）：同时写 md/html/csv/json",
    )
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
    col_p = sub.add_parser(
        "collect-features",
        help="M11 数据产线（task 050，D-M11-1）：卡池配对 × 种子区间采集特征 JSONL")
    col_p.add_argument("--pool", required=True, help="目标卡池 YAML 路径")
    col_p.add_argument("--games-per-pair", type=int, required=True,
                       help="每配对局数（正式跑批 2800）")
    col_p.add_argument("--seed-start", type=int, required=True,
                       help="种子锚点（pair i → [S+i×N, +N)；正式跑批 300000）")
    col_p.add_argument("--out", required=True, help="产物目录（pair-*.jsonl）")
    col_p.add_argument("--workers", type=int, default=1, help="多进程 worker 数（默认串行）")
    col_p.add_argument("--db", default=None,
                       help="ptcg-cn.db 路径（缺省读 config/battlefrontier.local.yml；"
                            "--feature-set v3 时必填，词表构建用）")
    col_p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR, help="DSL 定义库目录")
    col_p.add_argument("--feature-set", choices=["v1", "v3"], default="v1",
                       help="特征集（task 155 WP2）：v3 = header 钉清单 + 位置行紧凑"
                            "格式（词表 = build_card_vocab(pool, db)）；缺省 v1 不变")
    te_p = sub.add_parser(
        "train-eval",
        help="M11 WP2（task 051，D-M11-3）：collect-features 产物训练线性评估器（岭回归闭式解）")
    te_p.add_argument("--data", required=True, help="pair-*.jsonl 数据目录")
    te_p.add_argument("--out", required=True, help="模型资产 JSON 输出路径")
    te_p.add_argument("--split-seed", type=int, default=None,
                      help="按局 80/20 划分种子（缺省钉死 20261016，写进 meta）")
    te_p.add_argument("--pool", default=None, help="卡池 YAML 路径（meta 锚点，可选）")
    te_p.add_argument("--max-rows-per-game", type=int, default=None,
                      help="按局行数上限（确定性抽样；缺省 None = 全量。"
                           "正式数据 744 万行，建议 20 ≈ 2.0M 行，正落 D-M11-1 估算区间）")
    te_p.add_argument("--subsample-seed", type=int, default=None,
                      help="按局抽样种子（缺省钉死 20261017，写进 meta）")
    te_p.add_argument("--code-version", default=None,
                      help="代码版本 meta 覆盖（缺省取 git short sha；测试注入用）")
    te_p.add_argument("--feature-set", choices=["v1", "v3"], default="v1",
                      help="特征集（task 155 WP3）：v3 = v3 采集产物（bf-collect-v3 "
                           "header + 位置行）走分块两遍流式训练，λ 候选六档，资产 "
                           "bf-linear-eval-v3；缺省 v1 不变。两者互斥（v1 拒 v3 "
                           "数据、v3 拒 v1 数据，显式报错）")
    tp_p = sub.add_parser(
        "train-policy",
        help="M12 WP2（task 058，D-M12-3/4）：collect-snapshots 产物蒸馏训练策略打分机"
             "（torch dev-only；缺省 bf-distilled-policy-v1，--pool 触发 v2，task 062）")
    tp_p.add_argument("--data", required=True,
                      help="快照 JSONL 目录（collect-snapshots 产物，pair-*.jsonl）")
    tp_p.add_argument("--out", required=True, help="模型资产 JSON 输出路径")
    tp_p.add_argument("--epochs", type=int, default=None,
                      help="训练轮数（缺省钉死 100，写进 meta）")
    tp_p.add_argument("--lr", type=float, default=None,
                      help="Adam 学习率（缺省钉死 1e-3，写进 meta）")
    tp_p.add_argument("--hidden", type=int, default=None,
                      help="隐藏层宽度（缺省钉死 64，写进 meta）")
    tp_p.add_argument("--split-seed", type=int, default=None,
                      help="按局 80/20 划分种子（缺省钉死 20261018，写进 meta）")
    tp_p.add_argument("--pool", default=None,
                      help="卡池 YAML 路径：提供时构建卡身份词表触发 v2 特征训练"
                           "（bf-distilled-policy-v2，task 062，D-062-2）；"
                           "缺省 = v1 旧口径（逐位不变）")
    tp_p.add_argument("--code-version", default=None,
                      help="代码版本 meta 覆盖（缺省取 git short sha；测试注入用）")
    tp_p.add_argument("--weight-scheme", default="none",
                      choices=["none", "kind-weights-v1", "kind-weights-v2"],
                      help="样本权重方案（task 066，D-066-1/2/5）：缺省 none = 现状逐位"
                           "全等；kind-weights-v1 = play_stadium ×3 / use_ability ×2"
                           " + end_turn 双投票不一致 ×0.25；kind-weights-v2 = A2 降"
                           "剂量（×1.5 / ×1.25 / ×0.5）（meta 落 weight_scheme 段）")
    tp_p.add_argument("--ceiling-dir", default="results/m12-anchor1-ceiling",
                      help="end_turn 第二投票数据源目录（pair-*.json，仅 "
                           "kind-weights-v1 需要；缺省 results/m12-anchor1-ceiling）")
    cs_p = sub.add_parser(
        "collect-snapshots",
        help="M11 一致率快照采集（task 052，D-M11-5）：教师 MCTS 跑局落决策点快照 JSONL")
    cs_p.add_argument("--pool", required=True, help="目标卡池 YAML 路径")
    cs_p.add_argument("--games-per-pair", type=int, required=True, help="每配对局数")
    cs_p.add_argument("--seed-start", type=int, required=True,
                      help="种子锚点（pair i → [S+i×N, +N)，matrix 惯例）")
    cs_p.add_argument("--out", required=True,
                      help="产物目录（pair-*.jsonl；正式落 results/m11-eval/）")
    cs_p.add_argument("--workers", type=int, default=1, help="多进程 worker 数（默认串行）")
    cs_p.add_argument("--worlds", type=int, default=2, help="教师 MCTS worlds（基准 2）")
    cs_p.add_argument("--iterations", type=int, default=50,
                      help="教师 MCTS iterations（基准 50）")
    cs_p.add_argument("--rollout-turn-cap", type=int, default=50,
                      help="教师 rollout 回合上限（默认 50）")
    cs_p.add_argument("--pair-start", type=int, default=0,
                      help="断点续采：跳过前 N 对（默认 0；种子映射不变，"
                           "续采产物与全量跑同对文件逐字节全等；负数/越界报错）")
    cs_p.add_argument("--mix-population", action="store_true",
                      help="task 151 混编种群：每局 side0/side1 按 (seed−对种子"
                           "起点)%%2 交替指派 {MCTS, 启发式}；行级 agent 标签 + "
                           "header mix=true（task 152 过滤用；缺省 = 双侧同 MCTS）")
    cs_p.add_argument("--evaluator-path", default=None,
                      help="task 151：教师 MCTS evaluator_path（评估器模型资产 "
                           "JSON；提供时注入 teacher dict，缺省 None = 不注入）")
    cs_p.add_argument("--eval-cutoff-turns", type=int, default=None,
                      help="task 151：教师 MCTS rollout 浅截断 K（提供时注入 "
                           "teacher dict，缺省 None = 不注入；>0 须配评估器）")
    cs_p.add_argument("--db", default=None,
                      help="ptcg-cn.db 路径（缺省读 config/battlefrontier.local.yml）")
    cs_p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR, help="DSL 定义库目录")
    ag_p = sub.add_parser(
        "agreement",
        help="M11 决策一致率评估（task 052，D-M11-5）：快照 × 受测配置重放比对")
    ag_p.add_argument("snapshots", help="快照 JSONL 路径（collect-snapshots 产物）")
    ag_p.add_argument("--worlds", type=int, default=None,
                      help="受测 MCTS worlds（MCTS 学生必填；与 --policy 互斥）")
    ag_p.add_argument("--iterations", type=int, default=None,
                      help="受测 MCTS iterations（MCTS 学生必填；与 --policy 互斥）")
    ag_p.add_argument("--rollout-turn-cap", type=int, default=None,
                      help="受测 rollout 回合上限（默认 50；与 --policy 互斥）")
    ag_p.add_argument("--eval-cutoff-turns", type=int, default=None,
                      help="rollout 浅截断 K（默认 0 = 禁用；与 --policy 互斥）")
    ag_p.add_argument("--evaluator", default=None,
                      help="评估器模型资产 JSON 路径（K>0 必填，装载即校验；"
                           "与 --policy 互斥）")
    ag_p.add_argument("--policy", default=None,
                      help="distilled 学生（task 059，D-M12-5）："
                           "bf-distilled-policy-v1 模型资产 JSON 路径；"
                           "与全部 MCTS 预算 flags 互斥")
    ag_p.add_argument("--output", default=None,
                      help="完整报告 JSON 输出路径（含逐行明细；缺省只打印摘要）")
    args = parser.parse_args(argv)

    if args.cmd == "check-deck":
        return _cmd_check_deck(args)
    if args.cmd == "league":
        return _cmd_league(args)
    if args.cmd == "probe-throughput":
        return _cmd_probe_throughput(args)
    if args.cmd == "swap-search":
        return _cmd_swap_search(args)
    if args.cmd == "field-pick":
        return _cmd_field_pick(args)
    if args.cmd == "matchup-snap":
        return _cmd_matchup_snap(args)
    if args.cmd == "field-snap":
        return _cmd_field_snap(args)
    if args.cmd == "mod-check":
        return _cmd_mod_check(args)
    if args.cmd == "prep":
        return _cmd_prep(args)
    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "report":
        return _cmd_report(args)
    if args.cmd == "sensitivity":
        return _cmd_sensitivity(args)
    if args.cmd == "calibration":
        return _cmd_calibration(args)
    if args.cmd == "pairings":
        return _cmd_pairings(args)
    if args.cmd == "dsl-check":
        return _cmd_dsl_check(args)
    if args.cmd == "tune":
        return _cmd_tune(args)
    if args.cmd == "tune-verify":
        return _cmd_tune_verify(args)
    if args.cmd == "collect-features":
        return _cmd_collect_features(args)
    if args.cmd == "train-eval":
        return _cmd_train_eval(args)
    if args.cmd == "train-policy":
        return _cmd_train_policy(args)
    if args.cmd == "collect-snapshots":
        return _cmd_collect_snapshots(args)
    if args.cmd == "agreement":
        return _cmd_agreement(args)
    print(f"battlefrontier {__import__('battlefrontier').__version__}："
          f"子命令 run 可用（实验定义见 experiments/），其余随里程碑添加")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
