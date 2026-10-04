// Authenticated responsive probe on the PRODUCTION build (vite preview), isolated Edge via CDP.
// Adapted from certification/point17-20260916/browser_modules.mjs (Codex) with: two roles, production
// build, mobile touch-target and input font-size checks, token-in-storage check, JS exceptions, API errors.
import fs from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';
const dir = new URL('./', import.meta.url);
const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', dir), 'utf8'));
const APP = process.env.APP_URL || 'http://127.0.0.1:55175/';
const targets = await (await fetch('http://127.0.0.1:59223/json')).json();
const target = targets.find(x => x.type === 'page'); if (!target) throw Error('No isolated Edge target');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => { socket.onopen = res; socket.onerror = rej; });
let seq = 0; const pending = new Map(), exceptions = [], httpErrors = [];
socket.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id) { const p = pending.get(m.id); if (p) { pending.delete(m.id); clearTimeout(p.t); m.error ? p.rej(Error(JSON.stringify(m.error))) : p.res(m.result); } }
  if (m.method === 'Runtime.exceptionThrown') exceptions.push(m.params.exceptionDetails.exception?.description?.slice(0, 200) || m.params.exceptionDetails.text);
  if (m.method === 'Network.responseReceived') { const r = m.params.response; if (r.status >= 500 && r.url.includes('/api/')) httpErrors.push({path: new URL(r.url).pathname, status: r.status}); }
};
const call = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; const t = setTimeout(() => rej(Error('CDP timeout ' + method + ' ' + JSON.stringify(params).slice(0, 120))), 150000); pending.set(id, {res, rej, t}); socket.send(JSON.stringify({id, method, params})); });
async function evaluate(expression) { const r = await call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true}); if (r.exceptionDetails) throw Error(r.exceptionDetails.text); return r.result.value; }
async function until(expression) { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await delay(300); } throw Error('UI readiness timeout: ' + expression); }
await call('Runtime.enable'); await call('Page.enable'); await call('Network.enable');
const viewport = (width) => call('Emulation.setDeviceMetricsOverride', {width, height: 900, deviceScaleFactor: 1, mobile: width < 768});
const METRICS = `(()=>{const vw=innerWidth;const mobile=vw<768;
  const vis=e=>{const r=e.getBoundingClientRect();const s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
  const taps=[...document.querySelectorAll('button,a[href],[role=button]')].filter(vis);
  const small=taps.filter(e=>{const r=e.getBoundingClientRect();return Math.min(r.width,r.height)<40&&!e.closest('table')}).slice(0,6).map(e=>(e.getAttribute('aria-label')||e.textContent||e.tagName).trim().slice(0,30));
  const inputs=[...document.querySelectorAll('input,select,textarea')].filter(vis);
  const tinyFont=inputs.filter(e=>parseFloat(getComputedStyle(e).fontSize)<16).length;
  const named=e=>!!(e.getAttribute('aria-label')||e.getAttribute('aria-labelledby')||(e.id&&document.querySelector('label[for="'+CSS.escape(e.id)+'"]'))||e.closest('label')||e.title);
  const unnamed=inputs.filter(e=>!named(e)&&e.type!=='hidden').slice(0,6).map(e=>(e.placeholder||e.name||e.type||e.tagName).slice(0,30));
  const overflow=[...document.querySelectorAll('main *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.right>vw+2&&getComputedStyle(e).position!=='fixed'&&!e.closest('.tableWrap,.tableScroll,.table-scroll,[class*=scroll],[class*=Scroll]')}).slice(0,5).map(e=>e.tagName+'.'+String(e.className).slice(0,40));
  return {width:vw,scrollWidth:document.documentElement.scrollWidth,overflow,tapTargets:taps.length,smallTapTargets:mobile?small:[],inputs:inputs.length,inputsUnder16px:mobile?tinyFont:0,unnamedInputs:unnamed,
    tokenInStorage:[...Object.keys(localStorage),...Object.keys(sessionStorage)].filter(k=>/token|session|jwt|auth/i.test(k))};})()`;

const results = [];
for (const [school, userKey] of [['A', 'ADMIN'], ['A', 'CAISSIER1']]) {
  const s = fx[school], u = s.users[userKey];
  await viewport(1440);
  await call('Network.clearBrowserCookies');
  await call('Page.navigate', {url: APP}); await until('document.readyState==="complete"');
  await evaluate('localStorage.clear();sessionStorage.clear();true');
  const st = await evaluate(`(async()=>{const r=await fetch('/api/v1/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({scope: 'SCHOOL', school_code: s.code, email: u.email, password: u.password})})});return r.status})()`);
  if (st !== 200) throw Error(`login ${userKey} HTTP ${st}`);
  console.log('logged in', userKey, new Date().toISOString());
  await call('Page.reload'); await until('!!document.querySelector(".smartShell")');
  const modules = await evaluate('[...document.querySelectorAll(".smartNav .navLabel")].map(e=>e.textContent)');
  console.log(userKey, 'modules:', modules.join(' | '), new Date().toISOString());
  for (let i = 0; i < modules.length; i++) {
    await viewport(1440);
    await evaluate(`document.querySelectorAll('.smartNav button')[${i}].click()`); await delay(800);
    for (let w = 0; w < 40; w++) { if (await evaluate(`!document.querySelector('.skeleton,.thinLoader') && !document.body.innerText.includes('Ouverture du module')`)) break; await delay(500); }
    console.log(' ', userKey, modules[i], new Date().toISOString());
    for (const width of [320, 360, 390, 430, 768, 1024, 1440]) {
      await viewport(width); await delay(250);
      const m = await evaluate(METRICS);
      const pass = m.scrollWidth <= width && m.tokenInStorage.length === 0 && m.inputsUnder16px === 0;
      results.push({role: userKey, module: modules[i], viewport: width, ...m, pass});
      if (width === 360 || width === 1440) {
        const shot = await call('Page.captureScreenshot', {format: 'png'});
        await fs.writeFile(new URL(`screens/${userKey}-${i}-${width}.png`, dir), Buffer.from(shot.data, 'base64'));
      }
    }
  }
}
const failing = results.filter(r => !r.pass);
const smallTaps = results.filter(r => r.smallTapTargets?.length);
const unnamed = [...new Set(results.flatMap(r => (r.unnamedInputs||[]).map(x => `${r.module}: ${x}`)))];
const out = {app: APP, build: 'production (vite build + vite preview)', viewports: [320, 360, 390, 430, 768, 1024, 1440], screens: results.length,
  failing, unnamedInputs: unnamed, smallTapTargetScreens: smallTaps.map(r => ({role: r.role, module: r.module, viewport: r.viewport, examples: r.smallTapTargets})), exceptions, httpErrors, results};
await fs.writeFile(new URL('browser-live.json', dir), JSON.stringify(out, null, 2));
console.log(JSON.stringify({screens: results.length, failing: failing.length, smallTapScreens: smallTaps.length, unnamedInputs: unnamed.length, exceptions: exceptions.length, http5xx: httpErrors.length}));
socket.close();
