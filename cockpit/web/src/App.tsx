import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { useLens, LENS_META, type Lens } from "./lens";
import { useSnapshot, snapshotAgeHours } from "./snapshot";
import Dashboard from "./pages/Dashboard";
import Layers from "./pages/Layers";
import Opportunities from "./pages/Opportunities";
import Tracker from "./pages/Tracker";
import Scorecard from "./pages/Scorecard";
import Library from "./pages/Library";
import ReportViewer from "./pages/ReportViewer";
import Chart from "./pages/Chart";

const LINKS = [
  { to: "/", label: "蛋糕地图", end: true },
  { to: "/opportunities", label: "机会雷达" },
  { to: "/dashboard", label: "仪表盘" },
  { to: "/tracker", label: "标的跟踪" },
  { to: "/scorecard", label: "计分卡" },
  { to: "/library", label: "报告库" },
];

function SyncButton() {
  const { snap, rebuild, running, error } = useSnapshot();
  const dq = snap?.data_quality;
  const problems = dq ? dq.ashare_raw_eodhd.length + dq.split_suspects.length : null;
  const missingBenchmarks = snap?.benchmark_errors ?? [];
  const ageH = snapshotAgeHours(snap);
  const ageLabel =
    ageH == null ? "" : ageH < 1 ? "刚刚" : ageH < 24 ? `${Math.round(ageH)}h前` : `${Math.round(ageH / 24)}天前`;
  const stale = ageH != null && ageH >= 24;

  const title = error || (running
    ? `同步中:${snap?.progress.phase} ${snap?.progress.done}/${snap?.progress.total}`
    : snap?.exists
    ? `快照 ${snap.generated_at} · ${snap.symbol_count} 标的` +
      (missingBenchmarks.length ? `\n基准行情暂缺:${missingBenchmarks.join("、")}，对应 α 暂不可用` : "") +
      (dq ? `\n数据质检:A股前复权 ${dq.ashare_adjusted}/${dq.ashare_total}` +
        (problems ? `\n⚠ 价格变化或复权来源需核对:${[...dq.ashare_raw_eodhd, ...dq.split_suspects].join(" ")}` : " · 全部前复权 ✓")
        : "\n(本次质检数据待下次同步生成)") +
      `\n按当前跟踪表取价，可能需要几分钟并消耗数据服务额度`
    : snap?.message || "尚无价格快照,点击构建");

  return (
    <>
    <button className={`sync-btn ${running ? "running" : ""}`} onClick={() => !running && !snap?.demo && rebuild()} disabled={running || !snap || snap.demo} title={snap?.demo ? "离线演示不抓取行情；指定个人研究目录后可手动更新" : title}>
      {running ? (
        <>⟳ 同步中 <span className="mono">{snap?.progress.done}/{snap?.progress.total}</span></>
      ) : (
        <>
          {snap?.demo ? "历史快照" : "🔄 同步股价"}
          {snap?.exists && <span className={`sync-age ${stale ? "stale" : ""}`}>{ageLabel}</span>}
          {problems != null && (problems === 0
            ? !missingBenchmarks.length && <span className="sync-q ok" title="A股数据源全部前复权">✓</span>
            : <span className="sync-q warn">⚠{problems}</span>)}
          {missingBenchmarks.length > 0 && <span className="sync-q warn">⚠基准{missingBenchmarks.length}</span>}
        </>
      )}
    </button>
    {error && <span role="alert" style={{ color: "var(--red)", fontSize: 12, maxWidth: 300 }}>{error}</span>}
    </>
  );
}

export default function App() {
  const [version, setVersion] = useState("");
  const [mode, setMode] = useState<{ demo: boolean; dataset_label: string; price_asof: string | null } | null>(null);
  const [lens, setLens] = useLens();

  useEffect(() => {
    api.health().then((h) => { setVersion(h.version); setMode(h); }).catch(() => {});
  }, []);

  return (
    <div className="shell">
      <nav className="topnav">
        <span className="brand">
          Serenity Cockpit<small>瓶颈猎手驾驶舱</small>
        </span>
        <div className="navlinks">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end}
              className={({ isActive }) => (isActive ? "active" : "")}>
              {l.label}
            </NavLink>
          ))}
        </div>
        <div className="lens-switch" title={LENS_META[lens].desc}>
          {(["hunt", "coverage"] as Lens[]).map((k) => (
            <button key={k} className={`lens-btn ${lens === k ? "on" : ""} ${k}`}
              onClick={() => setLens(k)} title={LENS_META[k].desc}>
              {LENS_META[k].icon} {LENS_META[k].label}
            </button>
          ))}
        </div>
        <SyncButton />
        <span className="nav-right">{version || "…"} · 仅研究教育 非投资建议</span>
      </nav>
      {mode && <aside className={`dataset-banner ${mode.demo ? "demo" : "personal"}`}>
        <strong>{mode.dataset_label}</strong>
        <span>{mode.demo ? `行情截至 ${mode.price_asof} · 2 条历史样本 · 不联网取价，不代表当前判断` : "数据保存在你选择的本机目录 · 行情更新由你手动触发"}</span>
        <a href="https://github.com/Mrjie7205/serenity-bottleneck-hunter/blob/main/cockpit/README.md" target="_blank" rel="noreferrer">接入自己的研究 ↗</a>
      </aside>}
      <div className="main">
        <Routes>
          <Route path="/" element={<Layers />} />
          <Route path="/opportunities" element={<Opportunities />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/tracker" element={<Tracker />} />
          <Route path="/scorecard" element={<Scorecard />} />
          <Route path="/library" element={<Library />} />
          <Route path="/library/:file" element={<ReportViewer />} />
          <Route path="/chart/:symbol" element={<Chart />} />
        </Routes>
      </div>
    </div>
  );
}
