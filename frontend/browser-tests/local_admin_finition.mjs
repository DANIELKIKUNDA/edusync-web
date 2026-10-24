// Administrator finishing pass (2026-10-24) — the school system administrator does, in a real browser on the LOCAL
// stack (real API, real database, school C of the local fixtures), what this release adds or reworks. The test password
// is read from the local fixtures file and never printed. Screenshots in ../.local/finition.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const admin = FX.C.users.ADMIN; const OUT = '../.local/finition'; fs.mkdirSync(OUT, {recursive: true});
const http = []; let failures = 0; const RUN = Date.now().toString(36).slice(-4).toUpperCase();
const b = await chromium.launch({channel: 'msedge'});
const p = await (await b.newContext({viewport: {width: 1440, height: 900}})).newPage();
p.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/') && r.status() >= 400) http.push(`${r.request().method()} ${u.pathname} → ${r.status()}`); });
async function step(name, fn) {
  const before = http.length; let status = 'OK', detail = '';
  try { await fn(); await p.waitForTimeout(400);
    const alerts = (await p.locator('[role=alert]:visible, .error:visible').allInnerTexts()).map(t => t.trim()).filter(Boolean);
    if (alerts.length) { status = 'ERREUR AFFICHÉE'; detail = alerts.join(' | ').slice(0, 300); }
  } catch (e) { status = 'ÉCHEC'; detail = String(e.message).split('\n')[0].slice(0, 240); }
  if (status !== 'OK') failures++;
  const n = http.slice(before).filter(x => !x.includes('/auth/') && !x.includes('/branding/logo'));
  console.log(`${status.padEnd(16)} ${name}${detail ? ` — ${detail}` : ''}${n.length ? ` [${n.join(', ')}]` : ''}`);
  await p.screenshot({path: `${OUT}/${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`, fullPage: true});
}
const nav = () => p.getByRole('complementary', {name: 'Navigation principale'});
const module = async m => { await nav().getByRole('button', {name: m, exact: true}).click(); await p.waitForTimeout(1200); };
async function tab(label) { await p.locator('.sp-nav').getByRole('button', {name: new RegExp(`^${label}`)}).click(); await p.waitForTimeout(700); }
const toast = t => p.getByText(t).first().waitFor({timeout: 30000});

await step('01 connexion administrateur', async () => { await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(admin.email); await p.getByLabel('Mot de passe', {exact: true}).fill(admin.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 30000}); });
await step('02 paramétrage : un élément non applicable ne baisse plus le pourcentage', async () => { await module('Paramètres');
  await p.getByRole('heading', {name: 'Paramètres de l’établissement'}).waitFor(); await p.getByText(/100\s*%/).first().waitFor({timeout: 10000}); });

await step('10 année : période d’inscription définie et modifiable', async () => { await tab('Années scolaires');
  const card = p.locator('.yearList article.current'); await card.getByRole('button', {name: /Définir|Modifier/}).click();
  await card.getByLabel('Inscriptions du').fill('2026-08-01'); await card.getByLabel('au').fill('2026-10-15');
  await card.getByRole('button', {name: 'Enregistrer'}).click(); await toast(/Période d’inscription de .* enregistrée/);
  await card.getByText(/Inscriptions : .*→/).waitFor(); });

await step('20 articles : création avec prix, stock de départ et seuil', async () => { await tab('Articles scolaires');
  await p.getByRole('button', {name: 'Nouvel article'}).click(); await p.getByLabel('Article *').fill(`Uniforme ${RUN}`);
  await p.locator('.moneyInput input').fill('25000'); await p.getByLabel('Stock de départ').fill('50'); await p.getByLabel('Seuil d’alerte').fill('10');
  await p.getByRole('button', {name: 'Créer l’article'}).click(); await toast(/Article créé avec 50 en stock/);
  const card = p.locator('.productCard', {hasText: `Uniforme ${RUN}`}); await card.getByText('En stock').waitFor(); await card.locator('.productStock b', {hasText: '50'}).waitFor(); });
await step('21 articles : modifier le prix depuis la carte', async () => { const card = p.locator('.productCard', {hasText: `Uniforme ${RUN}`});
  await card.getByRole('button', {name: 'Prix & réglages'}).click(); await card.getByLabel(/Prix de vente unitaire/).fill('27500');
  await card.getByRole('button', {name: 'Enregistrer'}).click(); await toast('Article mis à jour'); await card.getByText(/27\s?500/).first().waitFor(); });

await step('30 plan anticipé : deux classes seulement', async () => { await tab('Plans anticipés');
  await p.getByRole('button', {name: 'Nouveau plan'}).click(); await p.getByLabel('Nom du plan *').fill(`Plan ${RUN}`);
  await p.getByLabel('Portée *').selectOption({label: 'Classe ouverte'});
  const chips = p.locator('.planTargets .sw-chip'); await chips.nth(0).click(); await chips.nth(1).click();
  await p.getByText(/2 choisies sur/).waitFor();
  await p.locator('.planForm fieldset', {hasText: 'Mois cibles'}).getByLabel('Juin').check();
  await p.locator('.planForm fieldset', {hasText: 'Mois de contribution'}).getByLabel('Octobre').check();
  await p.getByRole('button', {name: 'Enregistrer le plan'}).click(); await toast('Plan créé');
  await p.locator('.planList li', {hasText: `Plan ${RUN}`}).getByText(/Classes /).waitFor(); });

await step('40 tarifs : plusieurs frais appliqués puis un seul enregistrement', async () => { await tab('Tarifs & barèmes');
  await p.getByRole('button', {name: 'Assistant tarifaire'}).click(); const d = p.getByRole('dialog', {name: /Assistant tarifaire/});
  await d.getByLabel('Frais *').selectOption({label: 'Frais scolaires mensuels'}); await d.getByLabel('Montant — Primaire').fill('18000');
  await d.getByRole('button', {name: 'Appliquer ce frais'}).click(); await d.getByText(/1 règle\(s\) en attente/).waitFor();
  await d.getByLabel('Frais *').selectOption({label: 'Frais d’inscription'}); await d.getByLabel('Montant — Toute l’école').fill('10000');
  await d.getByRole('button', {name: 'Appliquer ce frais'}).click(); await d.getByText(/2 règle\(s\) en attente · 2 frais/).waitFor();
  await d.getByLabel('Frais *').selectOption({label: 'Frais scolaires mensuels'});
  if (await d.getByLabel('Montant — Primaire').inputValue() !== '18000') throw new Error('le montant appliqué n’est pas repris en revenant sur le frais');
  await d.getByRole('tab', {name: 'Frais réglementaires'}).click(); await d.getByRole('button', {name: 'Appliquer les frais réglementaires'}).click();
  await d.getByRole('button', {name: /^Tout enregistrer \(\d+\)$/}).click(); await d.waitFor({state: 'detached', timeout: 90000});
  await toast(/règle\(s\) tarifaire\(s\) enregistrée\(s\)/); });
await step('41 tarifs : quitter avec des règles en attente demande confirmation', async () => {
  await p.getByRole('button', {name: 'Assistant tarifaire'}).click(); const d = p.getByRole('dialog', {name: /Assistant tarifaire/});
  await d.getByLabel('Frais *').selectOption({label: 'Frais d’inscription'}); await d.getByLabel('Montant — Toute l’école').fill('11000');
  await d.getByRole('button', {name: 'Appliquer ce frais'}).click(); await d.getByRole('button', {name: 'Quitter'}).click();
  await p.getByText('Quitter sans enregistrer ?').waitFor(); await p.getByRole('button', {name: 'Quitter sans enregistrer'}).click(); await d.waitFor({state: 'detached'}); });

await step('50 communication : l’administrateur comprend ce qu’il pilote', async () => { await module('Communication');
  for (const t of ['Canaux de l’école', 'Notifications sur cet appareil', 'Qui peut écrire aux familles ?']) await p.getByRole('heading', {name: t}).waitFor();
  await p.locator('.commTile', {hasText: 'Peuvent écrire aux familles'}).click(); await p.getByRole('heading', {name: 'Qui peut écrire aux familles ?'}).waitFor(); });
await step('51 communication : interrupteurs et enregistrement', async () => {
  const sms = p.locator('.commToggle', {hasText: 'SMS'}).first();
  const master = p.locator('.commToggle.master input'); if (!await master.isChecked()) await master.check();
  await sms.locator('input').check();
  if (await p.getByRole('button', {name: 'Réglages à jour'}).isVisible()) await p.locator('.commToggle', {hasText: 'E-mail'}).locator('input').click();   // replayable: make one change
  await p.getByRole('button', {name: 'Enregistrer les réglages'}).click(); await toast('Réglages de communication enregistrés');
  await p.getByRole('button', {name: 'Réglages à jour'}).waitFor(); });

await step('60 synchronisation : cartes cliquables, appareil autorisé', async () => { await module('Synchronisation');
  await p.getByRole('heading', {name: 'Synchronisation & appareils'}).waitFor(); await p.locator('.syncKpi', {hasText: 'Appareils autorisés'}).click();
  await p.getByRole('button', {name: 'Autoriser cet appareil'}).click(); await toast('Cet appareil est maintenant autorisé'); await p.locator('.deviceCard').first().waitFor(); });

await step('70 documents : une carte du catalogue ouvre ses documents', async () => { await module('Documents');
  await p.getByRole('tab', {name: 'Catalogue'}).click(); await p.locator('.docCard.clickable').first().click();
  await p.getByText(/de ce type/).first().waitFor(); });

await step('80 accès & rôles : une carte chiffrée ouvre ce qu’elle compte', async () => { await module('Accès & rôles');
  await p.locator('.personMetric.clickable', {hasText: 'Rôles'}).click(); await p.getByRole('tab', {name: /Rôles/, selected: true}).waitFor(); });

await step('85 accès & rôles : ajouter un membre avec le formulaire premium', async () => {
  await p.getByRole('button', {name: 'Ajouter un membre'}).click(); const d = p.getByRole('dialog', {name: 'Ajouter un membre'});
  await d.getByLabel('Nom complet *').fill(`Membre Finition ${RUN}`); await d.getByLabel('Adresse e-mail *').fill(`finition-${RUN.toLowerCase()}@example.test`);
  await d.getByLabel('Rechercher un rôle').fill('secr'); await d.getByRole('radio', {name: /Secrétariat/}).click();
  await d.getByRole('radio', {name: /Mot de passe provisoire/}).click(); await d.getByRole('button', {name: 'Remplacement'}).click();
  await d.getByText(/Membre Finition .* · Secrétariat · mot de passe provisoire/).waitFor();
  await d.getByRole('button', {name: 'Ajouter le membre'}).click();
  await p.getByText('Mot de passe provisoire — il ne sera plus jamais affiché :').waitFor({timeout: 20000});
  await p.getByLabel('J’ai noté ou transmis ce mot de passe').check(); await p.getByRole('button', {name: 'Terminer'}).click();
  await p.getByText(`Membre Finition ${RUN}`).first().waitFor({timeout: 15000}); });

console.log(`\n${failures} échec(s) · erreurs HTTP : ${http.filter(x => !x.includes('/auth/') && !x.includes('/branding/logo')).join(', ') || 'aucune'}`);
await b.close(); process.exit(failures ? 1 : 0);
