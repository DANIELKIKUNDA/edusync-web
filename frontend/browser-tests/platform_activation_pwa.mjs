// Platform member activation from an invitation e-mail, on an Android phone with EduSync installed (fix 2026-10-24).
// LOCAL stack only (real API, real database). Scenarios:
//   A. PWA installed then completely closed → invitation link → PWA opens → password → sign-in (pre-filled e-mail) →
//      6-digit code enrolment → recovery codes → platform dashboard; the member leaves PENDING, a session exists;
//   B. link opened in a browser where EduSync is not installed;
//   C. PWA already open (link delivered as a same-document navigation);
//   D. expired link;  E. link already used;  F. no network, then network back (automatic retry).
// The tokens come from tools/local/platform_invitation_fixture.py and are never printed.
import {chromium, devices} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
const APP = 'http://localhost:5180';
const OUT = '../.local/activation';fs.mkdirSync(OUT, {recursive: true});
const PY = '../.venv/Scripts/python.exe';
const fixture = (...args) => JSON.parse(execFileSync(PY, ['../tools/local/platform_invitation_fixture.py', ...args], {encoding: 'utf8'}).trim().split('\n').pop());
const PASSWORD = `Pwa-${crypto.randomBytes(6).toString('hex')}-Ok`;
const BOOT_LIMIT = 6000;      // the phone must leave the boot screen quickly, whatever happens

function totp(secret) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = '';
  for (const ch of secret.replace(/[\s=]/g, '').toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, '0');
  const key = Buffer.from(bits.match(/.{8}/g).map(b => parseInt(b, 2)));
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto.createHmac('sha1', key).update(counter).digest(); const o = h[h.length - 1] & 15;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1e6)).padStart(6, '0');
}

let failures = 0;
async function scenario(name, fn) {
  try { await fn(); console.log(`OK      ${name}`); }
  catch (e) { failures++; console.log(`ÉCHEC   ${name} — ${String(e.message).split('\n')[0].slice(0, 260)}`); }
}
const browser = await chromium.launch({channel: 'msedge'});
const phone = {...devices['Pixel 7']};
delete phone.defaultBrowserType;
async function installedPwa() {
  // « Installed PWA »: service worker registered and controlling, shell cached, then every page closed.
  const ctx = await browser.newContext({...phone});
  const p = await ctx.newPage();
  await p.goto(APP + '/');
  await p.waitForFunction(async () => !!(await navigator.serviceWorker?.ready), null, {timeout: 30000});
  await p.reload(); await p.waitForFunction(() => !!navigator.serviceWorker.controller, null, {timeout: 30000});
  await p.close();
  return ctx;
}
async function leftBoot(p) {
  const t0 = Date.now();
  await p.waitForFunction(() => !document.getElementById('edusync-boot') || document.getElementById('edusync-boot').classList.contains('out')
    || document.getElementById('edusync-boot').hasAttribute('data-failed'), null, {timeout: 20000});
  const ms = Date.now() - t0;
  if (ms > BOOT_LIMIT) throw new Error(`écran de démarrage resté ${ms} ms`);
  return ms;
}
const card = p => p.getByRole('group', {name: 'Activer votre compte'});

await scenario('A. PWA installée puis fermée → invitation → mot de passe → code à 6 chiffres → tableau de bord', async () => {
  const fx = fixture('create');
  const ctx = await installedPwa();
  const p = await ctx.newPage();
  const logs = []; p.on('console', m => logs.push(m.text()));
  await p.goto(`${APP}/#invitation=${fx.token}`);
  await leftBoot(p);
  if (p.url().includes(fx.token)) throw new Error('le jeton est resté dans l’adresse');
  await card(p).getByText(/Bienvenue Second Manager E2E/).waitFor({timeout: 10000});
  await p.getByLabel('Nouveau mot de passe').fill(PASSWORD); await p.getByLabel('Confirmez le mot de passe').fill(PASSWORD);
  await p.getByRole('button', {name: 'Activer mon compte'}).click();
  await p.getByText(/Compte activé\. Connectez-vous avec ce mot de passe/).waitFor({timeout: 15000});
  if (fixture('status', fx.user_id).status !== 'ACTIVE') throw new Error('le membre est resté en attente après l’activation');
  if (await p.getByLabel('Adresse e-mail').inputValue() !== fx.email) throw new Error('adresse e-mail non préremplie');
  await p.getByLabel('Mot de passe', {exact: true}).fill(PASSWORD); await p.getByRole('button', {name: 'Se connecter'}).click();
  await p.getByRole('heading', {name: 'Activer la validation en deux étapes'}).waitFor({timeout: 20000});
  await p.getByRole('button', {name: /Saisir la clé manuellement/}).click();
  const secret = (await p.getByLabel('Clé de configuration').innerText()).replace(/\s/g, '');
  await p.getByRole('button', {name: 'J’ai ajouté le compte, continuer'}).click();
  await p.getByLabel('Code à 6 chiffres').fill(totp(secret));
  await p.getByRole('heading', {name: 'Conservez vos codes de secours'}).waitFor({timeout: 20000});
  await p.getByLabel('J’ai conservé ces codes en lieu sûr').check();
  await p.getByRole('button', {name: 'Accéder à la plateforme'}).click();
  await p.locator('.es-shell').waitFor({timeout: 30000});
  await p.screenshot({path: `${OUT}/A_tableau_de_bord.png`});
  const st = fixture('status', fx.user_id);
  if (!(st.status === 'ACTIVE' && st.open_sessions >= 1 && st.mfa_factors >= 1)) throw new Error(`état final inattendu ${JSON.stringify(st)}`);
  if (logs.some(l => l.includes(fx.token))) throw new Error('jeton présent dans les journaux de la console');
  await ctx.close();
});

await scenario('B. Lien ouvert dans un navigateur sans EduSync installé', async () => {
  const fx = fixture('create');
  const ctx = await browser.newContext({...phone, serviceWorkers: 'block'}); const p = await ctx.newPage();
  await p.goto(`${APP}/#invitation=${fx.token}`); await leftBoot(p);
  await card(p).getByText(/Bienvenue Second Manager E2E/).waitFor({timeout: 10000});
  await p.screenshot({path: `${OUT}/B_navigateur.png`}); await ctx.close();
});

await scenario('C. PWA déjà ouverte : le lien arrive sans rechargement', async () => {
  const fx = fixture('create');
  const ctx = await installedPwa(); const p = await ctx.newPage();
  await p.goto(APP + '/'); await leftBoot(p); await p.getByLabel('Adresse e-mail').waitFor();
  await p.evaluate(t => { location.hash = '#invitation=' + t; }, fx.token);
  await card(p).getByText(/Bienvenue Second Manager E2E/).waitFor({timeout: 10000});
  if (p.url().includes(fx.token)) throw new Error('le jeton est resté dans l’adresse');
  await p.screenshot({path: `${OUT}/C_pwa_ouverte.png`}); await ctx.close();
});

await scenario('D. Lien expiré : message clair et bouton Réessayer, jamais d’écran bloqué', async () => {
  const fx = fixture('create'); fixture('expire', fx.user_id);
  const ctx = await installedPwa(); const p = await ctx.newPage();
  await p.goto(`${APP}/#invitation=${fx.token}`); await leftBoot(p);
  await card(p).getByText('Lien invalide, expiré ou déjà utilisé. Contactez un Manager Système.').waitFor({timeout: 10000});
  await card(p).getByRole('button', {name: 'Réessayer'}).waitFor();
  await p.screenshot({path: `${OUT}/D_expire.png`}); await ctx.close();
});

await scenario('E. Lien déjà utilisé', async () => {
  const fx = fixture('create');
  const ctx = await installedPwa(); const p = await ctx.newPage();
  await p.goto(`${APP}/#invitation=${fx.token}`); await leftBoot(p);
  await p.getByLabel('Nouveau mot de passe').fill(PASSWORD); await p.getByLabel('Confirmez le mot de passe').fill(PASSWORD);
  await p.getByRole('button', {name: 'Activer mon compte'}).click(); await p.getByText(/Compte activé/).waitFor({timeout: 15000});
  const again = await ctx.newPage(); await again.goto(`${APP}/#invitation=${fx.token}`); await leftBoot(again);
  await card(again).getByText('Lien invalide, expiré ou déjà utilisé. Contactez un Manager Système.').waitFor({timeout: 10000});
  await again.screenshot({path: `${OUT}/E_deja_utilise.png`}); await ctx.close();
});

await scenario('F. Pas de réseau, puis retour du réseau : nouvelle vérification automatique', async () => {
  const fx = fixture('create');
  const ctx = await installedPwa(); await ctx.setOffline(true);
  const p = await ctx.newPage();
  await p.goto(`${APP}/#invitation=${fx.token}`); await leftBoot(p);
  await card(p).getByText(/Le serveur ne répond pas|Activation indisponible/).waitFor({timeout: 15000});
  await card(p).getByRole('button', {name: 'Réessayer'}).waitFor();
  await p.screenshot({path: `${OUT}/F_hors_ligne.png`});
  await ctx.setOffline(false);
  await card(p).getByText(/Bienvenue Second Manager E2E/).waitFor({timeout: 15000});
  await p.screenshot({path: `${OUT}/F_reseau_revenu.png`}); await ctx.close();
});

await scenario('G. Programme impossible à charger : jamais d’écran de démarrage infini, message et Réessayer', async () => {
  const fx = fixture('create');
  const ctx = await browser.newContext({...phone, serviceWorkers: 'block'}); const p = await ctx.newPage();
  await p.route(/\/(assets|src)\/.*\.(js|tsx?)(\?.*)?$/, r => r.abort());
  await p.goto(`${APP}/#invitation=${fx.token}`);
  await p.getByText('EduSync ne parvient pas à démarrer').waitFor({timeout: 20000});
  await p.getByRole('button', {name: 'Réessayer'}).waitFor();
  await p.screenshot({path: `${OUT}/G_secours_demarrage.png`});
  await p.unroute(/\/(assets|src)\/.*\.(js|tsx?)(\?.*)?$/);
  await p.getByRole('button', {name: 'Réessayer'}).click();       // the link is still in the address: it works now
  await card(p).getByText(/Bienvenue Second Manager E2E/).waitFor({timeout: 15000});
  await ctx.close();
});

await browser.close();
console.log(`\n${failures} échec(s)`);
process.exit(failures ? 1 : 0);
