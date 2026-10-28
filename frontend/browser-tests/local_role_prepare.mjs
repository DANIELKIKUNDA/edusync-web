// Role account preparation (2026-10-25), generalising local_caissier_prepare.mjs: the school administrator creates a
// member with the standard role given on the command line through « Ajouter un membre », the member signs in and
// replaces the temporary password. Account kept in ../.local/<folder>/.account.json (local only, never printed).
// Usage: node browser-tests/local_role_prepare.mjs <folder> "<role search>" "<role radio label regexp>" "<full name>"
import {chromium} from '@playwright/test';
import fs from 'node:fs';
import crypto from 'node:crypto';
const [folder = 'gestionnaire', search = 'gestion', radio = 'Gestionnaire', fullName = 'Gestionnaire Certification', sections = ''] = process.argv.slice(2);
// sections (optional, comma separated labels): required by section-bound leadership roles (Préfet, Direction de section).
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8')); const a = FX.C.users.ADMIN;
const OUT = `../.local/${folder}`; fs.mkdirSync(OUT, {recursive: true});
const RUN = Date.now().toString(36).slice(-4); const email = `${folder}-${RUN}@example.test`;
const b = await chromium.launch({channel: 'msedge'});
let p = await (await b.newContext({viewport: {width: 1440, height: 900}})).newPage();
await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(a.email); await p.getByLabel('Mot de passe', {exact: true}).fill(a.password);
await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 30000});
await p.getByRole('complementary', {name: 'Navigation principale'}).getByRole('button', {name: 'Accès & rôles', exact: true}).click();
await p.getByRole('button', {name: 'Ajouter un membre'}).click(); const d = p.getByRole('dialog', {name: 'Ajouter un membre'});
await d.getByLabel('Nom complet *').fill(fullName); await d.getByLabel('Adresse e-mail *').fill(email);
await d.getByLabel('Rechercher un rôle').fill(search); await d.getByRole('radio', {name: new RegExp(radio)}).first().click();
for (const label of sections.split(',').filter(Boolean)) await d.getByRole('group', {name: 'Sections du rôle'}).getByRole('button', {name: label, exact: true}).click();
await d.getByRole('button', {name: 'Ajouter le membre'}).click();
await p.locator('.secretBox code, .am-dialog .error').first().waitFor({timeout: 30000});
if (await p.locator('.am-dialog .error').count()) throw new Error(`ajout refusé : ${await p.locator('.am-dialog .error').innerText()}`);
const code = (await p.locator('.secretBox code').innerText()).trim(); await p.getByLabel('J’ai noté ou transmis ce mot de passe').check(); await p.getByRole('button', {name: 'Terminer'}).click();
await p.context().close();
p = await (await b.newContext({viewport: {width: 1440, height: 900}})).newPage();
await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(email); await p.getByLabel('Mot de passe', {exact: true}).fill(code); await p.getByRole('button', {name: 'Se connecter'}).click();
const pw = `Gs-${crypto.randomBytes(6).toString('hex')}-Ok`;
await p.getByLabel('Nouveau mot de passe').fill(pw); await p.getByLabel('Confirmer le mot de passe').fill(pw); await p.getByRole('button', {name: /Enregistrer|Changer|Valider/}).first().click();
await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2000);
fs.writeFileSync(`${OUT}/.account.json`, JSON.stringify({email, password: pw}));   // local only, never printed
const items = await p.getByRole('complementary', {name: 'Navigation principale'}).getByRole('button').allInnerTexts();
console.log(`compte « ${radio} » créé · menu :`, items.map(x => x.trim()).filter(Boolean).join(' | '));
await b.close();
