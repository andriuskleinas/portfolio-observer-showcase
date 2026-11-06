import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, query, type Account, type Asset, type Transaction } from "../api";
import { AccountForm, AssetForm, TransactionForm } from "../components/forms";
import { Empty, ErrorBox, Modal, Money, useAsync, useClassLabel, useMeta } from "../components/ui";
import { fmtDate, qty, TX_LABELS } from "../format";

// --- transactions ------------------------------------------------------------------

export function Transactions() {
  const [accountId, setAccountId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Transaction | "new" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const lists = useAsync(() => Promise.all([api.get<Account[]>("/api/accounts"), api.get<Asset[]>("/api/assets")]), []);
  const txs = useAsync(
    () => api.get<Transaction[]>(`/api/transactions${query({ account_id: accountId, asset_id: assetId, limit: 2000 })}`),
    [accountId, assetId],
  );
  const [accounts, assets] = lists.data ?? [[], []];
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return txs.data ?? [];
    return (txs.data ?? []).filter((t) =>
      [t.asset_name, t.asset_symbol, t.account_name, TX_LABELS[t.type], t.notes].some((s) => s?.toLowerCase().includes(q)),
    );
  }, [txs.data, search]);

  const remove = async (t: Transaction) => {
    if (!confirm(`Delete this ${TX_LABELS[t.type]?.toLowerCase() ?? t.type} from ${fmtDate(t.trade_date)}?`)) return;
    try {
      await api.del(`/api/transactions/${t.id}`);
      txs.reload();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Transactions</h1>
          <p>Every buy, sell, dividend and cash movement. Imported rows can be undone from the Import page.</p>
        </div>
        <button className="primary" disabled={!accounts.length} onClick={() => setEditing("new")}>Add transaction</button>
      </div>
      <div className="filterbar">
        <select aria-label="Account" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
          <option value="">All accounts</option>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select aria-label="Asset" value={assetId} onChange={(e) => setAssetId(e.target.value)}>
          <option value="">All assets</option>
          {assets.map((a) => <option key={a.id} value={a.id}>{a.symbol ? `${a.symbol} — ${a.name}` : a.name}</option>)}
        </select>
        <input type="search" placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <ErrorBox error={txs.error || actionError} />
      {!accounts.length && lists.data ? (
        <Empty title="Add an account first"><p><Link to="/accounts">Create an account</Link> to hold your transactions.</p></Empty>
      ) : (
        <section className={`card ${txs.loading ? "loading" : ""}`}>
          {shown.length === 0 ? (
            <p className="muted">No transactions.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Date</th><th>Type</th><th>Asset</th><th className="hide-sm">Account</th>
                    <th className="num">Quantity</th><th className="num">Price</th><th className="num">Amount</th>
                    <th className="num hide-sm">Fees</th><th />
                  </tr>
                </thead>
                <tbody>
                  {shown.map((t) => (
                    <tr key={t.id}>
                      <td>{fmtDate(t.trade_date)}</td>
                      <td>{TX_LABELS[t.type] ?? t.type}{t.source === "import" && <span className="sub">imported</span>}</td>
                      <td>
                        {t.asset_id ? <Link to={`/assets/${t.asset_id}`}>{t.asset_symbol || t.asset_name}</Link> : <span className="muted">{t.type === "fx" ? `${t.currency} → ${t.counter_currency}` : "—"}</span>}
                      </td>
                      <td className="hide-sm secondary">{t.account_name}</td>
                      <td className="num">{qty(t.quantity)}</td>
                      <td className="num">{t.price ? <Money v={Number(t.price)} ccy={t.currency} /> : "—"}</td>
                      <td className="num">{t.amount ? <Money v={Number(t.amount)} ccy={t.currency} /> : "—"}</td>
                      <td className="num hide-sm">{Number(t.fees) ? <Money v={Number(t.fees)} ccy={t.currency} /> : "—"}</td>
                      <td className="num">
                        <button className="ghost small" onClick={() => setEditing(t)}>Edit</button>
                        <button className="ghost small danger" onClick={() => remove(t)}>Delete</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      <Modal open={editing !== null} title={editing === "new" ? "Add transaction" : "Edit transaction"} onClose={() => setEditing(null)}>
        <TransactionForm
          tx={editing && editing !== "new" ? editing : undefined}
          accounts={accounts}
          assets={assets}
          defaults={{ account_id: accountId ? Number(accountId) : undefined, asset_id: assetId ? Number(assetId) : undefined }}
          onDone={() => { setEditing(null); txs.reload(); }}
          onCancel={() => setEditing(null)}
        />
      </Modal>
    </div>
  );
}

// --- accounts ----------------------------------------------------------------------

export function Accounts() {
  const meta = useMeta();
  const { data, error, reload } = useAsync(() => api.get<Account[]>("/api/accounts"), []);
  const [editing, setEditing] = useState<Account | "new" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const typeLabel = (k: string) => meta.account_types.find((t) => t.key === k)?.label ?? k;

  const remove = async (a: Account) => {
    if (!confirm(`Delete the account “${a.name}”?`)) return;
    try {
      await api.del(`/api/accounts/${a.id}`);
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Accounts</h1>
          <p>Where your investments are held: brokers, direct deals, property, wallets.</p>
        </div>
        <button className="primary" onClick={() => setEditing("new")}>Add account</button>
      </div>
      <ErrorBox error={error || actionError} />
      <section className="card">
        {data && data.length === 0 ? (
          <Empty title="No accounts yet">
            <p>Start with your Interactive Brokers account, then one for direct startup deals.</p>
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>Type</th><th className="hide-sm">Currency</th><th className="hide-sm">Cash</th><th className="num hide-sm">Ownership</th><th /></tr></thead>
              <tbody>
                {(data ?? []).map((a) => (
                  <tr key={a.id}>
                    <td>
                      <Link to={`/?account=${a.id}`}>{a.name}</Link>
                      <span className="sub">{[a.institution, a.external_ref].filter(Boolean).join(" · ")}</span>
                    </td>
                    <td className="secondary">{typeLabel(a.type)}</td>
                    <td className="hide-sm">{a.currency}</td>
                    <td className="hide-sm secondary">{a.tracks_cash ? "Tracked" : "Not tracked"}</td>
                    <td className="num hide-sm">{Number(a.ownership_pct) * 100}%</td>
                    <td className="num">
                      <button className="ghost small" onClick={() => setEditing(a)}>Edit</button>
                      <button className="ghost small danger" onClick={() => remove(a)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <Modal open={editing !== null} title={editing === "new" ? "Add account" : "Edit account"} onClose={() => setEditing(null)}>
        <AccountForm
          account={editing && editing !== "new" ? editing : undefined}
          onDone={() => { setEditing(null); reload(); }}
          onCancel={() => setEditing(null)}
        />
      </Modal>
    </div>
  );
}

// --- assets ------------------------------------------------------------------------

export function Assets() {
  const { data, error, reload } = useAsync(() => api.get<Asset[]>("/api/assets"), []);
  const [editing, setEditing] = useState<Asset | "new" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const classLabel = useClassLabel();

  const remove = async (a: Asset) => {
    if (!confirm(`Delete “${a.name}”?`)) return;
    try {
      await api.del(`/api/assets/${a.id}`);
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Assets</h1>
          <p>Everything you can own. Imports create these automatically.</p>
        </div>
        <button className="primary" onClick={() => setEditing("new")}>Add asset</button>
      </div>
      <ErrorBox error={error || actionError} />
      <section className="card">
        {data && data.length === 0 ? (
          <Empty title="No assets yet" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>Class</th><th className="hide-sm">Currency</th><th className="hide-sm">Valued by</th><th /></tr></thead>
              <tbody>
                {(data ?? []).map((a) => (
                  <tr key={a.id}>
                    <td>
                      <Link to={`/assets/${a.id}`}>{a.name}</Link>
                      <span className="sub">{[a.symbol, a.isin, ...a.tags].filter(Boolean).join(" · ")}</span>
                    </td>
                    <td className="secondary">{classLabel(a.asset_class)}</td>
                    <td className="hide-sm">{a.currency}</td>
                    <td className="hide-sm secondary">{a.valuation_method === "manual" ? "Valuations" : "Market price"}</td>
                    <td className="num">
                      <button className="ghost small" onClick={() => setEditing(a)}>Edit</button>
                      <button className="ghost small danger" onClick={() => remove(a)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <Modal open={editing !== null} title={editing === "new" ? "Add asset" : "Edit asset"} onClose={() => setEditing(null)}>
        <AssetForm
          asset={editing && editing !== "new" ? editing : undefined}
          onDone={() => { setEditing(null); reload(); }}
          onCancel={() => setEditing(null)}
        />
      </Modal>
    </div>
  );
}
