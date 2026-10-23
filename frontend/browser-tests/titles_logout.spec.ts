import {test,expect,type Page} from '@playwright/test';
// Lot 2026-10: window titles on every main platform route (navigation, deep link, back) and the confirmation of a
// voluntary sign-out (desktop and phone), on the real application with test server answers.
const labels:Record<string,string>={schools:'Écoles',access:'Utilisateurs & accès',team:'Équipe plateforme',notifications:'Notifications système',audit:'Journal d’audit',diagnostics:'État du service',messaging:'Messagerie'};
async function server(page:Page,state:{loggedOut:boolean}){
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    const user={id:'test-user',full_name:'Recette locale',email:'test@example.test'};
    let body:unknown={items:[],actions:[],total:0,has_more:false,next_cursor:null,limit:50};
    if(path.endsWith('/auth/logout')){state.loggedOut=true;return route.fulfill({status:204,body:''});}
    if(path.endsWith('/auth/refresh'))return state.loggedOut?route.fulfill({status:401,contentType:'application/json',body:'{"detail":"Session à renouveler"}'})
      :route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({access_token:'fixture-only',scope:'PLATFORM',user})});
    if(path.endsWith('/auth/contexts'))body={contexts:[],current:{scope:'PLATFORM'},current_valid:true};
    else if(path.endsWith('/identities/filters'))body={roles:[]};
    else if(path.endsWith('/platform/system/health'))body={checked_at:new Date().toISOString(),overall:'OK',components:[],alerts:[],refresh_seconds:30,shared:false,summary:{operational:0,configured:0,degraded:0,down:0,not_configured:0},figures:{}};
    else if(path.endsWith('/platform/team/me'))body={user,roles:[{code:'MANAGER_SYSTEME',label:'Manager Système',kind:'PLATFORM_STANDARD'}],permissions:[],
      menu:Object.entries(labels).map(([key,label])=>({key,label,capability:`test.${key}`}))};
    else if(path.endsWith('/platform/messaging/status'))body={channels:[{key:'push',channel:'PUSH',provider:'fcm',provider_label:'Firebase Cloud Messaging',config_state:'CONFIGURED',
      state:'CONFIGURED',reasons:['Identifiants Firebase valides'],simulated:false,health:null,volumes_24h:{}}],queue:{due:0,processing:0,retrying:0,dead_7d:0,failed_15m:0,worker_state:'OK'},measured_at:new Date().toISOString()};
    else if(path.endsWith('/stream'))return route.fulfill({status:200,contentType:'text/event-stream',body:''});
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  });
}
const once=(t:string)=>expect((t.match(/EduSync/g)||[]).length).toBe(1);

test('titles: every main route, deep link and browser back — « <page> — EduSync », never twice',async({page})=>{
  await server(page,{loggedOut:false});
  await page.goto('/?msg=channel:PUSH');                                         // deep link straight into a detail
  await expect.poll(()=>page.title()).toMatch(/ — EduSync$/);once(await page.title());
  expect(await page.title()).not.toContain('Gestion scolaire');
  const nav=page.getByRole('complementary',{name:'Navigation principale'});
  const seen:string[]=[];
  for(const label of Object.values(labels)){
    await nav.getByRole('button',{name:label,exact:true}).click();
    await expect.poll(()=>page.title()).toBe(`${label} — EduSync`);
    seen.push(await page.title());once(await page.title());
  }
  await page.goBack();
  await expect.poll(()=>page.title()).toBe(seen.at(-2)!);                      // back restores the previous screen title
  once(await page.title());
});

for(const viewport of [{name:'bureau',width:1280,height:850},{name:'mobile',width:375,height:812}]){
  test(`déconnexion (${viewport.name}) : confirmation, Annuler conserve la session, confirmer déconnecte`,async({page})=>{
    const state={loggedOut:false};
    await page.setViewportSize({width:viewport.width,height:viewport.height});
    await server(page,state);
    await page.goto('/');
    const open=async()=>{
      if(viewport.width<768){
        await page.getByRole('button',{name:'Ouvrir le menu',exact:true}).click();
        const drawer=page.getByRole('dialog',{name:'Menu EduSync'});
        await drawer.locator('.es-drawer-acct').click();
        await drawer.getByRole('button',{name:'Se déconnecter',exact:true}).click();
      }else{
        await page.getByRole('button',{name:/Ouvrir le menu du compte/}).click();
        await page.getByRole('menuitem',{name:'Se déconnecter'}).click();
      }
    };
    await open();
    const dialog=page.getByRole('alertdialog',{name:'Se déconnecter ?'});
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('Voulez-vous vraiment vous déconnecter de votre session EduSync ?');
    await expect.poll(()=>dialog.evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})).toBe(true);
    await dialog.getByRole('button',{name:'Annuler'}).click();
    await expect(dialog).toHaveCount(0);
    expect(state.loggedOut).toBe(false);
    await expect(page.locator('.es-shell')).toBeVisible();                       // still signed in
    await open();
    await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);expect(state.loggedOut).toBe(false);
    await open();
    await dialog.getByRole('button',{name:'Se déconnecter'}).click();
    await expect.poll(()=>state.loggedOut).toBe(true);
    await expect(page.getByRole('heading',{name:'Connexion'})).toBeVisible();
  });
}
