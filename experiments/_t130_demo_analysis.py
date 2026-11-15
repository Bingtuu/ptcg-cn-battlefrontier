"""task 130 E2E 演示交叉验证分析：搜索器 top 刀位 vs t1114 人工刀位对照。

判据（设计文档 §6，2026-11-15 冻结）：
1. 管线完整性：失败局 = 0；装载 vanilla 告警 = 0。
2. 方向共现：确认档 top-3 ∪ 筛选档 top-10 命中 t1114 同类方向
   （出手保障 = 换入 ∈ {火伊布ex, 伊布ex}；保护 = 换入 ∈ {友好宝芬}）；
   3 对手 ≥2 命中 = PASS。
3. 量级互证：演示档 ΔWR CI 半宽在 ±4–7pp（200/500 局档），
   与 t1114 2000 局口径（±2pp 级效应、半宽 ±3pp）自洽——不复现点估计。
"""

import sqlite3

OPS = {
    "dragapult": ("results/t130-swap-search-dragapult.db", "mik_moe:711851"),
    "grimmsnarl": ("results/t130-swap-search-grimmsnarl.db", "mik_moe:692446"),
    "joltik": ("results/t130-swap-search-joltik.db", "mik_moe:677291"),
}
DIRECTION_IN = {"火伊布ex": "出手保障", "伊布ex": "出手保障", "友好宝芬": "保护"}
T1114_HUMAN_KNIVES = [  # (out, in, ΔWR@2000局 vs 711851)
    ("空手道王的修炼", "火伊布ex", -0.0065),
    ("波波", "伊布ex", +0.0070),
    ("古剑豹", "友好宝芬", +0.0175),
    ("大比鸟ex", "叶伊布ex", -0.0155),
    ("太乐巴戈斯ex", "愿增猿", -0.0185),
]


def read_group(db_path, suffix):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT id, variant FROM experiments WHERE group_name LIKE ? AND variant != ''"
        " ORDER BY id", (f"%-{suffix}",)).fetchall()
    out = {}
    for exp_id, variant in rows:
        games = conn.execute(
            "SELECT COUNT(*) total,"
            " SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) failed,"
            " SUM(CASE WHEN error IS NULL AND is_draw = 0 AND winner = 0 THEN 1 ELSE 0 END) wins_a,"
            " SUM(CASE WHEN error IS NULL AND is_draw = 0 THEN 1 ELSE 0 END) decided"
            " FROM games WHERE experiment_id = ?", (exp_id,)).fetchone()
        out[exp_id] = (variant, games)
    base = conn.execute(
        "SELECT id FROM experiments WHERE group_name LIKE ? AND variant = ''"
        " ORDER BY id LIMIT 1", (f"%-{suffix}",)).fetchone()
    base_stats = conn.execute(
        "SELECT COUNT(*) total,"
        " SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) failed,"
        " SUM(CASE WHEN error IS NULL AND is_draw = 0 AND winner = 0 THEN 1 ELSE 0 END) wins_a,"
        " SUM(CASE WHEN error IS NULL AND is_draw = 0 THEN 1 ELSE 0 END) decided"
        " FROM games WHERE experiment_id = ?", (base[0],)).fetchone()
    conn.close()
    return out, base_stats


def swap_of(db_path, exp_id, variant):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    yaml_text, group = conn.execute(
        "SELECT definition_yaml, group_name FROM experiments WHERE id = ?",
        (exp_id,)).fetchone()
    conn.close()
    import yaml
    d = yaml.safe_load(yaml_text)
    # 实验行存的是整组定义：按 variant 名（cNNN）索引到该实验的刀位
    idx = int(variant[1:]) if variant.startswith("c") else 0
    assert d["variants"][idx]["name"] == variant, (group, variant)
    return d["variants"][idx]["swaps"][0]


def main():
    hits = 0
    for op, (db_path, vs) in OPS.items():
        print(f"\n===== {op}（vs {vs}）=====")
        total_failed = 0
        # 筛选档 top-10
        screen, base1 = read_group(db_path, "s1")
        total_failed += base1[1]
        rows = []
        for exp_id, (variant, g) in screen.items():
            total_failed += g[1]
            sw = swap_of(db_path, exp_id, variant)
            d_wr = g[2] / g[3] - base1[2] / base1[3] if g[3] and base1[3] else 0.0
            rows.append((d_wr, exp_id, sw))
        rows.sort(key=lambda r: -r[0])
        print(f"baseline（筛选档）：{base1[2]}/{base1[3]} = {base1[2]/base1[3]*100:.1f}%"
              f"（失败 {base1[1]}）")
        screen_top = rows[:10]
        hit_dirs = set()
        print("筛选档 top-10：")
        for d_wr, exp_id, sw in screen_top:
            tag = DIRECTION_IN.get(sw["in"], "")
            if tag:
                hit_dirs.add(tag)
            print(f"  {d_wr*100:+6.2f}pp  {sw['out']} → {sw['in']} [{sw.get('in_id')}]"
                  f"{'  <== t1114 同类方向:' + tag if tag else ''}")
        # 确认档 top-3
        conf, base2 = read_group(db_path, "s2")
        total_failed += base2[1]
        crows = []
        for exp_id, (variant, g) in conf.items():
            total_failed += g[1]
            sw = swap_of(db_path, exp_id, variant)
            d_wr = g[2] / g[3] - base2[2] / base2[3] if g[3] and base2[3] else 0.0
            se = ((g[2]/g[3]*(1-g[2]/g[3])/g[3]
                   + base2[2]/base2[3]*(1-base2[2]/base2[3])/base2[3]) ** 0.5)
            crows.append((d_wr, exp_id, sw, se))
        crows.sort(key=lambda r: -r[0])
        print(f"baseline（确认档 500 局）：{base2[2]}/{base2[3]} = "
              f"{base2[2]/base2[3]*100:.1f}%")
        print("确认档 top-3：")
        for d_wr, exp_id, sw, se in crows:
            tag = DIRECTION_IN.get(sw["in"], "")
            if tag:
                hit_dirs.add(tag)
            print(f"  {d_wr*100:+6.2f}pp（CI ±{1.96*se*100:.1f}pp）"
                  f"  {sw['out']} → {sw['in']}"
                  f"{'  <== t1114 同类方向:' + tag if tag else ''}")
        print(f"失败局合计：{total_failed}")
        print(f"方向命中：{sorted(hit_dirs) if hit_dirs else '无'}")
        if hit_dirs:
            hits += 1
        if op == "dragapult":
            print("t1114 人工刀位（2000 局同种子 460000..461999）对照：")
            for out, in_, d in T1114_HUMAN_KNIVES:
                print(f"  {d*100:+6.2f}pp  {out} → {in_}")
    print(f"\n===== 总判定：{hits}/3 对手命中 t1114 同类方向 "
          f"（预注册：≥2 PASS / =1 部分 / 0 FAIL）=====")


if __name__ == "__main__":
    main()
