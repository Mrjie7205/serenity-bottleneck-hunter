import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, LAYER_META } from "../api";
import type { Report } from "../types";

const LAYERS = [1, 2, 3, 4, 5];

export default function Library() {
  const [rows, setRows] = useState<Report[]>([]);
  const [theme, setTheme] = useState("");
  const [market, setMarket] = useState("");
  const [layer, setLayer] = useState(0);
  const [q, setQ] = useState("");
  const [withOld, setWithOld] = useState(false);
  const nav = useNavigate();

  useEffect(() => {
    api.reports(withOld).then((d) => setRows(d.rows)).catch(() => {});
  }, [withOld]);

  const themes = useMemo(() => [...new Set(rows.map((r) => r.theme))].sort(), [rows]);
  const markets = useMemo(
    () => [...new Map(rows.map((r) => [r.market, r.market_label])).entries()],
    [rows]
  );

  const ql = q.toLowerCase();
  const filtered = rows.filter(
    (r) =>
      (!theme || r.theme === theme) &&
      (!market || r.market === market) &&
      (!layer || r.layer === layer) &&
      (!ql || r.title.toLowerCase().includes(ql) || r.verdict_preview.toLowerCase().includes(ql))
  );

  return (
    <div className="mode-paper">
      <div className="page-title">Library · 研究资产库</div>
      <h1>报告库</h1>

      <div className="paper-filterbar">
        {LAYERS.map((n) => (
          <button
            key={n}
            className={`pchip ${layer === n ? "on" : ""}`}
            onClick={() => setLayer(layer === n ? 0 : n)}
            title={`第 ${n} 层`}
            style={layer === n ? { borderColor: LAYER_META[n].color } : undefined}
          >
            {n} {LAYER_META[n].short}
          </button>
        ))}
        <span style={{ width: 14 }} />
        <button className={`pchip ${theme === "" ? "on" : ""}`} onClick={() => setTheme("")}>
          全部主题
        </button>
        {themes.map((t) => (
          <button
            key={t}
            className={`pchip ${theme === t ? "on" : ""}`}
            onClick={() => setTheme(theme === t ? "" : t)}
          >
            {t}
          </button>
        ))}
        <span style={{ width: 14 }} />
        {markets.map(([k, label]) => (
          <button
            key={k}
            className={`pchip ${market === k ? "on" : ""}`}
            onClick={() => setMarket(market === k ? "" : k)}
          >
            {label}
          </button>
        ))}
        <span style={{ width: 14 }} />
        <input
          className="dk"
          placeholder="搜标题 / 结论…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ minWidth: 180 }}
        />
        <button className={`pchip ${withOld ? "on" : ""}`} onClick={() => setWithOld(!withOld)} title="包含已标'勿用'的历史版本">
          含历史版
        </button>
        <span className="count-note">{filtered.length} 份</span>
      </div>

      <div className="libgrid">
        {filtered.map((r) => (
          <div className="repcard" key={r.file} onClick={() => nav(`/library/${encodeURIComponent(r.file)}`)} style={r.deprecated ? { opacity: 0.55 } : undefined}>
            <div className="tags">
              {r.layer > 0 && (
                <span className="tag" style={{ background: LAYER_META[r.layer].color, color: "#fff" }}>
                  {r.layer} {LAYER_META[r.layer].short}
                </span>
              )}
              <span className="tag theme">{r.theme}</span>
              <span className="tag market">{r.market_label}</span>
              {r.dogfood != null && <span className="tag dogfood">Dogfood #{r.dogfood}</span>}
              {r.deprecated && <span className="tag dogfood" style={{ color: "var(--red)" }}>历史版 勿用</span>}
            </div>
            <h3>{r.title}</h3>
            {r.verdict_preview && <div className="preview">◆ {r.verdict_preview}</div>}
            <div className="meta">
              {r.report_date} · {r.size_kb} KB
            </div>
          </div>
        ))}
      </div>
      {filtered.length === 0 && (
        <div className="empty">无匹配报告</div>
      )}
    </div>
  );
}
