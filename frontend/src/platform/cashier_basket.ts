/** Cashier draft only. Server balances and priority rules are rechecked before payment. */
export type CashierBasketLine={enrollment_id:string;family_id:string;child:string;charge_ids:string[];labels:string[];amount:string;currency:'CDF'|'USD'};
const PREFIX='edusync.cashier-basket.';
const MAX_AGE_MS=24*60*60*1000;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function key(token:string):string|null{
 try{const part=token.split('.')[1];const claims=JSON.parse(atob(part.replace(/-/g,'+').replace(/_/g,'/')));
  return UUID.test(claims.sub)&&UUID.test(claims.school_id)?`${PREFIX}${claims.school_id}.${claims.sub}`:null;
 }catch{return null}
}
export function loadCashierBasket(token:string):CashierBasketLine[]{
 const k=key(token);if(!k)return [];
 try{const raw=localStorage.getItem(k);if(!raw)return [];const draft=JSON.parse(raw);
  if(!Number.isFinite(draft.saved_at)||Date.now()-draft.saved_at>MAX_AGE_MS||draft.saved_at>Date.now()+60000){localStorage.removeItem(k);return []}
  if(!Array.isArray(draft.lines)||draft.lines.length>20)return [];
  const lines=draft.lines.filter((l:CashierBasketLine)=>UUID.test(l.enrollment_id)&&UUID.test(l.family_id)
   &&Array.isArray(l.charge_ids)&&l.charge_ids.length>0&&l.charge_ids.length<=24&&l.charge_ids.every(id=>UUID.test(id))
   &&['CDF','USD'].includes(l.currency)&&Number.isFinite(Number(l.amount))&&Number(l.amount)>0
   &&typeof l.child==='string'&&l.child.length<=160&&Array.isArray(l.labels));
  return lines.length===draft.lines.length?lines:[];
 }catch{return []}
}
export function saveCashierBasket(token:string,lines:CashierBasketLine[]):void{
 const k=key(token);if(!k)return;
 try{if(lines.length)localStorage.setItem(k,JSON.stringify({saved_at:Date.now(),lines}));else localStorage.removeItem(k)}catch{/* Storage blocked: basket stays in memory. */}
}
export type CashierBasketRequest={signature:string;key:string};
function requestStorageKey(token:string):string|null{
 const basketKey=key(token);
 return basketKey?basketKey+'.request':null;
}
export function loadCashierBasketRequest(token:string):CashierBasketRequest|null{
 const storageKey=requestStorageKey(token);if(!storageKey)return null;
 try{
  // A completed payment clears the draft. A remaining key without a draft must never be reused.
  if(!loadCashierBasket(token).length){localStorage.removeItem(storageKey);return null}
  const raw=localStorage.getItem(storageKey);if(!raw)return null;
  const record=JSON.parse(raw);
  if(!Number.isFinite(record.saved_at)||Date.now()-record.saved_at>MAX_AGE_MS||record.saved_at>Date.now()+60000
   ||typeof record.signature!=='string'||record.signature.length>100000||!UUID.test(record.key)){
   localStorage.removeItem(storageKey);return null;
  }
  return {signature:record.signature,key:record.key};
 }catch{return null}
}
export function saveCashierBasketRequest(token:string,request:CashierBasketRequest|null):void{
 const storageKey=requestStorageKey(token);if(!storageKey)return;
 try{if(request)localStorage.setItem(storageKey,JSON.stringify({...request,saved_at:Date.now()}));
  else localStorage.removeItem(storageKey)}catch{/* Storage blocked: the current session still keeps the key. */}
}
export function clearAllCashierBaskets():void{
 try{for(let i=localStorage.length-1;i>=0;i--){const k=localStorage.key(i);if(k?.startsWith(PREFIX))localStorage.removeItem(k)}}catch{/* Storage blocked. */}
}
