import { useState, type FormEvent } from "react";
import { api, type Account, type Asset, type Transaction } from "../api";
import { today } from "../format";
import { ErrorBox, Field, useMeta } from "./ui";

type Values = Record<string, string>;

function useForm(initial: Values) {
  const [v, setV] = useState<Values>(initial);
  const set = (k: string) => (e: { target: { value: string } }) => setV((p) => ({ ...p, [k]: e.target.value }));
  return { v, setV, set };
}

const blankToNull = (s: string | undefined) => (s === undefined || s.trim() === "" ? null : s.trim());

function FormActions({ busy, onCancel, label }: { busy: boolean; onCancel: () => void; label: string }) {
  return (
    <div className="form-actions">
      <button type="button" onClick={onCancel}>Cancel</button>
      <button type="submit" className="primary" disabled={busy}>{busy ? "Saving…" : label}</button>
    </div>
  );
}

// --- account --------------------------------------------------------------------

export function AccountForm({ account, onDone, onCancel }: { account?: Account; onDone: () => void; onCancel: () => void }) {
  const meta = useMeta();
  const { v, setV, set } = useForm({
    name: account?.name ?? "",
    institution: account?.institution ?? "",
    type: account?.type ?? "broker",
    currency: account?.currency ?? meta.base_currency,
    tracks_cash: String(account?.tracks_cash ?? true),
    ownership_pct: account ? String(Number(account.ownership_pct) * 100) : "100",
    external_ref: account?.external_ref ?? "",
    notes: account?.notes ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      name: v.name, institution: blankToNull(v.institution), type: v.type, currency: v.currency,
      tracks_cash: v.tracks_cash === "true", ownership_pct: String(Number(v.ownership_pct) / 100),
      external_ref: blankToNull(v.external_ref), notes: blankToNull(v.notes), archived: account?.archived ?? false,
    };
    try {
      if (account) await api.put(`/api/accounts/${account.id}`, body);
      else await api.post("/api/accounts", body);
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <div className="form-grid">
        <Field label="Name"><input required value={v.name} onChange={set("name")} placeholder="Interactive Brokers" /></Field>
        <Field label="Type">
          <select
            value={v.type}
            onChange={(e) => {
              const t = meta.account_types.find((a) => a.key === e.target.value);
              setV((p) => ({ ...p, type: e.target.value, tracks_cash: String(t?.tracks_cash ?? true) }));
            }}
          >
            {meta.account_types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </Field>
        <Field label="Institution"><input value={v.institution} onChange={set("institution")} /></Field>
        <Field label="Currency"><input required maxLength={3} value={v.currency} onChange={set("currency")} /></Field>
        <Field label="Tracks a cash balance" hint="Brokers do; direct deals and property usually don't">
          <select value={v.tracks_cash} onChange={set("tracks_cash")}>
            <option value="true">Yes</option>
            <option value="false">No</option>
          </select>
        </Field>
        <Field label="Your ownership %" hint="e.g. 50 for a co-owned flat">
          <input type="number" min="0.01" max="100" step="any" required value={v.ownership_pct} onChange={set("ownership_pct")} />
        </Field>
        <Field label="Broker account id" hint="IBKR account number, to match imports">
          <input value={v.external_ref} onChange={set("external_ref")} placeholder="U1234567" />
        </Field>
      </div>
      <div style={{ marginTop: 12 }}>
        <Field label="Notes"><textarea value={v.notes} onChange={set("notes")} /></Field>
      </div>
      <ErrorBox error={error} />
      <FormActions busy={busy} onCancel={onCancel} label={account ? "Save account" : "Add account"} />
    </form>
  );
}

// --- asset ----------------------------------------------------------------------

export function AssetForm({ asset, onDone, onCancel }: { asset?: Asset; onDone: (a: Asset) => void; onCancel: () => void }) {
  const meta = useMeta();
  const classes = meta.asset_classes.filter((c) => c.key !== "cash");
  const { v, setV, set } = useForm({
    name: asset?.name ?? "",
    asset_class: asset?.asset_class ?? "equity",
    symbol: asset?.symbol ?? "",
    isin: asset?.isin ?? "",
    currency: asset?.currency ?? meta.base_currency,
    sector: asset?.sector ?? "",
    country: asset?.country ?? "",
    liquidity: asset?.liquidity ?? "liquid",
    valuation_method: asset?.valuation_method ?? "market",
    tags: (asset?.tags ?? []).join(", "),
    notes: asset?.notes ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      name: v.name, asset_class: v.asset_class, symbol: blankToNull(v.symbol), isin: blankToNull(v.isin),
      currency: v.currency, sector: blankToNull(v.sector), country: blankToNull(v.country), liquidity: v.liquidity,
      valuation_method: v.valuation_method, notes: blankToNull(v.notes),
      tags: v.tags.split(",").map((t) => t.trim()).filter(Boolean),
    };
    try {
      const saved = asset ? await api.put<Asset>(`/api/assets/${asset.id}`, body) : await api.post<Asset>("/api/assets", body);
      onDone(saved);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <div className="form-grid">
        <Field label="Name"><input required value={v.name} onChange={set("name")} /></Field>
        <Field label="Asset class">
          <select
            value={v.asset_class}
            onChange={(e) => {
              const c = classes.find((x) => x.key === e.target.value);
              setV((p) => ({ ...p, asset_class: e.target.value, liquidity: c?.liquidity ?? p.liquidity, valuation_method: c?.valuation ?? p.valuation_method }));
            }}
          >
            {classes.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </Field>
        <Field label="Symbol / ticker"><input value={v.symbol} onChange={set("symbol")} /></Field>
        <Field label="ISIN"><input maxLength={12} value={v.isin} onChange={set("isin")} /></Field>
        <Field label="Currency"><input required maxLength={3} value={v.currency} onChange={set("currency")} /></Field>
        <Field label="Valued by">
          <select value={v.valuation_method} onChange={set("valuation_method")}>
            <option value="market">Market price</option>
            <option value="manual">Manual valuations</option>
          </select>
        </Field>
        <Field label="Liquidity">
          <select value={v.liquidity} onChange={set("liquidity")}>
            <option value="liquid">Liquid</option>
            <option value="illiquid">Illiquid</option>
          </select>
        </Field>
        <Field label="Sector"><input value={v.sector} onChange={set("sector")} /></Field>
        <Field label="Country"><input value={v.country} onChange={set("country")} /></Field>
        <Field label="Tags" hint="Comma-separated"><input value={v.tags} onChange={set("tags")} /></Field>
      </div>
      <div style={{ marginTop: 12 }}>
        <Field label="Notes"><textarea value={v.notes} onChange={set("notes")} /></Field>
      </div>
      <ErrorBox error={error} />
      <FormActions busy={busy} onCancel={onCancel} label={asset ? "Save asset" : "Add asset"} />
    </form>
  );
}

// --- transaction --------------------------------------------------------------------

export function TransactionForm({ tx, accounts, assets, defaults, onDone, onCancel }: {
  tx?: Transaction;
  accounts: Account[];
  assets: Asset[];
  defaults?: { account_id?: number; asset_id?: number; type?: string };
  onDone: () => void;
  onCancel: () => void;
}) {
  const meta = useMeta();
  const { v, set } = useForm({
    type: tx?.type ?? defaults?.type ?? "buy",
    account_id: String(tx?.account_id ?? defaults?.account_id ?? accounts[0]?.id ?? ""),
    asset_id: String(tx?.asset_id ?? defaults?.asset_id ?? ""),
    trade_date: tx?.trade_date ?? today(),
    quantity: tx?.quantity ?? "",
    price: tx?.price ?? "",
    amount: tx?.amount ?? "",
    currency: tx?.currency ?? "",
    counter_amount: tx?.counter_amount ?? "",
    counter_currency: tx?.counter_currency ?? "",
    fees: tx && tx.fees !== "0" ? tx.fees : "",
    notes: tx?.notes ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const type = meta.tx_types.find((t) => t.key === v.type)!;
  const asset = assets.find((a) => String(a.id) === v.asset_id);
  const account = accounts.find((a) => String(a.id) === v.account_id);
  const has = (f: string) => type.fields.includes(f);
  const ccyPlaceholder = asset?.currency ?? account?.currency ?? meta.base_currency;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      type: v.type, account_id: Number(v.account_id), asset_id: type.asset === "none" || !v.asset_id ? null : Number(v.asset_id),
      trade_date: v.trade_date, quantity: has("quantity") ? blankToNull(v.quantity) : null,
      price: has("price") ? blankToNull(v.price) : null, amount: has("amount") ? blankToNull(v.amount) : null,
      currency: blankToNull(v.currency), counter_amount: has("counter_amount") ? blankToNull(v.counter_amount) : null,
      counter_currency: has("counter_currency") ? blankToNull(v.counter_currency) : null,
      fees: has("fees") ? blankToNull(v.fees) ?? "0" : "0", notes: blankToNull(v.notes),
    };
    try {
      if (tx) await api.put(`/api/transactions/${tx.id}`, body);
      else await api.post("/api/transactions", body);
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <div className="form-grid">
        <Field label="Type">
          <select value={v.type} onChange={set("type")}>
            {meta.tx_types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </Field>
        <Field label="Date"><input type="date" required value={v.trade_date} onChange={set("trade_date")} /></Field>
        <Field label="Account">
          <select required value={v.account_id} onChange={set("account_id")}>
            <option value="" disabled>Choose…</option>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </Field>
        {type.asset !== "none" && (
          <Field label={type.asset === "required" ? "Asset" : "Asset (optional)"}>
            <select required={type.asset === "required"} value={v.asset_id} onChange={set("asset_id")}>
              <option value="">{type.asset === "required" ? "Choose…" : "None (account level)"}</option>
              {assets.map((a) => <option key={a.id} value={a.id}>{a.symbol ? `${a.symbol} — ${a.name}` : a.name}</option>)}
            </select>
          </Field>
        )}
        {has("quantity") && (
          <Field label={v.type === "split" ? "Ratio (new per old)" : "Quantity"} hint={v.type === "split" ? "4 for a 4-for-1 split; 0.1 for 1-for-10" : undefined}>
            <input type="number" step="any" value={v.quantity} onChange={set("quantity")} required={v.type !== "capital_call"} />
          </Field>
        )}
        {has("price") && (
          <Field label="Price per unit"><input type="number" step="any" min="0" value={v.price} onChange={set("price")} required={["buy", "sell"].includes(v.type)} /></Field>
        )}
        {has("amount") && (
          <Field label={v.type === "fx" ? "Amount sold" : "Amount"}>
            <input type="number" step="any" value={v.amount} onChange={set("amount")} required={v.type !== "capital_call"} />
          </Field>
        )}
        <Field label={v.type === "fx" ? "Currency sold" : "Currency"}>
          <input maxLength={3} value={v.currency} onChange={set("currency")} placeholder={ccyPlaceholder} />
        </Field>
        {has("counter_amount") && (
          <>
            <Field label="Amount bought"><input type="number" step="any" required value={v.counter_amount} onChange={set("counter_amount")} /></Field>
            <Field label="Currency bought"><input maxLength={3} required value={v.counter_currency} onChange={set("counter_currency")} /></Field>
          </>
        )}
        {has("fees") && <Field label="Fees"><input type="number" step="any" min="0" value={v.fees} onChange={set("fees")} /></Field>}
      </div>
      <div style={{ marginTop: 12 }}>
        <Field label="Notes"><textarea value={v.notes} onChange={set("notes")} /></Field>
      </div>
      <ErrorBox error={error} />
      <FormActions busy={busy} onCancel={onCancel} label={tx ? "Save transaction" : "Add transaction"} />
    </form>
  );
}

// --- valuation (marks for illiquid assets) and manual prices -----------------------------------

export function ValuationForm({ asset, mode, onDone, onCancel }: { asset: Asset; mode: "mark" | "price"; onDone: () => void; onCancel: () => void }) {
  const meta = useMeta();
  const { v, set } = useForm({ date: today(), price: "", method: "last_round", source: "", confidence: "medium", notes: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "mark") {
        await api.post("/api/valuations", {
          asset_id: asset.id, date: v.date, price: v.price, method: v.method, source: blankToNull(v.source),
          confidence: v.confidence, notes: blankToNull(v.notes),
        });
      } else {
        await api.post("/api/prices", { asset_id: asset.id, date: v.date, price: v.price });
      }
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const labels: Record<string, string> = {
    last_round: "Last funding round", write_down: "Write-down", appraisal: "Appraisal", fund_statement: "Fund statement",
    own_estimate: "Own estimate", broker_statement: "Broker statement", other: "Other",
  };
  return (
    <form onSubmit={submit}>
      <div className="form-grid">
        <Field label="Date"><input type="date" required value={v.date} onChange={set("date")} /></Field>
        <Field label={`Value per unit (${asset.currency})`} hint={mode === "mark" ? "For a SAFE or property held as 1 unit, the whole value" : undefined}>
          <input type="number" step="any" min="0" required value={v.price} onChange={set("price")} />
        </Field>
        {mode === "mark" && (
          <>
            <Field label="Method">
              <select value={v.method} onChange={set("method")}>
                {meta.valuation_methods.map((m) => <option key={m} value={m}>{labels[m] ?? m}</option>)}
              </select>
            </Field>
            <Field label="Confidence">
              <select value={v.confidence} onChange={set("confidence")}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </Field>
            <Field label="Source"><input value={v.source} onChange={set("source")} placeholder="e.g. Series A at $1.80/share" /></Field>
          </>
        )}
      </div>
      {mode === "mark" && (
        <div style={{ marginTop: 12 }}>
          <Field label="Notes"><textarea value={v.notes} onChange={set("notes")} /></Field>
        </div>
      )}
      <ErrorBox error={error} />
      <FormActions busy={busy} onCancel={onCancel} label={mode === "mark" ? "Save valuation" : "Save price"} />
    </form>
  );
}
