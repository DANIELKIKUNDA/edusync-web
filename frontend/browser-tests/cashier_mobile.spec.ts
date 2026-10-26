import {test,expect} from '@playwright/test';

const school={id:'cashier-school',code:'REC',name:'École Recette'};
const user={id:'cashier-user',full_name:'Daniel Caissier',email:'cashier@example.test'};
const permissions=['finance.checkout.collect','finance.checkout.search','finance.checkout.balance.read'];
const person={student_id:'student-1',family_id:'family-1',matricule:'EDU-001',last_name:'KIKUNDA',middle_name:'',first_name:'Daniel',family_name:'Foyer Kikunda',enrollment_id:'enrollment-1',class_label:'2e CG'};

test('caissier mobile : recherche, montant unique, paiement et confirmation sans scroll horizontal',async({page})=>{
  await page.setViewportSize({width:375,height:812});
  let paid=false,collections=0;
  await page.route('**/api/**',async route=>{
    const req=route.request();const path=new URL(req.url()).pathname.replace('/api/v1','');
    if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:''});
    let body:unknown={items:[],total:0};
    if(path==='/auth/refresh')body={access_token:'fixture-cashier',scope:'SCHOOL',school,user,permissions};
    else if(path==='/auth/contexts')body={contexts:[],current:{scope:'SCHOOL'},current_valid:true};
    else if(path==='/access/me')body={membership_id:'cashier-member',school_id:school.id,role_label:'Caissier',permissions,scoped:[],roles:[],navigation:[{key:'home',label:'Accueil',icon:'home'},{key:'finance',label:'Centre financier',icon:'wallet'}],widgets:[],actions:[]};
    else if(path.startsWith('/finance/checkout/search'))body={items:[person]};
    else if(path.startsWith('/finance/checkout/balance/'))body={items:paid?[]:[{id:'fee-october',label:'Octobre',currency:'CDF',net_amount:'50000',paid_amount:'0',remaining:'50000',periodicity:'MONTHLY',eligible:true,requires:[]}]};
    else if(path.startsWith('/finance/checkout/registration-bundle/'))body={ready:false,items:[],totals:{}};
    else if(path.startsWith('/finance/checkout/fee-bundle/'))body={ready:false,items:[],totals:{}};
    else if(path==='/finance/checkout/payment-options')body={accepted_modes:['CASH'],partial_payments_enabled:true,partial_min_amount:'0',future_charge_payments_enabled:true,advance_payments_enabled:true};
    else if(path==='/finance/checkout/collect'){
      collections++;paid=true;body={id:'payment-1',receipt_number:'REC-001',amount:'50000',currency:'CDF',replayed:false};
    }
    return route.fulfill({json:body});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Ouvrir le menu',exact:true}).click();
  await page.getByRole('dialog',{name:'Menu EduSync'}).getByRole('button',{name:'Centre financier'}).click();
  const search=page.getByRole('textbox',{name:'Rechercher un élève ou une famille'});
  await expect(search).toBeVisible();await search.fill('Daniel');
  await page.getByRole('button',{name:/KIKUNDA.*Daniel/}).click();
  await page.getByRole('button',{name:/Octobre.*Reste/}).click();
  const mobile=page.getByRole('button',{name:/Voir \/ Encaisser/});
  await expect(mobile).toBeVisible();await mobile.click();
  const transaction=page.getByRole('complementary',{name:'Transaction active'});
  await expect(transaction).toBeVisible();
  await expect(transaction.getByText('50 000 FC').first()).toBeVisible();
  await transaction.getByRole('textbox',{name:'Montant remis par le parent'}).fill('50000');
  await transaction.getByRole('button',{name:'Encaisser maintenant'}).click();
  await expect(transaction.getByText(/Paiement enregistré · reçu REC-001/)).toBeVisible();
  expect(collections).toBe(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
