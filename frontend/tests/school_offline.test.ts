// @vitest-environment jsdom
// School offline policy (product rule 2026-10-23): authenticated read-only cache valid 7 days for a school, 24 h for the
// platform — an explicit policy per context, never one shared TTL. Display context only (no token), survives a closed
// app, read-only offline, erased on sign-out / revocation.
import 'fake-indexeddb/auto';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';

const school={school:{id:'sch-1',code:'EXC',name:'École Excellence'},user:{id:'u-1',email:'secr@example.test',full_name:'Secrétariat'},permissions:['students.read','finance.read']};
const platformMe={user:{id:'p-1',email:'owner@example.test',full_name:'Owner'},roles:[],permissions:['platform.audit.read'],menu:[{key:'audit',label:'Journal',capability:'platform.audit.read'}]};
const DAY=24*3600_000;
const network=vi.fn();
async function fresh(){vi.resetModules();return import('../src/platform/offline_session');}  // a closed then reopened app
beforeEach(()=>{localStorage.clear();sessionStorage.clear();network.mockReset().mockRejectedValue(new TypeError('network'));vi.stubGlobal('fetch',network);});
afterEach(async()=>{(await import('../src/platform/offline_session')).clearPlatformContext();vi.useRealTimers();vi.unstubAllGlobals();localStorage.clear();});

it('explicit policy per context: platform 24 h, school 7 days', async()=>{
  const {OFFLINE_POLICY}=await fresh();
  expect(OFFLINE_POLICY.PLATFORM.ttlMs).toBe(DAY);
  expect(OFFLINE_POLICY.SCHOOL.ttlMs).toBe(7*DAY);
  expect(OFFLINE_POLICY.SCHOOL.storageKey).not.toBe(OFFLINE_POLICY.PLATFORM.storageKey);
});

it('a school session validated online is found again after the app is closed, without any token', async()=>{
  (await fresh()).rememberSchoolContext({...school,token:'secret-bearer'} as any);
  const stored=localStorage.getItem('edusync.school.readonly-context')||'';
  expect(stored).toContain('sch-1');
  expect(stored).not.toMatch(/secret-bearer|access_token|Bearer|refresh/);
  sessionStorage.clear();
  const reopened=await fresh();
  reopened.restoreOfflineContext();
  expect(reopened.knownSchool()?.session.school.code).toBe('EXC');
  expect(reopened.knownPlatform()).toBeNull();
});

it('school context still valid after 6 days, expired after 7; a platform context expires after 24 h', async()=>{
  vi.useFakeTimers({toFake:['Date']});
  const start=Date.now();
  (await fresh()).rememberSchoolContext(school);
  vi.setSystemTime(start+25*3600_000);
  expect((await fresh()).restoreOfflineContext()?.kind).toBe('SCHOOL');          // > 24 h: the school keeps its own policy
  vi.setSystemTime(start+6*DAY);
  expect((await fresh()).restoreOfflineContext()?.kind).toBe('SCHOOL');
  vi.setSystemTime(start+7*DAY+1);
  expect((await fresh()).restoreOfflineContext()).toBeNull();
  expect(localStorage.getItem('edusync.school.readonly-context')).toBeNull();    // expired context removed
  vi.setSystemTime(start);
  (await fresh()).rememberPlatformContext(platformMe as any);
  vi.setSystemTime(start+25*3600_000);
  expect((await fresh()).restoreOfflineContext()).toBeNull();
});

it('only one space is kept: opening the platform forgets the school context and vice versa', async()=>{
  const m=await fresh();
  m.rememberSchoolContext(school);m.rememberPlatformContext(platformMe as any);
  expect(localStorage.getItem('edusync.school.readonly-context')).toBeNull();
  m.rememberSchoolContext(school);
  expect(localStorage.getItem('edusync.platform.readonly-context')).toBeNull();
});

it('school screens already consulted are cached; accounts, MFA, exports, imports, files and streams never', async()=>{
  const {cacheableSchoolPath}=await fresh();
  for(const p of ['/api/v1/schooling/students','/api/v1/finance/reports/daily','/api/v1/settings/academic-years','/api/v1/personnel/summary'])expect(cacheableSchoolPath(p)).toBe(true);
  for(const p of ['/api/v1/auth/contexts','/api/v1/access','/api/v1/schooling/exports/students','/api/v1/import/students','/api/v1/notifications/stream','/api/v1/finance/receipts/1.pdf','/api/v1/platform/schools'])expect(cacheableSchoolPath(p)).toBe(false);
});

it('offline in a school: consulted pages come from the cache, writes are refused before the network', async()=>{
  const m=await fresh();
  m.rememberSchoolContext(school);
  const url=new URL('/api/v1/schooling/students',location.origin);
  await m.rememberPlatformRead(url,new Response(JSON.stringify({items:[{name:'Élève déjà consulté'}]}),{headers:{'Content-Type':'application/json'}}));
  m.setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');
  const {resilientFetch}=await import('../src/platform/connectivity');
  expect(await (await resilientFetch('/api/v1/schooling/students')).json()).toEqual({items:[{name:'Élève déjà consulté'}]});
  await expect(resilientFetch('/api/v1/finance/cash/payments',{method:'POST',body:'{}'})).rejects.toMatchObject({code:'OFFLINE_READ_ONLY'});
  await expect(resilientFetch('/api/v1/schooling/families')).rejects.toMatchObject({code:'OFFLINE_NOT_CACHED'});
  expect(network).not.toHaveBeenCalled();
});

it('sign-out or a server revocation erases the school context and every cached read', async()=>{
  const m=await fresh();
  m.rememberSchoolContext(school);
  const url=new URL('/api/v1/schooling/students',location.origin);
  await m.rememberPlatformRead(url,new Response('{"items":[]}',{headers:{'Content-Type':'application/json'}}));
  m.clearPlatformContext();
  expect(localStorage.getItem('edusync.school.readonly-context')).toBeNull();
  m.rememberSchoolContext(school);                                                 // new namespace: the old read is gone
  expect(await m.cachedPlatformRead(url)).toBeNull();
  expect((await fresh()).restoreOfflineContext()?.kind).toBe('SCHOOL');
});
