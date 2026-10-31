// Certification (2026-10-30) — Intendant, Directeur des études, Directeur de discipline, LOCAL stack, school C. Accounts
// created by local_role_prepare.mjs (../.local/<folder>/.account.json, never printed). Every menu module is opened; an
// operation button outside the role's rights (registry: contracts/CAPABILITY_REGISTRY.json), a server refusal (HTTP >= 400),
// a vague error, an internal « CDF » code or a horizontal overflow (320 → 1440 px, real phone navigation) is a FAIL.
// « Le point du jour » must speak on the home page, and each finding must open its module.
// Screenshots: ../.local/three_roles/cert.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const OUT = '../.local/three_roles/cert'; fs.mkdirSync(OUT, {recursive: true});
const COMMON = [/^Encaisser/, /Ouvrir ma caisse/, /Nouvelle inscription|Inscrire une famille/, /Nouvel agent/, /Ajouter un membre/, /Ajouter un utilisateur/];
const STEWARD = [/Nouveau bien/, /Nouvel article/, /Nouvel inventaire/];
const ROLES = [
  {folder: 'intendant', label: 'Intendant', short: 'intendant', forbidden: COMMON, module: 'Intendance'},
  {folder: 'directeur_etudes', label: 'Directeur des études', short: 'dir_etudes', forbidden: [...COMMON, ...STEWARD], module: 'Élèves & inscriptions'},
  {folder: 'directeur_discipline', label: 'Directeur de discipline', short: 'dir_discipline', forbidden: [...COMMON, ...STEWARD], module: 'Élèves & inscriptions'},
  // 2026-10-31: the Secrétariat creates and updates staff records, completes pupil files, imports pupils and prepares
  // message templates — it never collects, enrols, sends a message or suspends an agent.
  {folder: 'secretariat', label: 'Secrétariat', short: 'secretariat', forbidden: [...COMMON.filter(re => re.source !== 'Nouvel agent'), ...STEWARD, /^Envoyer$/, /Suspendre/], module: 'Élèves & inscriptions'},
];
const ONLY = process.argv[2] ? process.argv[2].split(',') : null;
let failures = 0; const results = [];
const b = await chromium.launch({channel: 'msedge'});
for (const R of ROLES.filter(r => !ONLY || ONLY.includes(r.folder))) {
  const acc = JSON.parse(fs.readFileSync(`../.local/${R.folder}/.account.json`, 'utf8'));
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
    results.push({role: R.label, name, status, detail}); console.log(`${status.padEnd(5)} [${R.label}] ${name}${detail ? ` — ${detail}` : ''}`);
    if (shot) await p.screenshot({path: `${OUT}/${R.short}_${shot}.png`, fullPage: false});
  };
  const nav = () => p.getByRole('complementary', {name: 'Navigation principale'});
  const goHome = async () => { await nav().getByRole('button', {name: 'Accueil', exact: true}).click(); await p.waitForTimeout(1500); };
  const noOperation = async where => { for (const re of R.forbidden) if (await p.getByRole('button', {name: re}).count()) throw new Error(`bouton hors droits « ${re.source} » affiché (${where})`); };
  const overflow = () => p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  let menu = [];
  await step('01 connexion', async () => { await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
    await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500);
    menu = (await nav().getByRole('button').allInnerTexts()).map(x => x.trim()).filter(Boolean).filter(x => !/^[A-Z]{2}(\s|$)/.test(x) && x !== 'Réduire le menu');
    console.log(`      menu : ${menu.join(' | ')}`); }, '01_accueil');
  await step('02 accueil sans bouton hors droits', async () => { await noOperation('accueil'); });
  await step('03 « Le point du jour » : constats en clair, chacun ouvre son module', async () => {
    await p.locator('.sh-brief-item').first().waitFor({timeout: 20000});
    const lines = await p.locator('.sh-brief-item b').allInnerTexts(); console.log(`      point du jour : ${lines.join(' | ')}`);
    for (let i = 0; i < lines.length; i++) {
      await p.locator('.sh-brief-item').nth(i).click(); await p.waitForTimeout(1500);
      if (await p.locator('.sh-brief').count()) throw new Error(`le constat « ${lines[i]} » ne mène nulle part`);
      await goHome(); await p.locator('.sh-brief-item').first().waitFor({timeout: 20000});
    } }, '03_point_du_jour');
  if (R.folder === 'intendant') {
    await step('04 Intendance : fiche de stock, Excel du stock, export des inventaires', async () => {
      await nav().getByRole('button', {name: 'Intendance', exact: true}).click(); await p.waitForTimeout(1500);
      await p.getByRole('tab', {name: 'Consommables'}).click(); await p.waitForTimeout(800);
      const dl = p.waitForEvent('download', {timeout: 20000}); await p.getByRole('button', {name: 'Exporter en Excel'}).click();
      const f = await dl; if (!/\.xlsx$/i.test(f.suggestedFilename())) throw new Error(`fichier inattendu : ${f.suggestedFilename()}`);
      await p.getByRole('button', {name: 'Imprimer la fiche de stock'}).click(); await p.waitForTimeout(1500);
      await p.getByRole('tab', {name: 'Inventaires physiques'}).click(); await p.waitForTimeout(800);
      const xl = p.getByRole('button', {name: /^Exporter l’inventaire .* en Excel$/}).first();
      if (await xl.count()) { const d2 = p.waitForEvent('download', {timeout: 20000}); await xl.click(); await d2; }
      else console.log('      (aucun inventaire enregistré : export non exercé)'); }, '04_intendance');
  } else if (R.folder === 'secretariat') {
    await step('04 Élèves : annuaire exportable, ni inscription ni registre', async () => {
      await nav().getByRole('button', {name: 'Élèves & inscriptions', exact: true}).click(); await p.waitForTimeout(2000);
      if (await p.getByRole('tab', {name: /Inscription \/ Réinscription/}).count()) throw new Error('onglet « Inscription / Réinscription » affiché sans droit');
      await p.getByRole('tab', {name: /Annuaire élèves/}).click(); await p.waitForTimeout(1500);
      if (await p.getByRole('button', {name: /Registre des inscriptions/}).count()) throw new Error('registre des inscriptions affiché sans droit');
      const dl = p.waitForEvent('download', {timeout: 20000}).catch(() => null); await p.locator('.kp-exports button', {hasText: 'Excel'}).first().click(); await p.waitForTimeout(2500); await dl;
      await p.keyboard.press('Escape'); await p.waitForTimeout(500); }, '04_eleves');
    await step('05 Personnel : création d’agent proposée, suspension absente', async () => {
      await nav().getByRole('button', {name: 'Personnel', exact: true}).click(); await p.waitForTimeout(2000);
      if (!await p.getByRole('button', {name: /Nouvel agent/}).count()) throw new Error('« Nouvel agent » absent alors que le droit est accordé');
      if (await p.getByRole('button', {name: /Suspendre/}).count()) throw new Error('« Suspendre » affiché sans droit'); }, '05_personnel');
    await step('06 Communication : modèles oui, écriture de message non', async () => {
      await nav().getByRole('button', {name: 'Communication', exact: true}).click(); await p.waitForTimeout(2000);
      if (await p.getByRole('tab', {name: /Écrire un message/}).count()) throw new Error('« Écrire un message » affiché sans droit d’envoi');
      if (!await p.getByRole('tab', {name: /Modèles/}).count()) throw new Error('onglet des modèles absent'); }, '06_communication');
  } else {
    await step('04 Élèves : registre des inscriptions (PDF et Excel) dans le périmètre', async () => {
      await nav().getByRole('button', {name: 'Élèves & inscriptions', exact: true}).click(); await p.waitForTimeout(2000);
      // 2026-10-30: neither director enrols nor re-enrols — the tab must not even appear (it used to show empty).
      if (await p.getByRole('tab', {name: /Inscription \/ Réinscription/}).count()) throw new Error('onglet « Inscription / Réinscription » affiché sans droit');
      await p.getByRole('tab', {name: /Annuaire élèves/}).click(); await p.waitForTimeout(1500);
      await p.getByRole('button', {name: 'Registre des inscriptions en PDF'}).click(); await p.waitForTimeout(2500);
      await p.keyboard.press('Escape'); await p.waitForTimeout(500);
      await p.getByRole('button', {name: 'Registre des inscriptions en Excel'}).click(); await p.waitForTimeout(2500);
      await p.keyboard.press('Escape'); await p.waitForTimeout(500); }, '04_registre');
    await step('05 Personnel : consultation sans création ni modification', async () => {
      await nav().getByRole('button', {name: 'Personnel', exact: true}).click(); await p.waitForTimeout(2000);
      for (const re of [/Nouvel agent/, /Modifier l’agent|Modifier la fiche/, /Suspendre/]) if (await p.getByRole('button', {name: re}).count()) throw new Error(`bouton « ${re.source} » affiché`); }, '05_personnel');
  }
  for (const m of menu.filter(x => x !== 'Accueil')) {
    await step(`10 ${m} : ouvert, sans bouton hors droits`, async () => {
      await nav().getByRole('button', {name: m, exact: true}).click(); await p.waitForTimeout(1800);
      for (const t of await p.getByRole('tab').allInnerTexts()) { const tab = p.getByRole('tab', {name: t.trim(), exact: true}).first(); if (!await tab.isVisible().catch(() => false)) continue; await tab.click(); await p.waitForTimeout(1000); await noOperation(`${m} › ${t.trim()}`); }
      await noOperation(m);
    }, `10_${m.toLowerCase().normalize('NFD').replace(/[^a-z]/g, '').slice(0, 20)}`);
  }
  await step('80 responsive 320 → 1440 px (accueil et module principal, vraie navigation mobile)', async () => {
    const bad = []; const BOTTOM = {'Accueil': 'Accueil', 'Élèves & inscriptions': 'Élèves'};
    for (const w of [320, 390, 768, 1024, 1440]) { await p.setViewportSize({width: w, height: w < 768 ? 844 : 900});
      for (const m of ['Accueil', R.module]) {
        if (await nav().isVisible().catch(() => false)) await nav().getByRole('button', {name: m, exact: true}).click({timeout: 8000});
        else if (BOTTOM[m]) await p.getByRole('navigation', {name: 'Navigation rapide'}).getByRole('button', {name: BOTTOM[m], exact: true}).click({timeout: 8000});
        else { await p.getByRole('button', {name: 'Tous les modules'}).click({timeout: 8000}); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: m, exact: true}).click({timeout: 8000}); }
        await p.waitForTimeout(1100);
        const heading = (await p.locator('header h1, .es-topbar h1, h1').first().innerText().catch(() => '')).trim();
        if (!heading.startsWith(m === 'Élèves & inscriptions' ? 'Élèves' : m)) throw new Error(`${w}px : « ${m} » non ouvert (page « ${heading} »)`);
        const o = await overflow(); if (o > 1) bad.push(`${m} ${w}px +${o}px`);
        if (w === 390) await p.screenshot({path: `${OUT}/${R.short}_90_mobile_${m === 'Accueil' ? 'accueil' : 'module'}.png`, fullPage: true}); } }
    await p.setViewportSize({width: 1440, height: 900}); if (bad.length) throw new Error(`débordement horizontal : ${bad.join(', ')}`); });
  await ctx.close();
}
await b.close();
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.length - failures}/${results.length} PASS · ${failures} FAIL`);
process.exit(failures ? 1 : 0);
