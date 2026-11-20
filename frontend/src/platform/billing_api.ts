import {UserFacingError, friendlyHttpMessage} from './errors';

const API=import.meta.env.VITE_API_BASE_URL??'/api/v1';
const B=`${API}/platform/billing`;
export type Module={code:string;label:string;description:string;status:'ACTIVE'|'DRAFT'|'RETIRED';dependencies:string[];version:number};
export type Plan={id:string;code:string;name:string;description:string;status:string;public_offer:boolean;version:number;version_count:number};
export type PlanVersion={id:string;plan_id:string;version:number;billing_cycle:'MONTHLY'|'QUARTERLY'|'ANNUAL';currency:'USD'|'CDF';amount:string;trial_days:number;grace_days:number;effective_from:string;effective_until:string|null;status:string;module_codes:string[]};
export type Subscription={id:string;school_id:string;school_name:string;plan_version_id:string;plan_name:string;billing_cycle:string;status:string;current_period_start:string;current_period_end:string;next_billing_on:string|null;grace_days:number;auto_renew:boolean;version:number;amount:string;currency:string};
export type Invoice={id:string;invoice_number:string;school_id:string;school_name:string;subscription_id:string|null;status:string;currency:string;period_start:string;period_end:string;issued_at:string|null;due_at:string|null;subtotal:string;discount_total:string;fee_total:string;total:string;paid_total:string;version:number};
export type Payment={id:string;payment_reference:string;invoice_id:string;invoice_number:string;school_id:string;school_name:string;provider:string;provider_reference:string|null;channel:string;status:string;currency:string;amount:string;confirmed_at:string|null;created_at:string};

async function req<T>(token:string,path:string,init:RequestInit={}):Promise<T>{
 const r=await fetch(`${B}${path}`,{...init,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json',...(init.headers||{})}});
 if(!r.ok){let msg=friendlyHttpMessage(r.status);try{const j=await r.json();msg=typeof j.detail==='string'?j.detail:(j.detail?.message||msg)}catch{/* générique */}throw new UserFacingError(msg,String(r.status))}
 if(r.status===204)return undefined as T;return r.json();
}
const key=()=>crypto.randomUUID();
export const getCatalog=(t:string)=>req<{modules:Module[];plans:Plan[]}>(t,'/catalog');
export const getPlanVersions=(t:string,id:string)=>req<PlanVersion[]>(t,`/plans/${id}/versions`);
export const getSubscriptions=(t:string)=>req<Subscription[]>(t,'/subscriptions?limit=200');
export const getInvoices=(t:string)=>req<Invoice[]>(t,'/invoices?limit=200');
export const getPayments=(t:string)=>req<Payment[]>(t,'/payments?limit=100');
export const createPlan=(t:string,b:{code:string;name:string;description:string;public_offer:boolean})=>req<Plan>(t,'/plans',{method:'POST',body:JSON.stringify(b),headers:{'Idempotency-Key':key()}});
export const createPlanVersion=(t:string,id:string,b:{billing_cycle:string;currency:string;amount:string;trial_days:number;grace_days:number;effective_from:string;module_codes:string[]})=>req<PlanVersion>(t,`/plans/${id}/versions`,{method:'POST',body:JSON.stringify(b),headers:{'Idempotency-Key':key()}});
export const publishPlanVersion=(t:string,id:string,version:number,reason:string)=>req<{id:string;status:string}>(t,`/plan-versions/${id}/publish`,{method:'POST',body:JSON.stringify({version,reason})});
export const issueInvoice=(t:string,id:string,b:{period_start:string;due_days:number;discount_total:string;fee_total:string;reason:string})=>req<Invoice>(t,`/subscriptions/${id}/invoices`,{method:'POST',body:JSON.stringify(b),headers:{'Idempotency-Key':key()}});
export const recordPayment=(t:string,id:string,b:{amount:string;currency:string;provider:string;provider_reference:string;reason:string})=>req<Payment&{invoice_status:string}>(t,`/invoices/${id}/payments/manual`,{method:'POST',body:JSON.stringify(b),headers:{'Idempotency-Key':key()}});

