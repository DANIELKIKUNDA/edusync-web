// N3-E — cash desk: consecutive periods selectable together, recommended action, journal + écusson bundle (phone and
// desktop). Uses the last school created by checkout_rules_probe.py (credentials from the private fixtures, never printed).
import {connect, delay, fx, signInSchool} from '../n2-20261014/cdp.mjs';
const runs = Object.values(fx.N3E || {}); const school = runs[runs.length - 1];
if (!school) { console.log('Lancez d’abord checkout_rules_probe.py'); process.exit(1); }
const p = await connect(); let fail = 0;
const ok = (name, cond, extra = '') => { if (!cond) fail++; console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };
await signInSchool(p, school.users.CASH.email, school.users.CASH.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
    await p.ev('[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.toLowerCase().includes("financ")).click()'); }
  else await p.ev('[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||b.innerText).toLowerCase().includes("financ")).click()');
  await p.waitFor('!!document.querySelector("[aria-label=\\"Rechercher un élève ou une famille\\"]")', 20000);
  await p.type('[aria-label="Rechercher un élève ou une famille"]', 'SER'); await p.waitFor('!!document.querySelector(".checkoutHits button")', 15000);
  await p.ev('document.querySelector(".checkoutHits button").click()'); await p.waitFor('document.querySelectorAll(".chargeRow").length>5', 15000);
  const sept = 'document.querySelector(".chargeRow:not(.locked)")';
  const lockedBefore = await p.ev('document.querySelectorAll(".chargeRow.locked").length');
  await p.ev('[...document.querySelectorAll(".chargeRow")].find(b=>b.innerText.includes("Frais scolaires")&&!b.classList.contains("locked"))?.click()'); await delay(400);
  const lockedAfter = await p.ev('document.querySelectorAll(".chargeRow.locked").length');
  ok(`${w}px : septembre choisi → octobre devient sélectionnable (même reçu)`, lockedAfter < lockedBefore, `${lockedBefore} → ${lockedAfter} verrouillés`);
  ok(`${w}px : bouton « Action conseillée »`, await p.ev('[...document.querySelectorAll("button")].some(b=>b.innerText.trim()==="Action conseillée")'));
  ok(`${w}px : bouton « Journal + écusson »`, await p.ev('[...document.querySelectorAll("button")].some(b=>b.innerText.trim()==="Journal + écusson")'));
  await p.ev('[...document.querySelectorAll("button")].find(b=>b.innerText.trim()==="Journal + écusson")?.click()'); await delay(500);
  ok(`${w}px : le lot sélectionne exactement 2 postes`, await p.ev('document.querySelectorAll(".chargeRow.selected").length===2'));
  await p.shot(`n3e-checkout-${w}`, true);
  const m = await p.metrics(); ok(`${w}px : pas de défilement horizontal`, !m.hscroll, JSON.stringify(m.over));
}
const errs = p.consoleErrors.filter(e => !e.includes('HTTP 401'));
ok('aucune erreur console', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(fail ? `UI N3-E : ${fail} échec(s)` : 'UI N3-E : PASS');
process.exit(fail ? 1 : 0);
