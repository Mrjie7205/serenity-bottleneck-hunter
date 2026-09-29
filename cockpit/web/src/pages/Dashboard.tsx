import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtPct, pctClass, rngWord } from "../api";
import { errorMessage, type RequestOptions } from "../request";
import { MiniCake } from "../components/LayerCake";
import type { Meta, TriggerStatus } from "../types";

function triggerError(result: { ok?: boolean; error?: string; storage_errors?: string[] }) {
  const details = [...new Set([result.error, ...(result.storage_errors ?? [])].filter(Boolean))];
  return details.join("；") || (result.ok === false ? "本次操作未完成，请稍后重试。" : "");
}

export default function Dashboard() {
  const nav = useNavigate();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [trig, setTrig] = useState<TriggerStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [showAcked, setShowAcked] = useState(false);
  const [err, setErr] = useState("");
  const [metaError, setMetaError] = useState("");
  const operation = useRef<AbortController | null>(null);

  const loadTrig = useCallback(async (options?: RequestOptions) => {
    const value = await api.triggersStatus(options);
    if (options?.signal?.aborted) return;
    setTrig(value);
    setErr(triggerError(value));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    api.meta({ signal: controller.signal }).then((value) => {
      if (!controller.signal.aborted) setMeta(value);
    }).catch((error) => {
      if (!controller.signal.aborted) setMetaError(`仪表盘数据加载失败：${errorMessage(error)}`);
    });
    void loadTrig({ signal: controller.signal }).catch((error) => {
      if (!controller.signal.aborted) setErr(`告警读取失败：${errorMessage(error)}`);
    });
    return () => { controller.abort(); operation.current?.abort(); };
  }, [loadTrig]);

  const runNow = async () => {
    const controller = new AbortController();
    operation.current = controller;
    setRunning(true);
    setErr("");
    try {
      const result = await api.runTriggers(30, { signal: controller.signal }); // 快速核对前 30 个,省 EODHD 额度
      await loadTrig({ signal: controller.signal });
      if (!controller.signal.aborted && triggerError(result)) setErr(triggerError(result));
    } catch (e) {
      if (!controller.signal.aborted) setErr(`告警核对失败：${errorMessage(e)}`);
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  };

  const ack = async (e: MouseEvent, symbol: string, label: string, action: "done" | "ignore" | "clear") => {
    e.stopPropagation();
    setErr("");
    try {
      const result = await api.ackTrigger(symbol, label, action);
      const failure = triggerError(result);
      if (failure) { setErr(`告警标记失败：${failure}`); return; }
      await loadTrig();
    } catch (error) { setErr(`告警标记失败：${errorMessage(error)}`); }
  };

  if (metaError) return <div className="mode-dark"><div className="empty" role="alert">{metaError}</div></div>;
  if (!meta) return <div className="mode-dark"><div className="loading">LOADING…</div></div>;

  const allHits = trig?.hits ?? [];
  const fresh = allHits.filter((h) => !h.ack);
  const acked = allHits.filter((h) => h.ack);
  const hits = showAcked ? allHits : fresh;
  const staleThemes = meta.freshness.filter((f) => f.level !== "green");

  return (
    <div className="mode-dark">
      <div className="page-title">Morning Check · 晨检</div>
      <h1>仪表盘</h1>

      {/* ===== Trigger 告警流(置顶,M2 核心)===== */}
      <div
        className="card"
        style={{
          borderLeft: `4px solid ${fresh.length ? "var(--gold)" : "var(--line-strong)"}`,
          padding: "18px 22px", marginBottom: 24,
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: hits.length ? 14 : 0 }}>
          <span style={{ fontFamily: "var(--display)", fontWeight: 700, fontSize: 19, color: "var(--burg)" }}>
            🔔 Trigger 告警{fresh.length ? ` · ${fresh.length} 条待处理` : ""}
          </span>
          {trig && (
            <span className="mono dim" style={{ fontSize: 12 }}>
              监控 {trig.summary.watch_total} 只 · 自动 {trig.summary.auto} / 人工 {trig.summary.manual}
              {trig.last_run ? ` · 上次核对 ${trig.last_run}` : " · 尚未核对"}
              {trig.scope === "partial" && ` · 本轮快速核对 ${trig.checked_auto} 只`}
              {(trig.retained_hit_count ?? 0) > 0 && ` · 保留旧告警 ${trig.retained_hit_count} 条`}
            </span>
          )}
          {acked.length > 0 && (
            <button className="linkbtn" onClick={() => setShowAcked(!showAcked)}>
              {showAcked ? "隐藏" : `显示已处理 ${acked.length}`}
            </button>
          )}
          <button
            onClick={runNow}
            disabled={running || !trig || trig.demo}
            className="actbtn"
            style={{ marginLeft: "auto" }}
          >
            {trig?.demo ? "离线演示" : running ? "核对中…(稍候)" : "⟳ 立即核对(快速 30)"}
          </button>
        </div>

        {err && <div className="hintbar" role="alert" style={{ color: "var(--red)" }}>{err}</div>}

        {hits.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {hits.map((h) => (
              <div
                key={`${h.symbol}-${h.trigger_label}`}
                onClick={() => nav(`/chart/${encodeURIComponent(h.symbol)}`)}
                title="查看 K 线"
                className="hitrow"
                style={{ opacity: h.ack ? 0.55 : 1 }}
              >
                <span className="sym">{h.symbol} <span style={{ color: "var(--gold)", fontWeight: 400 }}>↗</span></span>
                <span style={{ fontWeight: 700, color: "var(--ink)" }}>{h.name}</span>
                {h.star_count >= 2 && <span className="starcell">{h.stars}×{h.star_count}</span>}
                <span className="trigger-pill">{h.trigger_label}</span>
                <span className="mono dim" style={{ fontSize: 12 }} title={`6月区间位置 ${h.snapshot.range_pos_6mo_pct}% · 距高点 ${h.snapshot.pct_off_6mo_high}%`}>
                  近1月 <span className={pctClass(h.snapshot.ret_1m_pct)}>{fmtPct(h.snapshot.ret_1m_pct)}</span>
                  {" "}· 水位 {rngWord(h.snapshot.range_pos_6mo_pct)}({h.snapshot.range_pos_6mo_pct}%) · {h.snapshot.stage}
                </span>
                <span className="mono dim" style={{ fontSize: 11.5, marginLeft: "auto" }}>{h.theme}</span>
                {h.checked_at && <span className="mono dim" style={{ fontSize: 11.5 }} title="该标的最近一次成功核对时间">{h.checked_at}</span>}
                <span className="ackbtns">
                  {h.ack ? (
                    <button className="ackbtn" title="撤销标记" onClick={(e) => ack(e, h.symbol, h.trigger_label, "clear")}>↩</button>
                  ) : (
                    <>
                      <button className="ackbtn done" title="已处理(已重扫/已重估)" onClick={(e) => ack(e, h.symbol, h.trigger_label, "done")}>✓</button>
                      <button className="ackbtn ignore" title="忽略" onClick={(e) => ack(e, h.symbol, h.trigger_label, "ignore")}>✕</button>
                    </>
                  )}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="mono dim" style={{ fontSize: 13, marginTop: 4 }}>
            {trig?.demo ? "历史演示没有执行行情核对，也不生成实时告警。接入个人研究目录后，可手动核对价格条件。" : err ? "本次核对或读取未完成，请以上方提示为准。" : allHits.length > 0 ? "全部告警已处理 ✓" : trig?.last_run ? "最近一次核对未发现新触发。可手动再次核对；定时任务需自行启用。" : "尚未核对。点击「立即核对」检查价格条件；财报和订单等仍需人工研究。"}
          </div>
        )}
      </div>

      <div className="statgrid">
        <div className="card stat clickable" onClick={() => nav("/tracker")}><div className="v">{meta.total_picks}</div><div className="l">判定总数</div></div>
        <div className="card stat clickable" onClick={() => nav("/tracker")}><div className="v gold">{meta.themes.length}</div><div className="l">主题数</div></div>
        <div className="card stat clickable" onClick={() => nav("/opportunities")}><div className="v green">{meta.verdict_counts.green}</div><div className="l">🟢 候选 · 进机会雷达 →</div></div>
        <div className="card stat clickable" onClick={() => nav("/tracker?verdict=amber")}><div className="v amber">{meta.verdict_counts.amber}</div><div className="l">🟡 观望(带 trigger)</div></div>
        <div className="card stat clickable" onClick={() => nav("/tracker?verdict=red")}><div className="v red">{meta.verdict_counts.red}</div><div className="l">🔴 排除</div></div>
        <div className="card stat clickable" onClick={() => nav("/library")}><div className="v">{meta.total_reports}</div><div className="l">报告数</div></div>
      </div>

      {/* ===== 五层蛋糕覆盖(迷你)===== */}
      {meta.layer_rollup && meta.layer_rollup.length > 0 && (
        <div className="dashcols" style={{ gridTemplateColumns: "1fr 1fr", marginBottom: 26 }}>
          <div>
            <div className="section-label">🍰 五层蛋糕覆盖 · 点击进地图</div>
            <div className="card" style={{ padding: 16 }}>
              <MiniCake rollup={meta.layer_rollup} onPick={(n) => nav(`/?layer=${n}`)} />
            </div>
          </div>
          <div>
            <div className="section-label">分层提示</div>
            <div className="card" style={{ padding: "14px 18px", fontSize: 13.5, color: "var(--ink-soft)", lineHeight: 1.7 }}>
              黄仁勋「底层战争是能源战争」——能源层是 #1 瓶颈却最薄。
              <br />
              <span className="mono dim" style={{ fontSize: 12 }}>
                {meta.layer_rollup.map((L) => `${L.layer}${L.layer_name.split("/")[0]} ${L.scanned}扫/${L.planned}待`).join(" · ")}
              </span>
              <br />
              <span className="linkbtn" onClick={() => nav("/")} style={{ marginTop: 8, display: "inline-block" }}>
                打开蛋糕地图 →
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ===== 主题新鲜度(F8):该重扫哪个主题了 ===== */}
      {staleThemes.length > 0 && (
        <>
          <div className="section-label">⏳ 主题新鲜度 · 该重扫了({staleThemes.length} 个超 30 天)</div>
          <div className="freshrow">
            {meta.freshness.map((f) => (
              <button
                key={f.theme}
                className={`freshchip ${f.level}`}
                title={`上次扫描 ${f.last_scan}`}
                onClick={() => nav(`/tracker?theme=${encodeURIComponent(f.theme)}`)}
              >
                {f.theme}
                <b>{f.age_days}天</b>
              </button>
            ))}
          </div>
        </>
      )}

      <div className="dashcols">
        <div>
          <div className="section-label">⭐ 跨主题节点(被 N 个 capex 周期同时锁定)</div>
          <div className="card starlist">
            {meta.star_nodes.map((s) => (
              <div className="starrow" key={s.symbol} style={{ cursor: "pointer" }} onClick={() => nav(`/chart/${encodeURIComponent(s.symbol)}`)}>
                <span className="n">×{s.star_count}</span>
                <span className="sym">{s.symbol} <span style={{ color: "var(--gold)", fontWeight: 400 }}>↗</span></span>
                <span>{s.name}</span>
                <span className="starcell" style={{ marginLeft: "auto" }}>{"⭐".repeat(Math.min(s.star_count, 6))}</span>
              </div>
            ))}
            <div className="starrow" style={{ cursor: "pointer", justifyContent: "center" }} onClick={() => nav("/scorecard")}>
              <span className="mono" style={{ fontSize: 12, color: "var(--burg)", fontWeight: 700 }}>查看完整跨主题矩阵 →</span>
            </div>
          </div>
        </div>

        <div>
          <div className="section-label">📑 最新报告</div>
          <div className="card starlist">
            {meta.latest_reports.map((r) => (
              <div className="starrow" key={r.file} style={{ cursor: "pointer" }} onClick={() => nav(`/library/${encodeURIComponent(r.file)}`)}>
                <span className="mono dim" style={{ fontSize: 11.5, whiteSpace: "nowrap" }}>{r.report_date}</span>
                <span style={{ fontWeight: 600, color: "var(--ink)" }}>{r.theme}</span>
                <span className="mkt">{r.market_label}</span>
                {r.dogfood != null && <span className="mono dim" style={{ fontSize: 11 }}>#{r.dogfood}</span>}
                <span className="mono" style={{ marginLeft: "auto", color: "var(--burg)" }}>阅读 →</span>
              </div>
            ))}
            <div className="starrow" style={{ cursor: "pointer", justifyContent: "center" }} onClick={() => nav("/library")}>
              <span className="mono" style={{ fontSize: 12, color: "var(--burg)", fontWeight: 700 }}>全部 {meta.total_reports} 份报告 →</span>
            </div>
          </div>
        </div>
      </div>

      {trig && trig.manual_watch.length > 0 && (
        <>
          <div className="section-label">需人工判定的 trigger(基本面/价格点条件,不自动告警)</div>
          <div className="card" style={{ padding: "8px 0" }}>
            {trig.manual_watch.slice(0, 8).map((m, i) => (
              <div className="starrow" key={i} style={{ borderBottom: i === Math.min(7, trig.manual_watch.length - 1) ? "0" : undefined }}>
                <span className="sym" style={{ minWidth: 110 }}>{m.symbol}</span>
                <span style={{ minWidth: 80 }}>{m.name}</span>
                <span className="trigger-pill">{m.trigger_label}</span>
                <span className="mono dim" style={{ fontSize: 11, marginLeft: "auto" }}>{m.theme}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
