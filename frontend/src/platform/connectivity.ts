import {cachedPlatformRead, cacheablePath, getPlatformAuthState, knownContext, rememberPlatformRead, setPlatformAuthState} from './offline_session';
import {UserFacingError} from './errors';
import {applyLocalPayment, enqueueWrite, loadPack, offlineWriteKind, searchPack} from '../offline/outbox';
export type ConnectivityState='ONLINE'|'DEGRADED'|'SUSPECTED_OFFLINE'|'OFFLINE'|'RECOVERING';
type Snapshot={state:ConnectivityState;failures:number;successes:number;since:number;lastSuccess?:number;lastFailure?:number};
export const nativeFetch=globalThis.fetch.bind(globalThis);let snap:Snapshot={state:'ONLINE',failures:0,successes:0,since:Date.now(),lastSuccess:Date.now()};
const listeners=new Set<(s:Snapshot)=>void>();
function publish(next:Snapshot){snap=next;listeners.forEach(fn=>fn({...snap}));window.dispatchEvent(new CustomEvent('edusync:connectivity',{detail:snap}))}
function success(){const now=Date.now();const recovering=snap.state==='OFFLINE'||snap.state==='SUSPECTED_OFFLINE'||snap.state==='RECOVERING';const successes=recovering?snap.successes+1:Math.min(snap.successes+1,3);const state:ConnectivityState=recovering?(successes>=2?'ONLINE':'RECOVERING'):'ONLINE';publish({state,failures:0,successes,since:state===snap.state?snap.since:now,lastSuccess:now,lastFailure:snap.lastFailure})}
function failure(){const now=Date.now();const failures=snap.failures+1;const failureSpan=snap.lastFailure?now-snap.lastFailure:0;let state:ConnectivityState=failures===1?'DEGRADED':'SUSPECTED_OFFLINE';if(failures>=4 && (now-snap.since>=20_000 || failureSpan>=8_000))state='OFFLINE';publish({state,failures,successes:0,since:snap.failures===0?now:snap.since,lastSuccess:snap.lastSuccess,lastFailure:now})}
const sleep=(ms:number)=>new Promise(r=>setTimeout(r,ms));
function retryable(input:RequestInfo|URL,init?:RequestInit){const method=(init?.method||((input as Request)?.method)||'GET').toUpperCase();if(method==='GET'||method==='HEAD')return true;const h=new Headers(init?.headers);return h.has('Idempotency-Key')}
let refreshing:Promise<string|null>|null=null;async function renewAccess(){if(refreshing)return refreshing;refreshing=(async()=>{try{const r=await nativeFetch('/api/v1/auth/refresh',{method:'POST',credentials:'include',cache:'no-store'});if(!r.ok){/* the space of the session may have been withdrawn: the app checks the other spaces of the identity */if(r.status===401)window.dispatchEvent(new CustomEvent('edusync:space-check'));return null}const data=await r.json();const token=String(data.access_token||'');if(token){window.dispatchEvent(new CustomEvent('edusync:token-refreshed',{detail:{token,scope:data.scope}}));return token}return null}catch{return null}finally{refreshing=null}})();return refreshing}
/* Write activity (POST/PUT/PATCH/DELETE to the API): what the status chip reports to the user.
   Nothing is queued offline here; a failed write is reported as not sent. */
export type WriteActivity={pending:number;retrying:boolean;last:'none'|'ok'|'failed';at:number};
let activity:WriteActivity={pending:0,retrying:false,last:'none',at:0};
const activityListeners=new Set<(a:WriteActivity)=>void>();
function setActivity(patch:Partial<WriteActivity>){activity={...activity,...patch};activityListeners.forEach(fn=>fn({...activity}))}
export function subscribeActivity(fn:(a:WriteActivity)=>void){activityListeners.add(fn);fn({...activity});return()=>{activityListeners.delete(fn)}}
function isWrite(input:RequestInfo|URL,init?:RequestInit){const method=(init?.method||((input as Request)?.method)||'GET').toUpperCase();const url=typeof input==='string'?input:input instanceof URL?input.toString():input.url;return !['GET','HEAD','OPTIONS'].includes(method)&&url.includes('/api/')&&!url.includes('/auth/')}
/* Unknown outcome protection: when a write ended without any response (connection cut), the server may
   have committed it. Re-sending the exact same request within 10 minutes reuses the same Idempotency-Key,
   so the server answers with the recorded result instead of creating a duplicate (payment, enrolment...). */
const UNKNOWN_OUTCOME_MS=10*60_000;const unknownOutcome=new Map<string,{key:string;at:number}>();
function writeSignature(input:RequestInfo|URL,init?:RequestInit){const body=init?.body;if(typeof body!=='string')return null;const method=(init?.method||'POST').toUpperCase();const url=typeof input==='string'?input:input instanceof URL?input.toString():input.url;return `${method} ${url} ${body}`}
function withRememberedKey(input:RequestInfo|URL,init:RequestInit|undefined,sig:string|null):RequestInit|undefined{if(!sig||!init)return init;const h=new Headers(init.headers);if(!h.has('Idempotency-Key'))return init;const now=Date.now();for(const [k,v] of unknownOutcome)if(now-v.at>UNKNOWN_OUTCOME_MS)unknownOutcome.delete(k);const prev=unknownOutcome.get(sig);if(prev){h.set('Idempotency-Key',prev.key);return {...init,headers:h}}return init}
export function isEduSyncApi(input:RequestInfo|URL):boolean {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  const url = new URL(raw, window.location.origin);
  return url.origin === window.location.origin && url.pathname.startsWith('/api/');
}
async function resilientApiFetch(input:RequestInfo|URL,init?:RequestInit):Promise<Response>{
// Third-party SDK requests retain their own credentials, errors and retry rules.
// In particular Firebase must never receive EduSync's credentials/include or MFA replay.
if (!isEduSyncApi(input)) return nativeFetch(input, init);
const write=isWrite(input,init);const sig=write?writeSignature(input,init):null;init=withRememberedKey(input,init,sig);if(write)setActivity({pending:activity.pending+1});let ok=false;try{const r=await attempt(input,init,write);ok=r.status<500;if(sig)unknownOutcome.delete(sig);return r}catch(e){const key=init?new Headers(init.headers).get('Idempotency-Key'):null;if(sig&&key)unknownOutcome.set(sig,{key,at:Date.now()});throw e}finally{if(write)setActivity({pending:Math.max(0,activity.pending-1),retrying:false,last:ok?'ok':'failed',at:Date.now()})}}
export async function resilientFetch(input:RequestInfo|URL,init?:RequestInit):Promise<Response>{
  if(!isEduSyncApi(input))return nativeFetch(input,init);
  const url=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url,window.location.origin);
  const method=(init?.method||(input instanceof Request?input.method:'GET')).toUpperCase();
  const scope=knownContext()?.scope||null;
  const read=method==='GET';
  const offline=knownContext() && (navigator.onLine===false || getPlatformAuthState()==='OFFLINE_AUTHENTICATED_CACHED');
  const school=knownContext()?.kind==='SCHOOL';
  const replay=new Headers(init?.headers).get('X-EduSync-Replay')==='outbox';
  // School space (owner decision 2026-10-25): enrollment, re-enrollment and payments do not depend on the network —
  // the write is kept in the device outbox with its Idempotency-Key and replayed later. The platform stays read-only.
  const queueable=school && !read && !replay && !!offlineWriteKind(url.pathname);
  if(offline && queueable)return queueWrite(url,method,init);
  if(offline && !['GET','HEAD','OPTIONS'].includes(method) && !/\/auth\/(refresh|logout)$/.test(url.pathname))
    throw new UserFacingError(school?'Hors connexion : cette action-là demande le réseau. Les inscriptions, les encaissements et les dépenses, eux, continuent sans connexion.':'Hors connexion — lecture seule. Cette action nécessite une connexion au serveur.','OFFLINE_READ_ONLY');
  if(offline && read && !/\/auth\//.test(url.pathname)){
    const local=school?await packRead(url):null;if(local)return local;
    const cached=await cachedPlatformRead(url,scope);if(cached)return cached;
    throw new UserFacingError('Cette donnée n’est pas disponible hors connexion. Réessayez au retour du réseau.','OFFLINE_NOT_CACHED');
  }
  try{const response=await resilientApiFetch(input,init);if(read)await rememberPlatformRead(url,response,scope);return response;}
  catch(error){
    // Connection lost during the write: the server may or may not have it — replaying the SAME key later is safe.
    if(queueable && !(error instanceof UserFacingError)){setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');return queueWrite(url,method,init);}
    if(read && scope && knownContext()?.scope===scope && cacheablePath(url.pathname)){
    setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');
    const local=school?await packRead(url):null;if(local)return local;
    const cached=await cachedPlatformRead(url,scope);if(cached)return cached;
  }throw error;}
}
/** Synthetic 202 « recorded on this device » answer; callers test `offline_queued`. */
async function queueWrite(url:URL,method:string,init?:RequestInit):Promise<Response>{
  const body=typeof init?.body==='string'?init.body:'{}';
  const key=new Headers(init?.headers).get('Idempotency-Key')||crypto.randomUUID();
  const op=await enqueueWrite(url.pathname,method,body,key);
  try{const b=JSON.parse(body);
    if(/\/finance\/checkout\/collect$/.test(url.pathname))await applyLocalPayment(b.enrollment_id,b.charge_ids??[],b.amount);
    if(/\/finance\/checkout\/family-collect$/.test(url.pathname))for(const l of b.lines??[])await applyLocalPayment(l.enrollment_id,l.charge_ids??[],l.amount);
  }catch{/* local copy only */}
  return new Response(JSON.stringify({offline_queued:true,operation_id:op.id,label:op.label,queued_at:op.createdAt,receipt_number:null,allocations:[]}),{status:202,headers:{'Content-Type':'application/json'}});
}
/** Offline answers for the cash desk from the offline pack (pupils of the year + payable charges, updated locally). */
async function packRead(url:URL):Promise<Response|null>{
  const pack=await loadPack().catch(()=>null);if(!pack)return null;
  const json=(v:unknown)=>new Response(JSON.stringify(v),{status:200,headers:{'Content-Type':'application/json','X-EduSync-Offline':'pack'}});
  if(url.pathname==='/api/v1/finance/checkout/search')return json({items:searchPack(pack,url.searchParams.get('q')||'')});
  const m=url.pathname.match(/^\/api\/v1\/finance\/checkout\/balance\/([0-9a-f-]{36})$/);if(m)return json({items:pack.balances[m[1]]??[]});
  // « Action conseillée » offline (proof on a phone, 2026-10-31): same order as the server — the oldest charge that may be
  // paid now (sequential eligibility kept in the pack). The admission bundle needs the server and is not guessed here; the
  // server re-checks everything when the payment is replayed.
  const rec=url.pathname.match(/^\/api\/v1\/finance\/checkout\/recommended\/([0-9a-f-]{36})$/);
  if(rec){const due=(pack.balances[rec[1]]??[]).find((c:any)=>c.eligible&&Number(c.remaining)>0);
    return json(due?{ready:true,kind:'ECHEANCE',label:due.label,currency:due.currency,allocations:[{charge_id:due.id,amount:String(due.remaining)}],total:String(due.remaining)}
      :{ready:false,reason:'Aucun frais payable dans la copie de cet appareil.',allocations:[],total:'0'});}
  return null;
}
async function attempt(input:RequestInfo|URL,init:RequestInit|undefined,write:boolean):Promise<Response>{const max=retryable(input,init)?3:1;let last:unknown;for(let i=0;i<max;i++){if(i>0&&write)setActivity({retrying:true});try{const controller=new AbortController();const timeout=window.setTimeout(()=>controller.abort(),12_000+8_000*i);let r=await nativeFetch(input,{...init,credentials:init?.credentials??'include',signal:init?.signal??controller.signal});clearTimeout(timeout);const url=typeof input==='string'?input:input instanceof URL?input.toString():input.url;if(r.status===401&&!url.includes('/auth/login')&&!url.includes('/auth/refresh')){const token=await renewAccess();if(token){const h=new Headers(init?.headers||(input instanceof Request?input.headers:undefined));h.set('Authorization',`Bearer ${token}`);r=await nativeFetch(input,{...init,headers:h,credentials:'include'})}}r=await withStepUp(r,input,init);if(r.status===403&&r.headers.get('X-EduSync-Space')==='WITHDRAWN')window.dispatchEvent(new CustomEvent('edusync:space-check'));if(r.status>=500){failure();if(i<max-1){await sleep([1200,2600,5200][i]+Math.random()*500);continue}}else success();return r}catch(e){last=e;failure();if(i<max-1){await sleep([1200,2600,5200][i]+Math.random()*500);continue}}}throw last instanceof Error?last:new Error('network')}
/* Step-up (owner decision 2026-10-13): a sensitive platform action answered 403 MFA_STEP_UP_REQUIRED asks the user for a
   code (dialog registered by Atelier Pro), then the same request is sent again (same Idempotency-Key, nothing doubled). */
type StepUpHandler=()=>Promise<boolean>;let stepUpHandler:StepUpHandler|null=null;let stepUpPending:Promise<boolean>|null=null;
export function setStepUpHandler(h:StepUpHandler|null){stepUpHandler=h}
async function withStepUp(r:Response,input:RequestInfo|URL,init:RequestInit|undefined):Promise<Response>{
  if(r.status!==403||!stepUpHandler)return r;
  let code='';try{code=(await r.clone().json())?.detail?.code||''}catch{return r}
  if(code!=='MFA_STEP_UP_REQUIRED')return r;
  stepUpPending??=stepUpHandler().finally(()=>{stepUpPending=null});
  if(!(await stepUpPending))return new Response(JSON.stringify({detail:'Action non effectuée : la confirmation par code a été annulée.'}),{status:403,headers:{'Content-Type':'application/json'}});
  return nativeFetch(input,{...init,credentials:'include'});
}
let installed=false;
export function installResilientFetch(){
  globalThis.fetch=resilientFetch as typeof fetch;
  if(!installed){installed=true;
    window.addEventListener('offline',()=>{publish({...snap,state:'OFFLINE',successes:0,since:Date.now()});if(knownContext())setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED')});
    window.addEventListener('online',()=>publish({...snap,state:'RECOVERING',successes:0,since:Date.now()}));
    if(navigator.onLine===false)publish({...snap,state:'OFFLINE',successes:0,since:Date.now()});
  }
  startHealthProbe();
}
export function getConnectivity(){return {...snap}}
export function subscribeConnectivity(fn:(s:Snapshot)=>void){listeners.add(fn);fn({...snap});return()=>{listeners.delete(fn)}}
let probeStarted=false;function startHealthProbe(){if(probeStarted)return;probeStarted=true;const probe=async()=>{try{const c=new AbortController();const t=setTimeout(()=>c.abort(),10_000);const r=await nativeFetch('/health-api',{cache:'no-store',signal:c.signal});clearTimeout(t);const healthy=r.ok&&r.headers.get('Content-Type')?.includes('application/json')&&(await r.json()).status==='ok';healthy?success():failure()}catch{failure()}finally{const delay=snap.state==='ONLINE'?30_000:snap.state==='OFFLINE'?12_000:8_000;setTimeout(probe,delay)}};setTimeout(probe,5000)}
export function connectivityLabel(s:ConnectivityState){return s==='ONLINE'?'En ligne':s==='DEGRADED'?'Connexion instable':s==='SUSPECTED_OFFLINE'?'Connexion très instable':s==='RECOVERING'?'Reconnexion…':'Hors ligne'}
