import {chromium, request, expect} from '@playwright/test';

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
  // Real staging, real authenticated requests. Only the browser's network is cut;
  // no school record is created or changed, and no manual recovery button is used.
  for(let cycle=0;cycle<3;cycle++){
    await context.setOffline(true);
    await page.getByText('Hors connexion — vous pouvez continuer.',{exact:true}).waitFor();
    await context.setOffline(false);
    await page.getByRole('button',{name:'Accueil',exact:true}).first().click();
    await personnel(page);
    await expect(page.getByText('Impossible de vérifier votre session pour le moment.',{exact:true})).toHaveCount(0);
    await expect(page.getByText('Hors connexion — vous pouvez continuer.',{exact:true})).toHaveCount(0);
  }
  await page.reload();
  await personnel(page);
  console.log('PASS — trois coupures réseau et reprises automatiques, puis rechargement et réponse réelle de Personnel');


  const signedInState = await context.storageState();
  const reopened = await browser.newContext({storageState: signedInState, serviceWorkers: 'block'});
  // This independent cookie jar can deliver a request to the real server without applying
  // its response to the browser under test, simulating a broken return path.
  const detached = await request.newContext({storageState: signedInState});
  try {
    const tab = await reopened.newPage();
    let refreshCount = 0;
    let lostResponseStatus;
    let lostResponseSetCookie;
    await tab.route(base + refresh, async route => {
      refreshCount++;
      if (refreshCount === 1) {
        const response = await detached.post(base + refresh, {headers: {Origin: base}});
        lostResponseStatus = response.status();
        lostResponseSetCookie = response.headersArray().some(h => h.name.toLowerCase() === 'set-cookie');
        await route.abort('connectionreset');
        return;
      }
      await route.continue();
    });
    const renewed = tab.waitForResponse(r => at(r, refresh) && r.ok());
    await tab.goto(base);
    await renewed;
    if (lostResponseStatus !== 200 || lostResponseSetCookie || refreshCount < 2) {
      throw new Error('La reprise après la perte de la réponse ne respecte pas le contrat');
    }
    await personnel(tab);
    console.log('PASS — réponse de renouvellement perdue après traitement serveur et reprise automatique de Personnel');
    await verifyBuild();
    const logout = await reopened.request.post(base + '/api/v1/auth/logout', {headers: {Origin: base}});
    if (logout.status() !== 204) throw new Error('Déconnexion scolaire non confirmée');
    // The detached jar still holds the credential, so a 401 proves server-side revocation.
    const refused = await detached.post(base + refresh, {headers: {Origin: base}});
    if (refused.status() !== 401) throw new Error('Ancien cookie accepté après révocation');
  } finally {
    await detached.dispose();
  }
  console.log('PASS — session fermée et renouvellement refusé');
} catch {
  console.error('ÉCHEC — parcours scolaire. Consulter la dernière étape PASS. Aucun détail de compte dans les journaux.');
  process.exitCode = 1;
} finally {
  await browser.close();
}
