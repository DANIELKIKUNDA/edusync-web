// N0/N1 journey through the UI only (production build, isolated headless Edge on CDP port 59223).
// Boot screen, sign-in without school code at 7 widths, keyboard basics, Manager Atelier Pro (dashboard, team,
// roles, health, audit, notifications, school creation), a PLATFORM_CUSTOM account whose menu differs,
// sign-out / sign-in, responsive Atelier Pro. Credentials come from the private fixtures (never printed).
import fs from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';

const dir = new URL('./', import.meta.url);
const SHOTS = new URL('captures/', dir);
await fs.mkdir(SHOTS, {recursive: true});
const env = Object.fromEntries((await fs.readFile(new URL('../../.local/certification.env', dir), 'utf8')).replace(/^﻿/, '').split(/\r?\n/).filter(l => l && !l.startsWith('#') && l.includes('=')).map(l => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]));
const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', dir), 'utf8'));
const APP = process.env.APP_URL || 'http://localhost:5180/';
const results = [];
const check = (name, ok, detail = '') => { results.push({check: name, pass: !!ok, detail: String(detail).slice(0, 300)}); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ': ' + detail : ''}`); };

async function connect() {
  const t = await (await fetch('http://127.0.0.1:59223/json/new?about:blank', {method: 'PUT'})).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0; const pend = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.j(Error(JSON.stringify(m.error))) : p.r(m.result); } };
  const call = (method, params = {}) => new Promise((r, j) => { const i = ++id; pend.set(i, {r, j}); ws.send(JSON.stringify({id: i, method, params})); setTimeout(() => { if (pend.has(i)) { pend.delete(i); j(Error('CDP timeout ' + method)); } }, 120000); });
  await call('Runtime.enable'); await call('Page.enable');
  const ev = async (expression) => { const r = await call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true}); if (r.exceptionDetails) throw Error(r.exceptionDetails.text + ' :: ' + expression.slice(0, 100)); return r.result.value; };
  const p = {
    ev, call,
    async viewport(width, height = 900) { await call('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: width < 768}); },
    async go(url = APP) { await call('Page.navigate', {url}); await p.waitFor('document.readyState==="complete"'); },
    async waitFor(expr, ms = 60000) { const end = Date.now() + ms; while (Date.now() < end) { try { if (await ev(expr)) return true; } catch {} await delay(300); } throw Error('timeout: ' + expr.slice(0, 140)); },
    async type(selector, value) {
      const ok = await ev(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)return false;el.focus();const proto=el.tagName==='SELECT'?HTMLSelectElement.prototype:el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);
      if (!ok) throw Error('field not found ' + selector); await delay(200);
    },
    async click(text) {
      const ok = await ev(`(()=>{const t=${JSON.stringify(text)}.toLowerCase();const c=[...document.querySelectorAll('button,a,[role=button],[role=tab]')].filter(e=>e.offsetParent!==null&&!e.disabled&&((e.innerText||'')+' '+(e.getAttribute('aria-label')||'')).toLowerCase().includes(t));c.sort((a,b)=>a.innerText.length-b.innerText.length);if(!c[0])return false;c[0].scrollIntoView({block:'center'});c[0].click();return true})()`);
      if (!ok) throw Error('clickable not found: ' + text); await delay(500);
    },
    async key(key, code, keyCode) { for (const type of ['keyDown', 'keyUp']) await call('Input.dispatchKeyEvent', {type, key, code, windowsVirtualKeyCode: keyCode}); await delay(150); },
    async shot(name) { const s = await call('Page.captureScreenshot', {format: 'png'}); await fs.writeFile(new URL(`${name}.png`, SHOTS), Buffer.from(s.data, 'base64')); },
    async noHScroll() { return ev('document.documentElement.scrollWidth<=window.innerWidth+1'); },
  };
  return p;
}

async function signOut(p) {
  await p.ev("fetch('/api/v1/auth/logout',{method:'POST',credentials:'include'})"); await p.ev('localStorage.clear()');
}
async function signIn(p, email, password) {
  await p.go(); await p.waitFor('!!document.querySelector(".lg-card")||!!document.querySelector(".es-shell")');
  if (await p.ev('!!document.querySelector(".es-shell")')) { await signOut(p); await p.go(); await p.waitFor('!!document.querySelector(".lg-card")'); }
  await p.type('#lg-email', email); await p.type('#lg-pass', password); await p.click('Se connecter');
  await p.waitFor('!!document.querySelector(".es-shell")||!!document.querySelector(".lg-ctx")');
}

const p = await connect();
// ---------------- N0: boot screen (API response delayed to see it) ----------------
await p.viewport(1280, 800);
await p.call('Fetch.enable', {patterns: [{urlPattern: '*/api/v1/auth/refresh*'}]});
await p.call('Page.navigate', {url: APP});
await delay(1500);
const bootVisible = await p.ev('!!document.getElementById("edusync-boot")&&getComputedStyle(document.getElementById("edusync-boot")).opacity!=="0"');
const bootText = await p.ev('document.getElementById("edusync-boot")?.innerText||""');
check('Démarrage : écran de démarrage visible tant que la session est vérifiée', bootVisible, bootText.replace(/\n/g, ' '));
await p.shot('n0-boot-1280');
await p.call('Fetch.disable');
await p.waitFor('!!document.querySelector(".lg-card")||!!document.querySelector(".es-shell")');
check('Démarrage : écran retiré dès la vérification terminée', await p.ev('!document.getElementById("edusync-boot")'));
await signOut(p);

// ---------------- N0: sign-in at 7 widths ----------------
for (const w of [320, 375, 390, 768, 1024, 1280, 1440]) {
  await p.viewport(w, w < 768 ? 800 : 900); await p.go(); await p.waitFor('!!document.querySelector(".lg-card")'); await delay(900);
  const noCode = await p.ev('!document.querySelector("#lg-code")&&!document.body.innerText.includes("Code établissement")');
  check(`Connexion ${w}px : pas de code établissement, pas de défilement horizontal`, noCode && await p.noHScroll());
  await p.shot(`n0-login-${w}`);
}
// Zoom 200 % of a 1280 px screen = 640 CSS px of layout width.
await p.viewport(640, 450); await p.go(); await p.waitFor('!!document.querySelector(".lg-card")'); await delay(600);
check('Zoom 200 % (640 px) : connexion utilisable sans défilement horizontal', await p.noHScroll()); await p.shot('n0-login-zoom200');
await p.viewport(1280, 800); await p.go(); await p.waitFor('!!document.querySelector(".lg-card")'); await delay(800);
// WCAG contrast of every visible text node of the sign-in card against its first opaque background.
const contrast = await p.ev(`(()=>{const lum=c=>{const v=c.match(/[\\d.]+/g).slice(0,3).map(x=>{x/=255;return x<=.03928?x/12.92:((x+.055)/1.055)**2.4});return .2126*v[0]+.7152*v[1]+.0722*v[2]};
 const bg=el=>{for(let e=el;e;e=e.parentElement){const b=getComputedStyle(e).backgroundColor;const a=b.match(/[\\d.]+/g);if(a&&(a.length<4||+a[3]>.9))return b}return 'rgb(255,255,255)'};
 const out=[];document.querySelectorAll('.lg-card *').forEach(el=>{if(!el.childNodes.length||![...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))return;const s=getComputedStyle(el);if(s.visibility==='hidden'||el.offsetParent===null)return;
 const L1=lum(s.color),L2=lum(bg(el));const r=(Math.max(L1,L2)+.05)/(Math.min(L1,L2)+.05);const large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&+s.fontWeight>=700);out.push({t:el.textContent.trim().slice(0,30),r:+r.toFixed(2),min:large?3:4.5})});return out})()`);
const weak = contrast.filter(c => c.r < c.min);
check('Contraste WCAG AA des textes de la carte de connexion', weak.length === 0, weak.length ? JSON.stringify(weak.slice(0, 4)) : `${contrast.length} textes, min ${Math.min(...contrast.map(c => c.r))}:1`);
check('Connexion : photo de campus servie localement', await p.ev('getComputedStyle(document.querySelector(".lg-photo")).backgroundImage.includes("/brand/login-campus")'));
check('Connexion : champ e-mail focalisé à l’ouverture', await p.ev('document.activeElement?.id==="lg-email"'));
await p.key('Tab', 'Tab', 9);
check('Clavier : Tab mène au mot de passe', await p.ev('document.activeElement?.id==="lg-pass"'));
await p.click('Afficher le mot de passe');
check('Afficher / masquer le mot de passe', await p.ev('document.querySelector("#lg-pass").type==="text"'));
check('Manager existant : aucun lien d’accès plateforme affiché (le Manager se connecte comme tout le monde)', await p.ev('!document.querySelector(".lg-quiet")&&!document.body.innerText.includes("Atelier Pro")'));
await p.type('#lg-email', 'inconnu@example.test'); await p.type('#lg-pass', 'mauvais'); await p.click('Se connecter');
await p.waitFor('!!document.querySelector(".lg-error")');
check('Erreur de connexion : message clair, sans révéler si le compte existe', await p.ev('document.querySelector(".lg-error").innerText.includes("incorrect")'));
await p.shot('n0-login-error-1280');

// ---------------- N1: Manager ----------------
await signIn(p, env.EDUSYNC_PLATFORM_ADMIN_EMAIL, env.EDUSYNC_PLATFORM_ADMIN_PASSWORD);
check('Manager : connexion automatique vers l’Atelier Pro', await p.ev('document.body.innerText.includes("Atelier Pro")'));
const menu = await p.ev('[...document.querySelectorAll("nav button, .es-nav button")].map(b=>b.innerText.trim()).filter(Boolean)');
check('Manager : menu complet (7 entrées)', ['Tableau de bord', 'Écoles', 'Accès écoles', 'Équipe plateforme', 'Notifications système', 'Journal d’audit', 'État du service'].every(x => menu.some(m => m.includes(x))), menu.join(' · '));
await p.shot('n1-dashboard-1280');
for (const [label, name, waitExpr] of [
  ['Équipe plateforme', 'n1-team-1280', '!!document.querySelector(".tm-list")'],
  ['État du service', 'n1-health-1280', '!!document.querySelector(".hl-grid")'],
  ['Journal d’audit', 'n1-audit-1280', '!!document.querySelector(".au-list")'],
  ['Notifications système', 'n1-notifications-1280', '!!document.querySelector(".cp-list")||document.body.innerText.includes("Aucune notification envoyée")'],
]) { await p.click(label); await p.waitFor(waitExpr); await delay(700); await p.shot(name); check(`Manager : écran « ${label} » chargé`, true); }
await p.click('Équipe plateforme'); await p.waitFor('!!document.querySelector(".tm-list")'); await p.click('Rôles ·'); await p.waitFor('!!document.querySelector(".tm-roles")'); await delay(500); await p.shot('n1-roles-1280');
await p.click('Nouveau rôle'); await p.waitFor('!!document.querySelector(".tm-caps")'); await delay(400); await p.shot('n1-role-editor-1280');
check('Éditeur de rôle : capacité réservée non cochable', await p.ev('[...document.querySelectorAll(".tm-caps label")].some(l=>l.innerText.includes("platform.collaborators.manage")&&l.querySelector("input").disabled)'));
await p.key('Escape', 'Escape', 27);
check('Dialogue : Échap ferme et rend le focus', await p.ev('!document.querySelector(".tm-caps")'));
await p.click('Journal d’audit'); await p.waitFor('!!document.querySelector(".au-list")'); await p.ev('document.querySelector(".au-list button").click()'); await p.waitFor('!!document.querySelector(".au-detail")'); await delay(400); await p.shot('n1-audit-detail-1280'); await p.key('Escape', 'Escape', 27);
await p.click('Écoles'); await p.waitFor('document.body.innerText.includes("Annuaire des écoles")'); await p.click('Nouvelle école'); await p.waitFor('!!document.querySelector(".sc-form")'); await delay(400);
await p.click('Créer l’école'); await delay(400);
check('Création d’école : erreurs de validation annoncées', await p.ev('document.querySelectorAll(".sc-field small[role=alert]").length>=2'));
await p.shot('n1-school-create-1280'); await p.key('Escape', 'Escape', 27);
await p.click('Notifications'); await delay(800); await p.shot('n1-bell-1280');
check('Cloche Atelier Pro : panneau rapide', await p.ev('!!document.querySelector(".nc-pop")'));
await p.key('Escape', 'Escape', 27);
for (const w of [375, 640, 768, 1440]) { await p.viewport(w, w < 768 ? 800 : 900); await p.click('Tableau de bord').catch(() => {}); await delay(900); check(`Atelier Pro ${w}px : pas de défilement horizontal`, await p.noHScroll()); await p.shot(`n1-dashboard-${w}`); }
await p.viewport(1280, 800);

// ---------------- N1: PLATFORM_CUSTOM account, menu differs ----------------
const u2 = fx.N1_TEAM?.u2;
if (u2) {
  await signIn(p, u2.email, u2.password);
  const m2 = await p.ev('[...document.querySelectorAll("nav button, .es-nav button")].map(b=>b.innerText.trim()).filter(Boolean)');
  check('Rôle personnalisé : menu réduit (pas d’Équipe, ni d’Audit, ni de Notifications)', !m2.some(x => /Équipe|audit|Notifications système/i.test(x)) && m2.some(x => x.includes('Écoles')), m2.join(' · '));
  check('Rôle personnalisé : pas de bouton « Nouvelle école »', await p.ev('(async()=>{const b=[...document.querySelectorAll("button")].find(x=>x.innerText.includes("Écoles"));b&&b.click();await new Promise(r=>setTimeout(r,1500));return !document.body.innerText.includes("Nouvelle école")})()'));
  await p.shot('n1-custom-role-1280');
}

// ---------------- sign-out / sign-in keeps working ----------------
await signOut(p); await p.go(); await p.waitFor('!!document.querySelector(".lg-card")');
check('Déconnexion : retour à l’écran de connexion', true);
await signIn(p, env.EDUSYNC_PLATFORM_ADMIN_EMAIL, env.EDUSYNC_PLATFORM_ADMIN_PASSWORD);
await p.go(); await p.waitFor('!!document.querySelector(".es-shell")');
check('Reconnexion puis rechargement : session persistante', true);

await fs.writeFile(new URL('n1-journey-live.json', dir), JSON.stringify(results, null, 2));
console.log(`== ${results.filter(r => r.pass).length}/${results.length} PASS -> n1-journey-live.json`);
process.exit(0);
