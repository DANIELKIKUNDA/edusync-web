import {chromium} from '@playwright/test';

const base = 'https://staging.myeducsync.com';
const {E2E_SCHOOL_EMAIL: email, E2E_SCHOOL_PASSWORD: password, E2E_EXPECTED_SHA: sha} = process.env;
if (!email || !password || !/^[0-9a-f]{40}$/.test(sha ?? '')) {
  console.error('ÉCHEC — identifiants scolaires ou SHA de staging absents.');
  process.exit(1);
}
const browser = await chromium.launch();
const context = await browser.newContext({serviceWorkers: 'block'});
const page = await context.newPage();
const refresh = '/api/v1/auth/refresh';
const at = (response, path) => new URL(response.url()).origin === base && new URL(response.url()).pathname === path;

async function verifyBuild() {
  const response = await context.request.get(base + '/version.json');
  if (!response.ok() || (await response.json()).build !== sha) throw new Error('SHA staging inattendu');
}
async function personnel(tab) {
  const response = tab.waitForResponse(r => at(r, '/api/v1/personnel') && r.ok());
  await tab.getByRole('button', {name: 'Personnel', exact: true}).click();
  await response;
  await tab.getByRole('heading', {name: 'Personnel · Espace de gestion', exact: true}).waitFor();
}
try {
  await verifyBuild();
  await page.goto(base);
  if (new URL(page.url()).origin !== base) throw new Error('Origine staging inattendue');
  await page.getByLabel('Adresse e-mail').fill(email);
  await page.locator('#lg-pass').fill(password);
  await page.getByRole('button', {name: 'Se connecter', exact: true}).click();
  await personnel(page);
  console.log('PASS — connexion scolaire et réponse authentifiée de Personnel');

  const reopened = await browser.newContext({storageState: await context.storageState(), serviceWorkers: 'block'});
  const tab = await reopened.newPage();
  let refreshCount = 0;
  await tab.route(base + refresh, async route => {
    refreshCount++;
    if (refreshCount === 1) {
      await new Promise(resolve => setTimeout(resolve, 4_000));
      await route.fulfill({status: 503, contentType: 'application/json', body: '{}'});
      return;
    }
    await route.continue();
  });
  const renewed = tab.waitForResponse(r => at(r, refresh) && r.ok());
  await tab.goto(base);
  await renewed;
  if (refreshCount < 2) throw new Error('Nouvel essai automatique absent');
  await personnel(tab);
  console.log('PASS — réouverture avec cookie, réponse lente, reprise automatique après 503 et rechargement de Personnel');
  await verifyBuild();
  const logout = await reopened.request.post(base + '/api/v1/auth/logout', {headers: {Origin: base}});
  if (logout.status() !== 204) throw new Error('Déconnexion scolaire non confirmée');
  const refused = await reopened.request.post(base + refresh, {headers: {Origin: base}});
  if (refused.status() !== 401) throw new Error('Refus après déconnexion absent');
  console.log('PASS — session fermée et renouvellement refusé');
} catch {
  console.error('ÉCHEC — parcours scolaire. Consulter la dernière étape PASS. Aucun détail de compte dans les journaux.');
  process.exitCode = 1;
} finally {
  await browser.close();
}
