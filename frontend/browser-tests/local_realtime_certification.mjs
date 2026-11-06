// Live changes (owner, 2026-11-01: « quand un caissier encaisse, après la validation, automatiquement tout le monde voit
// sans recharger » — for every school role). LOCAL stack, school C, three browsers open at the same time:
//   Caissier enrols a pupil → the Secrétariat's « Élèves » screen shows one more pupil, WITHOUT any reload;
//   Caissier collects a fee → the Gestionnaire's « Le point du jour » shows the new amount collected today, WITHOUT reload.
// A reload is detected (page « load » events counted): any reload is a FAIL. Accounts from .local (never printed).
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const OUT = '../.local/realtime'; fs.mkdirSync(OUT, {recursive: true});
const RUN = Date.now().toString(36).slice(-4).toUpperCase(); const PUPIL = `DIRECT${RUN}`;
// Light on the machine (2026-11-01, laptop thermal cut-offs): two browsers at a time — the Caissier and ONE observer.
//   node browser-tests/local_realtime_certification.mjs secretariat   |   … gestionnaire
const OBS = process.argv[2] || 'secretariat';
const results = []; let failures = 0;
const b = await chromium.launch({channel: 'msedge'});
async function open(folder) {
  const acc = JSON.parse(fs.readFileSync(`../.local/${folder}/.account.json`, 'utf8'));
  const p = await (await b.newContext({viewport: {width: 1440, height: 900}})).newPage(); p.loads = 0; p.on('load', () => { p.loads++; });
  await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500); return p; }
async function step(p, name, fn) { let status = 'PASS', detail = '';
  try { await fn(); } catch (e) { status = 'FAIL'; detail = String(e.message).split('\n').slice(0, 2).join(' / ').slice(0, 300); }
  if (status !== 'PASS') failures++; results.push({name, status, detail}); console.log(`${status.padEnd(5)} ${name}${detail ? ` — ${detail}` : ''}`);
  await p.screenshot({path: `${OUT}/${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`}).catch(() => {}); }
const nav = p => p.getByRole('complementary', {name: 'Navigation principale'});
const module = async (p, m) => { await nav(p).getByRole('button', {name: m, exact: true}).click(); await p.waitForTimeout(1500); };
const waitFor = async (fn, ms = 12000) => { const t0 = Date.now(); for (;;) { const v = await fn(); if (v) return Date.now() - t0; if (Date.now() - t0 > ms) return -1; await new Promise(r => setTimeout(r, 300)); } };

const cash = await open('caissier'); const sec = OBS === 'secretariat' ? await open('secretariat') : null; const gest = OBS === 'gestionnaire' ? await open('gestionnaire') : null;
// Secrétariat watches « Élèves & inscriptions »; Gestionnaire watches his home (« Le point du jour »).
if (sec) await module(sec, 'Élèves & inscriptions');
const pupils = async () => Number((await sec.locator('.schoolingKpi').first().locator('b, strong').first().innerText().catch(() => '0')).replace(/\D/g, '')) || 0;
const today = async () => (await gest.locator('.sh-brief-item b').allInnerTexts().catch(() => [])).find(t => /encaiss|Aucune caisse/i.test(t)) || '';
if (gest) await gest.locator('.sh-brief-item').first().waitFor({timeout: 20000});
const before = {pupils: sec ? await pupils() : 0, today: gest ? await today() : '', secLoads: sec?.loads, gestLoads: gest?.loads};
console.log(`      avant : ${before.pupils} élèves (Secrétariat) · « ${before.today} » (Gestionnaire)`);

await step(cash, '01 caissier : caisse ouverte et élève inscrit', async () => {
  await module(cash, 'Centre financier'); await cash.getByRole('button', {name: 'Caisse', exact: true}).first().click(); await cash.waitForTimeout(1200);
  await cash.locator('.cd-hero h3').filter({hasNotText: 'Chargement'}).waitFor({timeout: 20000});
  const o = cash.getByRole('button', {name: 'Ouvrir ma caisse'}); if (await o.count()) { await o.first().click(); await cash.getByRole('dialog', {name: 'Ouvrir ma caisse'}).getByRole('button', {name: 'Ouvrir ma caisse'}).click(); await cash.waitForTimeout(1500); }
  await module(cash, 'Élèves & inscriptions'); await cash.getByRole('button', {name: 'Nouvelle inscription'}).first().click(); const w = cash.locator('.enrollmentWizard');
  await w.getByRole('button', {name: 'Créer un nouveau foyer'}).click(); await w.getByLabel('Nom complet').fill(`Famille ${PUPIL}`); await w.getByLabel('Téléphone').fill('+243 97' + String(Date.now()).slice(-7));
  await w.getByRole('button', {name: 'Continuer'}).click();
  await w.getByLabel('Nom *', {exact: true}).fill(PUPIL); await w.getByLabel('Postnom *').fill('LIVE'); await w.getByLabel('Prénom *').fill('Grace');
  await w.locator('.cs-trigger').first().click(); await p.locator('.cs-option').first().click(); await w.getByRole('radio', {name: 'Masculin'}).first().click();
  await w.getByRole('button', {name: 'Continuer'}).click(); await w.getByRole('button', {name: /^Valider \d+ inscription/}).click(); await w.waitFor({state: 'detached', timeout: 30000}); });
if (sec) await step(sec, '02 Secrétariat : le nouvel élève apparaît sans recharger', async () => {
  const ms = await waitFor(async () => (await pupils()) > before.pupils);
  if (ms < 0) throw new Error(`toujours ${await pupils()} élèves après 12 s`);
  if (sec.loads !== before.secLoads) throw new Error('la page a été rechargée');
  console.log(`      ${before.pupils} → ${await pupils()} élèves en ${(ms / 1000).toFixed(1)} s, sans rechargement`); });
await step(cash, '03 caissier : encaissement validé', async () => {
  await module(cash, 'Centre financier'); await cash.getByRole('button', {name: 'Encaissement', exact: true}).first().click(); await cash.waitForTimeout(1000);
  await cash.getByPlaceholder(/Nom, matricule, famille/).fill(PUPIL); await cash.locator('.checkoutHits button').first().click({timeout: 15000});
  await cash.getByRole('button', {name: 'Action conseillée'}).click(); await cash.waitForTimeout(800);
  await cash.getByLabel(/Montant remis/).fill('12000'); await cash.getByRole('button', {name: /^Encaisser/}).first().click();
  const c = cash.getByRole('button', {name: /Confirmer|Valider l’encaissement/}); if (await c.count()) await c.first().click();
  await cash.getByText(/Reçu|REC-/).first().waitFor({timeout: 20000}); });
if (gest) await step(gest, '04 Gestionnaire : « Le point du jour » montre le nouvel encaissement sans recharger', async () => {
  const ms = await waitFor(async () => { const t = await today(); return t && t !== before.today; });
  if (ms < 0) throw new Error(`inchangé après 12 s : « ${await today()} »`);
  if (gest.loads !== before.gestLoads) throw new Error('la page a été rechargée');
  console.log(`      « ${before.today} » → « ${await today()} » en ${(ms / 1000).toFixed(1)} s, sans rechargement`); });
await b.close();
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.length - failures}/${results.length} PASS · ${failures} FAIL`);
process.exit(failures ? 1 : 0);
