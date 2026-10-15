from __future__ import annotations
from decimal import Decimal
from uuid import UUID,uuid4
from sqlalchemy import text
from edusync.modules.finance_checkout.domain.models import DueCharge,sequential_eligibility

class PostgresFinanceCheckoutRepository:
 def __init__(self,conn):self.conn=conn
 def search(self,school_id:UUID,q:str,limit:int=12):
  term=f"%{q.strip()}%"
  rows=self.conn.execute(text('''SELECT s.id student_id,s.family_id,s.matricule,s.last_name,s.middle_name,s.first_name,f.display_name family_name,f.phone,
   e.id enrollment_id,c.label class_label,y.label academic_year,y.status academic_year_status,
   EXISTS(SELECT 1 FROM enrollments oe JOIN academic_years oy ON oy.id=oe.academic_year_id JOIN finance_charges fc ON fc.enrollment_id=oe.id AND fc.school_id=oe.school_id AND fc.status='ACTIVE' AND fc.net_amount>fc.paid_amount WHERE oe.school_id=s.school_id AND oe.student_id=s.id AND oy.status IN ('CLOSED','ARCHIVED')) has_old_debt
   FROM students s JOIN families f ON f.id=s.family_id
   JOIN LATERAL (SELECT ee.* FROM enrollments ee JOIN academic_years yy ON yy.id=ee.academic_year_id WHERE ee.school_id=s.school_id AND ee.student_id=s.id ORDER BY (yy.status='ACTIVE') DESC,yy.start_date DESC LIMIT 1) e ON true
   JOIN academic_years y ON y.id=e.academic_year_id JOIN school_classes c ON c.id=e.class_id
   WHERE s.school_id=:sid AND (s.matricule ILIKE :q OR concat_ws(' ',s.last_name,s.middle_name,s.first_name) ILIKE :q OR f.display_name ILIKE :q OR coalesce(f.phone,'') ILIKE :q)
   ORDER BY (y.status='ACTIVE') DESC,s.last_name,s.middle_name,s.first_name LIMIT :lim'''),{'sid':str(school_id),'q':term,'lim':limit}).mappings().all()
  return [dict(r) for r in rows]
 def family_children(self,school_id:UUID,family_id:UUID):
  return self.search(school_id,'',50) if False else [dict(r) for r in self.conn.execute(text('''SELECT s.id student_id,s.family_id,s.matricule,s.last_name,s.middle_name,s.first_name,e.id enrollment_id,c.label class_label
   FROM students s JOIN enrollments e ON e.student_id=s.id AND e.school_id=s.school_id AND e.status='VALIDATED' JOIN academic_years y ON y.id=e.academic_year_id AND y.status='ACTIVE' JOIN school_classes c ON c.id=e.class_id
   WHERE s.school_id=:sid AND s.family_id=:fid AND s.status='ACTIVE' ORDER BY s.last_name,s.middle_name,s.first_name'''),{'sid':str(school_id),'fid':str(family_id)}).mappings().all()]
 def _cash_payable(self,school_id:UUID,rows)->list[DueCharge]:
  """Amount still payable at the cash desk, same definition as finance_charge_effective + recovery:
  net - active charge decisions (exemptions...) - outside-cash regularizations (historical import), minus paid."""
  ids=[str(r['id']) for r in rows]
  adj={}
  if ids:
   adj={str(a['id']):a for a in self.conn.execute(text("""SELECT c.id,
     coalesce((SELECT sum(d.amount) FROM finance_decisions d WHERE d.school_id=c.school_id AND d.charge_id=c.id AND d.status='ACTIVE' AND d.currency=c.currency),0) decisions,
     coalesce((SELECT sum(r.amount) FROM finance_charge_regularizations r WHERE r.school_id=c.school_id AND r.charge_id=c.id),0) outside_cash
     FROM finance_charges c WHERE c.school_id=:sid AND c.id=ANY(CAST(:ids AS uuid[]))"""),{'sid':str(school_id),'ids':ids}).mappings().all()}
  out=[]
  for r in rows:
   a=adj.get(str(r['id']),{}); payable_net=max(Decimal('0'),Decimal(str(r['net_amount']))-Decimal(str(a.get('decisions',0)))-Decimal(str(a.get('outside_cash',0))))
   out.append(DueCharge(UUID(str(r['id'])),r['label'],r['currency'],payable_net,Decimal(str(r['paid_amount'])),r['periodicity'],r['period_label'],r['period_order'],r.get('sequence_group'),r.get('sequence_order')))
  return out
 def charges(self,school_id:UUID,enrollment_id:UUID):
  rows=self.conn.execute(text('''SELECT id,label,currency,net_amount,paid_amount,periodicity,period_label,period_order,sequence_group,sequence_order FROM finance_charges WHERE school_id=:sid AND enrollment_id=:eid AND status='ACTIVE' ORDER BY currency,coalesce(period_order,0),due_date NULLS LAST,label'''),{'sid':str(school_id),'eid':str(enrollment_id)}).mappings().all()
  charges=self._cash_payable(school_id,rows); elig=sequential_eligibility(charges)
  # Settled charges (paid, exempted or regularized outside cash) still order the sequential chain but are not offered.
  return [{**dict(r),'remaining':str(c.remaining),'eligible':elig[c.id][0],'lock_reason':elig[c.id][1]} for r,c in zip(rows,charges) if c.remaining>0]
 def anticipation(self,school_id:UUID,enrollment_id:UUID,currency:str):
  # A plan is offered by the school; a parent does not need prior enrollment.
  # Membership is only the remembered decision for this child.
  row=self.conn.execute(text("""SELECT p.id plan_id,p.label,p.rules_json,coalesce(m.status,'AVAILABLE') membership_status
   FROM enrollments e JOIN finance_anticipation_plans p ON p.school_id=e.school_id AND p.academic_year_id=e.academic_year_id AND p.enabled=true AND p.currency=:cur
   LEFT JOIN finance_anticipation_memberships m ON m.school_id=p.school_id AND m.plan_id=p.id AND m.enrollment_id=e.id
   WHERE e.school_id=:sid AND e.id=:eid AND e.status='VALIDATED'
   ORDER BY CASE coalesce(m.status,'AVAILABLE') WHEN 'ACCEPTED' THEN 0 WHEN 'AVAILABLE' THEN 1 ELSE 2 END,p.updated_at DESC LIMIT 1"""),{'sid':str(school_id),'eid':str(enrollment_id),'cur':currency}).mappings().first()
  if not row:return None
  d=dict(row);d['accepted']=d['membership_status']=='ACCEPTED';d['available']=True;return d
 def accept_anticipation(self,school_id:UUID,enrollment_id:UUID,plan_id:UUID,user_id:UUID):
  self.conn.execute(text("""INSERT INTO finance_anticipation_memberships(id,school_id,plan_id,enrollment_id,status,decided_at,decided_by)
   VALUES(:id,:sid,:pid,:eid,'ACCEPTED',now(),:uid)
   ON CONFLICT(school_id,plan_id,enrollment_id) DO UPDATE SET status='ACCEPTED',decided_at=now(),decided_by=EXCLUDED.decided_by"""),
   {'id':str(uuid4()),'sid':str(school_id),'pid':str(plan_id),'eid':str(enrollment_id),'uid':str(user_id)})
 def _lock_idempotency_key(self,school_id:UUID,idempotency_key:str):
  # Serialises concurrent requests carrying the same key: the second one waits, then sees the committed payment.
  self.conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k,0))"),{'k':f'finance-payment:{school_id}:{idempotency_key}'})
 def _registration_bundle_first(self,school_id,enrollment_id,charges,charge_ids,amount):
  # Desktop finance_checkout (parity lot L4): while the registration bundle is due, no unrelated fee may leapfrog it; one
  # checkout may settle the whole bundle plus other fees in one shot.
  from edusync.adapters.postgres_fee_schedules import PostgresFeeScheduleRepository
  due=PostgresFeeScheduleRepository(self.conn).registration_bundle_due(school_id,enrollment_id)
  outstanding=[i for i in due['items'] if Decimal(i['balance'])>0]
  if not due['ready'] or not outstanding:return
  bundle_ids={i['charge_id'] for i in due['items']}
  selected=[c for c in charges if c.id in set(charge_ids)]
  if not any(str(c.id) not in bundle_ids for c in selected):return
  left=Decimal(str(amount));covered={}
  for c in sorted(selected,key=lambda x:(x.chain or '',x.order,str(x.id))):
   alloc=min(left,c.remaining);covered[str(c.id)]=alloc;left-=alloc
  if any(covered.get(i['charge_id'],Decimal('0'))<Decimal(i['balance']) for i in outstanding):
   raise ValueError("Les obligations exigées à l'inscription doivent être soldées avant les autres frais")
 def _apply_payment_policy(self,school_id,rows,charges,charge_ids,amount,mode,use_anticipation):
  # Desktop finance_checkout (parity lot L5): accepted modes, future months, partial payments and minimum deposit, advance.
  from edusync.adapters.postgres_settings import PostgresSettingsRepository
  from datetime import date
  policy=PostgresSettingsRepository(self.conn).get_payment_policy(school_id)
  if mode not in PostgresSettingsRepository.PAYMENT_MODES:raise ValueError('Mode de paiement invalide')
  if mode not in set(policy['accepted_modes']):raise ValueError("Ce mode de paiement n'est pas autorisé par la configuration de l'école")
  if use_anticipation and not policy['advance_payments_enabled']:raise ValueError("Les paiements anticipés sont désactivés par la politique de l'école")
  due={str(r['id']):r.get('due_date') for r in rows};selected=set(charge_ids)
  if not policy['future_charge_payments_enabled'] and not use_anticipation and any(due.get(str(i)) and due[str(i)]>date.today() for i in selected):
   raise ValueError("Le paiement d'un mois futur est désactivé par la politique de l'école")
  if use_anticipation:return
  left=Decimal(str(amount));minimum=Decimal(str(policy['partial_min_amount'] or 0))
  for c in sorted((x for x in charges if x.id in selected),key=lambda x:(x.chain or '',x.order,str(x.id))):
   if left<=0:break
   n=min(left,c.remaining);left-=n
   if 0<n<c.remaining:
    if not policy['partial_payments_enabled']:raise ValueError("Les paiements partiels ne sont pas autorisés par la politique de l'école")
    if minimum>0 and n<minimum:raise ValueError(f"L'acompte minimum autorisé est de {minimum:,.2f}".replace(',',' '))
 def collect(self,school_id:UUID,user_id:UUID,membership_id:UUID,enrollment_id:UUID,charge_ids:list[UUID],amount:Decimal,currency:str,idempotency_key:str,use_anticipation:bool=False,mode:str='CASH',reference:str|None=None):
  self._lock_idempotency_key(school_id,idempotency_key)
  existing=self.conn.execute(text('SELECT id,receipt_number,amount,currency,enrollment_id FROM finance_payments WHERE school_id=:sid AND idempotency_key=:k'),{'sid':str(school_id),'k':idempotency_key}).mappings().first()
  if existing:
   if str(existing['enrollment_id'])!=str(enrollment_id) or Decimal(str(existing['amount']))!=Decimal(str(amount)) or existing['currency']!=currency:
    raise ValueError('Idempotency-Key déjà utilisée pour un autre encaissement')
   out=dict(existing);out.pop('enrollment_id');return {**out,'replayed':True}
  if use_anticipation:
   # Parity lot L6: the former simplified plan (surplus stored as a provision) is retired from the cash desk; a payment plan
   # is collected through collect_with_plan (Desktop model), a free advance is a distinct « fonds anticipé » (not merged).
   raise ValueError("Le paiement anticipé s'encaisse désormais selon un plan de paiement anticipé (mois courant puis mois ciblés du plan)")
  session=self.conn.execute(text("SELECT id FROM finance_cash_sessions WHERE school_id=:sid AND membership_id=:mid AND status='OPEN' ORDER BY opened_at DESC LIMIT 1 FOR UPDATE"),{'sid':str(school_id),'mid':str(membership_id)}).scalar_one_or_none()
  if not session:raise ValueError('Aucune caisse ouverte pour cet utilisateur')
  rows=self.conn.execute(text("SELECT * FROM finance_charges WHERE school_id=:sid AND enrollment_id=:eid AND status='ACTIVE' FOR UPDATE"),{'sid':str(school_id),'eid':str(enrollment_id)}).mappings().all()
  charges=self._cash_payable(school_id,rows); payable={str(c.id):c for c in charges}
  from edusync.modules.finance_checkout.domain.models import validate_selection,split_payment
  expected=validate_selection(charges,charge_ids)
  selected_ids=set(charge_ids)
  # Only the selected charges must match: a student may owe CDF and USD fees, paid separately.
  if currency not in {'CDF','USD'} or any(c.currency!=currency for c in charges if c.id in selected_ids):raise ValueError('Devise incohérente')
  self._registration_bundle_first(school_id,enrollment_id,charges,charge_ids,amount)
  self._apply_payment_policy(school_id,rows,charges,charge_ids,amount,mode,use_anticipation)
  plan=self.anticipation(school_id,enrollment_id,currency) if use_anticipation else None
  plan_available=bool(plan and plan.get('available'))
  normal,advance=split_payment(amount,expected,plan_available)
  if advance>0 and plan and not plan.get('accepted'):
   self.accept_anticipation(school_id,enrollment_id,UUID(str(plan['plan_id'])),user_id)
   plan['accepted']=True;plan['membership_status']='ACCEPTED'
  pid=uuid4(); receipt=self.next_receipt_number(school_id)
  self.conn.execute(text('INSERT INTO finance_payments(id,school_id,enrollment_id,cash_session_id,actor_user_id,amount,currency,receipt_number,idempotency_key,payment_mode,payment_reference) VALUES(:id,:sid,:eid,:cs,:uid,:a,:cur,:r,:k,:mode,:ref)'),{'mode':mode,'ref':(reference or '').strip()[:80] or None,'id':str(pid),'sid':str(school_id),'eid':str(enrollment_id),'cs':str(session),'uid':str(user_id),'a':amount,'cur':currency,'r':receipt,'k':idempotency_key})
  left=normal; details=[]
  selected_set=set(charge_ids)
  for c in sorted((x for x in charges if x.id in selected_set),key=lambda x:(x.chain or '',x.order,str(x.id))):
   if left<=0:break
   alloc=min(left,c.remaining)
   if alloc>0:
    aid=uuid4();self.conn.execute(text('INSERT INTO finance_payment_allocations(id,school_id,payment_id,charge_id,amount) VALUES(:id,:sid,:p,:c,:a)'),{'id':str(aid),'sid':str(school_id),'p':str(pid),'c':str(c.id),'a':alloc});self.conn.execute(text('UPDATE finance_charges SET paid_amount=paid_amount+:a,updated_at=now() WHERE id=:id'),{'a':alloc,'id':str(c.id)});left-=alloc;details.append({'label':c.period_label or c.label,'amount':str(alloc)})
  advance_detail=None
  if advance>0:
   target=(plan.get('rules_json') or {}).get('target_summary') if isinstance(plan.get('rules_json'),dict) else None
   target=target or 'Échéances futures selon le plan anticipé'
   advance_id=uuid4()
   self.conn.execute(text('INSERT INTO finance_advance_allocations(id,school_id,payment_id,enrollment_id,plan_id,currency,amount,remaining_amount,target_summary) VALUES(:id,:sid,:p,:eid,:plan,:cur,:a,:a,:target)'),{'id':str(advance_id),'sid':str(school_id),'p':str(pid),'eid':str(enrollment_id),'plan':str(plan['plan_id']),'cur':currency,'a':advance,'target':target})
   # When the school plan names target periods, earmark the advance to the real future charge(s).
   rules=plan.get('rules_json') or {}; labels=rules.get('target_period_labels',[]) if isinstance(rules,dict) else []
   target_lines=[];remain=advance
   if labels:
    targets=[r for r in rows if r.get('period_label') in labels and r['currency']==currency and UUID(str(r['id'])) not in selected_set]
    targets.sort(key=lambda r:(r.get('period_order') or 999,r.get('sequence_order') or 999))
    for tr in targets:
     if remain<=0:break
     room=payable[str(tr['id'])].remaining;take=min(remain,room)
     if take>0:
      self.conn.execute(text('INSERT INTO finance_advance_targets(id,school_id,advance_allocation_id,charge_id,amount) VALUES(:id,:sid,:aid,:cid,:a)'),{'id':str(uuid4()),'sid':str(school_id),'aid':str(advance_id),'cid':str(tr['id']),'a':take});target_lines.append({'label':tr.get('period_label') or tr['label'],'amount':str(take)});remain-=take
    if remain>0:raise ValueError('Le montant anticipé dépasse les échéances futures prévues par le plan')
   advance_detail={'amount':str(advance),'target':target,'plan_label':plan['label'],'targets':target_lines}
  return {'id':str(pid),'receipt_number':receipt,'amount':str(amount),'currency':currency,'replayed':False,'allocations':details,'advance':advance_detail}

 def family_collect(self,school_id:UUID,user_id:UUID,membership_id:UUID,family_id:UUID,lines:list[dict],idempotency_key:str):
  """Family basket: several explicit lines committed atomically (all or none) under one Idempotency-Key.
  Each line is an ordinary payment (own receipt) allocated by the unchanged collect() rule. The cashier
  chooses child, charges and amount per line; EduSync never spreads one family amount across children."""
  import hashlib,json
  self._lock_idempotency_key(school_id,'family-basket:'+idempotency_key)
  canon=json.dumps({'family_id':str(family_id),'lines':[{'enrollment_id':str(l['enrollment_id']),'charge_ids':sorted(str(c) for c in l['charge_ids']),'amount':str(Decimal(str(l['amount'])).normalize()),'currency':l['currency']} for l in lines]},sort_keys=True)
  digest=hashlib.sha256(canon.encode()).hexdigest()
  prev=self.conn.execute(text('SELECT id,request_sha256 FROM finance_family_baskets WHERE school_id=:sid AND idempotency_key=:k'),{'sid':str(school_id),'k':idempotency_key}).mappings().first()
  if prev:
   if prev['request_sha256']!=digest:raise ValueError('Idempotency-Key déjà utilisée pour un autre panier')
   return {**self.family_basket(school_id,UUID(str(prev['id']))),'replayed':True}
  if not 1<=len(lines)<=20:raise ValueError('Un panier contient de 1 à 20 lignes')
  seen=set()
  for l in lines:
   pair=(str(l['enrollment_id']),l['currency'])
   if pair in seen:raise ValueError('Une seule ligne par élève et par devise : regroupez les frais')
   seen.add(pair)
  ids=sorted({str(l['enrollment_id']) for l in lines})
  owned={str(r[0]) for r in self.conn.execute(text('''SELECT e.id FROM enrollments e JOIN students s ON s.id=e.student_id AND s.school_id=e.school_id
   WHERE e.school_id=:sid AND s.family_id=:fid AND e.id=ANY(CAST(:ids AS uuid[]))'''),{'sid':str(school_id),'fid':str(family_id),'ids':ids}).all()}
  if owned!=set(ids):raise ValueError('Un élève du panier n’appartient pas à cette famille')
  session=self.conn.execute(text("SELECT id FROM finance_cash_sessions WHERE school_id=:sid AND membership_id=:mid AND status='OPEN' ORDER BY opened_at DESC LIMIT 1"),{'sid':str(school_id),'mid':str(membership_id)}).scalar_one_or_none()
  if not session:raise ValueError('Aucune caisse ouverte pour cet utilisateur')
  paid=[]
  for n,l in enumerate(lines,start=1):
   r=self.collect(school_id,user_id,membership_id,UUID(str(l['enrollment_id'])),[UUID(str(c)) for c in l['charge_ids']],Decimal(str(l['amount'])),l['currency'],f'{idempotency_key}#L{n}',False)
   if r.get('replayed'):raise ValueError('Ligne de panier déjà encaissée séparément : actualisez le panier')
   paid.append((n,r))
  totals:dict[str,Decimal]={}
  for _,r in paid:totals[r['currency']]=totals.get(r['currency'],Decimal('0'))+Decimal(r['amount'])
  basket=uuid4()
  self.conn.execute(text('''INSERT INTO finance_family_baskets(id,school_id,family_id,idempotency_key,request_sha256,cash_session_id,actor_user_id,line_count,totals_json)
   VALUES(:id,:sid,:fid,:k,:h,:cs,:uid,:n,CAST(:t AS jsonb))'''),{'id':str(basket),'sid':str(school_id),'fid':str(family_id),'k':idempotency_key,'h':digest,'cs':str(session),'uid':str(user_id),'n':len(paid),'t':json.dumps({k:str(v) for k,v in totals.items()})})
  for n,r in paid:
   self.conn.execute(text('INSERT INTO finance_family_basket_payments(basket_id,school_id,line_no,payment_id) VALUES(:b,:sid,:n,:p)'),{'b':str(basket),'sid':str(school_id),'n':n,'p':r['id']})
  return {**self.family_basket(school_id,basket),'replayed':False}

 def family_basket(self,school_id:UUID,basket_id:UUID):
  head=self.conn.execute(text('SELECT id,family_id,totals_json,created_at,line_count FROM finance_family_baskets WHERE school_id=:sid AND id=:id'),{'sid':str(school_id),'id':str(basket_id)}).mappings().one()
  rows=self.conn.execute(text('''SELECT bp.line_no,p.id payment_id,p.receipt_number,p.amount,p.currency,p.enrollment_id,s.last_name,s.middle_name,s.first_name,c.label class_label,
    (SELECT coalesce(json_agg(json_build_object('label',coalesce(fc.period_label,fc.label),'amount',a.amount::text) ORDER BY fc.period_order NULLS LAST,fc.label),'[]'::json)
       FROM finance_payment_allocations a JOIN finance_charges fc ON fc.id=a.charge_id WHERE a.payment_id=p.id AND a.school_id=p.school_id) allocations
   FROM finance_family_basket_payments bp JOIN finance_payments p ON p.id=bp.payment_id AND p.school_id=bp.school_id
   JOIN enrollments e ON e.id=p.enrollment_id JOIN students s ON s.id=e.student_id JOIN school_classes c ON c.id=e.class_id
   WHERE bp.school_id=:sid AND bp.basket_id=:id ORDER BY bp.line_no'''),{'sid':str(school_id),'id':str(basket_id)}).mappings().all()
  return {'basket_id':str(head['id']),'family_id':str(head['family_id']),'totals':head['totals_json'],'created_at':head['created_at'].isoformat(),
   'lines':[{**{k:(str(v) if k in ('payment_id','enrollment_id','amount') else v) for k,v in dict(r).items()}} for r in rows]}

 # --- receipts (printing is separate from the payment commit) -------------------------------------------
 def receipt_facts(self,school_id:UUID,payment_id:UUID)->dict|None:
  # users is readable by the tenant role only for the caller's own row (privacy): the cashier name is
  # resolved by the router through the platform role once access to this payment is authorised.
  p=self.conn.execute(text('''SELECT p.id,p.receipt_number,p.amount,p.currency,p.created_at,p.actor_user_id,u.full_name cashier,
    s.last_name,s.middle_name,s.first_name,s.matricule,c.label class_label,y.label academic_year
   FROM finance_payments p LEFT JOIN users u ON u.id=p.actor_user_id
   LEFT JOIN enrollments e ON e.id=p.enrollment_id LEFT JOIN students s ON s.id=e.student_id
   LEFT JOIN school_classes c ON c.id=e.class_id LEFT JOIN academic_years y ON y.id=e.academic_year_id
   WHERE p.school_id=:sid AND p.id=:pid'''),{'sid':str(school_id),'pid':str(payment_id)}).mappings().first()
  if not p:return None
  lines=[dict(r) for r in self.conn.execute(text('''SELECT coalesce(fc.period_label,fc.label) AS label,a.amount FROM finance_payment_allocations a
   JOIN finance_charges fc ON fc.id=a.charge_id WHERE a.school_id=:sid AND a.payment_id=:pid ORDER BY fc.period_order NULLS LAST,fc.label'''),{'sid':str(school_id),'pid':str(payment_id)}).mappings()]
  lines+=[dict(r) for r in self.conn.execute(text('''SELECT pr.label||' × '||trim(to_char(ps.quantity,'FM999999990.###')) AS label,ps.total AS amount FROM finance_product_sales ps
   JOIN school_products pr ON pr.id=ps.product_id WHERE ps.school_id=:sid AND ps.payment_id=:pid'''),{'sid':str(school_id),'pid':str(payment_id)}).mappings()]
  adv=self.conn.execute(text('SELECT amount,target_summary FROM finance_advance_allocations WHERE school_id=:sid AND payment_id=:pid'),{'sid':str(school_id),'pid':str(payment_id)}).mappings().first()
  out=dict(p);out['lines']=lines
  if adv:out['advance_amount']=adv['amount'];out['advance_target']=adv['target_summary']
  return out
 def record_receipt_print(self,school_id:UUID,payment_id:UUID,user_id:UUID)->int:
  self.conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k,0))"),{'k':f'receipt-print:{payment_id}'})
  n=int(self.conn.execute(text('SELECT coalesce(max(copy_no),0) FROM finance_receipt_prints WHERE school_id=:sid AND payment_id=:pid'),{'sid':str(school_id),'pid':str(payment_id)}).scalar_one())+1
  self.conn.execute(text("INSERT INTO finance_receipt_prints(school_id,payment_id,copy_no,kind,printed_by) VALUES(:sid,:pid,:n,:k,:u)"),{'sid':str(school_id),'pid':str(payment_id),'n':n,'k':'ORIGINAL' if n==1 else 'DUPLICATA','u':str(user_id)})
  return n
 def receipt_copies(self,school_id:UUID,payment_id:UUID)->int:
  return int(self.conn.execute(text('SELECT count(*) FROM finance_receipt_prints WHERE school_id=:sid AND payment_id=:pid'),{'sid':str(school_id),'pid':str(payment_id)}).scalar_one())
 def print_settings(self,school_id:UUID)->dict:
  r=self.conn.execute(text('SELECT receipt_policy,receipt_format,receipt_prefix,receipt_copies,version FROM school_print_settings WHERE school_id=:sid'),{'sid':str(school_id)}).mappings().first()
  return dict(r) if r else {'receipt_policy':'NONE','receipt_format':'A5','receipt_prefix':'REC','receipt_copies':1,'version':0}
 def next_receipt_number(self,school_id:UUID)->str:
  # Desktop next_receipt_no (parity lot L7): PREFIX-YEAR-000123, one atomic counter per calendar year, consumed inside the
  # payment transaction (a rollback gives the number back).
  from datetime import date
  year=date.today().year
  n=self.conn.execute(text('''INSERT INTO finance_receipt_sequences(school_id,year,last_number) VALUES(:sid,:y,1)
   ON CONFLICT(school_id,year) DO UPDATE SET last_number=finance_receipt_sequences.last_number+1 RETURNING last_number'''),{'sid':str(school_id),'y':year}).scalar_one()
  prefix=(self.print_settings(school_id).get('receipt_prefix') or 'REC').strip().upper()
  return f"{prefix}-{year}-{int(n):06d}"

 def historical_debts(self,school_id:UUID,student_id:UUID):
  rows=self.conn.execute(text("""SELECT e.id enrollment_id,y.id academic_year_id,y.label academic_year,c.label class_label,
   fc.id charge_id,fc.label,fc.currency,fc.net_amount,fc.paid_amount,(fc.net_amount-fc.paid_amount) remaining,
   fc.period_label,fc.periodicity
   FROM enrollments e JOIN academic_years y ON y.id=e.academic_year_id JOIN school_classes c ON c.id=e.class_id
   JOIN finance_charges fc ON fc.enrollment_id=e.id AND fc.school_id=e.school_id AND fc.status='ACTIVE' AND fc.net_amount>fc.paid_amount
   WHERE e.school_id=:sid AND e.student_id=:student AND y.status IN ('CLOSED','ARCHIVED')
   ORDER BY y.start_date DESC,fc.due_date NULLS LAST,fc.label"""),{'sid':str(school_id),'student':str(student_id)}).mappings().all()
  return [dict(r) for r in rows]
 def products(self,school_id:UUID,q:str=''):
  term=f"%{q.strip()}%"
  rows=self.conn.execute(text("""SELECT p.id,p.code,p.label,p.currency,p.unit_price,p.stock_tracking,p.enabled,
   CASE WHEN p.stock_tracking THEN coalesce(s.quantity,0) ELSE NULL END stock_quantity,
   CASE WHEN p.stock_tracking THEN coalesce(s.low_threshold,0) ELSE NULL END low_threshold
   FROM school_products p LEFT JOIN inventory_stock s ON s.school_id=p.school_id AND s.product_id=p.id
   WHERE p.school_id=:sid AND p.enabled=true AND (:raw='' OR p.code ILIKE :q OR p.label ILIKE :q)
   ORDER BY p.label LIMIT 40"""),{'sid':str(school_id),'q':term,'raw':q.strip()}).mappings().all()
  return [dict(r) for r in rows]
 def sell_product(self,school_id:UUID,user_id:UUID,membership_id:UUID,student_id:UUID|None,enrollment_id:UUID|None,product_id:UUID,quantity:Decimal,idempotency_key:str):
  if quantity<=0:raise ValueError('Quantité invalide')
  self._lock_idempotency_key(school_id,idempotency_key)
  existing=self.conn.execute(text("SELECT s.id,p.receipt_number,p.amount,p.currency FROM finance_product_sales s JOIN finance_payments p ON p.id=s.payment_id WHERE s.school_id=:sid AND p.idempotency_key=:k"),{'sid':str(school_id),'k':idempotency_key}).mappings().first()
  if existing:return {**dict(existing),'replayed':True}
  session=self.conn.execute(text("SELECT id FROM finance_cash_sessions WHERE school_id=:sid AND membership_id=:mid AND status='OPEN' ORDER BY opened_at DESC LIMIT 1 FOR UPDATE"),{'sid':str(school_id),'mid':str(membership_id)}).scalar_one_or_none()
  if not session:raise ValueError('Aucune caisse ouverte pour cet utilisateur')
  p=self.conn.execute(text("SELECT * FROM school_products WHERE school_id=:sid AND id=:pid AND enabled=true FOR UPDATE"),{'sid':str(school_id),'pid':str(product_id)}).mappings().first()
  if not p:raise ValueError('Article indisponible')
  if p['stock_tracking']:
   stock=self.conn.execute(text("SELECT quantity FROM inventory_stock WHERE school_id=:sid AND product_id=:pid FOR UPDATE"),{'sid':str(school_id),'pid':str(product_id)}).scalar_one_or_none()
   available=Decimal(str(stock or 0))
   if available<quantity:raise ValueError(f'Stock insuffisant : {available} disponible(s)')
  total=Decimal(str(p['unit_price']))*quantity; pay_id=uuid4(); sale_id=uuid4(); receipt=self.next_receipt_number(school_id)  # Desktop: one receipt sequence for every cash entry
  self.conn.execute(text("INSERT INTO finance_payments(id,school_id,enrollment_id,cash_session_id,actor_user_id,amount,currency,receipt_number,idempotency_key) VALUES(:id,:sid,:eid,:cs,:uid,:a,:cur,:r,:k)"),{'id':str(pay_id),'sid':str(school_id),'eid':str(enrollment_id) if enrollment_id else None,'cs':str(session),'uid':str(user_id),'a':total,'cur':p['currency'],'r':receipt,'k':idempotency_key})
  self.conn.execute(text("INSERT INTO finance_product_sales(id,school_id,student_id,enrollment_id,cash_session_id,payment_id,product_id,quantity,unit_price,currency,total,actor_user_id) VALUES(:id,:sid,:student,:eid,:cs,:pay,:product,:q,:price,:cur,:total,:uid)"),{'id':str(sale_id),'sid':str(school_id),'student':str(student_id) if student_id else None,'eid':str(enrollment_id) if enrollment_id else None,'cs':str(session),'pay':str(pay_id),'product':str(product_id),'q':quantity,'price':p['unit_price'],'cur':p['currency'],'total':total,'uid':str(user_id)})
  if p['stock_tracking']:
   self.conn.execute(text("UPDATE inventory_stock SET quantity=quantity-:q,updated_at=now(),version=version+1 WHERE school_id=:sid AND product_id=:pid"),{'q':quantity,'sid':str(school_id),'pid':str(product_id)})
   self.conn.execute(text("INSERT INTO inventory_stock_movements(id,school_id,product_id,movement_type,quantity_delta,reason,reference,actor_user_id) VALUES(:id,:sid,:pid,'SALE',:delta,'Vente au guichet',:ref,:uid)"),{'id':str(uuid4()),'sid':str(school_id),'pid':str(product_id),'delta':-quantity,'ref':receipt,'uid':str(user_id)})
  return {'id':str(sale_id),'payment_id':str(pay_id),'receipt_number':receipt,'amount':str(total),'currency':p['currency'],'quantity':str(quantity),'product_label':p['label'],'replayed':False}
