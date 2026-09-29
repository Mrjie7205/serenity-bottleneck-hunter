"""Serenity Cockpit · 后端 API(M2)
运行入口:python cockpit/run.py；可选 --data-dir 指定个人研究目录。
密钥通过环境变量或个人目录 .env 提供，绝不进前端。
"""
import os
import sys
import threading
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).resolve().parent
import settings

from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse

import data
import triggers
import snapshot

sys.path.insert(0, str(data.SKILL / "scripts"))
from price import fetch_history     # noqa: E402

app = FastAPI(title="Serenity Cockpit API", version=settings.VERSION)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(PermissionError)
async def permission_error(request: Request, exc: PermissionError):
    return JSONResponse({"error": str(exc)}, status_code=403)


@app.middleware("http")
async def local_actions(request: Request, call_next):
    # A cross-site page must not consume local quote quotas or modify local state.
    guarded = request.method == "POST" or request.url.path.startswith("/api/kline/")
    if guarded:
        from urllib.parse import urlsplit
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).hostname not in ("localhost", "127.0.0.1", "::1"):
            return JSONResponse({"error": "仅接受本机驾驶舱操作"}, status_code=403)
        if request.headers.get("x-serenity-request") != "cockpit":
            return JSONResponse({"error": "请通过驾驶舱操作；API 客户端需提供 X-Serenity-Request: cockpit"}, status_code=403)
    return await call_next(request)


# ---------- scheduler(每日收盘后自动核对 trigger)----------

_scheduler = None


@app.on_event("startup")
def _start_scheduler():
    global _scheduler
    if not settings.DEMO:
        settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
    if settings.DEMO or os.environ.get("SERENITY_SCHEDULER", "0").strip() != "1":
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler(daemon=True)
        # A 股/港股收盘后 16:30 本地时间跑一次(美股盘后数据次日 EOD 才稳,够用)
        _scheduler.add_job(lambda: triggers.run_check(), "cron",
                           hour=16, minute=30, id="daily_trigger")
        # 全量价格快照默认手动;.env 设 SNAPSHOT_AUTO=1 开每日自动
        if os.environ.get("SNAPSHOT_AUTO", "").strip() == "1":
            _scheduler.add_job(lambda: snapshot.run_snapshot(), "cron",
                               hour=16, minute=40, id="daily_snapshot")
        _scheduler.start()
    except Exception as e:
        print(f"[scheduler] 未启动:{e}")


@app.on_event("shutdown")
def _stop_scheduler():
    if _scheduler:
        _scheduler.shutdown(wait=False)


# ---------- basic ----------

@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version,
            "scheduler": bool(_scheduler and _scheduler.running), **settings.mode_info()}


@app.get("/api/meta")
def meta():
    m = data.load_meta()
    m["trigger_summary"] = triggers.trigger_summary()
    return m


def _merge_snapshot(rows):
    """跟踪表实时列:最新价 / since-call% / α% / 现 stage(快照驱动,无快照则为 None)"""
    snap = snapshot.load_snapshot()
    syms = (snap or {}).get("symbols", {})
    pcs = (snap or {}).get("picks", {})
    out = []
    for r in rows:
        m = syms.get(r["symbol"], {})
        c = pcs.get(r["record_key"], {})
        out.append({
            **r,
            "last": m.get("last"),
            "stage_now": m.get("stage_key"),
            "ret_1m_pct": m.get("ret_1m_pct"),
            "since_call_pct": c.get("since_call_pct"),
            "alpha_pct": c.get("alpha_pct"),
        })
    return out


@app.get("/api/picks")
def picks(
    theme: str = Query(default=""),
    market: str = Query(default=""),
    verdict: str = Query(default=""),
    archetype: str = Query(default=""),
    layer: int = Query(default=0),
    subsector: str = Query(default=""),
    star_min: int = Query(default=0),
    q: str = Query(default=""),
):
    rows = data.load_picks()
    if theme:
        rows = [r for r in rows if r["theme"] == theme]
    if layer:
        rows = [r for r in rows if r.get("layer") == layer]
    if subsector:
        rows = [r for r in rows if r.get("subsector") == subsector]
    if market:
        rows = [r for r in rows if r["market"] == market]
    if verdict:
        rows = [r for r in rows if r["verdict_class"] == verdict]
    if archetype:
        rows = [r for r in rows if archetype in r["archetypes"]]
    if star_min > 0:
        rows = [r for r in rows if r["star_count"] >= star_min]
    if q:
        ql = q.lower()
        rows = [r for r in rows
                if ql in r["symbol"].lower() or ql in r["name"].lower() or ql in r["thesis"].lower()]
    rows = sorted(rows, key=lambda r: (r["record_date"], r["id"]), reverse=True)
    return {"count": len(rows), "rows": _merge_snapshot(rows)}


@app.get("/api/taxonomy")
def taxonomy():
    """五层蛋糕分类树(层→板块→board,带覆盖统计)— 驱动蛋糕地图页"""
    return data.taxonomy_tree()


@app.get("/api/reports")
def reports(include_deprecated: bool = Query(default=False)):
    rows = data.load_reports()
    if not include_deprecated:
        rows = [r for r in rows if not r["deprecated"]]
    return {"count": len(rows), "rows": rows}


@app.get("/api/report-file/{filename}")
def report_file(filename: str):
    p = data.report_path(filename)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(p, media_type="text/html", headers={"Content-Security-Policy": "sandbox allow-scripts allow-popups"})


# ---------- K 线 + 判定标注 ----------

def _to_ms(date_str: str) -> int:
    try:
        return int(datetime.strptime(date_str, "%Y-%m-%d").timestamp() * 1000)
    except ValueError:
        return 0


@app.get("/api/kline/{ticker}")
def kline(ticker: str, days: int = Query(default=400, ge=30, le=1200)):
    if not any(p["symbol"] == ticker for p in data.load_picks()):
        raise HTTPException(status_code=404, detail="该标的不在当前跟踪表中")
    if settings.DEMO:
        anns = data.annotations_for(ticker)
        for ann in anns:
            ann["timestamp"] = _to_ms(ann["date"])
        return {"symbol": ticker, "name": data.pick_name(ticker), "provider": "public-historical-demo",
                "candles": [], "annotations": anns, "demo": True,
                "message": "离线演示未包含逐日K线，未发起行情请求。接入自己的研究目录后可查看历史走势。"}
    raw, provider = fetch_history(ticker, days=days)
    if not raw:
        return JSONResponse(
            {"error": f"无数据:{ticker}(EODHD/yfinance 均失败)"}, status_code=404)
    candles = [{
        "timestamp": _to_ms(x["date"]),
        "open": x["open"], "high": x["high"], "low": x["low"],
        "close": x["close"], "volume": 0,
    } for x in raw if _to_ms(x["date"]) > 0]
    anns = data.annotations_for(ticker)
    for a in anns:
        a["timestamp"] = _to_ms(a["date"])
    return {
        "symbol": ticker,
        "name": data.pick_name(ticker),
        "provider": provider,
        "candles": candles,
        "annotations": anns,
    }


# ---------- triggers ----------

@app.get("/api/triggers/status")
def triggers_status():
    out = triggers.load_alerts()
    out["summary"] = triggers.trigger_summary()
    return out


@app.post("/api/triggers/run")
def triggers_run(limit: int = Query(default=0, ge=0, le=10000)):
    """手动立即核对一次(limit>0 只查前 N 个,省 EODHD 额度)"""
    return triggers.run_check(limit=limit)


@app.post("/api/triggers/ack")
def triggers_ack(symbol: str = Query(...), trigger_label: str = Query(...),
                 action: str = Query(...)):
    if action not in ("done", "ignore", "clear"):
        return JSONResponse({"error": "action 必须是 done/ignore/clear"}, status_code=400)
    return triggers.ack(symbol, trigger_label, action)


# ---------- snapshot(M3:since-call / α / stage 全靠它)----------

_snap_thread: threading.Thread | None = None


@app.get("/api/snapshot/status")
def snapshot_status():
    return snapshot.status()


@app.post("/api/snapshot/run")
def snapshot_run(limit: int = Query(default=0, ge=0, le=10000)):
    """后台线程重建快照；请求次数随数据规模与回退情况变化，轮询 status 看进度"""
    global _snap_thread
    try:
        _snap_thread = snapshot.start_snapshot(limit=limit)
    except snapshot.SnapshotBusyError:
        return JSONResponse({"error": "快照正在构建中"}, status_code=409)
    return {"started": True, "limit": limit}


@app.get("/api/scorecard")
def scorecard():
    return snapshot.scorecard()


@app.get("/api/stages")
def stages():
    return snapshot.stage_board()


@app.get("/api/matrix")
def matrix():
    return snapshot.star_matrix()


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API not found")
    root = settings.WEB_DIST.resolve()
    requested = (root / path).resolve()
    if not requested.is_relative_to(root):
        raise HTTPException(status_code=404)
    if requested.is_file():
        return FileResponse(requested)
    if path and path.split("/")[0] not in ("tracker", "library", "chart", "dashboard", "opportunities", "scorecard"):
        raise HTTPException(status_code=404)
    if not (root / "index.html").is_file():
        raise HTTPException(status_code=503, detail="请先构建 cockpit/web 或使用完整发布包")
    return FileResponse(root / "index.html")
