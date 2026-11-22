// V2 lot 3a — local stack + local test accounts only (never staging or production).
// Administrator: Enseignants (titulaire + « tous les cours » for 1re primaire A, same titular for 2 humanités classes,
// one course by hand) → Conduite (barème: −, add a fact, save) → Étapes (4 steps). Teacher: « Mes classes ».
// Screenshots + measures at 5 sizes (overflow, elements outside the screen, targets < 40 px).
//     cd frontend && node browser-tests/local_pedagogy_lot3a.mjs
import {chromium} from '@playwright/test';
import fs from 'node:fs';

const OUT = '../.local/pedagogy_lot3a'; fs.mkdirSync(OUT, {recursive: true});
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const ADMIN = {email: FX.C.users.ADMIN.email, password: FX.C.users.ADMIN.password};
const T1 = JSON.parse(fs.readFileSync('../.local/enseignant/.account1.json', 'utf8'));
const T2 = JSON.parse(fs.readFileSync('../.local/enseignant/.account2.json', 'utf8'));
const SIZES = (process.env.EDUSYNC_VIEWPORTS || '320x568,390x844,768x1024,844x390,1440x900').split(',').map(v => v.split('x').map(Number));
const measure = p => p.evaluate(() => {
  const W = document.documentElement.clientWidth;
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const scroller = el => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { const ox = getComputedStyle(e).overflowX; if (ox === 'auto' || ox === 'scroll') return true; } return false; };
  const scope = document.querySelector('.pg'); if (!scope) return {missing: true};
  const wide = [...scope.querySelectorAll('*')].filter(e => vis(e) && e.getBoundingClientRect().right > W + 1 && !scroller(e));
  const small = [...scope.querySelectorAll('button,select,input:not([type=checkbox])')].filter(vis).filter(e => e.getBoundingClientRect().height < 40);
  return {overflow: document.documentElement.scrollWidth - W, offscreen: wide.length, offSamples: wide.slice(0, 3).map(e => String(e.className || e.tagName).slice(0, 40)),
    small: [...new Set(small.map(e => (e.getAttribute('aria-label') || e.textContent || e.tagName).trim().slice(0, 30)))].slice(0, 5)};
});
async function open(b, acc, W, H) {
  const phone = Math.min(W, H) < 600;
  const ctx = await b.newContext({viewport: {width: W, height: H}, isMobile: phone, hasTouch: phone, deviceScaleFactor: 1});
  const p = await ctx.newPage();
  await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500);
  const allBtn = p.getByRole('button', {name: 'Tous les modules'}).locator('visible=true').first();
  if (await allBtn.isVisible().catch(() => false)) { await allBtn.click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: 'Pédagogie', exact: true}).click(); }
  else if (await p.locator('.es-nav button').filter({hasText: 'Pédagogie'}).first().isVisible().catch(() => false)) await p.locator('.es-nav button').filter({hasText: 'Pédagogie'}).first().click();
  else await p.locator('.es-bottom button, nav button').filter({hasText: 'Pédagogie'}).first().click();
  await p.mouse.move(W - 4, H - 4); await p.locator('.pg').waitFor({timeout: 20000}); await p.waitForTimeout(1500);
  return {ctx, p};
}
const tab = async (p, name) => { await p.getByRole('tab', {name, exact: true}).click(); await p.waitForTimeout(1800); };
const toast = p => p.locator('[data-sonner-toast]').first().innerText().catch(() => '');
const R = {flow: []}; const step = (n, ok, d = '') => R.flow.push(`${ok ? 'PASS' : 'FAIL'} ${n}${d ? ' — ' + String(d).replace(/\s+/g, ' ').slice(0, 140) : ''}`);

const b = await chromium.launch({channel: 'msedge'});
try {
  if (!process.env.MEASURE_ONLY) {     // MEASURE_ONLY=1: screenshots and measures only (journey already done)
    const {ctx, p} = await open(b, ADMIN, 1280, 800);
    await tab(p, 'Enseignants'); await p.screenshot({path: `${OUT}/1_teachers_start.png`, fullPage: true});
    const p1 = p.locator('.pt-list > li').filter({hasText: '1re primaire A'}).first();
    await p1.getByLabel(/Titulaire/).selectOption({label: T1.name}); await p.waitForTimeout(1500);
    await p1.getByLabel('Donner tous les cours restants à').selectOption({label: T1.name});
    await p1.getByRole('button', {name: /Attribuer \d+ cours/}).click(); await p.waitForTimeout(2000);
    step('1re primaire A : titulaire et tous les cours en un clic', (await p1.innerText()).match(/(\d+)\/\1 cours attribués/), await p1.locator('.pc-chip').innerText());
    for (const label of ['1re Humanités Commerciale et gestion A', '1re Humanités Commerciale et gestion B']) {
      const c = p.locator('.pt-list > li').filter({hasText: label}).first();
      await c.getByLabel(/Titulaire/).selectOption({label: T2.name}); await p.waitForTimeout(1500);
    }
    step('un même titulaire pour 2 classes', await p.locator('.pt-list > li').filter({hasText: 'Humanités Commerciale et gestion'}).locator('select').first().evaluate(s => s.options[s.selectedIndex].text) === T2.name);
    const cg = p.locator('.pt-list > li').filter({hasText: '1re Humanités Commerciale et gestion A'}).first();
    await cg.getByRole('button', {name: /Voir et modifier cours par cours/}).click(); await p.waitForTimeout(500);
    await cg.getByLabel('Enseignant — Français').selectOption({label: T2.name}); await p.waitForTimeout(1500);
    step('un cours attribué à la main (Français)', (await toast(p)).includes('Français'), await toast(p));
    await p.screenshot({path: `${OUT}/2_teachers_done.png`, fullPage: true});
    await tab(p, 'Conduite'); await p.screenshot({path: `${OUT}/3_conduct_proposed.png`, fullPage: true});
    await p.getByRole('button', {name: 'Plus pour Retard'}).click();
    await p.getByLabel('Nouveau fait').fill('Téléphone en classe'); await p.getByRole('button', {name: 'Ajouter', exact: true}).click();
    await p.getByRole('button', {name: /Enregistrer ce barème|Enregistrer les changements/}).click(); await p.waitForTimeout(2000);
    step('barème de conduite enregistré (retard −1, téléphone ajouté)', (await toast(p)).includes('Barème'), await toast(p));
    await p.screenshot({path: `${OUT}/4_conduct_saved.png`, fullPage: true});
    await tab(p, 'Étapes'); await p.screenshot({path: `${OUT}/5_steps.png`, fullPage: true});
    step('étapes : 4 étapes, la 4e décrit les attributions', (await p.locator('.ps-steps li').count()) === 4, await p.locator('.ps-steps li').nth(3).innerText());
    await ctx.close();
  }
  if (!process.env.MEASURE_ONLY) {
    const {ctx, p} = await open(b, T1, 390, 844);
    step('l’enseignant arrive sur « Mes classes »', await p.getByRole('tab', {name: 'Mes classes'}).getAttribute('aria-selected') === 'true');
    const txt = await p.locator('.pt-mine').innerText();
    step('il voit sa classe, ses cours et son titulariat', txt.includes('1re primaire A') && txt.includes('titulaire'), txt);
    step('il ne voit pas l’onglet Enseignants', await p.getByRole('tab', {name: 'Enseignants'}).count() === 0);
    await p.screenshot({path: `${OUT}/6_teacher_mine_390.png`, fullPage: true});
    R.teacher390 = await measure(p);
    await ctx.close();
  }
  for (const [W, H] of SIZES) {
    const {ctx, p} = await open(b, ADMIN, W, H); const k = `${W}x${H}`; R[k] = {};
    for (const [name, file] of [['Enseignants', 'teachers'], ['Conduite', 'conduct'], ['Étapes', 'steps']]) {
      await tab(p, name); R[k][file] = await measure(p); await p.screenshot({path: `${OUT}/${file}_${k}.png`, fullPage: W < 800});
    }
    await ctx.close();
  }
} finally { await b.close(); }
console.log(JSON.stringify(R, null, 1));
