// Cashier certification (2026-10-24) — LOCAL stack, school C. The cashier (who, in the DRC, is usually also the
// secretary: CAISSIER ⊇ SECRÉTARIAT, migration 0090) does a real day at the desk: open the cash desk, enroll a pupil,
// collect the first fee, open the receipt, sell a school article, record an expense, close the cash desk. The account
// is created by the administrator (local_admin_finition / _caissier_tour) and stored in ../.local/caissier/.account.json,
// never printed. Screenshots in ../.local/caissier/cert.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const acc = JSON.parse(fs.readFileSync('../.local/caissier/.account.json', 'utf8'));
const OUT = '../.local/caissier/cert'; fs.mkdirSync(OUT, {recursive: true});
const RUN = Date.now().toString(36).slice(-4).toUpperCase(); const PUPIL = `KALALA${RUN}`;
const http = []; let failures = 0; const csp = [];
const b = await chromium.launch({channel: 'msedge'});
const ctx = await b.newContext({viewport: {width: 1440, height: 900}}); const p = await ctx.newPage();
p.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/') && r.status() >= 400 && !u.pathname.includes('/auth/') && !u.pathname.includes('branding/logo')) http.push(`${r.request().method()} ${u.pathname} → ${r.status()}`); });
p.on('console', m => { if (/Content Security Policy|Refused to frame/i.test(m.text())) csp.push(m.text().slice(0, 160)); });
async function step(name, fn) {
  const before = http.length; let status = 'OK', detail = '';
  try { await fn(); await p.waitForTimeout(400);
    const alerts = (await p.locator('[role=alert]:visible, .error:visible').allInnerTexts()).map(t => t.trim()).filter(Boolean);
    if (alerts.length) { status = 'ERREUR AFFICHÉE'; detail = alerts.join(' | ').slice(0, 300); }
  } catch (e) { status = 'ÉCHEC'; detail = String(e.message).split('\n')[0].slice(0, 260); }
  if (status !== 'OK') failures++;
  const n = http.slice(before); console.log(`${status.padEnd(16)} ${name}${detail ? ` — ${detail}` : ''}${n.length ? ` [${n.join(', ')}]` : ''}`);
  await p.screenshot({path: `${OUT}/${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`, fullPage: true});
}
const nav = () => p.getByRole('complementary', {name: 'Navigation principale'});
const module = async m => { await nav().getByRole('button', {name: m, exact: true}).click(); await p.waitForTimeout(1200); };
const toast = t => p.getByText(t).first().waitFor({timeout: 30000});
const finTab = async t => { await p.getByRole('button', {name: t, exact: true}).first().click(); await p.waitForTimeout(1200); };

await step('01 connexion caissier', async () => { await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 30000}); });
await step('02 accueil : outils du guichet, pas de paramétrage', async () => {
  await p.getByRole('button', {name: 'Nouvel encaissement'}).first().waitFor();
  if (await p.getByText('Mise en service de l’établissement').count()) throw new Error('le bloc de mise en service est affiché au caissier');
  if (await p.getByRole('button', {name: 'Compléter le paramétrage'}).count()) throw new Error('raccourci de paramétrage affiché au caissier'); });
await step('03 menu : droits du secrétariat présents', async () => {
  for (const m of ['Élèves & inscriptions', 'Centre financier', 'Personnel', 'Effectifs & dépôts', 'Communication']) await nav().getByRole('button', {name: m, exact: true}).waitFor(); });

await step('10 caisse : ouverture', async () => { await module('Centre financier'); await finTab('Caisse');
  const open = p.getByRole('button', {name: 'Ouvrir ma caisse'}); if (await open.count()) { await open.click(); }
  await p.getByText('OUVERTE').first().waitFor({timeout: 15000}); });

await step('20 inscription d’un élève (droit du secrétariat)', async () => { await module('Élèves & inscriptions');
  await p.getByRole('button', {name: 'Nouvelle inscription'}).click(); const w = p.locator('.enrollmentWizard');
  await w.getByRole('button', {name: 'Créer un nouveau foyer'}).click();
  await w.getByLabel('Nom complet').fill(`Mbuyi ${RUN}`); await w.getByLabel('Téléphone').fill('+243 97' + String(Date.now()).slice(-7));
  await w.getByRole('button', {name: 'Continuer'}).click();
  await w.getByLabel('Nom *', {exact: true}).fill(PUPIL); await w.getByLabel('Postnom *').fill('MBUYI'); await w.getByLabel('Prénom *').fill('Joseph');
  await w.getByLabel('Classe *').selectOption({index: 1}); await w.getByLabel('Sexe *').selectOption({index: 1});
  await w.getByRole('button', {name: 'Continuer'}).click(); await w.waitFor({state: 'detached', timeout: 30000});
  await p.getByText(PUPIL).first().waitFor({timeout: 15000}); });

await step('30 encaissement : recherche et action conseillée', async () => { await module('Centre financier'); await finTab('Encaissement');
  await p.getByPlaceholder(/Nom, matricule, famille/).fill(PUPIL); await p.locator('.checkoutHits button').first().click();
  await p.getByText(/obligation\(s\) ouverte\(s\)/).waitFor({timeout: 15000});
  await p.getByRole('button', {name: 'Action conseillée'}).click(); await p.getByText(/[1-9]\d* frais sélectionné/).waitFor(); });
await step('31 encaissement : montant, encaisser, reçu', async () => {
  const amount = p.getByLabel(/Montant remis/); await amount.fill('12000');
  await p.getByRole('button', {name: /^Encaisser/}).first().click();
  const confirm = p.getByRole('button', {name: /Confirmer|Valider l’encaissement/}); if (await confirm.count()) await confirm.first().click();
  await p.getByText(/Reçu|REC-/).first().waitFor({timeout: 20000}); });
await step('32 reçu : aperçu imprimable', async () => {
  const show = p.getByRole('button', {name: /Imprimer le reçu|Voir le reçu|Reçu/}).first(); await show.click();
  await p.locator('iframe.receiptFrame, .receiptFrame').first().waitFor({timeout: 20000}); await p.waitForTimeout(2500);
  if (csp.length) throw new Error(`aperçu du reçu bloqué par la politique de sécurité : ${csp[0]}`);
  await p.getByRole('button', {name: 'Fermer'}).last().click(); });

await step('40 vente d’un article scolaire', async () => { await module('Centre financier'); await finTab('Encaissement'); await finTab('Autres encaissements');
  await p.getByPlaceholder(/Nom, matricule, famille/).fill(PUPIL); await p.locator('.checkoutHits button').first().click();
  const article = p.locator('button.chargeRow:not([disabled])', {hasText: 'Uniforme'}).first(); await article.click();
  await p.getByText(/Total de la vente/).waitFor();
  await p.getByRole('button', {name: 'Encaisser la vente'}).click();
  await p.locator('.checkoutMessage').first().waitFor({timeout: 20000});
  const msg = await p.locator('.checkoutMessage').first().innerText(); if (!/REC-|enregistr|vendu|reçu/i.test(msg)) throw new Error(`message inattendu : ${msg.slice(0, 120)}`); });

await step('50 caisse : dépense justifiée', async () => { await finTab('Caisse');
  const box = p.locator('form.cashExpenseBox'); await box.getByLabel('Catégorie').fill('Fournitures'); await box.getByLabel('Montant').fill('1000');
  await box.getByLabel('Motif').fill('Craies pour les classes'); await box.getByRole('button', {name: 'Enregistrer la dépense'}).click();
  await p.getByText('Enregistrer cette dépense ?').waitFor(); await p.getByRole('button', {name: 'Enregistrer', exact: true}).click();
  await p.getByText(/Dépense enregistrée/i).first().waitFor({timeout: 15000}); });
await step('51 caisse : clôture au montant compté', async () => {
  const cdf = p.getByLabel('Compté CDF'); await cdf.fill((await cdf.getAttribute('placeholder')) ?? '0');
  const usd = p.getByLabel('Compté USD'); await usd.fill((await usd.getAttribute('placeholder')) ?? '0');
  await p.getByRole('button', {name: 'Clôturer ma caisse'}).click();
  const confirm = p.getByRole('button', {name: /Clôturer|Confirmer/}).last(); if (await p.getByRole('dialog').count()) await confirm.click();
  await p.getByText(/Fermée|FERMÉE|clôturée/i).first().waitFor({timeout: 20000}); });

console.log(`\n${failures} échec(s) · erreurs HTTP : ${http.join(', ') || 'aucune'}`);
await b.close(); process.exit(failures ? 1 : 0);
