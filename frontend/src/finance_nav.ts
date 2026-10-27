export const FINANCE_TARGET_KEY='edusync.finance.open';
export type FinanceTarget='checkout'|'recovery'|'cash'|'followup'|'reports'|'fees'|'import'|'controls';

export function setFinanceTarget(target:FinanceTarget){
  try{sessionStorage.setItem(FINANCE_TARGET_KEY,target)}catch{/* optional browser storage */}
}
export function takeFinanceTarget():string{
  try{const v=sessionStorage.getItem(FINANCE_TARGET_KEY)||'';sessionStorage.removeItem(FINANCE_TARGET_KEY);return v}catch{return ''}
}
