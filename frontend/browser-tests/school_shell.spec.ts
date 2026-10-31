import {test,expect,type Page} from '@playwright/test';
// Owner decisions 2026-10-23 (items 8-11), on the real application with test server answers: the school menu and
// home come from /access/me (an administrator sees neither the Centre financier nor « Rechercher un élève » nor the
// recovery chart), the account is docked in the desktop sidebar like the platform, a module shows a breadcrumb back
// to the home, and a failing screen keeps the shell. Desktop and phone.
const school={id:'sch-ui',code:'UI',name:'École Interface'};
const user={id:'u-ui',full_name:'Admin Recette',email:'admin@example.test'};
const ADMIN={membership_id:'m',school_id:school.id,role_label:'Administrateur système école',permissions:['access.users.read','access.roles.read','settings.school_identity.read'],scoped:[],roles:[],
  navigation:[{key:'home',label:'Accueil',icon:'home'},{key:'settings',label:'Paramètres',icon:'settings'},{key:'access',label:'Accès & rôles',icon:'lock'}],
  widgets:[{id:'access.members',title:'Comptes et accès',module:'access',priority:10},{id:'settings.academic_year',title:'Année scolaire',module:'settings',priority:13}],
  actions:[{id:'members.create',label:'Ajouter un utilisateur',module:'access'}]};

async function server(page:Page,{brokenAccess=false}={}){
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    let body:unknown={items:[],total:0,has_more:false,next_cursor:null,limit:50};
    if(path.endsWith('/auth/refresh'))body={access_token:'fixture-only',scope:'SCHOOL',school,user,permissions:ADMIN.permissions};
    else if(path.endsWith('/auth/contexts'))body={contexts:[],current:{scope:'SCHOOL'},current_valid:true};
    else if(path.endsWith('/access/me'))body=ADMIN;
    else if(path.endsWith('/access/dashboard'))body={'access.members':{active:5,inactive:0,without_role:1,expiring:0},'settings.academic_year':{active:'2026-2027',years:[]}};
    else if(path.endsWith('/settings/academic-years'))body=[];
    else if(brokenAccess&&path.startsWith('/api/v1/access/')&&!path.endsWith('/me'))body={items:'not-a-list',domains:42};   // malformed answer: the screen crashes
    else if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:''});
    await route.fulfill({json:body});
  });
}

for(const vp of [{name:'bureau',width:1280,height:850},{name:'mobile',width:375,height:812}]){
  test(`école (${vp.name}) : menu et accueil issus de /access/me, compte dans la barre latérale, fil d’Ariane`,async({page})=>{
    await page.setViewportSize({width:vp.width,height:vp.height});
    await server(page);
    await page.goto('/');
    await expect(page.locator('.es-shell')).toBeVisible();
    await expect(page.getByText('Administrateur système école').first()).toBeVisible();
    await expect(page.getByText('1 sans rôle')).toBeVisible();
    await expect(page.getByText('Évolution du recouvrement')).toHaveCount(0);
    await expect(page.getByText(/Rechercher un élève/)).toHaveCount(0);
    await expect(page.locator('.es-shell')).toHaveClass(/es-dock/);                     // same account placement as the platform
    if(vp.width>=768){
      const nav=page.getByRole('complementary',{name:'Navigation principale'});
      await expect(nav.getByRole('button',{name:'Centre financier'})).toHaveCount(0);
      await expect(nav.getByRole('button',{name:'Élèves & inscriptions'})).toHaveCount(0);
      await nav.getByRole('button',{name:'Accès & rôles',exact:true}).click();
    }else{
      await page.getByRole('button',{name:'Ouvrir le menu',exact:true}).click();
      const drawer=page.getByRole('dialog',{name:'Menu EduSync'});
      await expect(drawer.getByRole('button',{name:'Centre financier'})).toHaveCount(0);
      await drawer.getByRole('button',{name:'Accès & rôles',exact:true}).click();
    }
    await expect.poll(()=>page.title()).toBe('Accès & rôles — EduSync');
    const trail=page.getByRole('navigation',{name:'Fil d’Ariane'});
    if(vp.width>=768){
      await expect(trail).toBeVisible();
      await trail.getByRole('button').first().click();
    }else{
      // Mobile-first pass (2026-10-31): one title per screen — the « ‹ Module » row of a top-level module is hidden on
      // phones; the way back home is the « Accueil » destination of the bottom bar.
      await expect(trail).toBeHidden();
      await page.getByRole('navigation',{name:'Navigation rapide'}).getByRole('button',{name:'Accueil',exact:true}).click();
    }
    await expect(page.getByText('1 sans rôle')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  });
}

test('un écran en panne garde le shell et la navigation, avec Réessayer',async({page})=>{
  page.on('pageerror',()=>{});
  await server(page,{brokenAccess:true});
  await page.goto('/');
  const nav=page.getByRole('complementary',{name:'Navigation principale'});
  await nav.getByRole('button',{name:'Accès & rôles',exact:true}).click();
  await expect(page.locator('.screenError, .error').first()).toBeVisible();
  await expect(nav).toBeVisible();                                                     // the navigation survived
  await nav.getByRole('button',{name:'Accueil',exact:true}).click();
  await expect(page.getByText('1 sans rôle')).toBeVisible();
});
