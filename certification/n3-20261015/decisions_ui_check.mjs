// N3-C — decisions UI (pupil's financial situation, new decision form) on phone and desktop, GESTIONNAIRE of the last
// school created by decisions_probe.py (credentials from the private fixtures, never printed).
import {connect, delay, fx, signInSchool} from '../n2-20261014/cdp.mjs';
const runs = Object.values(fx.N3C || {}); const school = runs[runs.length - 1];
if (!school) { console.log('Lancez d’abord decisions_probe.py'); process.exit(1); }
const p = await connect(); let fail = 0;
const ok = (name, cond, extra = '') => { if (!cond) fail++; console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };
await signInSchool(p, school.users.GES.email, school.users.GES.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
    await p.ev('[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.toLowerCase().includes("financ")).click()'); }
  else await p.ev('[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||b.innerText).toLowerCase().includes("financ")).click()');
  await p.waitFor('!!document.querySelector(".financePage")', 20000); await delay(800);
  await p.ev('[...document.querySelectorAll("button")].find(b=>b.innerText.trim()==="Décisions financières")?.click()'); await delay(1200);
  ok(`${w}px : onglet « Situation d’un élève »`, await p.ev('!!document.querySelector(".decisionPanel")'));
  await p.type('[aria-label="Rechercher un élève"]', 'DEC'); await p.waitFor('!!document.querySelector(".decisionFinder .checkoutHits button")', 15000).catch(() => {});
  await p.ev('document.querySelector(".decisionFinder .checkoutHits button")?.click()');
  await p.waitFor('document.querySelectorAll(".operatorCharges li").length>0', 15000).catch(() => {});
  const n = await p.ev('document.querySelectorAll(".operatorCharges li").length');
  ok(`${w}px : situation par frais (statuts, décisions appliquées)`, n >= 10, `${n} frais`);
  ok(`${w}px : un frais exonéré visible`, await p.ev('!!document.querySelector(".operatorCharges li.op-EXONEREE")'));
  await p.ev('[...document.querySelectorAll(".payerStrip button")].find(b=>b.innerText.includes("Nouvelle décision"))?.click()'); await delay(600);
  ok(`${w}px : formulaire de décision (nature, portée, valeur, priorité)`, await p.ev('!!document.querySelector(".decisionForm")'));
  await p.shot(`n3c-decisions-${w}`, true);
  const m = await p.metrics(); ok(`${w}px : pas de défilement horizontal`, !m.hscroll, JSON.stringify(m.over));
}
const errs = p.consoleErrors.filter(e => !e.includes('HTTP 401'));
ok('aucune erreur console', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(fail ? `UI N3-C : ${fail} échec(s)` : 'UI N3-C : PASS');
process.exit(fail ? 1 : 0);
