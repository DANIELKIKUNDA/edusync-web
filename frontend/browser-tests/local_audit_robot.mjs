// Inspection robot (owner request 2026-10-25: « fais toutes les manipulations possibles et vérifie si le frontend expose
// réellement ce que le backend contient »). LOCAL stack only. Logs in with a role account, opens EVERY module of the
// menu, EVERY tab and sub-tab, opens the first line of every list / card (then closes it), presses read-only export
// buttons (PDF / Excel / Imprimer / Relevé) and records, per screen:
//   - every API refusal (HTTP >= 400), page crash (JS error), console error;
//   - every vague message (« Une difficulté est survenue ») and every visible error banner;
//   - endless loaders (skeleton or « Chargement… » still visible after 8 s), sideways overflow (page wider than screen);
//   - empty screens (no table, no card, no text) — a sign that the screen exposes nothing.
// It NEVER submits a form, collects money, saves, deletes or closes anything: buttons are filtered by a deny list.
// Usage: node browser-tests/local_audit_robot.mjs [account.json] [width]   → report in ../.local/robot/<role>_<width>.json
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const ACCOUNT = process.argv[2] || '../.local/caissier/.account.json';
const WIDTH = Number(process.argv[3] || 1440);
const acc = JSON.parse(fs.readFileSync(ACCOUNT, 'utf8'));
const OUT = '../.local/robot'; fs.mkdirSync(OUT, {recursive: true});
const SAFE_CLICK = /^(Voir|Ouvrir|Afficher|Détails?|Aperçu|PDF|Excel|Imprimer|Relevé PDF|Journal PDF|Fiche PDF|Exporter|Télécharger le modèle|Modèle Excel|Actualiser|Tout l’historique|Voir tout|Voir les \d+ lignes)/i;
const DENY = /(Encaisser|Valider|Enregistrer|Supprimer|Clôturer|Ouvrir ma caisse|Rouvrir|Envoyer|Importer|Confirmer|Annuler le|Contre-opération|Désactiver|Activer|Révoquer|Réinitialiser le mot|Déconnexion|Se déconnecter|Fusionner|Réinscrire|Nouvelle inscription|Déclarer|Suspendre|Publier|Sauvegarder|Restaurer|Inviter|Ajouter|Créer|Générer le rapport officiel)/i;
const issues = []; let screen = 'connexion';
const b = await chromium.launch({channel: 'msedge'});
const ctx = await b.newContext({viewport: {width: WIDTH, height: 900}, acceptDownloads: true});
const p = await ctx.newPage();
ctx.on('page', np => { if (np !== p) setTimeout(() => np.close().catch(() => {}), 1500); });
const role = (ACCOUNT.match(/\.local\/([^/]+)\//) || [, 'role'])[1]; const REPORT = `${OUT}/${role}_${WIDTH}.json`;
const save = () => fs.writeFileSync(REPORT, JSON.stringify({screens: visited, issues: issues.map(({key, ...i}) => i)}, null, 1)); const visited = [];
const add = (kind, detail) => { const k = `${screen}|${kind}|${detail}`; if (!issues.some(i => i.key === k)) { issues.push({key: k, screen, kind, detail}); console.log(`  ! ${kind} · ${screen} — ${detail}`); save(); } };
p.on('response', async r => { const u = new URL(r.url()); if (!u.pathname.startsWith('/api/') || r.status() < 400) return; if (u.pathname.includes('/auth/refresh') || u.pathname.includes('/auth/contexts') || u.pathname.includes('branding/logo')) return;
  let body = ''; try { body = (await r.text()).slice(0, 160); } catch {} add('HTTP', `${r.status()} ${r.request().method()} ${u.pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, ':id')} ${body}`); });
p.on('pageerror', e => add('JS', String(e.message).slice(0, 200)));
p.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) add('CONSOLE', m.text().slice(0, 200)); });
p.on('dialog', d => d.dismiss().catch(() => {}));

async function inspect(label) {
  screen = label; visited.push(label); await p.waitForTimeout(1200);
  const vague = await p.getByText('Une difficulté est survenue').count(); if (vague) add('MESSAGE VAGUE', 'Une difficulté est survenue');
  for (const t of (await p.locator('.error:visible, .es-alert-danger:visible, [role=alert]:visible').allInnerTexts()).map(x => x.trim()).filter(Boolean)) add('ERREUR AFFICHÉE', t.slice(0, 160));
  const w = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth); if (w > 2) add('DÉBORDEMENT', `page plus large de ${w}px`);
  await p.waitForTimeout(3800);
  const loading = await p.locator('.kp-skel:visible, .sf-skel:visible, .rc-skeleton:visible, [class*=skeleton]:visible, [aria-busy=true]:visible').count() + await p.getByText(/^Chargement…$/).filter({visible: true}).count();
  if (loading) add('CHARGEMENT SANS FIN', `${loading} zone(s) toujours en chargement après 5 s`);
  const main = await p.locator('main, .es-main, .es-content').first().innerText().catch(() => '');
  if (main.replace(/\s+/g, ' ').trim().length < 40) add('ÉCRAN VIDE', 'presque aucun contenu affiché');
}
const visibleNames = async sel => (await p.locator(sel).filter({visible: true}).allInnerTexts()).map(t => t.trim().split('\n')[0]).filter(Boolean);
async function closeOverlays() { for (let i = 0; i < 3; i++) { await p.keyboard.press('Escape'); await p.waitForTimeout(200); }
  const x = p.locator('[aria-label^="Fermer"]:visible, .drawerClose:visible, .kp-close:visible'); if (await x.count()) await x.first().click({timeout: 1500}).catch(() => {}); await p.waitForTimeout(300); }
async function pressSafeButtons(scope) {
  const names = [...new Set((await visibleNames('main button, .es-main button')).filter(n => SAFE_CLICK.test(n) && !DENY.test(n)))].slice(0, 8);
  for (const n of names) { const btn = p.locator('main button, .es-main button').filter({visible: true, hasText: n}).first();
    try { await btn.click({timeout: 3000}); await inspect(`${scope} › bouton « ${n} »`); await closeOverlays(); } catch {} }
}
async function openFirstRow(scope) {
  const row = p.locator('button.kp-row, button.chargeRow, .cashSessionList button, button.ui-card, .ui-grid button, .fx2BarRow, .kp-hit, [role=row] button').filter({visible: true}).first();
  if (!(await row.count())) return; const name = (await row.innerText().catch(() => '')).split('\n')[0].slice(0, 40);
  if (DENY.test(name)) return;
  try { await row.click({timeout: 3000}); await inspect(`${scope} › ouverture « ${name} »`); await pressSafeButtons(`${scope} › ${name}`); await closeOverlays(); } catch {}
}
const TAB_SEL = '[role=tab], .financeTabs button, .schoolingTabs button, .subTabs button, .checkoutSubtabs button, .fxTabs button, .fxMode button, .settingsNav button, .kp-tabs button, .sf-tabs button, .ui-tabs button, [class*=Tabs] > button';

await p.goto('http://localhost:5180/'); await p.getByLabel('Adresse e-mail').fill(acc.email); await p.getByLabel('Mot de passe', {exact: true}).fill(acc.password);
await p.getByRole('button', {name: 'Se connecter'}).click(); await p.locator('.es-shell').waitFor({timeout: 30000});
const nav = () => p.getByRole('complementary', {name: 'Navigation principale'});
const openMenu = async () => { if (WIDTH < 900) { await p.getByRole('button', {name: 'Tous les modules'}).click(); await p.waitForTimeout(500); } };
await openMenu();
const modules = (await (WIDTH < 900 ? p.locator('button[aria-label]').filter({visible: true}) : nav().locator('button[aria-label]')).evaluateAll(es => es.map(e => e.getAttribute('aria-label'))))
  .filter(n => n && !/menu|Compte|Réduire|Fermer/i.test(n));
if (WIDTH < 900) await closeOverlays();
console.log(`Rôle ${acc.email.split('@')[0].replace(/./g, '•')} · ${WIDTH}px · modules : ${modules.join(', ')}`);
for (const m of modules) {
  await openMenu();
  const target = WIDTH < 900 ? p.getByRole('button', {name: m, exact: true}).filter({visible: true}).last() : nav().getByRole('button', {name: m, exact: true});
  try { await target.click({timeout: 5000}); } catch { add('NAVIGATION', `module ${m} inaccessible`); continue; }
  await inspect(m); await pressSafeButtons(m); await openFirstRow(m);
  const tabs = [...new Set(await visibleNames(TAB_SEL))].slice(0, 14);
  for (const t of tabs) {
    const tb = p.locator(TAB_SEL).filter({visible: true, hasText: t}).first(); try { await tb.click({timeout: 3000}); } catch { continue; }
    await inspect(`${m} › ${t}`); await pressSafeButtons(`${m} › ${t}`); await openFirstRow(`${m} › ${t}`);
    const subs = [...new Set(await visibleNames(TAB_SEL))].filter(s => !tabs.includes(s)).slice(0, 10);
    for (const s of subs) { const sb = p.locator(TAB_SEL).filter({visible: true, hasText: s}).first(); try { await sb.click({timeout: 3000}); } catch { continue; }
      await inspect(`${m} › ${t} › ${s}`); await pressSafeButtons(`${m} › ${t} › ${s}`); await openFirstRow(`${m} › ${t} › ${s}`); }
  }
  await closeOverlays();
}
save();
const by = {}; for (const i of issues) (by[i.kind] ??= []).push(i);
for (const [k, list] of Object.entries(by)) { console.log(`\n== ${k} (${list.length})`); for (const i of list) console.log(`  · ${i.screen} — ${i.detail}`); }
console.log(`\n${issues.length} constat(s).`);
await b.close();
