// Offline proof on a phone (owner decisions 2026-10-25 and 2026-10-30) — LOCAL stack, REAL server and database, Caissier
// account (../.local/caissier/.account.json, never printed). An Android phone is emulated (390 × 844, touch, mobile user
// agent) on the compiled app with its service worker:
//   online sign-in (offline pack downloaded) → airplane mode → the app is CLOSED and REOPENED without network →
//   cash desk opened, a family enrolled, a fee collected, all offline → network back, and the server's FIRST answer to
//   the enrollment and to the payment is LOST on the way (the server recorded them, the phone never heard back) →
//   automatic synchronisation → the database holds every operation exactly ONCE (never 0, never 2).
// Screenshots: ../.local/offline_mobile.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
const acc = JSON.parse(fs.readFileSync('../.local/caissier/.account.json', 'utf8'));
const OUT = '../.local/offline_mobile'; fs.mkdirSync(OUT, {recursive: true});
const RUN = Date.now().toString(36).slice(-4).toUpperCase(); const PUPIL = `HORSLIGNE${RUN}`;
const results = []; let failures = 0; const http = [];
const b = await chromium.launch({channel: 'msedge'});
const ctx = await b.newContext({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true, deviceScaleFactor: 2, serviceWorkers: 'allow',
  userAgent: 'Mozilla/5.0 (Linux; Android 13; SM-A145F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36'});
const p = await ctx.newPage();
p.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/') && r.status() >= 400 && !u.pathname.includes('/auth/') && !u.pathname.includes('branding/logo')) http.push(`${r.request().method()} ${u.pathname} → ${r.status()}`); });
p.on('pageerror', e => http.push(`JS ${String(e.message).slice(0, 140)}`));
async function step(name, fn) {
  let status = 'PASS', detail = ''; const before = http.length;
  try { await fn(); } catch (e) { status = 'FAIL'; detail = String(e.message).split('\n').slice(0, 2).join(' / ').slice(0, 300); }
  const n = http.slice(before).filter(x => !/→ 0$/.test(x)); if (n.length && status === 'PASS') { status = 'FAIL'; detail = `refus serveur : ${[...new Set(n)].join(', ')}`; }
  if (status !== 'PASS') failures++; results.push({name, status, detail}); console.log(`${status.padEnd(5)} ${name}${detail ? ` — ${detail}` : ''}`);
  await p.screenshot({path: `${OUT}/${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`, fullPage: false}).catch(() => {});
}
// Phone navigation: bottom bar for the main modules, « Menu » for the others.
const go = async (bottom, full) => {
  const bar = p.getByRole('navigation', {name: 'Navigation rapide'});
  if (await bar.getByRole('button', {name: bottom, exact: true}).count()) await bar.getByRole('button', {name: bottom, exact: true}).click();
  else { await bar.getByRole('button', {name: 'Tous les modules'}).click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: full, exact: true}).click(); }
  await p.waitForTimeout(1500); };
const tab = async t => { await p.getByRole('button', {name: t, exact: true}).first().click(); await p.waitForTimeout(1200); };
const outbox = () => p.evaluate(() => new Promise(res => { const r = indexedDB.open('edusync-outbox-v1'); r.onsuccess = () => { const db = r.result;
  const q = db.transaction('requests').objectStore('requests').getAll(); q.onsuccess = () => res(q.result.map(x => ({kind: x.kind, key: x.idempotencyKey, status: x.status, label: x.label, error: x.lastError}))); }; r.onerror = () => res([]); }));
const pack = () => p.evaluate(() => new Promise(res => { const r = indexedDB.open('edusync-outbox-v1'); r.onsuccess = () => { const db = r.result;
  const q = db.transaction('packs').objectStore('packs').getAll(); q.onsuccess = () => res(q.result[0] ?? null); }; r.onerror = () => res(null); }));

let payee = null; let keys = [];
await step('01 connexion en ligne sur le téléphone, paquet hors ligne téléchargé', async () => {
  await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000});
  await p.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  for (let i = 0; i < 30 && !(await pack()); i++) await p.waitForTimeout(1000);
  const pk = await pack(); if (!pk) throw new Error('paquet hors ligne absent après 30 s');
  // a pupil with an eligible open fee, taken from the phone's own copy (what the cashier will find offline)
  for (const person of pk.people) { const open = Object.entries(pk.balances).find(([enr, list]) => (person.enrollment_id === enr || person.enrollments?.includes?.(enr)) && list.some(c => c.eligible && Number(c.remaining) > 0)); if (open) { payee = person; break; } }
  if (!payee) payee = pk.people.find(x => (pk.balances[x.enrollment_id] ?? []).some(c => c.eligible && Number(c.remaining) > 0));
  if (!payee) throw new Error('aucun élève avec un frais payable dans le paquet');
  console.log(`      paquet : ${pk.people.length} élèves · payeur choisi : ${payee.matricule}`);
  if (!await p.getByRole('navigation', {name: 'Navigation rapide'}).isVisible()) throw new Error('barre de navigation mobile absente'); });

await step('01b en ligne : caisse du jour clôturée, pour l’ouvrir ensuite sans réseau', async () => {
  await go('Finance', 'Centre financier'); await tab('Caisse'); await p.locator('.cd-hero h3').filter({hasNotText: 'Chargement'}).waitFor({timeout: 20000});
  const closeBtn = p.getByRole('button', {name: 'Clôturer ma caisse'});
  if (await closeBtn.count()) { await closeBtn.first().click(); const dlg = p.getByRole('dialog', {name: 'Clôturer ma caisse'});
    for (const l of ['Compté FC', 'Compté USD']) { const f = dlg.getByLabel(l); await f.fill((await f.getAttribute('placeholder')) ?? '0'); }
    await dlg.getByRole('button', {name: 'Clôturer ma caisse'}).click(); await dlg.waitFor({state: 'detached', timeout: 20000}); }
  await p.getByRole('button', {name: 'Ouvrir ma caisse'}).first().waitFor({timeout: 20000});
  await go('Accueil', 'Accueil'); });

await step('02 mode avion, application fermée puis rouverte sans réseau : la session tient', async () => {
  await ctx.setOffline(true); await p.reload({waitUntil: 'domcontentloaded'}); await p.locator('.es-shell').waitFor({timeout: 30000});
  if (await p.evaluate(() => navigator.onLine)) throw new Error('le téléphone se croit encore en ligne');
  if (await p.getByLabel('Adresse e-mail').count()) throw new Error('écran de connexion affiché hors ligne : la session est perdue'); });

await step('03 hors ligne : ouverture de caisse enregistrée sur l’appareil', async () => {
  await go('Finance', 'Centre financier'); await tab('Caisse'); await p.waitForTimeout(1500);
  const open = p.getByRole('button', {name: 'Ouvrir ma caisse'});
  if (await open.count()) { await open.first().click(); await p.getByRole('dialog', {name: 'Ouvrir ma caisse'}).getByRole('button', {name: 'Ouvrir ma caisse'}).click();
    await p.getByText(/Hors connexion/).first().waitFor({timeout: 15000}); }
  else throw new Error('« Ouvrir ma caisse » absent hors ligne'); });

await step('04 hors ligne : inscription d’une famille', async () => {
  await go('Élèves', 'Élèves & inscriptions');
  await p.getByRole('button', {name: 'Nouvelle inscription'}).first().click(); const w = p.locator('.enrollmentWizard');
  await w.getByRole('button', {name: 'Créer un nouveau foyer'}).click();
  await w.getByLabel('Nom complet').fill(`Famille ${PUPIL}`); await w.getByLabel('Téléphone').fill('+243 97' + String(Date.now()).slice(-7));
  await w.getByRole('button', {name: 'Continuer'}).click();
  await w.getByLabel('Nom *', {exact: true}).fill(PUPIL); await w.getByLabel('Postnom *').fill('MOBILE'); await w.getByLabel('Prénom *').fill('Esther');
  await w.locator('.cs-trigger').first().click(); await p.locator('.cs-option').first().click(); await w.getByRole('radio', {name: 'Masculin'}).first().click();
  await w.getByRole('button', {name: 'Continuer'}).click(); await w.getByRole('button', {name: /^Valider \d+ inscription/}).click();
  await p.getByText(/Hors connexion|enregistrée sur cet appareil/).first().waitFor({timeout: 20000}); });

await step('05 hors ligne : encaissement d’un élève retrouvé dans la copie locale', async () => {
  await go('Finance', 'Centre financier'); await tab('Encaissement');
  await p.getByPlaceholder(/Nom, matricule, famille/).fill(payee.matricule); await p.locator('.checkoutHits button').first().click({timeout: 15000});
  await p.getByRole('button', {name: 'Action conseillée'}).click({timeout: 15000}); await p.getByText(/[1-9]\d* frais sélectionné|[1-9]\d* obligation\(s\)/).first().waitFor();
  // phone: the selection lives in the bottom bar « Voir / Encaisser », which opens the amount
  if (!await p.getByLabel(/Montant remis/).isVisible().catch(() => false)) await p.getByRole('button', {name: /Voir \/ Encaisser/}).click();
  await p.getByLabel(/Montant remis/).fill('1000'); await p.getByRole('button', {name: /^Encaisser/}).first().click();
  const confirm = p.getByRole('button', {name: /Confirmer|Valider l’encaissement/}); if (await confirm.count()) await confirm.first().click();
  await p.getByText(/Hors connexion|enregistré sur cet appareil/).first().waitFor({timeout: 20000});
  // the cashier closes the transaction sheet (phone) before moving on
  const close = p.locator('.posMobileHead').getByRole('button', {name: 'Fermer la transaction'}); if (await close.isVisible().catch(() => false)) await close.click();
  await p.waitForTimeout(600); });

await step('06 l’appareil montre ce qui attend, avec une clé par opération', async () => {
  const q = await outbox(); keys = q.filter(x => x.kind === 'PAYMENT').map(x => x.key);
  console.log(`      en attente : ${q.map(x => x.label).join(' | ')}`);
  if (!q.some(x => x.kind === 'ENROLLMENT') || !keys.length) throw new Error(`file incomplète : ${JSON.stringify(q.map(x => x.kind))}`);
  if (new Set(q.map(x => x.key)).size !== q.length) throw new Error('deux opérations partagent la même clé');
  await p.getByRole('button', {name: /Synchronisation : \d+ en attente/}).waitFor({timeout: 10000}); });

await step('07 retour du réseau avec réponses perdues : synchronisation automatique, sans doublon', async () => {
  // The first answer to the enrollment and to the payment reaches the server, which records it, but never the phone.
  const lost = new Set();
  await ctx.route(/\/api\/v1\/(schooling\/enrollments\/family|finance\/checkout\/collect)$/, async route => {
    const path = new URL(route.request().url()).pathname;
    if (!lost.has(path)) { lost.add(path); await route.fetch().catch(() => null); return route.abort('connectionreset'); }
    return route.continue(); });
  await ctx.setOffline(false); await p.evaluate(() => window.dispatchEvent(new Event('online')));
  for (let i = 0; i < 120; i++) { const q = await outbox(); if (!q.some(x => x.status === 'PENDING') && lost.size >= 2) break;
    if (i % 15 === 14) await p.evaluate(() => window.dispatchEvent(new Event('online'))); await p.waitForTimeout(1000); }
  const q = await outbox();
  if (lost.size < 2) throw new Error(`réponses perdues simulées : ${lost.size}/2`);
  if (q.length) throw new Error(`reste sur l’appareil : ${JSON.stringify(q.map(x => `${x.label} ${x.status} ${x.error ?? ''}`))}`); });

await step('08 base de données : chaque opération existe exactement une fois', async () => {
  const out = JSON.parse(execFileSync('../.venv/Scripts/python.exe', ['../tools/local/offline_proof_db.py', PUPIL, keys.join(',')], {encoding: 'utf8'}).trim().split('\n').pop());
  console.log(`      base : ${JSON.stringify(out)}`);
  if (out.pupils !== 1 || out.enrollments !== 1) throw new Error(`élève inscrit hors ligne : ${out.pupils} fiche(s), ${out.enrollments} inscription(s) (attendu 1 et 1)`);
  for (const [k, v] of Object.entries(out.keys)) if (v.payments !== 1) throw new Error(`paiement ${k.slice(0, 8)}… : ${v.payments} ligne(s) (attendu 1)`); });

await step('09 l’élève inscrit hors ligne est visible en ligne, aucun conflit à vérifier', async () => {
  await go('Élèves', 'Élèves & inscriptions'); await p.getByRole('tab', {name: /Annuaire élèves/}).click(); await p.waitForTimeout(1200);
  await p.getByRole('textbox', {name: 'Rechercher un élève'}).fill(PUPIL); await p.getByText(PUPIL).first().waitFor({timeout: 20000});
  if (await p.getByRole('button', {name: /à vérifier/}).count()) throw new Error('des opérations sont « à vérifier »');
  const o = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth); if (o > 1) throw new Error(`débordement horizontal +${o}px`); });

await ctx.close(); await b.close();
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.length - failures}/${results.length} PASS · ${failures} FAIL`);
process.exit(failures ? 1 : 0);
