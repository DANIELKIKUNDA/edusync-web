// V2 lot 1 — « Pédagogie » of a school, local stack + local test accounts only (never staging or production).
// School C administrator: menu « Pédagogie » → Correspondance des classes (confirm EduSync's proposals) → Référentiel
// officiel (Secondaire, Technique groupe 1, programme 1CG). Screenshots + measures at 6 sizes; the links are made once
// (at 1280) then every size shows the linked state.
//     cd frontend && node browser-tests/local_pedagogy.mjs
import {chromium} from '@playwright/test';
import fs from 'node:fs';

const OUT = '../.local/pedagogy'; fs.mkdirSync(OUT, {recursive: true});
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const acc = {email: FX.C.users.ADMIN.email, password: FX.C.users.ADMIN.password};
const SIZES = (process.env.EDUSYNC_VIEWPORTS || '1280x800,320x568,390x844,768x1024,844x390,1440x900').split(',').map(v => v.split('x').map(Number));
const measure = p => p.evaluate(() => {
  const W = document.documentElement.clientWidth;
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const scroller = el => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { const ox = getComputedStyle(e).overflowX; if (ox === 'auto' || ox === 'scroll') return true; } return false; };
  const page = document.querySelector('.pg');
  const wide = page ? [...page.querySelectorAll('*')].filter(e => vis(e) && e.getBoundingClientRect().right > W + 1 && !scroller(e)) : [];
  const small = page ? [...page.querySelectorAll('button,select,input')].filter(vis).filter(e => e.getBoundingClientRect().height < 40) : [];
  return {overflow: document.documentElement.scrollWidth - W, offscreen: wide.length, offscreenSamples: wide.slice(0, 3).map(e => e.className || e.tagName),
    smallTargets: [...new Set(small.map(e => (e.textContent || e.getAttribute('aria-label') || e.tagName).trim().slice(0, 30)))].slice(0, 6),
    summary: [...document.querySelectorAll('.pg-summary b')].map(b => b.textContent)};
});

async function open(b, W, H) {
  const phone = Math.min(W, H) < 600;
  const ctx = await b.newContext({viewport: {width: W, height: H}, isMobile: phone, hasTouch: phone, deviceScaleFactor: 1});
  const p = await ctx.newPage();
  await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click();
  await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(3000);
  const allBtn = p.getByRole('button', {name: 'Tous les modules'}).locator('visible=true').first();
  if (await allBtn.isVisible().catch(() => false)) { await allBtn.click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: 'Pédagogie', exact: true}).click(); }
  else await p.locator('.es-nav button').filter({hasText: 'Pédagogie'}).first().click();
  await p.mouse.move(W - 4, H - 4);
  await p.locator('.pg').waitFor({timeout: 20000}); await p.waitForTimeout(2500);
  return {ctx, p};
}

const b = await chromium.launch({channel: 'msedge'});
const report = {};
try {
  for (const [W, H] of SIZES) {
    const {ctx, p} = await open(b, W, H); const key = `${W}x${H}`; report[key] = {};
    await p.getByRole('tab', {name: 'Classes de l’école'}).click(); await p.waitForTimeout(1500);
    if (W === 1280 && await p.getByRole('button', {name: /Confirmer les \d+ propositions/}).isVisible().catch(() => false)) {
      report.before = await measure(p); await p.screenshot({path: `${OUT}/links_before_${key}.png`, fullPage: true});
      await p.getByRole('button', {name: /Confirmer les \d+ propositions/}).click(); await p.waitForTimeout(3000);
      report.toast = await p.locator('[data-sonner-toast]').first().innerText().catch(() => '');
    }
    report[key].links = await measure(p); await p.screenshot({path: `${OUT}/links_${key}.png`}); await p.screenshot({path: `${OUT}/links_full_${key}.png`, fullPage: true});
    if (W === 390) {                                         // change one link by hand, on a phone
      await p.getByRole('button', {name: /^Modifier la classe officielle/}).first().click(); await p.waitForTimeout(800);
      await p.screenshot({path: `${OUT}/choose_${key}.png`});
      await p.getByRole('button', {name: 'Annuler'}).click(); await p.waitForTimeout(400);
    }
    await p.getByRole('tab', {name: 'Référentiel officiel'}).click(); await p.waitForTimeout(1500);
    await p.getByRole('button', {name: /Technique — Groupe 1/}).click(); await p.waitForTimeout(600);
    report[key].referential = await measure(p); await p.screenshot({path: `${OUT}/ref_${key}.png`});
    await p.getByRole('button', {name: /Programme 1ère humanité Commerciale/}).first().click(); await p.waitForTimeout(2000);
    report[key].programme = await p.evaluate(() => ({rows: document.querySelectorAll('.pg-table tbody tr').length,
      total: [...document.querySelectorAll('.pg-table tfoot td')].map(td => td.textContent).join(' '),
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth}));
    await p.screenshot({path: `${OUT}/programme_${key}.png`});
    await ctx.close();
  }
} finally { await b.close(); }
console.log(JSON.stringify(report, null, 1));
