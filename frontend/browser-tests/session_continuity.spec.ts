import {test,expect} from '@playwright/test';

async function setup(page:any){
  let mode='normal',refreshes=0;
  const school={id:'school-test',code:'TEST',name:'École de test'};
  const user={id:'user-test',full_name:'Compte de test',email:'test@example.test'};
  const token=`e30.${Buffer.from(JSON.stringify({exp:Math.floor(Date.now()/1000)+600})).toString('base64url')}.signature`;
  await page.route('**/api/**',async(route:any)=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/auth/refresh')){
      refreshes++;
      if(mode==='temporary')return route.fulfill({status:503,json:{detail:'Service indisponible'}});
      if(mode==='stale')return route.fulfill({status:409,headers:{'X-EduSync-Session':'STALE_REFRESH'},json:{detail:{code:'STALE_REFRESH'}}});
      return route.fulfill({json:{access_token:token,scope:'SCHOOL',school,user,permissions:['personnel.read']}});
    }
    if(path.endsWith('/auth/contexts'))return route.fulfill(mode==='stale'?{status:401,json:{detail:'Session à renouveler'}}:{json:{contexts:[],current:{scope:'SCHOOL'},current_valid:true}});
    let body:any={items:[],total:0,has_more:false};
    if(path.endsWith('/access/me'))body={membership_id:'m',school_id:school.id,role_label:'Secrétariat',permissions:['personnel.read'],scoped:[],roles:[],navigation:[{key:'home',label:'Accueil',icon:'home'},{key:'personnel',label:'Personnel',icon:'users'}],widgets:[],actions:[]};
    if(path.endsWith('/settings/academic-years'))body=[];
    if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:''});
    return route.fulfill({json:body});
  });
  await page.goto('/');await expect(page.locator('.es-shell')).toBeVisible();
  await page.clock.install({time:new Date(Date.now()+61_000)});
  return {setMode:(v:string)=>{mode=v},count:()=>refreshes};
}

test('a temporary background failure keeps the valid session and its usable module',async({page})=>{
 const state=await setup(page);state.setMode('temporary');
 const interrupted=page.waitForEvent('console',{predicate:msg=>msg.text().includes('EduSync session verification interrupted')});
 await page.evaluate(()=>window.dispatchEvent(new Event('edusync:session-retry')));await interrupted;
 expect(state.count()).toBeGreaterThanOrEqual(3);
 await expect(page.getByText('Impossible de vérifier votre session pour le moment.',{exact:true})).toHaveCount(0);
 const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/personnel'&&r.ok());
 await page.getByRole('button',{name:'Personnel',exact:true}).click();await response;
 await expect(page.getByRole('heading',{name:'Personnel · Espace de gestion',exact:true})).toBeVisible();
});

test('a legacy stale credential refused by identity ends at sign-in instead of retrying forever',async({page})=>{
 const state=await setup(page);state.setMode('stale');
 await page.evaluate(()=>window.dispatchEvent(new Event('edusync:session-retry')));
 await expect(page.getByLabel('Adresse e-mail',{exact:true})).toBeVisible();
 await expect(page.getByText('Impossible de vérifier votre session pour le moment.',{exact:true})).toHaveCount(0);
 expect(state.count()).toBeLessThanOrEqual(4);
});
