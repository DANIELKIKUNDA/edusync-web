// N2 exploratory UI audit: school administrator screens at phone and desktop widths (captures + layout metrics).
import fs from 'node:fs/promises';
import {connect, delay, fx, signInSchool} from './cdp.mjs';

const admin = fx.A?.users?.ADMIN;
if (!admin) throw Error('Compte administrateur de l’école A absent des fixtures');
const p = await connect();
const report = [];
await p.viewport(1280, 900);
await signInSchool(p, admin.email, admin.password);
await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1500);

async function capture(name) {
  for (const [w, h] of [[390, 844], [1280, 900]]) {
    await p.viewport(w, h); await delay(700);
    const m = await p.metrics();
    report.push({screen: name, width: w, ...m});
    await p.shot(`audit-${name}-${w}`, true);
  }
  await p.viewport(1280, 900);
}

await capture('home');
// Mobile navigation itself (bottom bar, then the secondary menu).
await p.viewport(390, 844); await delay(600); await p.shot('audit-nav-bottom-390');
await p.click('Menu').catch(async () => { await p.click('Plus').catch(() => {}); }); await delay(600); await p.shot('audit-nav-drawer-390');
await p.ev('document.querySelector("[aria-label=\\"Fermer le menu\\"]")?.click()'); await delay(500);
report.push({screen: 'drawer-closed', width: 390, hscroll: false, over: [], smallTargets: 0, h: 0, open: await p.ev('!!document.querySelector("[aria-label=\\"Fermer le menu\\"]")')});
await p.viewport(1280, 900); await delay(400);

await p.click('Paramètres'); await p.waitFor('!!document.querySelector(".settingsNav")'); await delay(1200);
for (const [label, key] of [['Mise en service', 'settings-overview'], ['École & identité', 'settings-identity'], ['Années scolaires', 'settings-years'],
  ['Structure & classes', 'settings-structure'], ['Types de frais', 'settings-fees'], ['Tarifs & barèmes', 'settings-tariffs'],
  ['Contributions en nature', 'settings-contributions'], ['Articles scolaires', 'settings-products']]) {
  await p.ev(`[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes(${JSON.stringify(label)}))?.click()`); await delay(900);
  await capture(key);
}
for (const [label, key] of [['Accès & rôles', 'access'], ['Personnel', 'personnel']]) {
  await p.click(label).catch(() => {}); await delay(1800);
  await capture(key);
}
await fs.writeFile(new URL('./audit-metrics.json', import.meta.url), JSON.stringify({report, consoleErrors: p.consoleErrors}, null, 2));
for (const r of report) console.log(`${r.screen.padEnd(24)} ${String(r.width).padStart(4)}px  hscroll=${r.hscroll}${r.hscroll ? ' (' + r.scrollWidth + ')' : ''}  cibles<36px=${r.smallTargets}  hauteur=${r.h}${r.over.length ? '  débordent: ' + r.over.join(' ') : ''}`);
console.log('erreurs console :', p.consoleErrors.length, p.consoleErrors.slice(0, 5));
process.exit(0);
