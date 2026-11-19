// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {hasUsableAccessToken} from '../src/platform/access_token';
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals()});
const token=(exp:number)=>`e30.${btoa(JSON.stringify({exp}))}.signature`;
it('keeps continuity only while the access token has time left',()=>{
 expect(hasUsableAccessToken(token(Date.now()/1000+60))).toBe(true);
 expect(hasUsableAccessToken(token(Date.now()/1000-1))).toBe(false);
 expect(hasUsableAccessToken(token(Date.now()/1000+3))).toBe(false);
 for(const value of ['offline-display-only','', 'bad.json.signature'])expect(hasUsableAccessToken(value)).toBe(false);
});
it('ends endless legacy stale-cookie retries only after the identity endpoint refuses it',async()=>{
 vi.resetModules();
 const stale=()=>new Response('{}',{status:409,headers:{'X-EduSync-Session':'STALE_REFRESH'}});
 const native=vi.fn().mockResolvedValueOnce(stale()).mockResolvedValueOnce(stale()).mockResolvedValueOnce(new Response('{}',{status:401}));
 vi.stubGlobal('fetch',native);Object.defineProperty(navigator,'locks',{configurable:true,value:undefined});
 const {refreshAccessSession}=await import('../src/platform/connectivity');
 expect((await refreshAccessSession()).status).toBe(401);
 expect(native.mock.calls[2][0]).toBe('/api/v1/auth/contexts');
});
it('does not turn a temporary identity-service error into a logout',async()=>{
 vi.resetModules();
 const stale=()=>new Response('{}',{status:409,headers:{'X-EduSync-Session':'STALE_REFRESH'}});
 const native=vi.fn().mockResolvedValueOnce(stale()).mockResolvedValueOnce(stale()).mockResolvedValueOnce(new Response('{}',{status:503}));
 vi.stubGlobal('fetch',native);Object.defineProperty(navigator,'locks',{configurable:true,value:undefined});
 const {refreshAccessSession}=await import('../src/platform/connectivity');
 expect((await refreshAccessSession()).status).toBe(409);
});
