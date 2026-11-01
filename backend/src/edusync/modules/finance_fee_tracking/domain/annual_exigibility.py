"""Pure, side-effect-free monthly exigibility calculation; policy persistence is separate."""
from __future__ import annotations
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

class PriorPeriodMode(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    FULL = "FULL"
    CUSTOM = "CUSTOM"

class ObligationStatus(str, Enum):
    DUE = "DUE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_EXIGIBLE = "NOT_EXIGIBLE"

@dataclass(frozen=True)
class DayBand:
    first_day: int
    last_day: int | None
    percent: Decimal

@dataclass(frozen=True)
class EntryPolicy:
    prior_period_mode: PriorPeriodMode
    entry_bands: tuple[DayBand, ...]
    prior_period_percent: Decimal | None = None

    def __post_init__(self):
        if self.prior_period_mode == PriorPeriodMode.CUSTOM:
            if self.prior_period_percent is None:
                raise ValueError("Custom prior-period policy requires percentage")
            _percent(self.prior_period_percent)
        elif self.prior_period_percent is not None:
            raise ValueError("Prior-period percentage requires CUSTOM mode")
        if not self.entry_bands:
            raise ValueError("Missing entry bands")
        for days in (28, 29, 30, 31):
            covered = set()
            for band in self.entry_bands:
                _percent(band.percent)
                if not 1 <= band.first_day <= 31 or (band.last_day is not None and not 1 <= band.last_day <= 31):
                    raise ValueError("Invalid band day")
                end = days if band.last_day is None else min(band.last_day, days)
                if band.first_day > end:
                    continue
                span = set(range(band.first_day, end + 1))
                if covered & span:
                    raise ValueError("Overlapping bands")
                covered |= span
            if covered != set(range(1, days + 1)):
                raise ValueError("Bands must cover every day of every month")

@dataclass(frozen=True)
class Obligation:
    status: ObligationStatus
    tariff: Decimal
    exigible: Decimal
    policy_percent: Decimal

def _percent(value):
    value = Decimal(str(value))
    if not value.is_finite() or not Decimal(0) <= value <= Decimal(100):
        raise ValueError("Invalid percentage")

def resolve_monthly_obligation(*, tariff: Decimal, period_year: int, period_month: int,
                               financial_entry_date: date, policy: EntryPolicy) -> Obligation:
    if not 1 <= period_month <= 12:
        raise ValueError("Invalid month")
    gross = Decimal(str(tariff))
    if not gross.is_finite() or gross < 0:
        raise ValueError("Invalid tariff")
    gross = gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    period = (period_year, period_month)
    entry = (financial_entry_date.year, financial_entry_date.month)
    if period < entry:
        if policy.prior_period_mode == PriorPeriodMode.NOT_APPLICABLE:
            return Obligation(ObligationStatus.NOT_APPLICABLE, gross, Decimal("0.00"), Decimal(0))
        pct = Decimal(100) if policy.prior_period_mode == PriorPeriodMode.FULL else policy.prior_period_percent
    elif period == entry:
        day = financial_entry_date.day
        pct = next(b.percent for b in policy.entry_bands if b.first_day <= day <=
                   (b.last_day if b.last_day is not None else monthrange(period_year, period_month)[1]))
    else:
        pct = Decimal(100)
    _percent(pct)
    due = (gross * Decimal(str(pct)) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Obligation(ObligationStatus.DUE if due else ObligationStatus.NOT_EXIGIBLE, gross, due, Decimal(str(pct)))
