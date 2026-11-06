import { useState } from "react";
import { Link } from "react-router-dom";
import { api, query, type Dashboard as DashboardData } from "../api";
import { AllocationBars } from "../components/AllocationBars";
import { FilterBar, useDashFilters } from "../components/FilterBar";
import { HoldingsTable } from "../components/HoldingsTable";
import { LineChart } from "../components/LineChart";
import { Delta, Empty, ErrorBox, Money, StatTile, useAsync, useMeta } from "../components/ui";
import { fmtDate, money, pct, PERIOD_LABELS } from "../format";

export function Dashboard() {
  const meta = useMeta();
  const [f, update] = useDashFilters();
  const { data, error, loading } = useAsync(
    () =>
      api.get<DashboardData>(
        `/api/dashboard${query({
          period: f.period,
          asset_class: f.assetClass ? [f.assetClass] : [],
          account_id: f.accountId ? [f.accountId] : [],
          include_illiquid: f.includeIlliquid ? null : "false",
        })}`,
      ),
    [f.period, f.assetClass, f.accountId, f.includeIlliquid],
  );

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return <div className="loading">Loading…</div>;
  const ccy = data.base_currency;
  const s = data.summary;
  const empty = data.holdings.length === 0 && s.end_value === 0 && !f.assetClass && !f.accountId;

  if (empty) {
    return (
      <Empty title="No investments yet">
        <p>Add an account and its transactions, or import them.</p>
        <div className="row" style={{ justifyContent: "center", marginTop: 12 }}>
          <Link className="btn" to="/accounts">Add an account</Link>
          <Link className="btn" to="/import">Import from Interactive Brokers or CSV</Link>
        </div>
      </Empty>
    );
  }

  const periodName = f.period === "ALL" ? "since inception" : `over ${PERIOD_LABELS[f.period] ?? f.period}`;
  const annual = s.days >= 365;

  return (
    <div className={`stack ${loading ? "loading" : ""}`}>
      <FilterBar
        f={f}
        update={update}
        periods={meta.periods}
        classes={data.filter_options.asset_classes}
        accounts={data.filter_options.accounts}
      />

      <section className="hero card" aria-label="Total value">
        <div className="hero-main">
          <div className="eyebrow">Total portfolio value</div>
          <div className="hero-value money">{money(s.end_value, ccy)}</div>
          <div className="hero-delta">
            <Delta v={s.gain} ccy={ccy} pill />
            <span className="delta-pct"><Delta v={s.twr} percent /></span>
            <span className="secondary">{periodName}</span>
          </div>
        </div>
        <dl className="hero-meta">
          <div><dt>As of</dt><dd>{fmtDate(data.as_of)}</dd></div>
          <div><dt>Positions</dt><dd>{data.holdings.length}</dd></div>
          <div><dt>Base currency</dt><dd>{ccy}</dd></div>
        </dl>
      </section>

      <section className="tiles" aria-label="Key figures">
        <StatTile label="Time-weighted return" sub={annual ? `${pct(s.twr_annualized, { signed: true })} a year` : "for the period"}>
          <Delta v={s.twr} percent />
        </StatTile>
        <StatTile label="Money-weighted return" sub={annual ? `${pct(s.mwr_annualized, { signed: true })} a year (XIRR)` : "XIRR, for the period"}>
          <Delta v={s.mwr} percent />
        </StatTile>
        <StatTile label="Unrealized gain" sub={<>on cost of <Money v={s.cost_basis} ccy={ccy} compact /></>}>
          <Delta v={s.unrealized} ccy={ccy} />
        </StatTile>
        <StatTile label="Income" sub="dividends, interest, rent">
          <Money v={s.income} ccy={ccy} />
        </StatTile>
        <StatTile label="Net contributions" sub={`in ${money(s.inflows, ccy, { compact: true })} · out ${money(s.outflows, ccy, { compact: true })}`}>
          <Money v={s.net_flows} ccy={ccy} signed />
        </StatTile>
      </section>

      <div className="grid-2">
        <ValueCard data={data} />
        <section className="card">
          <div className="card-head">
            <div>
              <h2>Allocation</h2>
              <p>By asset class · select one to filter</p>
            </div>
          </div>
          <AllocationBars rows={data.allocation} ccy={ccy} onSelect={(k) => update({ assetClass: k })} />
        </section>
      </div>

      {(data.stale.length > 0 || data.warnings.length > 0) && (
        <section className="card" aria-label="Needs attention">
          <div className="card-head">
            <h2>Needs attention</h2>
          </div>
          <ul className="list-plain">
            {data.stale.map((r) => (
              <li key={r.key}>
                <span>
                  <span className="chip warn">Stale</span> <Link to={`/assets/${r.asset_id}`}>{r.name}</Link>
                  <span className="muted"> — last {r.price_source === "mark" ? "valuation" : "price"} {fmtDate(r.price_date)}</span>
                </span>
                <Link to={`/assets/${r.asset_id}`} className="btn small">Update value</Link>
              </li>
            ))}
            {data.warnings.map((w) => (
              <li key={w}>
                <span><span className="chip warn">Check</span> {w}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <div className="card-head">
          <div>
            <h2>Holdings</h2>
            <p>{data.holdings.length} positions · period return is time-weighted</p>
          </div>
        </div>
        <HoldingsTable rows={data.holdings} ccy={ccy} showAccount={!f.accountId} />
      </section>
    </div>
  );
}

function ValueCard({ data }: { data: DashboardData }) {
  const [table, setTable] = useState(false);
  const ccy = data.base_currency;
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Value over time</h2>
          <p>Net invested = cumulative money in minus money out</p>
        </div>
        <div className="segmented" role="group" aria-label="View">
          <button aria-pressed={!table} onClick={() => setTable(false)}>Chart</button>
          <button aria-pressed={table} onClick={() => setTable(true)}>Table</button>
        </div>
      </div>
      {table ? (
        <div className="table-wrap" style={{ maxHeight: 300, overflowY: "auto" }}>
          <table>
            <thead>
              <tr><th>Date</th><th className="num">Value</th><th className="num">Net invested</th></tr>
            </thead>
            <tbody>
              {[...data.series].reverse().map((p) => (
                <tr key={p.date}>
                  <td>{fmtDate(p.date)}</td>
                  <td className="num"><Money v={p.value} ccy={ccy} /></td>
                  <td className="num"><Money v={p.invested} ccy={ccy} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <LineChart
          ariaLabel="Portfolio value and net invested capital over time"
          zeroBaseline
          series={[
            { name: "Value", color: "var(--series-1)", area: true, points: data.series.map((p) => ({ date: p.date, y: p.value })) },
            { name: "Net invested", color: "var(--series-2)", dashed: true, points: data.series.map((p) => ({ date: p.date, y: p.invested })) },
          ]}
          formatY={(v) => money(v, ccy, { compact: true })}
          formatValue={(v) => money(v, ccy)}
        />
      )}
    </section>
  );
}
