// Journey 3 — the Gestionnaire hires a teacher, then records the teacher's departure (owner decision 2026-10-02).
import fs from 'node:fs/promises';
import {open, uiLogin} from './ui.mjs';
const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', import.meta.url), 'utf8'));
const A = fx.A, u = A.users.UI_GEST;
const tag = Math.random().toString(36).slice(2, 7).toUpperCase();
const emp = `ENS-${tag}`, last = `MUKENDI${tag}`;
const results = [];
const page = await open();
const step = async (name, fn) => {
  const t = Date.now();
  try { await fn(); results.push({step: name, pass: true, ms: Date.now() - t}); console.log(`PASS ${name} (${Date.now() - t} ms)`); }
  catch (e) { results.push({step: name, pass: false, error: e.message}); console.log(`FAIL ${name}: ${e.message}`); await page.shot('gest-FAIL'); console.log('CONTROLS', JSON.stringify(await page.visibleControls()).slice(-1600)); throw e; }
};
await page.viewport(1366, 768);
try {
  await step('log in through the form', () => uiLogin(page, {code: A.code, email: u.email, password: u.password}));
  await step('open Personnel', async () => { await page.click('Personnel', {within: '.smartNav'}); await page.settle(); await page.waitText('Agents enregistrés', 60000); });
  await step('create a teacher record', async () => {
    await page.click('Nouvel agent');
    await page.fill('employee_no', emp);
    await page.fill('last_name', last);
    await page.fill('first_name', 'Esther');
    await page.ev(`(()=>{const s=[...document.querySelectorAll('select')].find(x=>[...x.options].some(o=>o.text==='Enseignant'));const o=[...s.options].find(o=>o.text==='Enseignant');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(s,o.value);s.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);
    await page.fill('phone', '+243810555000');
    await page.shot('gest-1-form');
    await page.click('Créer le dossier');
    await page.waitFor(`!document.body.innerText.includes('Créer le dossier')`, 30000);
  });
  await step('find the new teacher in the directory', async () => {
    await page.click('Annuaire'); await page.settle();
    const search = await page.ev(`!!document.querySelector('.searchBox input')`);
    if (search) await page.fill('Rechercher', last).catch(async () => { await page.ev(`(()=>{const i=document.querySelector('.searchBox input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,${JSON.stringify(last)});i.dispatchEvent(new Event('input',{bubbles:true}));return true})()`); });
    await page.waitText(last, 30000);
    await page.shot('gest-2-directory');
  });
  await step('open the teacher profile', async () => {
    const ok = await page.ev(`(()=>{const row=[...document.querySelectorAll('.personRow')].find(r=>r.innerText.includes(${JSON.stringify(last)}));const b=row&&row.querySelector('button[title="Voir la fiche"]');if(!b)return false;b.click();return true})()`);
    if (!ok) throw Error('open button not found in the row');
    await page.waitFor(`/Sortie|sortie/.test(document.body.innerText) && document.body.innerText.includes(${JSON.stringify(emp)})`, 20000);
    await page.shot('gest-3-profile');
  });
  await step('record the departure with a reason', async () => {
    const label = await page.ev(`(()=>{const b=[...document.querySelectorAll('button')].filter(b=>b.offsetParent&&!b.disabled).find(b=>/sortie/i.test(b.innerText));return b?b.innerText.trim():''})()`);
    if (!label) throw Error('no departure action visible');
    await page.click(label);
    await page.waitFor(`!!document.querySelector('textarea, [role=dialog] input, .accountSecurityDialog input')`, 15000);
    await page.ev(`(()=>{const t=document.querySelector('textarea')||document.querySelector('[role=dialog] input[type=text]');const p=t.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value').set.call(t,'Fin de contrat — parcours de recette');t.dispatchEvent(new Event('input',{bubbles:true}));return true})()`);
    await page.shot('gest-4-exit-dialog');
    const confirm = await page.ev(`(()=>{const b=[...document.querySelectorAll('[role=dialog] button, .wizardBackdrop button, .modalActions button, button')].filter(b=>b.offsetParent&&!b.disabled).find(b=>/confirmer|enregistrer la sortie|valider|sortie/i.test(b.innerText)&&!/annuler/i.test(b.innerText));return b?b.innerText.trim():''})()`);
    if (!confirm) throw Error('no confirmation button');
    await page.click(confirm);
    await page.waitFor(`/Sorti/i.test(document.body.innerText)`, 30000);
    await page.shot('gest-5-left');
  });
  await step('no JavaScript error, no server error', async () => {
    const http = page.http.filter(h => !h.includes('/auth/refresh'));
    if (page.errors.length || http.some(h => h.startsWith('5'))) throw Error(JSON.stringify({errors: page.errors, http}));
  });
} catch { /* recorded */ } finally { await page.close(); }
await fs.writeFile(new URL('journey-gestionnaire.json', import.meta.url), JSON.stringify(results, null, 2));
console.log(`== ${results.filter(r => r.pass).length}/${results.length} steps PASS`);
