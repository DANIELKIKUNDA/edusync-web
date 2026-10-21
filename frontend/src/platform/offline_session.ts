import type {PlatformMe} from '../api';
import {clearPlatformSnapshots, platformSnapshot} from '../offline/store';

export type PlatformAuthState='ONLINE_AUTHENTICATED'|'OFFLINE_AUTHENTICATED_CACHED'|'AUTH_REQUIRED';
type KnownPlatform={scope:string;me:PlatformMe;at:number};
const KEY='edusync.platform.readonly-context';
export const OFFLINE_PLATFORM_TOKEN='offline-display-only';
let known:KnownPlatform|null=null;
let state:PlatformAuthState='AUTH_REQUIRED';
let lastRead:number|undefined;

export function restorePlatformContext():KnownPlatform|null {
  try {const v=JSON.parse(sessionStorage.getItem(KEY)||'null');
    if(v?.me?.user?.id && Array.isArray(v.me.menu) && Array.isArray(v.me.permissions) && typeof v.scope==='string' && Date.now()-v.at<24*3600_000) known=v;
  } catch { /* no usable local context */ }
  return known;
}
export function rememberPlatformContext(me:PlatformMe){
  if(known && known.me.user.id!==me.user.id) void clearPlatformSnapshots().catch(()=>{});
  const scope=known?.me.user.id===me.user.id?known.scope:`platform:${crypto.randomUUID()}`;
  known={scope,me,at:Date.now()};
  try{sessionStorage.setItem(KEY,JSON.stringify(known))}catch{/* private mode: memory only */}
  setPlatformAuthState('ONLINE_AUTHENTICATED');
}
export function clearPlatformContext(){known=null;lastRead=undefined;try{sessionStorage.removeItem(KEY)}catch{};void clearPlatformSnapshots().catch(()=>{});setPlatformAuthState('AUTH_REQUIRED');}
export function getPlatformAuthState(){return state;}
export function setPlatformAuthState(next:PlatformAuthState){state=next;window.dispatchEvent(new CustomEvent('edusync:platform-auth',{detail:next}));}
export function platformLastRead(){return lastRead;}
export function knownPlatform(){return known;}

// No provider credentials, account/security responses, MFA secrets, exports,
// streams or files. Cache only a bounded JSON representation of approved reads.
export function cacheablePlatformPath(path:string){
  return /^\/api\/v1\/platform\/(dashboard(?:\/|$)|schools(?:\/|$)|identities(?:\/|$)|team(?:\/|$)|audit(?:-log)?(?:\/|$)|inbox(?:\/|$)|messaging(?:\/|$)|notification-campaigns(?:\/|$)|system\/health(?:\/|$))/.test(path)
    && !/\/(config|stream|avatar|sessions|recovery|mfa)(?:\/|$)|\/export(?:[./]|$)/.test(path);
}
export async function rememberPlatformRead(url:URL, response:Response, expectedScope:string|null=known?.scope||null){
  const context=known;
  if(!context || context.scope!==expectedScope || !response.ok || !cacheablePlatformPath(url.pathname) || !response.headers.get('Content-Type')?.includes('application/json'))return;
  try{const body=await response.clone().text();if(body.length>256_000||known?.scope!==expectedScope)return;await platformSnapshot(context.scope,url.pathname+url.search,body)}catch{/* caching must not block a live read */}
}
export async function cachedPlatformRead(url:URL, expectedScope:string|null=known?.scope||null):Promise<Response|null>{
  if(!known || known.scope!==expectedScope || !cacheablePlatformPath(url.pathname))return null;
  if(url.pathname==='/api/v1/platform/team/me')return new Response(JSON.stringify(known.me),{headers:{'Content-Type':'application/json','X-EduSync-Cached-At':String(known.at)}});
  try{const entry=await platformSnapshot(known.scope,url.pathname+url.search);if(!entry||known?.scope!==expectedScope)return null;lastRead=entry.at;
    window.dispatchEvent(new CustomEvent('edusync:platform-cache',{detail:entry.at}));
    return new Response(entry.body,{headers:{'Content-Type':'application/json','X-EduSync-Cached-At':String(entry.at)}});
  }catch{return null}
}
