# Importing from Interactive Brokers (Flex Query)

Portfolio Observer reads IBKR's **Activity Flex Query** report in **XML** format. You set the query up once in
IBKR, then download a file whenever you want to update and import it on the **Import** page.
Re-importing overlapping periods is safe: rows that were already imported are recognised and skipped.

IBKR renames menus from time to time; if a label below doesn't match exactly, look for the closest one.

## 1. Create the query

1. Log in to **Client Portal** → **Performance & Reports** → **Flex Queries**.
2. Next to **Activity Flex Query**, click **+** (create).
3. Name it, e.g. `Portfolio Observer`.
4. Add these sections. For each one, **select all fields** — the importer only reads what it needs.

| Section | Options | Used for |
|---|---|---|
| Account Information | — | Your IBKR account id and base currency |
| Trades | Level of detail: **Execution** | Buys, sells, currency conversions, commissions |
| Cash Transactions | Level of detail: **Detail** | Deposits, withdrawals, dividends, withholding tax, interest, fees |
| Corporate Actions | — | Stock splits (other actions are flagged for manual entry) |
| Open Positions | Level of detail: **Summary** | End-of-period positions check and closing prices |
| Prior Period Positions | — | Daily closing prices of what you held |
| Conversion Rates | — | Daily currency rates |

5. Delivery configuration:
   - **Format: XML**
   - **Period:** *Last 365 Calendar Days* for regular updates
   - Date format `yyyyMMdd` (the default) is fine; other date formats are also understood
6. Save.

## 2. Load your full history

A single run covers at most one year. To bring in older history, run the query with a **custom date
range** once per year (e.g. 2021, 2022, 2023…) and import each file — oldest first is easiest to
check, but any order works.

The preview's **positions check** compares IBKR's reported positions with what Portfolio Observer will hold
after the import. A mismatch usually means earlier years haven't been imported yet.

## 3. Import

1. In Portfolio Observer, create an account for IBKR (**Accounts → Add account**, type *Broker*) and put your
   IBKR account number (e.g. `U1234567`) in **Broker account id** so files match automatically.
2. **Import** → Source *Interactive Brokers — Flex Query (XML)* → choose the file → **Preview import**.
3. Check the preview: new rows, duplicates, rows that can't be imported, warnings, positions check.
4. **Commit**. If something looks wrong afterwards, **Roll back** from the import history.

## What gets imported

- Stock, ETF, fund, bond and crypto trades with commissions (options and futures are imported with the
  contract multiplier folded into the price, classed as *Other*).
- Currency conversions (`EUR.USD` trades) as currency exchanges between cash balances.
- Dividends, payments in lieu, withholding tax, interest received and paid, fees, deposits and withdrawals.
- Stock splits. Spin-offs, mergers and other corporate actions are listed as warnings to enter by hand.
- Closing prices and IBKR's currency rates (only when your IBKR base currency matches Portfolio Observer's).

## Coming later (DASH-17)

Automatic daily download through IBKR's Flex Web Service: you create a read-only token in Client Portal
(**Flex Queries → Flex Web Service Configuration**) and put it, with the query id, in `.env`
(`PT_IBKR_FLEX_TOKEN`, `PT_IBKR_FLEX_QUERY_ID`). Not implemented yet.
