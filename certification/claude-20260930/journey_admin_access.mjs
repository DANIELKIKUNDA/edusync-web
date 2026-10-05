// Journey 5 — the school's access manager adapts a standard role and grants it, entirely through "Accès & rôles".
import fs from 'node:fs/promises';
import {open, uiLogin} from './ui.mjs';
const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', import.meta.url), 'utf8'));
const C = fx.C, admin = C.users.ADMIN, member = C.users.C_MEMBER;
const tag = Math.random().toString(36).slice(2, 6).toUpperCase();
const roleName = `Gestionnaire sans sortie ${tag}`;
const memberName = 'Agent C_MEMBER';
const results = [];
const page = await open();
const step = async (name, fn) => {
  const t = Date.now();
  try { await fn(); results.push({step: name, pass: true, ms: Date.now() - t}); console.log(`PASS ${name} (${Date.now() - t} ms)`); }
  catch (e) { results.push({step: name, pass: false, error: e.message}); console.log(`FAIL ${name}: ${e.message}`); await page.shot('admin-FAIL'); console.log('CONTROLS', JSON.stringify(await page.visibleControls()).slice(-1500)); throw e; }
};
const memberRow = (expr) => page.ev(`(()=>{const r=[...document.querySelectorAll('.memberRow')].find(x=>x.innerText.includes(${JSON.stringify(memberName)}));return ${expr}})()`);
await page.viewport(1366, 768);
try {
  await step('log in as the school access manager', () => uiLogin(page, {code: C.code, email: admin.email, password: admin.password}));
  await step('open Accès & rôles', async () => { await page.click('Accès & rôles', {within: '.smartNav'}); await page.settle(); await page.waitFor(`/garde-fous actifs/i.test(document.body.innerText)`, 60000); await page.waitFor(`!!document.querySelector('.memberRow')`, 60000); await page.shot('admin-1-members'); });
  await step('own row is locked (no self-service)', async () => {
    const meLocked = await page.ev(`(()=>{const r=[...document.querySelectorAll('.memberRow')].find(x=>x.querySelector('.meBadge'));return !!(r&&r.querySelector('.selfLock')&&![...r.querySelectorAll('button')].some(b=>/Attribuer/.test(b.innerText)))})()`);
    if (!meLocked) throw Error('own row is not locked');
  });
  await step('clone the standard Gestionnaire role', async () => {
    await page.click('Rôles', {within: '.personTabs'}); await page.waitFor(`!!document.querySelector('.roleCard')`, 30000);
    const ok = await page.ev(`(()=>{const c=[...document.querySelectorAll('.roleCard')].find(x=>x.querySelector('h4')?.innerText.trim()==='Gestionnaire');const b=c&&[...c.querySelectorAll('button')].find(b=>/Cloner/.test(b.innerText));if(!b)return false;b.click();return true})()`);
    if (!ok) throw Error('clone button not found on the Gestionnaire card');
    await page.waitFor(`!!document.querySelector('.roleSheet')`, 15000);
  });
  await step('remove "record a departure" and name the role', async () => {
    await page.ev(`(()=>{const i=document.querySelector('.roleSheet input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,${JSON.stringify(roleName)});i.dispatchEvent(new Event('input',{bubbles:true}));return true})()`);
    await page.fill('Rechercher une permission', 'sortie d’un agent');
    const ok = await page.ev(`(()=>{const row=[...document.querySelectorAll('.capRow')].find(r=>/sortie d.un agent/i.test(r.innerText));const cb=row&&row.querySelector('input[type=checkbox]');if(!cb||!cb.checked)return false;cb.click();return !cb.checked})()`);
    if (!ok) throw Error('could not untick the departure permission');
    await page.waitFor(`/−1/.test(document.querySelector('.sheetSummary')?.innerText||'')`, 5000);
    await page.shot('admin-2-editor');
    await page.click('Créer le rôle');
    await page.waitFor(`!document.querySelector('.roleSheet') && [...document.querySelectorAll('.roleCard h4')].some(h=>h.innerText.includes(${JSON.stringify(roleName)}))`, 30000);
  });
  await step('grant the new role to a member for one month', async () => {
    await page.click('Membres', {within: '.personTabs'}); await page.waitFor(`!!document.querySelector('.memberRow')`, 30000);
    const ok = await memberRow(`(()=>{const b=r&&[...r.querySelectorAll('button')].find(b=>/Attribuer/.test(b.innerText));if(!b)return false;b.click();return true})()`);
    if (!ok) throw Error('Attribuer not found for the member');
    await page.waitFor(`!!document.querySelector('.assignDialog')`, 10000);
    const set = await page.ev(`(()=>{const s=document.querySelector('.assignDialog select');const o=[...s.options].find(o=>o.text.includes(${JSON.stringify(roleName)}));if(!o)return false;Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(s,o.value);s.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);
    if (!set) throw Error('role not offered in the assign dialog');
    await page.click('1 mois', {within: '.assignDialog'});
    await page.ev(`(()=>{const t=document.querySelector('.assignDialog textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(t,'Remplacement pendant le congé du gestionnaire');t.dispatchEvent(new Event('input',{bubbles:true}));return true})()`);
    await page.waitText('Expire automatiquement', 5000);
    await page.shot('admin-3-assign');
    await page.ev(`(()=>{const b=[...document.querySelectorAll('.assignDialog .modalActions button')].find(b=>b.innerText.trim()==='Attribuer');b.click();return true})()`);
    await page.waitFor(`!document.querySelector('.assignDialog')`, 30000);
    await page.waitFor(`(()=>{const r=[...document.querySelectorAll('.memberRow')].find(x=>x.innerText.includes(${JSON.stringify(memberName)}));return r&&r.innerText.includes(${JSON.stringify(roleName)})&&!!r.querySelector('.untilPill')})()`, 30000);
    await page.shot('admin-4-granted');
  });
  await step('revoke it with a reason (immediate)', async () => {
    const ok = await memberRow(`(()=>{const chip=r&&[...r.querySelectorAll('.roleChip')].find(c=>c.innerText.includes(${JSON.stringify(roleName)}));const x=chip&&chip.querySelector('.chipX');if(!x)return false;x.click();return true})()`);
    if (!ok) throw Error('remove button not found on the chip');
    await page.waitFor(`!!document.querySelector('[role=alertdialog] textarea')`, 10000);
    await page.ev(`(()=>{const t=document.querySelector('[role=alertdialog] textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(t,'Retour du gestionnaire titulaire');t.dispatchEvent(new Event('input',{bubbles:true}));return true})()`);
    await page.click('Retirer le rôle');
    await page.waitFor(`(()=>{const r=[...document.querySelectorAll('.memberRow')].find(x=>x.innerText.includes(${JSON.stringify(memberName)}));return r&&!r.innerText.includes(${JSON.stringify(roleName)})})()`, 30000);
  });
  await step('rights journal shows creation, grant and revocation with reasons', async () => {
    await page.click('Journal des droits', {within: '.personTabs'}); await page.settle();
    const ok = await page.ev(`(()=>{const t=document.body.innerText;return t.includes('Rôle créé')&&t.includes('Rôle attribué')&&t.includes('Rôle retiré')&&t.includes('Retour du gestionnaire titulaire')})()`);
    await page.shot('admin-5-journal');
    if (!ok) throw Error('journal incomplete');
  });
  await step('no JavaScript error, no server error', async () => {
    const http = page.http.filter(h => !h.includes('/auth/refresh'));
    if (page.errors.length || http.some(h => h.startsWith('5'))) throw Error(JSON.stringify({errors: page.errors, http}));
  });
} catch { /* recorded */ } finally { await page.close(); }
await fs.writeFile(new URL('journey-admin-access.json', import.meta.url), JSON.stringify(results, null, 2));
console.log(`== ${results.filter(r => r.pass).length}/${results.length} steps PASS`);
