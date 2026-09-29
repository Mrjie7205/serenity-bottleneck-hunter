"""triggers.py — Trigger 告警引擎(M2)
解析 🟡 观望标的的重估条件 → 结构化规则 → 每日收盘核对 → alerts.json

分层(对应 PRD §9 容错):
  auto   — 可纯价格判定(1m 转正 / 1m>+X / rng<X / off>-X) → 自动告警
  manual — 基本面/价格点条件(营收占比/visibility/财报/回$X) → 单列展示,不自动告警
"""
import re
import json
import sys
import math
import os
import tempfile
import threading
from pathlib import Path
from datetime import datetime

# 先 load_dotenv 再 import price(price.py 模块级读 EODHD_API_KEY)
HERE = Path(__file__).resolve().parent
import settings
from storage import replace_with_retry

import data  # noqa: E402

SCRIPTS = data.SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
from price import analyze  # noqa: E402

ALERTS_FILE = settings.STATE_DIR / "alerts.json"
ACK_FILE = settings.STATE_DIR / "alerts_ack.json"

# 检查全程串行；文件读改写单独加锁，抓价期间仍可标记告警。
_RUN_LOCK = threading.Lock()
_STATE_LOCK = threading.RLock()


class _StorageError(Exception):
    """持久化不可用时拒绝覆盖原文件，并向调用者返回明确失败。"""


def _empty_alerts():
    return {"last_run": None, "hit_count": 0, "hits": [],
            "manual_watch": [], "checked_auto": 0, "checked_manual": 0,
            "error_count": 0, "errors": []}


def _read_json(path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _StorageError(f"无法读取 {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise _StorageError(f"{path.name} 必须是 JSON 对象")
    return value


def _read_alerts():
    out = _read_json(ALERTS_FILE, _empty_alerts())
    hits = out.get("hits")
    if not isinstance(hits, list) or any(
        not isinstance(hit, dict)
        or not isinstance(hit.get("symbol"), str)
        or not isinstance(hit.get("trigger_label"), str)
        or not isinstance(hit.get("star_count") or 0, (int, float))
        or not math.isfinite(hit.get("star_count") or 0)
        for hit in hits
    ):
        raise _StorageError(f"{ALERTS_FILE.name} 的 hits 格式无效")
    if not isinstance(out.get("manual_watch", []), list):
        raise _StorageError(f"{ALERTS_FILE.name} 的 manual_watch 格式无效")
    return out


def _atomic_write(path, value):
    """同目录唯一临时文件 + 原子替换，失败时保留上次完整文件。"""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(lambda: os.replace(temporary, path))
    except (OSError, TypeError, ValueError) as exc:
        raise _StorageError(f"无法保存 {path.name}: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # 保存错误优先；临时文件不能使成功替换被误报为失败。


def _storage_failure(out, exc):
    return {**out, "ok": False, "error": str(exc), "storage_errors": [str(exc)]}

# 基本面/价格点关键词 → 无法纯价格自动化,标 manual
_MANUAL_KW = [
    "营收占比", "visibility", "财报", "可量化", "订单", "CHIPS", "利用率",
    "站回", "站稳", "SMA50", "出货占比", "毛利率", "营收/产能", "现金跑道",
    "需求面", "交叉验证", "营收", "占比", "回$", "回¥", "回€", "回HK", "回调到",
    "需求", "签约", "中标", "投产", "量产节点",
]

# 启动类定性词 → 1m 转正
_IGNITE_KW = ["转正", "止跌", "等启动", "等止跌", "deepDrop", "deep", "基础回调",
              "basing", "启动", "极深"]


def parse_trigger(verdict: str, entry_stage: str = ""):
    """从判定文本 + entry_stage 解析 trigger → dict(kind/field/op/threshold/label)

    关键:trigger 语义随 stage 方向而变 ——
      deep/range 标的 → "1m 转正" 才是 Mode A 启动信号(从负转正)
      ext 标的       → "1m 转正" 无意义(本来就在涨),真信号是"回调充分(rng 下降)"
    """
    v = verdict or ""
    es = (entry_stage or "").lower()

    # 1. 显式数值条件优先(报告里手写的精确阈值)
    m = re.search(r"1m\s*[>＞]\s*\+?\s*(\d+(?:\.\d+)?)", v)
    if m:
        return {"kind": "auto", "field": "ret_1m_pct", "op": ">",
                "threshold": float(m.group(1)), "label": f"1m > +{m.group(1)}%"}
    m = re.search(r"rng\s*[<＜]\s*(\d+)", v)
    if m:
        return {"kind": "auto", "field": "range_pos_6mo_pct", "op": "<",
                "threshold": float(m.group(1)), "label": f"回调 rng<{m.group(1)}"}
    m = re.search(r"off\s*[>＞]\s*-?\s*(\d+)", v)
    if m:
        return {"kind": "auto", "field": "pct_off_6mo_high", "op": ">",
                "threshold": -float(m.group(1)), "label": f"回调 off>-{m.group(1)}%"}

    # 2. 基本面/价格点 → 人工(放在定性词之前判,避免"回调"被启动类抢)
    if any(k in v for k in _MANUAL_KW):
        m2 = re.search(r"trigger[:：]\s*(.+?)[\]\)）]", v)
        raw = m2.group(1) if m2 else data.extract_trigger(v)
        return {"kind": "manual", "field": None, "op": None,
                "threshold": None, "label": raw[:50] or "需人工判定"}

    # 3. 按 stage 方向定默认规则(entry_stage 是扫描时 price.py 客观判的)
    is_ext = "ext" in es or "parabolic" in es or any(
        k in v for k in ["已ext", "抛物线", "偏mid", "mid-ext", "等回调", "等深度回调"])
    if is_ext:
        # ext 标的真信号 = 回调充分。提取 entry 时 rng,回到 (entry_rng - 25) 或 < 40
        rng_m = re.search(r"rng(\d+)", es)
        entry_rng = int(rng_m.group(1)) if rng_m else 60
        target = max(35, entry_rng - 25)
        return {"kind": "auto", "field": "range_pos_6mo_pct", "op": "<",
                "threshold": float(target), "label": f"回调 rng<{target}(深度回调)"}

    # 4. deep/range/启动类 → 1m 转正(Mode A 启动信号)
    if any(k in v for k in _IGNITE_KW) or "range" in es or "down" in es or "basing" in es:
        return {"kind": "auto", "field": "ret_1m_pct", "op": ">",
                "threshold": 0.0, "label": "1m 转正(启动信号)"}

    # 5. 兜底
    return {"kind": "auto", "field": "ret_1m_pct", "op": ">",
            "threshold": 0.0, "label": "1m 转正(默认)"}


def _cmp(value, op, threshold):
    if value is None:
        return False
    return value > threshold if op == ">" else value < threshold


def _watchlist():
    """🟡 观望标的(去重 symbol,保留最新一条判定)"""
    picks = [p for p in data.load_picks() if p["verdict_class"] == "amber"]
    by_sym = {}
    for p in sorted(picks, key=lambda x: x["record_date"]):
        by_sym[p["symbol"]] = p   # 后写覆盖 = 最新
    return list(by_sym.values())


def run_check(limit: int = 0):
    settings.require_personal_data()
    """对 🟡 auto 标的跑 analyze 核对 trigger,命中写 alerts.json。
    limit>0 时只查前 N 个(省 EODHD 额度)，保留本次未成功检查的旧告警。"""
    with _RUN_LOCK:
        return _run_check(limit)


def _run_check(limit):
    with _STATE_LOCK:
        try:
            previous = _read_alerts()
        except _StorageError as exc:
            return _storage_failure(_empty_alerts(), exc)

    watch = _watchlist()
    parsed = [(p, parse_trigger(p["verdict"], p["entry_stage"])) for p in watch]
    auto = [(p, t) for p, t in parsed if t["kind"] == "auto"]
    manual = [(p, t) for p, t in parsed if t["kind"] == "manual"]
    monitored = {p["symbol"] for p, _ in auto}
    scope = "partial" if limit > 0 else "full"
    if limit > 0:
        auto = auto[:limit]

    snap_cache = {}
    hits = []
    errors = []
    successful = set()
    for p, t in auto:
        sym = p["symbol"]
        try:
            if sym not in snap_cache:
                snap_cache[sym] = analyze(sym)
            snap = snap_cache[sym]
            if not isinstance(snap, dict):
                raise ValueError("行情返回格式无效")
            if snap.get("error"):
                raise ValueError(str(snap["error"]))
            val = snap.get(t["field"])
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError(f"行情缺少有效字段 {t['field']}")
        except Exception as exc:
            errors.append({"symbol": sym, "error": str(exc)[:80]})
            continue
        successful.add(sym)
        checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if _cmp(val, t["op"], t["threshold"]):
            hits.append({
                "symbol": sym,
                "name": p["name"],
                "theme": p["theme"],
                "market_label": p["market_label"],
                "trigger_label": t["label"],
                "field": t["field"],
                "fired_value": val,
                "snapshot": {
                    "last": snap.get("last"),
                    "ret_1m_pct": snap.get("ret_1m_pct"),
                    "ret_3m_pct": snap.get("ret_3m_pct"),
                    "range_pos_6mo_pct": snap.get("range_pos_6mo_pct"),
                    "pct_off_6mo_high": snap.get("pct_off_6mo_high"),
                    "stage": str(snap.get("stage") or "").split(" (")[0],
                },
                "verdict": p["verdict"],
                "thesis": p["thesis"],
                "entry_price": p["entry_price"],
                "currency": p["currency"],
                "record_date": p["record_date"],
                "star_count": p["star_count"],
                "stars": p["stars"],
                "checked_at": checked_at,
            })

    # 成功检查（包括未命中）才替换旧项。全量检查清理退出自动监控的项；
    # 局部检查保留所有未查项。失败项保留原值与原时间，不能伪装为新告警。
    retained = []
    for old in previous.get("hits", []):
        sym = old["symbol"]
        if sym in successful or (scope == "full" and sym not in monitored):
            continue
        retained.append({**old, "checked_at": old.get("checked_at", previous.get("last_run"))})
    hits.extend(retained)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = {
        "ok": not errors,
        "last_run": now,
        "checked_at": now,
        "scope": scope,
        "limit": limit,
        "checked_auto": len(auto),
        "successful_auto": len(successful),
        "checked_manual": len(manual),
        "hit_count": len(hits),
        "retained_hit_count": len(retained),
        "error_count": len(errors),
        "hits": sorted(hits, key=lambda h: (-(h.get("star_count") or 0), h["symbol"])),
        "errors": errors[:20],
        "failed_symbols": [e["symbol"] for e in errors],
        "manual_watch": [
            {"symbol": p["symbol"], "name": p["name"], "theme": p["theme"],
             "trigger_label": t["label"], "verdict": p["verdict"]}
            for p, t in manual
        ],
    }
    if errors:
        result["error"] = f"{len(errors)} 个标的行情检查失败，已保留其旧告警和检查时间"
    with _STATE_LOCK:
        try:
            _atomic_write(ALERTS_FILE, result)
        except _StorageError as exc:
            # 返回仍在磁盘上的旧结果，避免客户端把未保存结果当成最新状态。
            return _storage_failure(previous, exc)
    return result


def _load_acks():
    acks = _read_json(ACK_FILE, {})
    if any(not isinstance(a, dict) or a.get("action") not in ("done", "ignore")
           for a in acks.values()):
        raise _StorageError(f"{ACK_FILE.name} 的标记格式无效")
    return acks


def ack(symbol: str, trigger_label: str, action: str):
    settings.require_personal_data()
    """标记告警:done(已处理)/ ignore(忽略)/ clear(撤销标记)"""
    key = f"{symbol}|{trigger_label}"
    if action not in ("done", "ignore", "clear"):
        return {"ok": False, "error": "action 必须是 done/ignore/clear"}
    with _STATE_LOCK:
        try:
            acks = _load_acks()
            if action == "clear":
                acks.pop(key, None)
            else:
                acks[key] = {"action": action,
                             "at": datetime.now().strftime("%Y-%m-%d %H:%M")}
            _atomic_write(ACK_FILE, acks)
        except _StorageError as exc:
            return _storage_failure({"key": key, "action": action}, exc)
    return {"ok": True, "key": key, "action": action}


def load_alerts():
    if settings.DEMO:
        return {"ok": True, "demo": True, "last_run": None, "hits": [], "errors": [],
                "hit_count": 0, "error_count": 0, "checked_auto": 0, "checked_manual": 0, "manual_watch": []}
    with _STATE_LOCK:
        try:
            out = _read_alerts()
        except _StorageError as exc:
            return _storage_failure(_empty_alerts(), exc)
        try:
            acks = _load_acks()
        except _StorageError as exc:
            return _storage_failure(out, exc)
        for h in out.get("hits", []):
            a = acks.get(f"{h['symbol']}|{h['trigger_label']}")
            h["ack"] = a["action"] if a else None
            h.setdefault("checked_at", out.get("last_run"))
    return out


def trigger_summary():
    """不跑 analyze,只统计 watchlist 的 trigger 分层(供 UI 展示规则)"""
    watch = _watchlist()
    auto = manual = 0
    for p in watch:
        t = parse_trigger(p["verdict"], p["entry_stage"])
        if t["kind"] == "auto":
            auto += 1
        else:
            manual += 1
    return {"watch_total": len(watch), "auto": auto, "manual": manual}
