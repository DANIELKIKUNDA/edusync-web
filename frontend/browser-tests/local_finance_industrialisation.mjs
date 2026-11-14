// Centre financier walkthrough (2026-10-25) — LOCAL stack, school C, cashier account. Owner report: months cannot be
// skipped, the pay button is always visible, enrollment then « Encaisser maintenant », Suivi financier (who is in order
// for a month, printable list), pupil file with its financial situation, past cash sessions. Account never printed.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const acc = JSON.parse(fs.readFileSync('../.local/caissier/.account.json', 'utf8'));
const OUT = '../.local/finance'; fs.mkdirSync(OUT, {recursive: true});
const RUN = Date.now().toString(36).slice(-4).toUpperCase(); const PUPIL = `BOLINGO${RUN}`;
const http = []; let failures = 0;
const b = await chromium.launch({channel: 'msedge'});
const ctx = await b.newContext({viewport: {width: 1440, height: 900}, acceptDownloads: true}); const p = await ctx.newPage();
ctx.on('page', np => { if (np !== p) setTimeout(() => np.close().catch(() => {}), 1500); });
p.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/') && r.status() >= 400 && !u.pathname.includes('/auth/') && !u.pathname.includes('branding/logo')) http.push(`${r.request().method()} ${u.pathname} → ${r.status()}`); });
p.on('pageerror', e => http.push(`JS ${String(e.message).slice(0, 120)}`));
async function step(name, fn) {
  const before = http.length; let status = 'OK', detail = '';
  try { await fn(); await p.waitForTimeout(400);
    if (await p.getByText('Une difficulté est survenue').count()) { status = 'MESSAGE VAGUE'; }
  } catch (e) { status = 'ÉCHEC'; detail = String(e.message).split('\n').slice(0, 2).join(' / ').slice(0, 300); }
  const n = http.slice(before); if (n.length && status === 'OK') status = 'HTTP';
  if (status !== 'OK') failures++;
  console.log(`${status.padEnd(14)} ${name}${detail ? ` — ${detail}` : ''}${n.length ? ` [${n.join(', ')}]` : ''}`);
  await p.screenshot({path: `${OUT}/${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`, fullPage: false});
}
const nav = () => p.getByRole('complementary', {name: 'Navigation principale'});
const module = async m => { await nav().getByRole('button', {name: m, exact: true}).click(); await p.waitForTimeout(1200); };
const finTab = async t => { await p.locator('.financeTabs button', {hasText: t}).filter({hasText: new RegExp(`^${t}$`)}).first().click(); await p.waitForTimeout(1200); };

await step('01 connexion', async () => { await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 30000}); });
await step('02 caisse ouverte', async () => { await module('Centre financier'); await finTab('Caisse');
  await p.locator('.cd-hero h3').filter({hasNotText: 'Chargement'}).waitFor({timeout: 20000});
  const open = p.getByRole('button', {name: 'Ouvrir ma caisse'}); if (await open.count()) { await open.first().click(); await p.getByRole('dialog', {name: 'Ouvrir ma caisse'}).getByRole('button', {name: 'Ouvrir ma caisse'}).click(); }
  await p.locator('.cd-hero.open').waitFor({timeout: 15000}); await p.getByText('Caisses passées').waitFor(); });

await step('10 inscription puis « Encaisser maintenant »', async () => { await module('Élèves & inscriptions');
  await p.getByRole('button', {name: 'Nouvelle inscription'}).first().click(); const w = p.locator('.enrollmentWizard');
  await w.getByRole('button', {name: 'Créer un nouveau foyer'}).click();
  await w.getByLabel('Nom complet').fill(`Lusamba ${RUN}`); await w.getByLabel('Téléphone').fill('+243 99' + String(Date.now()).slice(-7));
  await w.getByRole('button', {name: 'Continuer'}).click();
  await w.getByLabel('Nom *', {exact: true}).fill(PUPIL); await w.getByLabel('Postnom *').fill('LUSAMBA'); await w.getByLabel('Prénom *').fill('Divine');
  await w.locator('.cs-trigger').first().click(); await p.locator('.cs-option').first().click(); await w.getByRole('radio', {name: 'Féminin'}).first().click();
  await w.getByRole('button', {name: 'Continuer'}).click(); await w.getByRole('button', {name: /^Valider \d+ inscription/}).click(); await w.waitFor({state: 'detached', timeout: 30000});
  await p.getByText(/Inscription enregistrée/).first().waitFor({timeout: 10000});
  await p.getByRole('button', {name: 'Encaisser maintenant'}).first().click();
  await p.locator('.checkoutHits button', {hasText: PUPIL}).first().click({timeout: 15000});
  await p.getByText(/obligation\(s\) ouverte\(s\)/).waitFor({timeout: 15000}); });

await step('11 ordre des mois et bouton toujours visible', async () => {
  const locked = await p.locator('button.chargeRow[disabled]', {hasText: /Octobre|Novembre/}).count(); if (!locked) throw new Error('un mois suivant n’est pas verrouillé');
  const box = await p.locator('.checkoutPay .collectBtn').boundingBox(); if (!box || box.y + box.height > 900) throw new Error(`« Encaisser maintenant » hors de l’écran (y=${box?.y})`); });

await step('20 suivi financier : classe, période, listes', async () => { await module('Centre financier'); await finTab('Suivi financier');
  const cls = p.locator('.ff-filters').getByLabel('Classe'); await cls.selectOption({index: 1}); await p.locator('.ff-kpis').waitFor({timeout: 15000});
  const not = Number(await p.locator('.ff-kpis .not b').innerText()); const ok = Number(await p.locator('.ff-kpis .ok b').innerText());
  if (Number.isNaN(not) || Number.isNaN(ok)) throw new Error('compteurs illisibles');
  if (await p.locator('.ff-chips button').count()) { await p.locator('.ff-chips button').first().click(); await p.waitForTimeout(800); }
  await p.getByRole('button', {name: 'Ce mois seulement'}).click(); await p.waitForTimeout(800); await p.getByRole('button', {name: 'Jusqu’à ce mois'}).click(); await p.waitForTimeout(800);
  await p.locator('.ff-kpis .ok').click(); await p.locator('.ff-kpis .not').click(); });
await step('21 suivi financier : liste à emporter et Excel', async () => {
  const list = p.getByRole('button', {name: 'Liste à emporter en classe'}); if (await list.isEnabled()) { await list.click(); await p.waitForTimeout(1500); }
  await p.getByRole('button', {name: 'Toute la classe'}).click(); await p.waitForTimeout(1500);
  const dl = p.waitForEvent('download', {timeout: 15000}).catch(() => null); await p.locator('.ff-bar').getByRole('button', {name: 'Excel'}).click(); await dl; });

await step('30 fiche élève : situation financière', async () => { await module('Élèves & inscriptions'); await p.getByRole('tab', {name: 'Annuaire élèves'}).click();
  await p.locator('.kp-directory').getByPlaceholder(/Matricule, nom/).fill(PUPIL); await p.waitForTimeout(1500); await p.locator('button.kp-row', {hasText: PUPIL}).first().click();
  await p.locator('.sf-root').waitFor({timeout: 15000}); await p.locator('.sf-sum, .sf-empty').first().waitFor({timeout: 15000});
  await p.locator('.sf-tabs button', {hasText: 'Paiements'}).click(); await p.keyboard.press('Escape'); });

await step('40 caisses passées : filtre et export de la période', async () => { await module('Centre financier'); await finTab('Caisse');
  await p.getByRole('button', {name: '7 derniers jours'}).click(); await p.waitForTimeout(1000);
  const dl = p.waitForEvent('download', {timeout: 15000}).catch(() => null); await p.getByRole('button', {name: 'Exporter la période'}).click(); await dl; });

console.log(`\n${failures} échec(s) · erreurs : ${http.join(', ') || 'aucune'}`);
await b.close(); process.exit(failures ? 1 : 0);
