// Local screenshot helper (local stack + local test accounts only): node browser-tests/local_shot.mjs <account> <WxH> <out.png> [module label]
import {chromium} from '@playwright/test';
import fs from 'node:fs';

const [f = 'gestionnaire', size = '1280x900', out = '../.local/shot.png', label = ''] = process.argv.slice(2);
const [W, H] = size.split('x').map(Number);
const acc = JSON.parse(fs.readFileSync(`../.local/${f}/.account.json`, 'utf8'));
const b = await chromium.launch({channel: 'msedge'});
const ctx = await b.newContext({viewport: {width: W, height: H}, isMobile: W < 600, hasTouch: W < 600, deviceScaleFactor: 1});
const p = await ctx.newPage();
await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
await p.getByRole('button', {name: 'Se connecter'}).click();
await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(Number(process.env.WAIT || 12000));
if (label) {
  const allBtn = p.getByRole('button', {name: 'Tous les modules'}).locator('visible=true').first();
  if (await allBtn.isVisible().catch(() => false)) { await allBtn.click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: label, exact: true}).click(); }
  else await p.locator('.es-nav button').filter({hasText: label}).first().click();
  await p.mouse.move(W - 4, H - 4); await p.waitForTimeout(3000);
}
for (const step of (process.env.CLICKS || '').split('|').filter(Boolean)) { await p.getByRole(step.startsWith('tab:') ? 'tab' : 'button', {name: step.replace(/^tab:/, '')}).first().click(); await p.waitForTimeout(2000); }
if (process.env.HOVER) { await p.locator('.ex-tile', {hasText: process.env.HOVER}).first().hover(); await p.waitForTimeout(Number(process.env.HOVER_WAIT || 1500)); }
await p.screenshot({path: out, fullPage: process.env.FULL !== '0'});
await b.close();
console.log(out);
