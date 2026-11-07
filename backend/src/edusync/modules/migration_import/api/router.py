from __future__ import annotations
from edusync.shared.infrastructure.xlsx_safety import neutralize_formulas
import csv, io, json, re
from datetime import date, datetime
from uuid import UUID, uuid4
from decimal import Decimal
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from openpyxl import load_workbook, Workbook
from pydantic import BaseModel
from sqlalchemy import text
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.adapters.postgres_repositories import PostgresAuditRepository, PostgresOutboxRepository
from edusync.modules.sync.domain.outbox import OutboxMessage
from edusync.modules.schooling.domain.models import Family,Guardian,Student,Enrollment,generate_family_label,ContactStatus
from edusync.adapters.postgres_schooling import PostgresSchoolingRepository
from edusync.modules.personnel.domain.models import StaffMember, StaffCategory, StaffStatus
from edusync.adapters.postgres_personnel import PostgresPersonnelRepository
from edusync.modules.migration_import.import_contract import build_template, read_official_xlsx, CONTRACTS, contract_version

MAX_IMPORT_BYTES=10*1024*1024
MAX_IMPORT_ROWS=5000

def guard_import_payload(data:bytes):
 if not data: raise HTTPException(400,'Fichier vide')
 if len(data)>MAX_IMPORT_BYTES: raise HTTPException(413,'Fichier trop volumineux : maximum 10 Mio')

async def read_import_body(request:Request)->bytes:
 data=bytearray()
 async for chunk in request.stream():
  data.extend(chunk)
  if len(data)>MAX_IMPORT_BYTES: raise HTTPException(413,'Fichier trop volumineux : maximum 10 Mio')
 result=bytes(data);guard_import_payload(result);return result

router=APIRouter(tags=['Migration & import'])
STALE_ANALYSIS="Les données ont changé depuis l'analyse de ce lot : analysez de nouveau le fichier"

def _same_file_duplicates(parsed,key):
 """Row numbers whose identity key already appeared earlier in the same file."""
 seen=set();out=set()
 for rn,row in parsed:
  k=key(row)
  if k and k in seen:out.add(rn)
  elif k:seen.add(k)
 return out
HEADERS=['Nom*','Postnom*','Prénom*','Sexe*','Classe*','Date naissance','Lieu naissance','Nationalité','Adresse','Nom responsable','Téléphone responsable','E-mail responsable','École de provenance','Observation','Date inscription']

def need(a,c):
 try:a.require(c)
 except PermissionError as e:raise HTTPException(403,str(e))
def clean(v): return ' '.join(str(v or '').strip().split())
def norm(v): return clean(v).casefold()
def parse_date(v):
 if not v:return None
 if isinstance(v,(date,datetime)):return v.date() if isinstance(v,datetime) else v
 s=clean(v)
 for f in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y'):
  try:return datetime.strptime(s,f).date()
  except ValueError:pass
 raise ValueError('Date invalide (AAAA-MM-JJ recommandé)')
def rows_from_xlsx(data:bytes):
 try:return read_official_xlsx(data,'STUDENTS')
 except ValueError as e:raise HTTPException(400,str(e)) from e

def rows_from_csv(data:bytes):
 try:s=data.decode('utf-8-sig')
 except UnicodeDecodeError as e:raise HTTPException(400,'CSV attendu en UTF-8') from e
 sample=s[:4096]; delim=';' if sample.count(';')>=sample.count(',') else ','; rd=csv.DictReader(io.StringIO(s),delimiter=delim)
 if not rd.fieldnames or [clean(x) for x in rd.fieldnames][:5]!=HEADERS[:5]:raise HTTPException(400,'En-têtes CSV EduSync invalides')
 return [(i,{h:r.get(h) for h in HEADERS}) for i,r in enumerate(rd,2)]

def analyze_row(conn,sid,year,row,period=None):
 issues=[]; n={}
 for src,dst in [('Nom*','last_name'),('Postnom*','middle_name'),('Prénom*','first_name'),('Sexe*','gender'),('Classe*','class_label'),('Lieu naissance','birth_place'),('Nationalité','nationality'),('Adresse','address'),('Nom responsable','guardian_name'),('Téléphone responsable','guardian_phone'),('E-mail responsable','guardian_email'),('École de provenance','previous_school'),('Observation','notes')]:n[dst]=clean(row.get(src)) or None
 for k,label in [('last_name','Nom'),('middle_name','Postnom'),('first_name','Prénom'),('gender','Sexe'),('class_label','Classe')]:
  if not n[k]:issues.append({'level':'ERROR','code':'REQUIRED','field':k,'message':f'{label} obligatoire'})
 if n['gender'] and n['gender'].upper() not in ('M','F'):issues.append({'level':'ERROR','code':'GENDER','field':'gender','message':'Sexe attendu : F ou M'})
 else:n['gender']=(n['gender'] or '').upper() or None
 try:n['birth_date']=parse_date(row.get('Date naissance')).isoformat() if row.get('Date naissance') else None
 except ValueError as e:n['birth_date']=None;issues.append({'level':'ERROR','code':'DATE','field':'birth_date','message':str(e)})
 # Contract 1.1: the real enrollment date (owner, 2026-11-01), never the import day when it is known. Checked against the
 # year's enrollment period (pupils enrol before the school year starts), or the year's dates when no period is set.
 try:enrolled=parse_date(row.get('Date inscription')) if row.get('Date inscription') else None
 except ValueError:enrolled=None;issues.append({'level':'ERROR','code':'ENROLLMENT_DATE','field':'enrolled_on','message':"Date d'inscription invalide (JJ/MM/AAAA)"})
 n['enrolled_on']=enrolled.isoformat() if enrolled else None
 if enrolled and enrolled>date.today():issues.append({'level':'ERROR','code':'ENROLLMENT_DATE','field':'enrolled_on','message':"Date d'inscription dans le futur"})
 elif enrolled and period and not (period[0]<=enrolled<=period[1]):issues.append({'level':'WARNING','code':'ENROLLMENT_DATE_OUTSIDE_YEAR','field':'enrolled_on','message':f"Date d'inscription hors de la période d'inscription de l'année ({period[0]:%d/%m/%Y} → {period[1]:%d/%m/%Y})"})
 cl=None
 if n['class_label']:
  cl=conn.execute(text("SELECT id,code,label FROM school_classes WHERE school_id=:sid AND academic_year_id=:y AND enabled AND (lower(code)=:q OR lower(label)=:q OR lower(coalesce(reference_code,''))=:q) ORDER BY CASE WHEN lower(code)=:q THEN 0 ELSE 1 END LIMIT 2"),{'sid':sid,'y':year,'q':norm(n['class_label'])}).all()
  if len(cl)==0:issues.append({'level':'ERROR','code':'CLASS_UNKNOWN','field':'class_label','message':f"Classe non reconnue : {n['class_label']}"})
  elif len(cl)>1:issues.append({'level':'ERROR','code':'CLASS_AMBIGUOUS','field':'class_label','message':'Classe ambiguë'})
  else:n['class_id']=str(cl[0][0]);n['class_code']=cl[0][1];n['class_label_resolved']=cl[0][2]
 if n.get('last_name') and n.get('middle_name') and n.get('first_name'):
  dup=conn.execute(text("SELECT matricule FROM students WHERE school_id=:sid AND lower(last_name)=:a AND lower(middle_name)=:b AND lower(first_name)=:c LIMIT 1"),{'sid':sid,'a':norm(n['last_name']),'b':norm(n['middle_name']),'c':norm(n['first_name'])}).first()
  if dup:issues.append({'level':'WARNING','code':'POSSIBLE_DUPLICATE','field':'student','message':f'Doublon possible : {dup[0]}'})
 return n,issues

@router.post('/students/analyze')
async def analyze_students(request:Request, filename:str=Query(...,min_length=1,max_length=240), academic_year_id:UUID=Query(...), actor:ActorContext=Depends(require_school_actor), services:AppServices=Depends(get_services)):
 need(actor,'migration.students.analyze'); data=await read_import_body(request)
 guard_import_payload(data)
 ext=filename.lower().rsplit('.',1)[-1] if '.' in filename else ''
 if ext!='xlsx':raise HTTPException(415,'Import sécurisé : utilisez uniquement le modèle XLSX officiel EduSync')
 parsed=rows_from_xlsx(data)
 if len(parsed)>MAX_IMPORT_ROWS:raise HTTPException(413,'Maximum 5 000 lignes par lot')
 bid=uuid4()
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  yr=conn.execute(text('SELECT id,COALESCE(enrollment_start,start_date),COALESCE(enrollment_end,end_date) FROM academic_years WHERE school_id=:sid AND id=:y'),{'sid':actor.school_id,'y':academic_year_id}).first()
  if not yr:raise HTTPException(404,'Année scolaire introuvable')
  counts={'VALID':0,'WARNING':0,'ERROR':0}; previews=[]
  conn.execute(text("INSERT INTO student_import_batches(id,school_id,academic_year_id,filename,source_format,created_by) VALUES(:id,:sid,:y,:f,:fmt,:u)"),{'id':bid,'sid':actor.school_id,'y':academic_year_id,'f':filename,'fmt':ext.upper(),'u':actor.user_id})
  in_file=_same_file_duplicates(parsed,lambda r:tuple(norm(r.get(h)) for h in ('Nom*','Postnom*','Prénom*')) if all(clean(r.get(h)) for h in ('Nom*','Postnom*','Prénom*')) else None)
  for rn,row in parsed:
   n,issues=analyze_row(conn,actor.school_id,academic_year_id,row,(yr[1],yr[2]))
   if rn in in_file:issues.append({'level':'WARNING','code':'POSSIBLE_DUPLICATE','field':'student','message':'Même élève présent plusieurs fois dans le fichier'})
   status='ERROR' if any(x['level']=='ERROR' for x in issues) else ('WARNING' if issues else 'VALID');counts[status]+=1
   conn.execute(text("INSERT INTO student_import_rows(school_id,batch_id,row_number,payload,normalized_payload,status,issues) VALUES(:sid,:b,:rn,CAST(:p AS jsonb),CAST(:n AS jsonb),:s,CAST(:i AS jsonb))"),{'sid':actor.school_id,'b':bid,'rn':rn,'p':json.dumps({k:str(v) if v is not None else None for k,v in row.items()},ensure_ascii=False),'n':json.dumps(n,ensure_ascii=False),'s':status,'i':json.dumps(issues,ensure_ascii=False)})
   if len(previews)<100:previews.append({'row_number':rn,'status':status,'data':n,'issues':issues})
  total=len(parsed); conn.execute(text("UPDATE student_import_batches SET total_rows=:t,valid_rows=:v,warning_rows=:w,error_rows=:e,status=CASE WHEN :e=0 THEN 'READY' ELSE 'ANALYZED' END WHERE id=:b"),{'t':total,'v':counts['VALID'],'w':counts['WARNING'],'e':counts['ERROR'],'b':bid})
  PostgresAuditRepository(conn).append(AuditRecord(action='STUDENT_IMPORT_ANALYZED',entity_type='student_import_batch',entity_id=bid,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,new_data={'filename':filename,'total':total,**{k.lower():v for k,v in counts.items()}},correlation_id=actor.correlation_id))
 return {'batch_id':str(bid),'filename':filename,'total_rows':len(parsed),'valid_rows':counts['VALID'],'warning_rows':counts['WARNING'],'error_rows':counts['ERROR'],'can_execute':counts['ERROR']==0,'preview':previews,'preview_truncated':len(parsed)>100}

@router.get('/students/batches')
def batches(limit:int=Query(30,ge=1,le=100),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'migration.students.analyze')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  rs=conn.execute(text('SELECT id,academic_year_id,filename,source_format,status,total_rows,valid_rows,warning_rows,error_rows,created_at,executed_at FROM student_import_batches WHERE school_id=:sid ORDER BY created_at DESC LIMIT :lim'),{'sid':actor.school_id,'lim':limit}).mappings().all()
  return {'items':[{k:(str(v) if isinstance(v,(UUID,datetime)) else v) for k,v in dict(r).items()} for r in rs]}

class ExecuteBody(BaseModel):
 accept_warnings:bool=False
 confirm_separate_households:bool=False

@router.post('/students/batches/{batch_id}/execute')
def execute(batch_id:UUID,body:ExecuteBody,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'migration.students.execute')
 if not (idempotency_key or '').strip():raise HTTPException(400,'Idempotency-Key obligatoire')
 if not body.confirm_separate_households:raise HTTPException(409,"Confirmation requise : l'import ne fusionne jamais silencieusement les foyers")
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  b=conn.execute(text('SELECT * FROM student_import_batches WHERE school_id=:sid AND id=:b FOR UPDATE'),{'sid':actor.school_id,'b':batch_id}).mappings().first()
  if not b:raise HTTPException(404,'Lot introuvable')
  if b['status']=='EXECUTED':return {'batch_id':str(batch_id),'status':'EXECUTED','imported':b['valid_rows']+b['warning_rows'],'replayed':True}
  if b['error_rows']:raise HTTPException(409,"Corrigez les lignes en erreur puis analysez de nouveau le fichier")
  if b['warning_rows'] and not body.accept_warnings:raise HTTPException(409,'Des avertissements existent ; confirmation explicite requise')
  rows=conn.execute(text("SELECT * FROM student_import_rows WHERE school_id=:sid AND batch_id=:b AND status IN ('VALID','WARNING') ORDER BY row_number FOR UPDATE"),{'sid':actor.school_id,'b':batch_id}).mappings().all(); repo=PostgresSchoolingRepository(conn); imported=[]
  for r in rows:
   n=dict(r['normalized_payload'])
   # Re-validate at execution: another batch may have imported the same pupils since this one was analyzed.
   now_dup=conn.execute(text("SELECT 1 FROM students WHERE school_id=:sid AND lower(last_name)=:a AND lower(middle_name)=:b AND lower(first_name)=:c LIMIT 1"),{'sid':actor.school_id,'a':norm(n.get('last_name')),'b':norm(n.get('middle_name')),'c':norm(n.get('first_name'))}).first()
   if now_dup and r['status']!='WARNING':raise HTTPException(409,STALE_ANALYSIS)
   fid=uuid4(); label,origin=generate_family_label(guardian_name=n.get('guardian_name'),student_name=' '.join(filter(None,[n.get('last_name'),n.get('middle_name'),n.get('first_name')]))); family=Family(school_id=actor.school_id,id=fid,code=f"IMP-{uuid4().hex[:10].upper()}",display_name=label,display_name_origin=origin,phone=n.get('guardian_phone'),email=n.get('guardian_email'),address=n.get('address'),contact_status=ContactStatus.COMPLETE if n.get('guardian_phone') else ContactStatus.TO_COMPLETE,notes='Créé par import EduSync');repo.create_family(family)
   if n.get('guardian_name'):
    g=Guardian(school_id=actor.school_id,full_name=n['guardian_name'],phone=n.get('guardian_phone'),email=n.get('guardian_email'));repo.create_guardian(g);repo.link_guardian(actor.school_id,family_id=fid,guardian_id=g.id,role='TUTEUR',is_primary=True)
   sid=uuid4(); mat=f"IMP-{date.today().year}-{uuid4().hex[:8].upper()}"; st=Student(school_id=actor.school_id,id=sid,family_id=fid,matricule=mat,last_name=n['last_name'],middle_name=n['middle_name'],first_name=n['first_name'],gender=n['gender'],birth_date=date.fromisoformat(n['birth_date']) if n.get('birth_date') else None,birth_place=n.get('birth_place'),nationality=n.get('nationality'),address=n.get('address'),previous_school=n.get('previous_school'),notes=n.get('notes'));repo.create_student(st)
   en=Enrollment(school_id=actor.school_id,student_id=sid,academic_year_id=b['academic_year_id'],class_id=UUID(n['class_id']),enrollment_kind='TRANSFER_IN' if n.get('previous_school') else 'NEW',origin_school=n.get('previous_school'),notes='Import EduSync',**({'enrolled_on':date.fromisoformat(n['enrolled_on'])} if n.get('enrolled_on') else {}));repo.create_enrollment(en)
   conn.execute(text("UPDATE student_import_rows SET status='IMPORTED',imported_student_id=:s,imported_enrollment_id=:e WHERE id=:id"),{'s':sid,'e':en.id,'id':r['id']});imported.append(str(sid))
  conn.execute(text("UPDATE student_import_batches SET status='EXECUTED',executed_at=now(),version=version+1 WHERE id=:b"),{'b':batch_id})
  PostgresAuditRepository(conn).append(AuditRecord(action='STUDENT_IMPORT_EXECUTED',entity_type='student_import_batch',entity_id=batch_id,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,new_data={'imported':len(imported),'accept_warnings':body.accept_warnings,'separate_households_confirmed':True},correlation_id=actor.correlation_id,idempotency_key=idempotency_key))
  PostgresOutboxRepository(conn).add(OutboxMessage(event_type='STUDENT_IMPORT_EXECUTED',aggregate_type='student_import_batch',aggregate_id=batch_id,school_id=actor.school_id,payload={'imported':len(imported)},correlation_id=actor.correlation_id,deduplication_key=f'import:{batch_id}'))
  return {'batch_id':str(batch_id),'status':'EXECUTED','imported':len(imported),'student_ids':imported[:50]}


# Point 12B — Import personnel industriel
STAFF_HEADERS=['Matricule*','Nom*','Postnom','Prénom','Sexe','Catégorie*','Date naissance','Téléphone','E-mail','Adresse','Qualification','Spécialité','Date engagement','Statut','Observation']

def staff_rows_xlsx(data:bytes):
 try:return read_official_xlsx(data,'STAFF')
 except ValueError as e:raise HTTPException(400,str(e)) from e

def staff_rows_csv(data:bytes):
 try:s=data.decode('utf-8-sig')
 except UnicodeDecodeError as e:raise HTTPException(400,'CSV attendu en UTF-8') from e
 delim=';' if s[:4096].count(';')>=s[:4096].count(',') else ',';rd=csv.DictReader(io.StringIO(s),delimiter=delim)
 if not rd.fieldnames or [clean(x) for x in rd.fieldnames][:len(STAFF_HEADERS)]!=STAFF_HEADERS:raise HTTPException(400,'En-têtes CSV Personnel EduSync invalides')
 return [(i,{h:row.get(h) for h in STAFF_HEADERS}) for i,row in enumerate(rd,2)]

def analyze_staff_row(conn,sid,row):
 issues=[]; n={}
 mapping=[('Matricule*','employee_no'),('Nom*','last_name'),('Postnom','middle_name'),('Prénom','first_name'),('Sexe','gender'),('Catégorie*','category'),('Téléphone','phone'),('E-mail','email'),('Adresse','address'),('Qualification','qualification'),('Spécialité','specialty'),('Statut','status'),('Observation','notes')]
 for src,dst in mapping:n[dst]=clean(row.get(src)) or None
 for k,label in [('employee_no','Matricule'),('last_name','Nom'),('category','Catégorie')]:
  if not n[k]:issues.append({'level':'ERROR','code':'REQUIRED','field':k,'message':f'{label} obligatoire'})
 if n['employee_no']: n['employee_no']=n['employee_no'].upper()
 if n['gender']: n['gender']=n['gender'].upper()
 if n['gender'] not in (None,'M','F','X'):issues.append({'level':'ERROR','code':'GENDER','field':'gender','message':'Sexe attendu : F, M ou X'})
 if n['category']: n['category']=n['category'].upper().replace('É','E')
 aliases={'ENSEIGNANT':'ENSEIGNANT','ADMINISTRATIF':'ADMINISTRATIF','OUVRIER':'OUVRIER','AUTRE':'AUTRE'}; n['category']=aliases.get(n['category'],n['category'])
 if n['category'] not in aliases:issues.append({'level':'ERROR','code':'CATEGORY','field':'category','message':'Catégorie attendue : ENSEIGNANT, ADMINISTRATIF, OUVRIER ou AUTRE'})
 n['status']=(n['status'] or 'ACTIVE').upper()
 if n['status'] not in ('ACTIVE','SUSPENDED','INACTIVE'):issues.append({'level':'ERROR','code':'STATUS','field':'status','message':'Statut importable : ACTIVE, SUSPENDED ou INACTIVE'})
 for src,dst in [('Date naissance','birth_date'),('Date engagement','hire_date')]:
  try:n[dst]=parse_date(row.get(src)).isoformat() if row.get(src) else None
  except ValueError as e:n[dst]=None;issues.append({'level':'ERROR','code':'DATE','field':dst,'message':str(e)})
 if n.get('employee_no'):
  dup=conn.execute(text('SELECT id,last_name,first_name FROM staff_members WHERE school_id=:sid AND upper(employee_no)=:no LIMIT 1'),{'sid':sid,'no':n['employee_no']}).first()
  if dup:issues.append({'level':'ERROR','code':'EMPLOYEE_NO_EXISTS','field':'employee_no','message':f"Matricule déjà utilisé : {n['employee_no']}"})
 if n.get('last_name'):
  dup=conn.execute(text("SELECT employee_no FROM staff_members WHERE school_id=:sid AND lower(last_name)=:a AND lower(coalesce(first_name,''))=:b AND lower(coalesce(middle_name,''))=:c LIMIT 1"),{'sid':sid,'a':norm(n['last_name']),'b':norm(n.get('first_name')),'c':norm(n.get('middle_name'))}).first()
  if dup:issues.append({'level':'WARNING','code':'POSSIBLE_DUPLICATE','field':'staff','message':f'Doublon possible : {dup[0]}'})
 return n,issues

@router.get('/staff/template.xlsx')
def staff_template(actor:ActorContext=Depends(require_school_actor)):
 need(actor,'migration.staff.analyze'); bio=io.BytesIO(build_template('STAFF'))
 return Response(content=bio.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="modele_import_personnel_edusync.xlsx"'})

@router.post('/staff/analyze')
async def analyze_staff(request:Request,filename:str=Query(...,min_length=1,max_length=240),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'migration.staff.analyze');data=await read_import_body(request)
 guard_import_payload(data)
 ext=filename.lower().rsplit('.',1)[-1] if '.' in filename else ''
 if ext!='xlsx':raise HTTPException(415,'Import sécurisé : utilisez uniquement le modèle XLSX officiel EduSync')
 parsed=staff_rows_xlsx(data)
 if len(parsed)>5000:raise HTTPException(413,'Maximum 5 000 agents par lot')
 bid=uuid4();counts={'VALID':0,'WARNING':0,'ERROR':0};previews=[]
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  conn.execute(text("INSERT INTO staff_import_batches(id,school_id,filename,source_format,created_by) VALUES(:id,:sid,:f,:fmt,:u)"),{'id':bid,'sid':actor.school_id,'f':filename,'fmt':ext.upper(),'u':actor.user_id})
  for rn,row in parsed:
   n,issues=analyze_staff_row(conn,actor.school_id,row);status='ERROR' if any(x['level']=='ERROR' for x in issues) else ('WARNING' if issues else 'VALID');counts[status]+=1
   conn.execute(text("INSERT INTO staff_import_rows(school_id,batch_id,row_number,payload,normalized_payload,status,issues) VALUES(:sid,:b,:rn,CAST(:p AS jsonb),CAST(:n AS jsonb),:s,CAST(:i AS jsonb))"),{'sid':actor.school_id,'b':bid,'rn':rn,'p':json.dumps({k:str(v) if v is not None else None for k,v in row.items()},ensure_ascii=False),'n':json.dumps(n,ensure_ascii=False),'s':status,'i':json.dumps(issues,ensure_ascii=False)})
   if len(previews)<100:previews.append({'row_number':rn,'status':status,'data':n,'issues':issues})
  conn.execute(text("UPDATE staff_import_batches SET total_rows=:t,valid_rows=:v,warning_rows=:w,error_rows=:e,status=CASE WHEN :e=0 THEN 'READY' ELSE 'ANALYZED' END WHERE id=:b"),{'t':len(parsed),'v':counts['VALID'],'w':counts['WARNING'],'e':counts['ERROR'],'b':bid})
  PostgresAuditRepository(conn).append(AuditRecord(action='STAFF_IMPORT_ANALYZED',entity_type='staff_import_batch',entity_id=bid,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,new_data={'filename':filename,'total':len(parsed),**{k.lower():v for k,v in counts.items()}},correlation_id=actor.correlation_id))
 return {'batch_id':str(bid),'filename':filename,'total_rows':len(parsed),'valid_rows':counts['VALID'],'warning_rows':counts['WARNING'],'error_rows':counts['ERROR'],'can_execute':counts['ERROR']==0,'preview':previews,'preview_truncated':len(parsed)>100}

class ExecuteStaffBody(BaseModel): accept_warnings:bool=False

@router.post('/staff/batches/{batch_id}/execute')
def execute_staff(batch_id:UUID,body:ExecuteStaffBody,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'migration.staff.execute')
 if not (idempotency_key or '').strip():raise HTTPException(400,'Idempotency-Key obligatoire')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  b=conn.execute(text('SELECT * FROM staff_import_batches WHERE school_id=:sid AND id=:b FOR UPDATE'),{'sid':actor.school_id,'b':batch_id}).mappings().first()
  if not b:raise HTTPException(404,'Lot introuvable')
  if b['status']=='EXECUTED':return {'batch_id':str(batch_id),'status':'EXECUTED','imported':b['valid_rows']+b['warning_rows'],'replayed':True}
  if b['error_rows']>0:raise HTTPException(409,'Le lot contient des erreurs')
  if b['warning_rows']>0 and not body.accept_warnings:raise HTTPException(409,'Confirmation explicite requise pour les avertissements')
  rows=conn.execute(text("SELECT id,normalized_payload,status FROM staff_import_rows WHERE school_id=:sid AND batch_id=:b AND status IN ('VALID','WARNING') ORDER BY row_number FOR UPDATE"),{'sid':actor.school_id,'b':batch_id}).mappings().all();repo=PostgresPersonnelRepository(conn);done=0
  for row in rows:
   n=dict(row['normalized_payload'])
   if conn.execute(text('SELECT 1 FROM staff_members WHERE school_id=:sid AND upper(employee_no)=upper(:no) LIMIT 1'),{'sid':actor.school_id,'no':n['employee_no']}).first():raise HTTPException(409,STALE_ANALYSIS)
   member=StaffMember(school_id=actor.school_id,employee_no=n['employee_no'],last_name=n['last_name'],first_name=n.get('first_name'),middle_name=n.get('middle_name'),gender=n.get('gender'),birth_date=date.fromisoformat(n['birth_date']) if n.get('birth_date') else None,phone=n.get('phone'),email=n.get('email'),address=n.get('address'),category=StaffCategory(n['category']),qualification=n.get('qualification'),specialty=n.get('specialty'),hire_date=date.fromisoformat(n['hire_date']) if n.get('hire_date') else None,status=StaffStatus(n['status']),notes=n.get('notes'));repo.create_staff(member);done+=1
   conn.execute(text("UPDATE staff_import_rows SET status='IMPORTED',imported_staff_id=:staff WHERE id=:id"),{'staff':member.id,'id':row['id']})
  conn.execute(text("UPDATE staff_import_batches SET status='EXECUTED',executed_at=now(),version=version+1 WHERE id=:b"),{'b':batch_id})
  PostgresAuditRepository(conn).append(AuditRecord(action='STAFF_IMPORT_EXECUTED',entity_type='staff_import_batch',entity_id=batch_id,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,new_data={'imported':done},correlation_id=actor.correlation_id))
  PostgresOutboxRepository(conn).add(OutboxMessage(school_id=actor.school_id,aggregate_type='staff_import_batch',aggregate_id=batch_id,event_type='STAFF_IMPORT_EXECUTED',payload={'batch_id':str(batch_id),'imported':done}))
 return {'batch_id':str(batch_id),'status':'EXECUTED','imported':done,'replayed':False}

# Point 12C — Reprise historique financière, explicitement hors caisse
FIN_HEADERS=['Année scolaire*','Matricule élève*','Frais*','Période','Montant*','Devise*','Date paiement*','Référence historique','Observation']
def fin_rows_xlsx(data:bytes):
 try:return read_official_xlsx(data,'FINANCE_HISTORY')
 except ValueError as e:raise HTTPException(400,str(e)) from e

def fin_rows_csv(data:bytes):
 try:s=data.decode('utf-8-sig')
 except UnicodeDecodeError as e:raise HTTPException(400,'CSV attendu en UTF-8') from e
 d=';' if s[:4096].count(';')>=s[:4096].count(',') else ',';rd=csv.DictReader(io.StringIO(s),delimiter=d)
 if not rd.fieldnames or [clean(x) for x in rd.fieldnames][:len(FIN_HEADERS)]!=FIN_HEADERS:raise HTTPException(400,'En-têtes CSV financiers EduSync invalides')
 return [(i,{h:r.get(h) for h in FIN_HEADERS}) for i,r in enumerate(rd,2)]
def analyze_fin_row(conn,sid,row):
 issues=[];n={'year':clean(row.get('Année scolaire*')),'matricule':clean(row.get('Matricule élève*')),'fee':clean(row.get('Frais*')),'period':clean(row.get('Période')) or None,'currency':clean(row.get('Devise*')).upper(),'reference':clean(row.get('Référence historique')) or None,'notes':clean(row.get('Observation')) or None}
 for k,label in [('year','Année scolaire'),('matricule','Matricule élève'),('fee','Frais'),('currency','Devise')]:
  if not n[k]:issues.append({'level':'ERROR','code':'REQUIRED','field':k,'message':f'{label} obligatoire'})
 try:n['amount']=str(__import__('decimal').Decimal(str(row.get('Montant*'))));assert __import__('decimal').Decimal(n['amount'])>0
 except Exception:n['amount']=None;issues.append({'level':'ERROR','code':'AMOUNT','field':'amount','message':'Montant strictement positif attendu'})
 if n['currency'] not in ('CDF','USD'):issues.append({'level':'ERROR','code':'CURRENCY','field':'currency','message':'Devise attendue : CDF ou USD'})
 try:n['paid_on']=parse_date(row.get('Date paiement*')).isoformat()
 except Exception:n['paid_on']=None;issues.append({'level':'ERROR','code':'DATE','field':'paid_on','message':'Date paiement invalide'})
 if issues:return n,issues
 q=conn.execute(text("""SELECT fc.id,fc.net_amount,fc.paid_amount,COALESCE((SELECT sum(r.amount) FROM finance_charge_regularizations r WHERE r.school_id=fc.school_id AND r.charge_id=fc.id),0) outside_cash,ay.label,ft.label,fc.period_label
 FROM students s JOIN enrollments e ON e.student_id=s.id AND e.school_id=s.school_id JOIN academic_years ay ON ay.id=e.academic_year_id
 JOIN finance_charges fc ON fc.enrollment_id=e.id AND fc.school_id=e.school_id LEFT JOIN fee_types ft ON ft.id=fc.fee_type_id
 WHERE s.school_id=:sid AND upper(s.matricule)=upper(:m) AND (lower(ay.code)=lower(:y) OR lower(ay.label)=lower(:y))
 AND (lower(coalesce(ft.code,''))=lower(:f) OR lower(coalesce(ft.label,''))=lower(:f) OR lower(fc.label)=lower(:f))
 AND (CAST(:p AS text) IS NULL OR lower(coalesce(fc.period_label,''))=lower(:p)) AND fc.currency=:cur AND fc.status='ACTIVE' LIMIT 3"""),{'sid':sid,'m':n['matricule'],'y':n['year'],'f':n['fee'],'p':n['period'],'cur':n['currency']}).mappings().all()
 if len(q)==0:issues.append({'level':'ERROR','code':'CHARGE_NOT_FOUND','field':'fee','message':'Obligation financière introuvable pour cet élève/année/frais/période'})
 elif len(q)>1:issues.append({'level':'ERROR','code':'CHARGE_AMBIGUOUS','field':'fee','message':'Plusieurs obligations correspondent : préciser la période'})
 else:
  x=q[0];n['charge_id']=str(x['id']);remaining=__import__('decimal').Decimal(str(x['net_amount']))-__import__('decimal').Decimal(str(x['paid_amount']))-__import__('decimal').Decimal(str(x['outside_cash']));n['remaining_before']=str(max(remaining,0));n['fee_resolved']=x['label'];n['year_resolved']=x['label_1'] if 'label_1' in x else n['year']
  if __import__('decimal').Decimal(n['amount'])>remaining:
   # N3-H / G-IMP-1 — Desktop finalize_historical_financial_import: a monthly amount above the month's balance is spread
   # over the following monthly charges of the same fee as historical advances; only what no month can absorb is refused.
   spread=_historical_spread(conn,sid,n['charge_id'],__import__('decimal').Decimal(n['amount']))
   if spread is None:issues.append({'level':'ERROR','code':'OVER_REGULARIZATION','field':'amount','message':f"Montant supérieur au reste dû ({max(remaining,0)} {n['currency']})"})
   else:
    n['allocations']=spread;issues.append({'level':'WARNING','code':'HISTORICAL_SPREAD','field':'amount','message':'Montant réparti sur les mois suivants (avance historique) : '+', '.join(f"{a['label']} {a['amount']}" for a in spread)})
  if n['reference']:
   dup=conn.execute(text("SELECT 1 FROM financial_history_import_ledger WHERE school_id=:sid AND historical_reference=:r AND amount=:a AND currency=:c LIMIT 1"),{'sid':sid,'r':n['reference'],'a':n['amount'],'c':n['currency']}).first()
   if dup:issues.append({'level':'ERROR','code':'HISTORY_DUPLICATE','field':'reference','message':'Cette référence historique a déjà été reprise'})
  else:issues.append({'level':'WARNING','code':'NO_REFERENCE','field':'reference','message':'Aucune référence historique : conserver la pièce source avant confirmation'})
 return n,issues

def _historical_spread(conn,sid,charge_id,amount):
 """Allocation of a historical amount over this monthly charge then the following months of the same fee (Desktop)."""
 from decimal import Decimal as _D
 base=conn.execute(text("SELECT enrollment_id,fee_type_id,currency,periodicity,coalesce(period_order,0) po FROM finance_charges WHERE id=:c AND school_id=:sid"),{'c':charge_id,'sid':sid}).mappings().first()
 if not base or base['periodicity']!='MONTHLY':return None
 rows=conn.execute(text("""SELECT fc.id,coalesce(fc.period_label,fc.label) label,GREATEST(fc.net_amount-finance_charge_decision_amount(fc.id)-fc.paid_amount
   -COALESCE((SELECT sum(r.amount) FROM finance_charge_regularizations r WHERE r.charge_id=fc.id),0),0) due
   FROM finance_charges fc WHERE fc.school_id=:sid AND fc.enrollment_id=:e AND fc.fee_type_id=:f AND fc.currency=:cur AND fc.status='ACTIVE' AND coalesce(fc.period_order,0)>=:po
   ORDER BY coalesce(fc.period_order,0),fc.due_date"""),{'sid':sid,'e':base['enrollment_id'],'f':base['fee_type_id'],'cur':base['currency'],'po':base['po']}).mappings().all()
 left=amount;out=[]
 for r in rows:
  take=min(left,_D(str(r['due'])))
  if take>0:out.append({'charge_id':str(r['id']),'label':r['label'],'amount':str(take)});left-=take
  if left<=0:break
 return out if left<=0 else None

@router.get('/finance-history/rows/{row_id}/suggestions')
def finance_history_suggestions(row_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """N3-H / G-IMP-2 — Desktop historical_student_suggestions (the Web line carries a matricule: ranked by matricule similarity)."""
 need(actor,'migration.finance_history.analyze')
 from edusync.adapters.postgres_schooling_parity import PostgresSchoolingParityRepository
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  r=conn.execute(text("SELECT normalized_payload FROM financial_history_import_rows WHERE id=:id AND school_id=:sid"),{'id':row_id,'sid':actor.school_id}).scalar_one_or_none()
  if r is None:raise HTTPException(404,"Ligne d'import historique introuvable")
  n=dict(r);return {'row_id':str(row_id),'matricule':n.get('matricule'),'suggestions':PostgresSchoolingParityRepository(conn).history_suggestions(actor.school_id,matricule=n.get('matricule') or '',year_label=n.get('year'))}

@router.post('/students/date-repair/preview')
async def enrollment_date_repair_preview(request:Request,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """N3-H / G-IMP-2 — Desktop preview_enrollment_date_repair: read-only diagnostic of historical enrollment dates (XLSX)."""
 need(actor,'migration.students.analyze')
 data=await read_import_body(request);guard_import_payload(data)
 rows=_date_repair_rows(data)
 if len(rows)>MAX_IMPORT_ROWS:raise HTTPException(413,'Maximum 5 000 lignes par fichier')
 from edusync.adapters.postgres_schooling_parity import PostgresSchoolingParityRepository
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  return PostgresSchoolingParityRepository(conn).date_repair_preview(actor.school_id,rows)

def _date_repair_rows(data:bytes)->list[dict]:
 from openpyxl import load_workbook
 wb=load_workbook(io.BytesIO(data),read_only=True,data_only=True);ws=wb.worksheets[0];it=ws.iter_rows(values_only=True)
 header=[clean(x).lower() if x is not None else '' for x in next(it,[])]
 def col(*names):
  for nm in names:
   for i,h in enumerate(header):
    if h.replace('*','').strip()==nm:return i
  return None
 ci={'last':col('nom'),'middle':col('postnom','post-nom'),'first':col('prénom','prenom'),'sex':col('sexe'),'class':col('classe'),
     'date':col('date inscription',"date d'inscription",'dates inscription',"dates d'inscription",'dates')}
 out=[]
 for rn,row in enumerate(it,2):
  get=lambda k:(row[ci[k]] if ci[k] is not None and ci[k]<len(row) else None)
  name=' '.join(str(get(k)).strip() for k in ('last','middle','first') if get(k));d=get('date')
  if not name:continue
  try:hd=d.date() if hasattr(d,'date') else (parse_date(d) if d else None)
  except Exception:hd=None
  out.append({'row':rn,'name':name,'gender':str(get('sex') or '').strip().upper()[:1],'class':str(get('class') or ''),'date':hd.isoformat() if hd else None,
              'warning':None if hd else 'Date historique absente ou invalide'})
 return out

@router.get('/finance-history/template.xlsx')
def finance_history_template(actor:ActorContext=Depends(require_school_actor)):
 need(actor,'migration.finance_history.analyze');bio=io.BytesIO(build_template('FINANCE_HISTORY'));return Response(content=bio.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="modele_reprise_historique_financiere_edusync.xlsx"'})

@router.post('/finance-history/analyze')
async def analyze_finance_history(request:Request,filename:str=Query(...,min_length=1,max_length=240),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'migration.finance_history.analyze');data=await read_import_body(request);ext=filename.lower().rsplit('.',1)[-1] if '.' in filename else ''
 guard_import_payload(data)
 if ext!='xlsx':raise HTTPException(415,'Reprise financière sécurisée : utilisez uniquement le modèle XLSX officiel EduSync')
 parsed=fin_rows_xlsx(data)
 if len(parsed)>MAX_IMPORT_ROWS:raise HTTPException(413,'Maximum 5 000 lignes financières par lot')
 bid=uuid4();counts={'VALID':0,'WARNING':0,'ERROR':0};preview=[]
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  conn.execute(text("INSERT INTO financial_history_import_batches(id,school_id,filename,source_format,created_by) VALUES(:id,:sid,:f,:fmt,:u)"),{'id':bid,'sid':actor.school_id,'f':filename,'fmt':ext.upper(),'u':actor.user_id})
  for rn,row in parsed:
   n,issues=analyze_fin_row(conn,actor.school_id,row);st='ERROR' if any(i['level']=='ERROR' for i in issues) else ('WARNING' if issues else 'VALID');counts[st]+=1
   conn.execute(text("INSERT INTO financial_history_import_rows(school_id,batch_id,row_number,payload,normalized_payload,status,issues) VALUES(:sid,:b,:rn,CAST(:p AS jsonb),CAST(:n AS jsonb),:st,CAST(:i AS jsonb))"),{'sid':actor.school_id,'b':bid,'rn':rn,'p':json.dumps({k:str(v) if v is not None else None for k,v in row.items()},ensure_ascii=False),'n':json.dumps(n,ensure_ascii=False),'st':st,'i':json.dumps(issues,ensure_ascii=False)})
   if len(preview)<100:preview.append({'row_number':rn,'status':st,'data':n,'issues':issues})
  conn.execute(text("UPDATE financial_history_import_batches SET total_rows=:t,valid_rows=:v,warning_rows=:w,error_rows=:e,status=CASE WHEN :e=0 THEN 'READY' ELSE 'ANALYZED' END WHERE id=:b"),{'t':len(parsed),'v':counts['VALID'],'w':counts['WARNING'],'e':counts['ERROR'],'b':bid})
  PostgresAuditRepository(conn).append(AuditRecord(action='FINANCIAL_HISTORY_IMPORT_ANALYZED',entity_type='financial_history_import_batch',entity_id=bid,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,new_data={'filename':filename,'total':len(parsed),**{k.lower():v for k,v in counts.items()}},correlation_id=actor.correlation_id))
 return {'batch_id':str(bid),'filename':filename,'total_rows':len(parsed),'valid_rows':counts['VALID'],'warning_rows':counts['WARNING'],'error_rows':counts['ERROR'],'can_execute':counts['ERROR']==0,'preview':preview,'preview_truncated':len(parsed)>100}
class ExecuteFinanceHistoryBody(BaseModel):accept_warnings:bool=False;confirm_outside_cash:bool=False
@router.post('/finance-history/batches/{batch_id}/execute')
def execute_finance_history(batch_id:UUID,body:ExecuteFinanceHistoryBody,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'migration.finance_history.execute')
 if not (idempotency_key or '').strip():raise HTTPException(400,'Idempotency-Key obligatoire')
 if not body.confirm_outside_cash:raise HTTPException(409,"Confirmation requise : la reprise est hors caisse et ne crée aucun reçu EduSync")
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  b=conn.execute(text('SELECT * FROM financial_history_import_batches WHERE school_id=:sid AND id=:b FOR UPDATE'),{'sid':actor.school_id,'b':batch_id}).mappings().first()
  if not b:raise HTTPException(404,'Lot introuvable')
  if b['status']=='EXECUTED':return {'batch_id':str(batch_id),'status':'EXECUTED','imported':b['valid_rows']+b['warning_rows'],'replayed':True,'cash_created':False}
  if b['error_rows']>0:raise HTTPException(409,'Le lot contient des erreurs')
  if b['warning_rows']>0 and not body.accept_warnings:raise HTTPException(409,'Confirmation explicite requise pour les avertissements')
  rows=conn.execute(text("SELECT id,normalized_payload,status FROM financial_history_import_rows WHERE school_id=:sid AND batch_id=:b AND status IN('VALID','WARNING') ORDER BY row_number FOR UPDATE"),{'sid':actor.school_id,'b':batch_id}).mappings().all();done=0
  expanded=[]
  for row in rows:
   n=dict(row['normalized_payload'])
   for a in (n.get('allocations') or [{'charge_id':n['charge_id'],'amount':n['amount']}]):expanded.append((row,{**n,'charge_id':a['charge_id'],'amount':a['amount'],'_row_amount':n['amount']}))
  ledgered=set()
  for row,n in expanded:
   # Lock the obligation and recompute what is still owed now (cash payments, decisions and
   # regularizations may have happened since analysis, including earlier rows of this batch).
   ch=conn.execute(text("""SELECT fc.net_amount,fc.paid_amount,
     finance_charge_decision_amount(fc.id) decisions,
     coalesce((SELECT sum(r.amount) FROM finance_charge_regularizations r WHERE r.school_id=fc.school_id AND r.charge_id=fc.id),0) outside_cash
     FROM finance_charges fc WHERE fc.school_id=:sid AND fc.id=:ch AND fc.status='ACTIVE' FOR UPDATE OF fc"""),{'sid':actor.school_id,'ch':n['charge_id']}).mappings().first()
   if not ch:raise HTTPException(409,STALE_ANALYSIS)
   still_due=Decimal(str(ch['net_amount']))-Decimal(str(ch['decisions']))-Decimal(str(ch['paid_amount']))-Decimal(str(ch['outside_cash']))
   if Decimal(str(n['amount']))>still_due:raise HTTPException(409,STALE_ANALYSIS+' (montant supérieur au reste dû)')
   if n.get('reference') and row.get('status')!='WARNING' and conn.execute(text("SELECT 1 FROM financial_history_import_ledger WHERE school_id=:sid AND historical_reference=:r AND amount=:a AND currency=:c LIMIT 1"),{'sid':actor.school_id,'r':n['reference'],'a':n['amount'],'c':n['currency']}).first():raise HTTPException(409,STALE_ANALYSIS+' (référence déjà reprise)')
   rid=uuid4();reason='Reprise historique importée — hors caisse'+(f" · {n['notes']}" if n.get('notes') else '')
   conn.execute(text("INSERT INTO finance_charge_regularizations(id,school_id,charge_id,amount,reason,reference,actor_user_id,created_at) VALUES(:id,:sid,:ch,:a,:reason,:ref,:u,:dt)"),{'id':rid,'sid':actor.school_id,'ch':n['charge_id'],'a':n['amount'],'reason':reason[:240],'ref':n.get('reference'),'u':actor.user_id,'dt':n['paid_on']})
   if row['id'] not in ledgered:   # one ledger line per source row (a spread row posts several regularizations)
    ledgered.add(row['id'])
    conn.execute(text("INSERT INTO financial_history_import_ledger(school_id,batch_id,row_id,charge_id,regularization_id,historical_paid_on,historical_reference,amount,currency) VALUES(:sid,:b,:row,:ch,:r,:d,:ref,:a,:c)"),{'sid':actor.school_id,'b':batch_id,'row':row['id'],'ch':n['charge_id'],'r':rid,'d':n['paid_on'],'ref':n.get('reference'),'a':n.get('_row_amount',n['amount']),'c':n['currency']})
   conn.execute(text("UPDATE financial_history_import_rows SET status='IMPORTED',imported_regularization_id=COALESCE(imported_regularization_id,:r) WHERE id=:id"),{'r':rid,'id':row['id']});done+=1
  conn.execute(text("UPDATE financial_history_import_batches SET status='EXECUTED',executed_at=now(),version=version+1 WHERE id=:b"),{'b':batch_id})
  PostgresAuditRepository(conn).append(AuditRecord(action='FINANCIAL_HISTORY_IMPORT_EXECUTED',entity_type='financial_history_import_batch',entity_id=batch_id,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,new_data={'imported':len(ledgered),'cash_created':False,'receipt_created':False},correlation_id=actor.correlation_id));PostgresOutboxRepository(conn).add(OutboxMessage(school_id=actor.school_id,aggregate_type='financial_history_import_batch',aggregate_id=batch_id,event_type='FINANCIAL_HISTORY_IMPORT_EXECUTED',payload={'batch_id':str(batch_id),'imported':len(ledgered),'cash_created':False}))
 return {'batch_id':str(batch_id),'status':'EXECUTED','imported':len(ledgered),'replayed':False,'cash_created':False,'receipt_created':False}

# Point 12E — traçabilité opérateur : historique des lots et rapport de contrôle exportable
_IMPORT_KIND = {
 'students': ('migration.students.analyze','Élèves'),
 'staff': ('migration.staff.analyze','Personnel'),
 'finance-history': ('migration.finance_history.analyze','Historique financier'),
}
def _import_kind(kind:str):
 cfg=_IMPORT_KIND.get(kind)
 if not cfg:raise HTTPException(404,'Type d’import inconnu')
 return cfg

def _batch_rows(conn,kind,sid,limit,offset):
 if kind=='students':
  total=conn.execute(text('SELECT count(*) FROM student_import_batches WHERE school_id=:sid'),{'sid':sid}).scalar_one();rows=conn.execute(text('SELECT id,filename,source_format,status,total_rows,valid_rows,warning_rows,error_rows,created_at,executed_at FROM student_import_batches WHERE school_id=:sid ORDER BY created_at DESC,id DESC LIMIT :lim OFFSET :off'),{'sid':sid,'lim':limit,'off':offset}).mappings().all()
 elif kind=='staff':
  total=conn.execute(text('SELECT count(*) FROM staff_import_batches WHERE school_id=:sid'),{'sid':sid}).scalar_one();rows=conn.execute(text('SELECT id,filename,source_format,status,total_rows,valid_rows,warning_rows,error_rows,created_at,executed_at FROM staff_import_batches WHERE school_id=:sid ORDER BY created_at DESC,id DESC LIMIT :lim OFFSET :off'),{'sid':sid,'lim':limit,'off':offset}).mappings().all()
 else:
  total=conn.execute(text('SELECT count(*) FROM financial_history_import_batches WHERE school_id=:sid'),{'sid':sid}).scalar_one();rows=conn.execute(text('SELECT id,filename,source_format,status,total_rows,valid_rows,warning_rows,error_rows,created_at,executed_at FROM financial_history_import_batches WHERE school_id=:sid ORDER BY created_at DESC,id DESC LIMIT :lim OFFSET :off'),{'sid':sid,'lim':limit,'off':offset}).mappings().all()
 return total,rows

def _batch_control_rows(conn,kind,sid,bid):
 if kind=='students':
  b=conn.execute(text('SELECT id,filename,status,total_rows,valid_rows,warning_rows,error_rows,created_at FROM student_import_batches WHERE school_id=:sid AND id=:bid'),{'sid':sid,'bid':bid}).mappings().first();r=conn.execute(text('SELECT row_number,status,issues,payload FROM student_import_rows WHERE school_id=:sid AND batch_id=:bid ORDER BY row_number'),{'sid':sid,'bid':bid}).mappings().all()
 elif kind=='staff':
  b=conn.execute(text('SELECT id,filename,status,total_rows,valid_rows,warning_rows,error_rows,created_at FROM staff_import_batches WHERE school_id=:sid AND id=:bid'),{'sid':sid,'bid':bid}).mappings().first();r=conn.execute(text('SELECT row_number,status,issues,payload FROM staff_import_rows WHERE school_id=:sid AND batch_id=:bid ORDER BY row_number'),{'sid':sid,'bid':bid}).mappings().all()
 else:
  b=conn.execute(text('SELECT id,filename,status,total_rows,valid_rows,warning_rows,error_rows,created_at FROM financial_history_import_batches WHERE school_id=:sid AND id=:bid'),{'sid':sid,'bid':bid}).mappings().first();r=conn.execute(text('SELECT row_number,status,issues,payload FROM financial_history_import_rows WHERE school_id=:sid AND batch_id=:bid ORDER BY row_number'),{'sid':sid,'bid':bid}).mappings().all()
 return b,r

@router.get('/batches/{kind}')
def import_batch_history(kind:str,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 capability,label=_import_kind(kind);need(actor,capability)
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:total,rows=_batch_rows(conn,kind,actor.school_id,limit,offset)
 return {'kind':kind,'label':label,'total':total,'limit':limit,'offset':offset,'items':[{**dict(r),'id':str(r['id']),'created_at':r['created_at'].isoformat() if r['created_at'] else None,'executed_at':r['executed_at'].isoformat() if r['executed_at'] else None} for r in rows]}

@router.get('/batches/{kind}/{batch_id}/control-report.xlsx')
def import_control_report(kind:str,batch_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 capability,label=_import_kind(kind);need(actor,capability)
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:batch,rows=_batch_control_rows(conn,kind,actor.school_id,batch_id)
 if not batch:raise HTTPException(404,'Lot d’import introuvable')
 wb=Workbook();ws=wb.active;ws.title='Contrôle import';ws.append(['EduSync — Rapport de contrôle import']);ws.append(['Type',label]);ws.append(['Fichier',batch['filename']]);ws.append(['Statut',batch['status']]);ws.append(['Total',batch['total_rows'],'Valides',batch['valid_rows'],'Avertissements',batch['warning_rows'],'Erreurs',batch['error_rows']]);ws.append([]);ws.append(['Ligne','État','Code','Champ','Message','Données source'])
 for r in rows:
  issues=r['issues'] or [];issues=json.loads(issues) if isinstance(issues,str) else issues;payload=r['payload'] if isinstance(r['payload'],dict) else json.loads(r['payload'] or '{}')
  if issues:
   for issue in issues:ws.append([r['row_number'],r['status'],issue.get('code',''),issue.get('field',''),issue.get('message',''),json.dumps(payload,ensure_ascii=False,default=str)])
  else:ws.append([r['row_number'],r['status'],'','','Prêt',json.dumps(payload,ensure_ascii=False,default=str)])
 ws.freeze_panes='A7';ws.auto_filter.ref=f'A7:F{max(7,ws.max_row)}'
 for col,width in {'A':10,'B':16,'C':24,'D':20,'E':60,'F':80}.items():ws.column_dimensions[col].width=width
 neutralize_formulas(wb);out=io.BytesIO();wb.save(out);safe=re.sub(r'[^A-Za-z0-9._-]+','_',batch['filename'])[:80]
 return Response(content=out.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="controle_import_{kind}_{safe}.xlsx"'})


# Point 12F — centre d'import: contrats publiés, annulation et nettoyage contrôlé des lots non exécutés
@router.get('/contracts')
def import_contract_registry(actor:ActorContext=Depends(require_school_actor)):
 kinds=[]
 for kind,c in CONTRACTS.items():
  cap={'STUDENTS':'migration.students.analyze','STAFF':'migration.staff.analyze','FINANCE_HISTORY':'migration.finance_history.analyze'}[kind]
  if cap in actor.permissions:
   kinds.append({'kind':kind,'contract_id':c['id'],'contract_version':contract_version(kind),'max_rows':MAX_IMPORT_ROWS,'max_bytes':MAX_IMPORT_BYTES,'format':'XLSX'})
 return {'contracts':kinds,'policy':'OFFICIAL_TEMPLATE_ONLY'}

class CancelImportBody(BaseModel):
 reason:str

def _cancel_batch(conn,kind,sid,bid):
 if kind=='students':
  b=conn.execute(text('SELECT id,status FROM student_import_batches WHERE school_id=:sid AND id=:bid FOR UPDATE'),{'sid':sid,'bid':bid}).mappings().first()
  update_sql="UPDATE student_import_batches SET status='CANCELLED',version=version+1 WHERE school_id=:sid AND id=:bid"
 elif kind=='staff':
  b=conn.execute(text('SELECT id,status FROM staff_import_batches WHERE school_id=:sid AND id=:bid FOR UPDATE'),{'sid':sid,'bid':bid}).mappings().first()
  update_sql="UPDATE staff_import_batches SET status='CANCELLED',version=version+1 WHERE school_id=:sid AND id=:bid"
 elif kind=='finance-history':
  b=conn.execute(text('SELECT id,status FROM financial_history_import_batches WHERE school_id=:sid AND id=:bid FOR UPDATE'),{'sid':sid,'bid':bid}).mappings().first()
  update_sql="UPDATE financial_history_import_batches SET status='CANCELLED',version=version+1 WHERE school_id=:sid AND id=:bid"
 else: raise HTTPException(404,'Type d’import inconnu')
 if not b: raise HTTPException(404,'Lot d’import introuvable')
 if b['status']=='EXECUTED': raise HTTPException(409,'Un lot exécuté ne peut pas être annulé')
 if b['status']!='CANCELLED': conn.execute(text(update_sql),{'sid':sid,'bid':bid})
 return b

@router.post('/batches/{kind}/{batch_id}/cancel')
def cancel_import_batch(kind:str,batch_id:UUID,body:CancelImportBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 capability,label=_import_kind(kind);need(actor,capability)
 reason=clean(body.reason)
 if len(reason)<5: raise HTTPException(422,'Motif d’annulation requis (5 caractères minimum)')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  _cancel_batch(conn,kind,actor.school_id,batch_id)
  PostgresAuditRepository(conn).append(AuditRecord(action='IMPORT_BATCH_CANCELLED',entity_type='import_batch',entity_id=batch_id,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,new_data={'kind':kind,'reason':reason},correlation_id=actor.correlation_id))
 return {'batch_id':str(batch_id),'status':'CANCELLED'}
