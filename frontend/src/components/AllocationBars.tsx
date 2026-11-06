import type { AllocationRow } from "../api";
import { money, pct } from "../format";
import { classColor } from "./ui";

/** Composition strip (parts of the whole) plus one labeled row per class.
 *  Every value is printed, so nothing hides behind hover. */
export function AllocationBars({ rows, ccy, onSelect }: { rows: AllocationRow[]; ccy: string; onSelect?: (key: string) => void }) {
  if (!rows.length) return <div className="empty muted">Nothing held</div>;
  const max = Math.max(...rows.map((r) => r.value), 1);
  const total = rows.reduce((a, r) => a + Math.max(r.value, 0), 0) || 1;
  return (
    <div className="alloc">
      <div className="alloc-strip" aria-hidden="true">
        {rows.filter((r) => r.value > 0).map((r) => (
          <span key={r.asset_class} style={{ width: `${(r.value / total) * 100}%`, background: classColor(r.asset_class) }} />
        ))}
      </div>
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
                <span className="bar-label">
                  <i className="key-dot" style={{ background: classColor(r.asset_class) }} />
                  {r.label}
                </span>
                <span className="bar-value">
                  <span className="muted money">{money(r.value, ccy, { compact: true })}</span>
                  <strong>{pct(r.weight)}</strong>
                </span>
              </span>
              <span className="bar-track">
                <span className="bar-fill" style={{ width: `${w}%`, background: classColor(r.asset_class) }} />
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
