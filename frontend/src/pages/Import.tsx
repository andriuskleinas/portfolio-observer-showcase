import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type Account, type CsvInspect, type CsvMapping, type ImportBatch } from "../api";
import { Empty, ErrorBox, Field, useAsync, useClassLabel, useMeta } from "../components/ui";
import { fmtDate, qty, TX_LABELS } from "../format";

const FIELD_LABELS: Record<string, string> = {
  date: "Date", type: "Transaction type", symbol: "Symbol / ticker", name: "Name / company", isin: "ISIN",
  asset_class: "Asset class", quantity: "Quantity / shares", price: "Price per unit", amount: "Amount / invested",
  currency: "Currency", fees: "Fees", external_id: "Unique row id", notes: "Notes", value: "Current value",
  value_date: "Valuation date", counter_amount: "FX: amount bought", counter_currency: "FX: currency bought",
};

export function Import() {
  const meta = useMeta();
  const classLabel = useClassLabel();
  const accounts = useAsync(() => api.get<Account[]>("/api/accounts"), []);
  const history = useAsync(() => api.get<ImportBatch[]>("/api/imports"), []);
  const templates = useAsync(() => api.get<{ id: number; name: string; mapping: CsvMapping }[]>("/api/import-templates"), []);

  const [kind, setKind] = useState<"ibkr_flex" | "csv">("ibkr_flex");
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [inspect, setInspect] = useState<CsvInspect | null>(null);
  const [mapping, setMapping] = useState<CsvMapping | null>(null);
  const [templateName, setTemplateName] = useState("");
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rowFilter, setRowFilter] = useState<"all" | "new" | "duplicate" | "error">("all");

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const chooseFile = (f: File | null) => {
    setFile(f);
    setBatch(null);
    setInspect(null);
    setMapping(null);
    if (f && kind === "csv") {
      run(async () => {
        const fd = new FormData();
        fd.append("file", f);
        const res = await api.post<CsvInspect>("/api/imports/inspect", fd);
        setInspect(res);
        setMapping(res.guess);
      });
    }
  };

  const preview = () =>
    run(async () => {
      if (!file) return;
      const fd = new FormData();
      fd.append("kind", kind);
      fd.append("file", file);
      if (accountId) fd.append("account_id", accountId);
      if (kind === "csv" && mapping) fd.append("mapping", JSON.stringify(mapping));
      setBatch(await api.post<ImportBatch>("/api/imports", fd));
      history.reload();
    });

  const commit = () =>
    run(async () => {
      if (!batch) return;
      const res = await api.post<ImportBatch>(`/api/imports/${batch.id}/commit`);
      const c = res.summary.committed!;
      setNotice(`Imported ${c.transactions} transactions, ${c.assets_created.length} new assets, ${c.prices} prices and ${c.valuations} valuations. Currency rates are refreshing in the background.`);
      setBatch(null);
      setFile(null);
      history.reload();
    });

  const discard = () =>
    run(async () => {
      if (!batch) return;
      await api.del(`/api/imports/${batch.id}`);
      setBatch(null);
      history.reload();
    });

  const rollback = (b: ImportBatch) =>
    run(async () => {
      if (!confirm(`Undo the import of ${b.filename ?? "this file"}? Its transactions, prices and new assets are removed.`)) return;
      await api.post(`/api/imports/${b.id}/rollback`);
      setNotice("Import rolled back.");
      history.reload();
    });

  const saveTemplate = () =>
    run(async () => {
      if (!mapping || !templateName.trim()) return;
      await api.post("/api/import-templates", { name: templateName.trim(), mapping });
      setNotice(`Saved mapping “${templateName.trim()}”.`);
      templates.reload();
    });

  const setCol = (field: string, col: string) =>
    setMapping((m) => {
      if (!m) return m;
      const columns = { ...m.columns };
      if (col) columns[field] = col;
      else delete columns[field];
      return { ...m, columns };
    });

  if (accounts.data && accounts.data.length === 0) {
    return (
      <Empty title="Add an account first">
        <p>Imports go into an account. <Link to="/accounts">Create your Interactive Brokers account</Link> (add its account id, e.g. U1234567, so files match automatically).</p>
      </Empty>
    );
  }

  const rows = (batch?.rows ?? []).filter((r) => rowFilter === "all" || r.status === rowFilter);

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Import</h1>
          <p>Preview first, then commit. Every import can be rolled back.</p>
        </div>
      </div>

      <section className="card">
        <div className="card-head"><h2>New import</h2></div>
        <div className="form-grid">
          <Field label="Source">
            <select value={kind} onChange={(e) => { setKind(e.target.value as typeof kind); chooseFile(null); }}>
              <option value="ibkr_flex">Interactive Brokers — Flex Query (XML)</option>
              <option value="csv">CSV — Notion export or any spreadsheet</option>
            </select>
          </Field>
          <Field label="Into account">
            <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
              <option value="">{kind === "ibkr_flex" ? "Match by IBKR account id" : "Choose…"}</option>
              {(accounts.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </Field>
          <Field label="File">
            <input type="file" accept={kind === "csv" ? ".csv,text/csv" : ".xml,application/xml,text/xml"} onChange={(e) => chooseFile(e.target.files?.[0] ?? null)} />
          </Field>
        </div>
        {kind === "ibkr_flex" && (
          <p className="muted" style={{ marginBottom: 0 }}>
            In IBKR Client Portal: Performance &amp; Reports → Flex Queries → Activity Flex Query, format XML, with Trades,
            Cash Transactions, Corporate Actions, Open Positions and Conversion Rates. Steps are in <code>docs/IBKR_FLEX_SETUP.md</code>.
          </p>
        )}

        {kind === "csv" && inspect && mapping && (
          <div style={{ marginTop: 16 }}>
            <div className="card-head">
              <div>
                <h2>Match your columns</h2>
                <p>{inspect.row_count} rows · guessed from the headers — check each one</p>
              </div>
              {(templates.data ?? []).length > 0 && (
                <select aria-label="Load saved mapping" defaultValue="" onChange={(e) => {
                  const t = templates.data?.find((x) => String(x.id) === e.target.value);
                  if (t) setMapping(t.mapping);
                }}>
                  <option value="">Load saved mapping…</option>
                  {templates.data!.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              )}
            </div>
            <div className="form-grid">
              {inspect.fields.map((f) => (
                <Field key={f} label={FIELD_LABELS[f] ?? f}>
                  <select value={mapping.columns[f] ?? ""} onChange={(e) => setCol(f, e.target.value)}>
                    <option value="">—</option>
                    {inspect.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                  </select>
                </Field>
              ))}
            </div>
            <h3 style={{ margin: "16px 0 8px" }}>When a column is missing or empty</h3>
            <div className="form-grid">
              <Field label="Transaction type" hint="Holdings lists are usually buys">
                <select value={mapping.defaults.type ?? ""} onChange={(e) => setMapping({ ...mapping, defaults: { ...mapping.defaults, type: e.target.value || null } })}>
                  <option value="">Use the type column</option>
                  {meta.tx_types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
              </Field>
              <Field label="Currency">
                <input maxLength={3} value={mapping.defaults.currency} onChange={(e) => setMapping({ ...mapping, defaults: { ...mapping.defaults, currency: e.target.value.toUpperCase() } })} />
              </Field>
              <Field label="Asset class">
                <select value={mapping.defaults.asset_class} onChange={(e) => setMapping({ ...mapping, defaults: { ...mapping.defaults, asset_class: e.target.value } })}>
                  {meta.asset_classes.filter((c) => c.key !== "cash").map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                </select>
              </Field>
              <Field label="Date format" hint="Leave empty to detect">
                <input placeholder="%d/%m/%Y" value={mapping.date_format ?? ""} onChange={(e) => setMapping({ ...mapping, date_format: e.target.value || null })} />
              </Field>
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <input placeholder="Mapping name, e.g. Notion startups" value={templateName} onChange={(e) => setTemplateName(e.target.value)} />
              <button disabled={!templateName.trim() || busy} onClick={saveTemplate}>Save mapping</button>
            </div>
            {inspect.sample.length > 0 && (
              <details style={{ marginTop: 12 }}>
                <summary className="secondary">Sample rows</summary>
                <div className="table-wrap">
                  <table>
                    <thead><tr>{inspect.headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
                    <tbody>
                      {inspect.sample.map((r, i) => <tr key={i}>{inspect.headers.map((h) => <td key={h}>{r[h]}</td>)}</tr>)}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </div>
        )}

        <div className="form-actions">
          <button className="primary" disabled={!file || busy || (kind === "csv" && !accountId)} onClick={preview}>
            {busy ? "Working…" : "Preview import"}
          </button>
        </div>
        <ErrorBox error={error} />
        {notice && <div className="note-box" role="status">{notice}</div>}
      </section>

      {batch && (
        <section className="card">
          <div className="card-head">
            <div>
              <h2>Preview — {batch.filename}</h2>
              <p>Into {batch.account}. Nothing is saved until you commit.</p>
            </div>
            <div className="row">
              <button onClick={discard} disabled={busy}>Discard</button>
              <button className="primary" onClick={commit} disabled={busy || batch.summary.new === 0}>
                Commit {batch.summary.new} transactions
              </button>
            </div>
          </div>
          <div className="row" style={{ marginBottom: 12 }}>
            <span className="chip ok">{batch.summary.new} new</span>
            <span className="chip">{batch.summary.duplicate} already imported</span>
            {batch.summary.error > 0 && <span className="chip bad">{batch.summary.error} can't import</span>}
            {batch.summary.prices > 0 && <span className="chip">{batch.summary.prices} prices</span>}
            {batch.summary.fx_rates > 0 && <span className="chip">{batch.summary.fx_rates} FX rates</span>}
            {batch.summary.valuations > 0 && <span className="chip">{batch.summary.valuations} valuations</span>}
          </div>
          {batch.summary.warnings.length > 0 && (
            <ul className="list-plain" style={{ marginBottom: 12 }}>
              {batch.summary.warnings.map((w) => <li key={w}><span><span className="chip warn">check</span> {w}</span></li>)}
            </ul>
          )}
          {batch.summary.new_assets.length > 0 && (
            <p className="secondary">
              New assets: {batch.summary.new_assets.map((a) => `${a.symbol ?? a.name} (${classLabel(a.asset_class)})`).join(", ")}
            </p>
          )}
          {(batch.summary.reconciliation ?? []).length > 0 && (
            <>
              <h3 style={{ margin: "12px 0 4px" }}>Positions check against the broker</h3>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Holding</th><th className="num">Broker says</th><th className="num">After import</th><th /></tr></thead>
                  <tbody>
                    {batch.summary.reconciliation!.map((r, i) => (
                      <tr key={i}>
                        <td>{r.symbol}<span className="sub">{r.name} · {fmtDate(r.date)}</span></td>
                        <td className="num">{qty(r.reported)}</td>
                        <td className="num">{qty(r.computed)}</td>
                        <td>{r.match ? <span className="chip ok">matches</span> : <span className="chip bad">differs — earlier history may be missing</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          <div className="row" style={{ margin: "16px 0 8px" }}>
            <div className="segmented" role="group" aria-label="Rows">
              {(["all", "new", "duplicate", "error"] as const).map((s) => (
                <button key={s} aria-pressed={rowFilter === s} onClick={() => setRowFilter(s)}>{s === "all" ? "All rows" : s === "duplicate" ? "Duplicates" : s === "error" ? "Problems" : "New"}</button>
              ))}
            </div>
            {batch.row_count > batch.rows.length && <span className="muted">Showing the first {batch.rows.length} of {batch.row_count}</span>}
          </div>
          <div className="table-wrap" style={{ maxHeight: 420, overflowY: "auto" }}>
            <table>
              <thead><tr><th>Status</th><th>Date</th><th>Type</th><th>Asset</th><th className="num">Quantity</th><th className="num">Price</th><th className="num">Amount</th><th>Currency</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>
                      {r.status === "new" ? <span className="chip ok">new</span> : r.status === "duplicate" ? <span className="chip">duplicate</span> : <span className="chip bad">problem</span>}
                      {r.errors.length > 0 && <span className="sub">{r.errors.join("; ")}</span>}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>{fmtDate(r.date)}</td>
                    <td>{r.type ? TX_LABELS[r.type] ?? r.type : "—"}</td>
                    <td>
                      {r.asset ? (r.asset.symbol ?? r.asset.name) : r.type === "fx" ? `${r.currency} → ${r.counter_currency}` : "—"}
                      {r.asset && <span className="sub">{r.asset_match ? `matches ${r.asset_match.name}` : r.status === "new" ? "new asset" : ""}</span>}
                    </td>
                    <td className="num">{qty(r.quantity)}</td>
                    <td className="num">{r.price ?? "—"}</td>
                    <td className="num">{r.amount ?? "—"}</td>
                    <td>{r.currency}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card">
        <div className="card-head"><h2>Import history</h2></div>
        {(history.data ?? []).length === 0 ? (
          <p className="muted">No imports yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>When</th><th>File</th><th className="hide-sm">Account</th><th>Status</th><th className="num">Rows</th><th /></tr></thead>
              <tbody>
                {history.data!.map((b) => (
                  <tr key={b.id}>
                    <td>{fmtDate(b.created_at)}</td>
                    <td>{b.filename}<span className="sub">{b.kind === "ibkr_flex" ? "Interactive Brokers" : "CSV"}</span></td>
                    <td className="hide-sm secondary">{b.account}</td>
                    <td>{{ preview: "Preview", committed: "Committed", rolled_back: "Rolled back" }[b.status]}</td>
                    <td className="num">{b.summary.committed?.transactions ?? b.summary.new}</td>
                    <td className="num">
                      {b.status === "committed" && <button className="ghost small danger" disabled={busy} onClick={() => rollback(b)}>Roll back</button>}
                      {b.status === "preview" && <button className="ghost small" onClick={() => api.get<ImportBatch>(`/api/imports/${b.id}`).then(setBatch)}>Open</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
