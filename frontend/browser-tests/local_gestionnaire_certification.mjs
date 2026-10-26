// GESTIONNAIRE certification (2026-10-26) — LOCAL stack, school C, standard Gestionnaire account created by
// local_role_prepare.mjs (../.local/gestionnaire/.account.json, never printed). Real business journey + required
// screenshots (../.local/gestionnaire/cert) + responsive checks (320 → 1440 px) + FORBIDDEN calls sent to the server with
// the Gestionnaire's own session: collecting money, opening a cash desk, enrolling, changing settings or members must be
// refused (403). Owner decision 2026-10-26: the Gestionnaire manages personnel (create / update / exit / assignments).
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const acc = JSON.parse(fs.readFileSync('../.local/gestionnaire/.account.json', 'utf8'));
const OUT = '../.local/gestionnaire/cert'; fs.mkdirSync(OUT, {recursive: true});
const http = []; let failures = 0; let bearer = '';
const results = [];
const b = await chromium.launch({channel: 'msedge'});
const ctx = await b.newContext({viewport: {width: 1440, height: 900}, acceptDownloads: true}); const p = await ctx.newPage();
ctx.on('page', np => { if (np !== p) setTimeout(() => np.close().catch(() => {}), 1500); });
p.on('request', r => { const h = r.headers().authorization; if (h && h.startsWith('Bearer ') && r.url().includes('/api/v1/')) bearer = h; });
p.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/') && r.status() >= 400 && !u.pathname.includes('/auth/') && !u.pathname.includes('branding/logo')) http.push(`${r.request().method()} ${u.pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, ':id')} → ${r.status()}`); });
p.on('pageerror', e => http.push(`JS ${String(e.message).slice(0, 140)}`));
async function step(name, fn, shot) {
  const before = http.length; let status = 'PASS', detail = '';
  try { await fn(); await p.waitForTimeout(400);
    if (await p.getByText('Une difficulté est survenue').count()) { status = 'FAIL'; detail = 'message vague affiché'; }
    // Owner rule: the user reads FC / USD, never the internal code CDF (checked on every screen).
    else { const seen = await p.evaluate(() => (document.querySelector('main, .es-main') || document.body).innerText.match(/CDF/g)); if (seen) { status = 'FAIL'; detail = `« CDF » affiché : ${seen.slice(0, 3).join(' | ')}`; } }
  } catch (e) { status = 'FAIL'; detail = String(e.message).split('\n').slice(0, 2).join(' / ').slice(0, 300); }
  const n = http.slice(before); if (n.length && status === 'PASS') { status = 'FAIL'; detail = `refus serveur inattendu : ${n.join(', ')}`; }
  if (status !== 'PASS') failures++;
  results.push({name, status, detail}); console.log(`${status.padEnd(5)} ${name}${detail ? ` — ${detail}` : ''}`);
  await p.screenshot({path: `${OUT}/${shot ?? name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`, fullPage: false});
}
const nav = () => p.getByRole('complementary', {name: 'Navigation principale'});
const module = async m => { await nav().getByRole('button', {name: m, exact: true}).click(); await p.waitForTimeout(1300); };
const finTab = async t => { await p.locator('.financeTabs button').filter({hasText: new RegExp(`^${t}$`)}).first().click(); await p.waitForTimeout(1200); };
const noText = async (t, why) => { if (await p.getByText(t, {exact: true}).count()) throw new Error(`${why} (« ${t} » affiché)`); };
const overflow = () => p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

await step('01 connexion gestionnaire', async () => { await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500); });
await step('02 accueil de pilotage (ordinateur)', async () => {
  await p.getByText(/pilotage de l’établissement/).first().waitFor({timeout: 15000});
  for (const t of ['Situation des caisses', 'Décisions financières actives', 'Rapports officiels récents']) await p.getByText(t, {exact: true}).first().waitFor({timeout: 15000});
  await p.getByRole('button', {name: 'Superviser les caisses'}).first().waitFor();
  await noText('Mise en service de l’établissement', 'bloc d’administration affiché au gestionnaire');
  if (await p.getByRole('button', {name: 'Nouvel encaissement'}).count()) throw new Error('raccourci d’encaissement affiché au gestionnaire'); }, 'gest_01_tableau_de_bord_ordinateur');
await step('03 menu : modules du gestionnaire', async () => {
  for (const m of ['Accueil', 'Personnel', 'Effectifs & dépôts', 'Centre financier', 'Documents']) await nav().getByRole('button', {name: m, exact: true}).waitFor();
  const items = (await nav().locator('button[aria-label]').evaluateAll(es => es.map(e => e.getAttribute('aria-label')))).filter(Boolean);
  console.log('      menu :', items.join(' | ')); });

await step('10 supervision des caisses', async () => { await p.getByRole('button', {name: 'Superviser les caisses'}).first().click(); await p.waitForTimeout(1500);
  await p.getByText('Vue de supervision').first().waitFor({timeout: 15000});
  if (await p.getByRole('button', {name: 'Ouvrir ma caisse'}).count()) throw new Error('le gestionnaire peut ouvrir une caisse');
  await p.getByText('Situation globale des caisses').first().waitFor({timeout: 15000});
  await p.getByText(/tous les caissiers/).first().waitFor({timeout: 15000});
  const body = await p.locator('.financePage').innerText(); if (/\bCDF\b/.test(body)) throw new Error('« CDF » affiché à l’utilisateur au lieu de « FC »'); }, 'gest_03_supervision_caisses');
await step('11 caisse passée : journal et export', async () => {
  await p.getByRole('button', {name: 'Ce mois'}).click(); await p.waitForTimeout(1200);
  const row = p.locator('button.cd-sess').first(); if (!(await row.count())) throw new Error('aucune caisse de caissier visible ce mois');
  await row.click(); const d = p.getByRole('dialog', {name: /Caisse du/}); await d.waitFor();
  const dl = p.waitForEvent('download', {timeout: 15000}).catch(() => null); await d.getByRole('button', {name: 'Excel'}).click(); if (!(await dl)) throw new Error('export Excel non reçu');
  // PDF opens in the in-app viewer (main 2026-10-26): visible, then closed with Échap (viewer, then the session window).
  await d.getByRole('button', {name: 'Journal PDF'}).click(); await p.getByText('Aperçu dans EduSync').waitFor({timeout: 15000});
  await p.keyboard.press('Escape'); await p.waitForTimeout(400); if (await d.isVisible().catch(() => false)) await p.keyboard.press('Escape'); await p.waitForTimeout(400); });
await step('12 clôture de la journée de l’école disponible', async () => { await p.getByText('Supervision des caisses').first().waitFor();
  await p.getByRole('button', {name: /Clôturer la journée|Journée clôturée|Rouvrir la journée/}).first().waitFor({timeout: 10000}); });

await step('20 centre financier : onglets de supervision, sans encaissement', async () => { await module('Centre financier');
  const tabs = (await p.locator('.financeTabs button').allInnerTexts()).map(t => t.trim()); console.log('      onglets :', tabs.join(' | '));
  if (tabs.includes('Encaissement')) throw new Error('onglet Encaissement visible pour le gestionnaire');
  for (const t of ['Recouvrement', 'Caisse', 'Suivi financier', 'Rapports', 'Décisions financières']) if (!tabs.includes(t)) throw new Error(`onglet ${t} absent`); }, 'gest_06_centre_financier');
await step('21 rapports : périodique, analyses, rapports générés', async () => { await finTab('Rapports');
  await p.getByRole('tab', {name: 'Rapports périodiques'}).click(); await p.getByRole('button', {name: /^(Aperçu|Afficher)$/}).click(); await p.waitForTimeout(2500);
  await p.getByRole('tab', {name: 'Analyses de gestion'}).click(); await p.getByText('Analyse par caissier').waitFor({timeout: 15000});
  await p.getByRole('tab', {name: 'Rapports générés'}).click(); await p.waitForTimeout(1200); }, 'gest_07_rapports');
await step('22 décisions financières', async () => { await finTab('Décisions financières'); await p.waitForTimeout(1500); await p.locator('.financePage').getByText(/Décision|exonération|Aucune/i).first().waitFor({timeout: 15000}); });
await step('23 recouvrement et suivi financier', async () => { await finTab('Recouvrement'); await p.locator('.recoveryTable, .recoveryPage').first().waitFor({timeout: 15000});
  await finTab('Suivi financier'); await p.locator('.ff-filters').getByLabel('Classe').selectOption({index: 1}); await p.locator('.ff-kpis').waitFor({timeout: 15000}); });

await step('30 personnel : synthèse, annuaire, gestion autorisée', async () => { await module('Personnel');
  await p.getByText('Agents actifs').first().waitFor({timeout: 15000});
  await p.getByRole('button', {name: /Nouvel agent/}).first().waitFor({timeout: 10000});                                  // décision 2026-10-26
  await p.getByRole('button', {name: /^Annuaire/}).first().click(); await p.waitForTimeout(1500); }, 'gest_04_personnel');
await step('40 effectifs : indicateurs, mouvements, export', async () => { await module('Effectifs & dépôts');
  await p.locator('.fx2Kpis').waitFor({timeout: 15000}); await p.getByRole('tab', {name: 'Mouvements'}).click(); await p.waitForTimeout(1200);
  await p.getByRole('tab', {name: 'Par classe'}).click(); await p.waitForTimeout(1200); }, 'gest_05_effectifs');
await step('50 documents : historique et visionneuse', async () => { await module('Documents');
  const open = p.getByRole('button', {name: 'Ouvrir'}).first(); if (await open.count()) { await open.click(); await p.waitForTimeout(2500); const v = p.locator('.docViewer'); if (await v.count()) await v.getByRole('button', {name: /Retour/}).click(); } });
await step('60 intendance : stocks consultables', async () => { const it = nav().getByRole('button', {name: 'Intendance', exact: true}); if (!(await it.count())) throw new Error('module Intendance absent');
  await it.click(); await p.waitForTimeout(2000); });

// FORBIDDEN calls with the Gestionnaire's own session — the server must refuse.
await step('70 opérations interdites refusées par le serveur', async () => {
  if (!bearer) throw new Error('session non capturée');
  const z = '00000000-0000-0000-0000-000000000000';                       // well-formed bodies: the RIGHT is what is refused
  const forbid = [['POST', '/api/v1/finance/cash/open', {opening_cdf: '0', opening_usd: '0'}],
    ['POST', '/api/v1/finance/checkout/collect', {enrollment_id: z, charge_ids: [z], amount: '1', currency: 'CDF'}],
    ['POST', '/api/v1/schooling/enrollments/family', {children: [{last_name: 'TEST', middle_name: 'TEST', first_name: 'Test', class_id: z, gender: 'M'}]}],
    ['PATCH', '/api/v1/settings/identity', {name: 'Nom modifié'}]];
  const bad = [];
  for (const [method, path, body] of forbid) {
    const r = await p.request.fetch(`http://localhost:5180${path}`, {method, headers: {Authorization: bearer, 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID(), 'If-Match': '1'}, data: body});
    console.log(`      ${method} ${path} → ${r.status()}`); if (r.status() !== 403) bad.push(`${path} → ${r.status()}`);
  }
  http.length = http.length;                                                                       // refusals are expected here
  if (bad.length) throw new Error(`non refusé : ${bad.join(', ')}`); });

// Multi-tenant isolation: a real pupil of ANOTHER school (A), read with the Gestionnaire session of school C.
await step('75 isolation entre écoles : les données de l’école A sont introuvables depuis l’école C', async () => {
  const fx = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8')).A.users.ADMIN;
  const c2 = await b.newContext(); const q = await c2.newPage(); let other = '';
  q.on('request', r => { const h = r.headers().authorization; if (h && h.startsWith('Bearer ') && r.url().includes('/api/v1/')) other = h; });
  await q.goto('http://localhost:5180/'); await q.getByLabel('Adresse e-mail').fill(fx.email); await q.getByLabel('Mot de passe', {exact: true}).fill(fx.password);
  await q.getByRole('button', {name: 'Se connecter'}).click(); await q.locator('.es-shell').waitFor({timeout: 40000}); await q.waitForTimeout(2000);
  const list = await q.request.get('http://localhost:5180/api/v1/schooling/students?limit=1', {headers: {Authorization: other}}); const pupil = (await list.json()).items?.[0]?.id; await c2.close();
  if (!pupil) throw new Error('aucun élève de l’école A pour le contrôle');
  const bad = [];
  for (const path of [`/api/v1/schooling/students/${pupil}`, `/api/v1/finance/reports/students/${pupil}/account`]) {
    const r = await p.request.get(`http://localhost:5180${path}`, {headers: {Authorization: bearer}}); console.log(`      ${path.replace(pupil, ':id-école-A')} → ${r.status()}`);
    if (r.status() < 400) bad.push(`${path} → ${r.status()}`); }
  if (bad.length) throw new Error(`fuite entre écoles : ${bad.join(', ')}`); });
await step('80 responsive 320 → 1440 px (accueil et centre financier)', async () => {
  const issues = [];
  for (const w of [320, 360, 390, 768, 1024, 1440]) { await p.setViewportSize({width: w, height: 840}); await p.waitForTimeout(500);
    for (const [label, go] of [['accueil', async () => { if (w >= 900) await module('Accueil'); else { await p.getByRole('button', {name: 'Tous les modules'}).click().catch(() => {}); await p.locator('button', {hasText: /^Accueil$/}).filter({visible: true}).last().click().catch(() => {}); } }],
      ['finance', async () => { if (w >= 900) await module('Centre financier'); else { await p.getByRole('button', {name: 'Tous les modules'}).click().catch(() => {}); await p.locator('button', {hasText: /^Centre financier$/}).filter({visible: true}).last().click().catch(() => {}); } }]]) {
      await go(); await p.waitForTimeout(1200); const o = await overflow(); if (o > 2) issues.push(`${label} ${w}px +${o}px`);
      if (w === 390 && label === 'accueil') await p.screenshot({path: `${OUT}/gest_02_tableau_de_bord_mobile.png`, fullPage: true}); } }
  await p.setViewportSize({width: 1440, height: 900});
  if (issues.length) throw new Error(`débordement horizontal : ${issues.join(', ')}`); });
await step('90 déconnexion puis reconnexion', async () => {
  await p.locator('.es-account, [aria-label^="Compte"]').first().click(); await p.getByRole('menuitem', {name: /Se déconnecter/}).or(p.getByRole('button', {name: /Se déconnecter/})).first().click();
  await p.waitForTimeout(500); const confirm = p.getByRole('button', {name: 'Se déconnecter', exact: true}).last(); if (await confirm.count()) await confirm.click();     // confirmation « Se déconnecter ? »
  await p.getByLabel('Adresse e-mail').waitFor({timeout: 20000}); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); });

fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.filter(r => r.status === 'PASS').length}/${results.length} PASS · ${failures} FAIL`);
await b.close(); process.exit(failures ? 1 : 0);
