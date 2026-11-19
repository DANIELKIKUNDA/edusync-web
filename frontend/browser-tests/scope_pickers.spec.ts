import {test,expect} from '@playwright/test';
const catalogue=[{id:'m',code:'MATERNELLE',label:'Maternelle'},{id:'p',code:'PRIMAIRE',label:'Primaire'},{id:'s',code:'SECONDAIRE',label:'Secondaire'}];
for(const scenario of [
 {name:'préfet secondaire',codes:['SECONDAIRE'],school:false},
 {name:'direction primaire',codes:['PRIMAIRE'],school:false},
 {name:'direction maternelle',codes:['MATERNELLE'],school:false},
 {name:'sections maternelle et primaire réunies',codes:['MATERNELLE','PRIMAIRE'],school:false},
 {name:'responsable de toute l’école',codes:['MATERNELLE','PRIMAIRE','SECONDAIRE'],school:true},
])test(`effectifs : filtres du ${scenario.name}`,async({page})=>{
 const permissions=['headcounts.read','headcounts.by_class.read'];
 let selectorSeen=false,unexpectedWrites=0;
 const year={id:'y',code:'2026-2027',label:'2026-2027',status:'ACTIVE'};
 const zero={female:0,male:0,total:0};
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname;
  if(req.method()!=='GET'&&!path.includes('/auth/'))unexpectedWrites++;
  let body:any={items:[]};
  if(path.endsWith('/auth/refresh'))body={scope:'SCHOOL',access_token:'fixture-access',school:{id:'school',code:'TEST',name:'École de test'},user:{id:'test',email:'test@example.test',full_name:'Compte de test'},permissions};
  else if(path.endsWith('/auth/contexts'))body={contexts:[],current:{scope:'SCHOOL'},current_valid:true};
  else if(path.endsWith('/access/me'))body={membership_id:'m',school_id:'school',role_label:scenario.name,permissions,scoped:[],roles:[],navigation:[{key:'home',label:'Accueil',icon:'home'},{key:'headcounts',label:'Effectifs & dépôts',icon:'chart'}],widgets:[],actions:[]};
  else if(path.endsWith('/academic-years/selector'))body=[year];
  else if(path.endsWith('/structure/selector')){expect(url.searchParams.get('capability')).toBe('headcounts.by_class.read');selectorSeen=true;body={school_wide:scenario.school,sections:catalogue.filter(s=>scenario.codes.includes(s.code)),classes:[],options:[]};}
  else if(path.endsWith('/effectifs/overview'))body={academic_year:year,active_students:0,active_girls:0,active_boys:0,active_classes:0,average_per_class:0};
  else if(path.endsWith('/effectifs/counts'))body={academic_year:year,items:[],total:{enrolled:zero,abandoned:zero,transferred:zero,active:zero}};
  else if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:''});
  return route.fulfill({json:body});
 });
 await page.goto('/headcounts');
 const group=page.getByRole('group',{name:'Périmètre'});
 const expected=[...(scenario.school?['Toute l’école']:scenario.codes.length>1?['Sections autorisées']:[]),...catalogue.filter(s=>scenario.codes.includes(s.code)).map(s=>s.label)];
 await expect(group.getByRole('button')).toHaveText(expected);
 if(scenario.codes.length===1)await expect(group.getByRole('button')).toHaveAttribute('aria-pressed','true');
 expect(selectorSeen).toBe(true);expect(unexpectedWrites).toBe(0);
});
