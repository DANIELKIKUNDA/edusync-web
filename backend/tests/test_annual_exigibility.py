from datetime import date
from decimal import Decimal
import pytest
from edusync.modules.finance_fee_tracking.domain.annual_exigibility import (
    DayBand, EntryPolicy, PriorPeriodMode, ObligationStatus, resolve_monthly_obligation,
)

BANDS = (DayBand(1, 15, Decimal(100)), DayBand(16, 24, Decimal(50)), DayBand(25, None, Decimal(0)))
POLICY = EntryPolicy(PriorPeriodMode.NOT_APPLICABLE, BANDS)

@pytest.mark.parametrize("entry,year,month,amount,status", [
    (date(2026, 9, 5), 2026, 9, "50000.00", ObligationStatus.DUE),
    (date(2026, 9, 20), 2026, 9, "25000.00", ObligationStatus.DUE),
    (date(2026, 9, 28), 2026, 9, "0.00", ObligationStatus.NOT_EXIGIBLE),
    (date(2026, 10, 10), 2026, 9, "0.00", ObligationStatus.NOT_APPLICABLE),
    (date(2026, 10, 10), 2026, 10, "50000.00", ObligationStatus.DUE),
    (date(2026, 10, 28), 2026, 10, "0.00", ObligationStatus.NOT_EXIGIBLE),
    (date(2026, 10, 28), 2026, 11, "50000.00", ObligationStatus.DUE),
    (date(2026, 11, 27), 2026, 9, "0.00", ObligationStatus.NOT_APPLICABLE),
    (date(2026, 12, 16), 2027, 1, "50000.00", ObligationStatus.DUE),
    (date(2028, 2, 29), 2028, 2, "0.00", ObligationStatus.NOT_EXIGIBLE),
])
def test_scenarios(entry, year, month, amount, status):
    result = resolve_monthly_obligation(tariff=Decimal(50000), period_year=year, period_month=month,
                                        financial_entry_date=entry, policy=POLICY)
    assert result.exigible == Decimal(amount)
    assert result.status == status

@pytest.mark.parametrize("mode,percent,expected", [
    (PriorPeriodMode.FULL, None, Decimal(100)),
    (PriorPeriodMode.CUSTOM, Decimal(25), Decimal(25)),
])
def test_prior_period_modes(mode, percent, expected):
    policy = EntryPolicy(mode, BANDS, percent)
    result = resolve_monthly_obligation(tariff=Decimal(100), period_year=2026, period_month=9,
                                        financial_entry_date=date(2026, 10, 28), policy=policy)
    assert result.exigible == expected

@pytest.mark.parametrize("bands", [
    (DayBand(1, 15, Decimal(100)), DayBand(15, None, Decimal(0))),
    (DayBand(1, 15, Decimal(100)), DayBand(17, None, Decimal(0))),
    (DayBand(1, None, Decimal(101)),),
])
def test_invalid_bands(bands):
    with pytest.raises(ValueError):
        EntryPolicy(PriorPeriodMode.NOT_APPLICABLE, bands)

@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1"])
def test_invalid_tariff(bad):
    with pytest.raises(ValueError):
        resolve_monthly_obligation(tariff=Decimal(bad), period_year=2026, period_month=9,
                                   financial_entry_date=date(2026, 9, 1), policy=POLICY)
