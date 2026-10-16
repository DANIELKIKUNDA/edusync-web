// N3-H — schooling parity UI (CAISSIER for schooling, GESTIONNAIRE for the article sales report and the contribution register), phone and desktop.
// Uses the last school created by schooling_parity_probe.py (credentials from the private fixtures, never printed).
import {connect, delay, fx, signInSchool, signOut} from '../n2-20261014/cdp.mjs';
const runs = Object.entries(fx.N3H || {}); const [run, school] = runs[runs.length - 1] || [];
if (!school) { console.log('Lancez d’abord schooling_parity_probe.py'); process.exit(1); }
const p = await connect(); let fail = 0;
const ok = (name, cond, extra = '') => { if (!cond) fail++; console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };
const click = (sel, txt) => p.ev(`[...document.querySelectorAll(${JSON.stringify(sel)})].find(b=>b.innerText.trim().toLowerCase().includes(${JSON.stringify(txt.toLowerCase())}))?.click()`);
async function nav(w, label) {
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
    const found = await p.ev(`(()=>{const b=[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.toLowerCase().includes(${JSON.stringify(label)}));b?.click();return b?'':JSON.stringify([...document.querySelectorAll(".es-drawer-nav button,.es-bottom button")].map(x=>x.innerText.trim()))})()`);
    if (found) console.log('NAV', label, found); }
  else await p.ev(`[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||b.innerText).toLowerCase().includes(${JSON.stringify(label)})).click()`);
  await delay(1500);
}
const setInput = (sel, v) => p.ev(`(()=>{const i=document.querySelector(${JSON.stringify(sel)});if(!i)return false;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,${JSON.stringify(v)});i.dispatchEvent(new Event('input',{bubbles:true}));return true})()`);

await signInSchool(p, school.users.CASH.email, school.users.CASH.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
  await nav(w, 'élèves');
  await click('.schoolingTabs button', 'Familles'); await delay(1500);
  ok(`${w}px : indicateurs familles et qualité des contacts`, await p.ev('!!document.querySelector(".familyKpis")&&!!document.querySelector(".familyDiag")'));
  await click('.familyKpis button', 'Familles nombreuses'); await delay(1000);
  ok(`${w}px : détail d’un indicateur famille`, await p.ev('document.querySelectorAll(".familyInsights .dayDetails li").length>=1'));
  let m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (familles)`, !m.hscroll, JSON.stringify(m.over));
  await p.shot(`n3h-families-${w}`, true);
  await click('.schoolingTabs button', 'Annuaire'); await delay(1500);
  await click('.studentRow', `dupont${run}`); await delay(1800);
  ok(`${w}px : arriérés des années antérieures dans la fiche élève`, await p.ev('!!document.querySelector(".probableBox.arrears")'));
  ok(`${w}px : bouton Suspendre (capacité students.lifecycle.suspend)`, await p.ev('[...document.querySelectorAll("button")].some(b=>b.innerText.trim()==="Suspendre")'));
  await p.shot(`n3h-student-${w}`, true);
  m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (fiche élève)`, !m.hscroll, JSON.stringify(m.over));
  await p.ev('document.querySelector(".drawerClose")?.click()'); await delay(600);
  await click('.schoolingTabs button', 'Inscription'); await delay(1500);
  await click('button', 'Créer un nouveau foyer'); await delay(400); await click('button', 'Continuer'); await delay(1000);
  await setInput('input[name="children.0.last_name"]', `DUPONT${run}`); await delay(1500);
  ok(`${w}px : doublon probable signalé pendant la saisie`, await p.ev('!!document.querySelector(".probableBox:not(.arrears)")'));
  m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (inscription)`, !m.hscroll, JSON.stringify(m.over));
}
await signOut(p);
await signInSchool(p, school.users.GES.email, school.users.GES.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
  await nav(w, 'financ'); await p.waitFor('!!document.querySelector(".financePage")', 20000); await delay(800);
  await p.ev('[...document.querySelectorAll("button")].find(b=>b.innerText.trim()==="Rapports")?.click()'); await delay(1000);
  await p.ev('[...document.querySelectorAll("button")].find(b=>b.innerText.trim()==="Analyses de gestion")?.click()'); await delay(1500);
  await p.ev('[...document.querySelectorAll(".productSales button")].find(b=>b.innerText.includes("Afficher les ventes"))?.click()'); await delay(1500);
  ok(`${w}px : rapport des ventes d’articles`, await p.ev('!!document.querySelector(".productSales table")'));
  let m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (ventes)`, !m.hscroll, JSON.stringify(m.over));
  await p.shot(`n3h-sales-${w}`, true);
  await nav(w, 'effectif');
  await click('button', 'Dépôts matériels'); await delay(1800);
  ok(`${w}px : registre exigé / déposé / reste`, await p.ev('!!document.querySelector(".contributionRegister table")'));
  m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (registre)`, !m.hscroll, JSON.stringify(m.over));
  await p.shot(`n3h-register-${w}`, true);
}
const errs = p.consoleErrors.filter(e => !e.includes('HTTP 401'));
ok('aucune erreur console', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(fail ? `UI N3-H : ${fail} échec(s)` : 'UI N3-H : PASS');
process.exit(fail ? 1 : 0);
