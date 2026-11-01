// @vitest-environment jsdom
import React from 'react';
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FinancePage from '../src/finance';

afterEach(()=>{cleanup();vi.unstubAllGlobals()});

it('searches by keyboard and resolves a registration prerequisite without losing the transaction',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{
    const path=String(input);
    let data:unknown={};
    if(path.includes('/finance/checkout/search?'))data={items:[{student_id:'student-1',family_id:'family-1',matricule:'EDU-001',last_name:'KIKUNDA',middle_name:'',first_name:'Daniel',family_name:'Foyer Kikunda',enrollment_id:'enrollment-1',class_label:'2e CG'}]};
    else if(path.includes('/finance/checkout/balance/'))data={items:[
      {id:'registration',label:'Frais d’inscription',currency:'CDF',net_amount:'20000',paid_amount:'0',remaining:'20000',periodicity:'ONE_OFF',eligible:true,requires:[]},
      {id:'october',label:'Octobre',currency:'CDF',net_amount:'50000',paid_amount:'0',remaining:'50000',periodicity:'MONTHLY',eligible:true,requires:[]}]};
    else if(path.includes('/finance/checkout/registration-bundle/'))data={ready:true,items:[{charge_id:'registration',fee_code:'INSCRIPTION',label:'Frais d’inscription',currency:'CDF',balance:'20000'}],totals:{CDF:'20000'}};
    else if(path.includes('/finance/checkout/payment-options'))data={accepted_modes:['CASH'],partial_payments_enabled:true,partial_min_amount:'0',future_charge_payments_enabled:true,advance_payments_enabled:true};
    else if(path.includes('/finance/checkout/fee-bundle/'))data={ready:false,items:[],totals:{}};
    return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
  }));
  render(<FinancePage token="test" permissions={['finance.checkout.collect','finance.checkout.search','finance.checkout.balance.read']}/>);
  const search=screen.getByRole('textbox',{name:'Rechercher un élève ou une famille'});
  await userEvent.type(search,'D');
  await waitFor(()=>expect(screen.getByRole('button',{name:/KIKUNDA.*Daniel/})).toBeTruthy());
  await userEvent.keyboard('{Enter}');
  await waitFor(()=>expect(screen.getByText('À payer maintenant')).toBeTruthy());
  await userEvent.click(screen.getByRole('button',{name:/Octobre.*Reste/}));
  expect(screen.getByText(/Paiement bloqué/)).toBeTruthy();
  await userEvent.click(screen.getByRole('button',{name:'Régler d’abord ces obligations'}));
  const transaction=screen.getByRole('complementary',{name:'Transaction active'});
  expect(within(transaction).getByText('70 000 FC')).toBeTruthy();
  // Phone dock: the selection is paid in one tap, details stay one tap away.
  const dock=screen.getByRole('region',{name:'Encaissement rapide'});
  expect(within(dock).getByRole('button',{name:/Encaisser 70\s000\sFC/})).toBeTruthy();
  expect(within(dock).getByRole('button',{name:/Détails/})).toBeTruthy();
});

it('keeps a committed family payment successful when the following balance refresh fails',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const person={student_id:'student-2',family_id:'family-2',matricule:'EDU-002',last_name:'SANGWA',middle_name:'',first_name:'Dorcas',family_name:'Foyer Sangwa',enrollment_id:'enrollment-2',class_label:'3e primaire'};
  let paid=false;
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{
    const path=String(input);
    if(path.includes('/finance/checkout/search?'))return new Response(JSON.stringify({items:[person]}),{status:200});
    if(path.includes('/finance/checkout/family/family-2/children'))return new Response(JSON.stringify({items:[person]}),{status:200});
    if(path.includes('/finance/checkout/balance/'))return paid?new Response(JSON.stringify({detail:'Rafraîchissement indisponible'}),{status:503}):new Response(JSON.stringify({items:[{id:'fee-2',label:'Octobre',currency:'CDF',net_amount:'50000',paid_amount:'0',remaining:'50000',periodicity:'MONTHLY',eligible:true,requires:[]}]}),{status:200});
    if(path.includes('/finance/checkout/family-collect')){paid=true;return new Response(JSON.stringify({basket_id:'basket-2',family_id:'family-2',totals:{CDF:'50000'},replayed:false,lines:[{line_no:1,payment_id:'payment-2',receipt_number:'REC-002',amount:'50000',currency:'CDF',last_name:'SANGWA',first_name:'Dorcas',class_label:'3e primaire',allocations:[]}]}),{status:200})}
    if(path.includes('/finance/checkout/payment-options'))return new Response(JSON.stringify({accepted_modes:['CASH'],partial_payments_enabled:true,partial_min_amount:'0',future_charge_payments_enabled:true,advance_payments_enabled:true}),{status:200});
    if(path.includes('/finance/checkout/registration-bundle/'))return new Response(JSON.stringify({ready:false,items:[],totals:{}}),{status:200});
    if(path.includes('/finance/checkout/fee-bundle/'))return new Response(JSON.stringify({ready:false,items:[],totals:{}}),{status:200});
    return new Response(JSON.stringify({items:[]}),{status:200});
  }));
  render(<FinancePage token="test" permissions={['finance.checkout.collect','finance.checkout.family.collect','finance.checkout.search','finance.checkout.balance.read']}/>);
  await userEvent.type(screen.getByRole('textbox',{name:'Rechercher un élève ou une famille'}),'D');
  await userEvent.click(await screen.findByRole('button',{name:/SANGWA.*Dorcas/}));
  await userEvent.click(screen.getByRole('button',{name:'+ Ajouter un enfant'}));
  await userEvent.click(await screen.findByRole('button',{name:/Octobre.*Reste/}));
  await userEvent.click(await screen.findByRole('button',{name:'Ajouter au panier'}));
  await userEvent.click(screen.getByRole('button',{name:'Encaisser le panier'}));
  await waitFor(()=>expect(screen.getByText(/Panier encaissé · 1 reçu/)).toBeTruthy());
  expect(screen.getByText(/Paiement enregistré ; actualisez les obligations/)).toBeTruthy();
});
