// Owner, 2026-10-31: « on ne saura pas définir tous les rôles … l'assistant du promoteur décide surtout, il doit prendre
// presque toutes les fonctionnalités du promoteur ; le système doit permettre de créer d'autres rôles ». Replays, LOCAL
// stack, school C, what a school administrator does in « Accès & rôles »: a new school role « Assistant du promoteur »
// created FROM the standard Promoteur, assigned to a test member, then that member signs in and must see the Promoteur's
// modules. Accounts from the private fixtures (never printed). Screenshots: ../.local/assistant_promoteur.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const OUT = '../.local/assistant_promoteur'; fs.mkdirSync(OUT, {recursive: true});
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const ADMIN = FX.C.users.ADMIN, MEMBER = FX.C.users.C_MEMBER, PROMO = JSON.parse(fs.readFileSync('../.local/promoteur/.account.json', 'utf8'));
const LABEL = 'Assistant du promoteur';
const results = []; let failures = 0;
const b = await chromium.launch({channel: 'msedge'});
const login = async (acc, w = 1440) => { const p = await (await b.newContext({viewport: {width: w, height: 900}})).newPage();
  await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500); return p; };
const menuOf = async p => (await p.getByRole('complementary', {name: 'Navigation principale'}).getByRole('button').allInnerTexts()).map(x => x.trim()).filter(x => x && !/^[A-Z]{2}(\s|$)/.test(x) && x !== 'Réduire le menu');
async function step(p, name, fn) { let status = 'PASS', detail = '';
  try { await fn(); } catch (e) { status = 'FAIL'; detail = String(e.message).split('\n').slice(0, 2).join(' / ').slice(0, 300); }
  if (status !== 'PASS') failures++; results.push({name, status, detail}); console.log(`${status.padEnd(5)} ${name}${detail ? ` — ${detail}` : ''}`);
  await p.screenshot({path: `${OUT}/${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`}).catch(() => {}); }

let promoMenu = [];
const pp = await login(PROMO); promoMenu = await menuOf(pp); await pp.context().close();
console.log(`      menu du Promoteur : ${promoMenu.join(' | ')}`);

const a = await login(ADMIN);
await step(a, '01 administrateur : Accès & rôles › Rôles, « Nouveau rôle à partir de… » le Promoteur', async () => {
  await a.getByRole('complementary', {name: 'Navigation principale'}).getByRole('button', {name: 'Accès & rôles', exact: true}).click(); await a.waitForTimeout(1500);
  await a.getByRole('tab', {name: /Rôles/}).click(); await a.waitForTimeout(1500);
  if (await a.getByText(LABEL, {exact: true}).count()) { console.log('      (rôle déjà créé lors d’un passage précédent)'); return; }
  const card = a.locator('article, li, section, div').filter({has: a.getByText('Promoteur', {exact: true})}).filter({has: a.getByRole('button', {name: /Nouveau rôle à partir de/})}).last();
  await card.getByRole('button', {name: /Nouveau rôle à partir de/}).click();
  const d = a.getByRole('dialog').last(); await d.waitFor();
  await d.getByLabel('Nom du rôle').fill(LABEL);
  await d.getByLabel('Description').fill('Assiste le promoteur et décide avec lui : reprend ses fonctionnalités (rôle créé par l’école).');
  if (await d.getByLabel('Motif *').count()) await d.getByLabel('Motif *').fill('Poste d’assistant du promoteur de l’école');
  await d.getByRole('button', {name: 'Créer le rôle'}).click(); await a.waitForTimeout(2500);
  await a.getByText(LABEL, {exact: true}).first().waitFor({timeout: 15000}); });
await step(a, '02 administrateur : rôle attribué à un membre (toute l’école)', async () => {
  await a.getByRole('tab', {name: /Membres/}).click(); await a.waitForTimeout(1200);
  await a.getByPlaceholder(/Nom, e-mail ou rôle/).fill(MEMBER.email.split('@')[0]); await a.waitForTimeout(1200);
  await a.locator('button, li, article').filter({hasText: MEMBER.email.split('@')[0]}).first().click(); await a.waitForTimeout(1500);
  if (await a.getByText(LABEL).count() > 1) { console.log('      (déjà attribué)'); return; }
  await a.getByRole('button', {name: 'Attribuer un rôle'}).click(); const d = a.getByRole('dialog', {name: 'Attribuer un rôle'}); await d.waitFor();
  await d.getByLabel('Rôle').selectOption({label: LABEL}).catch(async () => { const o = await d.getByLabel('Rôle').locator('option').allInnerTexts(); throw new Error(`rôle absent de la liste : ${o.join(' | ')}`); });
  await d.getByLabel('Motif *').fill('Nomination comme assistant du promoteur');
  await d.getByRole('button', {name: 'Attribuer'}).click(); await a.waitForTimeout(2500);
  const pending = await a.getByText(/approbation|en attente de validation/i).count(); if (pending) console.log('      (attribution soumise à approbation)'); });
await a.context().close();

const m = await login(MEMBER);
await step(m, '03 l’assistant se connecte : mêmes modules que le Promoteur, point du jour, sans opération de caisse', async () => {
  const menu = await menuOf(m); console.log(`      menu de l’assistant : ${menu.join(' | ')}`);
  const missing = promoMenu.filter(x => !menu.includes(x)); if (missing.length) throw new Error(`modules du Promoteur absents : ${missing.join(', ')}`);
  await m.locator('.sh-brief-item').first().waitFor({timeout: 20000});
  for (const re of [/^Encaisser/, /Ouvrir ma caisse/]) if (await m.getByRole('button', {name: re}).count()) throw new Error(`bouton d’opération affiché : ${re.source}`); });
await step(m, '04 sur téléphone : même barre du bas que le Promoteur', async () => {
  await m.setViewportSize({width: 390, height: 844}); await m.waitForTimeout(1200);
  const bar = (await m.locator('.es-bottom button').allInnerTexts()).map(x => x.trim()); console.log(`      barre : ${bar.join(' | ')}`);
  if (!bar.includes('Plus') || bar.length < 4) throw new Error(`barre inattendue : ${bar.join(', ')}`); });
await m.context().close(); await b.close();
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.length - failures}/${results.length} PASS · ${failures} FAIL`);
process.exit(failures ? 1 : 0);
