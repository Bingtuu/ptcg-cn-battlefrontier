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


def _cmd_collect_features(args: argparse.Namespace) -> int:
    """M11 数据产线（task 050 WP1，D-M11-1）：卡池全部配对 × 种子区间采集特征 JSONL。

    落 <out>/pair-<index>-<名A>x<名B>.jsonl（不落结果库，D-T4 先例）；
    失败局剔除并计数上报。正式跑批口径：36 对 × 2800 局 @seed-start 300000。
    """
    from battlefrontier.runner.collect import run_collect_pool

    db_path = args.db or load_db_path()
    summaries, warnings = run_collect_pool(
        args.pool, db_path, games_per_pair=args.games_per_pair,
        seed_start=args.seed_start, out_dir=args.out,
        workers=args.workers, cards_dir=args.cards_dir)
    for w in warnings:
        print(f"[装载告警] {w}")
    total_rows = sum(s.rows for s in summaries)
    total_failed = sum(s.failed for s in summaries)
    for s in summaries:
        print(f"[{s.pair_index:2d}] {s.archetype_a}×{s.archetype_b}：{s.filename} — "
              f"{s.games} 局 / {s.rows} 行 / 失败剔除 {s.failed}")
    print(f"采集完成：{len(summaries)} 个配对 × {args.games_per_pair} 局，"
          f"共 {total_rows} 行，失败剔除 {total_failed} 局（目录 {args.out}）")
    return 0


def _cmd_train_eval(args: argparse.Namespace) -> int:
    """M11 WP2（task 051，D-M11-3）：collect-features 产物 → 岭回归闭式解训练 → 模型资产 JSON。

    死维度警戒（设计文档 §5）：验证集 MSE 不优于常数基线 → 退出码 2（模型照常产出，
    如实落账不强行失败）；数据错误 → 退出码 1。
    """
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


def _cmd_train_policy(args: argparse.Namespace) -> int:
    """M12 WP2（task 058，D-M12-3/4）：教师快照目录 → MLP 策略打分机蒸馏训练 → 资产 JSON。

    torch dev-only（训练非复算面 D3-4）；缺省超参全钉死写 meta；holdout argmax
    准确率落 meta；数据错误 → 退出码 1。
    task 062 WP2d（D-062-2/4）：提供 --pool 时构建卡身份词表触发 v2 特征训练
    （资产 bf-distilled-policy-v2）；不提供 = v1 旧行为逐位不变。
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
            card_vocab=card_vocab)
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
    try:
        summaries, warnings = run_collect_snapshots_pool(
            args.pool, db_path, games_per_pair=args.games_per_pair,
            seed_start=args.seed_start, out_dir=args.out,
            workers=args.workers, cards_dir=args.cards_dir, teacher=teacher,
            pair_start=args.pair_start)
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
                       help="ptcg-cn.db 路径（缺省读 config/battlefrontier.local.yml）")
    col_p.add_argument("--cards-dir", default=DEFAULT_CARDS_DIR, help="DSL 定义库目录")
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
