// Enrollment form helpers (owner report 2026-11-06): Congolese by default, benefits written in words, never a fee code.
export const DEFAULT_NATIONALITY='Congolaise';
export const NATIONALITIES=['Congolaise','Congolaise (Brazzaville)','Angolaise','Zambienne','Rwandaise','Burundaise','Tanzanienne','Ougandaise','Centrafricaine','Sud-Soudanaise','Camerounaise','Belge','Française'];
const FEE_WORDS:Record<string,string>={SCOLARITE:'minerval',MINERVAL:'minerval',INSCRIPTION:'frais d’inscription'};
export function benefitShort(v:{discount_percent:string;fee_code:string;fee_codes?:string[]}){const fees=[...new Set((v.fee_codes?.length?v.fee_codes:[v.fee_code]).map(c=>FEE_WORDS[String(c).toUpperCase()]??String(c).toLowerCase().replace(/_/g,' ')))].join(', ');const pct=Number(v.discount_percent);return pct>=100?`${fees} gratuit`:`${pct} % de remise sur le ${fees}`}
