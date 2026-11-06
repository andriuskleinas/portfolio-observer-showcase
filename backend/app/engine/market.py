from bisect import bisect_right
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Iterable

from app.engine.types import ONE, Observation

# On the same date a manual mark beats a market price, which beats a trade price.
_PRIORITY = {"trade": 0, "market": 1, "mark": 2}


class PriceBook:
    """Latest-known price per asset: the most recent observation on or before a date."""

    def __init__(self, observations: Iterable[tuple[int, Observation]] = ()):
        raw: dict[int, list[Observation]] = defaultdict(list)
        for asset_id, obs in observations:
            raw[asset_id].append(obs)
        self._series: dict[int, list[Observation]] = {}
        self._dates: dict[int, list[date]] = {}
        for asset_id, series in raw.items():
            series.sort(key=lambda o: (o.date, _PRIORITY.get(o.source, 1)))
            deduped: dict[date, Observation] = {}
            for o in series:
                deduped[o.date] = o  # later (higher priority) wins
            ordered = list(deduped.values())
            self._series[asset_id] = ordered
            self._dates[asset_id] = [o.date for o in ordered]

    def latest(self, asset_id: int, on: date) -> Observation | None:
        dates = self._dates.get(asset_id)
        if not dates:
            return None
        i = bisect_right(dates, on) - 1
        return self._series[asset_id][i] if i >= 0 else None

    def series(self, asset_id: int) -> list[Observation]:
        return self._series.get(asset_id, [])


class FxBook:
    """Rates to the base currency: 1 unit of `currency` = rate units of base."""

    def __init__(self, base: str, rates: Iterable[tuple[str, date, Decimal]] = ()):
        self.base = base
        raw: dict[str, dict[date, Decimal]] = defaultdict(dict)
        for currency, d, rate in rates:
            raw[currency][d] = rate
        self._dates = {c: sorted(r) for c, r in raw.items()}
        self._rates = {c: [raw[c][d] for d in self._dates[c]] for c in raw}

    def rate(self, currency: str, on: date) -> Decimal | None:
        if currency == self.base:
            return ONE
        dates = self._dates.get(currency)
        if not dates:
            return None
        i = bisect_right(dates, on) - 1
        # Before the first known rate, the earliest rate is the best estimate available.
        return self._rates[currency][max(i, 0)]

    def has(self, currency: str) -> bool:
        return currency == self.base or currency in self._dates
