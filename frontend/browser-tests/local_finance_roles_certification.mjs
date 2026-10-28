// Certification (2026-10-28) — Responsable chargé des finances and Promoteur, LOCAL stack, school C. Accounts created by
// local_role_prepare.mjs (../.local/<folder>/.account.json, never printed). Both roles read, follow, print and export:
// every menu module is opened, no operation button may appear (collect, open a cash desk, enrol, new agent, new member),
// and any server refusal (HTTP >= 400), vague error, internal « CDF » code or horizontal overflow (320 → 1440 px) is a FAIL.
// Screenshots: ../.local/finance_roles/cert.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const OUT = '../.local/finance_roles/cert'; fs.mkdirSync(OUT, {recursive: true});
const ROLES = [{folder: 'responsable_finance', label: 'Responsable financier', short: 'rf'}, {folder: 'promoteur', label: 'Promoteur', short: 'promoteur'}];
const OPERATIONS = [/^Encaisser/, /Ouvrir ma caisse/, /Nouvelle inscription|Inscrire une famille/, /Nouvel agent/, /Ajouter un membre/, /Exécuter la reprise|Importer définitivement/];
let failures = 0; const results = [];
const b = await chromium.launch({channel: 'msedge'});
for (const R of ROLES) {
  const acc = JSON.parse(fs.readFileSync(`../.local/${R.folder}/.account.json`, 'utf8'));
  const ctx = await b.newContext({viewport: {width: 1440, height: 900}}); const p = await ctx.newPage();
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
    results.push({role: R.label, name, status, detail}); console.log(`${status.padEnd(5)} [${R.label}] ${name}${detail ? ` — ${detail}` : ''}`);
    if (shot) await p.screenshot({path: `${OUT}/${R.short}_${shot}.png`, fullPage: false});
  };
  const nav = () => p.getByRole('complementary', {name: 'Navigation principale'});
  const noOperation = async where => { for (const re of OPERATIONS) if (await p.getByRole('button', {name: re}).count()) throw new Error(`bouton d’opération « ${re.source} » affiché (${where})`); };
  const overflow = () => p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  let menu = [];
  await step('01 connexion', async () => { await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
    await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500);
    menu = (await nav().getByRole('button').allInnerTexts()).map(x => x.trim()).filter(Boolean).filter(x => !/^[A-Z]{2}(\s|$)/.test(x) && x !== 'Réduire le menu');   // the account avatar (initials) is not a module
    console.log(`      menu : ${menu.join(' | ')}`); }, '01_accueil');
  await step('02 accueil sans opération', async () => { await noOperation('accueil'); });
  for (const m of menu.filter(x => x !== 'Accueil')) {
    await step(`10 ${m} : ouvert en lecture, sans opération`, async () => {
      await nav().getByRole('button', {name: m, exact: true}).click(); await p.waitForTimeout(1800);
      if (m === 'Centre financier') { for (const t of await p.locator('.financeTabs button').allInnerTexts()) { await p.locator('.financeTabs button').filter({hasText: new RegExp(`^${t}$`)}).first().click(); await p.waitForTimeout(1300); await noOperation(`Centre financier › ${t}`); } }
      else await noOperation(m);
    }, `10_${m.toLowerCase().normalize('NFD').replace(/[^a-z]/g, '').slice(0, 20)}`);
  }
  await step('80 responsive 320 → 1440 px (accueil, centre financier, élèves)', async () => {
    const bad = [];
    for (const w of [320, 390, 768, 1024, 1440]) { await p.setViewportSize({width: w, height: w < 768 ? 844 : 900});
      for (const m of ['Accueil', 'Centre financier', 'Élèves & inscriptions'].filter(x => menu.includes(x))) {
        // Narrow screens use the bottom tab bar; the navigation must really happen (no silent fallback on the same page).
        const BOTTOM = {'Accueil': 'Accueil', 'Centre financier': 'Finance', 'Élèves & inscriptions': 'Élèves'};
        if (await nav().isVisible().catch(() => false)) await nav().getByRole('button', {name: m, exact: true}).click({timeout: 8000});
        else await p.getByRole('button', {name: BOTTOM[m], exact: true}).last().click({timeout: 8000});
        await p.waitForTimeout(1100);
        const heading = (await p.locator('header h1, .es-topbar h1, h1').first().innerText().catch(() => '')).trim();
        if (!heading.startsWith(m === 'Élèves & inscriptions' ? 'Élèves' : m)) throw new Error(`${w}px : « ${m} » non ouvert (page « ${heading} »)`);
        const o = await overflow(); if (o > 1) bad.push(`${m} ${w}px +${o}px`);
        if (w === 390 && m === 'Accueil') await p.screenshot({path: `${OUT}/${R.short}_90_mobile.png`, fullPage: true}); } }
    await p.setViewportSize({width: 1440, height: 900}); if (bad.length) throw new Error(`débordement horizontal : ${bad.join(', ')}`); });
  await ctx.close();
}
await b.close();
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.length - failures}/${results.length} PASS · ${failures} FAIL`);
process.exit(failures ? 1 : 0);
