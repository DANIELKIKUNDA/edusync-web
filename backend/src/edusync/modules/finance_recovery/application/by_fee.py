"""Money received, attributed to its fee type — shared by the executive home and the daily cash report."""
from __future__ import annotations


# « Comment l'argent perçu est réparti » (owner, 2026-11-22: « on encaisse 1 000 000 FC mais il y a 350 000 FC pour le
# frais de l'État ; quand il pointe sur le montant, qu'un petit bandeau montre comment les frais sont répartis »).
# EXACTLY the movements of PILOTAGE_SQL (so the parts always add up to the card), attributed to their fee type through
# the payment allocations: receipts (+), cancellations/refunds (−, in proportion to the reversed payment), advance funds
# and their restitutions, the part of a payment not allocated to a charge (product sales or advance), and the payments
# taken over from the previous system (by the fee of their charge).
PILOTAGE_BY_FEE_SQL = """
WITH b AS (SELECT CAST(%(today)s AS date) d, date_trunc('week', CAST(%(today)s AS date))::date w,
                  date_trunc('month', CAST(%(today)s AS date))::date m, CAST(%(start)s AS date) y),
p AS (SELECT p.id, p.currency, p.amount, s.business_date AS bday,
             EXISTS (SELECT 1 FROM finance_product_sales ps WHERE ps.payment_id=p.id) AS sale,
             COALESCE((SELECT sum(a.amount) FROM finance_payment_allocations a WHERE a.payment_id=p.id),0) AS allocated
        FROM finance_payments p JOIN finance_cash_sessions s ON s.id=p.cash_session_id
       WHERE s.school_id=%(sid)s AND s.business_date >= (SELECT least(y, w) FROM b)),
mv AS (
  SELECT p.bday, p.currency, COALESCE(ft.label, fc.label) AS fee, a.amount
    FROM p JOIN finance_payment_allocations a ON a.payment_id=p.id JOIN finance_charges fc ON fc.id=a.charge_id
    LEFT JOIN fee_types ft ON ft.id=fc.fee_type_id
  UNION ALL
  SELECT p.bday, p.currency, CASE WHEN p.sale THEN 'Ventes d’articles' ELSE 'Avance non encore affectée' END, p.amount-p.allocated
    FROM p WHERE p.amount<>p.allocated
  UNION ALL
  SELECT s.business_date, f.currency, 'Fonds anticipés', f.amount FROM finance_advance_funds f JOIN finance_cash_sessions s ON s.id=f.cash_session_id
   WHERE s.school_id=%(sid)s AND s.business_date >= (SELECT least(y, w) FROM b)
  UNION ALL
  SELECT r.business_date, r.currency, COALESCE(ft.label, fc.label), -a.amount*r.amount/NULLIF(op.amount,0)
    FROM finance_payment_reversals r JOIN finance_payments op ON op.id=r.payment_id
    JOIN finance_payment_allocations a ON a.payment_id=op.id JOIN finance_charges fc ON fc.id=a.charge_id LEFT JOIN fee_types ft ON ft.id=fc.fee_type_id
   WHERE r.school_id=%(sid)s AND r.business_date >= (SELECT least(y, w) FROM b)
  UNION ALL
  SELECT r.business_date, r.currency,
         CASE WHEN EXISTS (SELECT 1 FROM finance_product_sales ps WHERE ps.payment_id=op.id) THEN 'Ventes d’articles' ELSE 'Avance non encore affectée' END,
         -(op.amount-COALESCE((SELECT sum(a.amount) FROM finance_payment_allocations a WHERE a.payment_id=op.id),0))*r.amount/NULLIF(op.amount,0)
    FROM finance_payment_reversals r JOIN finance_payments op ON op.id=r.payment_id
   WHERE r.school_id=%(sid)s AND r.business_date >= (SELECT least(y, w) FROM b)
     AND op.amount<>COALESCE((SELECT sum(a.amount) FROM finance_payment_allocations a WHERE a.payment_id=op.id),0)
  UNION ALL
  SELECT c.business_date, f.currency, 'Fonds anticipés', -c.amount FROM finance_advance_fund_closures c JOIN finance_advance_funds f ON f.id=c.fund_id
   WHERE c.school_id=%(sid)s AND c.business_date >= (SELECT least(y, w) FROM b) AND c.closure_type IN ('ANNULATION','REMBOURSEMENT')
  UNION ALL
  SELECT l.historical_paid_on, l.currency, COALESCE(ft.label, fc.label), l.amount FROM financial_history_import_ledger l
    JOIN finance_charges fc ON fc.id=l.charge_id AND fc.school_id=l.school_id JOIN enrollments e ON e.id=fc.enrollment_id
    LEFT JOIN fee_types ft ON ft.id=fc.fee_type_id
   WHERE l.school_id=%(sid)s AND e.academic_year_id=%(yid)s AND l.historical_paid_on >= (SELECT least(y, w) FROM b))
SELECT mv.currency, mv.fee,
       COALESCE(sum(amount) FILTER (WHERE bday = b.d),0) AS today,
       COALESCE(sum(amount) FILTER (WHERE bday >= b.w AND bday <= b.d),0) AS week,
       COALESCE(sum(amount) FILTER (WHERE bday >= b.m AND bday <= b.d),0) AS month,
       COALESCE(sum(amount) FILTER (WHERE bday >= b.y AND bday <= b.d),0) AS year
  FROM mv, b GROUP BY mv.currency, mv.fee"""


def by_fee_breakdown(rows) -> dict:
    """{'CDF': {'today': [{'fee':…, 'amount':…}], 'week': …}, 'USD': …} — largest first, zero lines dropped."""
    from decimal import ROUND_HALF_UP, Decimal
    out: dict = {cur: {k: [] for k in ('today', 'week', 'month', 'year')} for cur in ('CDF', 'USD')}
    for r in rows:
        for k in ('today', 'week', 'month', 'year'):
            amount = Decimal(str(r[k] or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if amount != 0 and r['currency'] in out:
                out[r['currency']][k].append({'fee': r['fee'], 'amount': str(amount)})
    for cur in out.values():
        for k in cur:
            cur[k].sort(key=lambda x: -Decimal(x['amount']))
    return out
