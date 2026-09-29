#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_report.py — Serenity 瓶颈报告统一渲染引擎(修法 A 工具化)
ticker-verify: skip

报告 = **克隆最近一份合格报告的完整外壳**(head CSS + body 末尾全部脚本 reveal/术语/chain-draw)
     + 数据驱动渲染内容。agent 只写一个「主题 SPEC」(dict:候选 / §A§B / 产业链节点边 / 文字),
引擎负责:克隆外壳、拉 scan 价(零手填)、渲染**真 chain-viz**(.cnode/.edge-list 喂 layoutChain
自动绘制+判瓶颈)、水位标尺三价、§A 红队 + §B 证伪、写 forward_picks。
产出**过 verify_report 契约 by construction**——这就是修法 A:报告没法手搓/降级,引擎是唯一路。

用法:
  from render_report import render
  render(SPEC)                                   # 薄生成器里(见 tracking/_gen_mlcc_report.py)
  python render_report.py --spec theme_spec.json # 或 CLI(JSON spec)
"""
import os, re, csv, json, tempfile
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CCY = {"T":"¥","SHE":"¥","SHG":"¥","SS":"¥","SZ":"¥","TW":"NT$","KO":"₩","HK":"HK$",
       "US":"$","TO":"C$","PA":"€","L":"£","KS":"₩"}

def _p(path): return path if os.path.isabs(path) else os.path.normpath(os.path.join(ROOT, path))
def cy(tk): return CCY.get(tk.split(".")[-1], "$")
def word(r): return "贴顶" if r>=90 else "高位" if r>=70 else "中位" if r>=30 else "低位" if r>=10 else "贴底"
def scls(r): return "ext" if r>=88 else ("early" if r<60 else "range")

def justify(d):
    """二轴判定的第二轴:这波涨基本面跟不跟得上 → 区分「贵但对(动量龙头)」vs「真贴顶(纯重估)」。
    输入 scan 字段:rng + ret_3m + forward_pe/trailing_pe/peg/eps_growth/rev_growth + rs_rank/rs_total。
    返回 (hint, 内联样式的显示串)。数据缺失(A股常缺 forward/PEG)优雅降级,不强判。"""
    rng = d.get("range_pos_6mo_pct", 50); r3 = d.get("ret_3m_pct") or 0
    fpe, tpe, peg = d.get("forward_pe"), d.get("trailing_pe"), d.get("peg")
    epsg, revg = d.get("eps_growth"), d.get("rev_growth")
    rs, rst = d.get("rs_rank"), d.get("rs_total")
    mult = None
    if fpe and tpe and fpe > 0 and tpe > 0:
        mult = "压缩" if fpe < tpe * 0.95 else ("扩张" if fpe > tpe * 1.05 else "持平")
    growth = epsg if epsg is not None else revg
    g_sus = growth is not None and (growth > 300 or growth < -100)   # 小基数算爆/数据错 → 不计分,显示 ⚠️
    g_eff = None if g_sus else growth
    lead = (g_eff is not None and g_eff >= r3 * 0.6)         # 盈利/营收增速跟得上涨幅
    leader = bool(rs and rst and rs <= max(1, rst / 3))
    laggard = bool(rs and rst and rs > rst * 2 / 3)
    score = 0
    score += 1 if mult == "压缩" else (-1 if mult == "扩张" else 0)
    score += 1 if (peg is not None and 0 < peg <= 2) else (-1 if (peg is not None and peg > 3) else 0)
    score += 1 if (g_eff is not None and lead) else (-1 if (g_eff is not None and not lead and g_eff < 10) else 0)
    score += 1 if leader else (-1 if laggard else 0)
    pe_sus = fpe is not None and fpe >= 80                   # forward 绝对估值过高:压缩也不算「对」
    if rng >= 85:
        hint = "贵但对" if score >= 1 else ("真贴顶" if score <= -1 else "高位待判")
        if hint == "贵但对" and pe_sus:
            hint = "高位待判"
    elif rng <= 30:
        hint = "低位埋伏" if score >= 0 else "低位落后"
    else:
        hint = "中位"
    color = {"贵但对": "var(--green)", "低位埋伏": "var(--green)", "真贴顶": "var(--red)",
             "低位落后": "var(--red)"}.get(hint, "var(--muted)")
    def s(v): return v if v is not None else "—"
    parts = [f"fwdP/E {s(fpe)}" + (f"·{mult}" if mult else ""), f"PEG {s(peg)}",
             (f"盈利{epsg:+.0f}%" if epsg is not None else (f"营收{revg:+.0f}%" if revg is not None else "增速—")),
             (f"RS {rs}/{rst}" if rs else "")]
    warn = (" ⚠️增速存疑" if g_sus else "") + (" ⚠️估值极高" if pe_sus else "")
    disp = ('<br><span style="font-size:10px;color:var(--faint)">第二轴 · ' + " · ".join(p for p in parts if p)
            + warn + f' → <b style="color:{color}">{hint}</b></span>')
    return hint, disp

def ruler(S, tk):
    d=S[tk]; c=cy(tk); r=d["range_pos_6mo_pct"]; cl=scls(r); clamp=min(90,max(10,r))
    raw_stage=(d.get("stage") or "").lower()
    if "downtrend" in raw_stage:
        stage_cl, stage_label, stage_small = "range", "DOWNTREND/BASE", "下行/筑底"
    elif "extended" in raw_stage or "parabolic" in raw_stage:
        stage_cl, stage_label, stage_small = "ext", "EXTENDED", "已抛物线"
    elif "uptrend" in raw_stage:
        stage_cl, stage_label, stage_small = "early", "EARLY-UP", "上升初段"
    elif "range" in raw_stage or "neutral" in raw_stage:
        stage_cl, stage_label, stage_small = "range", "RANGE/NEUTRAL", "横盘/中性"
    else:
        stage_cl = cl
        stage_label = "EXTENDED" if cl=="ext" else "EARLY-UP" if cl=="early" else "RANGE/BASE"
        stage_small = "已抛物线" if cl=="ext" else "刚启动" if cl=="early" else "横盘/回调"
    return (f'<div class="mo s-{cl}"><div class="ends"><span>6月低 <b>{c}{d["low_6mo"]:.2f}</b></span>'
            f'<span><b>{c}{d["high_6mo"]:.2f}</b> 6月高</span></div>'
            f'<div class="gauge"><div class="track"></div><div class="dot" style="left:{r}%"></div>'
            f'<span class="cur" style="left:{clamp}%">{c}{d["last"]:.2f}</span></div>'
            f'<div class="lbl"><span class="word">{word(r)}</span> · 距高点 <b>{d["pct_off_6mo_high"]:.1f}%</b><br>'
            f'近1月 <b>{(d["ret_1m_pct"] or 0):+.1f}%</b> · 近3月 <b>{(d["ret_3m_pct"] or 0):+.1f}%</b>{justify(d)[1]}</div></div>'
            f'<div class="stage-t {stage_cl}">{stage_label}<small>{stage_small}</small></div>')

def badge(v, tier):
    cl={"green":"b-green","amber":"b-amber","red":"b-red"}[v]; ic={"green":"🟢","amber":"🟡","red":"🔴"}[v]
    return f'<span class="badge {cl}">{ic} {tier}</span>'

_SA_HEAD = ('<details style="margin-top:8px"><summary style="cursor:pointer;font-family:\'JetBrains Mono\',monospace;'
            'font-size:10.5px;font-weight:700;color:#b3261e">§A 反向研究/红队{sb_label} '
            '<span style="background:#7a2e3a;color:#fff;padding:1px 5px;border-radius:3px">Tier-1</span></summary>'
            '<div style="background:#f7e6e3;border:1px solid #e0a89f;border-radius:6px;padding:9px 11px;margin:6px 0 0;'
            'font-size:12px;line-height:1.5;color:#5a2420">{ra}<br><b style="color:#b3261e">最大杀点:{kill}</b></div>{sb}</details>')

def _redteam(ra, kill, fb=""):
    sb = (f'<div style="background:#eef1ea;border:1px solid #b8c4a8;border-radius:6px;padding:9px 11px;margin:6px 0 0;'
          f'font-size:12px;line-height:1.5;color:#2d4010"><b>§B 证伪(🟢 必带)</b> 满足任一即认错:· {fb}</div>') if fb else ""
    return _SA_HEAD.format(sb_label=(" + §B 证伪" if sb else ""), ra=ra, kill=kill, sb=sb)

def card(S, x, cockpit_url=None, demo=False):
    d=S[x["tk"]]; c=cy(x["tk"])
    chart = (f'<a class="ck" href="{escape(cockpit_url.rstrip("/"), quote=True)}/chart/{escape(x["tk"], quote=True)}" title="K线">📈</a>'
             if cockpit_url else '')
    head=(f'<div class="tk" data-ticker="{escape(x["tk"], quote=True)}">{x["tk"].split(".")[0]}'
          f'{chart}<span class="px">{c}{d["last"]:.2f}</span></div>')
    g="未评估" if demo else ("过" if x["v"]=="green" else "半过")
    other="未评估" if demo else ("半过" if x["v"]=="green" else "不过")
    nm=(f'<div class="nmcell"><div class="t">{x["t"]}</div><div class="d">{x["d"]}</div>{badge(x["v"],x["tier"])}'
        f'<div class="gates-mini"><span class="mid">🔒 真瓶颈 {g}</span><span class="no">👁 前机构 {other}</span>'
        f'<span class="mid">💰 便宜 {other}</span></div>'
        f'<details class="more"><summary>详情:原型 / 论点</summary><p><b>原型</b> {x["arch"]} · <b>论点</b> {x["th"]}</p></details>'
        f'{_redteam(x["ra"], x["kill"], x.get("fb","") if x["v"]=="green" else "")}</div>')
    return f'<div class="row">{head}{nm}{ruler(S,x["tk"])}</div>'

def merged_row(m):
    return (f'<div class="row"><div class="tk">{m["label"]}<span class="px">{m.get("px","对照")}</span></div>'
            f'<div class="nmcell"><div class="t">{m["title"]}</div><div class="d">{m["desc"]}</div>{badge(m["v"],m["tier"])}'
            f'{_redteam(m["ra"], m["kill"])}</div></div>')

def _cn_stage(S, tid):
    if tid not in S: return "s-early"
    r=S[tid]["range_pos_6mo_pct"]; return "s-ext" if r>=88 else ("s-range" if r>=60 else "s-early")
def _cnode(S, n, node_desc, snap):
    tid,lab,sub,star = n
    sv='<span class="star-inline">⭐</span>' if star else ''
    if tid in S:
        d=S[tid]; desc=f'{d["name_zh"]}——{sub}'
        status=f'水位{d["range_pos_6mo_pct"]} · 近1月{(d["ret_1m_pct"] or 0):+.0f}% · 近3月{(d["ret_3m_pct"] or 0):+.0f}% [{snap}]'
    else:
        desc=node_desc.get(tid, sub); status=""
    return f'<div class="cnode {_cn_stage(S,tid)}" data-id="{tid}" data-desc="{desc}" data-status="{status}">{sv}<b>{lab}</b><small>{sub}</small></div>'
def chain_viz(S, spec):
    nd=spec.get("chain_node_desc",{}); snap=spec["snapshot"]
    def layer(lid,label,small,nodes):
        return (f'<div class="chain-layer" data-layer="{lid}"><div class="layer-label">{label}<small>{small}</small></div>'
                f'<div class="layer-nodes">'+"".join(_cnode(S,n,nd,snap) for n in nodes)+'</div></div>')
    body="".join(layer(lid,lab,sm,nodes) for lid,lab,sm,nodes in spec["chain_layers"])
    el="".join(f'<span data-from="{a}" data-to="{b}" data-weight="{w}"></span>' for a,b,w in spec["chain_edges"])
    return ('<div class="chain-viz"><svg class="chain-edges" xmlns="http://www.w3.org/2000/svg"></svg>'
            +body+f'<div class="edge-list" hidden>{el}</div></div>')

def section(tag, inner): return f'<section><div class="wrap rv"><div class="tag">{tag}</div>{inner}</div></section>'

def _metadata_head(head, spec):
    head = re.sub(r'<!--.*?-->', '', head, flags=re.S)
    head = re.sub(r'<script\b[^>]*\bid=["\']serenity-report-meta["\'][^>]*>.*?</script>', '', head, flags=re.S | re.I)
    metadata = {"schema_version": 1, "report_date": spec["date"], "theme": spec["theme_tag"],
                "price_asof": spec["snapshot"], "demo": bool(spec.get("demo", False))}
    encoded = json.dumps(metadata, ensure_ascii=False).replace('<', '\\u003c')
    return head.replace('</head>', '<link rel="icon" href="data:,">\n<script type="application/json" id="serenity-report-meta">'+encoded+'</script>\n</head>')


def _atomic_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.serenity-', suffix='.tmp', dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def render(spec):
    with open(_p(spec["scan"]), encoding="utf-8-sig") as handle:
        S={d["ticker"]: d for d in json.load(handle)}
    required = ("last", "low_6mo", "high_6mo", "range_pos_6mo_pct", "pct_off_6mo_high", "ret_1m_pct", "ret_3m_pct", "stage")
    for candidate in spec["candidates"]:
        record = S[candidate["tk"]]
        if any(key not in record for key in required):
            raise ValueError('scan lacks required price fields for '+candidate['tk'])
    cards="\n".join(card(S,x,spec.get("cockpit_url"),spec.get("demo", False)) for x in spec["candidates"])
    merged="\n".join(merged_row(m) for m in spec.get("merged_rows",[]))
    capex=" &nbsp;·&nbsp; ".join(f'<b>{a}</b> {b}' for a,b in spec["capex_stats"])
    acts="".join(f'<div class="tp-card"><div class="tp-k">{k}</div><div class="tp-t">{t}</div><div class="tp-d">{d}</div><div class="tp-act">{a}</div></div>' for k,t,d,a in spec["action_cards"])
    foot="".join(f'<p class="note">{n}</p>' for n in spec["footer_notes"])
    demo_banner = '<p class="note"><b>历史演示 · 仅用于验证工具和报告结构，不代表当前行情或投资判断。</b></p>' if spec.get('demo') else ''
    body=f'''<header class="hero"><div class="wrap"><h1>{spec.get("title_html", escape(spec["title"]))}</h1>{demo_banner}
<p class="sub">{spec["subtitle"]}</p></div></header>
{section("◆ 一句话结论", spec["verdict"])}
{section("Step 1 · 资本开支确定性", f'<div class="callout">{capex}</div><p class="note">{spec["capex_note"]}</p>')}
{section("30 秒看懂", spec["thirty_sec"])}
{section("Step 2 · 产业链网状图(瓶颈双规则自动判定)", spec["chain_lead"]+chain_viz(S,spec)+f'<p class="note">{spec["chain_note"]}</p>')}
<section><div class="wrap rv"><div class="top-picks"><div class="tp-label">⚑ 本次行动点</div><div class="tp-grid">{acts}</div></div></div></section>
{section("Step 4–6 · 候选 leaderboard", spec["leaderboard_lead"]+'<div class="board"><div class="row head"><span>代码 / 现价</span><span>是什么 · 判定</span><span>6月水位 · 动量</span><span style="text-align:right">stage</span></div>'+cards+merged+'</div>')}
{section("Step 5 · 三道闸门", spec["gates"])}
{section("⭐ 跨主题信号", spec["cross_theme"])}
{section("Step 7 · 落地结论", spec["landing"])}
<footer><div class="wrap">{foot}<details class="glossary-section"><summary>术语速查</summary><div class="glossary-list"></div></details><p class="note disc">{spec["disclaimer"]}</p></div></footer>'''
    with open(_p(spec.get("shell_from", "reference/report_template.html")), encoding="utf-8") as handle:
        src=handle.read()
    shell_head='<!DOCTYPE html>\n'+src[src.index('<html'):src.index("</head>")+7]
    head=re.sub(r"<title>.*?</title>", lambda _: f'<title>{escape(spec["title"])}</title>', shell_head, flags=re.S)
    head=_metadata_head(head, spec)
    if spec.get("extra_css"):
        head=head.replace('</head>', '<style>'+spec['extra_css']+'</style></head>')
    scripts=src[src.index("<script>"): src.rindex("</script>")+len("</script>")]
    html=head+f'\n<body>\n{body}\n'+scripts+'\n</body>\n</html>'
    out=_p(spec["out"]); _atomic_text(out, html)
    print(f"render_report → {out} ({len(html)} chars · 克隆外壳 {len(scripts)} 脚本)")
    if spec.get("forward_picks", True): _write_fp(spec, S)
    return out

def _write_fp(spec, S):
    fp=_p(spec.get("tracking_file", "tracking/forward_picks.csv"))
    if not os.path.exists(fp):
        _atomic_text(fp, 'record_date,theme,eodhd_symbol,name,tier,archetypes,entry_price,currency,entry_stage,skill_verdict,thesis,invalidation\n')
    with open(fp, encoding="utf-8-sig") as source:
        existing={(r[1],r[2]) for r in list(csv.reader(source))[1:] if len(r)>=3}
    theme=spec["theme_tag"]; n=0
    with open(fp,"a",encoding="utf-8",newline="") as f:
        w=csv.writer(f)
        TIERZH = {"green": "上游咽喉", "amber": "观察", "red": "排除"}      # 🔴 也入库:score_tracker 🟢-vs-🔴 内部对照需反面参照
        VERD = {"green": "候选/Mode-A 小仓", "amber": "观望/等回调", "red": "排除/反面参照"}
        for x in spec["candidates"]:
            if x["v"] not in TIERZH or (theme, x["tk"]) in existing: continue
            d = S[x["tk"]]
            w.writerow([spec["date"], theme, x["tk"], d["name_zh"], TIERZH[x["v"]], x["arch"],
                        f'{d["last"]:.2f}', {"¥":"JPY" if x["tk"].endswith(".T") else "CNY","NT$":"TWD","₩":"KRW","HK$":"HKD","C$":"CAD","€":"EUR","£":"GBP","$":"USD"}.get(cy(x["tk"]), "USD"),
                        d.get("stage","")[:30], VERD[x["v"]], x["th"][:60], x.get("inv","")])
            n += 1
    print(f"forward_picks +{n}")

if __name__ == "__main__":
    import sys
    if "--spec" in sys.argv:
        with open(sys.argv[sys.argv.index("--spec")+1], encoding="utf-8-sig") as handle:
            render(json.load(handle))
    else:
        print(__doc__)
