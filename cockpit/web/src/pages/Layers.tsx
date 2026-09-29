import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, LAYER_META } from "../api";
import { useLens, LENS_META } from "../lens";
import { LayerCake } from "../components/LayerCake";
import type { Taxonomy, TaxLayer, TaxBoard } from "../types";

const STATUS_LABEL: Record<string, string> = {
  scanned: "已扫", planned: "待扫", gap: "无纯标", downstream: "下游",
};

function VBar({ b }: { b: TaxBoard }) {
  const v = b.verdict_counts;
  if (!b.pick_count) return null;
  return (
    <span className="vbar mono">
      🟢<b className="pos">{v.green}</b> 🟡<b className="amber">{v.amber}</b> 🔴<b className="neg">{v.red}</b>
    </span>
  );
}

export default function Layers() {
  const [tax, setTax] = useState<Taxonomy | null>(null);
  const [err, setErr] = useState("");
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const [lens] = useLens();
  const sel = Number(params.get("layer")) || tax?.layers[0]?.layer || 1;
  const showB = (b: TaxBoard) => lens === "coverage" || b.lens === "hunt";

  useEffect(() => {
    api.taxonomy().then(setTax).catch((e) => setErr(String(e)));
  }, []);

  const setSel = (n: number) => {
    const next = new URLSearchParams(params);
    next.set("layer", String(n));
    setParams(next, { replace: true });
  };

  const roadmap = useMemo(() => {
    if (!tax) return [];
    const out: { board: TaxBoard; layer: number; layer_name: string }[] = [];
    for (const L of tax.layers)
      for (const s of L.subsectors)
        for (const b of s.boards)
          if (b.status === "planned" && (lens === "coverage" || b.lens === "hunt"))
            out.push({ board: b, layer: L.layer, layer_name: L.layer_name });
    return out.sort((a, b) => (b.board.priority ?? 0) - (a.board.priority ?? 0));
  }, [tax, lens]);

  if (err) return <div className="mode-dark"><div className="empty">后端未启动?{err}</div></div>;
  if (!tax) return <div className="mode-dark"><div className="loading">LOADING…</div></div>;

  const layer: TaxLayer | undefined = tax.layers.find((l) => l.layer === sel);

  const openBoard = (b: TaxBoard) => {
    if (b.status !== "scanned" || !b.theme_key) return;
    if (b.latest_report) nav(`/library/${encodeURIComponent(b.latest_report.file)}`);
    else nav(`/tracker?theme=${encodeURIComponent(b.theme_key)}`);
  };

  return (
    <div className="mode-dark">
      <div className="page-title">Five-Layer Cake · 黄仁勋 AI 五层蛋糕</div>
      <h1>蛋糕地图</h1>
      {tax.layers.length === 0 && <div className="empty">当前研究目录还没有主题分类。可以先导入跟踪记录，再按说明补充 theme_taxonomy.csv。</div>}
      <p className="lead" style={{ color: "var(--muted)", marginTop: -8, marginBottom: 18, fontSize: 14 }}>
        {tax.framework} · 每层拉动下层,底层战争是能源战争。点击任一层查看其板块与待扫路线。
      </p>

      <LayerCake layers={tax.layers} selected={sel} onSelect={setSel} />

      {layer && (
        <div className="layer-detail">
          <div className="section-label" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="lbadge" style={{ color: LAYER_META[layer.layer].color }}>
              <span className="dot" />第 {layer.layer} 层 · {layer.layer_name}
            </span>
            <span className="dim mono" style={{ fontSize: 11.5, textTransform: "none", letterSpacing: 0 }}>
              {layer.role}
            </span>
          </div>

          {lens === "hunt" && (
            <div className="lens-note">
              <span className="pill">{LENS_META.hunt.icon} 猎手镜头</span>
              <span>只显示<b>瓶颈型</b>子层(上游卡脖子),已隐藏覆盖型(云/模型/应用大盘)。切右上「覆盖」看完整 AI 全栈。</span>
            </div>
          )}
          {lens === "hunt" && !layer.subsectors.some((s) => s.boards.some(showB)) && (
            <div className="empty">本层在猎手镜头下暂无瓶颈型板块 — 切「覆盖」镜头查看完整堆栈</div>
          )}

          {layer.subsectors.map((s) => {
            const vboards = s.boards.filter(showB);
            if (!vboards.length) return null;
            return (
            <div className="subsec" key={s.subsector}>
              <div className="subsec-h">
                <span className="sname">{s.subsector}</span>
                {s.leaders.length > 0 && <span className="sleaders">龙头 {s.leaders.join(" · ")}</span>}
              </div>
              <div className="bgrid">
                {vboards.map((b) => (
                  <div
                    key={b.board}
                    className={`bcard ${b.status} ${b.status === "scanned" ? "clickable" : ""}`}
                    onClick={() => openBoard(b)}
                    title={b.status === "scanned" ? "打开报告 / 跟踪表" : b.note}
                  >
                    <div className="bc-top">
                      <span className="bc-name">{b.board}</span>
                      <span className={`bc-status ${b.status}`}>{STATUS_LABEL[b.status]}</span>
                    </div>
                    {b.note && <div className="bc-sub">{b.note}</div>}
                    <div className="bc-meta">
                      {b.sublayer && <span className={`sublchip ${b.lens}`} title={`11层子层 · ${b.lens === "hunt" ? "瓶颈猎场" : "覆盖型"}`}>{b.sublayer} {b.sublayer_name}</span>}
                      <span>{b.market}</span>
                      {b.status === "scanned" && <span>{b.pick_count} 标的</span>}
                      <VBar b={b} />
                      {b.priority != null && <span className="pri">优先级 {b.priority}</span>}
                      {b.last_scan && <span>扫于 {b.last_scan}</span>}
                    </div>
                    {b.bottleneck_pureplays.length > 0 && (
                      <div className="bc-meta">
                        <span className="pp mono">纯标的:{b.bottleneck_pureplays.join(" · ")}</span>
                      </div>
                    )}
                    {b.latest_report && (
                      <div className="bc-meta">
                        <span className="mono" style={{ color: "var(--burg)" }}>
                          📄 {b.latest_report.title.slice(0, 22)}{b.latest_report.dogfood != null ? ` · #${b.latest_report.dogfood}` : ""}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
            );
          })}
        </div>
      )}

      <div className="section-label">⚑ 待扫路线图 — 全部 planned 板块按优先级(下一步逐个分析的 backlog)</div>
      <div className="card" style={{ padding: "6px 0", marginBottom: 30 }}>
        {roadmap.map(({ board, layer_name, layer }) => (
          <div className="roadmap-row" key={`${layer_name}-${board.board}`}>
            <span className="pri-n">{board.priority ?? "-"}</span>
            <span className="lbadge" style={{ color: LAYER_META[layer].color, minWidth: 64 }}>
              <span className="dot" />{LAYER_META[layer].short}
            </span>
            <span className="rm-board">{board.board}</span>
            {board.bottleneck_pureplays.length > 0 && (
              <span className="rm-pp">{board.bottleneck_pureplays.join(" · ")}</span>
            )}
            <span className="rm-note">{board.note}</span>
          </div>
        ))}
        {roadmap.length === 0 && <div className="empty">暂无待扫板块</div>}
      </div>
    </div>
  );
}
