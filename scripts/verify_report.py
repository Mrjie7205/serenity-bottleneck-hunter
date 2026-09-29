#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_report.py — L0 报告交付契约 linter
ticker-verify: skip   (本文件含 ticker 字面量/正则,不自我 verify)

查的是「契约/交付」,不是「思路/真相」:报告区块齐不齐、每个候选内部全不全、
数字和 ground-truth/脚本对不对得上、判定有没有正确入轨 forward_picks、文件卫不卫生。
不判断论点对错、不验证状态真值、不算 Alpha(那是 score_tracker 的事)。

用法:
  EODHD_API_KEY=xxx python scripts/verify_report.py reports/<主题>.html
  python scripts/verify_report.py 报告.html --scan tracking/_scan_x.json --today 2026-06-17 --fresh-days 30

退出码: 0 = 仅【警】或全过 ; 1 = 有【拦】 ; 2 = 用法错/读不到文件
级别: 【拦】不通过别宣布完成 ; 【警】打印提醒不阻断。
"""
import os, re, sys, csv, json, glob, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ticker_truth import lookup_by_ticker            # L1 ground truth
try:
    from verify_tickers import _name_matches          # L3 容差匹配,复用避免两套标准
except Exception:
    def _name_matches(c, tz, te):
        c = (c or "").lower(); tz = (tz or "").lower(); te = (te or "").lower()
        return (not c) or (c in tz or tz in c or (te and c in te))

BLOCK, WARN = "拦", "警"
# 交易所后缀 → 币种符号(防给 A 股标 $)
CCY = {"US": "$", "SHG": "¥", "SHE": "¥", "SS": "¥", "SZ": "¥", "HK": "HK$",
       "TW": "NT$", "TWO": "NT$", "TO": "C$", "PA": "€", "DE": "€", "MI": "€",
       "AS": "€", "L": "£", "LSE": "£", "T": "¥", "OL": "kr", "ST": "kr"}

F = []  # findings: (group, sev, where, msg)
def add(group, sev, where, msg): F.append((group, sev, where, msg))

def money(s):
    if s is None: return None
    m = re.search(r"-?\d[\d,]*\.?\d*", str(s))
    return float(m.group().replace(",", "")) if m else None

def approx(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol

def _first(chunk, pat):
    m = re.search(pat, chunk); return m.group(1) if m else None

def index(rows, getter):
    """按 ticker 建索引,full(MTRN.US)和 base(MTRN)都做 key"""
    d = {}
    for r in rows or []:
        t = (getter(r) or "").upper().strip()
        if not t: continue
        d[t] = r; d.setdefault(t.split(".")[0], r)
    return d

def lookup_map(d, tk):
    if not tk or not d: return None
    u = tk.upper()
    return d.get(u) or d.get(u.split(".")[0])

# ───────────────────────── A 组:顶层区块在不在 ─────────────────────────
SECTIONS = [
    ("一句话结论",      [r"一句话结论", r'class="verdict"', r'class="tldr"', r'class="lead-verdict"'], BLOCK),
    ("Step1 资本开支",  [r"资本开支"], BLOCK),
    ("30 秒看懂",       [r"30 ?秒"], WARN),
    ("产业链网状图",    [r"<svg"], BLOCK),
    ("本次行动点",      [r"top-picks", r"本次行动", r"行动点"], BLOCK),
    ("候选 leaderboard", [r'class="tk"'], BLOCK),
    ("跨主题信号",      [r"跨主题"], WARN),
    ("三道闸门",        [r"闸门", r"gates"], BLOCK),
    ("落地结论",        [r"落地", r"仓位", r"触发器"], BLOCK),
    ("免责声明",        [r"免责", r"非投资建议"], BLOCK),
    ("数据备注/快照",   [r"快照", r"price\.py", r"数据备注"], BLOCK),
    ("术语表",          [r"术语"], WARN),
]
def check_sections(html):
    for name, pats, sev in SECTIONS:
        if not any(re.search(p, html) for p in pats):
            add("A结构", sev, "-", f"缺区块:{name}")
    # 产业链双规则瓶颈判定标(金边漏斗 / 酒红边枢纽)
    if "<svg" in html and not re.search(r"--gold|金边|--burg|酒红", html):
        add("A结构", WARN, "chain-viz", "产业链图未见瓶颈判定标(金边/酒红边)")
    # 真 chain-viz 组件(防「静态简版」偷工:2026-06-17 教训 → lessons.md#chain-viz-fidelity)
    if re.search(r"产业链|chain-viz", html):
        for label, marker in [("cnode 真节点", 'class="cnode'), ("chain-edges svg", "chain-edges"),
                              ("edge-list 依赖边", "data-from"), ("自动绘制脚本", "layoutChain")]:
            if marker not in html:
                add("A结构", BLOCK, "chain-viz", f"产业链图缺真组件:{label}(疑似手搓静态简版,非交互真版)")

# ───────────────────────── B/C/D 组:逐候选 ─────────────────────────
def split_candidates(html):
    idxs = [m.start() for m in re.finditer(r'<div class="tk"[^>]*>', html)]
    return [html[s:(idxs[i + 1] if i + 1 < len(idxs) else len(html))]
            for i, s in enumerate(idxs)]

def cand_ticker(chunk):
    return (_first(chunk, r'data-ticker="([A-Za-z0-9.\-]+)"')
            or _first(chunk, r"/chart/([A-Za-z0-9.\-]+)")
            or _first(chunk, r'<div class="tk">([A-Za-z0-9.\-]+)'))

def check_candidates(html, scan_by, fp_by):
    cands = split_candidates(html)
    if not cands:
        add("B候选", BLOCK, "-", "未找到任何候选行(.tk)"); return
    print(f"· 候选行: {len(cands)} 个")
    for chunk in cands:
        tk = cand_ticker(chunk); where = tk or "??"
        badge = _first(chunk, r'class="badge b-(green|amber|red)"')
        has_chart = "/chart/" in chunk
        # 非候选行(下游对照 / 说明 / 表头):无 badge 且无 chart 链接 → 跳过,不当候选苛求 §A
        if not badge and not has_chart:
            continue
        # 合并双标行(如 "ATI / CRS"):一行两只,数字为代表值,跳过逐标的数字核对
        disp = _first(chunk, r'<div class="tk"[^>]*>([^<]*)') or ""
        merged = "/" in disp
        has_mo = 'class="mo' in chunk
        nm = (_first(chunk, r'class="t">([^<·]+)') or "").strip()

        # —— B:候选内部完整性 ——
        if not badge:
            add("B候选", WARN, where, "无判定标识(badge)")
        if badge in ("green", "amber") and not has_mo:
            add("B候选", BLOCK, where, "🟢/🟡 缺水位标尺(.mo)— 疑似掉块")
        if "红队" not in chunk:
            add("B候选", BLOCK, where, "缺 §A 红队折叠")
        if badge == "green" and "§B" not in chunk and "证伪" not in chunk:
            add("B候选", BLOCK, where, "🟢 缺 §B 证伪")
        if has_mo and not re.search(r"贴顶|高位|中位|低位|贴底", chunk):
            add("B候选", WARN, where, "标尺缺人话水位词")

        # —— 取价 ——
        px = money(_first(chunk, r'class="px">([^<]+)<'))
        ends = re.search(r'class="ends">(.*?)</div>', chunk, re.S)
        low = high = cur = None
        if ends:
            bs = re.findall(r"<b>([^<]+)</b>", ends.group(1))
            if len(bs) >= 2: low, high = money(bs[0]), money(bs[1])
        cur = money(_first(chunk, r'class="cur"[^>]*>([^<]+)<'))

        # —— 新功能:标尺三价齐不齐(本次新增,级别【警】;合并双标行跳过)——
        if has_mo and not merged:
            if low is None or high is None:
                add("B候选", WARN, where, "标尺两端未标 6 月低/高 价格")
            if cur is None:
                add("B候选", WARN, where, "标尺游标未标现价")

        # —— C:ticker/名称对账(第二张网,git hook 之外;合并双标行用裸 ticker,豁免)——
        if tk and not merged:
            info = lookup_by_ticker(tk)
            if info and nm:
                tz = (info.get("name_zh", "") or "").strip()
                te = (info.get("name_en", "") or "").strip()
                if not _name_matches(nm, tz, te):
                    add("C数据", BLOCK, where, f"名称不符:报告'{nm}' vs 真相 zh'{tz}'/en'{te}'")
            elif not info:
                add("C数据", WARN, where, f"{tk} 不在 ticker_truth 库")
            # 币种 sanity
            suf = tk.split(".")[-1] if "." in tk else "US"
            want = CCY.get(suf, "$")
            pxraw = _first(chunk, r'class="px">([^<]+)<') or ""
            if want != "$" and want not in pxraw and "$" in pxraw:
                add("C数据", WARN, where, f"{tk} 属 {suf} 却标 $(应 {want})")

        # —— C:价格对账 scan(linter 的牙齿;合并双标行跳过,数字为代表值)——
        sc = lookup_map(scan_by, tk)
        if sc and not merged:
            slast, slo, shi = sc.get("last"), sc.get("low_6mo"), sc.get("high_6mo")
            if px is not None and slast is not None and not approx(px, slast, max(0.02, abs(slast) * 0.002)):
                add("C数据", BLOCK, where, f"现价 {px} ≠ scan last {slast}")
            if low is not None and slo is not None and not approx(low, slo, max(0.02, abs(slo) * 0.003)):
                add("C数据", BLOCK, where, f"6 月低 {low} ≠ scan low_6mo {slo}")
            if high is not None and shi is not None and not approx(high, shi, max(0.02, abs(shi) * 0.003)):
                add("C数据", BLOCK, where, f"6 月高 {high} ≠ scan high_6mo {shi}")
            if cur is not None and slast is not None and not approx(cur, slast, max(0.02, abs(slast) * 0.002)):
                add("C数据", BLOCK, where, f"标尺现价 {cur} ≠ scan last {slast}")
            off = money(_first(chunk, r"距高点 <b>([^<]+)</b>"))
            soff = sc.get("pct_off_6mo_high")
            if off is not None and soff is not None and not approx(off, soff, 0.3):
                add("C数据", WARN, where, f"距高点 {off}% ≠ scan {soff}%")

        # —— D:入轨 forward_picks(合并双标行跳过逐标核对)——
        if tk and fp_by is not None and not merged:
            row = lookup_map(fp_by, tk)
            if not row:
                add("D入轨", BLOCK, where, f"{tk} 不在 forward_picks(漏入库)")
            elif badge == "green" and not (row.get("invalidation", "") or "").strip():
                add("D入轨", BLOCK, where, "🟢 forward_picks 的 invalidation 列为空")

# ───────────────────────── C 组:状态新鲜度绊线 ─────────────────────────
STATUS_KW = re.compile(r"(已上市|已 ?IPO|IPO 上市|挂牌上市|被[^,，。\s]{1,8}(?:收购|并购)|已被收购|"
                       r"私有公司|未上市|尚未上市|已退市|借壳上市|SPAC 上市)")
def check_status(html, today, N):
    seen = set()
    for m in STATUS_KW.finditer(html):
        s = max(0, m.start() - 90); e = min(len(html), m.end() + 90)
        win = html[s:e]
        dm = re.search(r"(20\d{2})-(\d{2})-(\d{2})", win) or re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月", win)
        key = (m.group(0), dm.group(0) if dm else None)
        if key in seen: continue
        seen.add(key)
        if not dm:
            add("C数据", BLOCK, "-", f"状态断言『{m.group(0)}』附近无日期(断言必须带日期)")
            continue
        try:
            d = (datetime.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
                 if dm.lastindex == 3 else datetime.date(int(dm.group(1)), int(dm.group(2)), 1))
            age = (today - d).days
            if age > N:
                add("C数据", WARN, "-", f"状态『{m.group(0)}』日期 {d} 已 {age} 天(>{N}),建议重核")
        except Exception:
            pass

# ───────────────────────── E 组:文件卫生 ─────────────────────────
def check_hygiene(html):
    leftovers = []
    for pat in [r"\{\{[^}]*\}\}", r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b", r"待填", r"PLACEHOLDER", r"占位符"]:
        leftovers += [m.group(0)[:24] for m in re.finditer(pat, html)]
    if leftovers:
        add("E卫生", BLOCK, "-", f"残留占位符 {len(leftovers)} 处:{leftovers[:6]}")
    o, c = len(re.findall(r"<details", html)), len(re.findall(r"</details>", html))
    if o != c:
        add("E卫生", BLOCK, "-", f"<details> 开合不平衡:{o} 开 / {c} 合")
    ds, de = len(re.findall(r"<summary", html)), len(re.findall(r"</summary>", html))
    if ds != de:
        add("E卫生", BLOCK, "-", f"<summary> 开合不平衡:{ds} / {de}")
    # 只查破坏「离线自包含」的外部资源(<link> 样式 + src= 资源);<a href> 正文引用本就该外链,不算
    res = re.findall(r'<link\b[^>]*href="(https?://[^"]+)"', html) + re.findall(r'\bsrc="(https?://[^"]+)"', html)
    res_ext = sorted({u for u in res if "fonts.googleapis" not in u and "fonts.gstatic" not in u})
    loc = sorted(set(re.findall(r'(?:href|src)="([^"]*(?:localhost|127\.0\.0\.1)[^"]*)"', html)))
    if res_ext:
        add("E卫生", WARN, "-", f"含外部资源链接(破坏离线自包含){len(res_ext)} 个:{res_ext[:3]}")
    if loc:
        add("E卫生", WARN, "-", f"含 localhost 链接 {len(loc)} 处(对他人是死链;私库自用可容忍)")

# 注入的关键 class 必须有对应 CSS 规则 —— 防「标记裸奔」(markup 注了 class 但内联 <style> 没规则)
# 由来:2026-06-17 给标尺注 <span class="cur"> 却忘了往报告内联 style 注 .cur 规则,
#       原 linter 只查 class 在不在、没查有没有样式 → 漏过视觉坏掉的报告。
STYLED_CLASSES = ["cur", "gauge", "dot", "track", "mo", "ends", "word", "lbl",
                  "badge", "stage-t", "gates-mini", "hist", "top-picks", "tp-card", "cnode"]
def check_styled(html):
    styles = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    if not styles:
        return  # 非自包含报告(无内联 style),跳过
    for cls in STYLED_CLASSES:
        if not re.search(rf'class="[^"]*(?<![\w-]){re.escape(cls)}(?![\w-])', html):
            continue  # markup 里没用这个 class
        if not re.search(rf"\.{re.escape(cls)}(?![\w-])", styles):
            add("E卫生", BLOCK, "-", f"class『{cls}』标记里用了但 <style> 无对应规则(标记裸奔→渲染坏)")
    # 揭示类无脚本 → 内容隐形(2026-06-17 全白报告教训):.X{opacity:0} + .X.Y{opacity:1} 但全文无 <script>
    has_script = "<script" in html
    for m in re.finditer(r"\.([\w-]+)\s*\{[^}]*opacity\s*:\s*0", styles):
        cls = m.group(1)
        if re.search(rf"\.{re.escape(cls)}\.[\w-]+\s*\{{[^}}]*opacity\s*:\s*1", styles) \
           and re.search(rf'class="[^"]*(?<![\w-]){re.escape(cls)}(?![\w-])', html) and not has_script:
            add("E卫生", BLOCK, "-", f"揭示类『{cls}』(opacity:0)在标记用了但全文无 <script> 揭示 → 内容会全白")

# ───────────────────────── scan 自动定位 ─────────────────────────
def find_scan(html, explicit):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    base = {s.split(".")[0].upper() for s in re.findall(r"/chart/([A-Za-z0-9.\-]+)", html)}
    best, bestn = None, 0
    for p in glob.glob(os.path.join(HERE, "..", "tracking", "_scan_*.json")):
        try:
            with open(p, encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except Exception:
            continue
        if not isinstance(data, list): continue
        tks = {str(d.get("ticker", "")).split(".")[0].upper() for d in data if isinstance(d, dict)}
        n = len(base & tks)
        if n > bestn: best, bestn = p, n
    return best if bestn >= 3 else None

def load_fp(path):
    if not os.path.exists(path): return None
    rows = []
    with open(path, encoding="utf-8") as f:
        rd = csv.reader(f); hdr = next(rd, None)
        if not hdr: return None
        def col(*names):
            for i, h in enumerate(hdr):
                if any(n in h.lower() for n in names): return i
            return -1
        ti, ii, ri = col("symbol", "ticker"), col("invalidation"), col("tier", "判定")
        if ti < 0: return rows
        for r in rd:
            if len(r) <= ti: continue
            rows.append({"ticker": r[ti].strip(),
                         "invalidation": r[ii].strip() if 0 <= ii < len(r) else "",
                         "tier": r[ri].strip() if 0 <= ri < len(r) else ""})
    return rows

# ───────────────────────── main ─────────────────────────
def main():
    F.clear()
    args = sys.argv[1:]
    report = scan_arg = tracking_arg = None
    strict = False
    today = datetime.date.today(); N = 30
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--scan" and i + 1 < len(args): scan_arg = args[i + 1]; i += 2; continue
        if a == "--tracking" and i + 1 < len(args): tracking_arg = args[i + 1]; i += 2; continue
        if a == "--strict": strict = True; i += 1; continue
        if a == "--today" and i + 1 < len(args): today = datetime.date.fromisoformat(args[i + 1]); i += 2; continue
        if a == "--fresh-days" and i + 1 < len(args): N = int(args[i + 1]); i += 2; continue
        if not a.startswith("--"): report = a
        i += 1
    if not report or not os.path.exists(report):
        print(__doc__); return 2

    with open(report, encoding="utf-8", errors="replace") as handle:
        html = handle.read()
    print(f"verify_report · {os.path.basename(report)}  (today={today}, fresh<{N}d)")

    scan_path = find_scan(html, scan_arg)
    scan_rows = load_scan(scan_path) if scan_path else None
    if scan_arg and not scan_rows:
        print('[ERROR] 指定的 scan 不存在、为空或格式无效'); return 2
    scan_by = index(scan_rows, lambda r: r["ticker"]) if scan_rows else {}
    if scan_rows: print(f"· 价格对账源: {os.path.basename(scan_path)}（{len(scan_rows)} 标的)")
    else: add("C数据", WARN, "-", "未找到匹配 scan JSON,跳过价格对账(用 --scan 指定)")

    fp_rows = load_fp(tracking_arg or os.path.join(HERE, "..", "tracking", "forward_picks.csv"))
    if tracking_arg and fp_rows is None:
        print('[ERROR] 指定的 tracking 文件不存在或格式无效'); return 2
    fp_by = index(fp_rows, lambda r: r["ticker"]) if fp_rows else None
    if fp_rows is None: add("D入轨", WARN, "-", "未找到 forward_picks.csv,跳过入轨检查")

    check_sections(html)
    check_candidates(html, scan_by, fp_by)
    if strict:
        if not scan_rows or fp_rows is None:
            add('C数据', BLOCK, '-', '严格模式需要有效 scan 和 tracking')
        for chunk in split_candidates(html):
            ticker = cand_ticker(chunk)
            if not lookup_map(scan_by, ticker):
                add('C数据', BLOCK, ticker or '-', '严格模式下每个候选必须有对应 scan')
    check_status(html, today, N)
    check_hygiene(html)
    check_styled(html)

    # —— 输出 ——
    order = ["A结构", "B候选", "C数据", "D入轨", "E卫生"]
    blocks = [f for f in F if f[1] == BLOCK]
    warns = [f for f in F if f[1] == WARN]
    for g in order:
        gf = [f for f in F if f[0] == g]
        if not gf: continue
        print(f"\n── {g} ──")
        for grp, sev, where, msg in gf:
            tag = "【拦】" if sev == BLOCK else "【警】"
            print(f"  {tag} [{where}] {msg}")
    print(f"\n{'='*52}")
    if blocks or (strict and warns):
        print(f"[FAIL] {len(blocks)} 个【拦】+ {len(warns)} 个【警】— 别宣布完成,先修【拦】")
        return 1
    print(f"[PASS] 0 个【拦】, {len(warns)} 个【警】(只提醒,不阻断)")
    return 0

def load_scan(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return [d for d in data if isinstance(d, dict) and d.get("ticker")]
    except Exception:
        return None

if __name__ == "__main__":
    sys.exit(main())
