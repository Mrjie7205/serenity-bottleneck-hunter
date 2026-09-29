#!/usr/bin/env python3
"""
跨主题节点扫描 / Cross-Theme Node Scan
=====================================
读 forward_picks.csv → 按 eodhd_symbol 分组统计跨主题次数 → 应用档位过滤 →
输出 ⭐ 跨主题节点 leaderboard + 主题状态(🔥/🌡️/❄️)+ 写快照。

Serenity 风格的 ⑤跨主题原型:**同一只标的服务多个 capex cycle = 非线性定价权**。
这个脚本是 SKILL.md Step 4 末尾的强制步骤,在 Step 5 三道闸门之前给候选打 ⭐。

档位过滤:防止巨头(STM/NVDA)因业务摊薄被误标。
  ✅ 计入:上游咽喉 / 上游设备 / 中游器件 / 高风险投机 / 中游卖铲子(必须有 ④)
  ❌ 排除:中游系统 / 下游对照 / 反面参照 / 任何 🔴 排除/跳过 的行

用法:
  python cross_theme_scan.py
  → 控制台打印 + 写 cross_theme_index_snapshot.csv
"""
import csv
import os
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "forward_picks.csv")
SNAPSHOT_PATH = os.path.join(HERE, "cross_theme_index_snapshot.csv")

# --- 档位过滤规则 ---
EXCLUDED_TIER_KEYWORDS = ["中游系统", "下游对照", "反面参照"]
EXCLUDED_VERDICT_KEYWORDS = ["🔴", "排除", "跳过"]
TIER_REQUIRES_ARCHETYPE_4 = ["中游卖铲子"]  # 中游卖铲子档必须有 ④ 才纳入


def is_eligible(row):
    """判定该行是否纳入跨主题计数。"""
    tier = str(row.get("tier", ""))
    verdict = str(row.get("skill_verdict", ""))
    archetypes = str(row.get("archetypes", ""))

    # 黑名单档位
    for kw in EXCLUDED_TIER_KEYWORDS:
        if kw in tier:
            return False
    # 黑名单 verdict
    for kw in EXCLUDED_VERDICT_KEYWORDS:
        if kw in verdict:
            return False
    # 中游卖铲子要求 ④ 普适
    for required_tier in TIER_REQUIRES_ARCHETYPE_4:
        if required_tier in tier and "④" not in archetypes:
            return False
    return True


def stage_bucket(stage_text):
    """把 entry_stage 文本桶化为 early / ext / basing-momentum / cool / seed / other。

    桶定义(2026-06-01 加 basing-momentum,修复物理 AI 主题被误判 cooled 的 bug):
    - seed:        历史种子,不计入主题状态
    - early:       明确写 "early-uptrend" 或类似
    - ext:         extended/parabolic/at-top/已到顶等
    - basing-momentum:  关键新增桶 — "深度回调后 1m 启动" 的真模式 A 早期
                        触发关键词:basing / range/启动 / 1m+ 转正 / 真basing
                        实际是 active 早期,不是 cooled
    - cool:        downtrend / range 且无启动信号 / 横盘 / 已回调多月
    - other:       兜底
    """
    s = (stage_text or "").lower()
    if "historical-seed" in s or "seed" in s:
        return "seed"
    if "early" in s:
        return "early"
    if "extend" in s or "parabolic" in s or "top" in s or "顶" in s or "hot" in s:
        return "ext"
    # basing-with-momentum:关键启动信号关键词(在 range/down 文本里出现的"启动 / 真 basing / 1m+xx%"等)
    if "启动" in s or "真 basing" in s or "真basing" in s or "basing 启动" in s or "basing-momentum" in s:
        return "basing-momentum"
    # 普通 range/down(无启动信号)
    if "down" in s or "横盘" in s or "range" in s or "basing" in s or "below" in s:
        return "cool"
    return "other"


def compute_theme_status(rows):
    """根据 stage 分布判定主题状态。

    优先级(从高到低):
    1. 多数 early 或 basing-momentum → 🔥 active(含早期启动场景)
    2. 多数 ext → 🌡️ mature
    3. 多数 cool(且无启动信号)→ ❄️ cooled
    4. 都是 seed → 🌱 seed-only
    5. 其它 → 🌡️ mixed
    """
    by_theme = defaultdict(lambda: defaultdict(int))
    for r in rows:
        b = stage_bucket(r.get("entry_stage", ""))
        by_theme[r["theme"]][b] += 1

    status = {}
    for theme, buckets in by_theme.items():
        n = sum(buckets.values()) - buckets.get("seed", 0)
        if n == 0:
            status[theme] = "🌱 seed-only"
            continue
        # active 早期 = early + basing-momentum 合计 ≥ 40%
        active_count = buckets.get("early", 0) + buckets.get("basing-momentum", 0)
        if active_count / n >= 0.4:
            # 进一步区分:basing-momentum 占多的标"🔥 active(早期启动)"
            if buckets.get("basing-momentum", 0) > buckets.get("early", 0):
                status[theme] = "🔥 active(早期启动)"
            else:
                status[theme] = "🔥 active"
        elif buckets.get("ext", 0) / n >= 0.5:
            status[theme] = "🌡️ mature"
        elif buckets.get("cool", 0) / n >= 0.3:
            status[theme] = "❄️ cooled"
        else:
            status[theme] = "🌡️ mixed"
    return status


def main():
    if not os.path.exists(CSV_PATH):
        print(f"❌ {CSV_PATH} 不存在")
        return 1

    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # 标记 eligible
    eligible = [r for r in rows if is_eligible(r)]

    # 按 symbol 聚合
    by_sym = defaultdict(list)
    for r in eligible:
        by_sym[r["eodhd_symbol"]].append(r)

    # 跨主题:同一 symbol 出现在 ≥2 个不同 theme
    cross = []
    for sym, rs in by_sym.items():
        themes = sorted({r["theme"] for r in rs})
        if len(themes) >= 2:
            cross.append({
                "symbol": sym,
                "name": rs[0].get("name", ""),
                "tier": rs[0].get("tier", ""),
                "archetypes": rs[0].get("archetypes", ""),
                "theme_count": len(themes),
                "themes": themes,
                "stars": "⭐⭐" if len(themes) >= 3 else "⭐",
            })
    cross.sort(key=lambda x: -x["theme_count"])

    theme_status = compute_theme_status(rows)

    # --- 打印 ---
    print("=" * 78)
    print(f"跨主题节点扫描 / Cross-Theme Node Scan")
    print("=" * 78)
    print(f"数据源:{CSV_PATH}")
    print(f"总行数:{len(rows)} | eligible(已过档位/排除过滤):{len(eligible)} | 独立公司:{len(by_sym)}")
    print(f"跨主题节点(≥2 主题):{len(cross)}")
    print()

    if not cross:
        print("⚠️ 当前 forward_picks 无跨主题节点。")
        print("   原因可能:① 主题间技术距离远;② 历史种子未覆盖足够主题。")
    else:
        print("跨主题节点 leaderboard(按主题数降序):")
        print("-" * 78)
        for c in cross:
            themes_str = " + ".join(c["themes"])
            print(f"  {c['stars']} {c['symbol']:12s} {c['name']:24s}  "
                  f"档位:{c['tier']} ({c['archetypes']})")
            print(f"      跨 {c['theme_count']} 主题:{themes_str}")
        print()

    print("主题状态(数据驱动 — 基于 stage 分布):")
    print("-" * 78)
    for theme, status in sorted(theme_status.items()):
        print(f"  {status}  {theme}")
    print()
    print(f"备注:跨主题加分仅在 🔥 active 主题间叠加才视为强信号(Serenity ⑤跨 capex cycle)。")
    print()

    # --- 写快照 ---
    snapshot_date = datetime.now().strftime("%Y-%m-%d")
    with open(SNAPSHOT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "snapshot_date", "symbol", "name", "tier", "archetypes",
            "theme_count", "stars", "themes_list", "themes_active_status"
        ])
        for c in cross:
            active_summary = "/".join(theme_status.get(t, "?") for t in c["themes"])
            w.writerow([
                snapshot_date, c["symbol"], c["name"], c["tier"], c["archetypes"],
                c["theme_count"], c["stars"], ";".join(c["themes"]), active_summary
            ])

    print(f"快照已写:{SNAPSHOT_PATH}")
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rebuild cross-theme stars from an explicitly selected registry; no network calls.")
    parser.add_argument("--input", default=CSV_PATH, help="Input forward_picks.csv (existing default preserved)")
    parser.add_argument("--output", default=SNAPSHOT_PATH, help="Output cross-theme snapshot (existing default preserved)")
    options = parser.parse_args()
    CSV_PATH, SNAPSHOT_PATH = os.path.abspath(options.input), os.path.abspath(options.output)
    if os.path.normcase(CSV_PATH) == os.path.normcase(SNAPSHOT_PATH):
        parser.error("input and output must be different files")
    exit(main())
