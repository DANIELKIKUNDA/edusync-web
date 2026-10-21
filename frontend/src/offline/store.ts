export type OfflineScope={schoolId:string;userId:string;deviceId:string};
export type OfflineOperation={
  id:string;
  operationId:string;
  schoolId:string;
  userId:string;
  deviceId:string;
  operationType:string;
  aggregateType:string;
  aggregateId:string;
  payload:unknown;
  idempotencyKey:string;
  baseVersion?:number|null;
  createdAt:string;
};

const DB='edusync-local-web0c';
const STORE='outbox';
const VERSION=2;
const READS='platform_reads';
const scopeKey=(s:OfflineScope)=>`${s.schoolId}:${s.userId}:${s.deviceId}`;

function openDb():Promise<IDBDatabase>{
  return new Promise((resolve,reject)=>{
    const req=indexedDB.open(DB,VERSION);
    req.onupgradeneeded=()=>{
      const db=req.result;
      if(!db.objectStoreNames.contains(READS)) db.createObjectStore(READS,{keyPath:'key'});
      const store=db.objectStoreNames.contains(STORE)
        ? req.transaction!.objectStore(STORE)
        : db.createObjectStore(STORE,{keyPath:'id'});
      if(!store.indexNames.contains('scope')) store.createIndex('scope',['schoolId','userId','deviceId'],{unique:false});
      if(!store.indexNames.contains('idempotencyKey')) store.createIndex('idempotencyKey',['schoolId','idempotencyKey'],{unique:true});
    };
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error);
    req.onblocked=()=>reject(new Error('Fermez les autres onglets EduSync pour actualiser le cache local.'));
    req.addEventListener('success',()=>{req.result.onversionchange=()=>req.result.close();});
  });
}

// Read-only platform snapshots share the existing IndexedDB infrastructure, but
// never the school mutation outbox. A per-browser-session namespace isolates
// identities and is discarded on logout/space change. No token is stored here.
export async function platformSnapshot(scope:string, path:string, value?:string):Promise<{body:string;at:number}|null>{
  const db=await openDb();
  try{return await new Promise((resolve,reject)=>{
    const tx=db.transaction(READS,value===undefined?'readonly':'readwrite');
    const store=tx.objectStore(READS), key=`${scope}:${path}`;
    let result:{body:string;at:number}|null=null;
    if(value===undefined){const get=store.get(key);get.onsuccess=()=>{result=get.result||null};}
    else {
      store.put({key,scope,body:value,at:Date.now()});
      // Keep at most 40 already-read responses per browser session.
      const all=store.getAll();all.onsuccess=()=>{const entries=all.result.sort((a,b)=>b.at-a.at);entries.slice(40).forEach(x=>store.delete(x.key));};
    }
    tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
  })}finally{db.close()}
}

export async function clearPlatformSnapshots(){
  const db=await openDb();
  try{await new Promise<void>((resolve,reject)=>{const tx=db.transaction(READS,'readwrite');tx.objectStore(READS).clear();tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);})}finally{db.close()}
}

export async function queueOperation(op:OfflineOperation){
  if(!op.schoolId||!op.userId||!op.deviceId||!op.idempotencyKey||!op.operationId) throw new Error('Contexte offline incomplet');
  const db=await openDb();
  await new Promise<void>((resolve,reject)=>{
    const tx=db.transaction(STORE,'readwrite');
    tx.objectStore(STORE).add(op); // add, never put: duplicate IDs/keys fail closed.
    tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error);
  });
}

export async function pendingOperations(scope:OfflineScope):Promise<OfflineOperation[]>{
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(STORE,'readonly');
    const req=tx.objectStore(STORE).index('scope').getAll([scope.schoolId,scope.userId,scope.deviceId]);
    req.onsuccess=()=>resolve((req.result as OfflineOperation[]).sort((a,b)=>a.createdAt.localeCompare(b.createdAt)));
    req.onerror=()=>reject(req.error);
  });
}

export async function removeOperation(scope:OfflineScope,id:string):Promise<void>{
  const db=await openDb();
  await new Promise<void>((resolve,reject)=>{
    const tx=db.transaction(STORE,'readwrite');
    const store=tx.objectStore(STORE);
    const get=store.get(id);
    get.onsuccess=()=>{
      const op=get.result as OfflineOperation|undefined;
      if(op && scopeKey(op)===scopeKey(scope)) store.delete(id);
    };
    tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error);
  });
}
