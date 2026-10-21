// @vitest-environment jsdom
import 'fake-indexeddb/auto';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cachedPlatformRead, cacheablePlatformPath, clearPlatformContext, getPlatformAuthState, knownPlatform, rememberPlatformContext, rememberPlatformRead, restorePlatformContext, setPlatformAuthState} from '../src/platform/offline_session';
import type {PlatformMe} from '../src/api';

const me:PlatformMe={user:{id:'owner',email:'owner@example.test',full_name:'Owner'},roles:[],permissions:['platform.audit.read'],menu:[{key:'audit',label:'Journal',capability:'platform.audit.read'}]};
const network=vi.fn();
beforeEach(()=>{network.mockReset().mockRejectedValue(new TypeError('network'));vi.stubGlobal('fetch',network);});
afterEach(()=>{clearPlatformContext();sessionStorage.clear();vi.unstubAllGlobals();});

it('stores display context without a bearer token and restores the same scoped identity',()=>{
  rememberPlatformContext(me);setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');
  expect(restorePlatformContext()?.me.user.id).toBe('owner');
  expect(getPlatformAuthState()).toBe('OFFLINE_AUTHENTICATED_CACHED');
  expect(sessionStorage.getItem('edusync.platform.readonly-context')).not.toMatch(/access_token|Bearer|refresh_token/);
});

it('only caches approved reads and never credentials, MFA, exports or streams',()=>{
  expect(cacheablePlatformPath('/api/v1/platform/schools')).toBe(true);
  for(const path of ['/api/v1/auth/platform/mfa','/api/v1/platform/inbox/push/config','/api/v1/platform/audit/export','/api/v1/platform/inbox/stream'])expect(cacheablePlatformPath(path)).toBe(false);
});

it('returns only already-read snapshots, with age, isolated from another identity',async()=>{
  rememberPlatformContext(me);const url=new URL('/api/v1/platform/schools',location.origin);
  await rememberPlatformRead(url,new Response(JSON.stringify({items:[{name:'École déjà lue'}]}),{headers:{'Content-Type':'application/json'}}));
  const cached=await cachedPlatformRead(url);expect(await cached?.json()).toEqual({items:[{name:'École déjà lue'}]});
  expect(Number(cached?.headers.get('X-EduSync-Cached-At'))).toBeGreaterThan(0);
  expect(await cachedPlatformRead(new URL('/api/v1/platform/schools/unread',location.origin))).toBeNull();
  rememberPlatformContext({...me,user:{...me.user,id:'another'}});
  expect(await cachedPlatformRead(url)).toBeNull();
});

it('blocks sensitive writes before any network call and never queues them',async()=>{
  rememberPlatformContext(me);setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');
  const {resilientFetch}=await import('../src/platform/connectivity');
  await expect(resilientFetch('/api/v1/platform/schools',{method:'POST',body:'{}'})).rejects.toMatchObject({code:'OFFLINE_READ_ONLY'});
  await expect(resilientFetch('/api/v1/auth/platform/mfa',{method:'POST',body:'{}'})).rejects.toMatchObject({code:'OFFLINE_READ_ONLY'});
  expect(fetch).not.toHaveBeenCalled();
  expect(knownPlatform()?.me.user.id).toBe('owner');
});

it('does not store an in-flight response in the next identity namespace',async()=>{
  rememberPlatformContext(me);const originalScope=knownPlatform()!.scope;
  rememberPlatformContext({...me,user:{...me.user,id:'next-user'}});
  const url=new URL('/api/v1/platform/schools',location.origin);
  await rememberPlatformRead(url,new Response('{"items":[{"name":"Previous identity"}]}',{headers:{'Content-Type':'application/json'}}),originalScope);
  expect(await cachedPlatformRead(url)).toBeNull();
  expect(await cachedPlatformRead(url,originalScope)).toBeNull();
});

it('does not resurrect cached data after a confirmed authorization refusal',async()=>{
  network.mockResolvedValue(new Response('{}',{status:403}));
  rememberPlatformContext(me);
  const {resilientFetch}=await import('../src/platform/connectivity');
  const r=await resilientFetch('/api/v1/platform/schools');expect(r.status).toBe(403);
  clearPlatformContext();expect(getPlatformAuthState()).toBe('AUTH_REQUIRED');expect(knownPlatform()).toBeNull();
});
