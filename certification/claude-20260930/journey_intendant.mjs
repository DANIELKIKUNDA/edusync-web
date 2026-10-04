// Journey 4 — the Intendant manages consumables end-to-end through the real UI only.
import fs from 'node:fs/promises';
import {open, uiLogin} from './ui.mjs';
const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', import.meta.url), 'utf8'));
const A = fx.A, u = A.users.UI_INT;
const tag = Math.random().toString(36).slice(2, 6).toUpperCase();
const label = `Papier A4 ${tag}`;
const results = [];
const page = await open();
const step = async (name, fn) => {
  const t = Date.now();
  try { await fn(); results.push({step: name, pass: true, ms: Date.now() - t}); console.log(`PASS ${name} (${Date.now() - t} ms)`); }
  catch (e) { results.push({step: name, pass: false, error: e.message}); console.log(`FAIL ${name}: ${e.message}`); await page.shot('int-FAIL'); console.log('CONTROLS', JSON.stringify(await page.visibleControls()).slice(-1400)); throw e; }
};
const qtyOf = () => page.ev(`(()=>{const r=[...document.querySelectorAll('.stockRow')].find(x=>x.innerText.includes(${JSON.stringify(label)}));return r?Number(r.querySelector('.stockQty b').innerText.replace(/[^0-9,.-]/g,'').replace(',','.')):-1})()`);
const rowButton = (txt) => page.ev(`(()=>{const r=[...document.querySelectorAll('.stockRow')].find(x=>x.innerText.includes(${JSON.stringify(label)}));const b=r&&[...r.querySelectorAll('button')].find(b=>b.innerText.trim()===${JSON.stringify(txt)});if(!b||b.disabled)return false;b.click();return true})()`);
await page.viewport(1366, 768);
try {
  await step('log in through the form', () => uiLogin(page, {code: A.code, email: u.email, password: u.password}));
  await step('open Intendance', async () => { await page.click('Intendance', {within: '.smartNav'}); await page.settle(); await page.waitText('Nouvel article', 60000); });
  await step('create a consumable item', async () => {
    await page.click('Nouvel article');
    await page.fill('Code article', `PAP-${tag}`); await page.fill('Désignation', label); await page.fill('Unité', 'rame'); await page.fill('Seuil', '10');
    await page.shot('int-1-item'); await page.click('Créer l’article');
    await page.waitFor(`[...document.querySelectorAll('.stockRow')].some(x=>x.innerText.includes(${JSON.stringify(label)}))`, 30000);
    if (await qtyOf() !== 0) throw Error('new item must start at 0');
  });
  await step('record a receipt of 50', async () => {
    if (!await rowButton('Entrée')) throw Error('no Entrée button');
    await page.fill('Quantité', '50'); await page.fill('Motif', 'Livraison fournisseur');
    await page.shot('int-2-receipt'); await page.click('Enregistrer');
    await page.waitFor(`(()=>{const r=[...document.querySelectorAll('.stockRow')].find(x=>x.innerText.includes(${JSON.stringify(label)}));return r&&/50/.test(r.querySelector('.stockQty b').innerText)})()`, 30000);
  });
  await step('record an issue of 12 to a destination', async () => {
    if (!await rowButton('Sortie')) throw Error('no Sortie button');
    await page.fill('Quantité', '12'); await page.fill('Destination', 'Classes de 1re année'); await page.fill('Motif', 'Distribution aux enseignants');
    await page.click('Enregistrer');
    await page.waitFor(`(()=>{const r=[...document.querySelectorAll('.stockRow')].find(x=>x.innerText.includes(${JSON.stringify(label)}));return r&&/38/.test(r.querySelector('.stockQty b').innerText)})()`, 30000);
  });
  await step('an impossible issue (more than in stock) is blocked on screen', async () => {
    if (!await rowButton('Sortie')) throw Error('no Sortie button');
    await page.fill('Quantité', '1000'); await page.fill('Motif', 'Essai de dépassement');
    const blocked = await page.ev(`document.body.innerText.includes('le stock ne peut pas devenir négatif') && [...document.querySelectorAll('.modalActions button')].find(b=>b.innerText.trim()==='Enregistrer').disabled`);
    await page.shot('int-3-blocked');
    if (!blocked) throw Error('negative stock not blocked');
    await page.click('Annuler');
  });
  await step('physical inventory: count, justify the variance, validate', async () => {
    await page.click('Nouvel inventaire');
    await page.waitFor(`!!document.querySelector('.countSheet')`, 30000);
    await page.fill(`Quantité comptée — ${label}`, '37');
    const needs = await page.ev(`document.body.innerText.includes('Justifiez chaque écart')`);
    if (!needs) throw Error('variance justification not required');
    await page.fill(`Justification — ${label}`, '1 rame abîmée par l’humidité');
    await page.shot('int-4-count');
    await page.click('Valider l’inventaire'); await page.click('Confirmer la validation');
    await page.waitFor(`!document.querySelector('.countSheet')`, 30000);
    await page.click('Consommables'); await page.settle();
    await page.waitFor(`(()=>{const r=[...document.querySelectorAll('.stockRow')].find(x=>x.innerText.includes(${JSON.stringify(label)}));return r&&/37/.test(r.querySelector('.stockQty b').innerText)})()`, 30000);
  });
  await step('movement history shows receipt, issue and inventory variance in French', async () => {
    await page.click('Entrées & sorties'); await page.settle();
    const ok = await page.ev(`(()=>{const t=document.body.innerText;return t.includes('Écart d’inventaire')&&t.includes('Entrée')&&t.includes('Sortie')&&!/\\b(RECEIPT|ISSUE|COUNT_ADJUSTMENT|CONSUMABLE)\\b/.test(t)})()`);
    await page.shot('int-5-movements');
    if (!ok) throw Error('movement labels missing or raw codes visible');
  });
  await step('no JavaScript error, no server error', async () => {
    const http = page.http.filter(h => !h.includes('/auth/refresh'));
    if (page.errors.length || http.some(h => h.startsWith('5'))) throw Error(JSON.stringify({errors: page.errors, http}));
  });
} catch { /* recorded */ } finally { await page.close(); }
await fs.writeFile(new URL('journey-intendant.json', import.meta.url), JSON.stringify(results, null, 2));
console.log(`== ${results.filter(r => r.pass).length}/${results.length} steps PASS`);
