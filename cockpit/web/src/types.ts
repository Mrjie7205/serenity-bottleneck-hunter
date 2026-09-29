export interface Pick {
  id: number;
  record_date: string;
  theme: string;
  symbol: string;
  name: string;
  name_verified: string;
  market: string;
  market_label: string;
  layer: number;
  layer_name: string;
  subsector: string;
  sublayer: string;
  lens: "hunt" | "coverage";
  tier: string;
  archetypes: string;
  entry_price: string;
  currency: string;
  entry_stage: string;
  verdict: string;
  verdict_class: "green" | "amber" | "red" | "other";
  trigger: string;
  thesis: string;
  star_count: number;
  stars: string;
  star_themes: string;
  // M3 快照列(无快照时为 null)
  last: number | null;
  stage_now: StageKey | null;
  ret_1m_pct: number | null;
  since_call_pct: number | null;
  alpha_pct: number | null;
}

export type StageKey = "deep" | "range" | "early" | "parabolic";

export interface Report {
  file: string;
  title: string;
  theme: string;
  layer: number;
  layer_name: string;
  market: string;
  market_label: string;
  dogfood: number | null;
  report_date: string;
  mtime: string;
  verdict_preview: string;
  deprecated: boolean;
  size_kb: number;
}

export interface Freshness {
  theme: string;
  last_scan: string;
  age_days: number;
  level: "green" | "amber" | "red";
}

export interface Meta {
  total_picks: number;
  total_reports: number;
  themes: string[];
  markets: string[];
  market_labels: Record<string, string>;
  verdict_counts: { green: number; amber: number; red: number; other: number };
  layer_rollup: LayerRollup[];
  star_nodes: { symbol: string; name: string; star_count: number; stars: string }[];
  freshness: Freshness[];
  latest_reports: {
    file: string; title: string; theme: string;
    market_label: string; report_date: string; dogfood: number | null;
  }[];
  trigger_summary: { watch_total: number; auto: number; manual: number };
  generated_at: string;
}

export interface TriggerHit {
  checked_at?: string | null;
  symbol: string;
  name: string;
  theme: string;
  market_label: string;
  trigger_label: string;
  field: string;
  fired_value: number;
  snapshot: {
    last: number;
    ret_1m_pct: number | null;
    ret_3m_pct: number | null;
    range_pos_6mo_pct: number;
    pct_off_6mo_high: number;
    stage: string;
  };
  verdict: string;
  thesis: string;
  entry_price: string;
  currency: string;
  record_date: string;
  star_count: number;
  stars: string;
  ack: "done" | "ignore" | null;
}

export interface TriggerRun {
  demo?: boolean;
  ok?: boolean;
  error?: string;
  storage_errors?: string[];
  scope?: "full" | "partial";
  checked_at?: string;
  successful_auto?: number;
  retained_hit_count?: number;
  last_run: string;
  checked_auto: number;
  checked_manual: number;
  hit_count: number;
  error_count: number;
  hits: TriggerHit[];
  errors: { symbol: string; error: string }[];
  manual_watch: { symbol: string; name: string; theme: string; trigger_label: string; verdict: string }[];
}

export interface TriggerStatus extends TriggerRun {
  summary: { watch_total: number; auto: number; manual: number };
}

// ---------- M3 ----------

export interface DataQuality {
  ashare_total: number;
  ashare_adjusted: number;
  ashare_raw_eodhd: string[];   // A股非首选复权来源，保留字段名以兼容旧快照
  split_suspects: string[];     // 大幅跳空待核对，不推断或改写公司行动
}

export interface SnapshotStatus {
  demo?: boolean;
  exists: boolean;
  progress: { running: boolean; done: number; total: number; phase: string; error?: string | null };
  refresh_required?: boolean;
  message?: string | null;
  generated_at?: string;
  symbol_count?: number;
  error_count?: number;
  complete?: boolean;
  benchmark_errors?: string[];
  partial?: boolean;
  data_quality?: DataQuality | null;
}

export interface ScoreGroup {
  key: string;
  label: string;
  n: number;
  avg_since?: number;
  avg_alpha?: number;
  med_alpha?: number;
  win_rate?: number;
  young_n?: number;
}

export interface Scorecard {
  demo?: boolean;
  message?: string;
  available: boolean;
  generated_at?: string;
  sample_n?: number;
  seeds_excluded_n?: number;
  verdict_spread?: number | null;
  by_verdict?: ScoreGroup[];
  by_star?: ScoreGroup[];
  by_market?: ScoreGroup[];
  by_layer?: ScoreGroup[];
  by_archetype?: ScoreGroup[];
  by_theme?: ScoreGroup[];
  benchmarks?: Record<string, string>;
}

export interface StageItem {
  symbol: string;
  name: string;
  theme: string;
  verdict_class: string;
  star_count: number;
  ret_1m_pct: number | null;
  ret_3m_pct: number | null;
  range_pos_6mo_pct: number;
}

export interface StageBoard {
  available: boolean;
  generated_at?: string;
  columns: { key: StageKey; label: string; count: number; items: StageItem[] }[];
}

export interface MatrixCell {
  verdict_class: string;
  record_date: string;
  tier: string;
}

export interface StarMatrix {
  rows: {
    symbol: string;
    name: string;
    star_count: number;
    stage_key: StageKey | "";
    ret_1m_pct: number | null;
    cells: Record<string, MatrixCell>;
  }[];
  themes: string[];
  generated_at?: string;
}

// ---------- 五层蛋糕分类 ----------

export type BoardStatus = "scanned" | "planned" | "gap" | "downstream";

export interface VerdictCounts { green: number; amber: number; red: number; other: number }

export interface LayerRollup {
  layer: number;
  layer_name: string;
  coverage_strength: "strong" | "partial" | "thin" | "none";
  scanned: number;
  planned: number;
  pick_count: number;
  verdict_counts: VerdictCounts;
}

export interface TaxBoard {
  board: string;
  theme_key: string;
  sublayer: string;
  sublayer_name: string;
  lens: "hunt" | "coverage";
  status: BoardStatus;
  market: string;
  priority: number | null;
  leaders: string[];
  bottleneck_pureplays: string[];
  note: string;
  pick_count: number;
  verdict_counts: VerdictCounts;
  last_scan: string | null;
  freshness_level: "green" | "amber" | "red" | null;
  latest_report: { file: string; title: string; report_date: string; dogfood: number | null } | null;
}

export interface TaxSubsector {
  subsector: string;
  market: string;
  leaders: string[];
  boards: TaxBoard[];
}

export interface TaxLayer {
  layer: number;
  layer_name: string;
  role: string;
  coverage_strength: "strong" | "partial" | "thin" | "none";
  stat: { scanned: number; planned: number; total_boards: number; pick_count: number; verdict_counts: VerdictCounts };
  subsectors: TaxSubsector[];
}

export interface Taxonomy {
  framework: string;
  layers: TaxLayer[];
  sublayer_meta: Record<string, string>;
  hunt_sublayers: string[];
  generated_at: string;
}
