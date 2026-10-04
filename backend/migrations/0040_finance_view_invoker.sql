-- Finance reporting must apply the caller's tenant RLS, not the view owner's rights.
ALTER VIEW finance_charge_effective SET (security_invoker = true);
