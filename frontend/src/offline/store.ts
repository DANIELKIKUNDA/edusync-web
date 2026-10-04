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
const VERSION=1;
const scopeKey=(s:OfflineScope)=>`${s.schoolId}:${s.userId}:${s.deviceId}`;

function openDb():Promise<IDBDatabase>{
  return new Promise((resolve,reject)=>{
    const req=indexedDB.open(DB,VERSION);
    req.onupgradeneeded=()=>{
      const db=req.result;
      const store=db.objectStoreNames.contains(STORE)
        ? req.transaction!.objectStore(STORE)
        : db.createObjectStore(STORE,{keyPath:'id'});
      if(!store.indexNames.contains('scope')) store.createIndex('scope',['schoolId','userId','deviceId'],{unique:false});
      if(!store.indexNames.contains('idempotencyKey')) store.createIndex('idempotencyKey',['schoolId','idempotencyKey'],{unique:true});
    };
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error);
  });
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
