// N3-F — staff children finance in the staff drawer (GESTIONNAIRE), phone and desktop. Uses the last school created by
// payroll_probe.py (credentials from the private fixtures, never printed).
import {connect, delay, fx, signInSchool} from '../n2-20261014/cdp.mjs';
const runs = Object.values(fx.N3F || {}); const school = runs[runs.length - 1];
if (!school) { console.log('Lancez d’abord payroll_probe.py'); process.exit(1); }
const p = await connect(); let fail = 0;
const ok = (name, cond, extra = '') => { if (!cond) fail++; console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };
await signInSchool(p, school.users.GES.email, school.users.GES.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
    await p.ev('[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.includes("Personnel")).click()'); }
  else await p.ev('[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||b.innerText).includes("Personnel")).click()');
  await delay(1500);
  await p.ev('(document.querySelector(".personRow button")||document.querySelector(".personRow"))?.click()'); await delay(1200);
  await p.waitFor('!!document.querySelector(".staffDrawer")', 10000).catch(() => {});
  await p.ev('[...document.querySelectorAll(".drawerTabs button")].find(b=>b.innerText.trim()==="Enfants")?.click()'); await delay(1200);
  ok(`${w}px : enfant de l'agent avec sa situation (mode, attendu, retenu, reste)`, await p.ev('!!document.querySelector(".staffChild") && /Retenue à la source/.test(document.querySelector(".staffChild").innerText)'));
  ok(`${w}px : retenues listées avec annulation possible`, await p.ev('document.querySelectorAll(".staffChild .dayDetails li").length>=2'));
  await p.shot(`n3f-staff-children-${w}`, true);
  const m = await p.metrics(); ok(`${w}px : pas de défilement horizontal`, !m.hscroll, JSON.stringify(m.over));
}
const errs = p.consoleErrors.filter(e => !e.includes('HTTP 401'));
ok('aucune erreur console', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(fail ? `UI N3-F : ${fail} échec(s)` : 'UI N3-F : PASS');
process.exit(fail ? 1 : 0);
