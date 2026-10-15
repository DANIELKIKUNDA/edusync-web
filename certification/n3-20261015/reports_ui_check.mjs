// N3-G — periodic reports and analyses UI (GESTIONNAIRE), phone and desktop. Uses the last school created by
// reports_probe.py (credentials from the private fixtures, never printed).
import {connect, delay, fx, signInSchool} from '../n2-20261014/cdp.mjs';
const runs = Object.values(fx.N3G || {}); const school = runs[runs.length - 1];
if (!school) { console.log('Lancez d’abord reports_probe.py'); process.exit(1); }
const p = await connect(); let fail = 0;
const ok = (name, cond, extra = '') => { if (!cond) fail++; console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };
await signInSchool(p, school.users.GES.email, school.users.GES.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
    await p.ev('[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.toLowerCase().includes("financ")).click()'); }
  else await p.ev('[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||b.innerText).toLowerCase().includes("financ")).click()');
  await p.waitFor('!!document.querySelector(".financePage")', 20000); await delay(800);
  await p.ev('[...document.querySelectorAll("button")].find(b=>b.innerText.trim()==="Rapports")?.click()'); await delay(1000);
  await p.ev('[...document.querySelectorAll("button")].find(b=>b.innerText.trim()==="Afficher")?.click()'); await delay(1500);
  const n = await p.ev('document.querySelectorAll(".reportsDesk .cashSummaryTable tbody tr").length');
  ok(`${w}px : rapport consolidé du jour (une ligne par paiement + total)`, n >= 5, `${n} lignes`);
  ok(`${w}px : PDF officiel numéroté et Excel`, await p.ev('[...document.querySelectorAll("button")].some(b=>b.innerText.includes("PDF officiel"))&&[...document.querySelectorAll("button")].some(b=>b.innerText.includes("Excel"))'));
  await p.shot(`n3g-reports-${w}`, true);
  let m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (rapports)`, !m.hscroll, JSON.stringify(m.over));
  await p.ev('[...document.querySelectorAll("button")].find(b=>b.innerText.trim()==="Analyses de gestion")?.click()'); await delay(1500);
  ok(`${w}px : analyses par frais et par caissier`, await p.ev('document.querySelectorAll(".reportsDesk h3").length>=2'));
  m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (analyses)`, !m.hscroll, JSON.stringify(m.over));
}
const errs = p.consoleErrors.filter(e => !e.includes('HTTP 401'));
ok('aucune erreur console', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(fail ? `UI N3-G : ${fail} échec(s)` : 'UI N3-G : PASS');
process.exit(fail ? 1 : 0);
