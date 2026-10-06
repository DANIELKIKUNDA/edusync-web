// UX sweep on the PRODUCTION build (vite preview) with an isolated headless Edge driven by CDP.
// Every module of every role, 7 widths. Checks beyond "no overflow": accessible names (placeholder alone is
// NOT a name), touch targets and 16px inputs on phones, emoji used as icons, raw technical codes shown to
// users, JS exceptions, server errors, tokens in browser storage. Screenshots at 375 and 1440 px.
import fs from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';

const dir = new URL('./', import.meta.url);
const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', dir), 'utf8'));
const APP = process.env.APP_URL || 'http://127.0.0.1:55175/';
const WIDTHS = [320, 375, 390, 768, 1024, 1280, 1440];
const ROLES = (process.env.ROLES || 'ADMIN,CAISSIER1,GEST,SECR,R_PROMOTEUR,R_RESPONSABLE_FINANCE,INTENDANT').split(',');
await fs.mkdir(new URL('screens/', dir), {recursive: true});

const target = await (await fetch('http://127.0.0.1:59223/json/new?about:blank', {method: 'PUT'})).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => { socket.onopen = res; socket.onerror = rej; });
let seq = 0; const pending = new Map(), exceptions = [], httpErrors = [];
socket.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id) { const p = pending.get(m.id); if (p) { pending.delete(m.id); clearTimeout(p.t); m.error ? p.rej(Error(JSON.stringify(m.error))) : p.res(m.result); } }
  if (m.method === 'Runtime.exceptionThrown') exceptions.push(m.params.exceptionDetails.exception?.description?.slice(0, 200) || m.params.exceptionDetails.text);
  if (m.method === 'Network.responseReceived') { const r = m.params.response; if (r.status >= 500 && r.url.includes('/api/')) httpErrors.push({path: new URL(r.url).pathname, status: r.status}); }
};
const call = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; const t = setTimeout(() => rej(Error('CDP timeout ' + method)), 150000); pending.set(id, {res, rej, t}); socket.send(JSON.stringify({id, method, params})); });
async function ev(expression) { const r = await call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true}); if (r.exceptionDetails) throw Error(r.exceptionDetails.text + ' :: ' + expression.slice(0, 80)); return r.result.value; }
async function until(expression, ms = 40000) { const end = Date.now() + ms; while (Date.now() < end) { try { if (await ev(expression)) return; } catch {} await delay(300); } throw Error('timeout: ' + expression.slice(0, 100)); }
await call('Runtime.enable'); await call('Page.enable'); await call('Network.enable');
const viewport = (width) => call('Emulation.setDeviceMetricsOverride', {width, height: width < 768 ? 812 : 900, deviceScaleFactor: 1, mobile: width < 768});
async function settle() { for (let i = 0; i < 40; i++) { if (await ev(`!document.querySelector('.skeleton,.thinLoader,.es-skeleton,[aria-busy=true]') && !document.body.innerText.includes('Ouverture du module') && !document.body.innerText.includes('Chargement')`)) break; await delay(400); } await delay(350); }

const METRICS = `(()=>{const vw=innerWidth;const mobile=vw<768;
 const vis=e=>{const r=e.getBoundingClientRect();const s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&s.opacity!=='0'};
 const taps=[...document.querySelectorAll('button,a[href],[role=button],[role=tab],select,input:not([type=hidden])')].filter(vis);
 const small=taps.filter(e=>{const r=e.getBoundingClientRect();return Math.min(r.width,r.height)<40&&!e.closest('table,.dataTable')&&e.type!=='checkbox'&&e.type!=='radio'}).slice(0,6).map(e=>(e.getAttribute('aria-label')||e.innerText||e.placeholder||e.tagName).trim().slice(0,30));
 const inputs=[...document.querySelectorAll('input,select,textarea')].filter(e=>vis(e)&&e.type!=='hidden'&&!e.classList.contains('es-sr'));
 const tinyFont=inputs.filter(e=>parseFloat(getComputedStyle(e).fontSize)<16).map(e=>(e.getAttribute('aria-label')||e.placeholder||e.name||e.type).slice(0,24)).slice(0,5);
 const named=e=>!!(e.getAttribute('aria-label')||e.getAttribute('aria-labelledby')||(e.id&&document.querySelector('label[for="'+CSS.escape(e.id)+'"]'))||e.closest('label')||e.title);
 const unnamed=inputs.filter(e=>!named(e)).slice(0,6).map(e=>(e.placeholder||e.name||e.type||e.tagName).slice(0,30));
 const unnamedButtons=[...document.querySelectorAll('button')].filter(e=>vis(e)&&!(e.innerText||'').trim()&&!e.getAttribute('aria-label')&&!e.title).length;
 const overflow=[...document.querySelectorAll('.es-content *,.lg-page *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.right>vw+2&&getComputedStyle(e).position!=='fixed'&&!e.closest('.tableWrap,.tableScroll,.table-scroll,[class*=scroll],[class*=Scroll],.dataTable,[role=tablist]')}).slice(0,5).map(e=>e.tagName+'.'+String(e.className).slice(0,40));
 const text=document.body.innerText;
 const emoji=[...new Set((text.match(/[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{26FF}\\u{2700}-\\u{27BF}]/gu)||[]))].filter(c=>!'✓✔'.includes(c));
 const codes=[...new Set((text.match(/\\b[A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]{2,})+\\b/g)||[]))].slice(0,8);
 return {width:vw,scrollWidth:document.documentElement.scrollWidth,overflow,smallTapTargets:mobile?small:[],inputsUnder16px:mobile?tinyFont:[],unnamedInputs:unnamed,unnamedButtons,emoji,codes,
  title:document.title,tokenInStorage:[...Object.keys(localStorage),...Object.keys(sessionStorage)].filter(k=>/token|jwt|auth/i.test(k))};})()`;

const results = [];
async function sweep(label, slug) {
  await settle();
  for (const width of WIDTHS) {
    await viewport(width); await delay(260);
    const m = await ev(METRICS);
    const issues = [];
    if (m.scrollWidth > width + 1) issues.push('horizontal-scroll');
    if (m.overflow.length) issues.push('overflow');
    if (m.unnamedInputs.length) issues.push('unnamed-input');
    if (m.unnamedButtons) issues.push('unnamed-button');
    if (m.inputsUnder16px.length) issues.push('input-font<16');
    if (m.smallTapTargets.length) issues.push('tap<40');
    if (m.emoji.length) issues.push('emoji');
    if (m.codes.length) issues.push('raw-code');
    if (m.tokenInStorage.length) issues.push('token-in-storage');
    results.push({screen: label, viewport: width, ...m, issues, pass: issues.length === 0});
    if (width === 375 || width === 1440) {
      const shot = await call('Page.captureScreenshot', {format: 'png'});
      await fs.writeFile(new URL(`screens/${slug}-${width}.png`, dir), Buffer.from(shot.data, 'base64'));
    }
  }
  await viewport(1440); await delay(200);
}

// 1. Sign-in page (signed out) — only when ROLES contains LOGIN.
if (ROLES.includes('LOGIN')) {
await viewport(1440); await call('Network.clearBrowserCookies');
await call('Page.navigate', {url: APP}); await until('document.readyState==="complete"');
await ev('try{localStorage.clear();sessionStorage.clear()}catch{};true');
await call('Page.reload'); await until('!!document.querySelector(".lg-card")');
await sweep('Connexion', 'login');
}

for (const key of ROLES.filter(r => r !== 'LOGIN')) {
  const s = fx.A, u = s.users[key];
  if (!u) { console.log('skip', key); continue; }
  await viewport(1440); await call('Network.clearBrowserCookies');
  await call('Page.navigate', {url: APP}); await until('document.readyState==="complete"');
  const st = await ev(`(async()=>{const r=await fetch('/api/v1/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({scope: 'SCHOOL', school_code: s.code, email: u.email, password: u.password})})});return r.status})()`);
  if (st !== 200) { console.log('login refused', key, st); results.push({screen: `login ${key}`, issues: [`login HTTP ${st}`], pass: false}); continue; }
  await call('Page.reload'); await until('!!document.querySelector(".es-shell")');
  const modules = await ev('[...document.querySelectorAll(".es-nav button")].map(b=>b.getAttribute("aria-label"))');
  console.log(key, '→', modules.join(' | '));
  for (let i = 0; i < modules.length; i++) {
    await ev(`document.querySelectorAll('.es-nav button')[${i}].click()`); await delay(700);
    await sweep(`${key} · ${modules[i]}`, `${key}-${i}`);
    // Sub-tabs inside the module (settings tabs, finance tabs, documents tabs...)
    const tabs = await ev(`[...document.querySelectorAll('.es-content [role=tab], .es-content .settingsNav button, .es-content .financeTabs button, .es-content .moduleTabs button')].filter(b=>b.offsetParent).map(b=>(b.innerText||b.getAttribute('aria-label')||'').trim()).filter(Boolean).slice(0,10)`);
    for (let t = 1; t < tabs.length; t++) {
      const clicked = await ev(`(()=>{const b=[...document.querySelectorAll('.es-content [role=tab], .es-content .settingsNav button, .es-content .financeTabs button, .es-content .moduleTabs button')].filter(b=>b.offsetParent).find(b=>(b.innerText||b.getAttribute('aria-label')||'').trim()===${JSON.stringify(tabs[t])});if(!b)return false;b.click();return true})()`);
      if (!clicked) continue;
      await delay(600);
      await sweep(`${key} · ${modules[i]} › ${tabs[t]}`, `${key}-${i}-${t}`);
    }
  }
}

const failing = results.filter(r => !r.pass);
const byIssue = {};
for (const r of failing) for (const i of r.issues) (byIssue[i] ||= new Set()).add(`${r.screen} @${r.viewport}`);
const summary = {screens: results.length, failing: failing.length, byIssue: Object.fromEntries(Object.entries(byIssue).map(([k, v]) => [k, v.size])), exceptions: exceptions.length, http5xx: httpErrors.length};
await fs.writeFile(new URL(`ux-sweep-${ROLES.join('_')}.json`, dir), JSON.stringify({app: APP, widths: WIDTHS, roles: ROLES, summary, exceptions, httpErrors,
  failing: failing.map(r => ({screen: r.screen, viewport: r.viewport, issues: r.issues, overflow: r.overflow, unnamedInputs: r.unnamedInputs, smallTapTargets: r.smallTapTargets, inputsUnder16px: r.inputsUnder16px, emoji: r.emoji, codes: r.codes})), results}, null, 2));
console.log(JSON.stringify(summary));
socket.close();
