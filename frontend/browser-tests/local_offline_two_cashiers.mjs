// School without internet, then synchronisation — owner decision 2026-10-25. LOCAL stack, school C, TWO cashiers.
// Online: both sign in, open their cash desk; the device downloads the offline pack. Network cut for both: both collect
// the SAME September fee of the SAME pupil (concurrency) and cashier 1 also enrolls a new pupil. Network back: cashier 1
// synchronises first (payment + enrollment accepted, final receipt), cashier 2 then synchronises: the duplicate payment is
// refused by the server and kept « À vérifier » with the reason — never counted twice. Accounts never printed.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const A = JSON.parse(fs.readFileSync('../.local/caissier/.account.json', 'utf8'));
const B = JSON.parse(fs.readFileSync('../.local/caissier2/.account.json', 'utf8'));
const OUT = '../.local/offline'; fs.mkdirSync(OUT, {recursive: true});
const RUN = Date.now().toString(36).slice(-4).toUpperCase(); const TARGET = `HORSLIGNE${RUN}`; const NEWPUPIL = `SANSRESEAU${RUN}`;
let failures = 0; const http = [];
const b = await chromium.launch({channel: 'msedge'});
async function session(acc, tag) {
  const ctx = await b.newContext({viewport: {width: 1440, height: 900}}); const p = await ctx.newPage();
  p.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/') && r.status() >= 500) http.push(`${tag} ${r.request().method()} ${u.pathname} → ${r.status()}`); });
  p.on('pageerror', e => http.push(`${tag} JS ${String(e.message).slice(0, 140)}`));
  await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); return {ctx, p};
}
async function step(p, name, fn) {
  let status = 'OK', detail = '';
  try { await fn(); if (await p.getByText('Une difficulté est survenue').count()) status = 'MESSAGE VAGUE'; }
  catch (e) { status = 'ÉCHEC'; detail = String(e.message).split('\n').slice(0, 2).join(' / ').slice(0, 300); }
  if (status !== 'OK') failures++;
  console.log(`${status.padEnd(14)} ${name}${detail ? ` — ${detail}` : ''}`);
  await p.screenshot({path: `${OUT}/${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`});
}
const nav = p => p.getByRole('complementary', {name: 'Navigation principale'});
const module = async (p, m) => { await nav(p).getByRole('button', {name: m, exact: true}).click(); await p.waitForTimeout(1200); };
const finTab = async (p, t) => { await p.locator('.financeTabs button').filter({hasText: new RegExp(`^${t}$`)}).first().click(); await p.waitForTimeout(1000); };
async function openCash(p) { await module(p, 'Centre financier'); await finTab(p, 'Caisse');
  await p.locator('.cd-hero h3').filter({hasNotText: 'Chargement'}).waitFor({timeout: 20000});
  const open = p.getByRole('button', {name: 'Ouvrir ma caisse'}); if (await open.count()) { await open.first().click(); await p.getByRole('dialog', {name: 'Ouvrir ma caisse'}).getByRole('button', {name: 'Ouvrir ma caisse'}).click(); }
  await p.locator('.cd-hero.open').waitFor({timeout: 20000}); }
const packSize = p => p.evaluate(() => new Promise(res => { const r = indexedDB.open('edusync-outbox-v1'); r.onsuccess = () => { try { const t = r.result.transaction('packs', 'readonly').objectStore('packs').getAll(); t.onsuccess = () => res((t.result[0]?.people ?? []).length); t.onerror = () => res(0); } catch { res(0); } }; r.onerror = () => res(0); }));
async function collectSeptember(p) {
  await module(p, 'Centre financier'); await finTab(p, 'Encaissement');
  await p.getByPlaceholder(/Nom, matricule, famille/).fill(TARGET); await p.locator('.checkoutHits button', {hasText: TARGET}).first().click({timeout: 15000});
  await p.locator('button.chargeRow:not([disabled])', {hasText: 'Septembre'}).first().click({timeout: 15000});
  await p.getByLabel(/Montant remis/).fill('15000'); await p.getByRole('button', {name: /^Encaisser maintenant/}).click();
  const confirm = p.getByRole('button', {name: /Confirmer et encaisser|Confirmer|Valider l’encaissement/}); if (await confirm.count()) await confirm.first().click();
  await p.locator('.checkoutMessage').filter({hasText: /Hors connexion : paiement/}).first().waitFor({timeout: 20000}); }

const one = await session(A, 'C1'), two = await session(B, 'C2');
await step(one.p, '01 en ligne : caisses ouvertes, élève cible inscrit', async () => {
  await openCash(one.p); await openCash(two.p);
  await module(one.p, 'Élèves & inscriptions'); await one.p.getByRole('button', {name: 'Nouvelle inscription'}).first().click(); const w = one.p.locator('.enrollmentWizard');
  await w.getByRole('button', {name: 'Créer un nouveau foyer'}).click(); await w.getByLabel('Nom complet').fill(`Foyer ${RUN}`); await w.getByLabel('Téléphone').fill('+243 97' + String(Date.now()).slice(-7));
  await w.getByRole('button', {name: 'Continuer'}).click(); await w.getByLabel('Nom *', {exact: true}).fill(TARGET); await w.getByLabel('Postnom *').fill('RESEAU'); await w.getByLabel('Prénom *').fill('Test');
  await w.locator('.cs-trigger').first().click(); await p.locator('.cs-option').first().click(); await w.getByRole('radio', {name: 'Masculin'}).first().click();
  await w.getByRole('button', {name: 'Continuer'}).click(); await w.getByRole('button', {name: /^Valider \d+ inscription/}).click(); await w.waitFor({state: 'detached', timeout: 30000}); });
await step(one.p, '02 en ligne : paquet hors ligne téléchargé sur les deux appareils', async () => {
  for (const {p} of [one, two]) { await p.reload(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(4000);
    await module(p, 'Élèves & inscriptions'); await module(p, 'Centre financier'); }                       // screens read once online
  const n1 = await packSize(one.p), n2 = await packSize(two.p); if (!n1 || !n2) throw new Error(`paquet absent (C1=${n1}, C2=${n2})`);
  console.log(`               paquet : ${n1} élève(s) sur C1, ${n2} sur C2`); });

await one.ctx.setOffline(true); await two.ctx.setOffline(true);
await step(one.p, '10 hors ligne : C1 encaisse septembre', async () => { await collectSeptember(one.p);
  await one.p.locator('.es-status').filter({hasText: /en attente/}).waitFor({timeout: 10000});
  if (await one.p.locator('button.chargeRow:not([disabled])', {hasText: 'Septembre'}).count()) throw new Error('septembre encore payable sur cet appareil'); });
await step(two.p, '11 hors ligne : C2 encaisse le MÊME septembre (concurrence)', async () => { await collectSeptember(two.p); });
await step(one.p, '12 hors ligne : C1 inscrit un nouvel élève', async () => {
  await module(one.p, 'Élèves & inscriptions'); await one.p.getByRole('button', {name: 'Nouvelle inscription'}).first().click(); const w = one.p.locator('.enrollmentWizard');
  await w.getByRole('button', {name: 'Créer un nouveau foyer'}).click(); await w.getByLabel('Nom complet').fill(`Foyer hors ligne ${RUN}`); await w.getByLabel('Téléphone').fill('+243 98' + String(Date.now()).slice(-7));
  await w.getByRole('button', {name: 'Continuer'}).click(); await w.getByLabel('Nom *', {exact: true}).fill(NEWPUPIL); await w.getByLabel('Postnom *').fill('HORS'); await w.getByLabel('Prénom *').fill('Ligne');
  await w.locator('.cs-trigger').first().click(); await p.locator('.cs-option').first().click(); await w.getByRole('radio', {name: 'Féminin'}).first().click();
  await w.getByRole('button', {name: 'Continuer'}).click(); await w.getByRole('button', {name: /^Valider \d+ inscription/}).click(); await one.p.getByText(/Hors connexion : inscription/).first().waitFor({timeout: 20000});
  await one.p.locator('.es-status').filter({hasText: /2 en attente/}).waitFor({timeout: 10000}); });
await step(one.p, '13 hors ligne : la caisse montre les opérations en attente', async () => { await module(one.p, 'Centre financier'); await finTab(one.p, 'Caisse');
  await one.p.locator('.cd-pending').first().waitFor({timeout: 10000}); });

await one.ctx.setOffline(false);
await step(one.p, '20 retour du réseau : C1 synchronise (paiement + inscription acceptés)', async () => {
  await one.p.getByText(/Synchronisé : Encaissement/).first().waitFor({timeout: 60000}); await one.p.getByText(/Synchronisé : Inscription/).first().waitFor({timeout: 60000});
  await one.p.waitForFunction(() => !/en attente|à synchroniser/.test(document.querySelector('.es-status')?.textContent ?? ''), null, {timeout: 30000}); });
await two.ctx.setOffline(false);
await step(two.p, '21 retour du réseau : C2 synchronise, le doublon est refusé et gardé « à vérifier »', async () => {
  await two.p.locator('.es-status').filter({hasText: /à vérifier/}).waitFor({timeout: 60000});
  await module(two.p, 'Synchronisation'); await two.p.locator('.ob-panel li.bad').first().waitFor({timeout: 15000});
  console.log('               raison du refus :', (await two.p.locator('.ob-panel li.bad small').first().innerText()).replace(/\s+/g, ' ').slice(0, 160)); });
await step(one.p, '22 serveur : élève inscrit hors ligne présent, septembre payé une seule fois', async () => {
  await module(one.p, 'Élèves & inscriptions'); await one.p.getByRole('tab', {name: 'Annuaire élèves'}).click();
  await one.p.locator('.kp-directory').getByPlaceholder(/Matricule, nom/).fill(NEWPUPIL); await one.p.locator('button.kp-row', {hasText: NEWPUPIL}).first().waitFor({timeout: 15000});
  await one.p.locator('.kp-directory').getByPlaceholder(/Matricule, nom/).fill(TARGET); await one.p.waitForTimeout(1500); await one.p.locator('button.kp-row', {hasText: TARGET}).first().click();
  await one.p.locator('.sf-tabs button', {hasText: 'Paiements'}).click(); await one.p.waitForTimeout(800);
  const rows = await one.p.locator('.sf-pay:not(.sf-th)').count(); if (rows !== 1) throw new Error(`${rows} paiement(s) enregistré(s) pour septembre au lieu d’un seul`); });

console.log(`\n${failures} échec(s) · erreurs : ${http.join(', ') || 'aucune'}`);
await b.close(); process.exit(failures ? 1 : 0);
