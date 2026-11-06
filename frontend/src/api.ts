// Thin typed client for the backend API. Money values arrive as numbers for analytics
// and as decimal strings for editable records.

export type Num = number | null;

export interface Metrics {
  start: string;
  end: string;
  days: number;
  start_value: number;
  end_value: number;
  net_flows: number;
  inflows: number;
  outflows: number;
  gain: number;
  twr: Num;
  twr_annualized: Num;
  mwr: Num;
  mwr_annualized: Num;
  moic: Num;
  income: number;
  realized: number;
  fees: number;
  taxes: number;
}

export interface HoldingRow {
  key: string;
  kind: "holding" | "cash";
  asset_id: number | null;
  account_id: number;
  account: string;
  name: string;
  symbol: string | null;
  asset_class: string;
  currency: string;
  quantity: number;
  price: Num;
  price_date: string | null;
  price_source: string | null;
  stale: boolean;
  value: number;
  weight: Num;
  cost_basis: Num;
  unrealized: Num;
  unrealized_pct: Num;
  period_gain: number;
  period_return: Num;
  income: number;
  realized: number;
}

export interface SeriesPoint {
  date: string;
  value: number;
  invested: number;
}

export interface AllocationRow {
  asset_class: string;
  label: string;
  value: number;
  weight: Num;
}

export interface Dashboard {
  base_currency: string;
  as_of: string;
  period: string;
  summary: Metrics & { cost_basis: number; unrealized: number };
  series: SeriesPoint[];
  allocation: AllocationRow[];
  holdings: HoldingRow[];
  movers: HoldingRow[];
  stale: HoldingRow[];
  warnings: string[];
  filter_options: { accounts: { id: number; name: string }[]; asset_classes: { key: string; label: string }[] };
}

export interface Account {
  id: number;
  name: string;
  institution: string | null;
  type: string;
  currency: string;
  tracks_cash: boolean;
  ownership_pct: string;
  external_ref: string | null;
  notes: string | null;
  archived: boolean;
}

export interface Asset {
  id: number;
  name: string;
  asset_class: string;
  sub_class: string | null;
  symbol: string | null;
  isin: string | null;
  currency: string;
  country: string | null;
  sector: string | null;
  liquidity: string;
  valuation_method: string;
  tags: string[];
  notes: string | null;
  external_ids: Record<string, string>;
}

export interface Transaction {
  id: number;
  account_id: number;
  asset_id: number | null;
  type: string;
  trade_date: string;
  quantity: string | null;
  price: string | null;
  amount: string | null;
  currency: string;
  counter_amount: string | null;
  counter_currency: string | null;
  fees: string;
  fx_rate_to_base: string | null;
  notes: string | null;
  source: string;
  external_id: string | null;
  import_batch_id: number | null;
  asset_name: string | null;
  asset_symbol: string | null;
  account_name: string | null;
}

export interface Valuation {
  id: number;
  asset_id: number;
  date: string;
  price: string;
  currency: string;
  method: string;
  source: string | null;
  confidence: string;
  notes: string | null;
}

export interface Attachment {
  id: number;
  filename: string;
  content_type: string | null;
  size: number;
  uploaded_at: string;
  notes: string | null;
}

export interface Lot {
  account: string;
  date: string;
  quantity: number;
  cost_local: number;
  cost_base: number;
  unit_cost: Num;
}

export interface AssetDetail {
  base_currency: string;
  as_of: string;
  period: string;
  asset: Asset;
  class_label: string;
  summary: Metrics;
  all_time: Metrics;
  positions: HoldingRow[];
  series: SeriesPoint[];
  prices: { date: string; price: number; source: string }[];
  lots: Lot[];
  transactions: Transaction[];
  valuations: Valuation[];
  attachments: Attachment[];
  warnings: string[];
}

export interface Meta {
  base_currency: string;
  periods: string[];
  asset_classes: { key: string; label: string; liquidity: string; valuation: string }[];
  tx_types: { key: string; label: string; asset: "required" | "optional" | "none"; fields: string[]; income?: boolean }[];
  account_types: { key: string; label: string; tracks_cash: boolean }[];
  valuation_methods: string[];
}

export interface ImportRow {
  row: number;
  type: string | null;
  date: string | null;
  asset: { symbol: string | null; name: string | null; asset_class: string; currency: string } | null;
  asset_match?: { id: number; name: string } | null;
  quantity: string | null;
  price: string | null;
  amount: string | null;
  currency: string | null;
  counter_amount: string | null;
  counter_currency: string | null;
  fees: string;
  notes: string | null;
  errors: string[];
  status: "new" | "duplicate" | "error";
}

export interface ImportBatch {
  id: number;
  kind: string;
  filename: string | null;
  status: "preview" | "committed" | "rolled_back";
  account_id: number | null;
  account: string | null;
  created_at: string;
  committed_at: string | null;
  summary: {
    new: number;
    duplicate: number;
    error: number;
    new_assets: { symbol: string | null; name: string | null; asset_class: string; currency: string }[];
    prices: number;
    fx_rates: number;
    valuations: number;
    warnings: string[];
    reconciliation?: { symbol: string | null; name: string | null; reported: string; computed: string; date: string; match: boolean }[];
    committed?: { transactions: number; assets_created: number[]; prices: number; fx_rates: number; valuations: number };
  };
  rows: ImportRow[];
  row_count: number;
}

export interface CsvInspect {
  headers: string[];
  sample: Record<string, string>[];
  row_count: number;
  fields: string[];
  guess: CsvMapping;
}

export interface CsvMapping {
  columns: Record<string, string>;
  defaults: { type: string | null; currency: string; asset_class: string };
  type_map: Record<string, string>;
  date_format: string | null;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
      else if (Array.isArray(data.detail))
        msg = data.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join("; ");
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: (path: string) => request<void>("DELETE", path),
};

export function query(params: Record<string, string | number | boolean | (string | number)[] | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
