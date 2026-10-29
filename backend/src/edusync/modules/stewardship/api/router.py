from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,Header,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import text
from edusync.bootstrap.dependencies import get_services,require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress
from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
router=APIRouter(tags=['Intendance'])
def need(a,c):
 try:a.require(c)
 except PermissionError as e:raise HTTPException(403,str(e)) from e
def rows(conn,sql,p):return [dict(x._mapping) for x in conn.execute(text(sql),p)]
@router.get('/dashboard')
def dashboard(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 if not ({'inventory.stock.read','inventory.assets.read','inventory.counts.read','inventory.stock.low_alerts.read'} & set(actor.permissions)): raise HTTPException(403,'Permission Intendance requise')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  p={'sid':str(actor.school_id)}
  permissions=set(actor.permissions)
  # Enforce each permission before running its SQL query, not only on output.
  locations=rows(c,"SELECT status,count(*) n FROM inventory_locations WHERE school_id=:sid GROUP BY status",p) if 'inventory.assets.read' in permissions else []
  assets=rows(c,"SELECT status,coalesce(sum(quantity),0) n FROM inventory_assets WHERE school_id=:sid GROUP BY status",p) if 'inventory.assets.read' in permissions else []
  low=rows(c,"SELECT id,code,label,unit,quantity,low_threshold FROM inventory_items WHERE school_id=:sid AND enabled AND quantity<=low_threshold ORDER BY quantity, label LIMIT 12",p) if 'inventory.stock.low_alerts.read' in permissions else []
  sales=rows(c,"SELECT p.id,p.code,p.label,p.currency,p.unit_price,coalesce(s.quantity,0) quantity,coalesce(s.low_threshold,0) low_threshold FROM school_products p LEFT JOIN inventory_stock s ON s.school_id=p.school_id AND s.product_id=p.id WHERE p.school_id=:sid AND p.enabled AND p.stock_tracking ORDER BY p.label",p) if 'inventory.stock.read' in permissions else []
  return {'locations':locations,'assets':assets,'low_stock':low,'sale_stock':sales}

@router.get('/stock')
def stock(limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.stock.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:p={'sid':str(actor.school_id),'limit':limit,'offset':offset}; items=rows(c,"SELECT i.*,l.label location_label FROM inventory_items i LEFT JOIN inventory_locations l ON l.id=i.location_id WHERE i.school_id=:sid AND i.enabled ORDER BY i.item_kind,i.label LIMIT :limit OFFSET :offset",p); total=c.execute(text("SELECT count(*) FROM inventory_items i WHERE i.school_id=:sid AND i.enabled"),{'sid':str(actor.school_id)}).scalar_one(); return {'items':items,'total':int(total),'limit':limit,'offset':offset}
class Movement(BaseModel):item_id:UUID;movement_type:Literal['RECEIPT','ISSUE','ADJUSTMENT'];quantity:Decimal=Field(gt=0);adjustment_direction:Literal['INCREASE','DECREASE']|None=None;reason:str=Field(min_length=3,max_length=700);destination:str|None=Field(None,max_length=180);reference:str|None=Field(None,max_length=96)
class ItemInput(BaseModel):
 code:str=Field(min_length=1,max_length=64);label:str=Field(min_length=2,max_length=180);unit:str=Field(min_length=1,max_length=32)
 low_threshold:Decimal=Field(default=Decimal('0'),ge=0);location_id:UUID|None=None
class ItemUpdate(BaseModel):
 label:str=Field(min_length=2,max_length=180);unit:str=Field(min_length=1,max_length=32);low_threshold:Decimal=Field(ge=0);location_id:UUID|None=None;enabled:bool=True
def _audit_item(c,actor,action,item_id,data):
 from edusync.adapters.postgres_repositories import PostgresAuditRepository
 from edusync.modules.audit.domain.audit import AuditRecord
 PostgresAuditRepository(c).append(AuditRecord(action=action,entity_type='inventory_item',entity_id=item_id,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,new_data={k:str(v) if v is not None else None for k,v in data.items()}))
@router.post('/items',status_code=201)
def create_item(b:ItemInput,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """New consumable: stock always starts at 0 and only moves through traced movements (receipt/issue/count)."""
 need(actor,'inventory.stock.item.manage')
 if not (idempotency_key or '').strip():raise HTTPException(400,'Idempotency-Key obligatoire')
 def action(c):
  code=b.code.strip().upper()
  if c.execute(text('SELECT 1 FROM inventory_items WHERE school_id=:sid AND upper(code)=:c'),{'sid':str(actor.school_id),'c':code}).first():raise HTTPException(409,'Ce code article existe déjà')
  if b.location_id and not c.execute(text('SELECT 1 FROM inventory_locations WHERE id=:l AND school_id=:sid'),{'l':str(b.location_id),'sid':str(actor.school_id)}).first():raise HTTPException(404,'Local introuvable')
  row=c.execute(text("INSERT INTO inventory_items(school_id,code,label,item_kind,unit,low_threshold,location_id) VALUES(:sid,:c,:l,'CONSUMABLE',:u,:t,:loc) RETURNING id,code,label,unit,quantity,low_threshold,version"),
   {'sid':str(actor.school_id),'c':code,'l':b.label.strip(),'u':b.unit.strip(),'t':b.low_threshold,'loc':str(b.location_id) if b.location_id else None}).mappings().one()
  out={k:(str(v) if not isinstance(v,(int,str)) else v) for k,v in dict(row).items()}
  _audit_item(c,actor,'INVENTORY_ITEM_CREATED',row['id'],out);return 201,out
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   return IdempotentExecutor(PostgresIdempotencyRepository(c)).execute(scope_key=str(actor.school_id),idempotency_key=idempotency_key,operation='STEWARDSHIP_ITEM_CREATE',
     payload=b.model_dump(mode='json'),school_id=str(actor.school_id),actor_user_id=str(actor.user_id),action=lambda:action(c)).body
 except (IdempotencyConflict,IdempotencyInProgress) as e:raise HTTPException(409,str(e)) from e
@router.put('/items/{item_id}')
def update_item(item_id:UUID,b:ItemUpdate,if_match:str|None=Header(None,alias='If-Match'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """Edits the item card only; quantity is never writable here (movements own it)."""
 need(actor,'inventory.stock.item.manage')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  cur=c.execute(text('SELECT version FROM inventory_items WHERE id=:id AND school_id=:sid FOR UPDATE'),{'id':str(item_id),'sid':str(actor.school_id)}).scalar_one_or_none()
  if cur is None:raise HTTPException(404,'Article introuvable')
  if if_match is not None and if_match.strip('"')!=str(cur):raise HTTPException(409,'Article modifié par un autre utilisateur : rechargez')
  row=c.execute(text('UPDATE inventory_items SET label=:l,unit=:u,low_threshold=:t,location_id=:loc,enabled=:e,version=version+1,updated_at=now() WHERE id=:id AND school_id=:sid RETURNING id,code,label,unit,quantity,low_threshold,enabled,version'),
   {'l':b.label.strip(),'u':b.unit.strip(),'t':b.low_threshold,'loc':str(b.location_id) if b.location_id else None,'e':b.enabled,'id':str(item_id),'sid':str(actor.school_id)}).mappings().one()
  out={k:(str(v) if not isinstance(v,(int,str,bool)) else v) for k,v in dict(row).items()}
  _audit_item(c,actor,'INVENTORY_ITEM_UPDATED',item_id,out);return out
@router.post('/stock/movements',status_code=201)
def movement(b:Movement,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 cap={'RECEIPT':'inventory.stock.receive','ISSUE':'inventory.stock.issue','ADJUSTMENT':'inventory.stock.adjust'}[b.movement_type];need(actor,cap)
 delta=b.quantity if b.movement_type=='RECEIPT' else (-b.quantity if b.movement_type=='ISSUE' else (b.quantity if b.adjustment_direction=='INCREASE' else -b.quantity))
 if b.movement_type=='ADJUSTMENT' and b.adjustment_direction is None:raise HTTPException(422,'Précisez le sens de la correction de stock')
 if not (idempotency_key or '').strip():raise HTTPException(400,'Idempotency-Key obligatoire')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   # A network retry carrying the same key returns the first result instead of moving stock twice.
   return IdempotentExecutor(PostgresIdempotencyRepository(c)).execute(scope_key=str(actor.school_id),idempotency_key=idempotency_key,operation='STEWARDSHIP_STOCK_MOVEMENT',
     payload=b.model_dump(mode='json'),school_id=str(actor.school_id),actor_user_id=str(actor.user_id),action=lambda:(201,_apply_movement(c,actor,b,delta))).body
 except (IdempotencyConflict,IdempotencyInProgress) as e:raise HTTPException(409,str(e)) from e
def _apply_movement(c,actor,b,delta):
  cur=c.execute(text('SELECT quantity FROM inventory_items WHERE id=:id AND school_id=:sid FOR UPDATE'),{'id':str(b.item_id),'sid':str(actor.school_id)}).scalar_one_or_none()
  if cur is None:raise HTTPException(404,'Article introuvable')
  if Decimal(str(cur))+delta<0:raise HTTPException(409,'Stock insuffisant')
  c.execute(text('UPDATE inventory_items SET quantity=quantity+:d,version=version+1,updated_at=now() WHERE id=:id AND school_id=:sid'),{'d':delta,'id':str(b.item_id),'sid':str(actor.school_id)})
  c.execute(text("INSERT INTO inventory_item_movements(school_id,item_id,movement_type,quantity_delta,reason,destination,reference,actor_user_id) VALUES(:sid,:id,:t,:d,:r,:dest,:ref,:uid)"),{'sid':str(actor.school_id),'id':str(b.item_id),'t':b.movement_type,'d':delta,'r':b.reason,'dest':b.destination,'ref':b.reference,'uid':str(actor.user_id)})
  return {'ok':True,'quantity':str(Decimal(str(cur))+delta)}
@router.get('/stock/movements')
def movement_list(limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.stock.movements.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:p={'sid':str(actor.school_id),'limit':limit,'offset':offset}; items=rows(c,"SELECT m.*,i.label item_label,i.unit FROM inventory_item_movements m JOIN inventory_items i ON i.id=m.item_id WHERE m.school_id=:sid ORDER BY m.created_at DESC LIMIT :limit OFFSET :offset",p); total=c.execute(text("SELECT count(*) FROM inventory_item_movements WHERE school_id=:sid"),{'sid':str(actor.school_id)}).scalar_one(); return {'items':items,'total':int(total),'limit':limit,'offset':offset}
@router.get('/assets')
def assets(limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.assets.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:p={'sid':str(actor.school_id),'limit':limit,'offset':offset}; items=rows(c,"SELECT a.*,t.label asset_type,l.label location_label FROM inventory_assets a JOIN inventory_asset_types t ON t.id=a.asset_type_id LEFT JOIN inventory_locations l ON l.id=a.location_id WHERE a.school_id=:sid ORDER BY t.label,l.label LIMIT :limit OFFSET :offset",p); total=c.execute(text("SELECT count(*) FROM inventory_assets WHERE school_id=:sid"),{'sid':str(actor.school_id)}).scalar_one(); return {'items':items,'total':int(total),'limit':limit,'offset':offset}
@router.get('/locations')
def locations(limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.assets.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:p={'sid':str(actor.school_id),'limit':limit,'offset':offset}; items=rows(c,"SELECT * FROM inventory_locations WHERE school_id=:sid ORDER BY label LIMIT :limit OFFSET :offset",p); total=c.execute(text("SELECT count(*) FROM inventory_locations WHERE school_id=:sid"),{'sid':str(actor.school_id)}).scalar_one(); return {'items':items,'total':int(total),'limit':limit,'offset':offset}
@router.get('/sale-stock')
def sale_stock(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.stock.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:return {'items':rows(c,"SELECT p.id,p.code,p.label,p.currency,p.unit_price,p.version,coalesce(s.quantity,0) quantity,coalesce(s.low_threshold,0) low_threshold FROM school_products p LEFT JOIN inventory_stock s ON s.school_id=p.school_id AND s.product_id=p.id WHERE p.school_id=:sid AND p.enabled AND p.stock_tracking ORDER BY p.label",{'sid':str(actor.school_id)})}

class AssetInput(BaseModel): asset_type_id:UUID;tag:str|None=Field(None,max_length=96);quantity:int=Field(ge=1);location_id:UUID|None=None;status:Literal['GOOD','TO_REPAIR','IN_REPAIR','OUT_OF_SERVICE','LOST','DISPOSED']='GOOD';notes:str|None=Field(None,max_length=1000)
@router.post('/assets',status_code=201)
def asset_create(b:AssetInput,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.assets.create')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  if not c.execute(text('SELECT 1 FROM inventory_asset_types WHERE id=:id AND school_id=:sid AND enabled'),{'id':b.asset_type_id,'sid':actor.school_id}).first():raise HTTPException(404,'Type de bien introuvable')
  if b.location_id and not c.execute(text('SELECT 1 FROM inventory_locations WHERE id=:id AND school_id=:sid'),{'id':b.location_id,'sid':actor.school_id}).first():raise HTTPException(404,'Local introuvable')
  aid=c.execute(text("INSERT INTO inventory_assets(school_id,asset_type_id,asset_tag,quantity,location_id,status,notes) VALUES(:sid,:t,:tag,:q,:loc,:st,:n) RETURNING id"),{'sid':actor.school_id,'t':b.asset_type_id,'tag':b.tag,'q':b.quantity,'loc':b.location_id,'st':b.status,'n':b.notes}).scalar_one();c.execute(text("INSERT INTO inventory_asset_events(school_id,asset_id,event_type,to_status,to_location_id,reason,actor_user_id) VALUES(:sid,:id,'CREATE',:st,:loc,'Création du bien',:uid)"),{'sid':actor.school_id,'id':aid,'st':b.status,'loc':b.location_id,'uid':actor.user_id});return {'id':str(aid)}
class AssetEdit(BaseModel):
 tag:str|None=Field(None,max_length=96)
 notes:str|None=Field(None,max_length=1000)
 quantity:int=Field(ge=1)
 version:int=Field(ge=1)
@router.put('/assets/{asset_id}')
def asset_update(asset_id:UUID,b:AssetEdit,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.assets.update')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  old=c.execute(text('SELECT version,asset_tag,notes,quantity FROM inventory_assets WHERE id=:id AND school_id=:sid FOR UPDATE'),{'id':asset_id,'sid':actor.school_id}).mappings().first()
  if not old:raise HTTPException(404,'Bien introuvable')
  if int(old['version'])!=b.version:raise HTTPException(409,'Fiche modifiée entre-temps : actualisez les données')
  if old['asset_tag']==b.tag and old['notes']==b.notes and old['quantity']==b.quantity:return {'ok':True,'version':b.version}
  version=c.execute(text('UPDATE inventory_assets SET asset_tag=:tag,notes=:notes,quantity=:q,version=version+1,updated_at=now() WHERE id=:id AND school_id=:sid RETURNING version'),{'tag':b.tag,'notes':b.notes,'q':b.quantity,'id':asset_id,'sid':actor.school_id}).scalar_one()
  c.execute(text("INSERT INTO inventory_asset_events(school_id,asset_id,event_type,reason,actor_user_id) VALUES(:sid,:id,'STATUS',:reason,:uid)"),{'sid':actor.school_id,'id':asset_id,'reason':'Modification de la fiche patrimoniale (référence, quantité ou observations)','uid':actor.user_id})
  return {'ok':True,'version':version}

class AssetStatus(BaseModel):status:Literal['GOOD','TO_REPAIR','IN_REPAIR','OUT_OF_SERVICE','LOST','DISPOSED'];reason:str=Field(min_length=3,max_length=700);location_id:UUID|None=None
@router.post('/assets/{asset_id}/status')
def asset_status(asset_id:UUID,b:AssetStatus,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.assets.status.update')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  old=c.execute(text("SELECT status,location_id FROM inventory_assets WHERE id=:id AND school_id=:sid FOR UPDATE"),{'id':asset_id,'sid':actor.school_id}).mappings().first()
  if not old:raise HTTPException(404,'Bien introuvable')
  if b.location_id and not c.execute(text('SELECT 1 FROM inventory_locations WHERE id=:id AND school_id=:sid'),{'id':b.location_id,'sid':actor.school_id}).first():raise HTTPException(404,'Local introuvable')
  c.execute(text("UPDATE inventory_assets SET status=:st,location_id=coalesce(:loc,location_id),version=version+1,updated_at=now() WHERE id=:id AND school_id=:sid"),{'st':b.status,'loc':b.location_id,'id':asset_id,'sid':actor.school_id});c.execute(text("INSERT INTO inventory_asset_events(school_id,asset_id,event_type,from_status,to_status,from_location_id,to_location_id,reason,actor_user_id) VALUES(:sid,:id,'STATUS',:fs,:ts,:fl,coalesce(:tl,:fl),:r,:uid)"),{'sid':actor.school_id,'id':asset_id,'fs':old['status'],'ts':b.status,'fl':old['location_id'],'tl':b.location_id,'r':b.reason,'uid':actor.user_id});return {'ok':True}
class AssetRepair(BaseModel):
 reason:str=Field(min_length=3,max_length=700)
 completed:bool=False
@router.post('/assets/{asset_id}/repairs')
def asset_repair(asset_id:UUID,b:AssetRepair,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.assets.repair.record')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  old=c.execute(text('SELECT status,location_id FROM inventory_assets WHERE id=:id AND school_id=:sid FOR UPDATE'),{'id':asset_id,'sid':actor.school_id}).mappings().first()
  if not old:raise HTTPException(404,'Bien introuvable')
  if old['status'] in ('LOST','DISPOSED'):raise HTTPException(409,'Réparation impossible pour un bien perdu ou sorti du patrimoine')
  status='GOOD' if b.completed else 'IN_REPAIR'
  c.execute(text('UPDATE inventory_assets SET status=:st,version=version+1,updated_at=now() WHERE id=:id AND school_id=:sid'),{'st':status,'id':asset_id,'sid':actor.school_id})
  c.execute(text("INSERT INTO inventory_asset_events(school_id,asset_id,event_type,from_status,to_status,from_location_id,to_location_id,reason,actor_user_id) VALUES(:sid,:id,'REPAIR',:fs,:ts,:loc,:loc,:r,:uid)"),{'sid':actor.school_id,'id':asset_id,'fs':old['status'],'ts':status,'loc':old['location_id'],'r':b.reason.strip(),'uid':actor.user_id})
  return {'ok':True,'status':status}

@router.get('/assets/{asset_id}/history')
def asset_history(asset_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.assets.history.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  exists=c.execute(text('SELECT 1 FROM inventory_assets WHERE id=:id AND school_id=:sid'),{'id':asset_id,'sid':actor.school_id}).first()
  if not exists:raise HTTPException(404,'Bien introuvable')
  return {'items':rows(c,"SELECT * FROM inventory_asset_events WHERE school_id=:sid AND asset_id=:id ORDER BY created_at DESC",{'sid':str(actor.school_id),'id':str(asset_id)})}
class CountInput(BaseModel):notes:str|None=Field(None,max_length=1000)
@router.post('/counts',status_code=201)
def count_create(b:CountInput,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.counts.create')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  cid=c.execute(text("INSERT INTO inventory_counts(school_id,code,counted_on,status,notes,created_by_user_id) VALUES(:sid,'INV-'||to_char(clock_timestamp(),'YYYYMMDD-HH24MISSMS'),current_date,'DRAFT',:n,:uid) RETURNING id"),{'sid':actor.school_id,'n':b.notes,'uid':actor.user_id}).scalar_one();return {'id':str(cid)}
class CountLine(BaseModel):item_id:UUID;counted_quantity:Decimal=Field(ge=0);reason:str|None=Field(None,max_length=700)
@router.post('/counts/{count_id}/lines')
def count_line(count_id:UUID,b:CountLine,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.counts.record')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  state=c.execute(text("SELECT status FROM inventory_counts WHERE id=:cid AND school_id=:sid FOR UPDATE"),{'cid':count_id,'sid':actor.school_id}).scalar_one_or_none()
  if state is None:raise HTTPException(404,'Inventaire introuvable')
  if state!='DRAFT':raise HTTPException(409,'Inventaire validé : il ne peut plus être modifié')
  theoretical=c.execute(text("SELECT quantity FROM inventory_items WHERE id=:id AND school_id=:sid"),{'id':b.item_id,'sid':actor.school_id}).scalar_one_or_none()
  if theoretical is None:raise HTTPException(404,'Article introuvable')
  if b.counted_quantity!=Decimal(str(theoretical)) and not (b.reason or '').strip():raise HTTPException(422,'Justification requise pour chaque écart')
  c.execute(text("INSERT INTO inventory_count_lines(count_id,school_id,item_id,theoretical_quantity,counted_quantity,reason) VALUES(:cid,:sid,:iid,:t,:c,:r) ON CONFLICT(count_id,item_id) DO UPDATE SET counted_quantity=excluded.counted_quantity,reason=excluded.reason"),{'cid':count_id,'sid':actor.school_id,'iid':b.item_id,'t':theoretical,'c':b.counted_quantity,'r':b.reason});return {'variance':str(b.counted_quantity-Decimal(str(theoretical)))}
@router.post('/counts/{count_id}/validate')
def count_validate(count_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.counts.validate')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  state=c.execute(text("SELECT status FROM inventory_counts WHERE id=:cid AND school_id=:sid FOR UPDATE"),{'cid':count_id,'sid':actor.school_id}).scalar_one_or_none()
  if state is None:raise HTTPException(404,'Inventaire introuvable')
  if state!='DRAFT':raise HTTPException(409,'Cet inventaire est déjà validé')
  lines=c.execute(text("SELECT item_id,theoretical_quantity,counted_quantity,reason FROM inventory_count_lines WHERE count_id=:cid AND school_id=:sid"),{'cid':count_id,'sid':actor.school_id}).mappings().all()
  if not lines:raise HTTPException(422,'Aucun comptage à valider')
  for x in lines:
   delta=Decimal(str(x['counted_quantity']))-Decimal(str(x['theoretical_quantity']))
   if delta and not (x['reason'] or '').strip():raise HTTPException(422,'Justification requise pour chaque écart')
   if delta:
    # Apply the variance observed at count time to the CURRENT stock: movements recorded between counting
    # and validation are preserved, and the movement ledger keeps summing to the quantity.
    current=c.execute(text("SELECT quantity FROM inventory_items WHERE id=:id AND school_id=:sid FOR UPDATE"),{'id':x['item_id'],'sid':actor.school_id}).scalar_one()
    if Decimal(str(current))+delta<0:raise HTTPException(409,'Écart incompatible avec le stock actuel : recomptez cet article')
    c.execute(text("UPDATE inventory_items SET quantity=quantity+:d,version=version+1,updated_at=now() WHERE id=:id AND school_id=:sid"),{'d':delta,'id':x['item_id'],'sid':actor.school_id});c.execute(text("INSERT INTO inventory_item_movements(school_id,item_id,movement_type,quantity_delta,reason,reference,actor_user_id) VALUES(:sid,:id,'COUNT_ADJUSTMENT',:d,:r,:ref,:uid)"),{'sid':actor.school_id,'id':x['item_id'],'d':delta,'r':x['reason'],'ref':str(count_id),'uid':actor.user_id})
  c.execute(text("UPDATE inventory_counts SET status='VALIDATED',validated_by_user_id=:uid,validated_at=now() WHERE id=:cid AND school_id=:sid AND status='DRAFT'"),{'uid':actor.user_id,'cid':count_id,'sid':actor.school_id});return {'status':'VALIDATED'}


@router.get('/asset-types')
def asset_types(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 if not ({'inventory.assets.read','inventory.assets.create'} & set(actor.permissions)):raise HTTPException(403,'Permission patrimoine requise')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:return {'items':rows(c,"SELECT id,code,label,unit,enabled FROM inventory_asset_types WHERE school_id=:sid AND enabled ORDER BY label",{'sid':str(actor.school_id)})}

@router.get('/counts')
def count_list(limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.counts.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:return {'items':rows(c,"SELECT c.id,c.code,c.counted_on,c.status,c.notes,c.created_at,c.validated_at,count(l.id) line_count,coalesce(sum(abs(l.counted_quantity-l.theoretical_quantity)),0) total_variance FROM inventory_counts c LEFT JOIN inventory_count_lines l ON l.count_id=c.id AND l.school_id=c.school_id WHERE c.school_id=:sid GROUP BY c.id ORDER BY c.created_at DESC LIMIT :limit OFFSET :offset",{'sid':str(actor.school_id),'limit':limit,'offset':offset}), 'limit':limit,'offset':offset}

@router.get('/counts/{count_id}')
def count_detail(count_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'inventory.counts.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  head=c.execute(text("SELECT id,code,counted_on,status,notes,created_at,validated_at FROM inventory_counts WHERE id=:id AND school_id=:sid"),{'id':count_id,'sid':actor.school_id}).mappings().first()
  if not head:raise HTTPException(404,'Inventaire introuvable')
  lines=rows(c,"SELECT l.*,i.code item_code,i.label item_label,i.unit,(l.counted_quantity-l.theoretical_quantity) variance FROM inventory_count_lines l JOIN inventory_items i ON i.id=l.item_id WHERE l.count_id=:id AND l.school_id=:sid ORDER BY i.label",{'id':str(count_id),'sid':str(actor.school_id)})
  return {'count':dict(head),'items':lines}
