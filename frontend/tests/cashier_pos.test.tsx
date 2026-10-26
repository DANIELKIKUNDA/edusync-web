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
  expect(screen.getByRole('button',{name:/Voir \/ Encaisser/})).toBeTruthy();
});
