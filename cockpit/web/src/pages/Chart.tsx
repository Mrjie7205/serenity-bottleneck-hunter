import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { init, dispose } from "klinecharts";
import { api, fmtPct, pctClass } from "../api";

type KChart = ReturnType<typeof init>;

interface Ann {
  date: string;
  timestamp: number;
  verdict_class: string;
  verdict: string;
  trigger: string;
  entry_price: string;
  currency: string;
  entry_stage: string;
  theme: string;
  tier: string;
  thesis: string;
}
interface Candle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
interface KlineResp {
  symbol: string;
  name: string;
  provider: string;
  candles: Candle[];
  annotations: Ann[];
  error?: string;
  message?: string;
  demo?: boolean;
}

const RANGES = [
  { label: "3月", days: 90 },
  { label: "6月", days: 180 },
  { label: "1年", days: 365 },
  { label: "最大", days: 800 },
];

const colorOf = (v: string) =>
  v === "green" ? "#1a7a4c" : v === "amber" ? "#b97608" : v === "red" ? "#b3261e" : "#6c7077";
const emojiOf = (v: string) =>
  v === "green" ? "🟢" : v === "amber" ? "🟡" : v === "red" ? "🔴" : "•";

export default function Chart() {
  const { symbol } = useParams<{ symbol: string }>();
  const nav = useNavigate();
  const ref = useRef<HTMLDivElement>(null);
  const [info, setInfo] = useState<KlineResp | null>(null);
  const [err, setErr] = useState("");
  const [days, setDays] = useState(365);
  const [showMA, setShowMA] = useState(true);

  useEffect(() => {
    if (!symbol) return;
    let chart: KChart = null;
    const controller = new AbortController();
    setErr("");
    setInfo(null);

    fetch(api.klineUrl(symbol, days), { signal: controller.signal, headers: { "X-Serenity-Request": "cockpit" } })
      .then((r) => r.json())
      .then((d: KlineResp) => {
        if (controller.signal.aborted) return;
        if (d.error) {
          setErr(d.error);
          return;
        }
        setInfo(d);
        if (!d.candles.length) return;
        if (!ref.current) return;
        chart = init(ref.current);
        if (!chart) return;
        chart.setStyles({
          grid: { horizontal: { color: "#e8e1d3" }, vertical: { color: "#e8e1d3" } },
          candle: {
            bar: {
              upColor: "#b3261e", downColor: "#1a7a4c",
              upBorderColor: "#b3261e", downBorderColor: "#1a7a4c",
              upWickColor: "#b3261e", downWickColor: "#1a7a4c",
            },
            priceMark: {
              high: { color: "#3a3d44" }, low: { color: "#3a3d44" },
              last: { line: { color: "#b8902e" }, text: { backgroundColor: "#b8902e" } },
            },
            tooltip: {
              rect: { color: "#fffdf8", borderColor: "#cdc3ad" },
              text: { color: "#3a3d44" },
              // 无成交量数据,legend 隐藏 Volume:0
              custom: [
                { title: "time", value: "{time}" },
                { title: "open", value: "{open}" },
                { title: "high", value: "{high}" },
                { title: "low", value: "{low}" },
                { title: "close", value: "{close}" },
              ],
            },
          },
          indicator: {
            lines: [
              { color: "#b8902e", size: 1 },
              { color: "#7a2e3a", size: 1 },
            ],
            tooltip: { text: { color: "#6c7077" } },
          },
          xAxis: { axisLine: { color: "#cdc3ad" }, tickText: { color: "#6c7077" } },
          yAxis: { axisLine: { color: "#cdc3ad" }, tickText: { color: "#6c7077" } },
        } as any);
        chart.applyNewData(d.candles as any);

        // MA20/50 叠加在主图(trigger 规则常引用 SMA50)
        if (showMA) {
          try {
            chart.createIndicator(
              { name: "MA", calcParams: [20, 50] } as any, true, { id: "candle_pane" });
          } catch { /* 指标失败不影响主图 */ }
        }

        const anns = d.annotations
          .filter((a) => a.timestamp > 0)
          .sort((a, b) => a.timestamp - b.timestamp);

        if (anns.length && d.candles.length) {
          const firstTs = d.candles[0].timestamp;
          const highAt = (ts: number) => {
            let best = d.candles[0];
            let bestDiff = Infinity;
            for (const c of d.candles) {
              const diff = Math.abs(c.timestamp - ts);
              if (diff < bestDiff) { bestDiff = diff; best = c; }
            }
            return best?.high ?? 0;
          };

          // ── 每个判定日一面小旗(只标 emoji+日期,保持图面干净;
          //    完整判定详情在图下方的历史时间线,hover 查看)──
          const seen = new Set<string>();
          const uniq = anns.filter((a) => {
            const k = `${a.date}|${a.verdict_class}|${a.theme}`;
            if (seen.has(k)) return false;
            seen.add(k);
            return true;
          });
          // 同一天多主题判定合并成一面旗,避免重叠
          const byDate = new Map<string, Ann[]>();
          for (const a of uniq) {
            const arr = byDate.get(a.date) ?? [];
            arr.push(a);
            byDate.set(a.date, arr);
          }
          for (const [date, group] of byDate) {
            const a = group[group.length - 1]; // 当日最新一条定颜色
            if (a.timestamp < firstTs) continue;
            const c = colorOf(a.verdict_class);
            const label =
              group.map((g) => emojiOf(g.verdict_class)).join("") +
              " " + date.slice(5);
            chart.createOverlay({
              name: "simpleAnnotation",
              points: [{ timestamp: a.timestamp, value: highAt(a.timestamp) }],
              extendData: label,
              styles: {
                text: {
                  color: c, size: 11,
                  family: "JetBrains Mono, monospace",
                  backgroundColor: "rgba(255,253,248,.94)",
                  borderColor: c, borderRadius: 4, borderSize: 1,
                  paddingLeft: 6, paddingRight: 6, paddingTop: 4, paddingBottom: 4,
                },
              },
            } as any);
          }

          // ── 最新 entry 价位虚线(锚点参考)──
          const latest = anns[anns.length - 1];
          const entry = parseFloat(latest.entry_price);
          if (Number.isFinite(entry) && entry > 0) {
            try {
              chart.createOverlay({
                name: "priceLine",
                points: [{ timestamp: latest.timestamp, value: entry }],
                lock: true,
                styles: {
                  line: { color: "#b8902e", style: "dashed", size: 1 },
                  text: { color: "#b8902e", backgroundColor: "rgba(255,253,248,.9)" },
                },
              } as any);
            } catch { /* overlay 不可用就跳过 */ }
          }
        }
      })
      .catch((e) => { if (!controller.signal.aborted) setErr(String(e)); });

    return () => {
      controller.abort();
      if (ref.current) dispose(ref.current);
    };
  }, [symbol, days, showMA]);

  // since-entry:最新判定 entry价 vs 最后收盘
  const latestAnn = info?.annotations.length ? info.annotations[info.annotations.length - 1] : null;
  const lastClose = info?.candles.length ? info.candles[info.candles.length - 1].close : null;
  const entryPx = latestAnn ? parseFloat(latestAnn.entry_price) : NaN;
  const sinceEntry =
    lastClose && Number.isFinite(entryPx) && entryPx > 0
      ? ((lastClose / entryPx - 1) * 100)
      : null;

  return (
    <div className="viewer">
      <div className="viewer-bar">
        <button className="back" onClick={() => nav(-1)}>← 返回</button>
        <span className="t">
          {symbol} {info?.name ? `· ${info.name}` : ""}
        </span>
        {latestAnn && (
          <span className={`vbadge ${latestAnn.verdict_class}`} title={latestAnn.verdict}>
            {emojiOf(latestAnn.verdict_class)} {latestAnn.date}
          </span>
        )}
        {info && lastClose != null && (
          <span className="mono" style={{ fontSize: 12.5 }}>
            现价 <b>{lastClose}</b>
            {sinceEntry != null && (
              <>
                {" "}· 对比记录价({latestAnn?.entry_price}{latestAnn?.currency})
                <b className={pctClass(sinceEntry)}> {fmtPct(sinceEntry)}</b>
              </>
            )}
          </span>
        )}
        <div className="chipgroup" style={{ marginLeft: "auto" }}>
          <button className={`chip ${showMA ? "on" : ""}`} onClick={() => setShowMA(!showMA)} title="MA20 金 / MA50 酒红">
            MA
          </button>
          {RANGES.map((r) => (
            <button
              key={r.days}
              className={`chip ${days === r.days ? "on" : ""}`}
              onClick={() => setDays(r.days)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <div className="mono dim" style={{ fontSize: 11.5, padding: "6px 22px 0", color: "var(--muted)" }}>
        {info ? `${info.provider} · ${info.candles.length} 根 · ${info.annotations.length} 次判定` : "数据源 EODHD(回退 yfinance)"}
        {" "}· 红涨绿跌 · 旗 = 判定日 · 金虚线 = 原始记录价（可能与复权价不同，仅参考） · MA20 金 / MA50 酒红
      </div>
      {/* 判定历史时间线:旗标只露日期,详情都在这里(hover 看 thesis) */}
      {info && info.annotations.length > 0 && (
        <div className="annstrip">
          {info.annotations.slice().reverse().map((a, i) => (
            <span
              key={i}
              className="annchip"
              style={{ borderColor: colorOf(a.verdict_class) }}
              title={`${a.verdict}\n入场 ${a.entry_price}${a.currency} · ${a.entry_stage}\n档位 ${a.tier}\n${a.thesis}`}
            >
              {emojiOf(a.verdict_class)} {a.date} · {a.theme}
              {a.trigger && <b> [{a.trigger.length > 24 ? a.trigger.slice(0, 24) + "…" : a.trigger}]</b>}
            </span>
          ))}
        </div>
      )}
      {info?.message && <div className="empty" role="status">{info.message}</div>}
      {err ? (
        <div className="empty" style={{ color: "var(--red)" }}>{err}</div>
      ) : !info ? (
        <div className="loading">LOADING K线…</div>
      ) : null}
      <div ref={ref} style={{ flex: 1, minHeight: 400, width: "100%", background: "var(--surface)",
          display: err || (info && !info.candles.length) ? "none" : "block" }} />
    </div>
  );
}
