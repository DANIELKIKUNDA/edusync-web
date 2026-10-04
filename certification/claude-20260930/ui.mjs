// Tiny CDP driver for real user journeys: type into fields, click by visible text, wait, screenshot.
// Everything goes through the production UI (no API shortcuts), like a school employee would.
import fs from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';

export const APP = process.env.APP_URL || 'http://127.0.0.1:55175/';
const DIR = new URL('./journeys/', import.meta.url);

export async function open() {
  await fs.mkdir(DIR, {recursive: true});
  const target = await (await fetch('http://127.0.0.1:59223/json/new?about:blank', {method: 'PUT'})).json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0; const pend = new Map(); const errors = []; const http = [];
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); clearTimeout(p.t); m.error ? p.j(Error(JSON.stringify(m.error))) : p.r(m.result); }
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description?.slice(0, 200) || m.params.exceptionDetails.text);
    if (m.method === 'Network.responseReceived' && m.params.response.url.includes('/api/') && m.params.response.status >= 400)
      http.push(`${m.params.response.status} ${new URL(m.params.response.url).pathname}`);
  };
  const call = (method, params = {}) => new Promise((r, j) => { const i = ++id; const t = setTimeout(() => j(Error('CDP timeout ' + method)), 120000); pend.set(i, {r, j, t}); ws.send(JSON.stringify({id: i, method, params})); });
  await call('Runtime.enable'); await call('Page.enable'); await call('Network.enable');
  const ev = async (expression) => { const r = await call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true}); if (r.exceptionDetails) throw Error(r.exceptionDetails.text + ' :: ' + expression.slice(0, 120)); return r.result.value; };
  const page = {
    errors, http, call, ev,
    async viewport(width, height = 900) { await call('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: width < 768}); },
    async go(url = APP) { await call('Page.navigate', {url}); await page.waitFor('document.readyState==="complete"'); },
    async waitFor(expr, ms = 30000) { const end = Date.now() + ms; while (Date.now() < end) { try { if (await ev(expr)) return true; } catch {} await delay(300); } throw Error('timeout waiting for ' + expr.slice(0, 140)); },
    async waitText(text, ms = 30000) { return page.waitFor(`document.body.innerText.includes(${JSON.stringify(text)})`, ms); },
    async settle() { for (let i = 0; i < 40; i++) { if (await ev(`!document.querySelector('.skeleton,.thinLoader') && !document.body.innerText.includes('Ouverture du module')`)) break; await delay(400); } await delay(300); },
    // fill an input/textarea/select found by its label text, placeholder or aria-label (React-safe setter)
    async fill(hint, value) {
      const ok = await ev(`(()=>{const h=${JSON.stringify(hint)}.toLowerCase();const vis=e=>e.offsetParent!==null;
        let el=[...document.querySelectorAll('input,textarea,select')].filter(vis).find(e=>(e.placeholder||'').toLowerCase().includes(h)||(e.getAttribute('aria-label')||'').toLowerCase().includes(h)||(e.name||'').toLowerCase()===h);
        if(!el){const lab=[...document.querySelectorAll('label')].filter(vis).find(l=>l.innerText.toLowerCase().includes(h));if(lab)el=lab.control||lab.querySelector('input,textarea,select');}
        if(!el)return false;el.focus();const proto=el.tagName==='SELECT'?HTMLSelectElement.prototype:el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
        if(el.tagName==='SELECT'){const o=[...el.options].find(o=>o.text.toLowerCase().includes(${JSON.stringify(String(value).toLowerCase())})||o.value===${JSON.stringify(String(value))});if(!o)return false;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,o.value);}
        else Object.getOwnPropertyDescriptor(proto,'value').set.call(el,${JSON.stringify(String(value))});
        el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);
      if (!ok) throw Error(`field not found: ${hint}`);
      await delay(250);
    },
    // click the smallest visible clickable element whose text contains `text`
    async click(text, {within} = {}) {
      const ok = await ev(`(()=>{const t=${JSON.stringify(text)}.toLowerCase();const root=${within ? `document.querySelector(${JSON.stringify(within)})` : 'document'};if(!root)return false;
        const c=[...root.querySelectorAll('button,a,[role=button],[role=tab],[role=radio],label,li,tr,.tr,article')].filter(e=>e.offsetParent!==null&&!e.disabled&&e.innerText.toLowerCase().includes(t));
        c.sort((a,b)=>a.innerText.length-b.innerText.length);if(!c[0])return false;c[0].scrollIntoView({block:'center'});c[0].click();return true})()`);
      if (!ok) throw Error(`clickable not found: ${text}`);
      await delay(400);
    },
    async press(key) { await call('Input.dispatchKeyEvent', {type: 'keyDown', key}); await call('Input.dispatchKeyEvent', {type: 'keyUp', key}); },
    async shot(name) { const s = await call('Page.captureScreenshot', {format: 'png'}); await fs.writeFile(new URL(`${name}.png`, DIR), Buffer.from(s.data, 'base64')); },
    async visibleControls() {
      return ev(`[...document.querySelectorAll('button,input,select,textarea,[role=tab]')].filter(e=>e.offsetParent!==null).map(e=>(e.tagName+':'+(e.innerText||e.placeholder||e.getAttribute('aria-label')||e.name||'').trim().slice(0,40))).filter(x=>!x.endsWith(':'))`);
    },
    async close() { ws.close(); },
  };
  return page;
}

// Log in through the real login form (no API shortcut).
export async function uiLogin(page, {code, email, password}) {
  await page.call('Network.clearBrowserCookies');
  await page.go();
  await page.ev('localStorage.clear();sessionStorage.clear();true');
  await page.go();
  await page.waitText('Bienvenue');
  await page.fill('code', code);
  await page.fill('e-mail', email);
  await page.fill('mot de passe', password);
  await page.click('Se connecter');
  await page.waitFor('!!document.querySelector(".smartShell")', 120000);
  await page.settle();
}
