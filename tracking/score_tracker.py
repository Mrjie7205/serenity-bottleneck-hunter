#!/usr/bin/env python3
"""score_tracker.py — 样本外 Alpha 打分(Tier 1 ③,2026-06 重写)

读 forward_picks.csv(带日期锁定的候选)→ 用 price.py 重拉现价 → 算:
  · raw return(自 record_date 以来涨跌)
  · **Alpha = raw − 同期主题 ETF 涨跌**(naive,假设 β=1,ETF 仅代理)
  · **🟢 篮子 vs 🔴 篮子内部对照**(同主题 beta 对消,差额 = 纯选股能力)= 最硬的检验
  · invalidation 触发检查(证伪条件,Tier 1 ②的闭环接口)

设计纪律(诚实):
  - 唯一方法论干净的验证(样本外、无未来函数/幸存者偏差),对照 in-sample 光子学回测。
  - **样本太短(picks 多为几天/几周)→ 全程标 `N<30 不解读 / 样本期太短`**。
    本工具价值是"现在把仪表装上、让表开始走",不是现在出结论。
  - ETF 当 beta 是粗活(市值加权偏巨头、β 假设=1);真正可信的是 🟢-vs-🔴 内部对照。

用法:
  EODHD_API_KEY=xxx python score_tracker.py            # 全量
  EODHD_API_KEY=xxx python score_tracker.py --limit 40 # 冒烟测试(前 40 行)
  控制台只打 ASCII 摘要;完整中文表写 scorecard.md(UTF-8)。价格缓存 _score_price_cache.json。
"""
import csv, json, os, sys, datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from price import fetch_history

CSV_F = os.path.join(HERE, "forward_picks.csv")
BENCH_F = os.path.join(HERE, "theme_benchmark.csv")
OUT_F = os.path.join(HERE, "scorecard.md")
CACHE_F = os.path.join(HERE, "_score_price_cache.json")

BROAD = {"US": ["SPY"], "CN": ["510300.SHG", "159919.SHE"], "HK": ["2800.HK"]}

# 种子/校准集 cutoff:≤ 此日期的 pick 是 in-sample(光子学校准集 + 历史种子,2026-01-02),
# **必须从样本外验证里剔除**——否则就是 skill 自己免责声明里警告的循环论证 + 幸存者偏差。
SEED_CUTOFF = "2026-02-01"

CACHE_POLICY = "provider-adjusted-v0.2"


def load_cache(path, today=None):
    today = today or datetime.date.today().isoformat()
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        if saved.get("policy") == CACHE_POLICY and saved.get("generated_on") == today and isinstance(saved.get("prices"), dict):
            return saved["prices"]
    except (OSError, ValueError, AttributeError):
        pass
    return {}


_cache = load_cache(CACHE_F)


def hist(sym, days=400):
    if not sym:
        return []
    if _cache.get(sym):
        return _cache[sym]
    data, _prov = fetch_history(sym, days=days)
    rows = [{"date": d["date"], "close": d["close"]} for d in data] if data else []
    _cache[sym] = rows
    return rows


def market_of(sym):
    if sym.endswith(".HK"):
        return "HK"
    if sym.endswith(".SHG") or sym.endswith(".SHE"):
        return "CN"
    return "US"  # .US / .T / .TW / .TWO → 用 SPY 代理(诚实标注)


def close_on_or_after(rows, date_str):
    for r in rows:
        if r["date"] >= date_str:
            return r["close"]
    return None


def ret_since(rows, date_str):
    if not rows:
        return None
    base = close_on_or_after(rows, date_str)
    last = rows[-1]["close"]
    if base and last and base > 0:
        return last / base - 1
    return None


def ret_1m(rows):
    if len(rows) < 22 or not rows[-22]["close"]:
        return None
    return rows[-1]["close"] / rows[-22]["close"] - 1


def first_pullable(cands):
    for c in cands:
        if hist(c):
            return c
    return None


def vbucket(v):
    v = (v or "").strip()
    return "G" if v.startswith("🟢") else "R" if v.startswith("🔴") else "Y" if v.startswith("🟡") else "?"


def fired_invalidation(pick_ret, r1m, rule):
    """默认规则:跌幅>15% 且 1m 转负。bespoke rule(invalidation 列)v1 暂只标注留人读。"""
    if pick_ret is None:
        return False
    return pick_ret < -0.15 and (r1m is not None and r1m < 0)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def hit_rate(xs):
    xs = [x for x in xs if x is not None]
    return (sum(1 for x in xs if x > 0) / len(xs)) if xs else None


def fmt(x):
    return f"{x*100:+.1f}%" if x is not None else "—"


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    today = datetime.date.today().isoformat()
    benchmarks = {}
    with open(BENCH_F, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            benchmarks[row["theme"]] = (row["benchmark"], row.get("note", ""))

    with open(CSV_F, encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if limit:
        rows = rows[:limit]

    scored, n_err = [], 0
    for r in rows:
        sym = r["eodhd_symbol"].strip()
        theme = r["theme"].strip()
        rec = r["record_date"].strip()
        ph = hist(sym)
        pr = ret_since(ph, rec)
        if pr is None:
            n_err += 1
            continue
        r1m = ret_1m(ph)
        mkt = market_of(sym)

        bsym, _note = benchmarks.get(theme, (None, ""))
        brows = hist(bsym) if bsym else []
        broad = False
        if not brows or (bsym and market_of(bsym) != mkt):
            cand = first_pullable(BROAD.get(mkt, []))
            if cand:
                bsym, brows, broad = cand, hist(cand), True
        br = ret_since(brows, rec) if brows else None
        alpha = (pr - br) if br is not None else None

        scored.append({
            "sym": sym, "theme": theme, "verdict": r.get("skill_verdict", ""),
            "vb": vbucket(r.get("skill_verdict", "")), "raw": pr, "alpha": alpha,
            "bench": bsym, "broad": broad, "seed": rec <= SEED_CUTOFF,
            "fired": fired_invalidation(pr, r1m, r.get("invalidation", "")),
        })

    from render_report import _atomic_text
    _atomic_text(CACHE_F, json.dumps({"policy": CACHE_POLICY, "generated_on": today, "prices": _cache}, ensure_ascii=False))

    # 种子/校准集(in-sample,光子学等)单列,**不进样本外头条**
    seed = [s for s in scored if s["seed"]]
    fwd = [s for s in scored if not s["seed"]]
    G = [s for s in fwd if s["vb"] == "G"]
    R = [s for s in fwd if s["vb"] == "R"]
    Y = [s for s in fwd if s["vb"] == "Y"]
    gmed, rmed = median([s["raw"] for s in G]), median([s["raw"] for s in R])
    gm, rm = mean([s["raw"] for s in G]), mean([s["raw"] for s in R])

    L = []
    L.append(f"# Scorecard — 样本外 Alpha 打分({today})\n")
    L.append("> ⚠️ **样本期太短(picks 多为 2-3 周)+ N 不足 → 本表只装仪表、不下结论。**")
    L.append(f"> **种子/校准集(光子学等 {len(seed)} 只,record_date ≤ {SEED_CUTOFF})已从样本外剔除**——")
    L.append("> 它是 skill 逆向建出来的 in-sample 赢家(SIVE +1918% 之类),算进来就是循环论证 + 幸存者偏差。")
    L.append("> 用 **median** 而非 mean 看 🟢(抗单只 10-bagger 拉偏);最硬的是 🟢-vs-🔴 内部对照(主题 beta 对消)。")
    L.append(f"> 样本外已打分 {len(fwd)} | 种子 {len(seed)}(单列) | 拉价失败 {n_err}\n")

    L.append("## ① 🟢 vs 🔴 内部对照(样本外 · 最硬 · 主题 beta 对消)\n")
    L.append("| 桶 | N | median raw | mean raw | 命中率(raw>0) |")
    L.append("|---|---|---|---|---|")
    for lab, b in (("🟢候选", G), ("🟡观望", Y), ("🔴排除", R)):
        nf = " ⚠N<30" if len(b) < 30 else ""
        h = hit_rate([s["raw"] for s in b])
        L.append(f"| {lab} | {len(b)}{nf} | {fmt(median([s['raw'] for s in b]))} | {fmt(mean([s['raw'] for s in b]))} | {f'{h*100:.0f}%' if h is not None else '—'} |")
    if gmed is not None and rmed is not None:
        L.append(f"\n**🟢−🔴 价差(median)= {(gmed-rmed)*100:+.1f}%**(>0 = 过滤器有选股信号;<0 = 反指 ⚠)。")
        L.append(f"⚠️ 样本外 picks 才 2-3 周,这个数 = 噪音,**现在只装表、等 3-6 个月再读**。\n")

    L.append("## ② Alpha vs 主题 ETF(样本外 · 次要 · naive β=1)\n")
    L.append("| 桶 | N | median Alpha | 命中率(α>0) |")
    L.append("|---|---|---|---|")
    for lab, b in (("🟢候选", G), ("🔴排除", R)):
        h = hit_rate([s["alpha"] for s in b])
        L.append(f"| {lab} | {len(b)} | {fmt(median([s['alpha'] for s in b]))} | {f'{h*100:.0f}%' if h is not None else '—'} |")

    L.append("\n## ③ 各主题 🟢 候选表现(样本外,raw median,N 小慎读)\n")
    L.append("| 主题 | 🟢 N | 🟢 median raw | benchmark |")
    L.append("|---|---|---|---|")
    for t in sorted(set(s["theme"] for s in fwd)):
        g = [s for s in G if s["theme"] == t]
        if g:
            L.append(f"| {t} | {len(g)} | {fmt(median([s['raw'] for s in g]))} | {g[0]['bench'] or '—'} |")

    # 种子/校准集单列(诚实标注:非样本外)
    if seed:
        sg = [s for s in seed if s["vb"] == "G"]
        L.append("\n## ⑤ 种子/校准集(in-sample · **非样本外 · 仅参考**)\n")
        L.append(f"光子学等 {len(seed)} 只,record_date ≤ {SEED_CUTOFF}(约 5.5 个月前)。这是 skill 逆向建模的 in-sample 赢家,**不能当业绩**。")
        L.append(f"\n| 标的 | 主题 | raw |")
        L.append("|---|---|---|")
        for s in sorted(sg, key=lambda x: -(x["raw"] or 0)):
            L.append(f"| {s['sym']} | {s['theme']} | {fmt(s['raw'])} |")

    fired = [s for s in fwd if s["fired"]]
    L.append(f"\n## ④ 证伪条件触发(默认规则:跌幅>15% 且 1m 转负)\n")
    L.append(f"本次 {len(fired)} 个 pick 触发证伪 → thesis 已被价格证否,应复盘:\n")
    for s in sorted(fired, key=lambda x: x["raw"])[:30]:
        L.append(f"- {s['sym']} ({s['theme']}) raw {s['raw']*100:+.0f}% · {s['verdict'][:24]}")

    open(OUT_F, "w", encoding="utf-8").write("\n".join(L))

    print("=" * 64)
    print(f"Scorecard {today} | forward {len(fwd)} | seed {len(seed)} (excl) | fail {n_err}")
    print("=" * 64)
    print("[1] OUT-OF-SAMPLE G-vs-R internal (median, theme beta cancels):")
    if gmed is not None and rmed is not None:
        print(f"    G median {gmed*100:+.1f}% (N={len(G)}) | R median {rmed*100:+.1f}% (N={len(R)})")
        print(f"    >>> G-R median spread = {(gmed-rmed)*100:+.1f}%  (>0 = filter has signal)")
        print(f"    (mean: G {gm*100:+.1f}% R {rm*100:+.1f}% -- skewed by outliers, use median)")
    amed = median([s["alpha"] for s in G])
    print(f"[2] G median alpha vs theme-ETF (naive b=1): {amed*100:+.1f}%" if amed is not None else "[2] alpha n/a")
    print(f"[4] invalidation fired (forward): {len(fired)} picks")
    print(f"[5] seed/in-sample EXCLUDED from above: {len(seed)} (photonics etc, NOT performance)")
    print("\n*** forward picks only 2-3 weeks old => INSTRUMENT ONLY, do not read signal ***")
    print(f"full table -> {OUT_F}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
