import type { Num } from "./api";

/** Whole units from 1,000 up, cents below; compact (12.9K) for axes and tight spots. */
export function money(v: Num | undefined, ccy = "USD", opts: { compact?: boolean; signed?: boolean; decimals?: number } = {}): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const decimals = opts.decimals ?? (opts.compact ? 1 : Math.abs(v) >= 1000 ? 0 : 2);
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: ccy,
    currencyDisplay: "narrowSymbol",
    notation: opts.compact ? "compact" : "standard",
    maximumFractionDigits: decimals,
    minimumFractionDigits: opts.compact ? 0 : decimals,
    signDisplay: opts.signed ? "exceptZero" : "auto",
  }).format(v);
}

export function pct(v: Num | undefined, opts: { signed?: boolean; digits?: number } = {}): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "percent",
    maximumFractionDigits: opts.digits ?? 1,
    minimumFractionDigits: opts.digits ?? 1,
    signDisplay: opts.signed ? "exceptZero" : "auto",
  }).format(v);
}

export function qty(v: Num | string | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? Number(v) : v;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: Math.abs(n) < 1 ? 8 : 4 }).format(n);
}

export function compactNumber(v: number): string {
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

export function fmtDate(s: string | null | undefined, opts: Intl.DateTimeFormatOptions = { year: "numeric", month: "short", day: "numeric" }): string {
  if (!s) return "—";
  const d = new Date(s.length === 10 ? `${s}T00:00:00` : s);
  return d.toLocaleDateString(undefined, opts);
}

export function tone(v: Num | undefined): "up" | "down" | "" {
  if (v === null || v === undefined || v === 0) return "";
  return v > 0 ? "up" : "down";
}

export function arrow(v: Num | undefined): string {
  if (v === null || v === undefined || v === 0) return "";
  return v > 0 ? "▲ " : "▼ ";
}

export function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const PERIOD_LABELS: Record<string, string> = {
  "1D": "1D", "1W": "1W", MTD: "MTD", "1M": "1M", "3M": "3M", YTD: "YTD", "1Y": "1Y", "3Y": "3Y", "5Y": "5Y", ALL: "All",
};

export const TX_LABELS: Record<string, string> = {
  buy: "Buy", sell: "Sell", deposit: "Deposit", withdrawal: "Withdrawal", dividend: "Dividend", interest: "Interest",
  coupon: "Coupon", rent: "Rent", distribution: "Distribution", staking_reward: "Staking reward",
  capital_call: "Capital call", return_of_capital: "Return of capital", fee: "Fee", tax: "Tax withheld",
  expense: "Expense", transfer_in: "Transfer in", transfer_out: "Transfer out", fx: "Currency exchange",
  split: "Split", airdrop: "Airdrop", write_off: "Write-off",
};
