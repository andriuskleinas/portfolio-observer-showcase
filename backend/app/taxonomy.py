"""Default asset-class taxonomy, transaction types and account types.

Asset classes are configurable (OSS-03): edit this table to rename, add or remove classes.
"""

ASSET_CLASSES: dict[str, dict] = {
    "equity": {"label": "Public equities & ETFs", "liquidity": "liquid", "valuation": "market", "stale_days": 4},
    "fund": {"label": "Funds", "liquidity": "liquid", "valuation": "market", "stale_days": 7},
    "fixed_income": {"label": "Fixed income", "liquidity": "liquid", "valuation": "market", "stale_days": 7},
    "crypto": {"label": "Crypto", "liquidity": "liquid", "valuation": "market", "stale_days": 3},
    "startup": {"label": "Startups", "liquidity": "illiquid", "valuation": "manual", "stale_days": 180},
    "private_fund": {"label": "Private funds", "liquidity": "illiquid", "valuation": "manual", "stale_days": 120},
    "real_estate": {"label": "Real estate", "liquidity": "illiquid", "valuation": "manual", "stale_days": 365},
    "commodity": {"label": "Commodities", "liquidity": "liquid", "valuation": "market", "stale_days": 7},
    "other": {"label": "Other", "liquidity": "illiquid", "valuation": "manual", "stale_days": 365},
    "cash": {"label": "Cash", "liquidity": "liquid", "valuation": "market", "stale_days": None},
}

# fields: which inputs the type uses. asset: "required" | "optional" | "none"
TX_TYPES: dict[str, dict] = {
    "buy": {"label": "Buy", "asset": "required", "fields": ["quantity", "price", "fees"]},
    "sell": {"label": "Sell", "asset": "required", "fields": ["quantity", "price", "fees"]},
    "deposit": {"label": "Deposit", "asset": "none", "fields": ["amount"]},
    "withdrawal": {"label": "Withdrawal", "asset": "none", "fields": ["amount"]},
    "dividend": {"label": "Dividend", "asset": "optional", "fields": ["amount"], "income": True},
    "interest": {"label": "Interest", "asset": "optional", "fields": ["amount"], "income": True},
    "coupon": {"label": "Coupon", "asset": "required", "fields": ["amount"], "income": True},
    "rent": {"label": "Rent income", "asset": "required", "fields": ["amount"], "income": True},
    "distribution": {"label": "Distribution", "asset": "required", "fields": ["amount"], "income": True},
    "staking_reward": {"label": "Staking reward", "asset": "required", "fields": ["quantity", "price"], "income": True},
    "capital_call": {"label": "Capital call", "asset": "required", "fields": ["amount", "quantity"]},
    "return_of_capital": {"label": "Return of capital", "asset": "required", "fields": ["amount"]},
    "fee": {"label": "Fee", "asset": "optional", "fields": ["amount"]},
    "tax": {"label": "Tax withheld", "asset": "optional", "fields": ["amount"]},
    "expense": {"label": "Expense", "asset": "optional", "fields": ["amount"]},
    "transfer_in": {"label": "Transfer in", "asset": "required", "fields": ["quantity", "price"]},
    "transfer_out": {"label": "Transfer out", "asset": "required", "fields": ["quantity", "price"]},
    "fx": {"label": "Currency exchange", "asset": "none", "fields": ["amount", "counter_amount", "counter_currency"]},
    "split": {"label": "Split", "asset": "required", "fields": ["quantity"]},
    "airdrop": {"label": "Airdrop", "asset": "required", "fields": ["quantity"]},
    "write_off": {"label": "Write-off", "asset": "required", "fields": []},
}

INCOME_TYPES = {k for k, v in TX_TYPES.items() if v.get("income")}

ACCOUNT_TYPES: dict[str, dict] = {
    "broker": {"label": "Broker", "tracks_cash": True},
    "exchange": {"label": "Crypto exchange", "tracks_cash": True},
    "bank": {"label": "Bank", "tracks_cash": True},
    "wallet": {"label": "Self-custody wallet", "tracks_cash": False},
    "direct": {"label": "Direct holdings (e.g. startup deals)", "tracks_cash": False},
    "property": {"label": "Property", "tracks_cash": False},
    "fund": {"label": "Fund commitment", "tracks_cash": False},
    "other": {"label": "Other", "tracks_cash": False},
}

VALUATION_METHODS = ["last_round", "write_down", "appraisal", "fund_statement", "own_estimate", "broker_statement", "other"]
