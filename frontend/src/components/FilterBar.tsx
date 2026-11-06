import { useSearchParams } from "react-router-dom";
import { PERIOD_LABELS } from "../format";

export interface DashFilters {
  period: string;
  assetClass: string;
  accountId: string;
  includeIlliquid: boolean;
}

/** Filter state lives in the URL so any view can be bookmarked (VIEW-02). */
export function useDashFilters(defaultPeriod = "YTD"): [DashFilters, (patch: Partial<DashFilters>) => void] {
  const [sp, setSp] = useSearchParams();
  const f: DashFilters = {
    period: sp.get("period") ?? defaultPeriod,
    assetClass: sp.get("class") ?? "",
    accountId: sp.get("account") ?? "",
    includeIlliquid: sp.get("illiquid") !== "0",
  };
  const update = (patch: Partial<DashFilters>) => {
    const n = { ...f, ...patch };
    const next = new URLSearchParams();
    if (n.period !== defaultPeriod) next.set("period", n.period);
    if (n.assetClass) next.set("class", n.assetClass);
    if (n.accountId) next.set("account", n.accountId);
    if (!n.includeIlliquid) next.set("illiquid", "0");
    setSp(next, { replace: true });
  };
  return [f, update];
}

export function PeriodPicker({ value, onChange, periods }: { value: string; onChange: (p: string) => void; periods: string[] }) {
  return (
    <div className="segmented" role="group" aria-label="Period">
      {periods.map((p) => (
        <button key={p} aria-pressed={p === value} onClick={() => onChange(p)}>
          {PERIOD_LABELS[p] ?? p}
        </button>
      ))}
    </div>
  );
}

export function FilterBar({ f, update, periods, classes, accounts }: {
  f: DashFilters;
  update: (p: Partial<DashFilters>) => void;
  periods: string[];
  classes: { key: string; label: string }[];
  accounts: { id: number; name: string }[];
}) {
  const active = f.assetClass || f.accountId || !f.includeIlliquid;
  return (
    <div className="filterbar">
      <PeriodPicker value={f.period} onChange={(period) => update({ period })} periods={periods} />
      <select aria-label="Asset class" value={f.assetClass} onChange={(e) => update({ assetClass: e.target.value })}>
        <option value="">All asset classes</option>
        {classes.map((c) => (
          <option key={c.key} value={c.key}>{c.label}</option>
        ))}
      </select>
      <select aria-label="Account" value={f.accountId} onChange={(e) => update({ accountId: e.target.value })}>
        <option value="">All accounts</option>
        {accounts.map((a) => (
          <option key={a.id} value={a.id}>{a.name}</option>
        ))}
      </select>
      <label className="check">
        <input type="checkbox" checked={f.includeIlliquid} onChange={(e) => update({ includeIlliquid: e.target.checked })} />
        Include illiquid
      </label>
      {active && (
        <button className="ghost small" onClick={() => update({ assetClass: "", accountId: "", includeIlliquid: true })}>
          Clear filters
        </button>
      )}
    </div>
  );
}
