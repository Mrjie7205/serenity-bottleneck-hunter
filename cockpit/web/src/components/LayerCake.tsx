import { LAYER_META } from "../api";
import type { TaxLayer, LayerRollup } from "../types";

const STRENGTH_LABEL: Record<string, string> = {
  strong: "覆盖充分", partial: "部分覆盖", thin: "覆盖薄", none: "空白",
};

// 顶=应用(L5,最窄)→ 底=能源(L1,最宽),视觉强化"底层是地基"
function widthPct(layer: number) {
  return 56 + (5 - layer) * 9; // L1=92% ... L5=56%
}

interface FullProps {
  layers: TaxLayer[];
  selected?: number;
  onSelect?: (n: number) => void;
}

export function LayerCake({ layers, selected, onSelect }: FullProps) {
  const byLayer = new Map(layers.map((l) => [l.layer, l]));
  return (
    <div className="cake">
      {[5, 4, 3, 2, 1].map((n) => {
        const L = byLayer.get(n);
        if (!L) return null;
        const v = L.stat.verdict_counts;
        return (
          <div
            key={n}
            className={`cake-band ${selected === n ? "sel" : ""}`}
            style={{ width: `${widthPct(n)}%`, background: LAYER_META[n].color }}
            onClick={() => onSelect?.(n)}
            title={L.role}
          >
            <span className="cb-n">{n}</span>
            <div>
              <div className="cb-name">{L.layer_name}</div>
              <div className="cb-role">{L.role.split("—")[1]?.trim() || L.role}</div>
            </div>
            <div className="cb-right">
              <div className="cb-stat">
                已扫 {L.stat.scanned} · 待扫 {L.stat.planned}
                <br />
                {L.stat.pick_count} 标的 · 🟢{v.green}/🟡{v.amber}/🔴{v.red}
              </div>
              <span className="cb-strength">{STRENGTH_LABEL[L.coverage_strength]}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface MiniProps {
  rollup: LayerRollup[];
  onPick?: (n: number) => void;
}

export function MiniCake({ rollup, onPick }: MiniProps) {
  const byLayer = new Map(rollup.map((l) => [l.layer, l]));
  return (
    <div className="minicake">
      {[5, 4, 3, 2, 1].map((n) => {
        const L = byLayer.get(n);
        if (!L) return null;
        return (
          <div
            key={n}
            className="minicake-band"
            style={{ width: `${widthPct(n)}%`, background: LAYER_META[n].color }}
            onClick={() => onPick?.(n)}
            title={`${L.layer_name} · ${STRENGTH_LABEL[L.coverage_strength]}`}
          >
            {n} {L.layer_name}
            <span className="mc-c">{L.scanned}扫/{L.planned}待</span>
          </div>
        );
      })}
    </div>
  );
}
