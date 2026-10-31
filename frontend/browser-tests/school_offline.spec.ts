import {test,expect} from '@playwright/test';
// School space offline (product rule 2026-10-23: authenticated read-only cache valid 7 days), on the compiled app with
// its service worker: open online, browse, close the app, airplane mode, reopen, stay in the school read-only, cached
// pages, no write, silent revalidation on network return, real revocation → cache erased and sign-in.
test.skip(process.env.EDUSYNC_TEST_BUILD!=='1','needs the compiled app and its service worker (offline reopening)');

const school={id:'sch-test',code:'EXC',name:'École Excellence'};
const user={id:'school-user',full_name:'Secrétariat recette',email:'secr@example.test'};
const KEY='edusync.school.readonly-context';

test('école : fermée puis rouverte en mode avion, reste connectée (bandeau : le travail continue, décision du 25/10), puis obéit à la révocation',async({context})=>{
  let offline=false,revoked=false,mutations=0,refreshes=0;
  await context.route('**/api/**',async route=>{
    if(offline)return route.abort('internetdisconnected');
    const req=route.request();const path=new URL(req.url()).pathname;
    if(path.endsWith('/auth/refresh'))refreshes++;
    if(revoked&&(path.endsWith('/auth/refresh')||path.endsWith('/auth/contexts')))return route.fulfill({status:401,json:{detail:'Session terminée'}});
    if(req.method()!=='GET'&&!path.includes('/auth/'))mutations++;
    let body:unknown={items:[],total:0,has_more:false,next_cursor:null,limit:50};
    if(path.endsWith('/auth/refresh'))body={access_token:'online-fixture-token',scope:'SCHOOL',school,user,permissions:['settings.read','personnel.read']};
    else if(path.endsWith('/auth/contexts'))body={contexts:[],current:{scope:'SCHOOL'},current_valid:true};
    else if(path.endsWith('/access/me'))body={membership_id:'m',school_id:school.id,role_label:'Secrétariat',permissions:['settings.read','personnel.read'],scoped:[],roles:[],
      navigation:[{key:'home',label:'Accueil',icon:'home'},{key:'settings',label:'Paramètres',icon:'settings'},{key:'personnel',label:'Personnel',icon:'users'}],widgets:[],actions:[]};
    else if(path.endsWith('/settings/overview'))body={school:{...school,version:1},readiness:{percent:80,global_blocking:false,items:[]}};
    else if(path.endsWith('/settings/academic-years'))body=[{id:'y1',code:'2026-2027',label:'2026-2027',start_date:'2026-09-01',end_date:'2027-07-02',status:'ACTIVE',version:1}];
    else if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:''});
    return route.fulfill({json:body});
  });

  // 1-2. online: open, then browse several screens
  const page=await context.newPage();
  await page.goto('/');
  await expect(page.locator('.es-shell')).toBeVisible();
  const nav=page.getByRole('complementary',{name:'Navigation principale'});
  for(const label of ['Paramètres','Personnel','Accueil'])await nav.getByRole('button',{name:label,exact:true}).click();
  await expect.poll(()=>page.evaluate(k=>localStorage.getItem(k),KEY)).toContain(school.id);
  expect(await page.evaluate(k=>localStorage.getItem(k),KEY)).not.toMatch(/online-fixture-token|access_token|Bearer/);
  await expect.poll(()=>page.evaluate(async()=>{const r=await fetch('/api/v1/settings/overview');return r.ok;})).toBe(true);

  // 3-5. close the app completely, airplane mode, reopen — only once the service worker controls the page and has the
  // application shell in cache (closing earlier is a first visit cut short, not an offline reopening)
  await expect.poll(()=>page.evaluate(async()=>{await navigator.serviceWorker.ready;if(!navigator.serviceWorker.controller)return false;
    for(const name of await caches.keys())if(await (await caches.open(name)).match('/'))return true;return false;}),{timeout:15000}).toBe(true);
  await page.close();
  offline=true;await context.setOffline(true);
  const reopened=await context.newPage();
  await reopened.goto('/');

  // 6-7. still in the school space, read-only banner, no sign-in screen
  await expect(reopened.locator('.es-shell')).toBeVisible();
  await expect(reopened.getByRole('heading',{name:'Connexion'})).toHaveCount(0);
  await expect(reopened.getByText('Hors connexion — vous pouvez continuer.',{exact:true})).toBeVisible();
  await expect(reopened.getByText(school.name).first()).toBeVisible();

  // 8. menus and pages already consulted come from the cache (with their date)
  const nav2=reopened.getByRole('complementary',{name:'Navigation principale'});
  for(const label of ['Paramètres','Personnel'])await expect(nav2.getByRole('button',{name:label,exact:true})).toBeVisible();
  await nav2.getByRole('button',{name:'Paramètres',exact:true}).click();
  const cached=await reopened.evaluate(async()=>{const r=await fetch('/api/v1/settings/overview');return {name:(await r.json()).school?.name,at:r.headers.get('X-EduSync-Cached-At')};});
  expect(cached.name).toBe(school.name);expect(Number(cached.at)).toBeGreaterThan(0);

  // 9. no sensitive write, nothing queued
  const write=await reopened.evaluate(async()=>{try{await fetch('/api/v1/finance/cash/payments',{method:'POST',body:'{}'});return 'sent';}catch(e){return (e as {code?:string}).code;}});
  expect(write).toBe('OFFLINE_READ_ONLY');expect(mutations).toBe(0);
  await reopened.screenshot({path:`${process.env.EDUSYNC_TEST_OUTPUT||'test-results'}/offline-school.png`});

  // 10. network back: silent revalidation, still in the school, banner gone
  const before=refreshes;
  offline=false;await context.setOffline(false);
  await expect.poll(()=>refreshes).toBeGreaterThan(before);
  await expect(reopened.getByText('Hors connexion — vous pouvez continuer.',{exact:true})).toHaveCount(0);
  await expect(reopened.locator('.es-shell')).toBeVisible();

  // 11. session really revoked server-side: cache erased, sign-in screen
  revoked=true;offline=true;await context.setOffline(true);offline=false;await context.setOffline(false);
  await expect(reopened.locator('.es-shell')).toHaveCount(0);
  await expect(reopened.getByRole('heading',{name:'Connexion'})).toBeVisible();
  expect(await reopened.evaluate(k=>localStorage.getItem(k),KEY)).toBeNull();
});
