VALID_DECISIONS={'EXEMPTION','REDUCTION','SPONSORSHIP','OTHER'}
VALID_RESPONSIBILITIES={'FAMILY','PAYROLL','SCHOOL','THIRD_PARTY'}

from decimal import Decimal

def credit_remaining(original,consumed)->Decimal:
    # Exact decimal arithmetic: money never goes through binary floating point.
    return max(Decimal('0'), Decimal(str(original))-Decimal(str(consumed)))
