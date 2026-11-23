// V2 lot 3b — a real teacher on his phone, local stack + local test accounts only (never staging or production).
// Teacher 2 (Français, 1re Humanités CG A, 36 pupils): Mes classes → Français → type marks with Enter, an over-maximum
// mark, « Abs. », the network cut (mark kept on the phone) and back (sent), a pasted column; then Conduite: tap a pupil,
// tap « Retard ». Administrator: « Suivi des cotes ». Screenshots + measures (overflow, elements outside, targets).
//     cd frontend && node browser-tests/local_pedagogy_lot3b.mjs
import {chromium} from '@playwright/test';
import fs from 'node:fs';

const OUT = '../.local/pedagogy_lot3b'; fs.mkdirSync(OUT, {recursive: true});
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const ADMIN = {email: FX.C.users.ADMIN.email, password: FX.C.users.ADMIN.password};
const T2 = JSON.parse(fs.readFileSync('../.local/enseignant/.account2.json', 'utf8'));
const SIZES = (process.env.EDUSYNC_VIEWPORTS || '320x568,390x844,768x1024,1440x900').split(',').map(v => v.split('x').map(Number));
const R = {flow: []}; const step = (n, ok, d = '') => R.flow.push(`${ok ? 'PASS' : 'FAIL'} ${n}${d ? ' — ' + String(d).replace(/\s+/g, ' ').slice(0, 150) : ''}`);
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
  const ctx = await b.newContext({viewport: {width: W, height: H}, isMobile: phone, hasTouch: phone, deviceScaleFactor: 1});
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
const rowState = (p, i) => p.locator('.pgr-row').nth(i).getAttribute('class');

const b = await chromium.launch({channel: 'msedge'});
try {
  if (!process.env.MEASURE_ONLY) {
    const {ctx, p} = await open(b, T2, 390, 844);
    await tab(p, 'Mes classes');
    await p.locator('.pt-courses-go button').filter({hasText: 'Français'}).first().click(); await p.waitForTimeout(2500);
    step('« Mes classes » → Français : la fiche s’ouvre sur la période en cours', (await p.locator('.pgr-periods button.on').innerText()).includes('P2'), await p.locator('.pgr-periods button.on').innerText());
    await p.screenshot({path: `${OUT}/1_sheet_open_390.png`});
    const first = p.locator('.pgr-row input').first(); await first.click();
    for (const v of ['32', '18', '25']) { await p.keyboard.type(v); await p.keyboard.press('Enter'); await p.waitForTimeout(700); }
    await p.waitForTimeout(1200);
    step('3 cotes tapées avec Entrée : on passe seul à l’élève suivant, chacune enregistrée',
      (await rowState(p, 0)).includes('pgr-saved') && (await rowState(p, 1)).includes('pgr-saved') && (await rowState(p, 2)).includes('pgr-saved'));
    step('18 sur 40 en rouge (sous la moitié)', (await p.locator('.pgr-row input').nth(1).getAttribute('class')) === 'pgr-fail');
    await p.keyboard.type('55'); await p.keyboard.press('Enter'); await p.waitForTimeout(1500);
    step('55 sur 40 : refusé avec « Maximum 40 » sous le nom', (await p.locator('.pgr-row').nth(3).innerText()).includes('Maximum 40'), await p.locator('.pgr-row').nth(3).innerText());
    await p.locator('.pgr-row').nth(3).locator('input').fill(''); await p.locator('.pgr-row').nth(3).getByRole('button', {name: /absent/}).click(); await p.waitForTimeout(1500);
    step('bouton « Abs. » : élève absent', (await rowState(p, 3)).includes('pgr-saved') && await p.locator('.pgr-row').nth(3).locator('input').inputValue() === 'a');
    await ctx.setOffline(true); await p.waitForTimeout(1500);
    await p.locator('.pgr-row').nth(4).locator('input').fill('27'); await p.keyboard.press('Enter'); await p.waitForTimeout(2000);
    step('réseau coupé : la cote reste sur le téléphone (« sera envoyée au retour du réseau »)', (await p.locator('.pgr-row').nth(4).innerText()).includes('retour du réseau'), await p.locator('.pgr-row').nth(4).innerText());
    await p.screenshot({path: `${OUT}/2_offline_390.png`});
    await ctx.setOffline(false); await p.waitForTimeout(9000);
    await p.getByRole('button', {name: /Mes classes/}).first().click(); await p.waitForTimeout(1500);
    await p.locator('.pt-courses-go button').filter({hasText: 'Français'}).first().click(); await p.waitForTimeout(2500);
    step('réseau revenu : la cote est arrivée sur le serveur', await p.locator('.pgr-row').nth(4).locator('input').inputValue() === '27', await p.locator('.pgr-row').nth(4).locator('input').inputValue());
    await p.getByRole('button', {name: 'Coller une liste de cotes'}).click(); await p.waitForTimeout(500);
    const n = await p.locator('.pgr-row').count();
    await p.getByLabel('Cotes à coller').fill(Array.from({length: n}, (_, i) => String(20 + (i % 15))).join('\n'));
    await p.screenshot({path: `${OUT}/3_paste_390.png`});
    await p.getByRole('button', {name: 'Remplir les cases vides'}).click(); await p.waitForTimeout(2500);
    const msg = await p.locator('[data-sonner-toast]').first().innerText().catch(() => '');
    step('coller la colonne : seules les cases vides sont remplies, les 5 déjà saisies gardées', /ajoutée/.test(msg) && msg.includes('5 déjà saisie'), msg);
    step('premières cotes intactes (32 n’est pas écrasé)', await p.locator('.pgr-row').nth(0).locator('input').inputValue() === '32');
    await p.screenshot({path: `${OUT}/4_sheet_full_390.png`, fullPage: true});
    await p.locator('.pgr-back').first().click(); await p.waitForTimeout(1200);
    await tab(p, 'Conduite');
    await p.locator('.pcd-row').first().click(); await p.waitForTimeout(600);
    await p.screenshot({path: `${OUT}/5_conduct_open_390.png`});
    step('faits graves non proposés à l’enseignant', await p.locator('.pcd-rules button.grave').count() === 0);
    await p.locator('.pcd-rules button').filter({hasText: 'Retard'}).first().click(); await p.waitForTimeout(2000);
    const t = await p.locator('[data-sonner-toast]').first().innerText().catch(() => '');
    step('3 touches : classe → élève → « Retard » : points recalculés aussitôt (barème de l’école), avec « Annuler »', /: 9\d points \(E\)/.test(t) && t.includes('Annuler'), t);
    await p.screenshot({path: `${OUT}/6_conduct_done_390.png`});
    await ctx.close();
    const a = await open(b, ADMIN, 1280, 800);
    await tab(a.p, 'Suivi des cotes'); await a.p.screenshot({path: `${OUT}/7_follow_1280.png`, fullPage: true});
    const row = await a.p.locator('.pgp-list li').filter({hasText: '1re Humanités Commerciale et gestion A'}).first().innerText();
    step('la direction voit l’avancement (français complet en 1re CG A)', /[1-9]\d*\/\d+ cours complets/.test(row), row);
    await a.ctx.close();
  }
  for (const [W, H] of SIZES) {
    const {ctx, p} = await open(b, T2, W, H); const k = `${W}x${H}`; R[k] = {};
    await tab(p, 'Mes classes'); await p.locator('.pt-courses-go button').filter({hasText: 'Français'}).first().click(); await p.waitForTimeout(2500);
    R[k].sheet = await measure(p); await p.screenshot({path: `${OUT}/sheet_${k}.png`}); await p.screenshot({path: `${OUT}/sheet_full_${k}.png`, fullPage: true});
    await p.locator('.pgr-back').first().click(); await p.waitForTimeout(1200);     // focus mode: back to the tabs
    await tab(p, 'Conduite'); R[k].conduct = await measure(p); await p.screenshot({path: `${OUT}/conduct_${k}.png`});
    await ctx.close();
  }
} finally { await b.close(); }
console.log(JSON.stringify(R, null, 1));
