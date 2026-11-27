// V2 lot 3c — comfort, as real users, local stack + local test accounts only (never staging or production).
// Teacher (phone): sheets prepared for no network → network cut → « Mes classes » and the sheet open from the phone copy,
// a mark kept on the phone → network back; « Trouver un élève » (pile of copies); class summary; printable sheet (PDF);
// conduct for several pupils in one tap. Management: « Qui n'a pas fini » + « Relancer ». Measures at 4 sizes.
//     cd frontend && node browser-tests/local_pedagogy_lot3c.mjs
import {chromium} from '@playwright/test';
import fs from 'node:fs';

const OUT = '../.local/pedagogy_lot3c'; fs.mkdirSync(OUT, {recursive: true});
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const ADMIN = {email: FX.C.users.ADMIN.email, password: FX.C.users.ADMIN.password};
const T2 = JSON.parse(fs.readFileSync('../.local/enseignant/.account2.json', 'utf8'));
const SIZES = (process.env.EDUSYNC_VIEWPORTS || '320x568,390x844,768x1024,1440x900').split(',').map(v => v.split('x').map(Number));
const R = {flow: []}; const step = (n, ok, d = '') => R.flow.push(`${ok ? 'PASS' : 'FAIL'} ${n}${d ? ' — ' + String(d).replace(/\s+/g, ' ').slice(0, 160) : ''}`);
const measure = p => p.evaluate(() => {
  const W = document.documentElement.clientWidth;
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const scroller = el => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { const ox = getComputedStyle(e).overflowX; if (ox === 'auto' || ox === 'scroll') return true; } return false; };
  const scope = document.querySelector('.pg'); if (!scope) return {missing: true};
  const wide = [...scope.querySelectorAll('*')].filter(e => vis(e) && e.getBoundingClientRect().right > W + 1 && !scroller(e));
  const small = [...scope.querySelectorAll('button,select,input')].filter(vis).filter(e => e.getBoundingClientRect().height < 40);
  return {overflow: document.documentElement.scrollWidth - W, offscreen: wide.length, offSamples: wide.slice(0, 3).map(e => String(e.className || e.tagName).slice(0, 40)),
    small: [...new Set(small.map(e => (e.getAttribute('aria-label') || e.textContent || e.tagName).trim().slice(0, 30)))].slice(0, 5)};
});
async function open(b, acc, W, H) {
  const phone = Math.min(W, H) < 600;
  const ctx = await b.newContext({viewport: {width: W, height: H}, isMobile: phone, hasTouch: phone, deviceScaleFactor: 1, acceptDownloads: true});
  const p = await ctx.newPage();
  await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500);
  const nav = p.locator('.es-nav button, .es-bottom button, nav button').filter({hasText: 'Pédagogie'}).locator('visible=true').first();
  if (await nav.isVisible().catch(() => false)) await nav.click();
  else { await p.getByRole('button', {name: 'Tous les modules'}).locator('visible=true').first().click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: 'Pédagogie', exact: true}).click(); }
  await p.mouse.move(W - 4, H - 4); await p.locator('.pg').waitFor({timeout: 20000}); await p.waitForTimeout(1500);
  return {ctx, p};
}
const tab = async (p, name) => { await p.getByRole('tab', {name, exact: true}).click(); await p.waitForTimeout(1800); };
const toast = p => p.locator('[data-sonner-toast]').first().innerText().catch(() => '');

const b = await chromium.launch({channel: 'msedge'});
try {
  if (!process.env.MEASURE_ONLY && !process.env.ONLY_MANAGEMENT) {
    const {ctx, p} = await open(b, T2, 390, 844);
    await tab(p, 'Mes classes');
    await p.getByText('Toutes vos fiches sont prêtes pour travailler sans réseau.').waitFor({timeout: 30000}).catch(() => {});
    step('« Mes classes » prépare toutes les fiches pour travailler sans réseau', await p.getByText('Toutes vos fiches sont prêtes pour travailler sans réseau.').count() === 1
      && await p.locator('.pt-ready').count() >= 1);
    await p.screenshot({path: `${OUT}/1_ready_390.png`});
    await ctx.setOffline(true); await p.waitForTimeout(1200);
    await tab(p, 'Calendrier'); await tab(p, 'Mes classes');
    step('sans réseau : « Mes classes » s’ouvre depuis le téléphone', await p.locator('.pt-courses-go button').filter({hasText: 'Français'}).count() >= 1);
    await p.locator('.pt-courses-go button').filter({hasText: 'Français'}).first().click(); await p.waitForTimeout(2500);
    const banner = await p.locator('.pc-note').first().innerText().catch(() => '');
    step('sans réseau : la fiche s’ouvre depuis le téléphone, avec la date de la copie', banner.includes('fiche enregistrée sur ce téléphone'), banner);
    const row = p.locator('.pgr-row').nth(5); const old = await row.locator('input').inputValue();
    const changed = old === '26' ? '27' : '26';
    await row.locator('input').fill(changed); await p.keyboard.press('Enter'); await p.waitForTimeout(2000);
    step('sans réseau : la cote reste sur le téléphone', (await row.innerText()).includes('retour du réseau'), await row.innerText());
    await p.screenshot({path: `${OUT}/2_offline_sheet_390.png`});
    await ctx.setOffline(false); await p.waitForTimeout(9000);
    await p.locator('.pgr-back').click(); await p.waitForTimeout(1500);
    await p.locator('.pt-courses-go button').filter({hasText: 'Français'}).first().click(); await p.waitForTimeout(2500);
    step('réseau revenu : la cote est arrivée', await p.locator('.pgr-row').nth(5).locator('input').inputValue() === changed);
    const name = (await p.locator('.pgr-row').nth(20).locator('.pgr-name').innerText()).split('\n')[0];
    const needle = name.split(/\s+/).slice(-1)[0].slice(0, 4);
    await p.getByPlaceholder(/Trouver un élève/).fill(needle); await p.waitForTimeout(400);
    const shownRows = await p.locator('.pgr-row:not(.pgr-gone)').count();
    await p.keyboard.press('Enter'); await p.waitForTimeout(300);
    await p.keyboard.type('31'); await p.keyboard.press('Enter'); await p.waitForTimeout(1500);
    const focused = await p.evaluate(() => document.activeElement?.getAttribute('placeholder') || '');
    step('« Trouver un élève » : tape 4 lettres, Entrée, la cote, Entrée → retour à la recherche (pile de copies)',
      shownRows >= 1 && shownRows < 36 && focused.includes('Trouver un élève') && await p.getByPlaceholder(/Trouver un élève/).inputValue() === '', `${needle} → ${shownRows} élèves`);
    const sum = await p.locator('.pgr-sum').innerText().catch(() => '');
    step('résumé de la classe : moyenne, sous la moitié, meilleure · plus faible, sans cote', /moyenne sur 40/.test(sum) && /sous la moitié/.test(sum), sum);
    await p.screenshot({path: `${OUT}/3_sheet_summary_390.png`, fullPage: true});
    const [dl] = await Promise.all([p.waitForEvent('download', {timeout: 15000}), p.getByRole('button', {name: 'Fiche vierge à imprimer'}).click()]);
    const file = await dl.path(); const head = fs.readFileSync(file).subarray(0, 5).toString();
    step('fiche vierge à imprimer : un vrai PDF téléchargé', head === '%PDF-' && dl.suggestedFilename().endsWith('.pdf'), dl.suggestedFilename());
    fs.copyFileSync(file, `${OUT}/fiche_vierge.pdf`);
    await p.locator('.pgr-back').click(); await p.waitForTimeout(1000);
    await tab(p, 'Conduite');
    await p.getByRole('button', {name: 'Plusieurs élèves'}).click(); await p.waitForTimeout(300);
    await p.locator('.pcd-row').nth(3).click(); await p.locator('.pcd-row').nth(4).click(); await p.waitForTimeout(300);
    await p.screenshot({path: `${OUT}/4_conduct_many_390.png`});
    await p.locator('.pcd-bar .pcd-rules button').filter({hasText: 'Bavardage'}).click(); await p.waitForTimeout(2000);
    const t = await toast(p);
    step('conduite : 2 élèves choisis, un seul toucher → fait enregistré pour les deux', t.includes('2 élèves'), t);
    await ctx.close();
  }
  if (!process.env.MEASURE_ONLY) {
    const a = await open(b, ADMIN, 1280, 800);
    await tab(a.p, 'Suivi des cotes');
    const lateTxt = await a.p.locator('.pgl').innerText().catch(() => '');
    step('direction : « Qui n’a pas fini » avec le nombre de cotes manquantes', /Qui n’a pas fini/i.test(lateTxt) && /cotes manquantes/.test(lateTxt), lateTxt.slice(0, 120));
    await a.p.locator('.pgl-list .ui-btn').first().click(); await a.p.waitForTimeout(1500);
    step('direction : « Relancer » un enseignant', /relancé|Déjà relancé/.test(await toast(a.p)), await toast(a.p));
    await a.p.screenshot({path: `${OUT}/5_follow_1280.png`, fullPage: true});
    await a.ctx.close();
  }
  for (const [W, H] of SIZES) {
    const {ctx, p} = await open(b, T2, W, H); const k = `${W}x${H}`; R[k] = {};
    await tab(p, 'Mes classes'); R[k].mine = await measure(p);
    await p.locator('.pt-courses-go button').filter({hasText: 'Français'}).first().click(); await p.waitForTimeout(2500);
    R[k].sheet = await measure(p); await p.screenshot({path: `${OUT}/sheet_${k}.png`});
    await p.locator('.pgr-back').click(); await p.waitForTimeout(1000);
    await tab(p, 'Conduite'); await p.getByRole('button', {name: 'Plusieurs élèves'}).click(); await p.locator('.pcd-row').first().click(); await p.waitForTimeout(300);
    R[k].conduct = await measure(p); await p.screenshot({path: `${OUT}/conduct_${k}.png`});
    await ctx.close();
  }
} finally { await b.close(); }
console.log(JSON.stringify(R, null, 1));
