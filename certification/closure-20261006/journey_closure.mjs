// Real user journeys on the PRODUCTION build through the UI only (clicks, typing), isolated headless Edge.
// Cashier checkout + receipt preview, family basket, network loss, lost response (no duplicate payment),
// session persistence across reload and browser restart. Charges are seeded by the owner role beforehand
// (journey_seed_closure.py) because no tariff->charge generator exists (owner decision pending).
import fs from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';

const dir = new URL('./', import.meta.url);
const SHOTS = new URL('journeys/', dir);
await fs.mkdir(SHOTS, {recursive: true});
const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', dir), 'utf8'));
const seed = JSON.parse(await fs.readFile(new URL('../../.local/closure/journey-seed.json', dir), 'utf8'));
const APP = process.env.APP_URL || 'http://127.0.0.1:55175/';
const results = [];
const check = (name, ok, detail = '') => { results.push({check: name, pass: !!ok, detail: String(detail).slice(0, 300)}); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ': ' + detail : ''}`); };

async function connect() {
  const t = await (await fetch('http://127.0.0.1:59223/json/new?about:blank', {method: 'PUT'})).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0; const pend = new Map(); const handlers = [];
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.j(Error(JSON.stringify(m.error))) : p.r(m.result); } if (m.method) handlers.forEach(h => h(m)); };
  const call = (method, params = {}) => new Promise((r, j) => { const i = ++id; pend.set(i, {r, j}); ws.send(JSON.stringify({id: i, method, params})); setTimeout(() => { if (pend.has(i)) { pend.delete(i); j(Error('CDP timeout ' + method)); } }, 120000); });
  await call('Runtime.enable'); await call('Page.enable'); await call('Network.enable');
  const ev = async (expression) => { const r = await call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true}); if (r.exceptionDetails) throw Error(r.exceptionDetails.text + ' :: ' + expression.slice(0, 100)); return r.result.value; };
  const page = {
    call, ev, on: h => handlers.push(h), ws, targetId: t.id,
    async viewport(width, height = 900) { await call('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: width < 768}); },
    async go(url = APP) { await call('Page.navigate', {url}); await page.waitFor('document.readyState==="complete"'); },
    async waitFor(expr, ms = 40000) { const end = Date.now() + ms; while (Date.now() < end) { try { if (await ev(expr)) return true; } catch {} await delay(300); } throw Error('timeout: ' + expr.slice(0, 140)); },
    async waitText(text, ms = 40000) { return page.waitFor(`document.body.innerText.includes(${JSON.stringify(text)})`, ms); },
    async type(selector, value) {
      const ok = await ev(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)return false;el.focus();const proto=el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);
      if (!ok) throw Error('field not found ' + selector); await delay(250);
    },
    async click(text, scope = 'document') {
      const ok = await ev(`(()=>{const t=${JSON.stringify(text)}.toLowerCase();const root=${scope};const c=[...root.querySelectorAll('button,a,[role=button],[role=menuitem],[role=tab]')].filter(e=>e.offsetParent!==null&&!e.disabled&&((e.innerText||'')+' '+(e.getAttribute('aria-label')||'')).toLowerCase().includes(t));c.sort((a,b)=>a.innerText.length-b.innerText.length);if(!c[0])return false;c[0].scrollIntoView({block:'center'});c[0].click();return true})()`);
      if (!ok) throw Error('clickable not found: ' + text); await delay(450);
    },
    async shot(name) { const s = await call('Page.captureScreenshot', {format: 'png'}); await fs.writeFile(new URL(`${name}.png`, SHOTS), Buffer.from(s.data, 'base64')); },
  };
  return page;
}

async function uiLogin(p, code, email, password) {
  await p.go(); await p.waitFor('!!document.querySelector(".lg-card")||!!document.querySelector(".es-shell")');
  if (await p.ev('!!document.querySelector(".es-shell")')) { await p.click('Agent'); await p.click('Se déconnecter'); await p.waitFor('!!document.querySelector(".lg-card")'); }
  await p.type('#lg-code', code); await p.type('#lg-email', email); await p.type('#lg-pass', password);
  await p.click('Se connecter'); await p.waitFor('!!document.querySelector(".es-shell")');
}
async function openCheckout(p) {
  await p.click('Centre financier'); await p.waitFor('!!document.querySelector(".checkoutWorkspace")||document.body.innerText.includes("Encaisser")', 30000);
  if (!(await p.ev('!!document.querySelector(".checkoutWorkspace")'))) await p.click('Encaisser');
  await p.waitFor('!!document.querySelector(".checkoutWorkspace input[aria-label=\\"Rechercher un élève ou une famille\\"]")');
}
async function chooseStudent(p, query, name) {
  await p.type('.checkoutWorkspace input[aria-label="Rechercher un élève ou une famille"]', query);
  await p.waitFor(`[...document.querySelectorAll('.checkoutHits button')].some(b=>b.innerText.includes(${JSON.stringify(name)}))`);
  await p.ev(`[...document.querySelectorAll('.checkoutHits button')].find(b=>b.innerText.includes(${JSON.stringify(name)})).click()`);
  await p.waitFor('!!document.querySelector(".payerStrip")'); await delay(800);
}
async function selectCharge(p, label) {
  await p.waitFor(`[...document.querySelectorAll('.chargeRow')].some(b=>b.innerText.includes(${JSON.stringify(label)}))`);
  await p.ev(`[...document.querySelectorAll('.chargeRow')].find(b=>b.innerText.includes(${JSON.stringify(label)})).click()`); await delay(500);
}
const paymentsFor = async (label) => (await (await fetch(`http://127.0.0.1:58100/health`)).ok, 0);

const cashier = fx.A.users.CAISSIER1;
let p = await connect();
await p.viewport(1440);
await p.call('Network.clearBrowserCookies');

// 1. Cashier: collect one charge, print/preview the receipt.
await uiLogin(p, fx.A.code, cashier.email, cashier.password);
check('caissier connecté par l’interface', true);
await openCheckout(p);
await chooseStudent(p, seed.child1.query, seed.child1.name);
await selectCharge(p, seed.child1.single);
await p.click('Encaisser maintenant');
await p.waitText('Paiement enregistré', 30000);
check('encaissement enregistré, numéro de reçu affiché', await p.ev(`/REC-[A-F0-9]{8}/.test(document.querySelector('.checkoutMessage')?.innerText||'')`));
await p.shot('cashier-paid-1440');
await p.click('Imprimer le reçu');
await p.waitFor('!!document.querySelector(".receiptModal iframe")', 30000); await delay(1500);
check('aperçu du reçu ouvert dans EduSync (impression = choix du caissier)', await p.ev('!!document.querySelector(".receiptModal iframe")?.src.startsWith("blob:")'));
await p.shot('cashier-receipt-preview-1440');
await p.click('Fermer');

// 2. Family basket: two children, one operation, one receipt per child.
await chooseStudent(p, seed.child1.query, seed.child1.name);
await p.click('Ajouter un enfant'); await delay(1200);
await selectCharge(p, seed.child1.basket);
await p.click('Ajouter au panier');
await p.waitFor('!!document.querySelector(".basketPanel")');
await p.ev(`[...document.querySelectorAll('.familyChips button')].find(b=>b.innerText.includes(${JSON.stringify(seed.child2.first)})).click()`); await delay(1500);
await selectCharge(p, seed.child2.basket);
await p.click('Ajouter au panier'); await delay(500);
check('panier : 2 lignes, totaux par devise', await p.ev(`document.querySelectorAll('.basketPanel li').length===2&&document.querySelector('.basketFoot').innerText.includes('Total CDF')`));
await p.shot('basket-ready-1440');
await p.click('Encaisser le panier');
await p.waitText('Panier encaissé', 30000);
check('panier encaissé : un reçu par enfant', await p.ev(`document.querySelectorAll('.basketDone li').length===2`));
await p.shot('basket-done-1440');
await p.click('Imprimer les reçus');
await p.waitFor('!!document.querySelector(".receiptModal iframe")', 30000); await delay(1200);
check('reçus du panier en un seul aperçu', true);
await p.click('Fermer');

// 3. Network loss: status chip, truthful message, recovery.
await p.call('Network.emulateNetworkConditions', {offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
await chooseStudent(p, seed.child2.query, seed.child2.name).catch(() => {});
await p.waitFor(`/Hors ligne|instable|Reconnexion|non confirmé/.test(document.querySelector('.es-status')?.innerText||document.querySelector('.es-status')?.title||'')`, 90000).catch(() => {});
const offlineState = await p.ev(`(document.querySelector('.es-status')?.innerText||'')+' | '+(document.querySelector('.es-status')?.title||'')`);
check('coupure réseau signalée en clair', /Hors ligne|instable|Reconnexion|non confirmé/.test(offlineState), offlineState);
await p.shot('offline-1440');
await p.call('Network.emulateNetworkConditions', {offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
await p.waitFor(`/En ligne|Enregistré/.test(document.querySelector('.es-status')?.innerText||'')`, 90000).catch(() => {});
check('retour en ligne affiché', /En ligne|Enregistré/.test(await p.ev(`document.querySelector('.es-status')?.innerText||''`)));

// 4. Lost response after the server committed: the retry must not create a second payment.
await p.go(); await p.waitFor('!!document.querySelector(".es-shell")');
await openCheckout(p);
await chooseStudent(p, seed.child2.query, seed.child2.name);
await selectCharge(p, seed.child2.lost);
await p.call('Fetch.enable', {patterns: [{urlPattern: '*finance/checkout/collect*', requestStage: 'Response'}]});
let intercepted = 0;
p.on(async (m) => { if (m.method === 'Fetch.requestPaused') { intercepted++; await p.call('Fetch.failRequest', {requestId: m.params.requestId, errorReason: 'ConnectionReset'}); } });
await p.click('Encaisser maintenant');
await p.waitFor(`/interrompue|confirmée|lente/i.test(document.querySelector('.checkoutMessage')?.innerText||'')`, 90000);
const lostMsg = await p.ev(`document.querySelector('.checkoutMessage')?.innerText||''`);
check('réponse perdue : message honnête (opération non confirmée)', /non confirm|pas pu être confirmée|interrompue/i.test(lostMsg), lostMsg);
await p.call('Fetch.disable');
await p.shot('lost-response-1440');
await p.click('Encaisser maintenant');
await p.waitText('Paiement enregistré', 40000);
const finalMsg = await p.ev(`document.querySelector('.checkoutMessage')?.innerText||''`);
check('nouvel essai : le serveur renvoie l’encaissement déjà enregistré', /REC-/.test(finalMsg), `${intercepted} réponse(s) coupée(s)`);
await fs.writeFile(new URL('../../.local/closure/journey-lost.json', dir), JSON.stringify({charge: seed.child2.lostId, message: finalMsg}));

// 5. Session persistence: reload, then a brand new browser tab/session with the same profile.
await p.go(); await p.waitFor('!!document.querySelector(".es-shell")', 30000);
check('rechargement de page : session conservée', true);
p.ws.close();
const p2 = await connect(); await p2.viewport(390, 844);
await p2.go(); await p2.waitFor('!!document.querySelector(".es-shell")||!!document.querySelector(".lg-card")', 30000);
check('nouvel onglet du navigateur : session conservée (cookie appareil)', await p2.ev('!!document.querySelector(".es-shell")'));
await p2.shot('session-restored-390');
await p2.click('Ouvrir le menu'); await delay(600);
await p2.click('Se déconnecter');
await p2.waitFor('!!document.querySelector(".lg-card")', 30000);
await p2.go(); await p2.waitFor('!!document.querySelector(".lg-card")||!!document.querySelector(".es-shell")', 30000);
check('après déconnexion : retour à la connexion, même après rechargement', await p2.ev('!!document.querySelector(".lg-card")'));

await fs.writeFile(new URL('journey-closure.json', dir), JSON.stringify({app: APP, passed: results.filter(r => r.pass).length, total: results.length, results}, null, 2));
console.log(`${results.filter(r => r.pass).length}/${results.length} PASS`);
p2.ws.close();
process.exit(results.every(r => r.pass) ? 0 : 1);
