// V2 lot 2 — the whole journey as a user would do it, local stack + local test administrator only (never staging or
// production). 1280: Étapes → Calendrier (save + validate both, close entry of P1) → Programmes (one click official,
// open 1CG, new version, change Droit, add a course, validate) → Étapes (all done). Then every size: screenshots +
// measures of Étapes, Calendrier, Programmes and the editor (overflow, elements outside the screen, targets < 40 px).
//     cd frontend && node browser-tests/local_pedagogy_lot2.mjs
import {chromium} from '@playwright/test';
import fs from 'node:fs';

const OUT = '../.local/pedagogy_lot2'; fs.mkdirSync(OUT, {recursive: true});
const FX = JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json', 'utf8'));
const acc = {email: FX.C.users.ADMIN.email, password: FX.C.users.ADMIN.password};
const SIZES = (process.env.EDUSYNC_VIEWPORTS || '320x568,390x844,768x1024,844x390,1440x900').split(',').map(v => v.split('x').map(Number));
const measure = (p, root = '.pg') => p.evaluate(sel => {
  const W = document.documentElement.clientWidth;
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const scroller = el => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { const ox = getComputedStyle(e).overflowX; if (ox === 'auto' || ox === 'scroll') return true; } return false; };
  const scope = document.querySelector(sel); if (!scope) return {missing: sel};
  const wide = [...scope.querySelectorAll('*')].filter(e => vis(e) && e.getBoundingClientRect().right > W + 1 && !scroller(e));
  const small = [...scope.querySelectorAll('button,select,input:not([type=checkbox])')].filter(vis).filter(e => e.getBoundingClientRect().height < 40);
  return {overflow: document.documentElement.scrollWidth - W, offscreen: wide.length, offSamples: wide.slice(0, 3).map(e => String(e.className || e.tagName).slice(0, 40)),
    small: [...new Set(small.map(e => (e.getAttribute('aria-label') || e.textContent || e.tagName).trim().slice(0, 30)))].slice(0, 5)};
}, root);
async function open(b, W, H) {
  const phone = Math.min(W, H) < 600;
  const ctx = await b.newContext({viewport: {width: W, height: H}, isMobile: phone, hasTouch: phone, deviceScaleFactor: 1});
  const p = await ctx.newPage();
  await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
  await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 40000}); await p.waitForTimeout(2500);
  const allBtn = p.getByRole('button', {name: 'Tous les modules'}).locator('visible=true').first();
  if (await allBtn.isVisible().catch(() => false)) { await allBtn.click(); await p.getByRole('dialog', {name: 'Menu EduSync'}).getByRole('button', {name: 'Pédagogie', exact: true}).click(); }
  else await p.locator('.es-nav button').filter({hasText: 'Pédagogie'}).first().click();
  await p.mouse.move(W - 4, H - 4); await p.locator('.pg').waitFor({timeout: 20000}); await p.waitForTimeout(1500);
  return {ctx, p};
}
const tab = async (p, name) => { await p.getByRole('tab', {name, exact: true}).click(); await p.waitForTimeout(1800); };
const toast = p => p.locator('[data-sonner-toast]').first().innerText().catch(() => '');

const b = await chromium.launch({channel: 'msedge'});
const R = {flow: []};
const step = (name, ok, detail = '') => { R.flow.push(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`); };
try {
  const {ctx, p} = await open(b, 1280, 800);
  await tab(p, 'Étapes'); await p.screenshot({path: `${OUT}/1_steps_start.png`, fullPage: true});
  step('étapes : 1 terminée sur 3 au départ', (await p.locator('.ps-progress b').innerText()).includes('1 étape sur 3'));
  await p.locator('.ps-next').getByRole('button').click(); await p.waitForTimeout(1800);
  step('le bouton de l’étape suivante ouvre le calendrier', await p.getByRole('tab', {name: 'Calendrier', exact: true}).getAttribute('aria-selected') === 'true');
  await p.screenshot({path: `${OUT}/2_calendar_proposed.png`, fullPage: true});
  for (let i = 0; i < 2; i++) {
    const card = p.locator('.pc-card').nth(i);
    await card.getByRole('button', {name: 'Enregistrer ces dates'}).click(); await p.waitForTimeout(1500);
    await card.getByRole('button', {name: 'Valider le calendrier'}).click(); await p.waitForTimeout(1500);
  }
  step('deux calendriers enregistrés puis validés', await p.locator('.pc-status.pc-ok').count() === 2);
  await p.locator('.pc-card').nth(0).getByRole('button', {name: 'Clôturer la saisie'}).first().click().catch(() => {}); await p.waitForTimeout(1500);
  step('clôturer la saisie d’une période en cours', (await toast(p)).includes('saisie clôturée') || await p.getByText('Saisie clôturée').count() > 0);
  await p.screenshot({path: `${OUT}/3_calendar_validated.png`, fullPage: true});
  await tab(p, 'Programmes'); await p.screenshot({path: `${OUT}/4_programmes_before.png`, fullPage: true});
  await p.getByRole('button', {name: /Utiliser les \d+ programmes officiels/}).click(); await p.waitForTimeout(3000);
  step('un clic : programmes officiels en service', /programmes? officiels? en service/.test(await toast(p)), await toast(p));
  await p.screenshot({path: `${OUT}/5_programmes_after.png`, fullPage: true});
  await p.locator('.pp-list li').filter({hasText: '1CG'}).getByRole('button', {name: 'Voir'}).click(); await p.waitForTimeout(2000);
  await p.screenshot({path: `${OUT}/6_editor_in_use.png`});
  await p.getByRole('button', {name: 'Créer une nouvelle version'}).click(); await p.waitForTimeout(2000);
  const droit = p.locator('.pp-lines li').filter({hasText: 'Droit'}).first();
  await droit.locator('input[type=number]').first().fill('20'); await p.waitForTimeout(300);
  await p.screenshot({path: `${OUT}/7_editor_editing.png`});
  await droit.getByRole('button', {name: 'Enregistrer'}).click(); await p.waitForTimeout(1500);
  step('Droit : 20 points → examen 40, marqué « Modifié »', (await droit.innerText()).includes('Modifié'));
  await p.getByPlaceholder(/Ajouter un cours/).fill('Infor'); await p.waitForTimeout(1200);
  const pick = p.locator('.pp-results button').first(); const picked = await pick.innerText().catch(() => '');
  await pick.click(); await p.waitForTimeout(400);
  await p.getByRole('button', {name: 'Ajouter ce cours'}).click(); await p.waitForTimeout(1500);
  step('ajouter un cours par la recherche', picked && (await p.locator('.pp-lines li').last().innerText()).includes('Ajout de l’école'), picked);
  await p.screenshot({path: `${OUT}/8_editor_added.png`, fullPage: false});
  await p.getByRole('button', {name: 'Valider ce programme'}).click(); await p.waitForTimeout(2000);
  step('valider la nouvelle version', (await toast(p)).includes('validé'), await toast(p));
  await p.keyboard.press('Escape'); await p.waitForTimeout(800);
  await tab(p, 'Étapes'); await p.screenshot({path: `${OUT}/9_steps_done.png`, fullPage: true});
  const step3 = await p.locator('.ps-steps li').nth(2).innerText();     // 3 maternelle classes: no official programme
  step('étape 3 : explique les classes sans programme officiel et propose de les construire', step3.includes('pas de programme officiel') && step3.includes('Construire 3 programmes'), step3.replace(/\s+/g, ' '));
  R['1280'] = {steps: await measure(p)};
  await ctx.close();
  for (const [W, H] of SIZES) {
    const {ctx, p} = await open(b, W, H); const k = `${W}x${H}`; R[k] = {};
    for (const [name, file] of [['Étapes', 'steps'], ['Calendrier', 'calendar'], ['Programmes', 'programmes']]) {
      await tab(p, name); R[k][file] = await measure(p); await p.screenshot({path: `${OUT}/${file}_${k}.png`, fullPage: W < 800});
    }
    await p.locator('.pp-list li').filter({hasText: '1CG'}).getByRole('button', {name: 'Voir'}).click(); await p.waitForTimeout(2000);
    await p.getByRole('button', {name: 'Créer une nouvelle version'}).click(); await p.waitForTimeout(2000);
    R[k].editor = await measure(p, '[role=dialog]'); await p.screenshot({path: `${OUT}/editor_${k}.png`});
    await p.getByRole('button', {name: 'Abandonner le brouillon'}).click(); await p.getByRole('button', {name: 'Oui, abandonner'}).click(); await p.waitForTimeout(1500);
    await ctx.close();
  }
} finally { await b.close(); }
console.log(JSON.stringify(R, null, 1));
