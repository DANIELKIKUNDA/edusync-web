// V1 setup — the 51 official options (owner 2026-11-22), local stack + local test administrator only.
// Paramètres › Structure & classes › Sections & options: screenshot of the option catalogue (general open, technical
// groups folded unless an option is opened) at 390 and 1280, plus measures. Opens nothing.
//     cd frontend && node browser-tests/local_options_catalog.mjs
import {chromium} from '@playwright/test';
import fs from 'node:fs';

const OUT = '../.local/pedagogy'; fs.mkdirSync(OUT, {recursive: true});
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const acc = {email: FX.C.users.ADMIN.email, password: FX.C.users.ADMIN.password};
const b = await chromium.launch({channel: 'msedge'});
const out = {};
try {
  for (const [W, H] of [[390, 844], [1280, 800]]) {
    const phone = W < 600;
    const ctx = await b.newContext({viewport: {width: W, height: H}, isMobile: phone, hasTouch: phone});
    const p = await ctx.newPage();
    await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
    await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500);
    const allBtn = p.getByRole('button', {name: 'Tous les modules'}).locator('visible=true').first();
    if (await allBtn.isVisible().catch(() => false)) { await allBtn.click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: 'Paramètres', exact: true}).click(); }
    else await p.locator('.es-nav button').filter({hasText: 'Paramètres'}).first().click();
    await p.mouse.move(W - 4, H - 4); await p.waitForTimeout(2000);
    await p.getByRole('button', {name: /Structure & classes/}).first().click(); await p.waitForTimeout(2000);
    await p.getByRole('tab', {name: /Sections & options/}).click(); await p.waitForTimeout(1500);
    const cat = p.locator('.sw-options').first();
    await cat.scrollIntoViewIfNeeded();
    out[W] = await p.evaluate(() => ({chips: document.querySelectorAll('.sw-options .sw-chip').length,
      groups: [...document.querySelectorAll('.sw-options .sw-option-group')].map(g => (g.querySelector('b')?.textContent || '') + (g.tagName === 'DETAILS' ? (g.open ? ' [ouvert]' : ' [replié]') : '')),
      bad: /Ã|Â/.test(document.querySelector('.sw-options')?.textContent || ''),
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth}));
    await cat.screenshot({path: `${OUT}/options_${W}.png`});
    await ctx.close();
  }
} finally { await b.close(); }
console.log(JSON.stringify(out, null, 1));
