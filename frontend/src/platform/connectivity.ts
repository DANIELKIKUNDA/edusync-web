import {cachedPlatformRead, cacheablePath, getPlatformAuthState, knownContext, rememberPlatformRead, setPlatformAuthState} from './offline_session';
import {UserFacingError} from './errors';
import {applyLocalPayment, enqueueWrite, loadPack, offlineWriteKind, searchPack} from '../offline/outbox';
export type ConnectivityState='ONLINE'|'DEGRADED'|'SUSPECTED_OFFLINE'|'OFFLINE'|'RECOVERING';
type Snapshot={state:ConnectivityState;failures:number;successes:number;since:number;lastSuccess?:number;lastFailure?:number;failingSince?:number};
export const nativeFetch=globalThis.fetch.bind(globalThis);let snap:Snapshot={state:'ONLINE',failures:0,successes:0,since:Date.now(),lastSuccess:Date.now()};
const listeners=new Set<(s:Snapshot)=>void>();
/* Network detection (owner, 2026-11-01: « pas un système qui détecte en une seconde l’absence de connexion »). Networks in the
   DRC drop for a second or two all the time, and the browser's online/offline signal follows every drop. The pattern used by
   offline-first apps (heartbeat verification + hysteresis): the browser signal and a failed request are only HINTS; the app
   checks the server itself with short probes and declares « Hors ligne » only after OFFLINE_AFTER_FAILURES failures spread
   over at least OFFLINE_GRACE_MS. Coming back needs RECOVER_SUCCESSES answers in a row, so a single lucky probe on a dying
   network does not switch the app back and forth. During the check nothing is lost: payments keep their Idempotency-Key and
   go to the device outbox if the server cannot be reached. */
export const OFFLINE_GRACE_MS=10_000, OFFLINE_AFTER_FAILURES=3, RECOVER_SUCCESSES=2;
function publish(next:Snapshot){const was=snap.state;snap=next;
  // Only a CONFIRMED loss puts the session in offline mode (cached reads, outbox); a suspicion does not.
  if(next.state==='OFFLINE'&&was!=='OFFLINE'&&knownContext()&&getPlatformAuthState()==='ONLINE_AUTHENTICATED')setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');
  listeners.forEach(fn=>fn({...snap}));window.dispatchEvent(new CustomEvent('edusync:connectivity',{detail:snap}))}
function success(){const now=Date.now();
  // Never confirmed offline (DEGRADED / SUSPECTED): one answer is enough. Confirmed offline: wait for RECOVER_SUCCESSES in a row.
  const confirmed=snap.state==='OFFLINE'||snap.state==='RECOVERING';const successes=confirmed?snap.successes+1:Math.min(snap.successes+1,3);
  const state:ConnectivityState=confirmed?(successes>=RECOVER_SUCCESSES?'ONLINE':'RECOVERING'):'ONLINE';
  publish({state,failures:0,successes,since:state===snap.state?snap.since:now,lastSuccess:now,lastFailure:snap.lastFailure});
  if(state==='RECOVERING')probeSoon(1_500)}
function failure(){const now=Date.now();const failures=snap.failures+1;const failingSince=snap.failingSince??now;
  let state:ConnectivityState;
  if(snap.state==='OFFLINE'||snap.state==='RECOVERING')state='OFFLINE';            // already confirmed: a failed recovery goes straight back
  else if(failures>=OFFLINE_AFTER_FAILURES&&now-failingSince>=OFFLINE_GRACE_MS)state='OFFLINE';
  else state=failures===1?'DEGRADED':'SUSPECTED_OFFLINE';
  publish({state,failures,successes:0,since:state===snap.state?snap.since:now,lastSuccess:snap.lastSuccess,lastFailure:now,failingSince});
  if(state==='DEGRADED'||state==='SUSPECTED_OFFLINE')probeSoon(2_500)}
/** True while the network is suspected but not yet confirmed lost: requests fail fast (no retry wait) and fall back to the device. */
function suspected(){return (typeof navigator!=='undefined'&&navigator.onLine===false)||snap.state==='SUSPECTED_OFFLINE'||snap.state==='OFFLINE'}
/** Offline mode for routing requests: only a confirmed loss (or a session reopened from the device). */
function confirmedOffline(){return !!knownContext()&&(getPlatformAuthState()==='OFFLINE_AUTHENTICATED_CACHED'||snap.state==='OFFLINE')}
const sleep=(ms:number)=>new Promise(r=>setTimeout(r,ms));
function retryable(input:RequestInfo|URL,init?:RequestInit){const method=(init?.method||((input as Request)?.method)||'GET').toUpperCase();if(method==='GET'||method==='HEAD')return true;const h=new Headers(init?.headers);return h.has('Idempotency-Key')}
async function doRefresh(signal?:AbortSignal){
  let r=await nativeFetch('/api/v1/auth/refresh',{method:'POST',credentials:'include',cache:'no-store',signal});
  // A request frozen by Chrome may resume with the preceding cookie after another tab/PWA has rotated it. The server
  // deliberately keeps the device session alive; retry once so the browser sends its current cookie.
  if(r.status===409&&r.headers.get('X-EduSync-Session')==='STALE_REFRESH'){
    await sleep(120);r=await nativeFetch('/api/v1/auth/refresh',{method:'POST',credentials:'include',cache:'no-store',signal});
  }
  return r;
}
/** One refresh at a time across Chrome tabs and the installed PWA (Web Locks is origin-wide). */
export async function refreshAccessSession(signal?:AbortSignal):Promise<Response>{
  const locks=typeof navigator!=='undefined'?navigator.locks:undefined;
  return locks?locks.request('edusync-session-refresh',()=>doRefresh(signal)):doRefresh(signal);
}
let refreshing:Promise<string|null>|null=null;async function renewAccess(){if(refreshing)return refreshing;refreshing=(async()=>{try{const r=await refreshAccessSession();if(!r.ok){/* the space of the session may have been withdrawn: the app checks the other spaces of the identity */if(r.status===401)window.dispatchEvent(new CustomEvent('edusync:space-check'));return null}const data=await r.json();const token=String(data.access_token||'');if(token){window.dispatchEvent(new CustomEvent('edusync:token-refreshed',{detail:{token,scope:data.scope}}));return token}return null}catch{return null}finally{refreshing=null}})();return refreshing}
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
  const offline=confirmedOffline();
  const school=knownContext()?.kind==='SCHOOL';
  const replay=new Headers(init?.headers).get('X-EduSync-Replay')==='outbox';
  // School space (owner decision 2026-10-25): enrollment, re-enrollment and payments do not depend on the network —
  // the write is kept in the device outbox with its Idempotency-Key and replayed later. The platform stays read-only.
  const headers=new Headers(init?.headers);const hasKey=!!headers.get('Idempotency-Key');
  // Only a JSON operation carrying its Idempotency-Key is kept: the replay must be recognised by the server (a file upload
  // or an operation without key cannot be replayed safely).
  const queueable=school && !read && !replay && !!offlineWriteKind(url.pathname) && hasKey && (init?.body==null || typeof init.body==='string');
  if(offline && queueable)return queueWrite(url,method,init);
  if(offline && !['GET','HEAD','OPTIONS'].includes(method) && !/\/auth\/(refresh|logout)$/.test(url.pathname))
    throw new UserFacingError(school?'Hors connexion : cette action demande le réseau (comptes et accès, imports, annulations et clôture de la journée de caisse). Le reste de votre travail continue sans connexion.':'Hors connexion — lecture seule. Cette action nécessite une connexion au serveur.','OFFLINE_READ_ONLY');
  if(offline && read && !/\/auth\//.test(url.pathname)){
    const local=school?await packRead(url):null;if(local)return local;
    const cached=await cachedPlatformRead(url,scope);if(cached)return cached;
    throw new UserFacingError('Cette donnée n’est pas disponible hors connexion. Réessayez au retour du réseau.','OFFLINE_NOT_CACHED');
  }
  try{const response=await resilientApiFetch(input,init);if(read)await rememberPlatformRead(url,response,scope);return response;}
  catch(error){
    // Connection lost during the write: the server may or may not have it — replaying the SAME key later is safe.
    // One failed request is not a lost network: the operation is kept / the read is answered from the device, but the whole
    // session switches to offline mode only when the probes confirm it (failure() → OFFLINE → publish).
    if(queueable && !(error instanceof UserFacingError))return queueWrite(url,method,init);
    if(read && scope && knownContext()?.scope===scope && cacheablePath(url.pathname)){
    const local=school?await packRead(url):null;if(local)return local;
    const cached=await cachedPlatformRead(url,scope);if(cached)return cached;
  }throw error;}
}
/** Synthetic 202 « recorded on this device » answer; callers test `offline_queued`. */
async function queueWrite(url:URL,method:string,init?:RequestInit):Promise<Response>{
  const body=typeof init?.body==='string'?init.body:'{}';
  const key=new Headers(init?.headers).get('Idempotency-Key')||crypto.randomUUID();
  const op=await enqueueWrite(url.pathname,method,body,key,new Headers(init?.headers).get('If-Match'));
  window.dispatchEvent(new CustomEvent('edusync:outbox-queued',{detail:{label:op.label,kind:op.kind}}));
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
async function attempt(input:RequestInfo|URL,init:RequestInit|undefined,write:boolean):Promise<Response>{
// While the network is suspected, one try only: the cashier is not kept waiting through retries, the operation goes to the
// device (outbox / local copy) at once and is replayed with the same Idempotency-Key.
const max=retryable(input,init)&&!suspected()?3:1;let last:unknown;for(let i=0;i<max;i++){if(i>0&&write)setActivity({retrying:true});try{const controller=new AbortController();const timeout=window.setTimeout(()=>controller.abort(),12_000+8_000*i);let r=await nativeFetch(input,{...init,credentials:init?.credentials??'include',signal:init?.signal??controller.signal});clearTimeout(timeout);const url=typeof input==='string'?input:input instanceof URL?input.toString():input.url;if(r.status===401&&!url.includes('/auth/login')&&!url.includes('/auth/refresh')){const token=await renewAccess();if(token){const h=new Headers(init?.headers||(input instanceof Request?input.headers:undefined));h.set('Authorization',`Bearer ${token}`);r=await nativeFetch(input,{...init,headers:h,credentials:'include'})}}r=await withStepUp(r,input,init);if(r.status===403&&r.headers.get('X-EduSync-Space')==='WITHDRAWN')window.dispatchEvent(new CustomEvent('edusync:space-check'));if(r.status>=500){failure();if(i<max-1){await sleep([1200,2600,5200][i]+Math.random()*500);continue}}else success();return r}catch(e){last=e;failure();if(i<max-1){await sleep([1200,2600,5200][i]+Math.random()*500);continue}}}throw last instanceof Error?last:new Error('network')}
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
  startHealthProbe();
  if(!installed){installed=true;
    // The browser signal is a hint, never the verdict: it starts a check, the probes decide.
    window.addEventListener('offline',()=>{failure();probeSoon(0)});
    window.addEventListener('online',()=>{
      // A native `online` event is still only a hint, but combined with one successful health request it is sufficient to
      // leave confirmed offline mode. This avoids keeping the interface read-only while a second probe is delayed by a
      // request that the browser froze during sleep.
      if(snap.state==='OFFLINE'||snap.state==='RECOVERING')snap={...snap,successes:RECOVER_SUCCESSES-1};
      probeSoon(0);
    });
    // Back to the app (phone unlocked, tab shown): check at once instead of waiting for the next beat.
    document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){
      if(snap.state!=='ONLINE')probeSoon(0);
      // A wake-up is a session-resume event even when Chrome still reports the network as online.
      // Do not start a refresh while the app already knows it is offline: a frozen request would occupy the cross-tab lock
      // and delay the real restoration when the network returns.
      if(knownContext()&&snap.state==='ONLINE'&&navigator.onLine!==false)void renewAccess();
    }});
    if(navigator.onLine===false){failure();probeSoon(0)}
  }
}
export function getConnectivity(){return {...snap}}
export function subscribeConnectivity(fn:(s:Snapshot)=>void){listeners.add(fn);fn({...snap});return()=>{listeners.delete(fn)}}
/* Heartbeat: every 30 s when online; every 2.5 s while checking a suspicion (so the verdict comes in ~10 s); when offline,
   exponential backoff with jitter (5 s → 30 s) so a phone without network does not drain its battery. */
let probeStarted=false,probeTimer:ReturnType<typeof setTimeout>|undefined,probing=false,offlineBeats=0;
async function probe(){
  // The browser can announce `online` while an old offline probe is still waiting for its timeout. Keep retrying briefly
  // instead of losing that wake-up signal; otherwise the offline banner can remain visible for another full backoff cycle.
  if(probing){probeSoon(250);return}probing=true;try{const c=new AbortController();const t=setTimeout(()=>c.abort(),6_000);const r=await nativeFetch('/health-api',{cache:'no-store',signal:c.signal});clearTimeout(t);
  // The question is « is the server reachable? ». A JSON health answer must say ok; an origin without the health route (the
  // dev server answers its index page) still proves the network is there. 5xx (backend down behind nginx) is a failure.
  const json=r.headers.get('Content-Type')?.includes('application/json');const healthy=r.ok&&(json?(await r.json().catch(()=>null))?.status==='ok':true);healthy?success():failure()}catch{failure()}finally{probing=false;offlineBeats=snap.state==='OFFLINE'?offlineBeats+1:0;
  // Chrome/PWA does not always emit `online` after a laptop wake-up. Retry quickly at first (1 s, 2 s, 4 s…), then
  // progressively back off to 30 s so recovery is prompt without draining a phone that remains offline.
  if(probeTimer===undefined)probeSoon(snap.state==='ONLINE'?30_000:snap.state==='OFFLINE'?Math.min(30_000,1_000*2**Math.min(offlineBeats-1,5))+Math.random()*500:2_500)}}
function probeSoon(ms:number){if(!probeStarted)return;if(probeTimer!==undefined)clearTimeout(probeTimer);probeTimer=setTimeout(()=>{probeTimer=undefined;void probe()},ms)}
function startHealthProbe(){if(probeStarted)return;probeStarted=true;if(probeTimer===undefined)probeSoon(5_000)}
export function connectivityLabel(s:ConnectivityState){return s==='ONLINE'?'En ligne':s==='DEGRADED'?'Connexion instable':s==='SUSPECTED_OFFLINE'?'Vérification du réseau…':s==='RECOVERING'?'Reconnexion…':'Hors ligne'}
