import type {PlatformMe, SchoolLoginResult} from '../api';
import {clearPlatformSnapshots, platformSnapshot} from '../offline/store';

export type PlatformAuthState='ONLINE_AUTHENTICATED'|'OFFLINE_AUTHENTICATED_CACHED'|'AUTH_REQUIRED';
export type OfflineContextKind='PLATFORM'|'SCHOOL';

/* Offline policy, explicit per context (product rule 2026-10-23) — never one shared TTL:
   - PLATFORM: authenticated read-only cache valid 24 h after the last online validation;
   - SCHOOL:   authenticated read-only cache valid 7 days after the last online validation.
   The stored context is display-only (identity, school, menu permissions): never a bearer or refresh token. It lives in
   localStorage so an installed app closed and reopened without network finds it again. Sign-out, a server revocation
   or a change of space erases it with every cached read. Offline, every write is refused before the network. */
export const OFFLINE_POLICY:Record<OfflineContextKind,{ttlMs:number;storageKey:string;maxReads:number}>={
  PLATFORM:{ttlMs:24*3600_000,storageKey:'edusync.platform.readonly-context',maxReads:40},
  SCHOOL:{ttlMs:7*24*3600_000,storageKey:'edusync.school.readonly-context',maxReads:120},
};

type KnownPlatform={kind:'PLATFORM';scope:string;me:PlatformMe;at:number};
export type SchoolDisplayContext={school:SchoolLoginResult['school'];user:SchoolLoginResult['user'];permissions:string[]};
type KnownSchool={kind:'SCHOOL';scope:string;session:SchoolDisplayContext;at:number};
type Known=KnownPlatform|KnownSchool;
export const OFFLINE_PLATFORM_TOKEN='offline-display-only';
export const OFFLINE_SCHOOL_TOKEN='offline-display-only';
let known:Known|null=null;
let state:PlatformAuthState='AUTH_REQUIRED';
let lastRead:number|undefined;

function valid(v:any, kind:OfflineContextKind):boolean{
  if(typeof v?.scope!=='string' || typeof v?.at!=='number' || Date.now()-v.at>=OFFLINE_POLICY[kind].ttlMs)return false;
  if(kind==='PLATFORM')return !!v.me?.user?.id && Array.isArray(v.me.menu) && Array.isArray(v.me.permissions);
  return !!v.session?.user?.id && !!v.session?.school?.id && Array.isArray(v.session.permissions);
}
function read(kind:OfflineContextKind):Known|null{
  const key=OFFLINE_POLICY[kind].storageKey;
  try{const v=JSON.parse(localStorage.getItem(key)||sessionStorage.getItem(key)||'null');
    if(v && valid(v,kind))return {...v,kind};
    if(v)localStorage.removeItem(key);                                         // expired: the context is not shown any more
  }catch{/* no usable local context */}
  return null;
}
function store(next:Known){
  known=next;
  for(const kind of Object.keys(OFFLINE_POLICY) as OfflineContextKind[]){
    const key=OFFLINE_POLICY[kind].storageKey;
    try{if(kind===next.kind)localStorage.setItem(key,JSON.stringify(next));else localStorage.removeItem(key);sessionStorage.removeItem(key)}catch{/* private mode: memory only */}
  }
  setPlatformAuthState('ONLINE_AUTHENTICATED');
}

/** Restores the most recently validated context still inside its own policy window. */
export function restoreOfflineContext():Known|null{
  const candidates=[read('PLATFORM'),read('SCHOOL')].filter(Boolean) as Known[];
  known=candidates.sort((a,b)=>b.at-a.at)[0]||null;
  return known;
}
export const restorePlatformContext=()=>{restoreOfflineContext();return knownPlatform();};
export function rememberPlatformContext(me:PlatformMe){
  const same=known?.kind==='PLATFORM' && known.me.user.id===me.user.id;
  if(known && !same) void clearPlatformSnapshots().catch(()=>{});
  store({kind:'PLATFORM',scope:same?known!.scope:`platform:${crypto.randomUUID()}`,me,at:Date.now()});
}
export function rememberSchoolContext(session:SchoolDisplayContext){
  const same=known?.kind==='SCHOOL' && known.session.user.id===session.user.id && known.session.school.id===session.school.id;
  if(known && !same) void clearPlatformSnapshots().catch(()=>{});
  const display={school:session.school,user:{id:session.user.id,email:session.user.email,full_name:session.user.full_name},permissions:[...session.permissions]};
  store({kind:'SCHOOL',scope:same?known!.scope:`school:${crypto.randomUUID()}`,session:display,at:Date.now()});
}
/** Forgets every offline context (platform and school) and every cached read. */
export function clearPlatformContext(){known=null;lastRead=undefined;
  for(const {storageKey} of Object.values(OFFLINE_POLICY)){try{localStorage.removeItem(storageKey);sessionStorage.removeItem(storageKey)}catch{/* facultatif */}}
  void clearPlatformSnapshots().catch(()=>{});setPlatformAuthState('AUTH_REQUIRED');}
export const clearOfflineContext=clearPlatformContext;
export function getPlatformAuthState(){return state;}
export function setPlatformAuthState(next:PlatformAuthState){state=next;window.dispatchEvent(new CustomEvent('edusync:platform-auth',{detail:next}));}
export function platformLastRead(){return lastRead;}
export function knownPlatform(){return known?.kind==='PLATFORM'?known:null;}
export function knownSchool(){return known?.kind==='SCHOOL'?known:null;}
export function knownContext(){return known;}

// No provider credentials, account/security responses, MFA secrets, exports,
// streams or files. Cache only a bounded JSON representation of approved reads.
export function cacheablePlatformPath(path:string){
  return /^\/api\/v1\/platform\/(dashboard(?:\/|$)|schools(?:\/|$)|identities(?:\/|$)|team(?:\/|$)|audit(?:-log)?(?:\/|$)|inbox(?:\/|$)|messaging(?:\/|$)|notification-campaigns(?:\/|$)|system\/health(?:\/|$))/.test(path)
    && !/\/(config|stream|avatar|sessions|recovery|mfa)(?:\/|$)|\/export(?:[./]|$)/.test(path);
}
// School screens already consulted (lists, records, settings, finance reports). Never accounts / sessions / MFA,
// imports, exports, files, documents to print or streams.
export function cacheableSchoolPath(path:string){
  return /^\/api\/v1\/(schooling|finance|personnel|settings|stewardship|effectifs|notifications|documents\/history|sync\/status)(?:\/|$)/.test(path)
    && !/\/(stream|avatar|sessions|recovery|mfa|import|imports|exports?|download|files?|pdf|branding)(?:[./]|$)|\.(pdf|csv|xlsx?|zip)$/.test(path);
}
export function cacheablePath(path:string, kind:OfflineContextKind|undefined=known?.kind){
  return kind==='PLATFORM'?cacheablePlatformPath(path):kind==='SCHOOL'?cacheableSchoolPath(path):false;
}
export async function rememberPlatformRead(url:URL, response:Response, expectedScope:string|null=known?.scope||null){
  const context=known;
  if(!context || context.scope!==expectedScope || !response.ok || !cacheablePath(url.pathname,context.kind) || !response.headers.get('Content-Type')?.includes('application/json'))return;
  try{const body=await response.clone().text();if(body.length>256_000||known?.scope!==expectedScope)return;await platformSnapshot(context.scope,url.pathname+url.search,body,OFFLINE_POLICY[context.kind].maxReads)}catch{/* caching must not block a live read */}
}
export async function cachedPlatformRead(url:URL, expectedScope:string|null=known?.scope||null):Promise<Response|null>{
  const context=known;
  if(!context || context.scope!==expectedScope || !cacheablePath(url.pathname,context.kind))return null;
  if(context.kind==='PLATFORM' && url.pathname==='/api/v1/platform/team/me')return new Response(JSON.stringify(context.me),{headers:{'Content-Type':'application/json','X-EduSync-Cached-At':String(context.at)}});
  try{const entry=await platformSnapshot(context.scope,url.pathname+url.search);
    if(!entry||known?.scope!==expectedScope||Date.now()-entry.at>=OFFLINE_POLICY[context.kind].ttlMs)return null;lastRead=entry.at;
    window.dispatchEvent(new CustomEvent('edusync:platform-cache',{detail:entry.at}));
    return new Response(entry.body,{headers:{'Content-Type':'application/json','X-EduSync-Cached-At':String(entry.at)}});
  }catch{return null}
}
