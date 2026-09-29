import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtPct, pctClass, rngWord, LAYER_META } from "../api";
import { useLens, LENS_META } from "../lens";
import type { Pick } from "../types";

const STAGE_BADGE: Record<string, { label: string; color: string }> = {
  deep: { label: "深底", color: "var(--ink-soft)" },
  range: { label: "震荡", color: "var(--gray)" },
  early: { label: "启动", color: "var(--green)" },
  parabolic: { label: "过热", color: "var(--red)" },
};

// 从 entry_stage 字符串里抠出建仓时的水位(rngNN)—— 报告里嵌的
function entryRng(entry_stage: string): number | null {
  const m = entry_stage?.match(/rng\s*(\d+)/i);
  return m ? Number(m[1]) : null;
}

function OppCard({ r, onOpen }: { r: Pick; onOpen: (s: string) => void }) {
  const sb = r.stage_now ? STAGE_BADGE[r.stage_now] : null;
  const rng = entryRng(r.entry_stage);
  const lm = r.layer ? LAYER_META[r.layer] : null;
  return (
    <div className="opp-card" onClick={() => onOpen(r.symbol)} title="查看 K 线 + 判定标注">
      <div className="oc-head">
        <span className="oc-sym">{r.symbol.replace(/\.(US|HK|SHG|SHE|BJ|T)$/, "")}</span>
        <span className="oc-name">{r.name}</span>
        {r.star_count >= 2 && <span className="starcell" title={r.star_themes}>⭐×{r.star_count}</span>}
        <span className={`vbadge ${r.verdict_class}`} style={{ marginLeft: "auto" }}>
          {r.verdict_class === "green" ? "🟢 候选" : "🟡 观望"}
        </span>
      </div>

      <div className="oc-theme">
        {lm && <span className="ldot" style={{ background: lm.color }} />}
        <span className="oc-themename">{r.theme}</span>
        <span className="dim mono" style={{ fontSize: 11 }}>{r.subsector}</span>
      </div>

      <div className="oc-tags">
        {sb && <span className="stagebadge" style={{ color: sb.color, borderColor: sb.color }}>{sb.label}</span>}
        {rng != null && <span className="oc-water mono" title="建仓时6月区间水位">水位 {rngWord(rng)} {rng}%</span>}
        <span className="mkt">{r.market_label}</span>
        <span className="mono dim" style={{ fontSize: 11 }}>{r.archetypes}</span>
      </div>

      <div className="oc-perf">
        <span className="ocp">
          <i>Entry</i><b className="mono">{r.entry_price} {r.currency}</b>
        </span>
        <span className="ocp">
          <i>最新</i><b className="mono">{r.last ?? "—"}</b>
        </span>
        <span className="ocp">
          <i>since</i><b className={`mono ${pctClass(r.since_call_pct)}`}>{fmtPct(r.since_call_pct)}</b>
        </span>
        <span className="ocp">
          <i>α 超额</i><b className={`mono ${pctClass(r.alpha_pct)}`} style={{ fontWeight: 800 }}>{fmtPct(r.alpha_pct)}</b>
        </span>
      </div>

      <div className="oc-thesis">{r.thesis}</div>

      {r.trigger && (
        <div className="oc-trig">
          <span className="oc-trig-k">触发/加仓信号</span>
          <span className="trigger-pill">{r.trigger}</span>
        </div>
      )}
      <div className="oc-foot mono">{r.record_date} 收录 · 点看 K 线 →</div>
    </div>
  );
}

export default function Opportunities() {
  const nav = useNavigate();
  const [greens, setGreens] = useState<Pick[]>([]);
  const [ambers, setAmbers] = useState<Pick[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [layer, setLayer] = useState(0);
  const [sort, setSort] = useState<"recent" | "alpha">("recent");
  const [lens] = useLens();

  // 镜头过滤:猎手模式只看瓶颈型(lens=hunt),隐藏覆盖型(应用/大盘广扫)
  const greensL = useMemo(() => lens === "hunt" ? greens.filter((r) => r.lens === "hunt") : greens, [greens, lens]);
  const ambersL = useMemo(() => lens === "hunt" ? ambers.filter((r) => r.lens === "hunt") : ambers, [ambers, lens]);
  const hiddenN = (greens.length - greensL.length) + (ambers.length - ambersL.length);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.picks({ verdict: "green" }).then((d) => d.rows),
      api.picks({ verdict: "amber" }).then((d) => d.rows),
    ])
      .then(([g, a]) => { setGreens(g); setAmbers(a); })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const open = (s: string) => nav(`/chart/${encodeURIComponent(s)}`);

  // 排序:最新收录优先(默认,新瓶颈研究在前)/ α 超额优先(看方法论赢家)
  const rankGreens = (rows: Pick[]) => {
    const lf = layer ? rows.filter((r) => r.layer === layer) : rows;
    if (sort === "recent") {
      return [...lf].sort((a, b) =>
        a.record_date < b.record_date ? 1 : a.record_date > b.record_date ? -1 : (b.alpha_pct ?? -Infinity) - (a.alpha_pct ?? -Infinity)
      );
    }
    return [...lf].sort((a, b) => {
      const aa = a.alpha_pct, ba = b.alpha_pct;
      if (aa != null && ba != null) return ba - aa;
      if (aa != null) return -1;
      if (ba != null) return 1;
      return a.record_date < b.record_date ? 1 : -1;
    });
  };

  const sortedGreens = useMemo(() => rankGreens(greensL), [greensL, layer, sort]);

  // 🟡 临界:有 trigger 的观望(条件触发即转机会)
  const watchTrig = useMemo(() => {
    const lf = layer ? ambersL.filter((r) => r.layer === layer) : ambersL;
    return lf.filter((r) => r.trigger && r.trigger.trim()).sort((a, b) =>
      a.record_date < b.record_date ? 1 : -1
    );
  }, [ambersL, layer]);

  // 🚀 启动区:现 stage = early(Mode-A 时机窗),🟢🟡 都算
  const igniting = useMemo(() => {
    const all = [...greensL, ...ambersL];
    const lf = layer ? all.filter((r) => r.layer === layer) : all;
    return lf.filter((r) => r.stage_now === "early").sort((a, b) =>
      (b.ret_1m_pct ?? -Infinity) - (a.ret_1m_pct ?? -Infinity)
    );
  }, [greensL, ambersL, layer]);

  if (err) return <div className="mode-dark"><div className="empty">后端未启动?{err}</div></div>;

  return (
    <div className="mode-dark">
      <div className="page-title">Opportunity Radar · 机会雷达</div>
      <h1>机会雷达</h1>
      <p className="lead" style={{ color: "var(--muted)", marginTop: -10, marginBottom: 16, fontSize: 14, maxWidth: 760 }}>
        一页看清「现在该研究哪些买入机会」。🟢 候选 = 二轴判定值得埋伏/贵但对;🟡 临界 = 带触发条件的观望,条件兑现即转机会;🚀 启动区 = 主题刚点火的 Mode-A 时机窗。<b>非投资建议</b>。
      </p>

      <div className="lens-note">
        <span className="pill">{LENS_META[lens].icon} {LENS_META[lens].label}镜头</span>
        {lens === "hunt"
          ? <span>只看<b>瓶颈型</b>机会(上游卡脖子){hiddenN > 0 && <> · 已隐藏 <b>{hiddenN}</b> 个覆盖型(应用/大盘)</>}。切右上「覆盖」看全栈。</span>
          : <span>显示<b>完整 AI 全栈</b>机会(含云/模型/应用大盘)。切右上「猎手」聚焦瓶颈。</span>}
      </div>

      {/* 概览 + 层筛选 */}
      <div className="opp-summary">
        <div className="opp-kpi"><b className="green">{greensL.length}</b><span>🟢 候选机会</span></div>
        <div className="opp-kpi"><b className="amber">{watchTrig.length}</b><span>🟡 临界(带触发)</span></div>
        <div className="opp-kpi"><b style={{ color: "var(--green)" }}>{igniting.length}</b><span>🚀 启动区</span></div>
        <div className="chipgroup" style={{ marginLeft: "auto" }}>
          <button className={`chip ${sort === "recent" ? "on" : ""}`} onClick={() => setSort("recent")} title="最新收录的研究在前">最新</button>
          <button className={`chip ${sort === "alpha" ? "on" : ""}`} onClick={() => setSort("alpha")} title="按 α 超额排序(方法论赢家)">α 超额</button>
        </div>
        <div className="chipgroup">
          <button className={`lchip ${layer === 0 ? "on" : ""}`} onClick={() => setLayer(0)}>全部层</button>
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} className={`lchip ${layer === n ? "on" : ""}`} onClick={() => setLayer(layer === n ? 0 : n)}>
              <span className="dot" style={{ background: LAYER_META[n].color }} />{n} {LAYER_META[n].short}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="loading">LOADING…</div>}

      {/* 🟢 候选机会 */}
      <div className="section-label">🟢 候选机会 · 二轴判定值得埋伏 / 贵但对（{sortedGreens.length}）</div>
      {sortedGreens.length > 0 ? (
        <div className="oppgrid">
          {sortedGreens.map((r) => <OppCard key={r.id} r={r} onOpen={open} />)}
        </div>
      ) : (
        !loading && <div className="empty">{layer ? "该层暂无 🟢 候选 — 试试其他层" : "暂无 🟢 候选"}</div>
      )}

      {/* 🚀 启动区 */}
      {igniting.length > 0 && (
        <>
          <div className="section-label" style={{ marginTop: 30 }}>🚀 启动区 · 主题刚点火、stage=启动的 Mode-A 时机窗（{igniting.length}）</div>
          <div className="card" style={{ padding: "4px 0" }}>
            {igniting.slice(0, 18).map((r) => (
              <div className="opp-row" key={`ig-${r.id}`} onClick={() => open(r.symbol)}>
                <span className={`vdot ${r.verdict_class}`} />
                <span className="sym">{r.symbol.replace(/\.(US|HK|SHG|SHE|BJ|T)$/, "")}<small>{r.name}</small></span>
                {r.layer ? <span className="ldot" style={{ background: LAYER_META[r.layer].color }} /> : null}
                <span className="dim" style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{r.theme}</span>
                <span className="mono" style={{ fontSize: 12 }}>近1月 <span className={pctClass(r.ret_1m_pct)}>{fmtPct(r.ret_1m_pct)}</span></span>
                <span className={`mono num ${pctClass(r.alpha_pct)}`} style={{ minWidth: 64, textAlign: "right", fontWeight: 700 }}>{fmtPct(r.alpha_pct)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* 🟡 临界观望(带触发条件)*/}
      {watchTrig.length > 0 && (
        <>
          <div className="section-label" style={{ marginTop: 30 }}>🟡 临界观望 · 带触发条件,兑现即转机会（{watchTrig.length}）</div>
          <div className="card" style={{ padding: "4px 0" }}>
            {watchTrig.slice(0, 24).map((r) => (
              <div className="opp-row" key={`w-${r.id}`} onClick={() => open(r.symbol)}>
                <span className="sym">{r.symbol.replace(/\.(US|HK|SHG|SHE|BJ|T)$/, "")}<small>{r.name}</small></span>
                {r.layer ? <span className="ldot" style={{ background: LAYER_META[r.layer].color }} title={`${r.layer} ${LAYER_META[r.layer].short}`} /> : null}
                <span className="dim" style={{ minWidth: 70, maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.theme}</span>
                <span className="trigger-pill" style={{ flex: 1, minWidth: 0 }}>{r.trigger}</span>
                <span className="mono dim" style={{ fontSize: 11, minWidth: 64, textAlign: "right" }}>{r.market_label}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="mono dim" style={{ fontSize: 11.5, margin: "20px 0 30px" }}>
        机会 = 框架二轴判定输出,非买卖建议。🟢/🟡 数字来自实测价格快照;α = since-call 收益 − 同期基准(向前样本外)。点任一行/卡看 K 线与历史判定标注。
      </div>
    </div>
  );
}
