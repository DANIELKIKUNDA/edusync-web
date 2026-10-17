// External messaging — UI check at 390 px and 1280 px (Edge headless over CDP, local stack, fake providers).
// School Communication Center (composer → preview → confirmation, history, settings, push on this device), login
// "mot de passe oublié" and recovery link screen, Atelier Pro "Messagerie" (providers, wallets). Uses the last school
// created by messaging_local_probe.py (credentials from the private fixtures, never printed).
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import {APP, connect, delay, env, fx, signInSchool, signOut} from '../n2-20261014/cdp.mjs';

const FX_PATH = new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', import.meta.url);
const runs = Object.entries(fx.MSG || {}).filter(([k]) => k.startsWith('A-'));
const [, school] = runs[runs.length - 1] || [];
if (!school) { console.log('Lancez d’abord messaging_local_probe.py'); process.exit(1); }
const p = await connect(); let fail = 0;
const ok = (name, cond, extra = '') => { if (!cond) fail++; console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };

function b32(s) { const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = ''; for (const ch of s.replace(/[=\s]/g, '').toUpperCase()) bits += A.indexOf(ch).toString(2).padStart(5, '0');
  const out = []; for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2)); return Buffer.from(out); }
function totp(secret, step) { const b = Buffer.alloc(8); b.writeBigUInt64BE(BigInt(step)); const h = crypto.createHmac('sha1', b32(secret)).update(b).digest();
  const o = h[h.length - 1] & 15; return String((h.readUInt32BE(o) & 0x7fffffff) % 1000000).padStart(6, '0'); }
async function nextCode(email) {
  const cur = JSON.parse(await fs.readFile(FX_PATH, 'utf8')); const st = cur.MFA_TOTP[email.toLowerCase()];
  let step = Math.floor(Date.now() / 30000);
  while (step <= (st.last_step || 0)) { await delay(1500); step = Math.floor(Date.now() / 30000); }
  st.last_step = step; await fs.writeFile(FX_PATH, JSON.stringify(cur, null, 2)); return totp(st.secret, step);
}
async function nav(w, label) {
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText))?.click()'); await delay(500);
    await p.ev(`[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.includes(${JSON.stringify(label)}))?.click()`); }
  else await p.ev(`[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||b.innerText).includes(${JSON.stringify(label)}))?.click()`);
  await delay(1500);
}
const clickText = (sel, txt) => p.ev(`[...document.querySelectorAll(${JSON.stringify(sel)})].find(b=>b.innerText.trim().includes(${JSON.stringify(txt)}))?.click()`);
const setValue = (sel, v) => p.ev(`(()=>{const el=document.querySelector(${JSON.stringify(sel)});if(!el)return false;const proto=el.tagName==='SELECT'?HTMLSelectElement.prototype:el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto,'value').set.call(el,${JSON.stringify(v)});el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));return true})()`);

// ---------------------------------------------------------------- school Communication Center
await signInSchool(p, school.users.PREFET.email, school.users.PREFET.password);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1000);
  await nav(w, 'Communication');
  ok(`${w}px : Centre de communication ouvert (composer, historique, réglages)`, await p.ev('!!document.querySelector(".commPage")&&document.querySelectorAll(".commTabs button").length===3'));
  ok(`${w}px : solde SMS visible`, await p.ev('!!document.querySelector(".commWallet")'));
  await setValue('select[aria-label="Type de destinataires"]', 'CLASS'); await delay(300);
  const cls = await p.ev('[...document.querySelectorAll("select[aria-label=Classe] option")].find(o=>o.innerText.includes("7e"))?.value');
  await setValue('select[aria-label="Classe"]', cls); await delay(200);
  await p.ev('[...document.querySelectorAll(".commChannels label")].find(l=>l.innerText.includes("SMS"))?.querySelector("input:not(:checked)")?.click()'); await delay(200);
  await setValue('textarea[aria-label="Message"]', `Rappel réunion ${w}px`); await delay(300);
  ok(`${w}px : compteur de caractères et unités SMS affiché`, await p.ev('/unité\\(s\\) SMS par destinataire/.test(document.querySelector(".commCount")?.innerText||"")'));
  await clickText('.commActions button', 'Vérifier l’envoi');
  await p.waitFor('!!document.querySelector(".commPreview")||!!document.querySelector(".commCard .error")', 15000);
  const pageError = await p.ev('document.querySelector(".commCard .error")?.innerText||""');
  if (pageError) console.log('Erreur affichée :', pageError);
  ok(`${w}px : aperçu avant envoi (destinataires, invalides, doublons, unités, solde après)`,
     await p.ev('(t=>/destinataires/.test(t)&&/invalides/.test(t)&&/doublons/.test(t)&&/unités SMS nécessaires/.test(t)&&/solde après envoi/.test(t))(document.querySelector(".commPreview").innerText)'));
  let m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (composer)`, !m.hscroll, JSON.stringify(m.over));
  await p.shot(`messaging-composer-${w}`, true);
  await clickText('.commActions button', 'Confirmer l’envoi'); await delay(2500);
  ok(`${w}px : envoi accepté par le serveur, formulaire réinitialisé`, await p.ev('!document.querySelector(".commPreview")&&(document.querySelector("textarea[aria-label=Message]")?.value||"")===""'));
  await clickText('.commTabs button', 'Historique'); await p.waitFor('document.querySelectorAll(".commHistory>li").length>0', 15000);
  // The billed units appear once the worker has sent the SMS (the list refreshes every 15 s).
  await p.waitFor('/unité/.test(document.querySelector(".commHistoryHead")?.innerText||"")', 30000).catch(() => undefined);
  await p.ev('document.querySelector(".commHistoryHead")?.click()'); await delay(1500);
  ok(`${w}px : historique (canal, statut, auteur, unités) et détail des envois`, await p.ev('document.querySelectorAll(".commDeliveries li").length>0&&/unité/.test(document.querySelector(".commHistoryHead").innerText)'));
  m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (historique)`, !m.hscroll, JSON.stringify(m.over));
  await p.shot(`messaging-history-${w}`, true);
  await clickText('.commTabs button', 'Réglages'); await delay(1200);
  ok(`${w}px : réglages — canaux, portefeuille SMS, notifications de cet appareil`,
     await p.ev('document.querySelectorAll(".commSwitch").length>=4&&!!document.querySelector(".commWalletRow")&&/Notifications sur cet appareil/.test(document.body.innerText)'));
  ok(`${w}px : aucune demande de permission push sans action explicite`, await p.ev('Notification.permission') === 'default');
  m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (réglages)`, !m.hscroll, JSON.stringify(m.over));
  await p.shot(`messaging-settings-${w}`, true);
}

// ---------------------------------------------------------------- login: forgotten password + recovery link screen
await signOut(p);
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await p.waitFor('!!document.querySelector(".lg-card")'); await delay(500);
  await clickText('.lg-card button', 'Mot de passe oublié'); await delay(500);
  ok(`${w}px : écran « Mot de passe oublié » (lien valable 30 minutes)`, await p.ev('/Recevoir un lien/.test(document.body.innerText)&&/30 minutes/.test(document.body.innerText)'));
  await p.go(`${APP}?r=${w}#reset=${'x'.repeat(43)}`); await p.waitFor('!!document.querySelector(".lg-card")'); await delay(800);
  ok(`${w}px : lien de réinitialisation ouvert, jeton retiré de la barre d’adresse`, await p.ev('/Nouveau mot de passe/.test(document.body.innerText)&&!location.hash'));
  const m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (liens de compte)`, !m.hscroll, JSON.stringify(m.over));
  await p.shot(`messaging-reset-${w}`, true);
}

// ---------------------------------------------------------------- Atelier Pro: Messagerie
await p.viewport(1280, 900); await p.go(); await p.waitFor('!!document.querySelector(".lg-card")');
await p.type('#lg-email', env.EDUSYNC_PLATFORM_ADMIN_EMAIL); await p.type('#lg-pass', env.EDUSYNC_PLATFORM_ADMIN_PASSWORD); await p.click('Se connecter');
await p.waitFor('!!document.querySelector("#mfa-code")||!!document.querySelector(".es-shell")||!!document.querySelector(".lg-ctx")', 20000);
if (await p.ev('!!document.querySelector(".lg-ctx")')) { await clickText('.lg-ctx button', 'Atelier'); await p.waitFor('!!document.querySelector("#mfa-code")||!!document.querySelector(".es-shell")', 20000); }
if (await p.ev('!!document.querySelector("#mfa-code")')) { await p.type('#mfa-code', await nextCode(env.EDUSYNC_PLATFORM_ADMIN_EMAIL)); await p.waitFor('!!document.querySelector(".es-shell")', 20000); }
for (const [w, h] of [[1280, 900], [390, 844]]) {
  await p.viewport(w, h); await delay(800);
  await nav(w, 'Messagerie'); await p.waitFor('!!document.querySelector(".commPage")', 20000); await delay(800);
  ok(`${w}px : Atelier Pro — fournisseurs, file d’envoi, portefeuilles SMS`, await p.ev('/Fournisseurs/.test(document.body.innerText)&&/File d’envoi/.test(document.body.innerText)&&/Portefeuilles SMS/.test(document.body.innerText)'));
  await p.ev(`[...document.querySelectorAll(".commLedger li")].find(li=>li.innerText.includes(${JSON.stringify(school.code.replace('MSGA-', ''))}))?.querySelector("button")?.click()`); await delay(1500);
  ok(`${w}px : détail du portefeuille d’une école (mouvements, recharge auditée)`, await p.ev('/Mouvements/.test(document.body.innerText)&&/Recharge payée/.test(document.body.innerText)'));
  const m = await p.metrics(); ok(`${w}px : pas de défilement horizontal (Atelier Pro messagerie)`, !m.hscroll, JSON.stringify(m.over));
  await p.shot(`messaging-platform-${w}`, true);
  await p.ev('[...document.querySelectorAll(".es-modal button")].find(b=>b.innerText.trim()==="Fermer")?.click()'); await delay(400);
}
const errs = p.consoleErrors.filter(e => !e.includes('HTTP 401') && !e.includes('HTTP 404'));
ok('aucune erreur console', errs.length === 0, errs.slice(0, 3).join(' | '));
console.log(fail ? `UI MESSAGERIE : ${fail} échec(s)` : 'UI MESSAGERIE : PASS');
process.exit(fail ? 1 : 0);
