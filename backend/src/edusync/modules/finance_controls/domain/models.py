# N3-C: Desktop natures (financial_decisions.py::_kinds). REDUCTION / SPONSORSHIP / OTHER remain readable on former rows only.
VALID_DECISIONS={'DISCOUNT','EXEMPTION','INDIVIDUAL_FREE','COLLECTIVE_EXEMPTION','DIRECTION_EXCEPTION','THIRD_PARTY_COVERAGE'}
VALID_RESPONSIBILITIES={'FAMILY','PAYROLL','SCHOOL','THIRD_PARTY'}

from decimal import Decimal

def credit_remaining(original,consumed)->Decimal:
    # Exact decimal arithmetic: money never goes through binary floating point.
    return max(Decimal('0'), Decimal(str(original))-Decimal(str(consumed)))
