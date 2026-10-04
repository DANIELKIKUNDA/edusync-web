// Journey 1 — the cashier collects school fees for a family, through the real UI only (desktop + phone).
import fs from 'node:fs/promises';
import {open, uiLogin} from './ui.mjs';
const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', import.meta.url), 'utf8'));
const A = fx.A, u = A.users.UI_CASH;
const results = [];
async function journey(label, width) {
  const page = await open();
  const step = async (name, fn) => {
    const t = Date.now();
    try { await fn(); results.push({journey: label, step: name, pass: true, ms: Date.now() - t}); console.log(`PASS [${label}] ${name} (${Date.now() - t} ms)`); }
    catch (e) { results.push({journey: label, step: name, pass: false, error: e.message}); console.log(`FAIL [${label}] ${name}: ${e.message}`); await page.shot(`cashier-${label}-FAIL`); throw e; }
  };
  await page.viewport(width, width < 768 ? 844 : 768);
  try {
    await step('log in through the form', () => uiLogin(page, {code: A.code, email: u.email, password: u.password}));
    const toFinance = async () => {
      if (width < 768) { await page.click('Finance', {within: '.mobileBottomNav'}); } else { await page.click('Centre financier', {within: '.smartNav'}); }
      await page.settle();
    };
    await step('open the Finance centre', toFinance);
    await step('open my cash desk (or find it open)', async () => {
      await page.click('Caisse'); await page.settle();
      if (await page.ev(`document.body.innerText.includes('Ouvrir ma caisse')`)) { await page.click('Ouvrir ma caisse'); }
      await page.waitFor(`!document.body.innerText.includes('Ouvrir ma caisse')`, 30000);
      await page.shot(`cashier-${label}-1-cash-open`);
    });
    await step('search the pupil (instant search)', async () => {
      await page.click('Encaissement'); await page.settle();
      await page.fill('Nom, matricule', 'ELEVEA POST1');
      await page.waitText('ELV-00001', 20000);
      await page.shot(`cashier-${label}-2-search`);
    });
    let before = 0;
    await step('select the pupil and see what is owed', async () => {
      await page.click('ELEVEA POST1 Un1');
      await page.waitFor(`[...document.querySelectorAll('button')].some(b=>b.innerText.includes('Frais de parcours UI')&&/Reste/.test(b.innerText))`, 45000);
      before = await page.ev(`(()=>{const row=[...document.querySelectorAll('button')].find(b=>b.innerText.includes('Frais de parcours UI'));const m=row&&row.innerText.match(/Reste\\s*([\\d\\s\\u202f\\u00a0]+)\\s*CDF/);return m?Number(m[1].replace(/\\D/g,'')):-1})()`);
      if (!(before > 0)) throw Error('no remaining amount displayed');
    });
    await step('select the due fee and type the amount handed over', async () => {
      await page.click('Frais de parcours UI');
      await page.fill('Montant remis', '5000');
      await page.waitFor(`/1 frais sélectionné/.test(document.body.innerText) || /Obligations sélectionnées\\s*[1-9]/.test(document.body.innerText)`, 10000);
      await page.shot(`cashier-${label}-3-ready`);
      const overflow = await page.ev(`(()=>{const i=document.getElementById('checkoutAmount');const c=i.closest('.advancePanel')||i.parentElement;return Math.round(i.getBoundingClientRect().right-c.getBoundingClientRect().right)})()`);
      if (overflow > 1) throw Error(`amount field overflows its card by ${overflow}px`);
    });
    await step('collect and get a receipt', async () => {
      await page.click('Encaisser maintenant');
      await page.waitFor(`/REC-[0-9A-F]{8}/.test(document.body.innerText)`, 30000);
      await page.shot(`cashier-${label}-4-receipt`);
    });
    await step('remaining amount updated on screen', async () => {
      const after = await page.ev(`(()=>{const row=[...document.querySelectorAll('button')].find(b=>b.innerText.includes('Frais de parcours UI'));const m=row&&row.innerText.match(/Reste\\s*([\\d\\s\\u202f\\u00a0]+)\\s*CDF/);return m?Number(m[1].replace(/\\D/g,'')):-1})()`);
      if (after !== -1 && after !== before - 5000) throw Error(`remaining ${before} -> ${after}, expected ${before - 5000}`);
    });
    await step('no JavaScript error, no server error', async () => {
      const http = page.http.filter(h => !h.includes('/auth/refresh'));
      if (page.errors.length || http.some(h => h.startsWith('5'))) throw Error(JSON.stringify({errors: page.errors, http}));
    });
  } catch { /* recorded */ } finally { await page.close(); }
}
await journey('desktop', 1366);
await journey('phone', 390);
await fs.writeFile(new URL('journey-cashier.json', import.meta.url), JSON.stringify(results, null, 2));
console.log(`== ${results.filter(r => r.pass).length}/${results.length} steps PASS`);
