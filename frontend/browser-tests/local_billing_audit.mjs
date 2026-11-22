// Abonnements — local visual certification (owner, 2026-11-21: « son interface est trop bizarre, il déplace la barre du
// haut et la barre du bas »). Logs in on the LOCAL stack with the local test accounts (never staging or production),
// opens the platform « Abonnements » screen and every tab, then the school « Mon abonnement », at 6 sizes. For each
// screen: screenshot + measures — page overflow (horizontal scroll), position of the top bar and of the bottom bar
// compared with the dashboard, elements outside the screen, touch targets under 40 px.
//     cd frontend && node browser-tests/local_billing_audit.mjs [platform,admin]
import {chromium} from '@playwright/test';
import fs from 'node:fs';
import crypto from 'node:crypto';

const OUT = '../.local/billing_audit'; fs.mkdirSync(OUT, {recursive: true});
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const accounts = (process.argv[2] || 'platform,admin').split(',');
const account = f => f === 'admin' ? {email: FX.C.users.ADMIN.email, password: FX.C.users.ADMIN.password} : JSON.parse(fs.readFileSync(`../.local/${f}/.account.json`, 'utf8'));
const SIZES = (process.env.EDUSYNC_VIEWPORTS || '320x568,390x844,768x1024,844x390,1280x800,1440x900').split(',').map(v => v.split('x').map(Number));
function totp(secret) {   // RFC 6238, the local test account's key (never printed)
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = '';
  for (const ch of secret.replace(/[\s=]/g, '').toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, '0');
  const key = Buffer.from(bits.match(/.{8}/g).map(x => parseInt(x, 2)));
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto.createHmac('sha1', key).update(counter).digest(); const o = h[h.length - 1] & 15;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1e6)).padStart(6, '0');
}
const measure = p => p.evaluate(() => {
  const rect = sel => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)}; };
  const W = document.documentElement.clientWidth;
  const scroller = el => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { const ox = getComputedStyle(e).overflowX; if (ox === 'auto' || ox === 'scroll') return true; } return false; };
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const wide = [...document.querySelectorAll('body *')].filter(e => vis(e) && e.getBoundingClientRect().right > W + 1 && !scroller(e) && getComputedStyle(e).position !== 'fixed');
  const offenders = wide.filter(e => !wide.includes(e.parentElement));
  const main = document.querySelector('.es-main, main') || document.body;
  const small = [...main.querySelectorAll('button,a,[role=tab],select,input:not([type=hidden]),textarea')].filter(vis).filter(e => e.getBoundingClientRect().height < 40);
  return {overflow: document.documentElement.scrollWidth - W, top: rect('.es-topbar') || rect('header'), bottom: rect('.es-bottom'),
    offscreen: offenders.length, offscreenSamples: offenders.slice(0, 4).map(e => (typeof e.className === 'string' && e.className ? e.className : e.tagName).slice(0, 50)),
    smallTargets: small.length, smallSamples: [...new Set(small.slice(0, 5).map(e => (e.textContent || e.getAttribute('aria-label') || e.tagName).trim().slice(0, 28)))],
    title: (document.querySelector('.es-topbar h1, header h1, h1')?.textContent || '').trim()};
});
const b = await chromium.launch({channel: 'msedge'});
const report = {};
let lastWindow = -1;   // a TOTP code is accepted once: wait for the next 30 s window before reusing the key
for (const f of accounts) for (const [W, H] of SIZES) {
  const acc = account(f); const size = `${W}x${H}`; const phone = Math.min(W, H) < 600;
  const ctx = await b.newContext({viewport: {width: W, height: H}, isMobile: phone, hasTouch: phone, deviceScaleFactor: 1, colorScheme: process.env.EDUSYNC_DARK ? 'dark' : 'light'});
  const p = await ctx.newPage(); const key = `${f}_${size}`; report[key] = {};
  try {
    await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
    await p.getByRole('button', {name: 'Se connecter'}).click();
    if (acc.totp) { const w = Math.floor(Date.now() / 30000); if (w === lastWindow) await p.waitForTimeout(30500 - (Date.now() % 30000)); lastWindow = Math.floor(Date.now() / 30000);
      await p.getByLabel('Code à 6 chiffres').first().waitFor({timeout: 20000}); await p.getByLabel('Code à 6 chiffres').first().fill(totp(acc.totp));
      const go = p.getByRole('button', {name: /Valider|Continuer|Se connecter|Vérifier/}).first(); if (await go.isVisible().catch(() => false)) await go.click(); }
    await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(3000);
    report[key].before = await measure(p); await p.screenshot({path: `${OUT}/${key}_0_accueil.png`});
    const label = f === 'platform' ? 'Abonnements' : 'Mon abonnement';
    const allBtn = p.getByRole('button', {name: 'Tous les modules'}).locator('visible=true').first();
    if (await allBtn.isVisible().catch(() => false)) { await allBtn.click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: label, exact: true}).click(); }
    else await p.locator('.es-nav button').filter({hasText: label}).first().click();
    await p.mouse.move(W - 4, H - 4);   // tablet rail expands on hover: move away before reading the screen
    await p.waitForTimeout(2500);
    report[key].module = await measure(p); await p.screenshot({path: `${OUT}/${key}_1_module.png`, fullPage: true});
    const tabs = p.locator('.bl-tabs button, .ss-tabs button, [role=tablist] button');
    const n = await tabs.count();
    for (let i = 0; i < n; i++) {
      const name = (await tabs.nth(i).innerText()).trim(); await tabs.nth(i).click(); await p.waitForTimeout(1200);
      report[key]['tab:' + name] = await measure(p);
      await p.screenshot({path: `${OUT}/${key}_2_${i}_${name.toLowerCase().normalize('NFD').replace(/[^a-z]/g, '').slice(0, 16)}.png`, fullPage: true});
    }
    if (f === 'platform') for (const [tabName, button, slug] of [['Abonnements', 'Attribuer une offre', 'attribuer'], ['Offres', 'Ajouter un tarif', 'tarif'],
      ['Factures', 'Enregistrer un paiement', 'paiement']]) {
      try {
        await p.getByRole('tab', {name: new RegExp('^' + tabName)}).click(); await p.waitForTimeout(900);
        await p.getByRole('button', {name: button}).first().click(); await p.waitForTimeout(1200);
        report[key]['dialog:' + slug] = await p.evaluate(() => { const d = document.querySelector('dialog[open]'); if (!d) return {open: false};
          const r = d.getBoundingClientRect(); return {open: true, fits: r.left >= 0 && r.right <= document.documentElement.clientWidth + 1, w: Math.round(r.width), h: Math.round(r.height)}; });
        await p.screenshot({path: `${OUT}/${key}_3_${slug}.png`});
        await p.keyboard.press('Escape'); await p.waitForTimeout(400);
      } catch (e) { report[key]['dialog:' + slug] = {error: String(e.message).split(String.fromCharCode(10))[0]}; }
    }
    const m = report[key].module, bef = report[key].before;
    const moved = JSON.stringify([bef.top, bef.bottom]) !== JSON.stringify([m.top, m.bottom]);
    console.log(`== ${key} débord=${m.overflow} horsÉcran=${m.offscreen}${m.offscreen ? '(' + m.offscreenSamples.join(',') + ')' : ''} barres déplacées=${moved} petits=${m.smallTargets} onglets=${n}`);
    for (const [k, v] of Object.entries(report[key])) if (k.startsWith('tab:') && (v.overflow > 0 || v.offscreen)) console.log(`   ${k} débord=${v.overflow} horsÉcran=${v.offscreen} (${v.offscreenSamples.join(',')})`);
    for (const [k, v] of Object.entries(report[key])) if (k.startsWith('dialog:')) console.log(`   ${k} ${v.error ? 'ERREUR ' + v.error.slice(0, 90) : v.open ? (v.fits ? 'tient dans l’écran' : 'DÉBORDE') + ` ${v.w}×${v.h}` : 'non ouverte'}`);
  } catch (e) { report[key].error = String(e.message).split('\n')[0]; console.log(`== ${key} — ERREUR ${report[key].error.slice(0, 160)}`); await p.screenshot({path: `${OUT}/${key}_erreur.png`}).catch(() => {}); }
  await ctx.close();
}
fs.writeFileSync(`${OUT}/audit.json`, JSON.stringify(report, null, 1));
await b.close();
