import type { AllocationRow } from "../api";
import { money, pct } from "../format";

/** Horizontal bars, one hue (length carries magnitude; the label carries identity).
 *  Every value is labeled at the bar tip, so nothing hides behind hover. */
export function AllocationBars({ rows, ccy, onSelect }: { rows: AllocationRow[]; ccy: string; onSelect?: (key: string) => void }) {
  if (!rows.length) return <div className="empty muted">Nothing held</div>;
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="bars" role="list">
      {rows.map((r) => {
        const w = Math.max(0, (r.value / max) * 100);
        return (
          <div
            key={r.asset_class}
            className="bar-row"
            role="listitem"
            tabIndex={onSelect ? 0 : -1}
            title={`${r.label}: ${money(r.value, ccy)} (${pct(r.weight)})`}
            onClick={() => onSelect?.(r.asset_class)}
            onKeyDown={(e) => e.key === "Enter" && onSelect?.(r.asset_class)}
          >
            <span className="bar-head">
              <span className="bar-label">{r.label}</span>
              <span className="bar-value">
                {pct(r.weight)}
                <span className="muted money">{money(r.value, ccy, { compact: true })}</span>
              </span>
            </span>
            <span className="bar-track">
              <span className="bar-fill" style={{ width: `${w}%` }} />
            </span>
          </div>
        );
      })}
    </div>
  );
}
