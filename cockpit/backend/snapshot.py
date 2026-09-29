"""snapshot.py — 全量价格快照引擎(M3)
对全部跟踪标的各抓一次历史价(EODHD→yfinance)→ 计算:
  · 当前指标:last / rng / off / 1m / 3m / SMA50 / stage
  · 每条判定:since-call 收益 + 同期基准收益 + 超额(α)
写 snapshot.json。计分卡 / Stage 看板 / 跟踪表实时列全部由它驱动。

成本随跟踪表与供应商回退次数变化，手动按钮触发;
auto 模式需 .env 设 SNAPSHOT_AUTO=1(每日 16:40)。
"""
import json
import logging
import math
import sys
import threading
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).resolve().parent
import settings

import data  # noqa: E402

sys.path.insert(0, str(data.SKILL / "scripts"))
from price import fetch_history  # noqa: E402

SNAPSHOT_FILE = settings.STATE_DIR / "snapshot.json"
SNAPSHOT_SCHEMA_VERSION = 2

# 基准 ETF 代理(指数本身 EODHD 套餐常不含,ETF 最稳)
BENCHMARKS = {
    "US": "QQQ.US",        # 纳指100
    "CN": "510300.SHG",    # 沪深300 ETF
    "HK": "2800.HK",       # 盈富(恒指)
    "JP": "EWJ.US",        # MSCI Japan
    "OTHER": "ACWI.US",    # 全球
}

_lock = threading.Lock()
_run_lock = threading.Lock()
_progress = {"running": False, "done": 0, "total": 0, "phase": "", "error": None}
_UNSET = object()


class SnapshotBusyError(RuntimeError):
    """所有入口共享的快照任务互斥。"""


class SnapshotIncompleteError(RuntimeError):
    """输入变化或行情完全不可用时保留正式快照。"""


def progress():
    with _lock:
        return dict(_progress)


def _set(done=None, total=None, phase=None, running=None, error=_UNSET):
    with _lock:
        if done is not None:
            _progress["done"] = done
        if total is not None:
            _progress["total"] = total
        if phase is not None:
            _progress["phase"] = phase
        if running is not None:
            _progress["running"] = running
        if error is not _UNSET:
            _progress["error"] = error


def _claim_run():
    settings.require_personal_data()
    if not _run_lock.acquire(blocking=False):
        raise SnapshotBusyError("快照正在构建中")
    _set(done=0, total=0, phase="准备", running=True, error=None)


def _run_claimed_snapshot(limit):
    try:
        result = _build_snapshot(limit)
        _set(phase="局部检查完成" if limit > 0 else "完成")
        return result
    except Exception as exc:
        _set(phase="失败", error=_public_error(exc))
        raise
    finally:
        _set(running=False)
        _run_lock.release()


def run_snapshot(limit: int = 0):
    """定时/同步入口：与手动后台入口共用同一把任务锁。"""
    _claim_run()
    return _run_claimed_snapshot(limit)


def start_snapshot(limit: int = 0):
    """先占锁再启动线程，避免连续请求或调度任务之间的竞态。"""
    _claim_run()

    def work():
        try:
            _run_claimed_snapshot(limit)
        except Exception:
            # 错误已写入 progress，日志保留 traceback 供排查。
            logging.getLogger(__name__).exception("快照构建失败")

    try:
        worker = threading.Thread(target=work, daemon=True)
        worker.start()
    except Exception as exc:
        _set(running=False, phase="失败", error=_public_error(exc))
        _run_lock.release()
        raise
    return worker


def _public_error(exc):
    # 第三方异常及文件错误可能带访问令牌或本机绝对路径，仅写入服务日志。
    if isinstance(exc, SnapshotIncompleteError):
        return str(exc)
    return f"快照构建失败（{type(exc).__name__}），请查看服务日志后重试"


def _metrics(hist):
    """从一段日线历史算 9 字段(与 price.analyze 同口径,避免重复抓取)"""
    closes = [x["close"] for x in hist]
    last = closes[-1]
    w6 = hist[-126:] if len(hist) >= 126 else hist
    lo6 = min(x["low"] for x in w6)
    hi6 = max(x["high"] for x in w6)
    rng = round((last - lo6) / (hi6 - lo6) * 100) if hi6 > lo6 else 50
    off = round((last / hi6 - 1) * 100, 1)
    sma50 = sum(closes[-50:]) / min(50, len(closes))
    r1m = round((last / closes[-21] - 1) * 100, 1) if len(closes) > 21 else None
    r3m = round((last / closes[-63] - 1) * 100, 1) if len(closes) > 63 else None
    up = last > sma50
    hot_1m = (r1m is not None and r1m > 40)
    at_top = (rng >= 95 and (r3m or 0) > 30)
    if (r3m is not None and r3m > 120) or hot_1m or at_top:
        stage, stage_key = "extended/parabolic", "parabolic"
    elif up and r3m is not None and 5 < r3m <= 120 and not hot_1m:
        stage, stage_key = "early-uptrend", "early"
    elif not up and r3m is not None and r3m < -10:
        stage, stage_key = "downtrend/basing", "deep"
    else:
        stage, stage_key = "range/neutral", "range"
    return {
        "last": round(last, 2),
        "last_date": hist[-1]["date"],
        "range_pos_6mo_pct": rng,
        "pct_off_6mo_high": off,
        "ret_1m_pct": r1m,
        "ret_3m_pct": r3m,
        "above_sma50": up,
        "stage": stage,
        "stage_key": stage_key,
    }


def _close_on_or_after(hist, date_str):
    """record_date 当日(或之后第一个交易日)的收盘价"""
    for x in hist:
        if x["date"] >= date_str:
            return x["close"]
    return None


def _build_snapshot(limit: int = 0):
    """全量重建快照。limit>0 只跑前 N 个 symbol(测试/省额度)。"""
    picks = data.load_picks()
    symbols = sorted({p["symbol"] for p in picks})
    if limit > 0:
        symbols = symbols[:limit]

    _set(done=0, total=len(symbols) + len(BENCHMARKS), phase="基准")

    # 1) 基准历史(每市场一次)
    bench_hist = {}
    n = 0
    for mkt, bsym in BENCHMARKS.items():
        hist, _prov = fetch_history(bsym, days=800)
        if hist:
            bench_hist[mkt] = hist
        n += 1
        _set(done=n)

    # 2) 个股
    _set(phase="个股")
    sym_data = {}
    errors = []
    for sym in symbols:
        hist, prov = fetch_history(sym, days=800)
        n += 1
        _set(done=n)
        if not hist:
            errors.append(sym)
            continue
        m = _metrics(hist)
        m["provider"] = prov
        sym_data[sym] = {"metrics": m, "_hist": hist}

    # 3) 逐判定算 since-call / α
    pick_calc = {}
    for p in picks:
        sym = p["symbol"]
        if sym not in sym_data:
            continue
        hist = sym_data[sym]["_hist"]
        last = sym_data[sym]["metrics"]["last"]
        base = _close_on_or_after(hist, p["record_date"])
        if not base or base <= 0:
            continue
        since = round((last / base - 1) * 100, 1)
        entry = {"since_call_pct": since, "bench_pct": None, "alpha_pct": None}
        bh = bench_hist.get(p["market"])
        if bh:
            bbase = _close_on_or_after(bh, p["record_date"])
            blast = bh[-1]["close"]
            if bbase and bbase > 0:
                bret = round((blast / bbase - 1) * 100, 1)
                entry["bench_pct"] = bret
                entry["alpha_pct"] = round(since - bret, 1)
        pick_calc[p["record_key"]] = entry

    # 数据质检(防 EODHD A股送转脏数据重现):A股是否全走前复权源 + 复权后是否仍有漏网除权跳空
    _ADJ_OK = ("akshare-qfq", "yfinance-qfq")
    dq = {"ashare_total": 0, "ashare_adjusted": 0, "ashare_raw_eodhd": [], "split_suspects": []}
    for s, v in sym_data.items():
        prov = v["metrics"].get("provider", "")
        if s.endswith((".SHG", ".SHE", ".BJ")):
            dq["ashare_total"] += 1
            if prov in _ADJ_OK:
                dq["ashare_adjusted"] += 1
            else:
                dq["ashare_raw_eodhd"].append(s)  # A股掉到非前复权源 → 价格变化或复权来源需核对
        h = v.get("_hist") or []
        w = h[-130:] if len(h) > 130 else h       # 近 ~6 月
        for i in range(1, len(w)):
            pc, cc = w[i - 1].get("close"), w[i].get("close")
            if pc and cc and (cc / pc < 0.78 or cc / pc > 1.45):  # 大幅跳空可能是事件或复权问题，仅提示核对，不自动修平
                dq["split_suspects"].append(s)
                break

    for v in sym_data.values():
        v.pop("_hist", None)

    out = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "data_version": data.picks_version(picks),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol_count": len(sym_data),
        "error_count": len(errors),
        "errors": errors[:30],
        "benchmark_errors": [m for m in BENCHMARKS if m not in bench_hist],
        "data_quality": dq,
        "partial": limit > 0,
        "benchmarks": {m: BENCHMARKS[m] for m in bench_hist},
        "symbols": {s: v["metrics"] for s, v in sym_data.items()},
        "picks": pick_calc,
    }
    if not picks:
        raise SnapshotIncompleteError("跟踪表为空，保留上次完整快照")
    # 少量停牌/退市标的缺价沿用原有可用结果语义，明确披露覆盖缺口。
    incomplete = bool(errors or out["benchmark_errors"])
    out["complete"] = not incomplete and limit == 0
    if not sym_data:
        raise SnapshotIncompleteError("未获取到任何个股行情，保留上次快照")
    # 局部试跑单独保存，绝不覆盖正式快照。
    target = SNAPSHOT_FILE
    if limit > 0:
        target = SNAPSHOT_FILE.with_name("snapshot.partial.json")
    # 抓价期间跟踪表也可能被编辑，不能把旧输入的结果发布为当前数据。
    if out["data_version"] != data.picks_version():
        raise SnapshotIncompleteError("构建期间跟踪表已变化，请重新刷新；保留上次完整快照")
    if limit == 0:
        previous = _read_snapshot()
        if (isinstance(previous, dict) and
                previous.get("schema_version") == SNAPSHOT_SCHEMA_VERSION and
                previous.get("complete") and not previous.get("partial") and
                previous.get("error_count", 0) == 0 and not previous.get("benchmark_errors")):
            _write_snapshot(SNAPSHOT_FILE.with_name("snapshot.last-complete.json"), previous)
    _write_snapshot(target, out)
    return {**{k: out[k] for k in
               ("generated_at", "symbol_count", "error_count", "partial", "complete")},
            "published": limit == 0}


def _write_snapshot(target, out):
    # 原子写:避免前端在写入瞬间读到半截 JSON。
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)


def _read_snapshot():
    source = settings.DEMO_DIR / "snapshot.json" if settings.DEMO else SNAPSHOT_FILE
    if not source.exists():
        return None
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _refresh_reason(snap):
    if not isinstance(snap, dict):
        return "快照无法读取，请刷新价格快照"
    if snap.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        return "旧快照缺少稳定记录标识，请刷新价格快照"
    if snap.get("partial"):
        return "现有文件是局部快照，请刷新完整价格快照"
    if snap.get("data_version") != data.picks_version():
        return "跟踪记录已变化，请刷新价格快照"
    if not isinstance(snap.get("symbols"), dict) or not isinstance(snap.get("picks"), dict):
        return "快照内容不完整，请刷新价格快照"
    invalid = "快照内容不完整或字段无效，请刷新价格快照"
    try:
        datetime.strptime(snap["generated_at"], "%Y-%m-%d %H:%M:%S")
    except (KeyError, TypeError, ValueError):
        return invalid
    for key in ("symbol_count", "error_count"):
        value = snap.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return invalid
    if snap["symbol_count"] != len(snap["symbols"]) or not snap["symbols"]:
        return invalid

    def number(value, nullable=False):
        return ((nullable and value is None) or
                (type(value) in (int, float) and math.isfinite(value)))

    for symbol, metrics in snap["symbols"].items():
        if not isinstance(symbol, str) or not symbol or not isinstance(metrics, dict):
            return invalid
        if metrics.get("stage_key") not in STAGE_ORDER:
            return invalid
        for key in ("last", "range_pos_6mo_pct"):
            if not number(metrics.get(key)):
                return invalid
        for key in ("ret_1m_pct", "ret_3m_pct"):
            if key not in metrics or not number(metrics[key], nullable=True):
                return invalid
    for record_key, calculation in snap["picks"].items():
        if not isinstance(record_key, str) or not record_key or not isinstance(calculation, dict):
            return invalid
        if not number(calculation.get("since_call_pct")):
            return invalid
        for key in ("bench_pct", "alpha_pct"):
            if key not in calculation or not number(calculation[key], nullable=True):
                return invalid
    return None


def load_snapshot():
    """仅返回与当前跟踪记录对应的完整 v2 快照，旧行号快照安全失效。"""
    snap = _read_snapshot()
    return snap if snap is not None and _refresh_reason(snap) is None else None


def status():
    stored = _read_snapshot()
    reason = _refresh_reason(stored) if settings.DEMO or SNAPSHOT_FILE.exists() else None
    snap = stored if reason is None else None
    st = {"exists": snap is not None, "progress": progress(),
          "refresh_required": reason is not None, "message": reason}
    if snap:
        st.update({
            "generated_at": snap["generated_at"],
            "symbol_count": snap["symbol_count"],
            "error_count": snap["error_count"],
            "partial": snap.get("partial", False),
            "complete": snap.get("complete", False),
            "benchmark_errors": snap.get("benchmark_errors", []),
            "data_quality": snap.get("data_quality"),
        })
    return {**st, **settings.mode_info()}


# ---------- 衍生视图 ----------

STAGE_ORDER = ["deep", "range", "early", "parabolic"]
STAGE_LABEL = {
    "deep": "深底 / 筑底",
    "range": "震荡 / 中性",
    "early": "启动(Mode A)",
    "parabolic": "过热 / 抛物线",
}


def _latest_pick_per_symbol(picks):
    by_sym = {}
    for p in sorted(picks, key=lambda x: x["record_date"]):
        by_sym[p["symbol"]] = p
    return by_sym


def stage_board():
    """Stage 流转看板:当前快照里每只标的落在哪一档(F5)"""
    snap = load_snapshot()
    if not snap:
        return {"available": False, "columns": []}
    latest = _latest_pick_per_symbol(data.load_picks())
    cols = {k: [] for k in STAGE_ORDER}
    for sym, m in snap["symbols"].items():
        p = latest.get(sym)
        if not p:
            continue
        cols[m["stage_key"]].append({
            "symbol": sym,
            "name": p["name"],
            "theme": p["theme"],
            "verdict_class": p["verdict_class"],
            "star_count": p["star_count"],
            "ret_1m_pct": m["ret_1m_pct"],
            "ret_3m_pct": m["ret_3m_pct"],
            "range_pos_6mo_pct": m["range_pos_6mo_pct"],
        })
    for k in cols:
        cols[k].sort(key=lambda x: (-x["star_count"], -(x["ret_1m_pct"] or -999)))
    return {
        "available": True,
        "generated_at": snap["generated_at"],
        "columns": [
            {"key": k, "label": STAGE_LABEL[k], "count": len(cols[k]), "items": cols[k]}
            for k in STAGE_ORDER
        ],
    }


def scorecard():
    """判定计分卡(F4):各分组的 since-call / α 统计。
    样本 < 30 天的判定单独计数(观察期未满)。"""
    if settings.DEMO:
        return {"available": False, "demo": True,
                "message": "演示只包含历史价格快照，没有逐日价格和基准序列，因此不展示收益率或超额收益。"}
    snap = load_snapshot()
    if not snap:
        return {"available": False}
    picks = data.load_picks()
    pc = snap["picks"]
    today = datetime.now()

    rows = []
    seeds_n = 0
    for p in picks:
        # 历史种子 = 回填的 Serenity 原始 call(2026-01-02 锚点价),非本框架实时判定
        # —— 属样本内重建,计入会循环论证灌水 🟢 α(README 校准说明明令禁止)
        if "历史种子" in p["verdict"]:
            seeds_n += 1
            continue
        c = pc.get(p["record_key"])
        if not c or c["alpha_pct"] is None:
            continue
        try:
            age = (today - datetime.strptime(p["record_date"], "%Y-%m-%d")).days
        except ValueError:
            age = 0
        rows.append({**p, **c, "age_days": age})

    def agg(items):
        n = len(items)
        if n == 0:
            return {"n": 0}
        alphas = [x["alpha_pct"] for x in items]
        sinces = [x["since_call_pct"] for x in items]
        wins = len([a for a in alphas if a > 0])
        return {
            "n": n,
            "avg_since": round(sum(sinces) / n, 1),
            "avg_alpha": round(sum(alphas) / n, 1),
            "med_alpha": round(sorted(alphas)[n // 2], 1),
            "win_rate": round(wins / n * 100),
            "young_n": len([x for x in items if x["age_days"] < 30]),
        }

    def group_by(keyfn, labels=None):
        groups = {}
        for r in rows:
            for k in keyfn(r):
                groups.setdefault(k, []).append(r)
        out = []
        for k, items in groups.items():
            out.append({"key": k, "label": (labels or {}).get(k, k), **agg(items)})
        out.sort(key=lambda g: -(g.get("avg_alpha") or -999))
        return out

    verdict_labels = {"green": "🟢 候选", "amber": "🟡 观望", "red": "🔴 排除"}
    by_verdict = group_by(
        lambda r: [r["verdict_class"]] if r["verdict_class"] in verdict_labels else [],
        verdict_labels)
    # 方法论 alpha = 🟢 平均超额 − 🔴 平均超额
    g = next((x for x in by_verdict if x["key"] == "green"), None)
    r_ = next((x for x in by_verdict if x["key"] == "red"), None)
    spread = None
    if g and r_ and g["n"] and r_["n"]:
        spread = round(g["avg_alpha"] - r_["avg_alpha"], 1)

    star_labels = {"0-1": "无星", "2-3": "⭐⭐~³", "4+": "⭐⭐⁴⁺"}

    def star_bucket(r):
        s = r["star_count"]
        return ["4+"] if s >= 4 else (["2-3"] if s >= 2 else ["0-1"])

    return {
        "available": True,
        "generated_at": snap["generated_at"],
        "sample_n": len(rows),
        "seeds_excluded_n": seeds_n,
        "verdict_spread": spread,
        "by_verdict": by_verdict,
        "by_star": group_by(star_bucket, star_labels),
        "by_market": group_by(lambda r: [r["market_label"]]),
        "by_layer": group_by(lambda r: [r["layer_name"]] if r.get("layer_name") and r.get("layer") else []),
        "by_archetype": group_by(
            lambda r: [ch for ch in r["archetypes"] if ch in "①②③④⑤⑥⑦⑧⑨"]),
        "by_theme": group_by(lambda r: [r["theme"]]),
        "benchmarks": snap.get("benchmarks", {}),
    }


def star_matrix():
    """⭐ 跨主题矩阵(F6):行=星级标的,列=主题,格=该主题里的判定"""
    picks = data.load_picks()
    starred = sorted({p["symbol"] for p in picks if p["star_count"] >= 2})
    if not starred:
        return {"rows": [], "themes": []}
    snap = load_snapshot()
    sym_m = (snap or {}).get("symbols", {})
    # 每 (symbol, theme) 取最新一条判定
    cell = {}
    info = {}
    for p in sorted(data.load_picks(), key=lambda x: x["record_date"]):
        if p["symbol"] not in starred:
            continue
        cell[(p["symbol"], p["theme"])] = {
            "verdict_class": p["verdict_class"],
            "record_date": p["record_date"],
            "tier": p["tier"],
        }
        info[p["symbol"]] = p
    themes = sorted({t for (_s, t) in cell})
    rows = []
    for sym in starred:
        p = info[sym]
        m = sym_m.get(sym, {})
        rows.append({
            "symbol": sym,
            "name": p["name"],
            "star_count": p["star_count"],
            "stage_key": m.get("stage_key", ""),
            "ret_1m_pct": m.get("ret_1m_pct"),
            "cells": {t: cell.get((sym, t)) for t in themes if (sym, t) in cell},
        })
    rows.sort(key=lambda r: -r["star_count"])
    return {"rows": rows, "themes": themes,
            "generated_at": (snap or {}).get("generated_at")}
