// Élèves & inscriptions + Effectifs & dépôts walkthrough (2026-10-25) — LOCAL stack, school C, cashier account
// (CAISSIER ⊇ SECRÉTARIAT). Checks the owner's report: home search opens a real search, enrollment chooses the section
// then the class, re-enrollment is its own procedure, directory filters, guided import, Effectifs indicators and
// deposit dialog. Account in ../.local/caissier/.account.json (never printed). Screenshots in ../.local/eleves.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const acc = JSON.parse(fs.readFileSync('../.local/caissier/.account.json', 'utf8'));
const OUT = '../.local/eleves'; fs.mkdirSync(OUT, {recursive: true});
const RUN = Date.now().toString(36).slice(-4).toUpperCase(); const PUPIL = `NGALULA${RUN}`;
const http = []; let failures = 0;
const b = await chromium.launch({channel: 'msedge'});
const width = Number(process.env.W || 1440);
const ctx = await b.newContext({viewport: {width, height: 900}}); const p = await ctx.newPage();
p.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/') && r.status() >= 400 && !u.pathname.includes('/auth/') && !u.pathname.includes('branding/logo')) http.push(`${r.request().method()} ${u.pathname} → ${r.status()}`); });
p.on('pageerror', e => http.push(`JS ${String(e.message).slice(0, 120)}`));
async function step(name, fn) {
  const before = http.length; let status = 'OK', detail = '';
  try { await fn(); await p.waitForTimeout(400);
    const alerts = (await p.locator('.error:visible').allInnerTexts()).map(t => t.trim()).filter(Boolean);
    if (alerts.length) { status = 'ERREUR AFFICHÉE'; detail = alerts.join(' | ').slice(0, 300); }
  } catch (e) { status = 'ÉCHEC'; detail = String(e.message).split('\n').slice(0, 3).join(' / ').slice(0, 400); }
  const n = http.slice(before); if (n.length && status === 'OK') status = 'HTTP';
  if (status !== 'OK') failures++;
  console.log(`${status.padEnd(16)} ${name}${detail ? ` — ${detail}` : ''}${n.length ? ` [${n.join(', ')}]` : ''}`);
  await p.screenshot({path: `${OUT}/${width}_${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`, fullPage: true});
}
const nav = () => p.getByRole('complementary', {name: 'Navigation principale'});
const module = async m => { if (width < 900) { await p.getByRole('button', {name: 'Tous les modules'}).click(); await p.waitForTimeout(500); await p.getByRole('button', {name: m, exact: true}).filter({visible: true}).last().click(); }
  else await nav().getByRole('button', {name: m, exact: true}).click(); await p.waitForTimeout(1200); };
const tab = async t => { await p.getByRole('tab', {name: t}).first().click(); await p.waitForTimeout(900); };

await step('01 connexion', async () => { await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 30000}); });

await step('10 inscription : section puis classe filtrée', async () => { await module('Élèves & inscriptions');
  await tab('Inscription / Réinscription');
  await p.locator('.kp-choiceCard', {hasText: 'Nouvelle inscription'}).waitFor(); await p.locator('.kp-choiceCard', {hasText: 'Réinscription'}).waitFor();
  await p.locator('.kp-choiceCard', {hasText: 'Nouvelle inscription'}).click(); const w = p.locator('.enrollmentWizard');
  await w.getByRole('button', {name: 'Créer un nouveau foyer'}).click();
  await w.getByLabel('Nom complet').fill(`Tshibola ${RUN}`); await w.getByLabel('Téléphone').fill('+243 98' + String(Date.now()).slice(-7));
  await w.getByRole('button', {name: 'Continuer'}).click();
  await w.getByLabel('Nom *', {exact: true}).fill(PUPIL); await w.getByLabel('Postnom *').fill('TSHIBOLA'); await w.getByLabel('Prénom *').fill('Grâce');
  const secs = w.locator('.kp-sections button'); const nSec = await secs.count(); if (nSec < 1) throw new Error('aucune puce de section');
  const allBefore = await w.locator('.kp-classes button').count();
  await secs.nth(nSec - 1).click(); await p.waitForTimeout(200);
  const filtered = await w.locator('.kp-classes button').count(); if (!filtered) throw new Error('aucune classe après le choix de la section');
  if (nSec > 1 && allBefore && filtered >= allBefore) throw new Error('les classes ne sont pas filtrées par section');
  await w.locator('.kp-classes button').first().click(); await w.locator('.kp-chosen').waitFor();
  await w.getByLabel('Sexe *').selectOption({index: 2});
  await w.getByRole('button', {name: 'Continuer'}).click(); await w.waitFor({state: 'detached', timeout: 30000});
  await p.getByText(PUPIL).first().waitFor({timeout: 15000}); });

await step('20 annuaire : filtres section / classe / sexe', async () => { await tab('Annuaire élèves');
  const d = p.locator('.kp-directory'); await d.waitFor();
  const sec = d.getByLabel('Section'); const opts = await sec.locator('option').count(); if (opts < 2) throw new Error('pas de section dans le filtre');
  await sec.selectOption({index: opts - 1}); await p.waitForTimeout(900);
  const cls = d.getByLabel('Classe'); if (await cls.locator('option').count() < 2) throw new Error('classes non filtrées');
  await cls.selectOption({index: 1}); await p.waitForTimeout(900);
  await d.getByLabel('Sexe').selectOption('F'); await p.waitForTimeout(900);
  await d.getByRole('button', {name: /Réinitialiser/}).click(); await p.waitForTimeout(900);
  await d.getByPlaceholder(/Matricule, nom/).fill(PUPIL); await p.waitForTimeout(1200);
  await d.locator('button.kp-row', {hasText: PUPIL}).first().waitFor({timeout: 10000}); });

await step('30 réinscription : procédure distincte et garde « déjà inscrit »', async () => {
  await p.getByRole('button', {name: 'Réinscrire'}).first().click(); const dlg = p.getByRole('dialog').last(); await dlg.waitFor();
  await dlg.getByLabel('Rechercher l’élève à réinscrire').fill(PUPIL); await dlg.locator('.kp-hit').first().click({timeout: 15000});
  await dlg.getByText(/déjà inscrit/).waitFor({timeout: 10000});
  await dlg.getByRole('button', {name: 'Annuler'}).click(); });

await step('40 import : parcours guidé en 4 étapes', async () => { await tab('Import');
  await p.locator('.ki-steps li').nth(3).waitFor(); await p.getByText('Glissez le fichier ici ou cliquez pour le choisir').waitFor();
  if (!(await p.getByRole('button', {name: 'Analyser le fichier'}).isDisabled())) throw new Error('analyse possible sans fichier'); });

await step('50 accueil : la recherche ouvre une vraie recherche', async () => { await module('Accueil');
  await p.locator('.sh-search').click(); const dlg = p.getByRole('dialog', {name: 'Rechercher un élève'}); await dlg.waitFor();
  await dlg.getByRole('combobox').fill(PUPIL); await dlg.getByRole('option').first().waitFor({timeout: 10000});
  await p.keyboard.press('Enter'); await p.getByText(PUPIL).first().waitFor({timeout: 15000});
  if (!(await p.locator('.studentDrawer, [class*=Drawer]').count())) throw new Error('la fiche de l’élève ne s’ouvre pas');
  await p.keyboard.press('Escape'); await p.waitForTimeout(300); const close = p.getByRole('button', {name: 'Fermer'}).first(); if (await close.isVisible().catch(() => false)) await close.click(); await p.waitForTimeout(400); });

await step('60 effectifs : indicateurs cliquables et répartition', async () => { await module('Effectifs & dépôts');
  await p.locator('.fx2Kpis button', {hasText: 'Abandons & transferts'}).click(); await p.waitForTimeout(700);
  if (await p.getByRole('tab', {name: 'Mouvements'}).count()) { await p.getByRole('tab', {name: 'Mouvements'}).click(); await p.locator('.fx2Chips button', {hasText: 'Transferts'}).click(); await p.waitForTimeout(700); }
  await p.getByRole('tab', {name: 'Par classe'}).click(); await p.waitForTimeout(1000);
  if (await p.locator('.fx2BarRow').count()) { await p.locator('.fx2BarRow').first().hover(); await p.locator('.fx2Tip').waitFor(); await p.locator('.fx2BarRow').first().click(); await p.waitForTimeout(300); }
  await p.getByText('Total général').count(); });

await step('70 dépôts : boîte guidée', async () => { await p.locator('.fx2Kpis button', {hasText: 'Dépôts matériels'}).click(); await p.waitForTimeout(900);
  const add = p.getByRole('button', {name: 'Enregistrer un dépôt'}); if (!(await add.count())) return;
  await add.click(); const dlg = p.getByRole('dialog', {name: 'Nouveau dépôt matériel'}); await dlg.waitFor();
  await dlg.getByLabel('Rechercher l’élève').fill(PUPIL); await dlg.locator('.kp-hit').first().click({timeout: 10000});
  await dlg.locator('.kp-pupil').waitFor(); await p.keyboard.press('Escape'); await dlg.waitFor({state: 'detached'}); });

console.log(`\n${failures} échec(s) · erreurs : ${http.join(', ') || 'aucune'}`);
await b.close(); process.exit(failures ? 1 : 0);
