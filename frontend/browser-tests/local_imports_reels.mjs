// Real imports of every official template (owner request 2026-10-25: « essaie de faire les vrais imports de tous les
// modèles prévus »). LOCAL stack, school C. For each kind: download the template FROM THE SCREEN, fill it (python, values
// read from the template's own reference sheet), upload it: a file with a wrong row must be blocked, the corrected file
// must import, and the imported data must be visible. Pupils and financial history: cashier; staff: school administrator.
// Accounts are read from local files and never printed.
import {chromium} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
const cashier = JSON.parse(fs.readFileSync('../.local/caissier/.account.json', 'utf8'));
// Staff import belongs to the Gestionnaire (owner decision 2026-10-24), account made by local_role_prepare.mjs.
const admin = JSON.parse(fs.readFileSync('../.local/gestionnaire/.account.json', 'utf8'));
const OUT = '../.local/imports'; fs.mkdirSync(OUT, {recursive: true});
const RUN = Date.now().toString(36).slice(-4).toUpperCase();
const PY = '../.venv/Scripts/python.exe';
let failures = 0; const http = [];
const b = await chromium.launch({channel: 'msedge'});

async function session(acc) {
  const ctx = await b.newContext({viewport: {width: 1440, height: 900}, acceptDownloads: true}); const p = await ctx.newPage();
  p.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/') && r.status() >= 500) http.push(`${r.request().method()} ${u.pathname} → ${r.status()}`); });
  await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 30000}); return {ctx, p};
}
async function step(p, name, fn) {
  let status = 'OK', detail = '';
  try { await fn(); if (await p.getByText('Une difficulté est survenue').count()) status = 'MESSAGE VAGUE'; }
  catch (e) { status = 'ÉCHEC'; detail = String(e.message).split('\n').slice(0, 2).join(' / ').slice(0, 300); }
  if (status !== 'OK') failures++;
  console.log(`${status.padEnd(14)} ${name}${detail ? ` — ${detail}` : ''}`);
  await p.screenshot({path: `${OUT}/${name.replace(/[^a-z0-9]+/gi, '_').toLowerCase()}.png`});
}
const fill = (kind, tpl, out, bad) => execFileSync(PY, ['-I', 'browser-tests/fill_import_template.py', kind, tpl, out, RUN, ...(bad ? ['bad'] : [])], {encoding: 'utf8'}).trim();
async function download(p, button) { const dl = p.waitForEvent('download', {timeout: 20000}); await button.click(); const d = await dl; const path = `${OUT}/${d.suggestedFilename()}`; await d.saveAs(path); return path; }
const nav = p => p.getByRole('complementary', {name: 'Navigation principale'});

// Guided stepper (pupils, staff): blocked file, then the corrected file imports.
async function stepper(p, kind, label, verify) {
  let tpl = '';
  await step(p, `${label} 1 modèle téléchargé depuis l’écran`, async () => { tpl = await download(p, p.locator('.ki-head').getByRole('button', {name: 'Modèle Excel'})); console.log('               ', fill(kind, tpl, `${OUT}/${kind}_bad.xlsx`, true)); });
  await step(p, `${label} 2 une ligne fausse bloque le lot`, async () => {
    await p.locator('.ki-drop input[type=file]').setInputFiles(`${OUT}/${kind}_bad.xlsx`); await p.getByRole('button', {name: 'Analyser le fichier'}).click();
    await p.getByText('Import bloqué').waitFor({timeout: 30000});
    if (await p.getByRole('button', {name: 'Importer définitivement'}).isEnabled()) throw new Error('import possible malgré une ligne en erreur'); });
  await step(p, `${label} 3 le fichier corrigé s’importe`, async () => {
    console.log('               ', fill(kind, tpl, `${OUT}/${kind}_ok.xlsx`, false));
    await p.locator('.ki-drop input[type=file]').setInputFiles(`${OUT}/${kind}_ok.xlsx`); await p.getByRole('button', {name: /Analyser/}).click();
    await p.getByText(/Prêt à importer/).waitFor({timeout: 30000});
    const accept = p.locator('.ki-accept input'); if (await accept.count()) await accept.check();
    await p.getByRole('button', {name: 'Importer définitivement'}).click(); await p.locator('.ki-done').waitFor({timeout: 30000}); });
  await step(p, `${label} 4 données importées visibles`, verify);
}

{ const {ctx, p} = await session(cashier);
  await nav(p).getByRole('button', {name: 'Élèves & inscriptions', exact: true}).click(); await p.getByRole('tab', {name: 'Import'}).click(); await p.waitForTimeout(1000);
  await stepper(p, 'STUDENTS', 'Élèves', async () => { await p.getByRole('tab', {name: 'Annuaire élèves'}).click();
    await p.locator('.kp-directory').getByPlaceholder(/Matricule, nom/).fill(`IMPORT${RUN}`); await p.waitForTimeout(1500);
    const n = await p.locator('button.kp-row', {hasText: `IMPORT${RUN}`}).count(); if (n !== 3) throw new Error(`${n} élève(s) importé(s) trouvé(s) au lieu de 3`); });

  await nav(p).getByRole('button', {name: 'Centre financier', exact: true}).click(); await p.locator('.financeTabs button', {hasText: 'Import historique'}).click(); await p.waitForTimeout(1000);
  let tpl = '';
  await step(p, 'Historique financier 1 modèle téléchargé depuis l’écran', async () => { tpl = await download(p, p.getByRole('button', {name: 'Télécharger le modèle'})); console.log('               ', fill('FINANCE_HISTORY', tpl, `${OUT}/FIN_bad.xlsx`, true)); });
  await step(p, 'Historique financier 2 une ligne fausse bloque', async () => {
    await p.getByLabel('Fichier Excel à importer').setInputFiles(`${OUT}/FIN_bad.xlsx`); await p.getByRole('button', {name: 'Analyser le fichier'}).click(); await p.waitForTimeout(3000);
    const go = p.getByRole('button', {name: /Reprendre/}); if (await go.count() && await go.isEnabled()) throw new Error('reprise possible malgré une ligne en erreur'); });
  await step(p, 'Historique financier 3 le fichier corrigé est repris', async () => {
    console.log('               ', fill('FINANCE_HISTORY', tpl, `${OUT}/FIN_ok.xlsx`, false));
    await p.getByLabel('Fichier Excel à importer').setInputFiles(`${OUT}/FIN_ok.xlsx`); await p.getByRole('button', {name: 'Analyser le fichier'}).click(); await p.waitForTimeout(3000);
    const go = p.getByRole('button', {name: /Reprendre/}); await go.waitFor({timeout: 15000}); if (!(await go.isEnabled())) throw new Error(`reprise refusée : ${(await p.locator('.financePage').innerText()).match(/[^\n]*(erreur|Erreur)[^\n]*/)?.[0] ?? ''}`);
    await go.click(); await p.getByText(/Reprise terminée|terminée/).first().waitFor({timeout: 30000}); });
  await ctx.close(); }

{ const {ctx, p} = await session(admin); await p.waitForTimeout(2000); await p.screenshot({path: `${OUT}/admin_accueil.png`});
  await nav(p).getByRole('button', {name: 'Personnel', exact: true}).click(); await p.waitForTimeout(1200);
  await p.getByRole('button', {name: 'Import', exact: true}).click(); await p.waitForTimeout(1000);
  await stepper(p, 'STAFF', 'Personnel', async () => {
    if (await p.getByText('Aucun lot d’import').count()) throw new Error('historique des imports non rafraîchi après l’import');
    await p.getByRole('button', {name: /^Annuaire/}).first().click(); await p.waitForTimeout(1200);
    const search = p.getByPlaceholder(/Rechercher|Nom|matricule/i).first(); await search.fill(`IMP${RUN}`); await p.waitForTimeout(1500);
    const n = await p.getByText(new RegExp(`IMP${RUN}`)).count(); if (n < 2) throw new Error(`${n} agent(s) importé(s) visible(s) au lieu de 2`); });
  await ctx.close(); }

console.log(`\n${failures} échec(s) · erreurs serveur : ${http.join(', ') || 'aucune'}`);
await b.close(); process.exit(failures ? 1 : 0);
