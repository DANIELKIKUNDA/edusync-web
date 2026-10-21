import {test,expect} from '@playwright/test';
const labels:Record<string,string>={schools:'Écoles',audit:'Journal d’audit',messaging:'Messagerie',team:'Équipe plateforme',access:'Utilisateurs & accès',diagnostics:'État du service',notifications:'Notifications système'};
const roles=[
  {name:'Manager système',keys:Object.keys(labels)},
  {name:'Collaborateur standard',keys:['schools','audit']},
  {name:'Collaborateur avec capacités supplémentaires',keys:['schools','audit','messaging']},
  {name:'Rôle custom',keys:['audit']},
];
for(const role of roles){
  test(`${role.name}: effective menu, direct unauthorized link and mobile drawer`,async({page})=>{
    await page.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      const user={id:'test-user',full_name:'Recette locale',email:'test@example.test'};
      let body:unknown={items:[],actions:[],total:0,has_more:false,next_cursor:null,limit:50};
      if(path.endsWith('/auth/refresh'))body={access_token:'fixture-only',scope:'PLATFORM',user};
      else if(path.endsWith('/auth/contexts'))body={contexts:[],current:{scope:'PLATFORM'},current_valid:true};
      else if(path.endsWith('/platform/team/me'))body={user,roles:[{code:'CUSTOM_TEST',label:role.name,kind:'PLATFORM_CUSTOM'}],permissions:[],menu:role.keys.map(key=>({key,label:labels[key],capability:`test.${key}`}))};
      else if(path.endsWith('/platform/messaging/status'))body={channels:[{key:'push',channel:'PUSH',provider:'fcm',provider_label:'FCM',config_state:'CONFIGURED',state:'CONFIGURED',reasons:[],simulated:false,health:null,volumes_24h:{}}],queue:{},measured_at:new Date().toISOString()};
      else if(path.endsWith('/stream'))return route.fulfill({status:200,contentType:'text/event-stream',body:''});
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    });
    await page.goto('/?msg=channel:PUSH');
    const nav=page.getByRole('complementary',{name:'Navigation principale'});
    for(const key of Object.keys(labels)){
      const item=nav.getByRole('button',{name:labels[key],exact:true});
      if(role.keys.includes(key))await expect(item).toBeVisible();else await expect(item).toHaveCount(0);
    }
    // All four roles render the same shell/components, including custom roles.
    await expect(page.locator('.es-shell.es-dock')).toBeVisible();
    await expect(page.getByRole('heading',{level:2}).first()).toBeVisible();
    expect((await page.title()).match(/EduSync/g)).toHaveLength(1);
    await page.getByRole('button',{name:'Réduire le menu',exact:true}).click();
    await expect(page.locator('.es-shell')).toHaveClass(/es-collapsed/);
    await page.keyboard.press('Tab');await expect(page.locator('.es-side')).toHaveClass(/es-peek/);
    await page.keyboard.press('Escape');await expect(page.locator('.es-side')).not.toHaveClass(/es-peek/);
    await page.setViewportSize({width:360,height:800});
    await page.getByRole('button',{name:'Ouvrir le menu',exact:true}).click();
    const drawer=page.getByRole('dialog',{name:'Menu EduSync'});await expect(drawer).toBeVisible();
    await expect.poll(()=>drawer.evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})).toBe(true);
    for(const key of Object.keys(labels))await expect(drawer.getByRole('button',{name:labels[key],exact:true})).toHaveCount(role.keys.includes(key)?1:0);
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:`${process.env.EDUSYNC_TEST_OUTPUT||'test-results'}/role-${role.keys.join('-')}-360.png`});
  });
}
