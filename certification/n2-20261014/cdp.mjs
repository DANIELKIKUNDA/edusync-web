// Minimal Chrome DevTools Protocol driver for the N2 UI audits (isolated headless Edge, production build).
// Credentials come from the private fixtures (never printed).
import fs from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';

export const dir = new URL('./', import.meta.url);
export const SHOTS = new URL('captures/', dir);
await fs.mkdir(SHOTS, {recursive: true});
export const APP = process.env.APP_URL || 'http://localhost:5180/';
export const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', dir), 'utf8'));
export const env = Object.fromEntries((await fs.readFile(new URL('../../.local/certification.env', dir), 'utf8')).replace(/^﻿/, '').split(/\r?\n/)
  .filter(l => l && !l.startsWith('#') && l.includes('=')).map(l => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]));
export {delay};

export async function connect() {
  const t = await (await fetch(`http://127.0.0.1:${process.env.CDP_PORT || 59223}/json/new?about:blank`, {method: 'PUT'})).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0; const pend = new Map(); const consoleErrors = [];
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.j(Error(JSON.stringify(m.error))) : p.r(m.result); }
    if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails.text);
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description ?? '').join(' ').slice(0, 200));
  };
  const call = (method, params = {}) => new Promise((r, j) => { const i = ++id; pend.set(i, {r, j}); ws.send(JSON.stringify({id: i, method, params})); setTimeout(() => { if (pend.has(i)) { pend.delete(i); j(Error('CDP timeout ' + method)); } }, 90000); });
  await call('Runtime.enable'); await call('Page.enable');
  const ev = async expression => { const r = await call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true}); if (r.exceptionDetails) throw Error(r.exceptionDetails.text + ' :: ' + expression.slice(0, 100)); return r.result.value; };
  const p = {
    ev, call, consoleErrors,
    async viewport(width, height = 900) { await call('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: width < 768}); await delay(350); },
    async go(url = APP) { await call('Page.navigate', {url}); await p.waitFor('document.readyState==="complete"'); },
    async waitFor(expr, ms = 45000) { const end = Date.now() + ms; while (Date.now() < end) { try { if (await ev(expr)) return true; } catch {} await delay(300); } throw Error('timeout: ' + expr.slice(0, 140)); },
    async type(selector, value) {
      const ok = await ev(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)return false;el.focus();const proto=el.tagName==='SELECT'?HTMLSelectElement.prototype:el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);
      if (!ok) throw Error('field not found ' + selector); await delay(200);
    },
    async click(text) {
      const ok = await ev(`(()=>{const t=${JSON.stringify(text)}.toLowerCase();const c=[...document.querySelectorAll('button,a,[role=button],[role=tab],[role=menuitem]')].filter(e=>e.offsetParent!==null&&!e.disabled&&((e.innerText||'')+' '+(e.getAttribute('aria-label')||'')).toLowerCase().includes(t));c.sort((a,b)=>a.innerText.length-b.innerText.length);if(!c[0])return false;c[0].scrollIntoView({block:'center'});c[0].click();return true})()`);
      if (!ok) throw Error('clickable not found: ' + text); await delay(600);
    },
    async shot(name, full = false) {
      let clip;
      if (full) { const m = await call('Page.getLayoutMetrics'); clip = {x: 0, y: 0, width: m.cssContentSize.width, height: Math.min(m.cssContentSize.height, 6000), scale: 1}; }
      const s = await call('Page.captureScreenshot', {format: 'png', ...(clip ? {clip, captureBeyondViewport: true} : {})});
      await fs.writeFile(new URL(`${name}.png`, SHOTS), Buffer.from(s.data, 'base64'));
    },
    async metrics() {
      return ev(`(()=>{const w=window.innerWidth;const over=[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.right>w+1&&getComputedStyle(e).position!=='fixed'}).slice(0,6).map(e=>(e.className&&typeof e.className==='string'?e.className.split(' ')[0]:e.tagName)+':'+Math.round(e.getBoundingClientRect().right));
        const small=[...document.querySelectorAll('button,a,input,select,[role=tab]')].filter(e=>{const r=e.getBoundingClientRect();return e.offsetParent!==null&&r.width>0&&(r.height<36||r.width<36)}).length;
        return {hscroll:document.documentElement.scrollWidth>w+1,scrollWidth:document.documentElement.scrollWidth,over,smallTargets:small,h:document.documentElement.scrollHeight}})()`);
    },
  };
  return p;
}

export async function signOut(p) { await p.ev("fetch('/api/v1/auth/logout',{method:'POST',credentials:'include'})"); await p.ev('localStorage.clear()'); }

export async function signInSchool(p, email, password) {
  await p.go(); await p.waitFor('!!document.querySelector(".lg-card")||!!document.querySelector(".es-shell")');
  if (await p.ev('!!document.querySelector(".es-shell")')) { await signOut(p); await p.go(); await p.waitFor('!!document.querySelector(".lg-card")'); }
  await p.type('#lg-email', email); await p.type('#lg-pass', password); await p.click('Se connecter');
  await p.waitFor('!!document.querySelector(".es-shell")||!!document.querySelector(".lg-ctx")');
}
