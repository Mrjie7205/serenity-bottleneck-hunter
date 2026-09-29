#!/usr/bin/env python3
"""
Provider-agnostic price/momentum helper for the Serenity bottleneck-hunter skill.

按优先级回退抓历史价,**严禁靠网页猜价格**——SKILL Step 6 的 stage 判定必须基于真实数据:
  1) EODHD            (若环境变量 EODHD_API_KEY 已设;**全球覆盖最广,海外股优先**)
  2) yfinance         (无需 key,**美股覆盖好,海外股常有 gap**)
  3) 失败 → 报错退出 (do NOT silently guess)

返回每只票的 JSON:last、6 月区间位置、距高点、1/3 月动量、stage 标签。

CLI:
    python scripts/price.py AEHR NVTS VICR IPWR POWI            # 默认走 yfinance(无 EODHD key)
    EODHD_API_KEY=xxx python scripts/price.py XFAB.STU AEHR     # 海外股请用 EODHD

可作为模块导入:
    from price import analyze, fetch_history
"""
import json, os, sys, urllib.request, datetime, math


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _clean(rows):
    """Validate provider bars; never infer corporate actions from a price jump."""
    if not isinstance(rows, list):
        return None
    by_date = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not all(_finite(row.get(k)) and row[k] > 0 for k in ("open", "high", "low", "close")):
            continue
        try:
            date = datetime.date.fromisoformat(row["date"]).isoformat()
        except (KeyError, TypeError, ValueError):
            continue
        if row["high"] < max(row["open"], row["close"], row["low"]) or row["low"] > min(row["open"], row["close"]):
            continue
        bar = {"date": date, **{k: row[k] for k in ("open", "high", "low", "close")}}
        if date in by_date and by_date[date] != bar:
            return None
        by_date[date] = bar
    return [by_date[d] for d in sorted(by_date)] or None


_ASHARE_SUFFIXES = (".SHG", ".SHE", ".SS", ".SZ", ".SH", ".BJ")


def _yfinance_symbol(symbol):
    symbol = symbol.strip().upper()
    for source, target in ((".US", ""), (".SHG", ".SS"), (".SH", ".SS"), (".SHE", ".SZ")):
        if symbol.endswith(source):
            return symbol[:-len(source)] + target
    return symbol


def _fetch_akshare_qfq(symbol, days=400):
    try:
        import akshare as ak
        end = datetime.date.today()
        df = ak.stock_zh_a_hist(symbol=symbol.split(".")[0], period="daily",
            start_date=(end - datetime.timedelta(days=days)).strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"), adjust="qfq", timeout=20)
        if df is None or df.empty:
            return None
        return [{"date": str(r["日期"]), "open": float(r["开盘"]), "high": float(r["最高"]),
                 "low": float(r["最低"]), "close": float(r["收盘"])} for _, r in df.iterrows()]
    except Exception:
        return None


def _adjust_eodhd(rows):
    """Scale OHLC only by the provider's explicit adjusted_close / close factor."""
    if not isinstance(rows, list) or not rows:
        return None
    out = []
    for row in rows:
        if not isinstance(row, dict) or not all(_finite(row.get(k)) and row[k] > 0
                for k in ("open", "high", "low", "close", "adjusted_close")):
            return None  # Do not mix raw and adjusted bars within one series.
        factor = row["adjusted_close"] / row["close"]
        out.append({"date": row.get("date"), **{k: row[k] * factor for k in ("open", "high", "low")},
                    "close": row["adjusted_close"]})
    return _clean(out)

EODHD_KEY = os.environ.get("EODHD_API_KEY", "").strip()
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    EODHD_KEY = os.environ.get("EODHD_API_KEY", "").strip()
except ImportError:
    pass
if EODHD_KEY == "your_eodhd_key_here":
    EODHD_KEY = ""


def _fetch_eodhd(symbol, days=400):
    end = datetime.date.today().isoformat()
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    url = f"https://eodhd.com/api/eod/{symbol}?api_token={EODHD_KEY}&from={start}&to={end}&period=d&fmt=json"
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                d = json.load(r)
                if isinstance(d, list) and d:
                    return _adjust_eodhd(d)
        except Exception:
            pass
    return None


def _fetch_yf(symbol, days=400):
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        t = yf.Ticker(_yfinance_symbol(symbol))
        end = datetime.date.today() + datetime.timedelta(days=1)
        h = t.history(start=(end - datetime.timedelta(days=max(days, 400))).isoformat(),
                      end=end.isoformat(), auto_adjust=True, repair=False, timeout=20)
        if h is None or len(h) == 0:
            return None
        return [{"date": idx.strftime("%Y-%m-%d"),
                 "open": float(row["Open"]), "high": float(row["High"]),
                 "low": float(row["Low"]),   "close": float(row["Close"])}
                for idx, row in h.iterrows()]
    except Exception:
        return None


def fetch_history(symbol, days=400):
    """A股:akshare qfq→Yahoo→EODHD；其他:EODHD→Yahoo。只接收源提供的复权。"""
    symbol = symbol.strip().upper()
    is_a = symbol.endswith(_ASHARE_SUFFIXES)
    if is_a:
        data = _clean(_fetch_akshare_qfq(symbol, days))
        if data:
            return data, "akshare-qfq"
        if not symbol.endswith(".BJ"):
            data = _clean(_fetch_yf(_yfinance_symbol(symbol), days))
            if data:
                return data, "yfinance-qfq"
    if EODHD_KEY:
        data = _clean(_fetch_eodhd(symbol, days))
        if data:
            return data, "eodhd-adj"
    if is_a:
        return None, None
    data = _clean(_fetch_yf(_yfinance_symbol(symbol), days))
    if data:
        return data, "yfinance-adj"
    return None, None


def analyze(symbol, days=400):
    data, prov = fetch_history(symbol, days)
    if data is None:
        return {"ticker": symbol,
                "error": "no usable adjusted data (check dependencies, network/certificates, provider coverage and exchange suffix)"}
    closes = [x["close"] for x in data]
    last = closes[-1]
    last_date = data[-1]["date"]
    w6 = data[-126:] if len(data) >= 126 else data
    lo6 = min(x["low"] for x in w6)
    hi6 = max(x["high"] for x in w6)
    rng_pos = round((last - lo6) / (hi6 - lo6) * 100) if hi6 > lo6 else 50
    off_high = round((last / hi6 - 1) * 100, 1)
    sma50 = sum(closes[-50:]) / min(50, len(closes))
    r1m = round((last / closes[-21] - 1) * 100, 1) if len(closes) > 21 else None
    r3m = round((last / closes[-63] - 1) * 100, 1) if len(closes) > 63 else None
    up = last > sma50
    # stage heuristic — 同时看 1 月动量(避免把刚暴拉的标判成 early)
    hot_1m = (r1m is not None and r1m > 40)
    at_top = (rng_pos >= 95 and (r3m or 0) > 30)
    if (r3m is not None and r3m > 120) or hot_1m or at_top:
        stage = "extended/parabolic (already ran hot -> late for Mode A; DON'T chase, wait for pullback)"
    elif up and r3m is not None and 5 < r3m <= 120 and not hot_1m:
        stage = "early-uptrend (reasonable Mode-A entry: theme igniting, not yet overextended)"
    elif not up and r3m is not None and r3m < -10:
        stage = "downtrend/basing (only Mode B 'buy the dip' if catalyst is non-material)"
    else:
        stage = "range/neutral"
    return {
        "ticker": symbol,
        "provider": prov,
        "last": round(last, 2),
        "last_date": last_date,
        "range_pos_6mo_pct": rng_pos,
        "pct_off_6mo_high": off_high,
        "ret_1m_pct": r1m,
        "ret_3m_pct": r3m,
        "above_sma50": up,
        "stage": stage,
        "high_6mo": round(hi6, 4),
        "low_6mo": round(lo6, 4),
        "observations": len(data),
        "quality_warnings": (["少于126个交易日，6月区间样本不完整"] if len(data) < 126 else [])
            + (["A股首选复权源不可用，EODHD复权结果需独立核对"]
               if symbol.upper().endswith(_ASHARE_SUFFIXES) and prov == "eodhd-adj" else []),
    }


# ── 估值/速度字段(二轴判定的「基本面跟不跟得上」轴)= 多源 ──
# A股→akshare(中国源:百度 PE-TTM + 东财券商一致预期 forward + 东财财务增速);美股/海外→yfinance。
# 实测:yfinance 的 A股 trailing PE / 盈利增速 基本准,但 forward 系统性偏低(乐观)→ A股 forward 用 akshare 更可信;
# 且两源对 trailing 可交叉验证。每个 akshare 接口独立 try(本机代理会拦部分 endpoint),缺字段由 yfinance 兜底。
_AK_FC = None  # 东财全市场一致预期表,缓存一次(~2700 只,拉一次 ~35s)

def _ak_forecast():
    global _AK_FC
    if _AK_FC is None:
        import akshare as ak
        _AK_FC = ak.stock_profit_forecast_em()
    return _AK_FC

def _ak_valuation(code, last=None):
    out = {"forward_pe": None, "trailing_pe": None, "peg": None, "eps_growth": None, "rev_growth": None, "src": "akshare"}
    import akshare as ak
    try:  # ① PE-TTM(百度,序列尾 = 最新)
        df = ak.stock_zh_valuation_baidu(symbol=code, indicator="市盈率(TTM)", period="近一年")
        out["trailing_pe"] = round(float(df["value"].iloc[-1]), 2)
    except Exception:
        pass
    try:  # ② forward = 现价 ÷ 次年券商一致预期 EPS(真 forward,非 yfinance 乐观值)
        fc = _ak_forecast(); row = fc[fc["代码"] == code]
        forecast_year = datetime.date.today().year + 1
        col = next((c for c in fc.columns if str(forecast_year) in str(c) and "每股收益" in str(c)), None)
        if not row.empty and col and last:
            eps = float(row[col].iloc[0])
            if eps > 0:
                out["forward_pe"] = round(last / eps, 2)
    except Exception:
        pass
    try:  # ③ 增速:财务摘要 归母净利润 / 营业总收入 最新 vs 4 季前 YoY
        fa = ak.stock_financial_abstract(symbol=code)
        dc = sorted([c for c in fa.columns if str(c).isdigit() and len(str(c)) == 8], reverse=True)
        def yoy(metric):
            r = fa[fa["指标"].astype(str) == metric]
            if r.empty or len(dc) < 5:
                return None
            try:
                cur, pri = float(r[dc[0]].iloc[0]), float(r[dc[4]].iloc[0])
                return round((cur - pri) / abs(pri) * 100, 1) if pri else None
            except Exception:
                return None
        out["eps_growth"] = yoy("归母净利润")
        out["rev_growth"] = yoy("营业总收入")
    except Exception:
        pass
    if out["trailing_pe"] and out["eps_growth"] and out["eps_growth"] > 0:  # 粗略 PEG
        out["peg"] = round(out["trailing_pe"] / out["eps_growth"], 2)
    for field in ("forward_pe", "trailing_pe", "peg", "eps_growth", "rev_growth"):
        if not _finite(out[field]):
            out[field] = None
    return out

def _yf_valuation(yf_symbol, info=None):
    yf_symbol = _yfinance_symbol(yf_symbol)
    out = {"forward_pe": None, "trailing_pe": None, "peg": None, "eps_growth": None, "rev_growth": None, "src": "yfinance"}
    if info is None:
        try:
            import yfinance as yf
            info = yf.Ticker(yf_symbol).info or {}
        except Exception:
            return out
    def g(k):
        v = info.get(k)
        return round(float(v), 2) if _finite(v) else None
    out["forward_pe"] = g("forwardPE"); out["trailing_pe"] = g("trailingPE")
    out["peg"] = g("pegRatio") or g("trailingPegRatio")
    eg = g("earningsGrowth")
    if eg is None:
        eg = g("earningsQuarterlyGrowth")
    out["eps_growth"] = round(eg * 100, 1) if eg is not None else None
    rg = g("revenueGrowth")
    out["rev_growth"] = round(rg * 100, 1) if rg is not None else None
    return out

_A_SUFFIX = (".SS", ".SZ", ".SHG", ".SHE", ".SH")
def valuation(symbol, info=None, last=None):
    """多源估值:A股(.SS/.SZ/.SHG/.SHE 或 6 位数)→ akshare,缺字段 yfinance 兜底;美股/海外 → yfinance。
    传 last(现价)供 A股算 forward。返回含 src 标来源,便于报告标注与交叉验证。"""
    su = (symbol or "").upper()
    is_a = su.endswith(_A_SUFFIX) or (len(su) >= 6 and su[:6].isdigit())
    if not is_a:
        return _yf_valuation(symbol, info)
    code = su.split(".")[0][:6]
    try:
        out = _ak_valuation(code, last)
    except Exception:
        out = None
    if not out or all(out.get(k) is None for k in ("trailing_pe", "forward_pe", "eps_growth")):
        v = _yf_valuation(symbol, info); v["src"] = "yfinance(ak不可用)"; return v
    if any(out.get(k) is None for k in ("trailing_pe", "forward_pe", "eps_growth", "rev_growth")):  # 缺字段兜底
        yv = _yf_valuation(symbol, info); filled = False
        for k in ("forward_pe", "trailing_pe", "peg", "eps_growth", "rev_growth"):
            if out.get(k) is None and yv.get(k) is not None:
                out[k] = yv[k]; filled = True
        if filled:
            out["src"] = "akshare+yf兜底"
    return out


if __name__ == "__main__":
    syms = sys.argv[1:]
    if not syms:
        print("usage: python scripts/price.py TICKER [TICKER ...]", file=sys.stderr)
        print("notes: 优先 EODHD (set EODHD_API_KEY),回退 yfinance。海外股必须 EODHD。", file=sys.stderr)
        sys.exit(1)
    for s in syms:
        print(json.dumps(analyze(s), ensure_ascii=False))
