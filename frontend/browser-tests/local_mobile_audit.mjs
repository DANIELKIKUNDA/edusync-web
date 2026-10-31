// Mobile-first audit (2026-10-31) — every role, every module, 390 × 844 phone (touch, Android user agent), LOCAL stack.
// Objective measures per screen, written to ../.local/mobile_audit/audit.json, plus a screenshot of the first screen:
//   overflow (page wider than the phone), cut tables, hidden tabs, touch targets < 44 px, the page title repeated,
//   the bottom navigation bar (destinations offered to the role), the height of the page before the first content.
// Usage: node browser-tests/local_mobile_audit.mjs [folder,folder] — accounts in ../.local/<folder>/.account.json
// (« admin » = the administrator of the fixtures, « platform » = the local Manager Système with its test second factor). Read only: it opens screens, never submits anything.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
import crypto from 'node:crypto';
const OUT = '../.local/mobile_audit'; fs.mkdirSync(OUT, {recursive: true});
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const ALL = ['platform', 'admin', 'gestionnaire', 'caissier', 'secretariat', 'intendant', 'prefet', 'directeur_etudes', 'directeur_discipline', 'directeur_primaire', 'directrice_maternelle', 'responsable_finance', 'promoteur'];
const accounts = (process.argv[2] ? process.argv[2].split(',') : ALL);
const account = f => f === 'admin' ? {email: FX.C.users.ADMIN.email, password: FX.C.users.ADMIN.password} : JSON.parse(fs.readFileSync(`../.local/${f}/.account.json`, 'utf8'));
function totp(secret) {   // RFC 6238, the local test account's key (never printed)
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = '';
  for (const ch of secret.replace(/[\s=]/g, '').toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, '0');
  const key = Buffer.from(bits.match(/.{8}/g).map(x => parseInt(x, 2)));
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto.createHmac('sha1', key).update(counter).digest(); const o = h[h.length - 1] & 15;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1e6)).padStart(6, '0');
}
const report = fs.existsSync(`${OUT}/audit.json`) ? JSON.parse(fs.readFileSync(`${OUT}/audit.json`, 'utf8')) : {};
const b = await chromium.launch({channel: 'msedge'});
const measure = p => p.evaluate(() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const main = document.querySelector('.es-main, main') || document.body;
  const title = (document.querySelector('.es-topbar h1, header h1, h1')?.textContent || '').trim();
  const repeats = title ? [...main.querySelectorAll('h1,h2,h3,b,strong,span')].filter(e => vis(e) && e.children.length === 0 && e.textContent.trim() === title).length : 0;
  const small = [...main.querySelectorAll('button,a,[role=tab],select,input:not([type=hidden])')].filter(vis).filter(e => { const r = e.getBoundingClientRect(); return r.height < 40 || (e.tagName !== 'INPUT' && e.tagName !== 'SELECT' && r.width < 40); });
  const tables = [...main.querySelectorAll('table')].filter(vis);
  const cut = tables.filter(t => (t.parentElement?.scrollWidth ?? 0) > (t.parentElement?.clientWidth ?? 0) + 2 || t.scrollWidth > main.clientWidth + 2).length;
  const tabs = [...main.querySelectorAll('[role=tablist], .personTabs, .financeTabs, .kp-tabs')].filter(vis).filter(t => t.scrollWidth > t.clientWidth + 2).length;
  const bar = [...document.querySelectorAll('.es-bottom button')].map(x => x.textContent.trim());
  const firstContent = [...main.querySelectorAll('section, article, table, ul, form')].filter(vis).map(e => e.getBoundingClientRect().top + scrollY).filter(t => t > 140)[0] ?? 0;
  return {title, repeats, smallTargets: small.length, smallSamples: [...new Set(small.slice(0, 6).map(e => (e.textContent || e.getAttribute('aria-label') || e.tagName).trim().slice(0, 30)))],
    tables: tables.length, cutTables: cut, hiddenTabs: tabs, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    height: document.documentElement.scrollHeight, firstContentTop: Math.round(firstContent), bottomBar: bar};
});
for (const f of accounts) {
  const acc = account(f);
  const ctx = await b.newContext({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true, deviceScaleFactor: 1,
    userAgent: 'Mozilla/5.0 (Linux; Android 13; SM-A145F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36'});
  const p = await ctx.newPage(); report[f] = {};
  try {
    await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
    await p.getByRole('button', {name: 'Se connecter'}).click();
    if (acc.totp) { await p.getByLabel('Code à 6 chiffres').first().waitFor({timeout: 20000}); await p.getByLabel('Code à 6 chiffres').first().fill(totp(acc.totp));
      const go = p.getByRole('button', {name: /Valider|Continuer|Se connecter|Vérifier/}).first(); if (await go.isVisible().catch(() => false)) await go.click(); }
    await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(3500);
    const space = p.getByRole('button', {name: /Plateforme EduSync|Atelier/}).first(); if (f === 'platform' && await space.isVisible().catch(() => false) && !(await p.locator('.es-bottom').count())) await space.click();
    await p.getByRole('button', {name: 'Tous les modules'}).click(); await p.waitForTimeout(600);
    const modules = (await p.getByRole('dialog', {name: 'Menu EduSync'}).locator('nav button, .es-drawer-nav button').allInnerTexts()).map(x => x.trim()).filter(x => x && !/^[A-Z]{2}(\s|$)/.test(x));
    await p.keyboard.press('Escape'); await p.waitForTimeout(400); if (await p.getByRole('dialog', {name: 'Menu EduSync'}).isVisible().catch(() => false)) await p.mouse.click(380, 400);
    console.log(`== ${f} : ${modules.join(' | ')}`);
    for (const m of modules) {
      try {
        await p.getByRole('button', {name: 'Tous les modules'}).click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: m, exact: true}).click();
        await p.waitForTimeout(2200);
        const r = await measure(p); report[f][m] = r;
        const slug = m.toLowerCase().normalize('NFD').replace(/[^a-z]/g, '').slice(0, 18);
        await p.screenshot({path: `${OUT}/${f}_${slug}.png`});
        console.log(`   ${m.padEnd(24)} titre×${r.repeats} petits=${r.smallTargets} tableaux=${r.tables}(coupés ${r.cutTables}) onglets cachés=${r.hiddenTabs} débord=${r.overflow} 1er contenu=${r.firstContentTop}px barre=[${r.bottomBar.join(', ')}]`);
      } catch (e) { report[f][m] = {error: String(e.message).split('\n')[0]}; console.log(`   ${m} — ERREUR ${String(e.message).split('\n')[0].slice(0, 120)}`); }
    }
  } catch (e) { console.log(`== ${f} — ERREUR ${String(e.message).split('\n')[0]}`); }
  await ctx.close();
  fs.writeFileSync(`${OUT}/audit.json`, JSON.stringify(report, null, 1));
}
await b.close();
