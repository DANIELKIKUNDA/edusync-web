import {test,expect,type Page} from '@playwright/test';
// Premium pass of the school space (2026-10-24): every main card is the entry point (no « Voir » button), touch targets
// ≥ 44 px on phones, visible keyboard focus, motion removed under prefers-reduced-motion, a readiness step opens its
// settings section with a breadcrumb down to it and a phone back control, and the shared scroll control is present.
const school={id:'sch-p',code:'P',name:'École Premium'};
const user={id:'u-p',full_name:'Daniel Admin',email:'admin@example.test'};
const perms=['access.users.read','access.roles.read','access.roles.manage','settings.school_identity.read','settings.academic_year.read','settings.structure.read','settings.fee_types.read','settings.tariffs.read'];
const me={membership_id:'m',school_id:school.id,role_label:'Administrateur système école',permissions:perms,scoped:[],roles:[],
  navigation:[{key:'home',label:'Accueil',icon:'home'},{key:'settings',label:'Paramètres',icon:'settings'},{key:'access',label:'Accès & rôles',icon:'lock'}],
  widgets:[{id:'access.members',title:'Comptes et accès',module:'access',priority:10},{id:'settings.readiness',title:'Paramétrage',module:'settings',priority:12},
    {id:'settings.academic_year',title:'Année scolaire',module:'settings',priority:13},{id:'audit.recent',title:'Dernières actions administratives',module:'access',priority:15}],
  actions:[{id:'members.create',label:'Ajouter un utilisateur',module:'access'},{id:'settings.open',label:'Compléter le paramétrage',module:'settings'}]};
const answers:Record<string,unknown>={
  '/auth/refresh':{access_token:'fixture-only',scope:'SCHOOL',school,user,permissions:perms},
  '/auth/contexts':{contexts:[],current:{scope:'SCHOOL'},current_valid:true},'/access/me':me,
  '/settings/reference-catalog':{sections:[],classes:[],fee_types:[]},
  '/access/dashboard':{'access.members':{active:9,inactive:0,without_role:1,expiring:0},'settings.academic_year':{active:'2026-2027',years:[]},
    'audit.recent':[{at:new Date().toISOString(),action:'ACADEMIC_YEAR_ACTIVATED',actor:'Daniel Admin'}]},
  '/settings/overview':{school:{id:school.id,code:'P',name:school.name,version:1},readiness:{percent:43,global_blocking:false,items:[
    {code:'IDENTITY',label:'Identité de l’école',state:'READY',detail:'Renseignée',blocking_only_for:[]},
    {code:'FEE_TYPES',label:'Types de frais',state:'TO_COMPLETE',detail:'Aucun type de frais',blocking_only_for:['finance']}]}},
};
async function server(page:Page){
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname.replace('/api/v1','');
    if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:''});
    await route.fulfill({json:answers[path]??(path.includes('/settings/')?[]:{items:[],total:0})});
  });
}

for(const vp of [{name:'bureau',width:1280,height:850},{name:'mobile',width:375,height:812}]){
  test(`accueil premium (${vp.name}) : cartes cliquables sans « Voir », libellés métier, cibles tactiles`,async({page})=>{
    await page.setViewportSize({width:vp.width,height:vp.height});
    await server(page);await page.goto('/');
    const home=page.locator('.sh-home');
    await expect(home.getByText('Bonjour Daniel')).toBeVisible();
    await expect(home.getByRole('button',{name:'Voir',exact:true})).toHaveCount(0);
    await expect(home.getByText('ACADEMIC_YEAR_ACTIVATED')).toHaveCount(0);
    await expect(home.getByText('Année scolaire activée').first()).toBeVisible();
    await expect(home.getByText('1 sans rôle')).toBeVisible();
    if(vp.width<768){
      const small=await page.locator('.sh-home button:visible').evaluateAll(els=>els.filter(e=>e.getBoundingClientRect().height<44).map(e=>e.textContent?.trim()));
      expect(small).toEqual([]);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
      await expect(page.locator('.pf-vertical')).toHaveCount(1);                       // shared scroll control (platform pattern)
    }
    await home.getByRole('button',{name:/Comptes et accès/}).click();                    // the whole card is the entry point
    await expect.poll(()=>page.title()).toBe('Accès & rôles — EduSync');
  });
}

test('focus clavier visible et animations coupées en reduced-motion',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  await server(page);await page.goto('/');
  const card=page.locator('.sh-home .ui-card-action').first();
  await card.focus();
  await page.keyboard.press('Shift+Tab');await page.keyboard.press('Tab');
  expect(await card.evaluate(e=>getComputedStyle(e).outlineStyle)).not.toBe('none');
  expect(await card.evaluate(e=>getComputedStyle(e).animationName)).toBe('none');
});

for(const vp of [{name:'bureau',width:1280,height:850},{name:'mobile',width:375,height:812}]){
  test(`paramètres (${vp.name}) : une étape du parcours ouvre sa section, fil d’Ariane et retour`,async({page})=>{
    await page.setViewportSize({width:vp.width,height:vp.height});
    await server(page);await page.goto('/');
    await page.locator('.sh-readiness').getByRole('button',{name:/Types de frais/}).click();
    await expect.poll(()=>page.title()).toBe('Types de frais — EduSync');            // the window title follows the open section
    const trail=page.getByRole('navigation',{name:'Fil d’Ariane'});
    if(vp.width>=768){
      await expect(trail.locator('.pf-trail-desktop [aria-current="page"]')).toHaveText('Types de frais');
      await trail.getByRole('button',{name:'Paramètres'}).click();
    }else{
      await trail.getByRole('button',{name:'Retour : Paramètres'}).click();            // premium phone back, not only Android's
    }
    await expect(page.getByRole('heading',{name:'Paramètres de l’établissement'})).toBeVisible();
    await expect(page.getByText('Votre parcours de paramétrage')).toBeVisible();
    await expect(page.locator('.sp-home').getByRole('button',{name:/Types de frais — À compléter/})).toBeVisible();
  });
}
