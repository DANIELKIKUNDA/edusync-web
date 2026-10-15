// N3-B — cash desk UI (expense form, school-day panel, PDFs) on phone and desktop. Uses the last school created by
// cash_integrity_probe.py (credentials from the private fixtures, never printed).
import {connect, delay, fx, signInSchool} from '../n2-20261014/cdp.mjs';
const runs = Object.values(fx.N3B || {}); const school = runs[runs.length - 1];
if (!school) { console.log('Lancez d’abord cash_integrity_probe.py'); process.exit(1); }
const p = await connect(); let fail = 0;
const ok = (name, cond, extra = '') => { if (!cond) fail++; console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };
async function openCash(w) {
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
    await p.ev('[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.toLowerCase().includes("financ")).click()'); }
  else await p.ev('[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||b.innerText).toLowerCase().includes("financ")).click()');
  await p.waitFor('!!document.querySelector(".financePage")', 20000); await delay(800);
  await p.ev('[...document.querySelectorAll("button")].find(b=>/^Caisse/.test(b.innerText.trim()))?.click()'); await delay(1500);
}
for (const [who, key] of [['caissier', 'CASH_A'], ['gestionnaire', 'GES']]) {
  await signInSchool(p, school.users[key].email, school.users[key].password);
  for (const [w, h] of [[390, 844], [1280, 900]]) {
    await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
    await openCash(w);
    if (who === 'caissier') ok(`${w}px caissier : formulaire de dépense dans sa caisse ouverte`, await p.ev('!!document.querySelector(".cashExpenseBox")'));
    else {
      await p.waitFor('!!document.querySelector(".schoolDay")', 15000).catch(() => {});
      ok(`${w}px gestionnaire : journée de caisse de l’école`, await p.ev('!!document.querySelector(".schoolDay")'));
      ok(`${w}px gestionnaire : boutons PDF et clôture/réouverture`, await p.ev('[...document.querySelectorAll(".dayActions button")].length>=2'));
    }
    await p.shot(`n3b-cash-${who}-${w}`, true);
    const m = await p.metrics(); ok(`${w}px ${who} : pas de défilement horizontal`, !m.hscroll, JSON.stringify(m.over));
  }
}
const errs = p.consoleErrors.filter(e => !e.includes('HTTP 401'));
ok('aucune erreur console', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(fail ? `UI N3-B : ${fail} échec(s)` : 'UI N3-B : PASS');
process.exit(fail ? 1 : 0);
