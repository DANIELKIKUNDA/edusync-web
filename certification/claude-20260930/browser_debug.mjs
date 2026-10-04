// Minimal CDP sanity check: open the production preview, report timings, save one screenshot.
import fs from 'node:fs/promises';
const t0 = Date.now(); const ms = () => `${Date.now() - t0}ms`;
const targets = await (await fetch('http://127.0.0.1:59223/json')).json();
console.log('targets', targets.map(t => `${t.type}:${t.url}`).join(' | '));
let target = targets.find(x => x.type === 'page');
if (!target) target = await (await fetch('http://127.0.0.1:59223/json/new?about:blank', {method: 'PUT'})).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let id = 0; const pend = new Map();
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
const call = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({id: i, method, params})); });
await call('Page.enable');
console.log('1+1 =', (await call('Runtime.evaluate', {expression: '1+1', returnByValue: true})).result?.result?.value, ms());
await call('Page.navigate', {url: 'http://127.0.0.1:55175/'});
for (let i = 0; i < 60; i++) {
  const s = (await call('Runtime.evaluate', {expression: 'document.readyState+"|"+document.title+"|"+document.body?.innerText?.slice(0,80)', returnByValue: true})).result?.result?.value;
  if (i % 5 === 0 || String(s).startsWith('complete')) console.log('state', s, ms());
  if (String(s).startsWith('complete')) break;
  await new Promise(r => setTimeout(r, 1000));
}
const shot = await call('Page.captureScreenshot', {format: 'png'});
await fs.writeFile(new URL('screens/debug-login.png', import.meta.url), Buffer.from(shot.result.data, 'base64'));
console.log('screenshot saved', ms()); ws.close();
