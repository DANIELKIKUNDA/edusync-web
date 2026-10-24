import {test,type Page} from '@playwright/test';
// Visual comparison captures (before / after a UI pass): school home and settings, desktop and phone, with fixed
// server answers so both runs show exactly the same data. Run only on demand:
//   EDUSYNC_CAPTURE=before|after EDUSYNC_TEST_BROWSER=msedge node browser-tests/run.mjs capture_school.spec.ts
const tag=process.env.EDUSYNC_CAPTURE;
test.skip(!tag,'captures on demand only');
const out=`${process.env.EDUSYNC_CAPTURE_DIR||'../.local/captures'}`;
const school={id:'sch-cap',code:'EXC',name:'Excellencia Collège Riziki'};
const user={id:'u-cap',full_name:'Daniel Admin',email:'admin@example.test'};
const perms=['access.users.read','access.users.create','access.roles.read','access.roles.manage','settings.school_identity.read','settings.academic_year.read','settings.structure.read',
  'settings.fee_types.read','settings.tariffs.read','settings.payment_policy.read','settings.enrollment_policy.read','settings.benefits.read','settings.contributions.read','settings.products.read',
  'finance.anticipation_plans.read','audit.school.read','sync.status.read','notifications.internal.read'];
const me={membership_id:'m',school_id:school.id,role_label:'Administrateur système école',permissions:perms,scoped:[],roles:[],
  navigation:[['home','Accueil','home'],['settings','Paramètres','settings'],['personnel','Personnel','users'],['documents','Documents','folder'],['sync','Synchronisation','sync'],
    ['communications','Communication','bell'],['access','Accès & rôles','lock']].map(([key,label,icon])=>({key,label,icon})),
  widgets:[['access.members','Comptes et accès','access',10],['access.requests','Demandes d’approbation','access',11],['settings.readiness','Paramétrage de l’établissement','settings',12],
    ['settings.academic_year','Année scolaire','settings',13],['settings.structure','Structure : sections et classes','settings',14],['audit.recent','Dernières actions administratives','access',15],
    ['sync.devices','Appareils et synchronisation','sync',16]].map(([id,title,module,priority])=>({id,title,module,priority})),
  actions:[{id:'members.create',label:'Ajouter un utilisateur',module:'access'},{id:'settings.open',label:'Compléter le paramétrage',module:'settings'}]};
const now=Date.now();
const answers:Record<string,unknown>={
  '/auth/refresh':{access_token:'fixture-only',scope:'SCHOOL',school,user,permissions:perms},
  '/auth/contexts':{contexts:[],current:{scope:'SCHOOL'},current_valid:true},
  '/access/me':me,
  '/access/dashboard':{'access.members':{active:12,inactive:1,without_role:2,expiring:1},'access.requests':{pending:1,adjusted_roles:2},
    'settings.academic_year':{active:'2026-2027',years:[{label:'2026-2027',status:'ACTIVE'}]},'settings.structure':{sections:2,classes:14},
    'audit.recent':[{at:new Date(now-36e5).toISOString(),action:'ACADEMIC_YEAR_ACTIVATED',actor:'Daniel Admin'},{at:new Date(now-72e5).toISOString(),action:'ACCESS_ROLE_ASSIGNED',actor:'Daniel Admin'},
      {at:new Date(now-864e5).toISOString(),action:'SETTINGS_FEE_TYPE_CREATED',actor:'Grâce Mbuyi'},{at:new Date(now-2*864e5).toISOString(),action:'ACCESS_MEMBER_CREATED',actor:'Daniel Admin'}]},
  '/settings/overview':{school:{id:school.id,code:school.code,name:school.name,email:'contact@riziki.cd',phone:'+243 81 000 0000',city:'Lubumbashi',province:'Haut-Katanga',version:3},
    readiness:{percent:43,global_blocking:false,items:[
      {code:'IDENTITY',label:'Identité de l’école',state:'READY',detail:'Nom, coordonnées et logo renseignés',blocking_only_for:[]},
      {code:'ACADEMIC_YEAR',label:'Année scolaire active',state:'READY',detail:'2026-2027 est active',blocking_only_for:[]},
      {code:'STRUCTURE',label:'Sections et classes',state:'READY',detail:'14 classes ouvertes',blocking_only_for:[]},
      {code:'FEE_TYPES',label:'Types de frais',state:'TO_COMPLETE',detail:'Aucun type de frais : les inscriptions payantes sont impossibles',blocking_only_for:['finance']},
      {code:'TARIFFS',label:'Tarifs et barèmes',state:'TO_COMPLETE',detail:'Aucun tarif pour l’année active',blocking_only_for:['finance']},
      {code:'PAYMENT_POLICY',label:'Règles d’encaissement',state:'TO_CONFIRM',detail:'Valeurs par défaut à confirmer',blocking_only_for:[]},
      {code:'DOCUMENTS',label:'Documents et reçus',state:'TO_CONFIRM',detail:'Préfixes et signature à vérifier',blocking_only_for:[]}]}},
  '/settings/academic-years':[{id:'y1',code:'2026-2027',label:'2026-2027',start_date:'2026-09-01',end_date:'2027-07-02',status:'ACTIVE',version:1}],
};
async function server(page:Page){
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname.replace('/api/v1','');
    if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:''});
    const body=answers[path]??(path.includes('/settings/')?[]:{items:[],total:0});
    await route.fulfill({json:body});
  });
}
for(const vp of [{name:'desktop',width:1366,height:900},{name:'mobile',width:390,height:844}]){
  test(`capture ${vp.name}`,async({page})=>{
    await page.setViewportSize({width:vp.width,height:vp.height});
    await page.emulateMedia({reducedMotion:'reduce'});
    await server(page);
    await page.goto('/');
    await page.getByText('Administrateur système école').first().waitFor();
    await page.waitForTimeout(600);
    await page.screenshot({path:`${out}/${tag}-dashboard-${vp.name}.png`,fullPage:true});
    if(vp.width<768){await page.getByRole('button',{name:'Ouvrir le menu',exact:true}).click();await page.getByRole('dialog',{name:'Menu EduSync'}).getByRole('button',{name:'Paramètres',exact:true}).click()}
    else await page.getByRole('complementary',{name:'Navigation principale'}).getByRole('button',{name:'Paramètres',exact:true}).click();
    await page.waitForTimeout(800);
    await page.screenshot({path:`${out}/${tag}-settings-${vp.name}.png`,fullPage:true});
  });
}
