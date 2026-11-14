from __future__ import annotations
from uuid import UUID
from psycopg.rows import dict_row

class PostgresFinanceRecoveryRepository:
    def __init__(self,conn): self.conn=conn.connection.driver_connection
    def year(self,school_id:UUID,year_id:UUID|None):
        with self.conn.cursor(row_factory=dict_row) as c:
            if year_id:c.execute("SELECT id,label,start_date,end_date,status FROM academic_years WHERE school_id=%s AND id=%s",(school_id,year_id))
            else:c.execute("SELECT id,label,start_date,end_date,status FROM academic_years WHERE school_id=%s ORDER BY (status='ACTIVE') DESC,start_date DESC LIMIT 1",(school_id,))
            r=c.fetchone();return dict(r) if r else None
    def school_identity(self,school_id):
        with self.conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT name,code FROM schools WHERE id=%s",(school_id,));r=c.fetchone();return dict(r) if r else {'name':'École'}
    def monthly(self,school_id,year_id,currency='CDF',*,scopes=()):
        # Dashboard/recovery reads must never widen an actor scope. A SCHOOL grant sees all;
        # SECTION/CYCLE and CLASS grants are intersected at SQL level.
        school_scope=any(t=='SCHOOL' for t,_ in scopes)
        sections=[str(v).upper() for t,v in scopes if t in ('SECTION','CYCLE') and v]
        classes=[str(v).upper() for t,v in scopes if t=='CLASS' and v]
        scope_sql='TRUE'; scope_args=[]
        if scopes and not school_scope:
            parts=[]
            if sections: parts.append('upper(ss.code)=ANY(%s)'); scope_args.append(sections)
            if classes: parts.append('upper(sc.code)=ANY(%s)'); scope_args.append(classes)
            scope_sql='('+' OR '.join(parts)+')' if parts else 'FALSE'
        sql=f"""WITH base AS (
          SELECT CASE WHEN fc.periodicity='MONTHLY' THEN COALESCE(fc.period_order,((EXTRACT(MONTH FROM fc.due_date)::int+3)%%12)+1,0) ELSE 100 END ord,
                 CASE WHEN fc.periodicity='MONTHLY' THEN COALESCE(fc.period_label,to_char(fc.due_date,'TMMonth'),'Autres') ELSE fc.label END month_label,
                 fc.enrollment_id,fc.effective_net_amount net_amount,fc.paid_amount,
                 fc.outside_cash_amount outside_cash,
                 -- N3-G (Desktop monthly_recovery_overview): non-cash settlements (payroll deductions) shown apart from cash
                 COALESCE((SELECT sum(ns.amount) FROM finance_noncash_settlements ns WHERE ns.charge_id=fc.id
                   AND NOT EXISTS (SELECT 1 FROM finance_noncash_cancellations nc WHERE nc.settlement_id=ns.id)),0) noncash
          FROM finance_charge_effective fc JOIN enrollments e ON e.id=fc.enrollment_id
          JOIN school_classes sc ON sc.id=e.class_id AND sc.school_id=e.school_id
          JOIN school_sections ss ON ss.id=sc.section_id AND ss.school_id=e.school_id
          WHERE fc.school_id=%s AND e.academic_year_id=%s AND fc.status='ACTIVE' AND fc.currency=%s
            AND fc.effective_net_amount>0 AND {scope_sql}
        ), agg AS (
          SELECT ord,month_label,count(DISTINCT enrollment_id) debtors,
                 count(DISTINCT enrollment_id) FILTER (WHERE paid_amount+outside_cash>=net_amount) in_order,
                 count(DISTINCT enrollment_id) FILTER (WHERE paid_amount+outside_cash<net_amount) not_in_order,
                 sum(net_amount) expected,sum(paid_amount-noncash) cash_collected,sum(noncash) noncash,sum(outside_cash) outside_cash
          FROM base GROUP BY ord,month_label
        ) SELECT ord,month_label,debtors,in_order,not_in_order,expected,cash_collected,noncash,outside_cash,
                 cash_collected+noncash+outside_cash regularized_total,
                 greatest(expected-cash_collected-noncash-outside_cash,0) remaining,
                 CASE WHEN expected>0 THEN round((cash_collected+noncash+outside_cash)*100/expected,1) ELSE 0 END recovery_rate,
                 CASE WHEN expected>0 THEN round(cash_collected*100/expected,1) ELSE 0 END cash_recovery_rate
          FROM agg ORDER BY ord,month_label"""
        with self.conn.cursor(row_factory=dict_row) as c:
            c.execute(sql,(school_id,year_id,currency,*scope_args));return [dict(r) for r in c.fetchall()]

    def classes(self,school_id,year_id):
        with self.conn.cursor(row_factory=dict_row) as c:
            c.execute("""SELECT DISTINCT sc.id,sc.label,sec.id section_id,sec.label section_label
              FROM school_classes sc JOIN school_sections sec ON sec.id=sc.section_id AND sec.school_id=sc.school_id
              JOIN enrollments e ON e.class_id=sc.id AND e.school_id=sc.school_id
             WHERE sc.school_id=%s AND e.academic_year_id=%s AND e.status<>'CANCELLED'
             ORDER BY sec.label,sc.label""",(school_id,year_id));return [dict(r) for r in c.fetchall()]

    def fees(self,school_id,year_id,section_id=None):
        """Fees that really generated obligations in the requested scope, with only their available periods."""
        extra=" AND sc.section_id=%s" if section_id else "";params=[school_id,year_id]+([section_id] if section_id else [])
        with self.conn.cursor(row_factory=dict_row) as c:
            c.execute(f"""SELECT ft.id,ft.label,fc.periodicity,fc.period_order,fc.period_label
              FROM finance_charge_effective fc JOIN enrollments e ON e.id=fc.enrollment_id AND e.school_id=fc.school_id
              JOIN school_classes sc ON sc.id=e.class_id AND sc.school_id=e.school_id
              JOIN fee_types ft ON ft.id=fc.fee_type_id AND ft.school_id=fc.school_id
             WHERE fc.school_id=%s AND e.academic_year_id=%s AND fc.status='ACTIVE' AND fc.effective_net_amount>0 {extra}
             GROUP BY ft.id,ft.label,fc.periodicity,fc.period_order,fc.period_label
             ORDER BY ft.label,fc.period_order NULLS LAST,fc.period_label""",tuple(params));rows=c.fetchall()
        out={}
        for row in rows:
            item=out.setdefault(str(row['id']),{'id':row['id'],'label':row['label'],'periodicity':row['periodicity'],'periods':[]})
            if row['period_order'] is not None and not any(p['order']==row['period_order'] for p in item['periods']):
                item['periods'].append({'order':row['period_order'],'label':row['period_label'] or f"Période {row['period_order']}"})
        return list(out.values())

    def class_register(self,school_id,year_id,class_id,currency='CDF'):
        with self.conn.cursor(row_factory=dict_row) as c:
            c.execute("""SELECT sc.label class_label FROM school_classes sc WHERE sc.school_id=%s AND sc.id=%s""",(school_id,class_id)); cr=c.fetchone()
            if not cr:return None
            # One charge = one financial obligation. We never manufacture an 'inscription' value from an enrollment payment aimed at June.
            c.execute("""SELECT e.id enrollment_id,e.enrolled_on,s.id student_id,s.matricule,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student_name,
              fc.id charge_id,fc.label,fc.effective_net_amount net_amount,fc.paid_amount,fc.due_date,fc.periodicity,fc.period_label,fc.period_order,fc.sequence_group,fc.sequence_order,
              coalesce(ft.code,CASE WHEN fc.periodicity='MONTHLY' THEN 'MINERVAL' ELSE 'OTHER' END) fee_code,
              coalesce(ft.label,fc.label) fee_label,coalesce(ft.regulatory,false) regulatory,
              coalesce((SELECT sum(at.amount) FROM finance_advance_targets at WHERE at.school_id=fc.school_id AND at.charge_id=fc.id),0) advance_amount
             FROM enrollments e JOIN students s ON s.id=e.student_id
             JOIN finance_charge_effective fc ON fc.enrollment_id=e.id AND fc.school_id=e.school_id AND fc.currency=%s
             LEFT JOIN fee_types ft ON ft.id=fc.fee_type_id
             WHERE e.school_id=%s AND e.academic_year_id=%s AND e.class_id=%s AND e.status<>'CANCELLED' AND fc.status='ACTIVE'
             ORDER BY s.last_name,s.middle_name,s.first_name,coalesce(fc.period_order,999),coalesce(fc.sequence_order,999),fc.label""",(currency,school_id,year_id,class_id)); charges=[dict(r) for r in c.fetchall()]
            c.execute("""SELECT e.student_id,ev.event_type,ev.effective_date FROM enrollments e JOIN student_status_events ev ON ev.student_id=e.student_id AND ev.school_id=e.school_id WHERE e.school_id=%s AND e.academic_year_id=%s AND e.class_id=%s AND ev.event_type IN('ABANDON','TRANSFER') AND ev.effective_date BETWEEN (SELECT start_date FROM academic_years WHERE id=%s) AND (SELECT end_date FROM academic_years WHERE id=%s) ORDER BY ev.effective_date""",(school_id,year_id,class_id,year_id,year_id)); events={str(r['student_id']):dict(r) for r in c.fetchall()}
        students={}; columns={}
        for r in charges:
            sid=str(r['student_id']);students.setdefault(sid,{'student_id':sid,'matricule':r['matricule'],'student_name':r['student_name'],'enrolled_on':r['enrolled_on'],'cells':{}})
            code=r['fee_code']; periodic=r['periodicity'] in ('MONTHLY','PERIODIC','INSTALLMENT')
            if code=='MINERVAL' or r['periodicity']=='MONTHLY': group='MONTHLY'; key=f"MONTH:{r['period_order'] or r['sequence_order'] or 0}:{r['period_label'] or r['label']}"; label=r['period_label'] or r['label']; parent='Frais mensuels'
            elif code in ('INSCRIPTION','REINSCRIPTION'): group='REGISTRATION';key='REGISTRATION';label='Inscription';parent=''
            else: group='FEE';key=f"FEE:{code}:{r['sequence_order'] or r['period_order'] or 0}:{r['period_label'] or r['label']}";label=r['period_label'] or (f"{r['sequence_order']}e tranche" if periodic and r['sequence_order'] else r['fee_label']);parent=r['fee_label']
            columns.setdefault(key,{'key':key,'group':group,'parent':parent,'label':label,'order':r['period_order'] or r['sequence_order'] or 999,'regulatory':r['regulatory']})
            students[sid]['cells'][key]={'net':r['net_amount'],'paid':r['paid_amount'],'advance':r['advance_amount'],'period_order':r['period_order'],'due_date':r['due_date'],'label':label}
        # Terminal status fills only obligations whose period is on/after the effective date; cancelled post-status charges should normally already be absent.
        import datetime
        for sid,st in students.items():
            ev=events.get(sid)
            if ev:
                st['terminal']={'type':ev['event_type'],'effective_date':ev['effective_date']}
                for cell in st['cells'].values():
                    if cell.get('due_date') and cell['due_date']>=ev['effective_date']:
                        cell['status_label']='Abandon' if ev['event_type']=='ABANDON' else 'Transféré'
        cols=sorted(columns.values(),key=lambda x:(0 if x['group']=='REGISTRATION' else 1 if x['group']=='MONTHLY' else 2,x['order'],x['parent'],x['label']))
        
        from edusync.modules.finance_recovery.domain.summaries import register_footer
        student_rows=list(students.values())
        return {'class_label':cr['class_label'],'columns':cols,'students':student_rows,'currency':currency,'footer':register_footer(student_rows,cols)}

    def class_monthly(self,school_id,year_id,class_id,currency='CDF'):
        sql="""WITH base AS (
          SELECT CASE WHEN fc.periodicity='MONTHLY' THEN COALESCE(fc.period_order,((EXTRACT(MONTH FROM fc.due_date)::int+3)%%12)+1,0) ELSE 100 END ord,CASE WHEN fc.periodicity='MONTHLY' THEN COALESCE(fc.period_label,to_char(fc.due_date,'TMMonth'),'Autres') ELSE fc.label END month_label,
          fc.enrollment_id,fc.effective_net_amount net_amount,fc.paid_amount,fc.outside_cash_amount outside_cash
          FROM finance_charge_effective fc JOIN enrollments e ON e.id=fc.enrollment_id WHERE fc.school_id=%s AND e.academic_year_id=%s AND e.class_id=%s AND fc.status='ACTIVE' AND fc.currency=%s AND fc.effective_net_amount>0
        ), agg AS (SELECT ord,month_label,count(DISTINCT enrollment_id) debtors,count(DISTINCT enrollment_id) FILTER (WHERE paid_amount+outside_cash>=net_amount) in_order,count(DISTINCT enrollment_id) FILTER (WHERE paid_amount+outside_cash<net_amount) not_in_order,sum(net_amount) expected,sum(paid_amount) cash_collected,sum(outside_cash) outside_cash FROM base GROUP BY ord,month_label)
        SELECT ord,month_label,debtors,in_order,not_in_order,expected,cash_collected,outside_cash,cash_collected+outside_cash regularized_total,greatest(expected-cash_collected-outside_cash,0) remaining,CASE WHEN expected>0 THEN round((cash_collected+outside_cash)*100/expected,1) ELSE 0 END recovery_rate FROM agg ORDER BY ord,month_label"""
        with self.conn.cursor(row_factory=dict_row) as c:c.execute(sql,(school_id,year_id,class_id,currency));return [dict(r) for r in c.fetchall()]

    def section_list(self,school_id,year_id):
        with self.conn.cursor(row_factory=dict_row) as c:
            c.execute("""SELECT DISTINCT sec.id,sec.label FROM school_sections sec JOIN school_classes sc ON sc.section_id=sec.id AND sc.school_id=sec.school_id JOIN enrollments e ON e.class_id=sc.id AND e.school_id=sc.school_id WHERE sec.school_id=%s AND e.academic_year_id=%s AND e.status<>'CANCELLED' ORDER BY sec.label""",(school_id,year_id));return [dict(r) for r in c.fetchall()]

    def scope_summary(self,school_id,year_id,currency='CDF',section_id=None,period_order=None,fee_type_id=None):
        extra=" AND sc.section_id=%s" if section_id else ""; params=[school_id,year_id,currency]+([section_id] if section_id else [])
        if fee_type_id is not None:
            extra += " AND fc.fee_type_id=%s";params.append(fee_type_id)
        if period_order is not None:
            # Backward compatibility: the old month-only API still derives a missing monthly order from the due date.
            # With the professional fee selector, periods belong to that fee and use their explicit order.
            extra += (" AND fc.period_order=%s" if fee_type_id is not None else
                      " AND fc.periodicity='MONTHLY' AND COALESCE(fc.period_order,((EXTRACT(MONTH FROM fc.due_date)::int+3)%%12)+1,0)=%s")
            params.append(period_order)
        sql=f"""WITH b AS (SELECT sc.id class_id,sc.label class_label,sec.id section_id,sec.label section_label,e.id enrollment_id,fc.effective_net_amount net_amount,fc.paid_amount,fc.outside_cash_amount outside_cash FROM school_classes sc JOIN school_sections sec ON sec.id=sc.section_id JOIN enrollments e ON e.class_id=sc.id AND e.school_id=sc.school_id JOIN finance_charge_effective fc ON fc.enrollment_id=e.id AND fc.school_id=e.school_id WHERE sc.school_id=%s AND e.academic_year_id=%s AND fc.currency=%s AND fc.status='ACTIVE' {extra}), per_student AS (SELECT class_id,class_label,section_id,section_label,enrollment_id,sum(net_amount) expected,sum(paid_amount) cash_collected,sum(outside_cash) outside_cash FROM b GROUP BY class_id,class_label,section_id,section_label,enrollment_id) SELECT class_id,class_label,section_id,section_label,count(*) debtors,count(*) FILTER(WHERE cash_collected+outside_cash>=expected) in_order,count(*) FILTER(WHERE cash_collected+outside_cash<expected) not_in_order,sum(expected) expected,sum(cash_collected) cash_collected,sum(outside_cash) outside_cash,sum(cash_collected+outside_cash) regularized_total,sum(greatest(expected-cash_collected-outside_cash,0)) remaining,CASE WHEN sum(expected)>0 THEN round(sum(cash_collected+outside_cash)*100/sum(expected),1) ELSE 0 END recovery_rate FROM per_student GROUP BY class_id,class_label,section_id,section_label ORDER BY class_label"""
        with self.conn.cursor(row_factory=dict_row) as c:c.execute(sql,tuple(params));return [dict(r) for r in c.fetchall()]

    # ------------------------------------------------------------ rapport de recouvrement de direction (14/11/2026)
    @staticmethod
    def _scope_filter(scopes):
        """Same rule as monthly(): SCHOOL sees all; SECTION/CYCLE and CLASS grants are intersected, never widened."""
        if not scopes or any(t=='SCHOOL' for t,_ in scopes): return 'TRUE',[]
        sections=[str(v).upper() for t,v in scopes if t in ('SECTION','CYCLE') and v]
        classes=[str(v).upper() for t,v in scopes if t=='CLASS' and v]
        parts,args=[],[]
        if sections: parts.append('upper(ss.code)=ANY(%s)'); args.append(sections)
        if classes: parts.append('upper(sc.code)=ANY(%s)'); args.append(classes)
        return ('('+' OR '.join(parts)+')' if parts else 'FALSE'),args

    def direction_report_rows(self,school_id,year_id,currency,*,as_of,fee_type_id=None,period_order=None,scopes=()):
        """Rows for the direction report: (charges in scope, pupils for whom the period is not due).
        Without an explicit period, only obligations already due at `as_of` are kept. A charge after an abandon or a
        transfer is not owed (same rule as the class register)."""
        scope_sql,scope_args=self._scope_filter(scopes)
        f_charge,f_args=[],[]
        if fee_type_id is not None: f_charge.append('fc.fee_type_id=%s'); f_args.append(fee_type_id)
        if period_order is not None: f_charge.append('fc.period_order=%s'); f_args.append(period_order)
        else: f_charge.append('(fc.due_date IS NULL OR fc.due_date<=%s)'); f_args.append(as_of)
        charge_filter=' AND '.join(f_charge)
        common="""s.matricule,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student_name,e.enrolled_on,
              sc.id class_id,sc.label class_label,ss.id section_id,ss.label section_label"""
        sql=f"""SELECT e.id enrollment_id,{common},
              coalesce(ft.label,fc.label) fee_label,coalesce(fc.period_label,fc.label) period_label,fc.period_order,fc.due_date,
              fc.effective_net_amount net,fc.net_amount gross_net,fc.decision_amount,fc.paid_amount paid,fc.outside_cash_amount outside,
              coalesce((SELECT sum(at.amount) FROM finance_advance_targets at WHERE at.school_id=fc.school_id AND at.charge_id=fc.id),0) advance,
              coalesce(g.full_name,fa.display_name) contact_name,coalesce(nullif(g.phone,''),nullif(fa.phone,'')) contact_phone
            FROM enrollments e JOIN students s ON s.id=e.student_id AND s.school_id=e.school_id
            JOIN school_classes sc ON sc.id=e.class_id AND sc.school_id=e.school_id
            JOIN school_sections ss ON ss.id=sc.section_id AND ss.school_id=e.school_id
            JOIN finance_charge_effective fc ON fc.enrollment_id=e.id AND fc.school_id=e.school_id
            LEFT JOIN fee_types ft ON ft.id=fc.fee_type_id AND ft.school_id=fc.school_id
            LEFT JOIN families fa ON fa.id=s.family_id AND fa.school_id=s.school_id
            LEFT JOIN LATERAL (SELECT gg.full_name,gg.phone FROM family_guardians fg JOIN guardians gg ON gg.id=fg.guardian_id AND gg.school_id=fg.school_id
                                WHERE fg.school_id=s.school_id AND fg.family_id=s.family_id AND fg.active
                                ORDER BY fg.is_primary DESC,(nullif(gg.phone,'') IS NOT NULL) DESC,fg.created_at LIMIT 1) g ON TRUE
           WHERE e.school_id=%s AND e.academic_year_id=%s AND e.status<>'CANCELLED' AND fc.status='ACTIVE' AND fc.currency=%s
             AND {charge_filter} AND {scope_sql}
             AND NOT EXISTS (SELECT 1 FROM student_status_events ev WHERE ev.school_id=e.school_id AND ev.student_id=e.student_id
                   AND ev.event_type IN ('ABANDON','TRANSFER') AND fc.due_date IS NOT NULL AND ev.effective_date<=fc.due_date
                   AND ev.effective_date BETWEEN (SELECT start_date FROM academic_years WHERE id=e.academic_year_id)
                                             AND (SELECT end_date FROM academic_years WHERE id=e.academic_year_id))"""
        f_sched,fs_args=[],[]
        if fee_type_id is not None: f_sched.append('fs.fee_type_id=%s'); fs_args.append(fee_type_id)
        if period_order is not None: f_sched.append('fs.period_order=%s'); fs_args.append(period_order)
        else: f_sched.append('(fs.due_date IS NULL OR fs.due_date<=%s)'); fs_args.append(as_of)
        # Monthly periods the annual policy did not make due (arrival after the cut-off day): no charge exists for them.
        arrivals=f"""SELECT DISTINCT e.id enrollment_id,{common},coalesce(fs.period_label,ft.label) period_label,fs.period_order,'ARRIVAL' reason
            FROM finance_exigibility_assessments a JOIN fee_schedules fs ON fs.id=a.schedule_id AND fs.school_id=a.school_id
            JOIN fee_types ft ON ft.id=fs.fee_type_id AND ft.school_id=fs.school_id
            JOIN enrollments e ON e.id=a.enrollment_id AND e.school_id=a.school_id
            JOIN students s ON s.id=e.student_id AND s.school_id=e.school_id
            JOIN school_classes sc ON sc.id=e.class_id AND sc.school_id=e.school_id
            JOIN school_sections ss ON ss.id=sc.section_id AND ss.school_id=e.school_id
           WHERE a.school_id=%s AND e.academic_year_id=%s AND e.status<>'CANCELLED' AND fs.currency=%s AND a.status IN ('NOT_APPLICABLE','NOT_EXIGIBLE')
             AND {' AND '.join(f_sched)} AND {scope_sql}
             AND NOT EXISTS (SELECT 1 FROM finance_charges c WHERE c.school_id=a.school_id AND c.enrollment_id=a.enrollment_id
                               AND c.schedule_id=a.schedule_id AND c.status='ACTIVE' AND c.net_amount>0)"""
        with self.conn.cursor(row_factory=dict_row) as c:
            c.execute(sql,(school_id,year_id,currency,*f_args,*scope_args)); charges=[dict(r) for r in c.fetchall()]
            c.execute(arrivals,(school_id,year_id,currency,*fs_args,*scope_args)); arrived=[dict(r) for r in c.fetchall()]
        exempt=[{**{k:r[k] for k in ('enrollment_id','matricule','student_name','enrolled_on','class_id','class_label','section_id','section_label','period_label')},'reason':'EXEMPTION'}
                for r in charges if r['net']<=0]
        return charges,arrived+exempt

    def fee_label(self,school_id,fee_type_id,period_order=None):
        with self.conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT label FROM fee_types WHERE school_id=%s AND id=%s",(school_id,fee_type_id)); f=c.fetchone()
            if not f: return None,None
            period=None
            if period_order is not None:
                c.execute("SELECT period_label FROM fee_schedules WHERE school_id=%s AND fee_type_id=%s AND period_order=%s AND period_label IS NOT NULL LIMIT 1",(school_id,fee_type_id,period_order))
                p=c.fetchone(); period=p['period_label'] if p else f"Période {period_order}"
            return f['label'],period
