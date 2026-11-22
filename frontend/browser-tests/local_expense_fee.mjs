// Local end-to-end (local stack + local test cashier only): record a NEW expense through the form, choosing
// « Pris dans les frais de : Frais de l’État » (owner, 2026-11-22). Opens the cash desk if it is closed.
//     cd frontend && node browser-tests/local_expense_fee.mjs [WxH]
import {chromium} from '@playwright/test';
import fs from 'node:fs';

const [W, H] = (process.argv[2] || '390x844').split('x').map(Number);
const acc = JSON.parse(fs.readFileSync('../.local/caissier/.account.json', 'utf8'));
const OUT = '../.local/report_audit'; fs.mkdirSync(OUT, {recursive: true});
const b = await chromium.launch({channel: 'msedge'});
const ctx = await b.newContext({viewport: {width: W, height: H}, isMobile: W < 600, hasTouch: W < 600});
const p = await ctx.newPage();
await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
await p.getByRole('button', {name: 'Se connecter'}).click();
await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(8000);
const allBtn = p.getByRole('button', {name: 'Tous les modules'}).locator('visible=true').first();
if (await allBtn.isVisible().catch(() => false)) { await allBtn.click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: /^(Finances|Centre financier)$/}).first().click(); }
else await p.locator('.es-nav button').filter({hasText: /Finances|Centre financier/}).first().click();
await p.waitForTimeout(4000);
const cashTab = p.locator('button, [role=tab]').filter({hasText: /^Caisse$/}).first();
if (await cashTab.isVisible().catch(() => false)) { await cashTab.click(); await p.waitForTimeout(4000); }
const open = p.getByRole('button', {name: 'Ouvrir ma caisse'}).first();
if (await open.isVisible().catch(() => false)) {
  await open.click(); await p.waitForTimeout(800);
  await p.getByRole('dialog').getByRole('button', {name: 'Ouvrir ma caisse'}).click(); await p.waitForTimeout(3000);
  console.log('caisse ouverte');
}
await p.screenshot({path: `${OUT}/expense_before_${W}.png`, fullPage: true});
await p.getByRole('button', {name: 'Nouvelle dépense'}).first().click(); await p.waitForTimeout(1200);
const form = p.locator('form.cashExpenseBox');
await form.getByLabel('Catégorie').fill('Essai frais de l’État');
await form.getByLabel('Montant').fill('2500');
const select = form.getByLabel('Pris dans les frais de');
const options = await select.locator('option').allInnerTexts();
console.log('choix proposés :', options.join(' | '));
await select.selectOption({label: 'Frais de l’État'});
await form.getByLabel('Motif').fill('Essai : dépense prise dans les frais de l’État');
await p.screenshot({path: `${OUT}/expense_form_${W}.png`});
await form.getByRole('button', {name: 'Enregistrer la dépense'}).click(); await p.waitForTimeout(800);
const confirmText = await p.locator('.eduDialog').innerText().catch(() => '');
console.log('confirmation :', confirmText.replace(/\s+/g, ' ').slice(0, 160));
await p.locator('.eduDialog').getByRole('button', {name: 'Enregistrer'}).click(); await p.waitForTimeout(2500);
const toast = await p.locator('[data-sonner-toast]').first().innerText().catch(() => '');
console.log('message :', toast.replace(/\s+/g, ' '));
await p.screenshot({path: `${OUT}/expense_done_${W}.png`});
await b.close();
