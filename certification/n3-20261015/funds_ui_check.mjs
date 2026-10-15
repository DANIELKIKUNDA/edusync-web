// N3-D — fonds anticipés UI: cash-desk panel (cashier) and credits register (GESTIONNAIRE) on phone and desktop.
// Uses the last school created by advance_funds_probe.py (credentials from the private fixtures, never printed).
import {connect, delay, fx, signInSchool} from '../n2-20261014/cdp.mjs';
const runs = Object.values(fx.N3D || {}); const school = runs[runs.length - 1];
if (!school) { console.log('Lancez d’abord advance_funds_probe.py'); process.exit(1); }
const p = await connect(); let fail = 0;
const ok = (name, cond, extra = '') => { if (!cond) fail++; console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };
async function finance(w) {
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
    await p.ev('[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.toLowerCase().includes("financ")).click()'); }
  else await p.ev('[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||b.innerText).toLowerCase().includes("financ")).click()');
  await p.waitFor('!!document.querySelector(".financePage")', 20000); await delay(800);
}
await signInSchool(p, school.users.CASH.email, school.users.CASH.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200); await finance(w);
  await p.type('[aria-label="Rechercher un élève ou une famille"]', 'FON'); await p.waitFor('!!document.querySelector(".checkoutHits button")', 15000);
  await p.ev('document.querySelector(".checkoutHits button").click()');
  await p.waitFor('!!document.querySelector(".fundsPanel li")', 15000).catch(() => {});
  ok(`${w}px caissier : panneau fonds anticipés avec ses fonds`, await p.ev('document.querySelectorAll(".fundsPanel li").length>=1'));
  ok(`${w}px caissier : bouton « Recevoir un fonds »`, await p.ev('[...document.querySelectorAll(".fundsPanel button")].some(b=>b.innerText.includes("Recevoir"))'));
  await p.ev('document.querySelector(".fundsPanel")?.scrollIntoView()'); await delay(300);
  await p.shot(`n3d-funds-cashier-${w}`, true);
  const m = await p.metrics(); ok(`${w}px caissier : pas de défilement horizontal`, !m.hscroll, JSON.stringify(m.over));
}
await signInSchool(p, school.users.GES.email, school.users.GES.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200); await finance(w);
  await p.ev('[...document.querySelectorAll("button")].find(b=>b.innerText.trim()==="Décisions financières")?.click()'); await delay(800);
  await p.ev('[...document.querySelectorAll("button")].find(b=>b.innerText.includes("Crédits"))?.click()'); await delay(1200);
  await p.ev('(()=>{const s=[...document.querySelectorAll(".reportControls select")].pop();if(s){const set=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value").set;set.call(s,"ALL");s.dispatchEvent(new Event("change",{bubbles:true}))}})()'); await delay(1200);
  ok(`${w}px gestionnaire : registre des crédits (fonds et crédits de décision)`, await p.ev('document.querySelectorAll(".cashSummaryTable tbody tr").length>=3'));
  await p.shot(`n3d-credits-${w}`, true);
  const m = await p.metrics(); ok(`${w}px gestionnaire : pas de défilement horizontal`, !m.hscroll, JSON.stringify(m.over));
}
const errs = p.consoleErrors.filter(e => !e.includes('HTTP 401'));
ok('aucune erreur console', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(fail ? `UI N3-D : ${fail} échec(s)` : 'UI N3-D : PASS');
process.exit(fail ? 1 : 0);
