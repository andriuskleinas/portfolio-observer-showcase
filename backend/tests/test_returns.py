from datetime import date
from decimal import Decimal as D

from app.engine.analytics import _minus_months, period_start
from app.engine.returns import annualize, twr, xirr


def test_twr_no_flows():
    assert twr([D(110)], [D(0)], D(100)) == D("0.1")


def test_twr_ignores_timing_of_inflows():
    # +10% before and after a deposit that doubles the portfolio -> 21% either way
    r = twr([D(220), D(242)], [D(100), D(0)], D(100))
    assert r == D("0.21")


def test_twr_full_sale_at_a_loss_is_not_minus_100_percent():
    r = twr([D(0)], [D(-95)], D(100))
    assert r == D("-0.05")


def test_twr_none_without_capital():
    assert twr([D(0), D(0)], [D(0), D(0)], D(0)) is None


def test_xirr_simple_year():
    r = xirr([(date(2021, 1, 1), D(-1000)), (date(2022, 1, 1), D(1100))])
    assert abs(float(r) - 0.10) < 1e-6


def test_xirr_matches_excel_reference():
    flows = [
        (date(2008, 1, 1), D(-10000)),
        (date(2008, 3, 1), D(2750)),
        (date(2008, 10, 30), D(4250)),
        (date(2009, 2, 15), D(3250)),
        (date(2009, 4, 1), D(2750)),
    ]
    assert abs(float(xirr(flows)) - 0.373362535) < 1e-6


def test_xirr_needs_both_signs():
    assert xirr([(date(2021, 1, 1), D(-1000))]) is None


def test_annualize_only_after_a_year():
    assert annualize(D("0.1"), 200) is None
    assert abs(float(annualize(D("0.21"), 730)) - 0.1) < 1e-3


def test_period_starts():
    end = date(2026, 3, 31)
    assert period_start("1M", end, date(2020, 1, 1)) == date(2026, 3, 1)
    assert period_start("YTD", end, date(2020, 1, 1)) == date(2026, 1, 1)
    assert period_start("1Y", end, date(2026, 2, 1)) == date(2026, 2, 1)  # clamped to inception
    assert period_start("1D", end, date(2020, 1, 1)) == end
    assert _minus_months(date(2024, 3, 31), 1) == date(2024, 2, 29)
