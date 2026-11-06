# Portfolio Observer

A private, self-hosted investment tracker: one dashboard for listed stocks, startups, real estate,
crypto, bonds and anything else you own, with correct performance numbers across all of it.
It runs on your own computer, and your data stays there.

> **Not financial advice.** This is a personal tracking tool. Numbers are only as good as the data you
> put in, and nothing here is a recommendation to buy or sell anything.

The full plan (dashboard, thesis workspace, AI news feed) is in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

## What works today

**Foundation and dashboard (first MVP slice):**

- Accounts, assets, transactions and valuations — add, edit and delete them by hand.
- 21 transaction types: buys and sells, dividends, interest, rent, fees, tax withheld, deposits and
  withdrawals, currency exchange, splits, capital calls, write-offs and more.
- **Interactive Brokers import** from a Flex Query XML file, with a positions check against the broker
  ([setup guide](docs/IBKR_FLEX_SETUP.md)).
- **CSV import** with a column-mapping step and saved mappings. A Notion database export works too:
  a list of holdings becomes buys, and a "current value" column becomes valuations.
- Every import is previewed first, skips rows already imported, and can be rolled back.
- **Performance**:
  - value, cost basis (FIFO), unrealized and realized gains, income and fees;
  - time-weighted return, money-weighted return (XIRR) and MOIC for any period;
  - available for the whole portfolio, an asset class, an account or a single holding.
- **Multi-currency**: everything is reported in one base currency (USD by default), using daily ECB
  rates from the free Frankfurter API plus any rates IBKR provides.
- **Illiquid assets**: startups and property are valued with manual marks (last round, write-down,
  appraisal…) and flagged as stale when a valuation gets old.
- Partial ownership (e.g. 50% of a co-owned flat) and accounts with or without a cash balance.
- Documents (SAFEs, term sheets, statements) attached to holdings.
- Dashboard with period picker, filters kept in the URL, value-over-time chart, allocation, a list of
  stale valuations needing an update, and a holdings table that drills down to each investment.
- Privacy mode (blurs amounts), light/dark theme, phone-sized layout.

**Not built yet** (see the requirements for the full list):

- **Login (SEC-01).** Keep the app on `127.0.0.1` and don't expose it to a network until this lands.
- **Automatic backups (DATA-04).** Until then, copy the `data/` folder yourself.
- Market price feeds for listed assets (data provider decision D8 is open). Today, prices come from
  IBKR imports, trade prices and manual entries.
- Installable phone app (PWA), daily IBKR sync, benchmarks, risk metrics.
- The thesis workspace and the AI news feed (modules 2 and 3).

## Quick start

Requirements: Python 3.12+ and Node 20+.

```bash
make setup     # install backend and frontend dependencies
make demo      # explore with fake data at http://127.0.0.1:8000
make start     # your real portfolio at http://127.0.0.1:8000
```

Your data lives in `data/portfolio.db` (the demo uses `data/demo/`). The `data/` folder is git-ignored
and never leaves your machine.
Settings are environment variables; copy `.env.example` to `.env` to change them, e.g.
`PT_BASE_CURRENCY`.

### Development

```bash
make api       # backend with auto-reload on :8000
make web       # frontend with hot reload on :5173 (proxies /api to :8000)
make test      # backend tests + frontend type check
```

## How the numbers work

- **Time-weighted return (TWR)** chains daily returns, so deposits and withdrawals don't distort it.
  Use it to compare with an index.
- **Money-weighted return (XIRR)** is the internal rate of return of your actual cash flows: how *your
  money* did. It matters most for startups and property, where money goes in and out irregularly.
- Returns over a year are also shown per year; shorter periods are never annualized.
- **Cost basis** uses FIFO lots. Money is calculated with decimals, not floating point.
- Accounts that track cash (brokers) treat only deposits and withdrawals as money in or out. Accounts
  that don't (direct deals, property) treat each purchase as new money in and each sale or income
  payment as money out.

All analytics live in `backend/app/engine/` as pure functions with reference tests (including Excel's
published XIRR example).

## Project layout

```
backend/   FastAPI + SQLAlchemy + Alembic (SQLite)
  app/engine/      calculation engine (ledger replay, returns, analytics)
  app/importers/   IBKR Flex XML and CSV importers, preview/commit/rollback
  app/api/         HTTP endpoints
  tests/           engine, importer and API tests
frontend/  React + TypeScript (Vite)
docs/      requirements and guides
scripts/   run helpers
```

## Licence

MIT — see [LICENSE](LICENSE).
