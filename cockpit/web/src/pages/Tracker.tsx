import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, fmtPct, pctClass, LAYER_META } from "../api";
import { errorMessage } from "../request";
import { useLens, LENS_META } from "../lens";
import type { Meta, Pick, Taxonomy } from "../types";

const LAYERS = [1, 2, 3, 4, 5];

const VERDICTS = [
  { key: "green", label: "🟢 候选", cls: "on-green" },
  { key: "amber", label: "🟡 观望", cls: "on-amber" },
  { key: "red", label: "🔴 排除", cls: "on-red" },
] as const;

const ARCHETYPES = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"];

type SortKey = "date" | "since" | "alpha" | "star";

const STAGE_BADGE: Record<string, { label: string; color: string }> = {
  deep: { label: "深底", color: "var(--ink-soft)" },
  range: { label: "震荡", color: "var(--gray)" },
  early: { label: "启动", color: "var(--green)" },
  parabolic: { label: "过热", color: "var(--red)" },
};

const STAGES = [
  { key: "deep", label: "深底" },
  { key: "range", label: "震荡" },
  { key: "early", label: "启动" },
  { key: "parabolic", label: "过热" },
] as const;

export default function Tracker() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [tax, setTax] = useState<Taxonomy | null>(null);
  const [rows, setRows] = useState<Pick[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filterError, setFilterError] = useState("");
  const [lens] = useLens();

  // 筛选状态全部进 URL —— 看完 K 线返回不丢
  const theme = params.get("theme") ?? "";
  const market = params.get("market") ?? "";
  const verdict = params.get("verdict") ?? "";
  const archetype = params.get("arch") ?? "";
  const layer = Number(params.get("layer")) || 0;
  const subsector = params.get("subsector") ?? "";
  const stage = params.get("stage") ?? "";
  const starOnly = params.get("star") === "1";
  const urlQ = params.get("q") ?? "";
  const sortKey = (params.get("sort") as SortKey) || "date";

  const [q, setQ] = useState(urlQ);
  const [qDebounced, setQDebounced] = useState(urlQ);

  const patch = (kv: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(kv)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace: true });
  };

  useEffect(() => {
    const controller = new AbortController();
    api.meta({ signal: controller.signal }).then((value) => {
      if (!controller.signal.aborted) setMeta(value);
    }).catch((error) => {
      if (!controller.signal.aborted) setFilterError(`主题与市场选项加载失败：${errorMessage(error)}`);
    });
    api.taxonomy({ signal: controller.signal }).then((value) => {
      if (!controller.signal.aborted) setTax(value);
    }).catch((error) => {
      if (!controller.signal.aborted) setFilterError(`板块选项加载失败：${errorMessage(error)}`);
    });
    return () => controller.abort();
  }, []);

  const subsectorOpts = useMemo(() => {
    if (!tax) return [];
    const layers = layer ? tax.layers.filter((l) => l.layer === layer) : tax.layers;
    const set = new Set<string>();
    layers.forEach((l) => l.subsectors.forEach((s) => set.add(s.subsector)));
    return [...set];
  }, [tax, layer]);

  useEffect(() => {
    const t = setTimeout(() => {
      setQDebounced(q);
      if (q !== urlQ) patch({ q });
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setRows([]);
    setCount(0);
    api
      .picks({
        theme,
        market,
        verdict,
        archetype,
        layer: layer ? String(layer) : "",
        subsector,
        star_min: starOnly ? "2" : "",
        q: qDebounced,
      }, { signal: controller.signal })
      .then((d) => {
        if (controller.signal.aborted) return;
        setRows(d.rows);
        setCount(d.count);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(`跟踪数据加载失败：${errorMessage(error)}`);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [theme, market, verdict, archetype, layer, subsector, starOnly, qDebounced]);

  const sorted = useMemo(() => {
    // 镜头(猎手只看瓶颈型)+ stage(现状态)客户端筛选 —— 依赖快照,无 backend 参数
    const lensRows = lens === "hunt" ? rows.filter((r) => r.lens === "hunt") : rows;
    const arr = stage ? lensRows.filter((r) => r.stage_now === stage) : [...lensRows];
    const nil = -Infinity;
    if (sortKey === "since") arr.sort((a, b) => (b.since_call_pct ?? nil) - (a.since_call_pct ?? nil));
    else if (sortKey === "alpha") arr.sort((a, b) => (b.alpha_pct ?? nil) - (a.alpha_pct ?? nil));
    else if (sortKey === "star") arr.sort((a, b) => b.star_count - a.star_count || (b.record_date < a.record_date ? -1 : 1));
    return arr; // date = 后端默认序
  }, [rows, sortKey, stage, lens]);

  // 仅镜头隐藏的条数(不含 stage 过滤)—— 用于"已隐藏覆盖型"计数,避免叠加 stage 时高估
  const lensHidden = useMemo(
    () => (lens === "hunt" ? rows.filter((r) => r.lens !== "hunt").length : 0),
    [rows, lens]
  );

  const hasSnapshot = rows.some((r) => r.last !== null);

  const marketChips = useMemo(
    () =>
      (meta?.markets ?? []).map((m) => ({
        key: m,
        label: meta?.market_labels[m] ?? m,
      })),
    [meta]
  );

  const Th = ({ k, children }: { k: SortKey; children: ReactNode }) => (
    <th className={`sortable num ${sortKey === k ? "sorted" : ""}`}
      onClick={() => patch({ sort: sortKey === k ? "" : k })}
      title="点击排序">
      {children}{sortKey === k ? " ▾" : ""}
    </th>
  );

  return (
    <div className="mode-dark">
      <div className="page-title">Tracker · 全部判定可追溯</div>
      <h1>标的跟踪</h1>

      {(error || filterError) && <div className="hintbar" role="alert" style={{ color: "var(--red)" }}>{error || filterError}</div>}

      <div className="filterbar">
        <div className="chipgroup" title="按五层蛋糕筛选">
          {LAYERS.map((n) => (
            <button
              key={n}
              className={`lchip ${layer === n ? "on" : ""}`}
              onClick={() => patch({ layer: layer === n ? "" : String(n), subsector: "" })}
            >
              <span className="dot" style={{ background: LAYER_META[n].color }} />
              {n} {LAYER_META[n].short}
            </button>
          ))}
        </div>

        {subsectorOpts.length > 0 && (
          <select className="dk" value={subsector} onChange={(e) => patch({ subsector: e.target.value })} title="按板块筛选">
            <option value="">{layer ? `第${layer}层 全部板块` : "全部板块"}</option>
            {subsectorOpts.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        )}

        <select className="dk" value={theme} onChange={(e) => patch({ theme: e.target.value })}>
          <option value="">全部主题</option>
          {(meta?.themes ?? []).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <div className="chipgroup">
          {marketChips.map((m) => (
            <button
              key={m.key}
              className={`chip ${market === m.key ? "on" : ""}`}
              onClick={() => patch({ market: market === m.key ? "" : m.key })}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div className="chipgroup">
          {VERDICTS.map((v) => (
            <button
              key={v.key}
              className={`chip ${verdict === v.key ? v.cls : ""}`}
              onClick={() => patch({ verdict: verdict === v.key ? "" : v.key })}
            >
              {v.label}
            </button>
          ))}
        </div>

        <select className="dk" value={archetype} onChange={(e) => patch({ arch: e.target.value })} title="按原型筛选">
          <option value="">原型 ①-⑨</option>
          {ARCHETYPES.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>

        <div className="chipgroup" title="按现状态筛选(需价格快照:深底→启动→过热)">
          {STAGES.map((s) => (
            <button
              key={s.key}
              className={`chip ${stage === s.key ? "on" : ""}`}
              onClick={() => patch({ stage: stage === s.key ? "" : s.key })}
            >
              {s.label}
            </button>
          ))}
        </div>

        <button className={`chip ${starOnly ? "on" : ""}`} onClick={() => patch({ star: starOnly ? "" : "1" })}>
          ⭐ 跨主题
        </button>

        <input
          className="dk"
          placeholder="搜代码 / 名称 / thesis…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <span className="count-note">{loading ? "…" : (stage || lens === "hunt") ? `${sorted.length} / ${count} 条(${[stage && STAGES.find((s) => s.key === stage)?.label, lens === "hunt" && "猎手镜头"].filter(Boolean).join(" · ")})` : `${count} 条判定`}</span>
      </div>

      {lens === "hunt" && !loading && lensHidden > 0 && (
        <div className="lens-note">
          <span className="pill">{LENS_META.hunt.icon} 猎手镜头</span>
          <span>只看<b>瓶颈型</b>标的,已隐藏 <b>{lensHidden}</b> 条覆盖型(应用/大盘广扫)。切右上「覆盖」看全部。</span>
        </div>
      )}

      {!hasSnapshot && !loading && rows.length > 0 && (
        <div className="hintbar mono">
          ⓘ 最新价 / since-call / α 列需要价格快照 —— 去「计分卡」页点一次「构建快照」
        </div>
      )}

      <div className="tablewrap card">
        <table className="dk">
          <thead>
            <tr>
              <th>日期</th>
              <th>代码 / 名称</th>
              <th>市场</th>
              <th>主题</th>
              <th>判定</th>
              <th>Trigger / 理由</th>
              <th className="num">Entry</th>
              <th className="num">最新</th>
              <Th k="since">since-call</Th>
              <Th k="alpha">α 超额</Th>
              <th>现 stage</th>
              <Th k="star">⭐</Th>
              <th>Thesis</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const sb = r.stage_now ? STAGE_BADGE[r.stage_now] : null;
              return (
                <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => nav(`/chart/${encodeURIComponent(r.symbol)}`)} title="查看 K 线 + 判定标注">
                  <td className="mono dim" style={{ whiteSpace: "nowrap" }}>
                    {r.record_date}
                  </td>
                  <td>
                    <span className="sym">
                      {r.symbol} <span style={{ color: "var(--gold)", fontWeight: 400 }}>↗</span>
                      <small>{r.name}</small>
                    </span>
                  </td>
                  <td>
                    <span className="mkt">{r.market_label}</span>
                  </td>
                  <td className="dim" style={{ whiteSpace: "nowrap" }}>
                    {r.layer ? <span className="ldot" style={{ background: LAYER_META[r.layer]?.color }} title={`第${r.layer}层 ${LAYER_META[r.layer]?.short} · ${r.subsector ?? ""}`} /> : null}
                    {r.theme}
                  </td>
                  <td>
                    <span className={`vbadge ${r.verdict_class}`} title={r.verdict}>
                      {r.verdict_class === "green" ? "🟢 候选" : r.verdict_class === "amber" ? "🟡 观望" : r.verdict_class === "red" ? "🔴 排除" : "—"}
                    </span>
                  </td>
                  <td>{r.trigger ? <span className="trigger-pill">{r.trigger}</span> : <span className="dim">—</span>}</td>
                  <td className="mono num" style={{ whiteSpace: "nowrap" }}>
                    {r.entry_price} <span className="dim">{r.currency}</span>
                  </td>
                  <td className="mono num">{r.last ?? "—"}</td>
                  <td className={`mono num ${pctClass(r.since_call_pct)}`}>{fmtPct(r.since_call_pct)}</td>
                  <td className={`mono num ${pctClass(r.alpha_pct)}`} style={{ fontWeight: 700 }}>{fmtPct(r.alpha_pct)}</td>
                  <td>
                    {sb ? (
                      <span className="stagebadge" style={{ color: sb.color, borderColor: sb.color }}>{sb.label}</span>
                    ) : (
                      <span className="dim">—</span>
                    )}
                  </td>
                  <td className="starcell" title={r.star_themes}>
                    {r.star_count >= 2 ? `${r.stars}${r.star_count}` : ""}
                  </td>
                  <td>
                    <div className="thesis" title={`${r.tier} · ${r.archetypes}\n${r.entry_stage}\n${r.thesis}`}>
                      {r.thesis}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!loading && !error && rows.length === 0 && <div className="empty">无匹配 — 调整筛选条件</div>}
      </div>
    </div>
  );
}
