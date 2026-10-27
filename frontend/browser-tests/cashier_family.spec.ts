import {test,expect,type Page} from '@playwright/test';

const school={id:'11111111-1111-4111-8111-111111111111',code:'REC',name:'École Recette'};
const user={id:'22222222-2222-4222-8222-222222222222',full_name:'Daniel Caissier',email:'cashier@example.test'};
const family='33333333-3333-4333-8333-333333333333';
const cashierToken=`e30.${btoa(JSON.stringify({sub:user.id,school_id:school.id}))}.sig`;
const person=(n:number,name:string)=>({student_id:`44444444-4444-4444-8444-44444444444${n}`,family_id:family,matricule:`EDU-00${n}`,last_name:'KIKUNDA',middle_name:'',first_name:name,family_name:'Foyer Kikunda',enrollment_id:`55555555-5555-4555-8555-55555555555${n}`,class_label:n===1?'2e CG':'3e primaire'});
const children=[person(1,'Daniel'),person(2,'Dorcas')];
const fees:Record<string,string>={[children[0].enrollment_id]:'66666666-6666-4666-8666-666666666661',[children[1].enrollment_id]:'66666666-6666-4666-8666-666666666662'};
const permissions=['finance.checkout.collect','finance.checkout.family.collect','finance.checkout.search','finance.checkout.balance.read','finance.cash.read'];

async function prepare(page:Page,ambiguous=false){
  let attempts=0;const keys:string[]=[];
  await page.route('**/api/**',async route=>{
    const req=route.request();const path=new URL(req.url()).pathname.replace('/api/v1','');
    if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:''});
    let body:unknown={items:[],total:0};
    if(path==='/auth/refresh')body={access_token:cashierToken,scope:'SCHOOL',school,user,permissions};
    else if(path==='/auth/contexts')body={contexts:[],current:{scope:'SCHOOL'},current_valid:true};
    else if(path==='/access/me')body={membership_id:'cashier-member',school_id:school.id,role_label:'Caissier',permissions,scoped:[],roles:[],navigation:[{key:'home',label:'Accueil',icon:'home'},{key:'finance',label:'Centre financier',icon:'wallet'}],widgets:[],actions:[]};
    else if(path.startsWith('/finance/checkout/search'))body={items:[children[0]]};
    else if(path.startsWith('/finance/checkout/family/'))body={items:children};
    else if(path.startsWith('/finance/checkout/balance/')){
      const enrollment=path.split('/').pop()!;const fee=fees[enrollment];
      body={items:fee?[{id:fee,label:enrollment===children[0].enrollment_id?'Octobre':'Septembre',currency:'CDF',net_amount:'50000',paid_amount:'0',remaining:'50000',periodicity:'MONTHLY',eligible:true,requires:[]}]:[]};
    }
    else if(path.startsWith('/finance/checkout/registration-bundle/'))body={ready:true,items:[],totals:{}};
    else if(path.startsWith('/finance/checkout/fee-bundle/'))body={ready:false,items:[],totals:{}};
    else if(path==='/finance/checkout/payment-options')body={accepted_modes:['MOBILE_MONEY'],partial_payments_enabled:true,partial_min_amount:'0',future_charge_payments_enabled:true,advance_payments_enabled:true};
    else if(path==='/finance/checkout/family-collect'){
      attempts++;
      const submitted=req.postDataJSON();
      expect(submitted.mode).toBe('MOBILE_MONEY');
      expect(submitted.reference).toBe('MM-1234');
      keys.push(req.headers()['idempotency-key']);
      if(attempts===1)return route.fulfill({status:409,json:{detail:ambiguous?'Réponse du serveur perdue':'Aucune caisse ouverte pour cet utilisateur'}});
      body={basket_id:'basket-1',family_id:family,totals:{CDF:'100000'},replayed:ambiguous,lines:children.map((child,i)=>({line_no:i+1,payment_id:`payment-${i+1}`,receipt_number:`REC-${i+1}`,amount:'50000',currency:'CDF',last_name:child.last_name,first_name:child.first_name,class_label:child.class_label,allocations:[]}))};
    }
    return route.fulfill({json:body});
  });
  await page.goto('/');
  if((page.viewportSize()?.width??0)<900){
    const menu=page.getByRole('button',{name:'Ouvrir le menu',exact:true});
    await expect(menu).toBeVisible();
    await menu.click();
    await page.getByRole('dialog',{name:'Menu EduSync'}).getByRole('button',{name:'Centre financier'}).click();
  }else{
    const finance=page.getByRole('complementary',{name:'Navigation principale'}).getByRole('button',{name:'Centre financier'});
    await expect(finance).toBeVisible();
    await finance.click();
  }
  await page.getByRole('textbox',{name:'Rechercher un élève ou une famille'}).fill('Daniel');
  await page.getByRole('button',{name:/KIKUNDA.*Daniel/}).first().click();
  await page.getByRole('button',{name:/Ajouter un enfant/}).click();
  await expect(page.getByRole('button',{name:/Dorcas.*3e primaire/})).toBeVisible();
  await page.getByRole('button',{name:/Octobre.*Reste/}).click();
  if(await page.getByRole('button',{name:/Voir \/ Encaisser/}).isVisible())await page.getByRole('button',{name:/Voir \/ Encaisser/}).click();
  await page.getByRole('button',{name:'Ajouter au panier'}).click();
  if(await page.getByRole('button',{name:'Fermer la transaction'}).first().isVisible())await page.getByRole('button',{name:'Fermer la transaction'}).first().click();
  await page.getByRole('button',{name:/Dorcas.*3e primaire/}).click();
  await page.getByRole('button',{name:/Septembre.*Reste/}).click();
  if(await page.getByRole('button',{name:/Voir \/ Encaisser/}).isVisible())await page.getByRole('button',{name:/Voir \/ Encaisser/}).click();
  await page.getByRole('button',{name:'Ajouter au panier'}).click();
  return {attempts:()=>attempts,keys};
}

for(const vp of [{name:'desktop',width:1440,height:900},{name:'desktop-court',width:1280,height:650},{name:'mobile',width:375,height:812}]){
  test(`famille caisse — ${vp.name}`,async({page},testInfo)=>{
    await page.setViewportSize({width:vp.width,height:vp.height});
    const result=await prepare(page);
    if(vp.name==='mobile' && !await page.getByRole('complementary',{name:'Transaction active'}).isVisible())await page.getByRole('button',{name:/Voir \/ Encaisser/}).click();
    const aside=page.getByRole('complementary',{name:'Transaction active'});
    await expect(aside.getByText('Panier familial · 2 ligne(s)')).toBeVisible();
    await aside.getByRole('textbox',{name:'Référence de transaction du panier'}).fill('MM-1234');
    if(vp.name==='desktop-court')await page.evaluate(()=>{document.querySelectorAll('*').forEach(el=>{if(el.scrollTop>0)el.scrollTop=0});window.scrollTo(0,0)});
    await page.screenshot({path:testInfo.outputPath(`${vp.name}-before.png`),fullPage:false});
    const button=aside.getByRole('button',{name:'Encaisser le panier'});
    await expect(button).toBeEnabled();
    const box=await button.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y+box!.height).toBeLessThanOrEqual(vp.height);
    await button.click();
    await expect(aside.locator('.basketActionError')).toContainText('Aucune caisse ouverte pour cet utilisateur');
    expect(result.attempts()).toBe(1);
    await expect(aside.getByRole('button',{name:'Ouvrir la caisse'})).toBeVisible();
    await page.screenshot({path:testInfo.outputPath(`${vp.name}-error.png`),fullPage:false});
    await button.click();
    await expect(aside.getByText('Panier encaissé · 2 reçu(s)')).toBeVisible();
    expect(result.attempts()).toBe(2);expect(result.keys[0]).toBe(result.keys[1]);
    await page.screenshot({path:testInfo.outputPath(`${vp.name}-success.png`),fullPage:false});  });
}

test('panier partiellement payé : reprise après réponse perdue réutilise la clé',async({page})=>{
  await page.setViewportSize({width:1440,height:900});
  const result=await prepare(page,true);
  let aside=page.getByRole('complementary',{name:'Transaction active'});
  await aside.getByRole('textbox',{name:'Référence de transaction du panier'}).fill('MM-1234');
  await aside.getByRole('button',{name:'Encaisser le panier'}).click();
  await expect(aside.locator('.basketActionError')).toContainText('Réponse du serveur perdue');
  expect(result.attempts()).toBe(1);
  expect((await page.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('edusync.cashier-basket.')))).length).toBe(2);
  await page.reload();
  const finance=page.getByRole('complementary',{name:'Navigation principale'}).getByRole('button',{name:'Centre financier'});
  await expect(finance).toBeVisible();
  await finance.click();
  await expect(page.getByText('Panier familial retrouvé')).toBeVisible();
  await page.getByRole('button',{name:'Reprendre et vérifier'}).click();
  aside=page.getByRole('complementary',{name:'Transaction active'});
  await expect(aside.getByText('Panier familial · 2 ligne(s)')).toBeVisible();
  await aside.getByRole('textbox',{name:'Référence de transaction du panier'}).fill('MM-1234');
  await aside.getByRole('button',{name:'Encaisser le panier'}).click();
  await expect(aside.getByText('Panier encaissé · 2 reçu(s) (déjà enregistré)')).toBeVisible();
  expect(result.keys).toHaveLength(2);
  expect(result.keys[1]).toBe(result.keys[0]);
});

test('panier restauré avec période antérieure impayée : refus visible avant tout encaissement',async({page})=>{
  await page.setViewportSize({width:1440,height:900});
  const result=await prepare(page);
  const earlier='77777777-7777-4777-8777-777777777777';
  await page.route('**/api/v1/finance/checkout/balance/**',async route=>{
    const enrollment=new URL(route.request().url()).pathname.split('/').pop();
    if(enrollment!==children[0].enrollment_id)return route.fallback();
    return route.fulfill({json:{items:[
      {id:earlier,label:'Frais scolaires mensuels — Septembre',period_label:'Septembre',currency:'CDF',net_amount:'55000',paid_amount:'0',remaining:'55000',periodicity:'MONTHLY',eligible:true,requires:[]},
      {id:fees[enrollment],label:'Frais scolaires mensuels — Octobre',period_label:'Octobre',currency:'CDF',net_amount:'50000',paid_amount:'0',remaining:'50000',periodicity:'MONTHLY',eligible:false,lock_reason:'Septembre doit être soldé d’abord',requires:[earlier]}
    ]}});
  });
  await page.reload();
  const finance=page.getByRole('complementary',{name:'Navigation principale'}).getByRole('button',{name:'Centre financier'});
  await finance.click();
  await page.getByRole('button',{name:'Reprendre et vérifier'}).click();
  const aside=page.getByRole('complementary',{name:'Transaction active'});
  await expect(aside.locator('.basketActionError')).toContainText('Octobre exige d’abord Septembre');
  await expect(aside.getByRole('button',{name:'Modifier'}).first()).toBeVisible();
  await aside.getByRole('button',{name:'Encaisser le panier'}).click();
  await expect(aside.locator('.basketActionError')).toContainText('Octobre exige d’abord Septembre');
  await aside.getByRole('button',{name:'Modifier'}).first().click();
  await page.getByText('À venir · obligations sous conditions').click();
  await page.getByRole('button',{name:/Octobre.*Septembre doit être soldé d’abord/}).click();
  await expect(page.getByRole('region',{name:'Paiement'})).toHaveCount(0);
  expect(result.attempts()).toBe(0);
});
