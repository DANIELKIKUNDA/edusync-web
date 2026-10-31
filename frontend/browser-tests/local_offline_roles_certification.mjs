// Every school role works offline (owner, 2026-10-31: « au niveau école tout le monde peut travailler offline ») — LOCAL
// stack, REAL server and database, emulated Android phone, accounts from local_role_prepare.mjs (never printed).
// For each role: online sign-in (the app and the role's lists are kept on the phone — the module is NOT opened online),
// airplane mode, app closed and reopened, ONE everyday operation done offline, network back with the server's first
// answer LOST on the way, automatic synchronisation, and the database holds the operation exactly ONCE.
//   Intendant   : stock entry (« Entrée ») on a consumable
//   Secrétariat : a new staff record (« Nouvel agent »)
// Screenshots: ../.local/offline_roles.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
const OUT = '../.local/offline_roles'; fs.mkdirSync(OUT, {recursive: true});
const RUN = Date.now().toString(36).slice(-4).toUpperCase();
const REASON = `Livraison hors ligne ${RUN}`; const EMP = `HL${RUN}`;
const ROLES = [
  {folder: 'intendant', label: 'Intendant', menu: 'Intendance', lost: /\/api\/v1\/stewardship\/stock\/movements$/,
    act: async p => { await p.getByRole('tab', {name: 'Consommables'}).click(); await p.locator('.stockRow').first().waitFor({timeout: 20000});
      await p.locator('.stockRow').first().getByRole('button', {name: 'Entrée'}).click(); const d = p.getByRole('dialog', {name: 'Entrée de stock'});
      await d.getByLabel('Quantité').fill('4'); await d.getByLabel('Motif').fill(REASON); await d.getByRole('button', {name: 'Enregistrer'}).click(); },
    db: out => out.stock_movements === 1 ? '' : `${out.stock_movements} mouvement(s) de stock (attendu 1)`},
  {folder: 'secretariat', label: 'Secrétariat', menu: 'Personnel', lost: /\/api\/v1\/personnel$/,
    act: async p => { await p.getByRole('button', {name: /Nouvel agent/}).first().click();
      const m = p.locator('form.staffModal'); await m.getByLabel('Matricule *').fill(EMP); await m.getByLabel('Nom *').fill('KABEYA');
      await m.getByLabel('Prénom').fill('Ruth'); await m.getByRole('button', {name: 'Créer le dossier'}).click(); },
    db: out => out.staff === 1 ? '' : `${out.staff} dossier(s) d'agent (attendu 1)`},
];
const only = process.argv[2] ? process.argv[2].split(',') : null;
const results = []; let failures = 0;
execFileSync('../.venv/Scripts/python.exe', ['../tools/local/offline_proof_db.py', '--seed-item', `CRAIE${RUN}`]);   // the Intendant's stock (demo school has none)
const b = await chromium.launch({channel: 'msedge'});
for (const R of ROLES.filter(r => !only || only.includes(r.folder))) {
  const acc = JSON.parse(fs.readFileSync(`../.local/${R.folder}/.account.json`, 'utf8'));
  const ctx = await b.newContext({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true, serviceWorkers: 'allow',
    userAgent: 'Mozilla/5.0 (Linux; Android 13; SM-A145F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36'});
  const p = await ctx.newPage(); const errors = [];
  p.on('pageerror', e => errors.push(String(e.message).slice(0, 140)));
  const step = async (name, fn) => { let status = 'PASS', detail = '';
    try { await fn(); if (errors.length) throw new Error(`erreur JavaScript : ${errors.splice(0).join(' | ')}`); }
    catch (e) { status = 'FAIL'; detail = String(e.message).split('\n').slice(0, 2).join(' / ').slice(0, 300); }
    if (status !== 'PASS') failures++; results.push({role: R.label, name, status, detail}); console.log(`${status.padEnd(5)} [${R.label}] ${name}${detail ? ` — ${detail}` : ''}`);
    await p.screenshot({path: `${OUT}/${R.folder}_${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`}).catch(() => {}); };
  const openModule = async () => { const bar = p.getByRole('navigation', {name: 'Navigation rapide'});
    await bar.getByRole('button', {name: 'Tous les modules'}).click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: R.menu, exact: true}).click(); await p.waitForTimeout(1500); };
  const outbox = () => p.evaluate(() => new Promise(res => { const r = indexedDB.open('edusync-outbox-v1'); r.onsuccess = () => {
    const q = r.result.transaction('requests').objectStore('requests').getAll(); q.onsuccess = () => res(q.result.map(x => ({label: x.label, status: x.status, error: x.lastError}))); }; r.onerror = () => res([]); }));

  await step('01 connexion en ligne (module jamais ouvert), puis mode avion et réouverture', async () => {
    await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
    await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000});
    await p.evaluate(() => navigator.serviceWorker.ready.then(() => true)); await p.waitForTimeout(8000);   // background copy of the app and the role's lists
    await ctx.setOffline(true); await p.reload({waitUntil: 'domcontentloaded'}); await p.locator('.es-shell').waitFor({timeout: 30000});
    await p.getByText('Hors connexion — vous pouvez continuer.').first().waitFor({timeout: 10000}); });
  await step(`02 hors ligne : ${R.menu} s'ouvre et l'opération est gardée sur l'appareil`, async () => {
    await openModule(); await R.act(p);
    await p.getByText(/Hors connexion/).first().waitFor({timeout: 15000});
    for (let i = 0; i < 10 && !(await outbox()).length; i++) await p.waitForTimeout(500);
    const q = await outbox(); console.log(`      en attente : ${q.map(x => x.label).join(' | ')}`); if (q.length !== 1) throw new Error(`${q.length} opération(s) en attente (attendu 1)`);
    await p.getByRole('button', {name: /Synchronisation : 1 en attente/}).waitFor({timeout: 10000}); });
  await step('03 retour du réseau, première réponse perdue : synchronisée, une seule fois en base', async () => {
    let lost = false;
    await ctx.route(R.lost, async route => { if (!lost && route.request().method() !== 'GET') { lost = true; await route.fetch().catch(() => null); return route.abort('connectionreset'); } return route.continue(); });
    await ctx.setOffline(false); await p.evaluate(() => window.dispatchEvent(new Event('online')));
    for (let i = 0; i < 90; i++) { if (lost && !(await outbox()).length) break; if (i % 15 === 14) await p.evaluate(() => window.dispatchEvent(new Event('online'))); await p.waitForTimeout(1000); }
    const q = await outbox(); if (!lost) throw new Error('réponse perdue non simulée'); if (q.length) throw new Error(`reste sur l’appareil : ${JSON.stringify(q)}`);
    const out = JSON.parse(execFileSync('../.venv/Scripts/python.exe', ['../tools/local/offline_proof_db.py', '-', '', EMP, REASON], {encoding: 'utf8'}).trim().split('\n').pop());
    console.log(`      base : ${JSON.stringify(out)}`); const bad = R.db(out); if (bad) throw new Error(bad); });
  await ctx.close();
}
await b.close();
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.length - failures}/${results.length} PASS · ${failures} FAIL`);
process.exit(failures ? 1 : 0);
