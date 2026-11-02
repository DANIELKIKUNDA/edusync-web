export const FINANCE_TARGET_KEY='edusync.finance.open';
// 'products': the « Autres encaissements » (articles for sale) part of the cash desk — home card « Articles à surveiller ».
export type FinanceTarget='checkout'|'products'|'recovery'|'cash'|'followup'|'reports'|'fees'|'import'|'controls';

export function setFinanceTarget(target:FinanceTarget){
  try{sessionStorage.setItem(FINANCE_TARGET_KEY,target)}catch{/* optional browser storage */}
  // The finance page may already be open (phone bar « Encaisser » while on « Caisse »): it switches tab at once.
  if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('edusync:finance-target',{detail:target}));
}
export function takeFinanceTarget():string{
  try{const v=sessionStorage.getItem(FINANCE_TARGET_KEY)||'';sessionStorage.removeItem(FINANCE_TARGET_KEY);return v}catch{return ''}
}
/** Reads the requested screen WITHOUT consuming it (2026-10-31): React may render a screen and discard that render (a
 *  lazy part still loading); consuming during render made « Superviser les caisses » open Recouvrement instead of Caisse.
 *  The page clears the request once it is really shown (clearFinanceTarget, in an effect). */
export function peekFinanceTarget():string{
  try{return sessionStorage.getItem(FINANCE_TARGET_KEY)||sessionStorage.getItem('edusync.finance.tab')||''}catch{return ''}
}
export function clearFinanceTarget(){
  try{sessionStorage.removeItem(FINANCE_TARGET_KEY);sessionStorage.removeItem('edusync.finance.tab')}catch{/* optional browser storage */}
}
