import type {
  Meta, Pick, Report, TriggerStatus, TriggerRun,
  SnapshotStatus, Scorecard, StageBoard, StarMatrix, Taxonomy,
} from "./types";
import { request, type RequestOptions } from "./request";

const get = <T>(url: string, options?: RequestOptions) => request<T>(url, "GET", options);
const post = <T>(url: string, options?: RequestOptions) => request<T>(url, "POST", options);

export const api = {
  health: (options?: RequestOptions) => get<{ ok: boolean; version: string; demo: boolean; dataset_label: string; price_asof: string | null }>("/api/health", options),
  meta: (options?: RequestOptions) => get<Meta>("/api/meta", options),
  picks: (params: Record<string, string>, options?: RequestOptions) => {
    const q = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== ""))
    );
    return get<{ count: number; rows: Pick[] }>(`/api/picks?${q}`, options);
  },
  reports: (includeDeprecated = false, options?: RequestOptions) =>
    get<{ count: number; rows: Report[] }>(
      `/api/reports?include_deprecated=${includeDeprecated}`, options),
  reportUrl: (file: string) => `/api/report-file/${encodeURIComponent(file)}`,
  klineUrl: (symbol: string, days = 400) => `/api/kline/${encodeURIComponent(symbol)}?days=${days}`,
  triggersStatus: (options?: RequestOptions) => get<TriggerStatus>("/api/triggers/status", options),
  runTriggers: (limit = 0, options?: RequestOptions) => post<TriggerRun>(`/api/triggers/run?limit=${limit}`, { timeoutMs: 20 * 60_000, ...options }),
  ackTrigger: (symbol: string, label: string, action: "done" | "ignore" | "clear", options?: RequestOptions) =>
    post<{ ok: boolean; error?: string; storage_errors?: string[] }>(`/api/triggers/ack?symbol=${encodeURIComponent(symbol)}&trigger_label=${encodeURIComponent(label)}&action=${action}`, options),
  snapshotStatus: (options?: RequestOptions) => get<SnapshotStatus>("/api/snapshot/status", options),
  runSnapshot: (limit = 0, options?: RequestOptions) => post<{ started: boolean }>(`/api/snapshot/run?limit=${limit}`, options),
  scorecard: (options?: RequestOptions) => get<Scorecard>("/api/scorecard", options),
  stages: (options?: RequestOptions) => get<StageBoard>("/api/stages", options),
  matrix: (options?: RequestOptions) => get<StarMatrix>("/api/matrix", options),
  taxonomy: (options?: RequestOptions) => get<Taxonomy>("/api/taxonomy", options),
};

// 五层蛋糕:层号 → 品牌色 + 简称(全站统一层视觉语言)
export const LAYER_META: Record<number, { short: string; color: string }> = {
  1: { short: "能源", color: "var(--layer-1)" },
  2: { short: "芯片", color: "var(--layer-2)" },
  3: { short: "基建", color: "var(--layer-3)" },
  4: { short: "模型", color: "var(--layer-4)" },
  5: { short: "应用", color: "var(--layer-5)" },
};

export const fmtPct = (v: number | null | undefined, signed = true): string => {
  if (v === null || v === undefined) return "—";
  const s = v > 0 && signed ? "+" : "";
  return `${s}${v.toFixed(1)}%`;
};

export const pctClass = (v: number | null | undefined): string =>
  v === null || v === undefined ? "dim" : v > 0 ? "pos" : v < 0 ? "neg" : "dim";

// 6 月区间位置 → 人话水位词(与报告模板同一套口径)
export const rngWord = (rng: number | null | undefined): string => {
  if (rng === null || rng === undefined) return "—";
  if (rng >= 90) return "贴顶";
  if (rng >= 70) return "高位";
  if (rng >= 30) return "中位";
  if (rng >= 10) return "低位";
  return "贴底";
};
