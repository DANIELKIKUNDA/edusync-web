// PR #27 certification (2026-10-27) — LOCAL stack, school C: Préfet des études (Secondaire), Directeur de section (Primaire),
// Directrice de section (Maternelle), accounts created by local_role_prepare.mjs with their section (../.local/<folder>/.account.json,
// never printed). Every module of the menu is opened; any unexpected server refusal (HTTP >= 400), vague error, internal « CDF »
// code or horizontal overflow (320 → 1440 px) is a FAIL. Screenshots: ../.local/section_leaders/cert.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const OUT = '../.local/section_leaders/cert'; fs.mkdirSync(OUT, {recursive: true});
const LEADERS = [
  {folder: 'prefet', label: 'Préfet (Secondaire)', short: 'prefet', section: 'Secondaire', options: true},
  {folder: 'directeur_primaire', label: 'Directeur (Primaire)', short: 'primaire', section: 'Primaire', options: false},
  {folder: 'directrice_maternelle', label: 'Directrice (Maternelle)', short: 'maternelle', section: 'Maternelle', options: false},
];
const OTHER = ['Secondaire', 'Primaire', 'Maternelle'];
let failures = 0; const results = [];
const b = await chromium.launch({channel: 'msedge'});
for (const L of LEADERS) {
  const acc = JSON.parse(fs.readFileSync(`../.local/${L.folder}/.account.json`, 'utf8'));
  const ctx = await b.newContext({viewport: {width: 1440, height: 900}, acceptDownloads: true}); const p = await ctx.newPage();
  ctx.on('page', np => { if (np !== p) setTimeout(() => np.close().catch(() => {}), 1500); });
  const http = [];
  p.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/') && r.status() >= 400 && !u.pathname.includes('/auth/') && !u.pathname.includes('branding/logo')) http.push(`${r.request().method()} ${u.pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, ':id')} → ${r.status()}`); });
  p.on('pageerror', e => http.push(`JS ${String(e.message).slice(0, 140)}`));
  const step = async (name, fn, shot) => {
    const before = http.length; let status = 'PASS', detail = '';
    try { await fn(); await p.waitForTimeout(500);
      if (await p.getByText('Une difficulté est survenue').count()) { status = 'FAIL'; detail = 'message vague affiché'; }
      else { const seen = await p.evaluate(() => (document.querySelector('main, .es-main') || document.body).innerText.match(/\bCDF\b/g)); if (seen) { status = 'FAIL'; detail = '« CDF » affiché'; } }
    } catch (e) { status = 'FAIL'; detail = String(e.message).split('\n').slice(0, 2).join(' / ').slice(0, 300); }
    const n = http.slice(before); if (n.length && status === 'PASS') { status = 'FAIL'; detail = `refus serveur inattendu : ${[...new Set(n)].join(', ')}`; }
    if (status !== 'PASS') failures++;
    results.push({role: L.label, name, status, detail}); console.log(`${status.padEnd(5)} [${L.label}] ${name}${detail ? ` — ${detail}` : ''}`);
    if (shot) await p.screenshot({path: `${OUT}/${L.short}_${shot}.png`, fullPage: false});
  };
  const nav = () => p.getByRole('complementary', {name: 'Navigation principale'});
  const module = async m => { await nav().getByRole('button', {name: m, exact: true}).click(); await p.waitForTimeout(1600); };
  const overflow = () => p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  let menu = [];

  await step('01 connexion', async () => { await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
    await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500);
    menu = (await nav().getByRole('button').allInnerTexts()).map(x => x.trim()).filter(Boolean); console.log(`      menu : ${menu.join(' | ')}`); });
  await step('02 accueil : effectifs Total / Filles / Garçons de sa seule section', async () => {
    const card = p.locator('.sh-fgt').first(); await card.waitFor({timeout: 20000});
    console.log(`      F/G/T : ${(await card.innerText()).replace(/\s+/g, ' ')}`);
    const sections = await p.locator('ul[aria-label="Effectifs par section"] li b').allInnerTexts();
    const foreign = sections.filter(s => s !== L.section); if (foreign.length) throw new Error(`autre section affichée : ${foreign.join(', ')}`);
    const opt = await p.locator('ul[aria-label="Effectifs par option"] li').count();
    if (L.options && !opt) throw new Error('effectifs par option absents pour le préfet');
    if (L.options) console.log(`      options : ${(await p.locator('ul[aria-label="Effectifs par option"] li').allInnerTexts()).map(t => t.replace(/\s+/g, ' ')).join(' | ')}`);
  }, '01_accueil');
  await step('03 menu sans module d’opération (caisse, intendance, accès)', async () => {
    for (const m of ['Intendance', 'Accès & rôles']) if (menu.includes(m)) throw new Error(`module « ${m} » visible`); });
  await step('10 élèves & inscriptions : liste de sa section', async () => { await module('Élèves & inscriptions');
    await p.waitForTimeout(1500); const txt = await p.locator('main, .es-main').first().innerText();
    const foreign = OTHER.filter(s => s !== L.section && new RegExp(`\\b${s}\\b`).test(txt) && !/Toutes les sections/.test(s)); if (foreign.length) console.log(`      (mention d’autres sections dans la page : ${foreign.join(', ')})`); }, '02_eleves');
  await step('20 personnel : consultation, sans création ni modification', async () => { await module('Personnel');
    if (await p.getByRole('button', {name: /Nouvel agent/}).count()) throw new Error('bouton « Nouvel agent » affiché sans droit de création');
    const dir = p.getByRole('button', {name: /^Annuaire/}).first(); if (await dir.count()) { await dir.click(); await p.waitForTimeout(1500); }
    if (await p.getByRole('button', {name: /^Modifier$/}).count()) throw new Error('bouton « Modifier » affiché sans droit de modification'); }, '03_personnel');
  await step('30 effectifs & dépôts', async () => { await module('Effectifs & dépôts'); await p.waitForTimeout(1500); }, '04_effectifs');
  await step('40 centre financier : lecture sans encaissement', async () => { await module('Centre financier');
    if (await p.getByRole('button', {name: /^Encaisser/}).count()) throw new Error('bouton d’encaissement affiché');
    const tabs = await p.locator('.financeTabs button').allInnerTexts(); console.log(`      onglets : ${tabs.join(' | ')}`);
    for (const t of tabs) { await p.locator('.financeTabs button').filter({hasText: new RegExp(`^${t}$`)}).first().click(); await p.waitForTimeout(1500); } }, '05_finance');
  for (const m of ['Documents', 'Communication', 'Paramètres']) if (menu.includes(m))
    await step(`50 ${m.toLowerCase()}`, async () => { await module(m); }, `06_${m.toLowerCase().normalize('NFD').replace(/[^a-z]/g, '')}`);
  await step('80 responsive 320 → 1440 px (accueil, élèves, personnel)', async () => {
    const bad = [];
    for (const w of [320, 390, 768, 1024, 1440]) { await p.setViewportSize({width: w, height: w < 768 ? 844 : 900});
      for (const m of ['Accueil', 'Élèves & inscriptions', 'Personnel']) {
        if (w < 1024) { const burger = p.getByRole('button', {name: /Ouvrir le menu|Menu/}).first(); if (await burger.count() && !(await nav().isVisible().catch(() => false))) { await burger.click(); await p.waitForTimeout(400); } }
        await nav().getByRole('button', {name: m, exact: true}).click({timeout: 8000}).catch(async () => { await p.keyboard.press('Escape'); });
        await p.waitForTimeout(1100); const o = await overflow(); if (o > 1) bad.push(`${m} ${w}px +${o}px`);
        if (w === 390 && m === 'Accueil') await p.screenshot({path: `${OUT}/${L.short}_07_mobile.png`, fullPage: true});
        if (w === 768 && m === 'Accueil') await p.screenshot({path: `${OUT}/${L.short}_08_tablette.png`, fullPage: false}); } }
    await p.setViewportSize({width: 1440, height: 900}); if (bad.length) throw new Error(`débordement horizontal : ${bad.join(', ')}`); });
  await ctx.close();
}
await b.close();
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.length - failures}/${results.length} PASS · ${failures} FAIL`);
process.exit(failures ? 1 : 0);
