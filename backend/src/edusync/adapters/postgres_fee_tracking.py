from uuid import UUID
from psycopg.rows import dict_row

class PostgresFeeTrackingRepository:
    def __init__(self,conn): self.conn=conn.connection.driver_connection
    def year(self,school_id,year_id=None):
        with self.conn.cursor(row_factory=dict_row) as c:
            if year_id:c.execute("SELECT id,label FROM academic_years WHERE school_id=%s AND id=%s",(school_id,year_id))
            else:c.execute("SELECT id,label FROM academic_years WHERE school_id=%s ORDER BY (status='ACTIVE') DESC,start_date DESC LIMIT 1",(school_id,))
            r=c.fetchone();return dict(r) if r else None
    def taxonomy(self,school_id,year_id):
        with self.conn.cursor(row_factory=dict_row) as c:
            c.execute("""SELECT coalesce(cat.id::text,CASE WHEN ft.regulatory THEN 'REGULATORY' ELSE 'SCHOOL' END) category_id,
              coalesce(cat.label,CASE WHEN ft.regulatory THEN 'Frais de l’État' ELSE 'Frais scolaires' END) category_label,
              ft.id fee_type_id,ft.code,ft.label,ft.regulatory
              FROM fee_types ft LEFT JOIN fee_categories cat ON cat.id=ft.category_id
              WHERE ft.school_id=%s AND ft.enabled AND EXISTS(SELECT 1 FROM tariffs t WHERE t.school_id=ft.school_id AND t.fee_type_id=ft.id AND t.academic_year_id=%s AND t.enabled)
              ORDER BY coalesce(cat.sort_order,CASE WHEN ft.regulatory THEN 20 ELSE 10 END),category_label,ft.label""",(school_id,year_id));return [dict(r) for r in c.fetchall()]
    def _base(self,school_id,year_id,currency,fee_type_id=None,category_id=None,class_id=None,section_id=None,status=None):
        filters=["fc.school_id=%s","e.academic_year_id=%s","fc.currency=%s","fc.status='ACTIVE'"];p=[school_id,year_id,currency]
        if fee_type_id:filters.append("fc.fee_type_id=%s");p.append(fee_type_id)
        if category_id:
            if category_id=='REGULATORY':filters.append("ft.regulatory=true AND ft.category_id IS NULL")
            elif category_id=='SCHOOL':filters.append("ft.regulatory=false AND ft.category_id IS NULL")
            else:filters.append("ft.category_id=%s");p.append(category_id)
        if class_id:filters.append("e.class_id=%s");p.append(class_id)
        if section_id:filters.append("sc.section_id=%s");p.append(section_id)
        having=''
        if status=='IN_ORDER':having="HAVING sum(fc.paid_amount+coalesce(reg.outside_cash,0))>=sum(fc.effective_net_amount)"
        elif status=='PARTIAL':having="HAVING sum(fc.paid_amount+coalesce(reg.outside_cash,0))>0 AND sum(fc.paid_amount+coalesce(reg.outside_cash,0))<sum(fc.effective_net_amount)"
        elif status=='NOT_IN_ORDER':having="HAVING sum(fc.paid_amount+coalesce(reg.outside_cash,0))=0 AND sum(fc.effective_net_amount)>0"
        sql=f"""SELECT s.id student_id,s.matricule,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student_name,sc.label class_label,
          ft.id fee_type_id,ft.label fee_label,coalesce(cat.label,CASE WHEN ft.regulatory THEN 'Frais de l’État' ELSE 'Frais scolaires' END) category_label,
          sum(fc.effective_net_amount) net_expected,sum(fc.paid_amount+coalesce(reg.outside_cash,0)) regularized,
          greatest(sum(fc.effective_net_amount)-sum(fc.paid_amount+coalesce(reg.outside_cash,0)),0) remaining,
          sum(fc.decision_amount) decisions
          FROM finance_charge_effective fc JOIN enrollments e ON e.id=fc.enrollment_id JOIN students s ON s.id=e.student_id
          JOIN school_classes sc ON sc.id=e.class_id LEFT JOIN fee_types ft ON ft.id=fc.fee_type_id LEFT JOIN fee_categories cat ON cat.id=ft.category_id
          LEFT JOIN LATERAL(SELECT sum(r.amount) outside_cash FROM finance_charge_regularizations r WHERE r.school_id=fc.school_id AND r.charge_id=fc.id) reg ON true
          WHERE {' AND '.join(filters)} GROUP BY s.id,s.matricule,s.last_name,s.middle_name,s.first_name,sc.label,ft.id,ft.label,cat.label,ft.regulatory {having}
          ORDER BY sc.label,s.last_name,s.middle_name,s.first_name,ft.label"""
        return sql,p
    def students(self,*args,**kwargs):
        sql,p=self._base(*args,**kwargs)
        with self.conn.cursor(row_factory=dict_row) as c:c.execute(sql,p);return [dict(r) for r in c.fetchall()]
    def overview(self,school_id,year_id,currency):
        rows=self.students(school_id,year_id,currency)
        groups={}
        for r in rows:
            k=r['category_label'];g=groups.setdefault(k,{'category_label':k,'net_expected':0,'regularized':0,'remaining':0,'students':set()})
            for x in ('net_expected','regularized','remaining'):g[x]+=r[x]
            g['students'].add(str(r['student_id']))
        out=[]
        for g in groups.values():
            g['student_count']=len(g.pop('students'));g['rate']=round(g['regularized']*100/g['net_expected'],1) if g['net_expected'] else 0;out.append(g)
        return out
    def student_summary(self,school_id,student_id,currency='CDF'):
        y=self.year(school_id,None)
        if not y:return {'items':[]}
        rows=self.students(school_id,y['id'],currency)
        return {'academic_year':y,'currency':currency,'items':[r for r in rows if str(r['student_id'])==str(student_id)]}
    def family_summary(self,school_id,family_id,currency='CDF'):
        y=self.year(school_id,None)
        if not y:return {'items':[]}
        with self.conn.cursor(row_factory=dict_row) as c:c.execute("SELECT id FROM students WHERE school_id=%s AND family_id=%s",(school_id,family_id));ids={str(r['id']) for r in c.fetchall()}
        rows=self.students(school_id,y['id'],currency)
        return {'academic_year':y,'currency':currency,'items':[r for r in rows if str(r['student_id']) in ids]}
