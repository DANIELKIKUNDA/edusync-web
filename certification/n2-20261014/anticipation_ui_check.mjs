// Plans anticipés (parity lot L6): settings screen (plans manager) and checkout plan panel (cashier) — phone and desktop.
// Uses the last school created by anticipation_probe.py (credentials from the private fixtures, never printed).
import {connect, delay, fx, signInSchool} from './cdp.mjs';
const runs = Object.values(fx.L6 || {}); const school = runs[runs.length - 1];
if (!school) { console.log('Lancez d’abord anticipation_probe.py'); process.exit(1); }
const p = await connect(); let fail = 0;
const ok = (name, cond, extra = '') => { if (!cond) fail++; console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };
async function openModule(w, label) {
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
    await p.ev(`[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.toLowerCase().includes(${JSON.stringify(label)}.toLowerCase())).click()`); }
  else await p.ev(`[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||b.innerText).toLowerCase().includes(${JSON.stringify(label)}.toLowerCase())).click()`);
}
await signInSchool(p, school.users.PLANS.email, school.users.PLANS.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
  await openModule(w, 'Paramètres'); await p.waitFor('!!document.querySelector(".settingsNav")'); await delay(700);
  await p.ev('[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes("Plans anticipés")).click()');
  await p.waitFor('!!document.querySelector(".planList")', 20000).catch(() => {});
  const n = await p.ev('document.querySelectorAll(".planList li").length');
  ok(`${w}px : liste des plans affichée`, n >= 1, `${n} plan(s)`);
  ok(`${w}px : distinction plan / fonds anticipé visible`, await p.ev('document.body.innerText.includes("fonds anticipé")'));
  await p.ev('[...document.querySelectorAll(".planList button")].find(b=>b.innerText==="Modifier")?.click()'); await delay(600);
  ok(`${w}px : plan avec adhésions verrouillé (nouvelle version)`, await p.ev('document.body.innerText.includes("créez une nouvelle version")'));
  await p.shot(`anticipation-settings-${w}`, true);
  const m = await p.metrics(); ok(`${w}px : pas de défilement horizontal`, !m.hscroll, JSON.stringify(m.over));
}
await signInSchool(p, school.users.CASH.email, school.users.CASH.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
  await openModule(w, 'financ'); await p.waitFor('!!document.querySelector("[aria-label=\\"Rechercher un élève ou une famille\\"]")', 20000);
  await p.type('[aria-label="Rechercher un élève ou une famille"]', 'Recette'); await p.waitFor('!!document.querySelector(".checkoutHits button")', 15000);
  await p.ev('document.querySelector(".checkoutHits button").click()');
  await p.waitFor('!!document.querySelector(".planPanel")', 15000).catch(() => {});
  ok(`${w}px : panneau « Paiement selon un plan anticipé » à la caisse`, await p.ev('!!document.querySelector(".planPanel")'));
  ok(`${w}px : ancien « Paiement avec avance » absent`, !(await p.ev('document.body.innerText.includes("Paiement avec avance")')));
  await p.ev('document.querySelector(".planPanel")?.scrollIntoView()'); await delay(400);
  await p.shot(`anticipation-checkout-${w}`, true);
  const m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (caisse)`, !m.hscroll, JSON.stringify(m.over));
}
const errs = p.consoleErrors.filter(e => !e.includes('HTTP 401'));  // 401 = session check before sign-in, expected
ok('aucune erreur console', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(fail ? `UI L6 : ${fail} échec(s)` : 'UI L6 : PASS');
process.exit(fail ? 1 : 0);
