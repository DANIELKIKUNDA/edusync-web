// Journey 2 — enrolling a new family with one child, through the real UI only (cashier = enrollment operator).
import fs from 'node:fs/promises';
import {open, uiLogin} from './ui.mjs';
const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', import.meta.url), 'utf8'));
const A = fx.A, u = A.users.UI_CASH;
const tag = Math.random().toString(36).slice(2, 7).toUpperCase();
const child = {nom: `PARCOURS${tag}`, postnom: 'UI', prenom: 'Grace'};
const results = [];
const page = await open();
const step = async (name, fn) => {
  const t = Date.now();
  try { await fn(); results.push({step: name, pass: true, ms: Date.now() - t}); console.log(`PASS ${name} (${Date.now() - t} ms)`); }
  catch (e) { results.push({step: name, pass: false, error: e.message}); console.log(`FAIL ${name}: ${e.message}`); await page.shot('enroll-FAIL'); console.log('CONTROLS', JSON.stringify(await page.visibleControls()).slice(0, 1500)); throw e; }
};
await page.viewport(1366, 768);
try {
  await step('log in through the form', () => uiLogin(page, {code: A.code, email: u.email, password: u.password}));
  await step('open Pupils & enrollment', async () => { await page.click('Élèves & inscriptions', {within: '.smartNav'}); await page.settle(); await page.waitFor(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Élèves enregistrés'));return b&&/^[1-9]/.test(b.innerText.trim())})()`, 90000); });
  await step('start a new enrollment and create a new household', async () => {
    await page.click('Nouvelle inscription'); await page.waitText('Retrouver le foyer');
    await page.click('Créer un nouveau foyer');
    await page.fill('Peut être complété', `PARENT ${tag}`);
    await page.fill('guardian.phone', '+243820000777');
    await page.shot('enroll-1-household');
    await page.click('Continuer'); await page.waitText('Seuls 5 éléments bloquent');
  });
  await step('fill the 5 blocking fields of the child', async () => {
    await page.waitFor(`[...document.querySelectorAll('select')].some(x=>[...x.options].some(o=>o.text.includes('1re année A')))`, 60000);
    await page.fill('children.0.last_name', child.nom);
    await page.fill('children.0.middle_name', child.postnom);
    await page.fill('children.0.first_name', child.prenom);
    await page.ev(`(()=>{const s=[...document.querySelectorAll('select')].find(x=>[...x.options].some(o=>o.text.includes('1re année A')));const o=[...s.options].find(o=>o.text.includes('1re année A'));Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(s,o.value);s.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);
    const optionText = await page.ev(`(()=>{const s=[...document.querySelectorAll('select')].find(x=>[...x.options].some(o=>o.text.includes('1re année A')));return s?s.options[s.selectedIndex].text:''})()`);
    if (optionText.trim().startsWith('·')) throw Error(`class option label incomplete: "${optionText}"`);
    await page.ev(`(()=>{const s=[...document.querySelectorAll('select')].find(x=>[...x.options].some(o=>o.text==='Féminin'));const o=[...s.options].find(o=>o.text==='Féminin');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(s,o.value);s.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);
    await page.shot('enroll-2-child');
  });
  await step('review step', async () => { await page.click('Continuer'); await page.waitFor(`/Vérification/.test(document.body.innerText) && /${child.nom}/.test(document.body.innerText)`, 20000); await page.shot('enroll-3-review'); });
  await step('confirm the enrollment', async () => {
    const label = await page.ev(`(()=>{const b=[...document.querySelectorAll('.wizardBackdrop button, [role=dialog] button, button')].filter(b=>b.offsetParent&&!b.disabled).find(b=>/Confirmer|Inscrire|Valider|Enregistrer/i.test(b.innerText));return b?b.innerText.trim():''})()`);
    if (!label) throw Error('no confirm button');
    await page.click(label);
    await page.waitFor(`!document.body.innerText.includes('Seuls 5 éléments bloquent') && !/INSCRIPTION INTELLIGENTE/.test(document.body.innerText)`, 30000);
    await page.shot('enroll-4-done');
  });
  await step('the child appears in the pupil directory', async () => {
    await page.click('Annuaire élèves'); await page.settle();
    await page.fill('Rechercher', child.nom).catch(() => {});
    await page.waitText(child.nom, 30000);
    await page.shot('enroll-5-directory');
  });
  await step('no JavaScript error, no server error', async () => {
    const http = page.http.filter(h => !h.includes('/auth/refresh'));
    if (page.errors.length || http.length) throw Error(JSON.stringify({errors: page.errors, http}));
  });
} catch { /* recorded */ } finally { await page.close(); }
await fs.writeFile(new URL('journey-enrollment.json', import.meta.url), JSON.stringify(results, null, 2));
console.log(`== ${results.filter(r => r.pass).length}/${results.length} steps PASS`);
