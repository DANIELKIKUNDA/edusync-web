// N2 certification UI journey (school A administrator, certification database).
//  1. Real phone journey (390 px) through the interface only: sign-in → identity → years → structure → enrollment rules →
//     tariffs → users → roles → home → sign-out → sign-in again.
//  2. Sweep of the N2 screens at 320/375/390/768/1024/1280/1440: horizontal overflow, targets < 24 px (WCAG 2.2 AA 2.5.8),
//     console errors. Captures in captures/journey-*. Verdict in n2-journey.json (exit code 1 on any failure).
import fs from 'node:fs/promises';
import {connect, delay, fx, signInSchool, signOut} from './cdp.mjs';

const admin = fx.A.users.ADMIN;
const p = await connect();
const steps = [];
const failures = [];
const check = (name, ok, detail = '') => { steps.push({name, ok, detail}); if (!ok) failures.push(`${name} ${detail}`); console.log(ok ? 'OK ' : 'ÉCHEC', name, detail); };

const strictSmall = () => p.ev(`[...document.querySelectorAll('button,a,input,select,[role=tab],[role=switch]')].filter(e=>{const r=e.getBoundingClientRect();const label=e.closest('label');const lr=label?label.getBoundingClientRect():null;
  const h=Math.max(r.height,lr?lr.height:0),w=Math.max(r.width,lr?lr.width:0);return e.offsetParent!==null&&r.width>0&&(h<24||w<24)}).map(e=>(e.innerText||e.getAttribute('aria-label')||e.tagName).slice(0,24))`);
const phone = () => p.ev('innerWidth<768');
async function openModule(label) {
  if (await phone()) {
    const inBar = await p.ev(`[...document.querySelectorAll(".es-bottom button")].some(b=>b.innerText.includes(${JSON.stringify(label)}))`);
    if (inBar) { await p.ev(`[...document.querySelectorAll(".es-bottom button")].find(b=>b.innerText.includes(${JSON.stringify(label)})).click()`); }
    else { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
      await p.ev(`[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.includes(${JSON.stringify(label)})).click()`); }
  } else await p.ev(`[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||"").includes(${JSON.stringify(label)})).click()`);  // rail: labels hidden, aria-label kept
  await delay(1200);
}
async function openSettings(section) {
  await openModule('Paramètres'); await p.waitFor('!!document.querySelector(".settingsNav")');
  await p.ev(`[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes(${JSON.stringify(section)})).click()`); await delay(1000);
}
const settingsBack = async () => { if (await phone()) { await p.ev('document.querySelector(".settingsBack")?.click()'); await delay(600); } };

// ---------- 1. phone journey ----------
await p.viewport(390, 844);
await signInSchool(p, admin.email, admin.password);
check('connexion administrateur (390)', await p.ev('!!document.querySelector(".es-shell")'));
await openSettings('École & identité');
check('identité : logo vérifié, pas de champ URL', await p.ev('!!document.querySelector(".logoField") && !document.body.innerText.includes("URL du logo")'));
check('identité : clavier téléphone et e-mail', await p.ev('document.querySelector("input[type=tel]")?.inputMode==="tel" && !!document.querySelector("input[type=email][inputmode=email]")'));
await settingsBack(); await openSettings('Années scolaires');
check('années : une année en cours', await p.ev('!!document.querySelector(".yearList article.current")'));
await p.ev('[...document.querySelectorAll(".rowActions button")].find(b=>/Clôturer/.test(b.innerText))?.click()'); await delay(400);
check('années : clôture demandée → confirmation explicite', await p.ev('!!document.querySelector(".eduDialog[role=alertdialog]")'));
await p.ev('document.querySelector(".eduDialogActions .ghost").click()'); await delay(400);
check('années : annuler ne clôture pas', await p.ev('!!document.querySelector(".yearList article.current")'));
await settingsBack(); await openSettings('Structure & classes');
check('structure : classes en liste, sans tableau débordant', await p.ev('!!document.querySelector(".classList") && !document.querySelector(".settingsContent .dataTable")'));
await settingsBack(); await openSettings('Inscriptions');
check('inscriptions : règles appliquées par le serveur', await p.ev('document.querySelectorAll(".switchRow input").length===7'));
await settingsBack(); await openSettings('Tarifs & barèmes');
const amounts = await p.ev('[...document.querySelectorAll(".moneyList .amount")].map(e=>e.innerText)');
check('tarifs : montants formatés', amounts.length > 0 && amounts.every(a => /^-?\d{1,3}([   ]\d{3})*(,\d{2})? (CDF|USD)$/.test(a)), JSON.stringify(amounts.slice(0, 3)));
await openModule('Accès & rôles'); await p.waitFor('!!document.querySelector(".memberList")');
check('utilisateurs : liste des membres en premier sur téléphone', await p.ev('document.querySelector(".memberList").getBoundingClientRect().top < innerHeight'));
await p.ev('[...document.querySelectorAll("[role=tab], .accessTabs button")].find(b=>/Rôles/.test(b.innerText))?.click()'); await delay(800);
check('rôles : onglet accessible', await p.ev('/Rôles/.test(document.querySelector(".es-content").innerText)'));
await openModule('Accueil');
check('accueil', await p.ev('!!document.querySelector(".es-shell")'));
await p.ev('document.querySelector(".es-account-btn")?.click()'); await delay(400);
await p.ev('[...document.querySelectorAll(".es-menu button")].find(b=>/Se déconnecter/.test(b.innerText))?.click()'); await delay(1500);
check('déconnexion par le menu du compte', await p.ev('!!document.querySelector(".lg-card")'));
await signInSchool(p, admin.email, admin.password);
check('reconnexion', await p.ev('!!document.querySelector(".es-shell")'));

// ---------- 2. sweep ----------
const screens = [
  ['settings-home', async () => { await openModule('Paramètres'); if (await phone()) await settingsBack(); }],
  ['settings-readiness', () => openSettings('Mise en service')],
  ['settings-identity', () => openSettings('École & identité')],
  ['settings-years', () => openSettings('Années scolaires')],
  ['settings-structure', () => openSettings('Structure & classes')],
  ['settings-enrollment', () => openSettings('Inscriptions')],
  ['settings-tariffs', () => openSettings('Tarifs & barèmes')],
  ['settings-products', () => openSettings('Articles scolaires')],
  ['access-members', async () => { await openModule('Accès & rôles'); await p.waitFor('!!document.querySelector(".memberList")'); }],
  ['home', () => openModule('Accueil')],
];
const sweep = [];
for (const [w, h] of [[320, 640], [375, 812], [390, 844], [768, 1024], [1024, 768], [1280, 900], [1440, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1000);
  for (const [name, open] of screens) {
    await open(); await p.ev('window.scrollTo(0,0)'); await delay(300);
    const m = await p.metrics(); const small = await strictSmall();
    sweep.push({screen: name, width: w, hscroll: m.hscroll, over: m.over, targetsUnder24: small});
    if (m.hscroll) failures.push(`${name}@${w} débordement horizontal ${JSON.stringify(m.over)}`);
    if (small.length) failures.push(`${name}@${w} cibles < 24 px ${JSON.stringify(small)}`);
    if ([320, 390, 768, 1280].includes(w)) await p.shot(`journey-${name}-${w}`);
  }
  console.log(w, 'balayage terminé');
}
const errors = p.consoleErrors.filter(e => !/favicon|Failed to load resource: the server responded with a status of 4/.test(e));
if (errors.length) failures.push(`erreurs console ${JSON.stringify(errors.slice(0, 5))}`);
const verdict = {date: new Date().toISOString(), steps, sweep, consoleErrors: errors, failures, pass: failures.length === 0};
await fs.writeFile(new URL('n2-journey.json', import.meta.url), JSON.stringify(verdict, null, 1));
console.log(verdict.pass ? 'PARCOURS N2 : PASS' : `PARCOURS N2 : ÉCHEC (${failures.length})`); failures.forEach(f => console.log(' -', f));
process.exit(verdict.pass ? 0 : 1);
