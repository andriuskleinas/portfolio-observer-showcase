import { useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, query, type Account, type Asset, type AssetDetail } from "../api";
import { PeriodPicker } from "../components/FilterBar";
import { AssetForm, TransactionForm, ValuationForm } from "../components/forms";
import { LineChart, type Marker } from "../components/LineChart";
import { Delta, ErrorBox, Modal, Money, StatTile, useAsync, useMeta } from "../components/ui";
import { fmtDate, money, pct, qty, TX_LABELS } from "../format";

export function HoldingDetail() {
  const { id } = useParams();
  const meta = useMeta();
  const [sp, setSp] = useSearchParams();
  const period = sp.get("period") ?? "ALL";
  const { data, error, loading, reload } = useAsync(
    () => api.get<AssetDetail>(`/api/assets/${id}/detail${query({ period })}`),
    [id, period],
  );
  const lists = useAsync(() => Promise.all([api.get<Account[]>("/api/accounts"), api.get<Asset[]>("/api/assets")]), []);
  const [dialog, setDialog] = useState<null | "mark" | "price" | "edit" | "tx">(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return <div className="loading">Loading…</div>;
  const { asset, summary: s, all_time: at } = data;
  const ccy = data.base_currency;
  const open = data.positions.filter((p) => p.quantity !== 0);
  const value = open.reduce((t, p) => t + p.value, 0);
  const cost = open.reduce((t, p) => t + (p.cost_basis ?? 0), 0);
  const quantity = open.reduce((t, p) => t + p.quantity, 0);
  const manual = asset.valuation_method === "manual";
  const stale = open.some((p) => p.stale);
  const lastPrice = open[0];

  const markerColor = { buy: "var(--series-3)", sell: "var(--series-2)" } as Record<string, string>;
  const markers: Marker[] = data.transactions
    .filter((t) => (t.type === "buy" || t.type === "sell") && t.price && t.trade_date >= s.start)
    .map((t) => ({
      date: t.trade_date,
      y: Number(t.price),
      color: markerColor[t.type],
      label: `${TX_LABELS[t.type]} ${qty(t.quantity)} @ ${money(Number(t.price), t.currency)}`,
    }));

  // A manual valuation holds until the next one, so carry the last value to today.
  const pricePoints = data.prices.map((p) => ({ date: p.date, y: p.price }));
  const lastPoint = pricePoints[pricePoints.length - 1];
  if (manual && lastPoint && lastPoint.date < data.as_of && open.length) pricePoints.push({ date: data.as_of, y: lastPoint.y });

  const done = () => {
    setDialog(null);
    reload();
  };

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setActionError(null);
    for (const file of Array.from(files)) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("asset_id", String(asset.id));
      try {
        await api.post("/api/attachments", fd);
      } catch (e) {
        setActionError((e as Error).message);
      }
    }
    if (fileRef.current) fileRef.current.value = "";
    reload();
  };

  const remove = async (path: string, what: string) => {
    if (!confirm(`Delete this ${what}? This can't be undone.`)) return;
    setActionError(null);
    try {
      await api.del(path);
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  return (
    <div className={`stack ${loading ? "loading" : ""}`}>
      <div className="page-head">
        <div>
          <div className="muted"><Link to="/">Dashboard</Link> / {data.class_label}</div>
          <h1>{asset.name}</h1>
          <p>
            {[asset.symbol, asset.isin, asset.currency, manual ? "valued manually" : "market priced", asset.liquidity].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="row">
          <button className="primary" onClick={() => setDialog(manual ? "mark" : "price")}>
            {manual ? "Add valuation" : "Set price"}
          </button>
          <button onClick={() => setDialog("tx")}>Add transaction</button>
          <button onClick={() => setDialog("edit")}>Edit asset</button>
        </div>
      </div>

      {stale && (
        <div className="note-box">
          <span className="chip warn">stale</span> The latest {lastPrice?.price_source === "mark" ? "valuation" : "price"} is from{" "}
          {fmtDate(lastPrice?.price_date)}. {manual ? "Add a new valuation when you get an update." : "Refresh prices or set one manually."}
        </div>
      )}
      <ErrorBox error={actionError} />

      <section className="tiles">
        <StatTile label="Value" sub={lastPrice?.price != null ? <>{qty(quantity)} × <Money v={lastPrice.price} ccy={asset.currency} /></> : undefined}>
          <Money v={value} ccy={ccy} />
        </StatTile>
        <StatTile label="Unrealized gain" sub={<>on cost of <Money v={cost} ccy={ccy} compact /></>}>
          <Delta v={value - cost} ccy={ccy} />
        </StatTile>
        <StatTile label="Multiple (MOIC)" sub="all time, incl. income and sales">
          {at.moic !== null ? `${at.moic.toFixed(2)}×` : "—"}
        </StatTile>
        <StatTile label="Money-weighted return" sub={at.mwr_annualized !== null ? "a year since first purchase (XIRR)" : "since first purchase"}>
          <Delta v={at.mwr_annualized ?? at.mwr} percent />
        </StatTile>
        <StatTile label="Income" sub="all time"><Money v={at.income} ccy={ccy} /></StatTile>
        <StatTile label="Realized" sub="all time, FIFO"><Delta v={at.realized} ccy={ccy} /></StatTile>
      </section>

      <section className="card">
        <div className="card-head">
          <div>
            <h2>{manual ? "Valuation history" : "Price"}</h2>
            <p>{data.prices.length ? `${pct(s.twr, { signed: true })} time-weighted over the period` : "No prices yet"}</p>
          </div>
          <PeriodPicker value={period} onChange={(p) => setSp(p === "ALL" ? {} : { period: p }, { replace: true })} periods={meta.periods} />
        </div>
        <LineChart
          ariaLabel={`${asset.name} ${manual ? "valuation" : "price"} over time with buys and sells`}
          series={[{ name: `${manual ? "Value per unit" : "Price"} (${asset.currency})`, color: "var(--series-1)", step: manual, points: pricePoints }]}
          markers={markers}
          markerLegend={[
            ...(markers.some((m) => m.color === markerColor.buy) ? [{ label: "Buy", color: markerColor.buy }] : []),
            ...(markers.some((m) => m.color === markerColor.sell) ? [{ label: "Sell", color: markerColor.sell }] : []),
          ]}
          formatY={(v) => money(v, asset.currency, { compact: true })}
          formatValue={(v) => money(v, asset.currency)}
        />
      </section>

      <div className="grid-halves">
        <section className="card">
          <div className="card-head"><h2>Positions</h2></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Account</th><th className="num">Quantity</th><th className="num">Value</th><th className="num">Cost</th></tr></thead>
              <tbody>
                {data.positions.map((p) => (
                  <tr key={p.key}>
                    <td>{p.account}{p.quantity === 0 && <span className="sub">closed</span>}</td>
                    <td className="num">{qty(p.quantity)}</td>
                    <td className="num"><Money v={p.value} ccy={ccy} /></td>
                    <td className="num"><Money v={p.cost_basis} ccy={ccy} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.lots.length > 0 && (
            <>
              <h3 style={{ margin: "16px 0 4px" }}>Open lots (FIFO)</h3>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Bought</th><th className="num">Quantity</th><th className="num">Unit cost</th><th className="num">Cost ({ccy})</th></tr></thead>
                  <tbody>
                    {data.lots.map((l, i) => (
                      <tr key={i}>
                        <td>{fmtDate(l.date)}<span className="sub">{l.account}</span></td>
                        <td className="num">{qty(l.quantity)}</td>
                        <td className="num"><Money v={l.unit_cost} ccy={asset.currency} /></td>
                        <td className="num"><Money v={l.cost_base} ccy={ccy} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>

        <section className="card">
          <div className="card-head">
            <div>
              <h2>Documents</h2>
              <p>Term sheets, SAFEs, statements — stored in your data folder</p>
            </div>
            <label className="btn small">
              Upload
              <input ref={fileRef} type="file" multiple hidden onChange={(e) => upload(e.target.files)} />
            </label>
          </div>
          {data.attachments.length === 0 ? (
            <p className="muted">No documents yet.</p>
          ) : (
            <ul className="list-plain">
              {data.attachments.map((a) => (
                <li key={a.id}>
                  <span>
                    <a href={`/api/attachments/${a.id}/download`}>{a.filename}</a>
                    <span className="muted"> · {(a.size / 1024).toFixed(0)} KB · {fmtDate(a.uploaded_at)}</span>
                  </span>
                  <button className="ghost small danger" onClick={() => remove(`/api/attachments/${a.id}`, "document")}>Delete</button>
                </li>
              ))}
            </ul>
          )}
          {data.valuations.length > 0 && (
            <>
              <h3 style={{ margin: "16px 0 4px" }}>Valuations</h3>
              <ul className="list-plain">
                {data.valuations.map((v) => (
                  <li key={v.id}>
                    <span>
                      <strong className="money">{money(Number(v.price), v.currency)}</strong> per unit · {fmtDate(v.date)}
                      <span className="sub">{[v.method.replace("_", " "), v.source, `${v.confidence} confidence`].filter(Boolean).join(" · ")}</span>
                    </span>
                    <button className="ghost small danger" onClick={() => remove(`/api/valuations/${v.id}`, "valuation")}>Delete</button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>

      <section className="card">
        <div className="card-head"><h2>Transactions</h2></div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Date</th><th>Type</th><th className="hide-sm">Account</th><th className="num">Quantity</th><th className="num">Price</th><th className="num">Amount</th><th className="num hide-sm">Fees</th></tr>
            </thead>
            <tbody>
              {data.transactions.map((t) => (
                <tr key={t.id}>
                  <td>{fmtDate(t.trade_date)}</td>
                  <td>{TX_LABELS[t.type] ?? t.type}{t.source === "import" && <span className="sub">imported</span>}</td>
                  <td className="hide-sm secondary">{t.account_name}</td>
                  <td className="num">{qty(t.quantity)}</td>
                  <td className="num">{t.price ? <Money v={Number(t.price)} ccy={t.currency} /> : "—"}</td>
                  <td className="num">{t.amount ? <Money v={Number(t.amount)} ccy={t.currency} /> : "—"}</td>
                  <td className="num hide-sm">{Number(t.fees) ? <Money v={Number(t.fees)} ccy={t.currency} /> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Modal open={dialog === "mark" || dialog === "price"} title={dialog === "mark" ? "Add valuation" : "Set price"} onClose={() => setDialog(null)}>
        <ValuationForm asset={asset} mode={dialog === "mark" ? "mark" : "price"} onDone={done} onCancel={() => setDialog(null)} />
      </Modal>
      <Modal open={dialog === "edit"} title="Edit asset" onClose={() => setDialog(null)}>
        <AssetForm asset={asset} onDone={done} onCancel={() => setDialog(null)} />
      </Modal>
      <Modal open={dialog === "tx"} title="Add transaction" onClose={() => setDialog(null)}>
        {lists.data && (
          <TransactionForm
            accounts={lists.data[0]}
            assets={lists.data[1]}
            defaults={{ asset_id: asset.id, account_id: open[0]?.account_id }}
            onDone={done}
            onCancel={() => setDialog(null)}
          />
        )}
      </Modal>
    </div>
  );
}
