import type {EnrollmentBenefitView} from './api';
// Enrollment form helpers (owner report 2026-11-06): Congolese by default, benefits written in words, never a fee code.
export const DEFAULT_NATIONALITY='Congolaise';
export const NATIONALITIES=['Congolaise','Congolaise (Brazzaville)','Angolaise','Zambienne','Rwandaise','Burundaise','Tanzanienne','Ougandaise','Centrafricaine','Sud-Soudanaise','Camerounaise','Belge','Française'];
const FEE_WORDS:Record<string,string>={SCOLARITE:'minerval',MINERVAL:'minerval',INSCRIPTION:'frais d’inscription'};
const lower=(t:string)=>t.charAt(0).toLowerCase()+t.slice(1);
/** « gratuité : frais scolaires mensuels », « remise de 50 % : minerval » — the school's own fee names, never a code. */
export function benefitShort(v:{discount_percent:string;fee_code:string;fee_codes?:string[];fee_labels?:string[];all_fees?:boolean}){
  const fees=v.all_fees?'tous les frais':[...new Set(v.fee_labels?.length?v.fee_labels.map(lower):(v.fee_codes?.length?v.fee_codes:[v.fee_code]).map(c=>FEE_WORDS[String(c).toUpperCase()]??String(c).toLowerCase().replace(/_/g,' ')))].join(', ');
  const pct=Number(v.discount_percent);return pct>=100?`gratuité : ${fees}`:`remise de ${pct} % : ${fees}`}

/** Large-family benefit offered only from the school's threshold (enrolled + children of this form) and within the limit. */
export function largeFamilyState(v:EnrollmentBenefitView|null|undefined,batch:number,selected:number){if(!v)return {visible:false,total:0,remaining:0,canAdd:false};const total=(v.family_enrolled_children??0)+batch;const cap=v.per_group&&v.min_children>0?Math.floor(total/v.min_children)*Math.max(1,v.beneficiary_limit):v.beneficiary_limit;const remaining=v.per_group||v.beneficiary_limit>0?Math.max(0,cap-(v.family_beneficiaries??0)):Infinity;const visible=total>=v.min_children&&remaining>0;return {visible,total,remaining,canAdd:visible&&selected<remaining}}
