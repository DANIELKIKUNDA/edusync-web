VALID_DECISIONS={'EXEMPTION','REDUCTION','SPONSORSHIP','OTHER'}
VALID_RESPONSIBILITIES={'FAMILY','PAYROLL','SCHOOL','THIRD_PARTY'}

def credit_remaining(original,consumed):
    return max(0, float(original)-float(consumed))
