import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtPct, pctClass } from "../api";
import { errorMessage } from "../request";
import { useSnapshot } from "../snapshot";
import type { Scorecard as SC, StageBoard, StarMatrix, ScoreGroup } from "../types";

const VERDICT_EMOJI: Record<string, string> = { green: "🟢", amber: "🟡", red: "🔴" };
const STAGE_DOT: Record<string, string> = {
  deep: "var(--ink-soft)", range: "var(--gray)", early: "var(--green)", parabolic: "var(--red)",
};

function GroupTable({ title, groups, note }: { title: string; groups: ScoreGroup[]; note?: string }) {
  if (!groups || groups.length === 0) return null;
  return (
    <div style={{ minWidth: 0 }}>
      <div className="section-label">{title}{note && <span className="dim" style={{ fontWeight: 400, textTransform: "none", letterSpacing: 0, marginLeft: 8 }}>{note}</span>}</div>
      <div className="tablewrap card">
        <table className="dk">
          <thead>
            <tr>
              <th>分组</th><th className="num">样本</th><th className="num">均收益</th>
              <th className="num">均α</th><th className="num">中位α</th><th className="num">胜率</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.key}>
                <td style={{ whiteSpace: "nowrap" }}>{g.label}</td>
                <td className="mono num">{g.n}{(g.young_n ?? 0) > 0 && <span className="dim" title="观察期未满 30 天"> ({g.young_n}新)</span>}</td>
                <td className={`mono num ${pctClass(g.avg_since)}`}>{fmtPct(g.avg_since)}</td>
                <td className={`mono num ${pctClass(g.avg_alpha)}`} style={{ fontWeight: 700 }}>{fmtPct(g.avg_alpha)}</td>
                <td className={`mono num ${pctClass(g.med_alpha)}`}>{fmtPct(g.med_alpha)}</td>
                <td className="mono num">{g.win_rate != null ? `${g.win_rate}%` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Scorecard() {
  const nav = useNavigate();
  const { snap, rebuild, running, error: snapshotError } = useSnapshot();   // 共享 store:与导航「同步股价」按钮同一份状态/轮询
  const [sc, setSc] = useState<SC | null>(null);
  const [board, setBoard] = useState<StageBoard | null>(null);
  const [matrix, setMatrix] = useState<StarMatrix | null>(null);
  const [err, setErr] = useState("");
  const wasRunning = useRef(false);
  const request = useRef<AbortController | null>(null);

  const loadAll = useCallback(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setErr("");
    const options = { signal: controller.signal };
    void Promise.allSettled([api.scorecard(options), api.stages(options), api.matrix(options)]).then(([score, stages, stars]) => {
      if (controller.signal.aborted) return;
      if (score.status === "fulfilled") setSc(score.value);
      if (stages.status === "fulfilled") setBoard(stages.value);
      if (stars.status === "fulfilled") setMatrix(stars.value);
      const labels = ["计分卡", "Stage 看板", "跨主题矩阵"];
      const failures = [score, stages, stars].flatMap((result, index) =>
        result.status === "rejected" ? [`${labels[index]}加载失败：${errorMessage(result.reason)}`] : []);
      setErr(failures.join("；"));
    });
  }, []);

  useEffect(() => {
    loadAll();
    return () => request.current?.abort();
  }, [loadAll]);

  // 构建完成(running:true→false)→ 刷新计分卡/看板/矩阵
  useEffect(() => {
    const r = !!snap?.progress?.running;
    if (wasRunning.current && !r) loadAll();
    wasRunning.current = r;
  }, [snap, loadAll]);

  const verdictGroups = sc?.by_verdict ?? [];
  const green = verdictGroups.find((g) => g.key === "green");
  const red = verdictGroups.find((g) => g.key === "red");

  return (
    <div className="mode-dark">
      <div className="page-title">Scorecard · 方法论是否真的有 α</div>
      <h1>判定计分卡</h1>

      {(err || snapshotError) && <div className="hintbar" role="alert" style={{ color: "var(--red)" }}>{[err, snapshotError].filter(Boolean).join("；")}</div>}
      {snap?.refresh_required && <div className="hintbar" role="status">{snap.message || "研究数据已更新，请重建快照以刷新计分卡。"}</div>}

      {/* 快照状态条 */}
      <div className="card snapbar">
        {running ? (
          <>
            <span className="mono" style={{ color: "var(--amber)", fontWeight: 700 }}>
              ⟳ 快照构建中 · {snap?.progress.phase} {snap?.progress.done}/{snap?.progress.total}
            </span>
            <progress value={snap?.progress.done} max={snap?.progress.total || 1} style={{ flex: 1, maxWidth: 360 }} />
          </>
        ) : snap?.exists ? (
          <>
            <span className="mono dim">
              快照 {snap.generated_at} · {snap.symbol_count} 标的
              {(snap.error_count ?? 0) > 0 && <span style={{ color: "var(--red)" }}> · {snap.error_count} 抓取失败</span>}
              {snap.partial && <span style={{ color: "var(--amber)" }}> · ⚠ 部分快照(测试)</span>}
            </span>
            <button className="actbtn" onClick={rebuild} disabled={snap.demo}>{snap.demo ? "历史快照（只读）" : "⟳ 重建快照(全量，可能需要几分钟)"}</button>
          </>
        ) : (
          <>
            <span className="mono dim">尚无价格快照 — 计分卡 / Stage 看板 / 实时列需要先构建一次</span>
            <button className="actbtn" onClick={rebuild} disabled={!snap || snap.demo}>▶ 构建快照(全量，可能需要几分钟)</button>
          </>
        )}
      </div>

      {sc?.message && <div className="hintbar" role="status">{sc.message}</div>}

      {!!snap?.benchmark_errors?.length && !running && (
        <div className="hintbar" role="status" style={{ color: "var(--amber)" }}>
          基准行情暂缺：{snap.benchmark_errors.join("、")}。对应市场的 α 超额收益和相关计分卡统计暂不可用；已取得的个股行情仍可查看。
        </div>
      )}

      {snap?.data_quality && !running && (() => {
        const dq = snap.data_quality;
        const probs = [...dq.ashare_raw_eodhd, ...dq.split_suspects];
        return (
          <div className={`dq-banner ${probs.length ? "warn" : "ok"}`}>
            {probs.length === 0 ? (
              <>✓ 未发现已检查的价格异常 · A股首选复权源 <b>{dq.ashare_adjusted}/{dq.ashare_total}</b> · 来源质量仍需核对</>
            ) : (
              <>
                ⚠ <b>{probs.length}</b> 个标的数据存疑 · A股前复权 {dq.ashare_adjusted}/{dq.ashare_total}
                {dq.ashare_raw_eodhd.length > 0 && <> · 非首选复权来源（需核对）:<b>{dq.ashare_raw_eodhd.join(" ")}</b></>}
                {dq.split_suspects.length > 0 && <> · 大幅跳空待核对:<b>{dq.split_suspects.join(" ")}</b></>}
              </>
            )}
          </div>
        );
      })()}

      {sc?.available ? (
        <>
          {/* 方法论 Alpha 总览 */}
          <div className="statgrid" style={{ marginTop: 22 }}>
            <div className="card stat">
              <div className={`v ${pctClass(sc.verdict_spread)}`}>{fmtPct(sc.verdict_spread)}</div>
              <div className="l">方法论价差<br /><span className="dim">🟢均α − 🔴均α(正 = 判定有效)</span></div>
            </div>
            <div className="card stat">
              <div className={`v ${pctClass(green?.avg_alpha)}`}>{fmtPct(green?.avg_alpha)}</div>
              <div className="l">🟢 候选平均超额(n={green?.n ?? 0})</div>
            </div>
            <div className="card stat">
              <div className={`v ${pctClass(red?.avg_alpha)}`}>{fmtPct(red?.avg_alpha)}</div>
              <div className="l">🔴 排除平均超额(n={red?.n ?? 0})</div>
            </div>
            <div className="card stat">
              <div className="v gold">{sc.sample_n}</div>
              <div className="l">有效样本(真实向前判定){(sc.seeds_excluded_n ?? 0) > 0 && <><br /><span className="dim">已剔除 {sc.seeds_excluded_n} 条回填种子(防循环论证)</span></>}</div>
            </div>
          </div>
          <div className="mono dim" style={{ fontSize: 11.5, marginTop: -16, marginBottom: 24 }}>
            基准:{Object.entries(sc.benchmarks ?? {}).map(([m, b]) => `${m}→${b}`).join(" · ")} ·
            α = since-call 收益 − 同期基准 · 向前(样本外)验证,非回测
          </div>

          {/* Stage 流转看板 */}
          {board?.available && (
            <>
              <div className="section-label">Stage 看板 · 全部跟踪标的现在处于哪一段(深底 → 启动 → 过热)</div>
              <div className="kanban">
                {board.columns.map((col) => (
                  <div className="kcol card" key={col.key}>
                    <div className="khead">
                      <span className="kdot" style={{ background: STAGE_DOT[col.key] }} />
                      {col.label}
                      <span className="kcount">{col.count}</span>
                    </div>
                    <div className="kbody">
                      {col.items.slice(0, 30).map((it) => (
                        <div className="kcard" key={it.symbol} onClick={() => nav(`/chart/${encodeURIComponent(it.symbol)}`)}>
                          <span className="mono" style={{ fontWeight: 700 }}>
                            {VERDICT_EMOJI[it.verdict_class] ?? "•"} {it.symbol.replace(/\.(US|HK|SHG|SHE|T)$/, "")}
                          </span>
                          <span className="kname">{it.name}</span>
                          {it.star_count >= 2 && <span className="starcell">×{it.star_count}</span>}
                          <span className={`mono ${pctClass(it.ret_1m_pct)}`} style={{ marginLeft: "auto", fontSize: 11.5 }}>
                            {fmtPct(it.ret_1m_pct)}
                          </span>
                        </div>
                      ))}
                      {col.items.length > 30 && <div className="dim mono" style={{ fontSize: 11, padding: "4px 10px" }}>… 还有 {col.items.length - 30} 只</div>}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mono dim" style={{ fontSize: 11.5, margin: "8px 0 26px" }}>
                「启动」列 = Mode A 关注区 · 「深底」列里 1m 转正的 = 明日最可能流入启动列 · 点卡片看 K 线
              </div>
            </>
          )}

          {/* 分组统计 */}
          <div className="scoregrid">
            <GroupTable title="按判定档(核心检验)" groups={sc.by_verdict ?? []} />
            <GroupTable title="按 ⭐ 星级" groups={sc.by_star ?? []} />
            <GroupTable title="按市场" groups={sc.by_market ?? []} />
            <GroupTable title="按蛋糕层(五层)" groups={sc.by_layer ?? []} />
            <GroupTable title="按原型 ①-⑨" groups={(sc.by_archetype ?? []).filter((g) => g.n >= 3)} note="样本≥3" />
          </div>
          <GroupTable title="按主题" groups={sc.by_theme ?? []} />
        </>
      ) : (
        !running && !sc?.demo && <div className="empty">构建快照后,这里会回答:「🟢 候选平均超额是多少?🔴 排除真的跑输了吗?」</div>
      )}

      {/* ⭐ 跨主题矩阵(无快照也能显示判定,有快照多 stage 色点) */}
      {matrix && matrix.rows.length > 0 && (
        <>
          <div className="section-label">⭐ 跨主题矩阵 · 被多个 capex 周期同时锁定的 root 节点</div>
          <div className="tablewrap card" style={{ marginBottom: 30 }}>
            <table className="dk matrix">
              <thead>
                <tr>
                  <th>标的</th><th className="num">⭐</th><th>现 stage</th>
                  {matrix.themes.map((t) => <th key={t} className="vert"><span>{t}</span></th>)}
                </tr>
              </thead>
              <tbody>
                {matrix.rows.map((r) => (
                  <tr key={r.symbol}>
                    <td style={{ whiteSpace: "nowrap", cursor: "pointer" }} onClick={() => nav(`/chart/${encodeURIComponent(r.symbol)}`)}>
                      <span className="sym">{r.symbol}<small>{r.name}</small></span>
                    </td>
                    <td className="starcell num">×{r.star_count}</td>
                    <td>
                      {r.stage_key ? (
                        <span className="mono" style={{ fontSize: 11.5, whiteSpace: "nowrap" }}>
                          <span className="kdot" style={{ background: STAGE_DOT[r.stage_key], display: "inline-block", marginRight: 5 }} />
                          {r.stage_key}
                          <span className={pctClass(r.ret_1m_pct)} style={{ marginLeft: 6 }}>{fmtPct(r.ret_1m_pct)}</span>
                        </span>
                      ) : <span className="dim">—</span>}
                    </td>
                    {matrix.themes.map((t) => {
                      const c = r.cells[t];
                      return (
                        <td key={t} className="mcell" title={c ? `${t} · ${c.record_date} · ${c.tier}` : ""}>
                          {c ? VERDICT_EMOJI[c.verdict_class] ?? "•" : ""}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
