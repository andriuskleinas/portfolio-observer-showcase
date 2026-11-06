import { useState } from "react";
import { api } from "../api";
import { ErrorBox, StatTile, useAsync } from "../components/ui";
import { fmtDate } from "../format";

interface StatusData {
  base_currency: string;
  counts: Record<string, number>;
  fx: { currency: string; last_date: string; count: number }[];
  fx_missing: string[];
  last_price_date: string | null;
  last_import: { id: number; filename: string; committed_at: string } | null;
  warnings: string[];
}

export function Status() {
  const { data, error, reload } = useAsync(() => api.get<StatusData>("/api/status"), []);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = async () => {
    setBusy(true);
    setActionError(null);
    try {
      const r = await api.post<{ updated: Record<string, number>; errors: Record<string, string> }>("/api/fx/refresh");
      const added = Object.entries(r.updated).map(([c, n]) => `${c}: ${n} new`).join(", ");
      setResult(added || "Already up to date");
      if (Object.keys(r.errors).length) setActionError(`Couldn't fetch ${Object.keys(r.errors).join(", ")} — the provider may not cover these currencies.`);
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (error) return <ErrorBox error={error} />;
  if (!data) return <div className="loading">Loading…</div>;
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Status</h1>
          <p>Data freshness and anything that needs a look. Reporting currency: {data.base_currency}.</p>
        </div>
      </div>
      <section className="tiles">
        {Object.entries(data.counts).map(([k, n]) => (
          <StatTile key={k} label={k[0].toUpperCase() + k.slice(1)}>{n.toLocaleString()}</StatTile>
        ))}
        <StatTile label="Latest price">{fmtDate(data.last_price_date)}</StatTile>
        <StatTile label="Last import" sub={data.last_import?.filename}>{data.last_import ? fmtDate(data.last_import.committed_at) : "—"}</StatTile>
      </section>
      <section className="card">
        <div className="card-head">
          <div>
            <h2>Currency rates</h2>
            <p>Daily ECB reference rates from the Frankfurter API; IBKR imports add their own</p>
          </div>
          <button onClick={refresh} disabled={busy}>{busy ? "Refreshing…" : "Refresh rates"}</button>
        </div>
        {data.fx.length === 0 && data.fx_missing.length === 0 ? (
          <p className="muted">Everything is in {data.base_currency}; no rates needed.</p>
        ) : (
          <ul className="list-plain">
            {data.fx.map((r) => (
              <li key={r.currency}>
                <span>{r.currency} → {data.base_currency}</span>
                <span className="secondary">{r.count.toLocaleString()} days · latest {fmtDate(r.last_date)}</span>
              </li>
            ))}
            {data.fx_missing.map((c) => (
              <li key={c}><span><span className="chip warn">missing</span> {c} → {data.base_currency}</span><span className="muted">refresh rates</span></li>
            ))}
          </ul>
        )}
        {result && <p className="secondary">{result}</p>}
        <ErrorBox error={actionError} />
      </section>
      <section className="card">
        <div className="card-head"><h2>Data checks</h2></div>
        {data.warnings.length === 0 ? (
          <p className="secondary"><span className="chip ok">all clear</span> No data problems found.</p>
        ) : (
          <ul className="list-plain">
            {data.warnings.map((w) => <li key={w}><span><span className="chip warn">check</span> {w}</span></li>)}
          </ul>
        )}
      </section>
    </div>
  );
}
