import {test,expect} from '@playwright/test';
test('platform session survives network loss, then revalidates and obeys revocation',async({page,context})=>{
  let offline=false,revoked=false,mutations=0;
  await page.route('**/api/**',async route=>{
    if(offline)return route.abort('internetdisconnected');
    const path=new URL(route.request().url()).pathname;
    const user={id:'offline-test',full_name:'Compte recette',email:'offline@example.test'};
    if(revoked&&(path.endsWith('/auth/refresh')||path.endsWith('/auth/contexts')))return route.fulfill({status:401,json:{detail:'Session terminée'}});
    let body:unknown={items:[],actions:[],total:0,has_more:false,next_cursor:null,limit:50};
    if(path.endsWith('/auth/refresh'))body={access_token:'online-fixture-token',scope:'PLATFORM',user};
    else if(path.endsWith('/auth/contexts'))body={contexts:[],current:{scope:'PLATFORM'},current_valid:true};
    else if(path.endsWith('/platform/team/me'))body={user,roles:[],permissions:['platform.audit.read'],menu:[{key:'audit',label:'Journal d’audit',capability:'platform.audit.read'}]};
    else if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:''});
    if(path.startsWith('/api/v1/platform/')&&route.request().method()==='POST')mutations++;
    return route.fulfill({json:body});
  });
  await page.goto('/');await expect(page.getByRole('heading',{name:'Journal d’audit',level:2})).toBeVisible();
  await expect.poll(()=>page.evaluate(()=>sessionStorage.getItem('edusync.platform.readonly-context')!==null)).toBe(true);
  if(process.env.EDUSYNC_TEST_BUILD==='1'){
    // First-visit boot assets are cached after worker activation, not only on a second visit.
    await expect.poll(()=>page.evaluate(async()=>{const names=await caches.keys();const cache=await caches.open(names.find(n=>n.startsWith('edusync-shell'))!);const urls=performance.getEntriesByType('resource').map(r=>r.name).filter(raw=>new URL(raw).pathname.startsWith('/assets/'));return urls.length>0&&(await Promise.all(urls.map(u=>cache.match(u)))).every(Boolean);})).toBe(true);
    expect(await page.evaluate(async()=>{for(const name of await caches.keys())for(const r of await(await caches.open(name)).keys())if(/\/api\/|\/health/.test(new URL(r.url).pathname)||r.headers.has('Authorization'))return false;return true;})).toBe(true);
  }
  offline=true;await context.setOffline(true);
  await expect(page.getByText('Hors connexion — lecture seule.',{exact:true})).toBeVisible();
  const result=await page.evaluate(async()=>{try{await fetch('/api/v1/platform/schools',{method:'POST',body:'{}'});return 'sent';}catch(e){return (e as {code?:string}).code;}});
  expect(result).toBe('OFFLINE_READ_ONLY');expect(mutations).toBe(0);
  if(process.env.EDUSYNC_TEST_BUILD==='1'){
    await page.reload();await expect(page.locator('.es-shell')).toBeVisible();
    await expect(page.getByText('Hors connexion — lecture seule.',{exact:true})).toBeVisible();
    await expect(page.getByRole('heading',{name:'Journal d’audit',level:2})).toBeVisible();
  }
  await page.screenshot({path:`${process.env.EDUSYNC_TEST_OUTPUT||'test-results'}/offline-platform.png`});
  offline=false;await context.setOffline(false);
  await expect(page.getByText('Hors connexion — lecture seule.',{exact:true})).toHaveCount(0);
  await expect(page.locator('.es-shell')).toBeVisible();
  revoked=true;offline=true;await context.setOffline(true);offline=false;await context.setOffline(false);
  await expect(page.locator('.es-shell')).toHaveCount(0);
  expect(await page.evaluate(()=>sessionStorage.getItem('edusync.platform.readonly-context'))).toBeNull();
});
