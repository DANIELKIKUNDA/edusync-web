"""Build the minimal school structure through the public API (years, section, class, families)."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__file__))
from common import *

def setup(n):
    s=ensure_school(n,()); ensure_user(s,'ADMIN',('GESTIONNAIRE','SECRETARIAT','RESPONSABLE_FINANCE'))
    c=user_client(s,'ADMIN')
    if 'year_id' not in s:
        r=must(c,'POST','settings/academic-years',201,json={'code':'2026-2027','label':'Année 2026-2027','start_date':'2026-09-01','end_date':'2027-07-31'})
        s['year_id']=r.json()['id']; save()
    y=[x for x in must(c,'GET','settings/academic-years').json() if x['id']==s['year_id']][0]
    if y['status']!='ACTIVE':
        r=call(c,'POST',f"settings/academic-years/{s['year_id']}/activate",headers={'If-Match':str(y['version'])}); print('activate',r.status_code,r.text[:200])
    if 'section_id' not in s:
        r=call(c,'PUT','settings/sections/PRIMAIRE',json={'code':'PRIMAIRE','label':'Primaire'}); print('section',r.status_code,r.text[:300])
        secs=must(c,'GET','settings/sections').json(); print('sections',str(secs)[:300])
        s['section_id']=secs[0]['id']; save()
    if 'class_id' not in s:
        r=call(c,'POST','settings/classes',json={'academic_year_id':s['year_id'],'section_id':s['section_id'],'code':'1A','label':'1re année A'}); print('class',r.status_code,r.text[:300])
        s['class_id']=r.json()['id']; save()
    ensure_user(s,'CAISSIER1',('CAISSIER',))
    if n=='A': ensure_user(s,'CAISSIER2',('CAISSIER',))
    c.close(); c=user_client(s,'CAISSIER1')
    if "family" not in s or "family_id" not in s["family"]:
        body={'household_confidence':'NONE','primary_guardian':{'full_name':'PARENT '+n,'role':'PERE','phone':'+243810000000','is_primary':True},
              'children':[{'last_name':f'ELEVE{n}','middle_name':f'POST{i}','first_name':f'Un{i}','class_id':s['class_id'],'gender':'M' if i%2 else 'F'} for i in range(1,4)]}
        r=call(c,'POST','schooling/enrollments/family',json=body); print('enroll',r.status_code,r.text[:600])
        s['family']=r.json(); save()
    c.close(); return s
for n in ('A','B'): setup(n)
