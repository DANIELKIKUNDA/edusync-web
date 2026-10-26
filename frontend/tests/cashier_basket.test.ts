// @vitest-environment jsdom
import {beforeEach,describe,expect,it} from 'vitest';
import {clearAllCashierBaskets,loadCashierBasket,saveCashierBasket,type CashierBasketLine} from '../src/platform/cashier_basket';
const user='00000000-0000-0000-0000-000000000001',school='00000000-0000-0000-0000-000000000002',other='00000000-0000-0000-0000-000000000003';
const token=(sub:string)=>`x.${btoa(JSON.stringify({sub,school_id:school}))}.x`;
const line:CashierBasketLine={enrollment_id:'00000000-0000-0000-0000-000000000004',family_id:'00000000-0000-0000-0000-000000000005',child:'Élève test',charge_ids:['00000000-0000-0000-0000-000000000006'],labels:['Inscription'],amount:'20000',currency:'CDF'};
beforeEach(()=>localStorage.clear());
describe('cashier basket draft',()=>{
 it('survives reload but never crosses accounts',()=>{saveCashierBasket(token(user),[line]);expect(loadCashierBasket(token(user))).toEqual([line]);expect(loadCashierBasket(token(other))).toEqual([])});
 it('rejects stale or malformed drafts',()=>{const key=`edusync.cashier-basket.${school}.${user}`;localStorage.setItem(key,JSON.stringify({saved_at:Date.now()-25*60*60*1000,lines:[line]}));expect(loadCashierBasket(token(user))).toEqual([]);localStorage.setItem(key,JSON.stringify({saved_at:Date.now(),lines:[{...line,charge_ids:['bad']}]}));expect(loadCashierBasket(token(user))).toEqual([])});
 it('clears private drafts at logout',()=>{saveCashierBasket(token(user),[line]);clearAllCashierBaskets();expect(loadCashierBasket(token(user))).toEqual([])});
});
