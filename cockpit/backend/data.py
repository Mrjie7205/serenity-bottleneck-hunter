"""data.py — Serenity Cockpit 数据层
从明确选择的本机数据目录解析跟踪表、报告、真值和星级；默认只读公开演示。
零数据库、零爬虫。只读。
"""
import csv
import re
import os
import json
import hashlib
from pathlib import Path
from functools import lru_cache
from datetime import datetime
import settings

HERE = Path(__file__).resolve().parent
ROOT = settings.DATA_DIR
SKILL = settings.PACKAGE_ROOT
TRACKING = ROOT / "tracking"
REFERENCE = ROOT / "reference"
REPORTS_DIR = ROOT / "reports"

FORWARD_PICKS = TRACKING / "forward_picks.csv"
CROSS_THEME = TRACKING / "cross_theme_index_snapshot.csv"
TICKER_TRUTH = (REFERENCE / "ticker_truth.csv") if (REFERENCE / "ticker_truth.csv").exists() else SKILL / "reference" / "ticker_truth.csv"
TAXONOMY = TRACKING / "theme_taxonomy.csv"
REPORT_CATALOG = REPORTS_DIR / "catalog.json"

# 黄仁勋 AI 五层蛋糕(2026-03-10)— 层定位文案,供蛋糕地图页展示
LAYER_ROLES = {
    1: "能源/电力 — 实时电力=实时智能的瓶颈,黄仁勋点名的头号瓶颈层(底层战争是能源战争)",
    2: "芯片 — 把能源高效转成算力;芯片层进展决定 AI 扩张速度",
    3: "基础设施(AI 工厂)— 土地/供电/冷却/网络/把上万处理器编排成一台机器",
    4: "模型 — 理解多模态信息的 AI 模型;烧钱方多非瓶颈,猎区在卖给训练方的铲子",
    5: "应用 — 最顶层,拉动下面所有层;多为下游,瓶颈机会需甄别",
}

# 11 层子层(L0-L12)— 在 5 宏层下加更细的瓶颈定位等高线(与 tracking/_sublayer_map.py 同源)
SUBLAYER_META = {
    "L0": "发电", "L1": "输配电", "L2": "数据中心物理基建", "L3": "芯片与硬件",
    "L4": "网络与互联", "L5": "云与算力批发", "L6": "基础模型",
    "L6d": "训练数据/语料", "L7": "模型工具", "L8": "AI基础设施SaaS",
    "L9": "Agent平台", "L10": "终端应用与设备", "L11": "AI安全", "L12": "网络安全",
}
# 镜头:hunt=瓶颈猎场(上游卡脖子,我们的主战场) / coverage=覆盖型(云/模型/应用大盘广扫)
HUNT_SUBLAYERS = {"L0", "L1", "L2", "L3", "L4", "L6d", "L8", "L11", "L12"}


def lens_of(sublayer: str) -> str:
    """子层 → 镜头。未映射(空)归 coverage,避免污染猎手视图。"""
    return "hunt" if sublayer in HUNT_SUBLAYERS else "coverage"


# ---------- market / verdict helpers ----------

def _norm_row(row: dict) -> dict:
    """防御:历史 CSV 曾出现 BOM/引号包进列名的脏数据 — 归一化 key"""
    return {
        (k or "").replace("﻿", "").strip().strip('"').strip(): v
        for k, v in row.items()
    }


def market_of(symbol: str) -> str:
    if symbol.endswith(".US"):
        return "US"
    if symbol.endswith(".HK"):
        return "HK"
    if symbol.endswith((".SHG", ".SHE")):
        return "CN"
    if symbol.endswith(".T"):
        return "JP"
    return "OTHER"


MARKET_LABEL = {"US": "美股", "HK": "港股", "CN": "A股", "JP": "日股", "OTHER": "海外"}


def verdict_class(v: str) -> str:
    if v.startswith("🟢"):
        return "green"
    if v.startswith("🟡"):
        return "amber"
    if v.startswith("🔴"):
        return "red"
    return "other"


_TRIGGER_RE = re.compile(r"[\[\(（]([^\]\)）]*)[\]\)）]")


def extract_trigger(verdict: str) -> str:
    """从判定文本提取方括号内的 trigger/原因说明"""
    m = _TRIGGER_RE.search(verdict)
    return m.group(1) if m else ""


# ---------- file mtime cache-buster ----------

def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _file_version(p: Path):
    try:
        stat = p.stat()
        return (str(p), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return (str(p), 0, 0)


# ---------- cross-theme stars ----------

@lru_cache(maxsize=4)
def _load_stars(cache_key: float):
    stars = {}
    if not CROSS_THEME.exists():
        return stars
    with open(CROSS_THEME, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip()
            if not sym:
                continue
            try:
                count = int(row.get("theme_count") or 0)
            except ValueError:
                count = 0
            stars[sym] = {
                "theme_count": count,
                "stars": (row.get("stars") or "").strip(),
                "themes_list": (row.get("themes_list") or "").strip(),
            }
    return stars


def load_stars():
    return _load_stars(_file_version(CROSS_THEME))


# ---------- ticker truth ----------

@lru_cache(maxsize=4)
def _load_truth(cache_key: float):
    truth = {}
    if not TICKER_TRUTH.exists():
        return truth
    with open(TICKER_TRUTH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            t = (row.get("ticker") or "").strip()
            if t:
                truth[t] = {
                    "name_zh": (row.get("name_zh") or "").strip(),
                    "name_en": (row.get("name_en") or "").strip(),
                }
    return truth


def load_truth():
    return _load_truth(_file_version(TICKER_TRUTH))


# ---------- taxonomy(五层蛋糕分类)----------

@lru_cache(maxsize=4)
def _load_taxonomy(cache_key: float):
    rows = []
    if not TAXONOMY.exists():
        return rows
    with open(TAXONOMY, encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            row = _norm_row(raw)
            try:
                layer = int((row.get("layer") or "0").strip())
            except ValueError:
                continue
            rows.append({
                "layer": layer,
                "layer_name": (row.get("layer_name") or "").strip(),
                "subsector": (row.get("subsector") or "").strip(),
                "board": (row.get("board") or "").strip(),
                "theme_key": (row.get("theme_key") or "").strip(),
                "sublayer": (row.get("sublayer") or "").strip(),
                "status": (row.get("status") or "").strip() or "planned",
                "market": (row.get("market") or "").strip(),
                "priority": _to_int(row.get("priority")),
                "leaders": _split_list(row.get("leaders")),
                "bottleneck_pureplays": _split_list(row.get("bottleneck_pureplays")),
                "note": (row.get("note") or "").strip(),
            })
    return rows


def _to_int(v):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _split_list(v):
    return [x.strip() for x in (v or "").split(";") if x.strip()]


def load_taxonomy():
    return _load_taxonomy(_file_version(TAXONOMY))


def _theme_layer_map():
    """theme_key -> {layer, layer_name, subsector, board} (仅已扫/有 theme_key 的行)"""
    m = {}
    for r in load_taxonomy():
        if r["theme_key"]:
            m[r["theme_key"]] = {
                "layer": r["layer"], "layer_name": r["layer_name"],
                "subsector": r["subsector"], "board": r["board"],
                "sublayer": r["sublayer"],
            }
    return m


def layer_for_theme(theme: str) -> dict:
    return _theme_layer_map().get(theme, {
        "layer": 0, "layer_name": "未分类", "subsector": "未分类", "board": theme,
        "sublayer": "",
    })


# ---------- forward picks ----------

@lru_cache(maxsize=4)
def _load_picks(cache_key: float):
    picks = []
    if not FORWARD_PICKS.exists():
        return picks
    stars = load_stars()
    truth = load_truth()
    with open(FORWARD_PICKS, encoding="utf-8-sig") as f:
        for i, raw in enumerate(csv.DictReader(f)):
            row = _norm_row(raw)
            sym = (row.get("eodhd_symbol") or "").strip()
            if not sym:
                continue
            verdict = (row.get("skill_verdict") or "").strip()
            star_info = stars.get(sym, {})
            truth_info = truth.get(sym, {})
            theme = (row.get("theme") or "").strip()
            tax = layer_for_theme(theme)
            picks.append({
                "id": i,
                "record_key": hashlib.sha256(json.dumps(
                    row, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")).hexdigest(),
                "record_date": (row.get("record_date") or "").strip(),
                "theme": theme,
                "layer": tax["layer"],
                "layer_name": tax["layer_name"],
                "subsector": tax["subsector"],
                "sublayer": tax.get("sublayer", ""),
                "lens": lens_of(tax.get("sublayer", "")),
                "symbol": sym,
                "name": (row.get("name") or "").strip(),
                "name_verified": truth_info.get("name_zh", ""),
                "market": market_of(sym),
                "market_label": MARKET_LABEL[market_of(sym)],
                "tier": (row.get("tier") or "").strip(),
                "archetypes": (row.get("archetypes") or "").strip(),
                "entry_price": (row.get("entry_price") or "").strip(),
                "currency": (row.get("currency") or "").strip(),
                "entry_stage": (row.get("entry_stage") or "").strip(),
                "verdict": verdict,
                "verdict_class": verdict_class(verdict),
                "trigger": extract_trigger(verdict),
                "thesis": (row.get("thesis") or "").strip(),
                "star_count": star_info.get("theme_count", 0),
                "stars": star_info.get("stars", ""),
                "star_themes": star_info.get("themes_list", ""),
            })
    return picks


def load_picks():
    return _load_picks(tuple(_file_version(p) for p in
                             (FORWARD_PICKS, TAXONOMY, CROSS_THEME, TICKER_TRUTH)))


def picks_version(picks=None):
    """内容版本与 CSV 行序无关；编辑判定后旧快照不能冒充新判定收益。"""
    rows = load_picks() if picks is None else picks
    keys = sorted(p["record_key"] for p in rows)
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def annotations_for(symbol: str):
    """某 ticker 的全部判定标注点(供 K 线打旗),按日期排序"""
    out = []
    for p in load_picks():
        if p["symbol"] != symbol:
            continue
        out.append({
            "date": p["record_date"],
            "verdict_class": p["verdict_class"],
            "verdict": p["verdict"],
            "trigger": p["trigger"],
            "entry_price": p["entry_price"],
            "currency": p["currency"],
            "entry_stage": p["entry_stage"],
            "theme": p["theme"],
            "tier": p["tier"],
            "thesis": p["thesis"],
        })
    return sorted(out, key=lambda x: x["date"])


def pick_name(symbol: str) -> str:
    truth = load_truth()
    if symbol in truth and truth[symbol]["name_zh"]:
        return truth[symbol]["name_zh"]
    for p in load_picks():
        if p["symbol"] == symbol:
            return p["name"]
    return symbol


# ---------- reports ----------

_DOGFOOD_RE = re.compile(r"Dogfood\s*#(\d+)")
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
_REPORT_META_RE = re.compile(r'<script\b[^>]*\bid=["\']serenity-report-meta["\'][^>]*>(.*?)</script>', re.S | re.I)
_VERDICT_RE = re.compile(
    r'一句话结论</div>\s*<p>(.*?)</p>', re.S)


def _report_market(filename: str) -> str:
    if any(k in filename for k in ("A加H", "A+H", "AH股", "A股港股")):
        return "CN"
    if "美股" in filename and "A股" in filename:
        return "MIXED"
    if "美股" in filename:
        return "US"
    if "港股" in filename and "A股" not in filename and "AH" not in filename:
        return "HK"
    if any(k in filename for k in ("A股", "AH股", "中国", "A 股")):
        return "CN"
    return "MIXED"


_REPORT_MARKET_LABEL = {"US": "美股", "HK": "港股", "CN": "A股/港股", "MIXED": "混合"}


def _report_layer(report_theme: str) -> dict:
    """报告 theme 是文件名首段(较松)→ best-effort 映射到层:精确→前缀→子串"""
    tmap = _theme_layer_map()
    if report_theme in tmap:
        return tmap[report_theme]
    for k, v in tmap.items():
        if k.startswith(report_theme) or report_theme.startswith(k):
            return v
    for k, v in tmap.items():
        if report_theme and (report_theme in k or k in report_theme):
            return v
    # 交叉/复合主题(如"低空经济+人形交集")→ 取最长公共前缀≥3 的 theme_key 所在层
    best, best_len = None, 0
    for k, v in tmap.items():
        n = 0
        for a, b in zip(report_theme, k):
            if a == b:
                n += 1
            else:
                break
        if n > best_len:
            best_len, best = n, v
    if best and best_len >= 3:
        return best
    return {"layer": 0, "layer_name": "未分类", "subsector": "未分类", "board": report_theme}


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=256)
def _report_text(path: str, version):
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _catalog():
    return _catalog_with_errors()[0]


def _catalog_with_errors():
    if not REPORT_CATALOG.exists():
        return {}, []
    try:
        obj = json.loads(REPORT_CATALOG.read_text(encoding="utf-8-sig"))
        if not isinstance(obj, dict) or not isinstance(obj.get("reports"), dict):
            raise ValueError("catalog must contain a reports object")
        return obj["reports"], []
    except (OSError, ValueError):
        return {}, ["catalog.json 无法解析或结构无效"]


def _metadata_values(value):
    """A malformed report must not take down the dashboard; retain diagnostics."""
    if not isinstance(value, dict):
        return {}, ["报告元数据必须是对象"]
    valid, errors = {}, []
    for key in ("theme", "report_date", "market", "dogfood", "classification"):
        if key not in value or value[key] is None:
            if key == "dogfood" and key in value:
                valid[key] = None
            continue
        item = value[key]
        ok = True
        if key == "theme":
            ok = isinstance(item, str) and bool(item.strip())
        elif key == "report_date":
            try:
                ok = isinstance(item, str) and datetime.strptime(item, "%Y-%m-%d").strftime("%Y-%m-%d") == item
            except (TypeError, ValueError):
                ok = False
        elif key == "market":
            ok = isinstance(item, str) and item in _REPORT_MARKET_LABEL
        elif key == "dogfood":
            ok = type(item) is int and item >= 0
        elif key == "classification":
            ok = item == "standalone"
        if ok:
            valid[key] = item
        else:
            errors.append("报告元数据字段无效: " + key)
    return valid, errors


def _report_theme(filename):
    # Only known suffixes delimit a theme: AI_Agent / AI_PCB remain intact.
    stem = Path(filename).stem
    return re.split(r"_(?=(?:A股|A加H|A\+H|AH股|美股|港股|中国|全球|完整|双镜头|分析报告|20\d{2}-))",
                    stem, maxsplit=1)[0].replace("_", " ")


@lru_cache(maxsize=4)
def _load_reports(cache_key: float):
    reports = []
    if not REPORTS_DIR.exists():
        return reports
    catalog, catalog_errors = _catalog_with_errors()
    for p in sorted(REPORTS_DIR.glob("*.html")):
        if not p.resolve().is_relative_to(REPORTS_DIR.resolve()):
            continue
        fname = p.name
        skip = "勿用" in fname or fname.startswith("demo_")
        try:
            head = _report_text(str(p), _file_version(p))
        except OSError:
            continue
        title_m = _TITLE_RE.search(head)
        title = title_m.group(1).strip() if title_m else fname.replace(".html", "")
        comment_m = _COMMENT_RE.search(head)
        comment = comment_m.group(1) if comment_m else ""
        dog_m = _DOGFOOD_RE.search(comment) or _DOGFOOD_RE.search(head[:4000])
        date_m = _DATE_RE.search(comment)
        verdict_m = _VERDICT_RE.search(head)
        verdict_text = _strip_tags(verdict_m.group(1))[:300] if verdict_m else ""
        embedded = _REPORT_META_RE.search(head)
        metadata_errors = list(catalog_errors)
        try:
            raw_meta = json.loads(embedded.group(1)) if embedded else {}
        except ValueError:
            raw_meta = {}
            metadata_errors.append("内嵌报告元数据不是有效 JSON")
        meta, embedded_errors = _metadata_values(raw_meta)
        override, override_errors = _metadata_values(catalog.get(fname, {}))
        meta.update(override)
        metadata_errors.extend(embedded_errors + override_errors)
        theme = meta.get("theme") or _report_theme(fname)
        tax = _report_layer(theme)
        if meta.get("classification") == "standalone":
            tax = {"layer": 0, "layer_name": "独立专题"}
        mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
        filename_date = _DATE_RE.search(fname)
        report_date = (meta.get("report_date") or
                       (filename_date.group(1) if filename_date else None) or
                       (date_m.group(1) if date_m else mtime))
        market = meta.get("market") or _report_market(fname)
        reports.append({
            "file": fname,
            "title": title,
            "theme": theme,
            "layer": tax["layer"],
            "layer_name": tax["layer_name"],
            "market": market,
            "market_label": _REPORT_MARKET_LABEL[market],
            "dogfood": meta.get("dogfood", int(dog_m.group(1)) if dog_m else None),
            "report_date": report_date,
            "mtime": mtime,
            "verdict_preview": verdict_text,
            "deprecated": skip,
            "size_kb": round(p.stat().st_size / 1024),
            "metadata_errors": metadata_errors,
        })
    # 最新在前
    reports.sort(key=lambda r: (r["report_date"], r["dogfood"] or 0), reverse=True)
    return reports


def load_reports():
    files = sorted(REPORTS_DIR.glob("*.html")) if REPORTS_DIR.exists() else []
    key = tuple(_file_version(p) for p in [TAXONOMY, REPORT_CATALOG, *files])
    return _load_reports(key)


def report_path(filename: str) -> Path | None:
    """安全取报告文件路径(防穿越:必须在已扫描清单内)"""
    valid = {r["file"] for r in load_reports()}
    if filename not in valid:
        return None
    resolved = (REPORTS_DIR / filename).resolve()
    return resolved if resolved.is_relative_to(REPORTS_DIR.resolve()) else None


# ---------- meta ----------

def theme_freshness():
    """每主题最近一次扫描日期 + 距今天数(F8:>30 天黄,>60 天红)"""
    picks = load_picks()
    last = {}
    for p in picks:
        if p["record_date"] > last.get(p["theme"], ""):
            last[p["theme"]] = p["record_date"]
    today = datetime.now()
    out = []
    for theme, d in last.items():
        try:
            age = (today - datetime.strptime(d, "%Y-%m-%d")).days
        except ValueError:
            continue
        out.append({
            "theme": theme, "last_scan": d, "age_days": age,
            "level": "red" if age > 60 else ("amber" if age > 30 else "green"),
        })
    out.sort(key=lambda x: -x["age_days"])
    return out


def _verdict_counts(rows):
    c = {"green": 0, "amber": 0, "red": 0, "other": 0}
    for r in rows:
        c[r["verdict_class"]] += 1
    return c


def taxonomy_tree():
    """五层蛋糕树:层 → 板块(subsector)→ board,带 pick 统计/判定分布/最新报告/新鲜度。
    驱动蛋糕地图页。"""
    tax = load_taxonomy()
    picks = load_picks()
    reports = [r for r in load_reports() if not r["deprecated"]]
    # 按 theme 聚合 picks
    picks_by_theme = {}
    for p in picks:
        picks_by_theme.setdefault(p["theme"], []).append(p)
    # 按 theme_key 找最新报告(报告 theme 是松前缀,这里宽松匹配)
    freshness = {f["theme"]: f for f in theme_freshness()}

    def latest_report_for(theme_key):
        if not theme_key:
            return None
        cand = [r for r in reports
                if theme_key.startswith(r["theme"]) or r["theme"].startswith(theme_key)
                or r["theme"] in theme_key]
        if not cand:
            return None
        r = sorted(cand, key=lambda x: x["report_date"], reverse=True)[0]
        return {"file": r["file"], "title": r["title"], "report_date": r["report_date"], "dogfood": r["dogfood"]}

    layers = []
    for ln in (1, 2, 3, 4, 5):
        rows = [r for r in tax if r["layer"] == ln]
        if not rows:
            continue
        layer_name = rows[0]["layer_name"]
        # 板块分组(保持 CSV 内出现顺序)
        sub_order = []
        subs = {}
        for r in rows:
            if r["subsector"] not in subs:
                subs[r["subsector"]] = []
                sub_order.append(r["subsector"])
            subs[r["subsector"]].append(r)
        subsectors = []
        l_pick = 0
        l_scanned = l_planned = 0
        l_vc = {"green": 0, "amber": 0, "red": 0, "other": 0}
        for sname in sub_order:
            boards = []
            for r in subs[sname]:
                tp = picks_by_theme.get(r["theme_key"], []) if r["theme_key"] else []
                vc = _verdict_counts(tp)
                fr = freshness.get(r["theme_key"]) if r["theme_key"] else None
                if r["status"] == "scanned":
                    l_scanned += 1
                elif r["status"] == "planned":
                    l_planned += 1
                l_pick += len(tp)
                for k in l_vc:
                    l_vc[k] += vc[k]
                boards.append({
                    "board": r["board"], "theme_key": r["theme_key"],
                    "sublayer": r["sublayer"],
                    "sublayer_name": SUBLAYER_META.get(r["sublayer"], ""),
                    "lens": lens_of(r["sublayer"]),
                    "status": r["status"], "market": r["market"],
                    "priority": r["priority"], "leaders": r["leaders"],
                    "bottleneck_pureplays": r["bottleneck_pureplays"], "note": r["note"],
                    "pick_count": len(tp), "verdict_counts": vc,
                    "last_scan": fr["last_scan"] if fr else None,
                    "freshness_level": fr["level"] if fr else None,
                    "latest_report": latest_report_for(r["theme_key"]),
                })
            subsectors.append({
                "subsector": sname,
                "market": subs[sname][0]["market"],
                "leaders": subs[sname][0]["leaders"],
                "boards": boards,
            })
        total_boards = sum(len(s["boards"]) for s in subsectors)
        strength = ("strong" if l_scanned >= 4 else "partial" if l_scanned >= 2
                    else "thin" if l_scanned >= 1 else "none")
        layers.append({
            "layer": ln, "layer_name": layer_name, "role": LAYER_ROLES.get(ln, ""),
            "coverage_strength": strength,
            "stat": {"scanned": l_scanned, "planned": l_planned, "total_boards": total_boards,
                     "pick_count": l_pick, "verdict_counts": l_vc},
            "subsectors": subsectors,
        })
    return {
        "framework": "黄仁勋 AI 五层蛋糕(2026-03-10):①能源 ②芯片 ③基础设施 ④模型 ⑤应用",
        "layers": layers,
        "sublayer_meta": SUBLAYER_META,
        "hunt_sublayers": sorted(HUNT_SUBLAYERS),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def load_meta():
    picks = load_picks()
    reports = load_reports()
    themes = sorted({p["theme"] for p in picks})
    markets = sorted({p["market"] for p in picks})
    verdicts = {"green": 0, "amber": 0, "red": 0, "other": 0}
    for p in picks:
        verdicts[p["verdict_class"]] += 1
    starred = sorted(
        [p for p in {x["symbol"]: x for x in picks}.values() if p["star_count"] >= 2],
        key=lambda x: -x["star_count"],
    )
    fresh = [r for r in reports if not r["deprecated"]]
    tree = taxonomy_tree()
    layer_rollup = [
        {"layer": L["layer"], "layer_name": L["layer_name"],
         "coverage_strength": L["coverage_strength"],
         "scanned": L["stat"]["scanned"], "planned": L["stat"]["planned"],
         "pick_count": L["stat"]["pick_count"], "verdict_counts": L["stat"]["verdict_counts"]}
        for L in tree["layers"]
    ]
    return {
        "total_picks": len(picks),
        "total_reports": len(fresh),
        "themes": themes,
        "layer_rollup": layer_rollup,
        "markets": markets,
        "market_labels": MARKET_LABEL,
        "verdict_counts": verdicts,
        "star_nodes": [
            {"symbol": s["symbol"], "name": s["name"], "star_count": s["star_count"], "stars": s["stars"]}
            for s in starred[:12]
        ],
        "freshness": theme_freshness(),
        "latest_reports": [
            {"file": r["file"], "title": r["title"], "theme": r["theme"],
             "market_label": r["market_label"], "report_date": r["report_date"],
             "dogfood": r["dogfood"]}
            for r in fresh[:3]
        ],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
