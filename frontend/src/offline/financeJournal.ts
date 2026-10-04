export type FinanceOfflineScope={schoolId:string;userId:string;deviceId:string;leaseId:string};
export type FinanceAllocation={chargeId:string;amount:string};
export type OfflineChargeSnapshotLocal={chargeId:string;enrollmentId:string;studentId:string;currency:'CDF'|'USD';remainingAmount:string;version:number};
export type OfflineReceiptToken={id:string;receiptNo:string;status:'AVAILABLE'|'CONSUMED'|'VOID'};
export type OfflineLeaseLocal={
  key:string;
  schoolId:string;
  userId:string;
  deviceId:string;
  leaseId:string;
  cashSessionId:string;
  status:'ACTIVE'|'DRAINING'|'CLOSED'|'FORCE_RELEASED';
  protocolVersion?:'AUTHORIZED_PARTITIONED_CASH_V2'|'EXCLUSIVE_SINGLE_WRITER_CASH_V1';
  localStopAt:string;
  maxPayments:number;
  maxCdf:string;
  maxUsd:string;
};
export type OfflineCashPayment={
  id:string;
  operationId:string;
  idempotencyKey:string;
  schoolId:string;
  leaseId:string;
  deviceId:string;
  cashierUserId:string;
  cashSessionId:string;
  studentId:string;
  enrollmentId:string;
  currency:'CDF'|'USD';
  amount:string;
  mode:'CASH';
  receiptTokenId:string;
  receiptNo:string;
  allocations:FinanceAllocation[];
  journalSeq:number;
  clientTime:string;
  previousEntryHash:string|null;
  entryHash:string;
  syncStatus:'PENDING'|'SYNCED';
};

const DB='edusync-finance-offline-v1';
const JOURNAL='journal';
const META='meta';
const TOKENS='receiptTokens';
const SNAPSHOTS='chargeSnapshots';
const VERSION=2;
const scopeKey=(s:FinanceOfflineScope)=>`${s.schoolId}:${s.userId}:${s.deviceId}:${s.leaseId}`;

function openDb():Promise<IDBDatabase>{
  return new Promise((resolve,reject)=>{
    const req=indexedDB.open(DB,VERSION);
    req.onupgradeneeded=()=>{
      const db=req.result;
      const journal=db.objectStoreNames.contains(JOURNAL)
        ? req.transaction!.objectStore(JOURNAL)
        : db.createObjectStore(JOURNAL,{keyPath:'id'});
      if(!journal.indexNames.contains('scope')) journal.createIndex('scope',['schoolId','cashierUserId','deviceId','leaseId'],{unique:false});
      if(!journal.indexNames.contains('operation')) journal.createIndex('operation',['schoolId','operationId'],{unique:true});
      if(!journal.indexNames.contains('idempotency')) journal.createIndex('idempotency',['schoolId','idempotencyKey'],{unique:true});
      if(!journal.indexNames.contains('receipt')) journal.createIndex('receipt',['schoolId','receiptNo'],{unique:true});
      if(!journal.indexNames.contains('sequence')) journal.createIndex('sequence',['leaseId','journalSeq'],{unique:true});
      if(!db.objectStoreNames.contains(META)) db.createObjectStore(META,{keyPath:'key'});
      if(!db.objectStoreNames.contains(TOKENS)){
        const tokens=db.createObjectStore(TOKENS,{keyPath:'id'});
        tokens.createIndex('receipt',['schoolId','receiptNo'],{unique:true});
        tokens.createIndex('lease',['leaseId','status'],{unique:false});
      }
      if(!db.objectStoreNames.contains(SNAPSHOTS)){
        const snaps=db.createObjectStore(SNAPSHOTS,{keyPath:'id'});
        snaps.createIndex('lease',['leaseId','studentId','enrollmentId'],{unique:false});
        snaps.createIndex('leaseOnly','leaseId',{unique:false});
        snaps.createIndex('charge',['leaseId','chargeId'],{unique:true});
      }
    };
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error);
  });
}

function canonicalJson(value:unknown):string{
  if(value===null || typeof value!=='object') return JSON.stringify(value);
  if(Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  const obj=value as Record<string,unknown>;
  return `{${Object.keys(obj).sort().map(k=>`${JSON.stringify(k)}:${canonicalJson(obj[k])}`).join(',')}}`;
}

async function sha256Hex(text:string):Promise<string>{
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
}

function minorUnits(value:string):bigint{
  const v=value.trim();
  if(!/^\d+(?:\.\d{1,2})?$/.test(v)) throw new Error('Montant monétaire invalide');
  const [whole,frac='']=v.split('.');
  return BigInt(whole)*100n+BigInt((frac+'00').slice(0,2));
}

function normalizeMoney(value:string):string{
  const cents=minorUnits(value);
  const whole=cents/100n;
  const frac=(cents%100n).toString().padStart(2,'0');
  return `${whole}.${frac}`;
}
function moneyFromMinor(cents:bigint):string{
  return `${cents/100n}.${(cents%100n).toString().padStart(2,'0')}`;
}

export async function ensureDurableStorage():Promise<void>{
  if(!navigator.storage?.persisted || !navigator.storage?.persist)
    throw new Error('Ce navigateur ne permet pas de garantir le stockage persistant requis pour la caisse offline');
  if(!('locks' in navigator) || !(navigator as Navigator & {locks?:LockManager}).locks?.request)
    throw new Error('Web Locks indisponible: ce navigateur ne peut pas garantir une écriture de caisse locale sérialisée');
  if(!globalThis.crypto?.subtle) throw new Error('WebCrypto indisponible: intégrité Finance offline non garantie');
  if(await navigator.storage.persisted()) return;
  if(!(await navigator.storage.persist()))
    throw new Error('Stockage persistant refusé: encaissement offline désactivé sur cet appareil');
}

async function withFinanceWriteLock<T>(scope:FinanceOfflineScope,fn:()=>Promise<T>):Promise<T>{
  const manager=(navigator as Navigator & {locks?:LockManager}).locks;
  if(!manager?.request) throw new Error('Web Locks requis pour l’encaissement offline');
  return manager.request(`edusync:finance:${scopeKey(scope)}`,{mode:'exclusive'},fn);
}

export async function armLeaseLocally(
  lease:Omit<OfflineLeaseLocal,'key'>,
  tokens:OfflineReceiptToken[],
  snapshots:OfflineChargeSnapshotLocal[]
):Promise<void>{
  await ensureDurableStorage();
  if(lease.status!=='ACTIVE') throw new Error('Seul un lease ACTIVE peut armer la caisse offline');
  if(Date.parse(lease.localStopAt)<=Date.now()) throw new Error('Fenêtre offline déjà expirée');
  if(tokens.length<1) throw new Error('Aucun reçu préalloué disponible');
  if(snapshots.length<1) throw new Error('Aucune charge figée: caisse offline non activable');
  const usableTokens=tokens.filter(x=>x.status==='AVAILABLE');
  if(usableTokens.length<1) throw new Error('Aucun reçu AVAILABLE pour cette caisse offline');
  if(new Set(usableTokens.map(x=>x.id)).size!==usableTokens.length || new Set(usableTokens.map(x=>x.receiptNo)).size!==usableTokens.length)
    throw new Error('Doublon dans les reçus préalloués');
  for(const snap of snapshots){
    if(snap.version<1 || minorUnits(snap.remainingAmount)<0n) throw new Error('Snapshot financier invalide');
  }
  if(new Set(snapshots.map(x=>x.chargeId)).size!==snapshots.length) throw new Error('Charge snapshot dupliquée');
  const db=await openDb();
  const scope:FinanceOfflineScope={schoolId:lease.schoolId,userId:lease.userId,deviceId:lease.deviceId,leaseId:lease.leaseId};
  await new Promise<void>((resolve,reject)=>{
    const tx=db.transaction([META,TOKENS,SNAPSHOTS],'readwrite');
    tx.objectStore(META).put({...lease,key:`lease:${scopeKey(scope)}`});
    tx.objectStore(META).put({key:`lastHash:${scopeKey(scope)}`,value:null});
    tx.objectStore(META).put({key:`nextSeq:${scopeKey(scope)}`,value:1});
    for(const token of usableTokens){
      tx.objectStore(TOKENS).add({...token,schoolId:lease.schoolId,leaseId:lease.leaseId});
    }
    for(const snap of snapshots){
      tx.objectStore(SNAPSHOTS).add({...snap,id:`${lease.leaseId}:${snap.chargeId}`,leaseId:lease.leaseId,schoolId:lease.schoolId,remainingAmount:normalizeMoney(snap.remainingAmount)});
    }
    tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error); tx.onabort=()=>reject(tx.error);
  });
}

async function readLease(db:IDBDatabase,scope:FinanceOfflineScope):Promise<OfflineLeaseLocal>{
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(META,'readonly');
    const req=tx.objectStore(META).get(`lease:${scopeKey(scope)}`);
    req.onsuccess=()=>req.result?resolve(req.result as OfflineLeaseLocal):reject(new Error('Lease offline local introuvable'));
    req.onerror=()=>reject(req.error);
  });
}

async function journalRows(db:IDBDatabase,scope:FinanceOfflineScope):Promise<OfflineCashPayment[]>{
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(JOURNAL,'readonly');
    const req=tx.objectStore(JOURNAL).index('scope').getAll([scope.schoolId,scope.userId,scope.deviceId,scope.leaseId]);
    req.onsuccess=()=>resolve((req.result as OfflineCashPayment[]).sort((a,b)=>a.journalSeq-b.journalSeq));
    req.onerror=()=>reject(req.error);
  });
}

async function chargeSnapshots(db:IDBDatabase,scope:FinanceOfflineScope):Promise<any[]>{
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(SNAPSHOTS,'readonly');
    const req=tx.objectStore(SNAPSHOTS).index('leaseOnly').getAll(scope.leaseId);
    req.onsuccess=()=>resolve((req.result as any[]).filter(x=>x.schoolId===scope.schoolId));
    req.onerror=()=>reject(req.error);
  });
}

function assertAllocationsAgainstFrozenBalances(scope:FinanceOfflineScope,rows:OfflineCashPayment[],snaps:any[],input:any){
  const byId=new Map(snaps.map(x=>[x.chargeId,x]));
  const already=new Map<string,bigint>();
  for(const row of rows) for(const a of row.allocations) already.set(a.chargeId,(already.get(a.chargeId)??0n)+minorUnits(a.amount));
  for(const a of input.allocations){
    const snap=byId.get(a.chargeId);
    if(!snap) throw new Error('Charge absente du snapshot offline');
    if(snap.studentId!==input.studentId||snap.enrollmentId!==input.enrollmentId||snap.currency!==input.currency)
      throw new Error('Allocation vers une autre inscription/devise interdite');
    const projected=(already.get(a.chargeId)??0n)+minorUnits(a.amount);
    if(projected>minorUnits(snap.remainingAmount)) throw new Error('Montant cumulé supérieur au solde figé de la charge');
  }
}

function assertLimits(lease:OfflineLeaseLocal,rows:OfflineCashPayment[],currency:'CDF'|'USD',amount:string){
  if(rows.length+1>lease.maxPayments) throw new Error('Nombre maximal de paiements offline atteint');
  const sum=(cur:'CDF'|'USD')=>rows.filter(x=>x.currency===cur).reduce((a,x)=>a+minorUnits(x.amount),0n);
  const projected=sum(currency)+minorUnits(amount);
  const limit=minorUnits(currency==='CDF'?lease.maxCdf:lease.maxUsd);
  if(projected>limit) throw new Error(`Plafond ${currency} offline dépassé`);
}

export async function appendCashPayment(
  scope:FinanceOfflineScope,
  input:Omit<OfflineCashPayment,'id'|'journalSeq'|'previousEntryHash'|'entryHash'|'syncStatus'>
):Promise<OfflineCashPayment>{
  return withFinanceWriteLock(scope,()=>appendCashPaymentLocked(scope,input));
}

async function appendCashPaymentLocked(
  scope:FinanceOfflineScope,
  input:Omit<OfflineCashPayment,'id'|'journalSeq'|'previousEntryHash'|'entryHash'|'syncStatus'>
):Promise<OfflineCashPayment>{
  if(input.mode!=='CASH') throw new Error('Le protocole Finance offline V2 autorise uniquement CASH en finalité locale');
  if(input.schoolId!==scope.schoolId||input.cashierUserId!==scope.userId||input.deviceId!==scope.deviceId||input.leaseId!==scope.leaseId)
    throw new Error('Contexte de caisse offline incohérent');
  if(!input.operationId||!input.idempotencyKey?.trim()||input.idempotencyKey.length>180||!input.receiptNo?.trim())
    throw new Error('Identité idempotente/reçu obligatoire');
  if(input.allocations.length<1) throw new Error('Au moins une allocation exacte est requise');
  if(new Set(input.allocations.map(x=>x.chargeId)).size!==input.allocations.length) throw new Error('Charge dupliquée dans le paiement');
  if(minorUnits(input.amount)<=0n || input.allocations.some(x=>minorUnits(x.amount)<=0n)) throw new Error('Montants strictement positifs requis');
  const allocationTotal=input.allocations.reduce((a,x)=>a+minorUnits(x.amount),0n);
  if(allocationTotal!==minorUnits(input.amount)) throw new Error('Allocations différentes du montant encaissé');
  const db=await openDb();
  const lease=await readLease(db,scope);
  if(lease.status!=='ACTIVE') throw new Error('La caisse offline n’accepte plus de nouveaux paiements');
  if(Date.now()>Date.parse(lease.localStopAt)) throw new Error('Fenêtre offline terminée: synchronisez la caisse');
  const rows=await journalRows(db,scope);
  const snaps=await chargeSnapshots(db,scope);
  assertLimits(lease,rows,input.currency,input.amount);
  assertAllocationsAgainstFrozenBalances(scope,rows,snaps,input);
  const state=await new Promise<{previous:string|null;seq:number;token:any}>((resolve,reject)=>{
    const tx=db.transaction([META,TOKENS],'readonly');
    const h=tx.objectStore(META).get(`lastHash:${scopeKey(scope)}`);
    const q=tx.objectStore(META).get(`nextSeq:${scopeKey(scope)}`);
    const t=tx.objectStore(TOKENS).get(input.receiptTokenId);
    tx.oncomplete=()=>resolve({previous:h.result?.value??null,seq:q.result?.value??1,token:t.result});
    tx.onerror=()=>reject(tx.error);
  });
  if(!state.token || state.token.leaseId!==scope.leaseId || state.token.schoolId!==scope.schoolId)
    throw new Error('Jeton de reçu étranger à cette caisse offline');
  if(state.token.status!=='AVAILABLE' || state.token.receiptNo!==input.receiptNo)
    throw new Error('Jeton de reçu déjà utilisé ou numéro incohérent');
  const clientTime=new Date(input.clientTime || new Date().toISOString()).toISOString();
  const normalizedAmount=normalizeMoney(input.amount);
  const normalizedAllocations=input.allocations.map(x=>({chargeId:x.chargeId,amount:normalizeMoney(x.amount)}));
  const base={
    school_id:input.schoolId,lease_id:input.leaseId,device_id:input.deviceId,cashier_user_id:input.cashierUserId,
    cash_session_id:input.cashSessionId,student_id:input.studentId,enrollment_id:input.enrollmentId,currency:input.currency,
    amount:normalizedAmount,receipt_token_id:input.receiptTokenId,receipt_no:input.receiptNo,journal_seq:state.seq,
    allocations:[...normalizedAllocations].sort((a,b)=>a.chargeId.localeCompare(b.chargeId)).map(x=>({charge_id:x.chargeId,amount:x.amount})),
    operation_id:input.operationId,idempotency_key:input.idempotencyKey,mode:'CASH',client_time:clientTime,
    previous_entry_hash:state.previous
  };
  const entryHash=await sha256Hex(canonicalJson(base));
  const row:OfflineCashPayment={...input,amount:normalizedAmount,allocations:normalizedAllocations,clientTime,id:input.operationId,journalSeq:state.seq,previousEntryHash:state.previous,entryHash,syncStatus:'PENDING'};
  await new Promise<void>((resolve,reject)=>{
    const tx=db.transaction([JOURNAL,META,TOKENS],'readwrite');
    tx.objectStore(JOURNAL).add(row); // immutable money append; duplicate op/key/receipt/seq aborts transaction.
    tx.objectStore(META).put({key:`lastHash:${scopeKey(scope)}`,value:entryHash});
    tx.objectStore(META).put({key:`nextSeq:${scopeKey(scope)}`,value:state.seq+1});
    tx.objectStore(TOKENS).put({...state.token,status:'CONSUMED',consumedByOperationId:input.operationId});
    tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error); tx.onabort=()=>reject(tx.error);
  });
  return row;
}

export async function allCashPayments(scope:FinanceOfflineScope):Promise<OfflineCashPayment[]>{
  const db=await openDb();
  return journalRows(db,scope);
}

export async function pendingCashPayments(scope:FinanceOfflineScope):Promise<OfflineCashPayment[]>{
  const db=await openDb();
  return (await journalRows(db,scope)).filter(x=>x.syncStatus==='PENDING');
}

export async function markSynced(scope:FinanceOfflineScope,operationId:string):Promise<void>{
  const db=await openDb();
  await new Promise<void>((resolve,reject)=>{
    const tx=db.transaction(JOURNAL,'readwrite');
    const store=tx.objectStore(JOURNAL);
    const req=store.get(operationId);
    req.onsuccess=()=>{
      const row=req.result as OfflineCashPayment|undefined;
      if(!row) return;
      if(row.schoolId!==scope.schoolId||row.cashierUserId!==scope.userId||row.deviceId!==scope.deviceId||row.leaseId!==scope.leaseId)
        throw new Error('Tentative de modifier un journal d’une autre caisse');
      store.put({...row,syncStatus:'SYNCED'}); // financial fields remain immutable; only sync status changes.
    };
    tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error); tx.onabort=()=>reject(tx.error);
  });
}

export async function localReconciliation(scope:FinanceOfflineScope){
  const db=await openDb();
  const rows=await journalRows(db,scope);
  return {
    expectedCount:rows.length,
    expectedCdf:moneyFromMinor(rows.filter(x=>x.currency==='CDF').reduce((a,x)=>a+minorUnits(x.amount),0n)),
    expectedUsd:moneyFromMinor(rows.filter(x=>x.currency==='USD').reduce((a,x)=>a+minorUnits(x.amount),0n)),
    totalsAreMinorUnits:false,
    finalEntryHash:rows.length?rows[rows.length-1].entryHash:null,
  };
}
