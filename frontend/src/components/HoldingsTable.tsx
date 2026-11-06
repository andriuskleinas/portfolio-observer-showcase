import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { HoldingRow } from "../api";
import { fmtDate, pct, qty } from "../format";
import { AssetAvatar, Delta, Money, SortHeader, useClassLabel } from "./ui";

type Key = "name" | "asset_class" | "value" | "weight" | "unrealized" | "unrealized_pct" | "period_return" | "period_gain";

export function HoldingsTable({ rows, ccy, showAccount = true }: { rows: HoldingRow[]; ccy: string; showAccount?: boolean }) {
  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({ key: "value", dir: -1 });
  const nav = useNavigate();
  const classLabel = useClassLabel();
  const sorted = useMemo(() => {
    const val = (r: HoldingRow) => {
      const v = r[sort.key];
      return typeof v === "string" ? v.toLowerCase() : v ?? -Infinity;
    };
    return [...rows].sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * sort.dir);
  }, [rows, sort]);

  if (!rows.length) return <div className="empty muted">No holdings match these filters</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <SortHeader k="name" label="Holding" sort={sort} setSort={setSort} />
            <SortHeader k="asset_class" label="Class" sort={sort} setSort={setSort} className="hide-sm" />
            <th className="num hide-sm">Quantity</th>
            <th className="num hide-sm">Price</th>
            <SortHeader k="value" label="Value" sort={sort} setSort={setSort} className="num" />
            <SortHeader k="weight" label="Weight" sort={sort} setSort={setSort} className="num hide-sm" />
            <SortHeader k="unrealized" label="Unrealized" sort={sort} setSort={setSort} className="num" />
            <SortHeader k="period_return" label="Period return" sort={sort} setSort={setSort} className="num hide-sm" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr
              key={r.key}
              className={r.asset_id ? "clickable" : ""}
              onClick={() => r.asset_id && nav(`/assets/${r.asset_id}`)}
            >
              <td>
                <div className="holding-cell">
                  <AssetAvatar name={r.name} symbol={r.symbol} assetClass={r.asset_class} />
                  <div className="holding-text">
                    <span className="holding-name">
                      {r.asset_id ? <a href={`/assets/${r.asset_id}`} onClick={(e) => e.preventDefault()}>{r.name}</a> : r.name}
                      {r.stale && (
                        <span className="chip warn" title={`Last price or valuation ${fmtDate(r.price_date)}`}>Stale</span>
                      )}
                    </span>
                    <span className="sub">
                      {[r.symbol && r.symbol !== r.name ? r.symbol : null, showAccount ? r.account : null].filter(Boolean).join(" · ")}
                    </span>
                  </div>
                </div>
              </td>
              <td className="hide-sm secondary nowrap">{classLabel(r.asset_class)}</td>
              <td className="num hide-sm">{qty(r.quantity)}</td>
              <td className="num hide-sm">
                {r.price !== null ? <Money v={r.price} ccy={r.currency} /> : "—"}
                {r.price_source === "mark" && <span className="sub">mark {fmtDate(r.price_date, { month: "short", year: "2-digit" })}</span>}
              </td>
              <td className="num"><Money v={r.value} ccy={ccy} /></td>
              <td className="num hide-sm">{pct(r.weight)}</td>
              <td className="num">
                {r.unrealized !== null ? <Delta v={r.unrealized} ccy={ccy} /> : <span className="muted">—</span>}
                {r.unrealized_pct !== null && <span className="sub">{pct(r.unrealized_pct, { signed: true })}</span>}
              </td>
              <td className="num hide-sm">{r.period_return !== null ? <Delta v={r.period_return} percent /> : <span className="muted">—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
