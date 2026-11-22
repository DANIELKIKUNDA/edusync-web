// V2 lot 0 — « Modules » of the platform school sheet, local stack + local test accounts only (never staging or production).
// 1. platform sign-in (TOTP of the local test account, never printed), Écoles → school C sheet → Modules card;
// 2. screenshots + measures at 6 sizes (page overflow, elements outside the screen, touch targets < 40 px in the card);
// 3. at 1280: Activer « Pédagogie » (motif, confirmation code) → state « Actif depuis… » + history line;
//    at 390 (phone): Retirer (motif) → back to « Retiré le… ».
//     cd frontend && node browser-tests/local_school_modules.mjs
import {chromium} from '@playwright/test';
import fs from 'node:fs';
import crypto from 'node:crypto';

const OUT = '../.local/school_modules'; fs.mkdirSync(OUT, {recursive: true});
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const SCHOOL = FX.C.code;
const acc = JSON.parse(fs.readFileSync('../.local/platform/.account.json', 'utf8'));
const SIZES = (process.env.EDUSYNC_VIEWPORTS || '320x568,390x844,768x1024,844x390,1280x800,1440x900').split(',').map(v => v.split('x').map(Number));
function totp(secret) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = '';
  for (const ch of secret.replace(/[\s=]/g, '').toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, '0');
  const key = Buffer.from(bits.match(/.{8}/g).map(x => parseInt(x, 2)));
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto.createHmac('sha1', key).update(counter).digest(); const o = h[h.length - 1] & 15;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1e6)).padStart(6, '0');
}
let lastWindow = -1;   // a code is accepted once: wait for the next 30 s window before reusing the key
async function freshCode() {
  if (Math.floor(Date.now() / 30000) === lastWindow) await new Promise(r => setTimeout(r, 30500 - (Date.now() % 30000)));
  lastWindow = Math.floor(Date.now() / 30000); return totp(acc.totp);
}
const measure = p => p.evaluate(() => {
  const W = document.documentElement.clientWidth;
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const scroller = el => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { const ox = getComputedStyle(e).overflowX; if (ox === 'auto' || ox === 'scroll') return true; } return false; };
  const card = document.querySelector('.sm-card');
  const wide = card ? [...card.querySelectorAll('*')].filter(e => vis(e) && e.getBoundingClientRect().right > W + 1 && !scroller(e)) : [];
  const small = card ? [...card.querySelectorAll('button')].filter(vis).filter(e => e.getBoundingClientRect().height < 40) : [];
  return {overflow: document.documentElement.scrollWidth - W, card: !!card, cardOffscreen: wide.length,
    smallTargets: small.map(e => e.textContent.trim()), state: card?.querySelector('.sm-state')?.textContent || null,
    included: card ? card.querySelectorAll('.sm-included li').length : 0};
});

async function signIn(b, W, H) {
  const phone = Math.min(W, H) < 600;
  const ctx = await b.newContext({viewport: {width: W, height: H}, isMobile: phone, hasTouch: phone, deviceScaleFactor: 1});
  const p = await ctx.newPage();
  await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click();
  await p.getByLabel('Code à 6 chiffres').first().waitFor({timeout: 20000}); await p.getByLabel('Code à 6 chiffres').first().fill(await freshCode());
  const go = p.getByRole('button', {name: /Valider|Continuer|Se connecter|Vérifier/}).first(); if (await go.isVisible().catch(() => false)) await go.click();
  await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500);
  const allBtn = p.getByRole('button', {name: 'Tous les modules'}).locator('visible=true').first();
  if (await allBtn.isVisible().catch(() => false)) { await allBtn.click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: 'Écoles', exact: true}).click(); }
  else await p.locator('.es-nav button').filter({hasText: 'Écoles'}).first().click();
  await p.mouse.move(W - 4, H - 4); await p.waitForTimeout(2000);
  await p.locator('.sc-row').filter({hasText: SCHOOL}).first().click();
  await p.locator('.sm-card').waitFor({timeout: 20000}); await p.waitForTimeout(1200);
  return {ctx, p};
}

async function change(p, kind, reason) {
  await p.locator('.sm-card').getByRole('button', {name: kind === 'activate' ? 'Activer' : 'Retirer'}).click();
  const dlg = p.getByRole('dialog').filter({hasText: kind === 'activate' ? 'Activer le module' : 'Retirer le module'});
  await dlg.getByLabel('Motif *').fill(reason); await p.waitForTimeout(800);   // end of the opening animation
  await p.screenshot({path: `${OUT}/${kind}_dialog_${p.viewportSize().width}.png`});
  await dlg.getByRole('button', {name: kind === 'activate' ? 'Activer' : 'Retirer', exact: true}).click();
  const code = p.locator('.es-stepup-code');
  if (await code.waitFor({timeout: 5000}).then(() => true).catch(() => false)) {
    await p.screenshot({path: `${OUT}/${kind}_code_${p.viewportSize().width}.png`});
    await code.fill(await freshCode());
  }
  await p.waitForTimeout(3000);
}

const b = await chromium.launch({channel: 'msedge'});
const report = {};
try {
  // the active state first, measured at every size afterwards
  {
    const {ctx, p} = await signIn(b, 1280, 800);
    report.before = await measure(p); await p.locator('.sm-card').screenshot({path: `${OUT}/card_before_1280.png`});
    if (report.before.state?.startsWith('Actif')) { await change(p, 'withdraw', 'Remise à zéro du test local'); }
    await change(p, 'activate', 'Essai local du module Pédagogie (lot 0)');
    report.activated = await measure(p);
    report.toast = await p.locator('[data-sonner-toast]').first().innerText().catch(() => '');
    report.history = await p.locator('.sc-history li').first().innerText().catch(() => '');
    await p.screenshot({path: `${OUT}/sheet_activated_1280.png`, fullPage: true});
    await ctx.close();
  }
  for (const [W, H] of SIZES) {
    const {ctx, p} = await signIn(b, W, H);
    report[`${W}x${H}`] = await measure(p);
    await p.locator('.sm-card').scrollIntoViewIfNeeded(); await p.screenshot({path: `${OUT}/card_${W}x${H}.png`});
    await p.screenshot({path: `${OUT}/sheet_${W}x${H}.png`, fullPage: true});
    if (W === 390) {
      await change(p, 'withdraw', 'Fin de l’essai local du module Pédagogie');
      report.withdrawn = await measure(p);
      await p.locator('.sm-card').screenshot({path: `${OUT}/card_withdrawn_390.png`});
    }
    await ctx.close();
  }
} finally { await b.close(); }
console.log(JSON.stringify(report, null, 1));
