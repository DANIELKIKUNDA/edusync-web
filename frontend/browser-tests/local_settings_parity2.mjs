// Settings parity pass 2 (2026-10-24) — real administrator check on the LOCAL stack (real API, real database, school C
// of the local fixtures, already set up by local_settings_walkthrough.mjs). The test password is read from the local
// fixtures file and never printed. Covers: parallels per level, fee edit / disable, tariff assistant (grid, several
// targets, regulatory bundle), apply tariffs, a benefit covering several fees.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const FX=JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json','utf8'));
const admin=FX.C.users.ADMIN;const OUT='../.local/walk2';fs.mkdirSync(OUT,{recursive:true});
const http=[];const consoleErr=[];let failures=0;
const b=await chromium.launch({channel:'msedge'});
const ctx=await b.newContext({viewport:{width:1366,height:900}});const p=await ctx.newPage();
p.on('response',r=>{const u=new URL(r.url());if(u.pathname.startsWith('/api/')&&r.status()>=400)http.push(`${r.request().method()} ${u.pathname} → ${r.status()}`)});
p.on('console',m=>{if(m.type()==='error')consoleErr.push(m.text().slice(0,200))});
async function step(name,fn){const before=http.length;let status='OK',detail='';
  try{await fn();await p.waitForTimeout(500);
    const alerts=(await p.locator('[role=alert]:visible, .error:visible').allInnerTexts()).map(t=>t.trim()).filter(Boolean);
    if(alerts.length){status='ERREUR AFFICHÉE';detail=alerts.join(' | ').slice(0,300)}
  }catch(e){status='ÉCHEC';detail=String(e.message).split('\n')[0].slice(0,240)}
  if(status!=='OK')failures++;
  const newHttp=http.slice(before);console.log(`${status.padEnd(16)} ${name}${detail?` — ${detail}`:''}${newHttp.length?` [${newHttp.join(', ')}]`:''}`);
  await p.screenshot({path:`${OUT}/${name.replace(/[^a-z0-9]+/gi,'_').toLowerCase()}.png`,fullPage:true});}
const nav=()=>p.getByRole('complementary',{name:'Navigation principale'});
async function openTab(label){await p.locator('.sp-nav').getByRole('button',{name:new RegExp(`^${label}`)}).click();await p.waitForTimeout(600)}
const toast=t=>p.getByText(t).first().waitFor({timeout:30000});

await step('01 connexion',async()=>{await p.goto('http://localhost:5180/');await p.getByLabel('Adresse e-mail').fill(admin.email);await p.getByLabel('Mot de passe',{exact:true}).fill(admin.password);
  await p.getByRole('button',{name:'Se connecter'}).click();await p.locator('.es-shell').waitFor({timeout:30000})});
await step('02 paramètres',async()=>{await nav().getByRole('button',{name:'Paramètres',exact:true}).click();await p.getByRole('heading',{name:'Paramètres de l’établissement'}).waitFor()});

// ---- parallels per level
await step('10 classes : la grille part des parallèles déjà ouvertes',async()=>{await openTab('Structure & classes');await p.getByRole('button',{name:'Ouvrir des classes'}).click();
  const d=p.getByRole('dialog',{name:/Ouvrir des classes/});await d.locator('.sw-seg').first().getByRole('button',{name:'Primaire'}).click();
  await d.getByText(/Toutes les classes cochées sont déjà ouvertes/).waitFor({timeout:10000})});
await step('11 classes : 3 en 4e primaire seulement, les autres inchangées',async()=>{const d=p.getByRole('dialog',{name:/Ouvrir des classes/});
  await d.getByRole('button',{name:'Une classe de plus — 4e primaire'}).click();
  await d.getByText('4e primaire C').waitFor();const count=await d.locator('.sw-count').innerText();if(!/^1 classe à créer/.test(count))throw new Error(`compteur inattendu : ${count}`);
  await d.getByRole('button',{name:'Créer les classes'}).click();await d.waitFor({state:'detached',timeout:30000})});
await step('12 classes : « tout à 1 » ne crée jamais de classe sans lettre',async()=>{await p.getByRole('button',{name:'Ouvrir des classes'}).click();const d=p.getByRole('dialog',{name:/Ouvrir des classes/});
  await d.locator('.sw-seg').first().getByRole('button',{name:'Primaire'}).click();await d.locator('.sw-levels-quick').getByRole('button',{name:'1',exact:true}).click();
  await d.getByText(/Toutes les classes cochées sont déjà ouvertes/).waitFor();await d.getByRole('button',{name:'Annuler'}).click()});

// ---- fee edit / disable
await step('20 frais : modifier un frais existant',async()=>{await openTab('Types de frais');const row=p.locator('.cardsList article',{hasText:/^Frais de laboratoire/});
  await row.first().getByRole('button',{name:'Modifier'}).click();await p.getByLabel('Nom du frais',{exact:true}).fill('Frais de laboratoire et TP');
  await p.locator('.feeEdit').getByRole('button',{name:'Enregistrer'}).click();await toast('Frais de laboratoire et TP modifié')});
await step('21 frais : désactiver puis réactiver',async()=>{const row=p.locator('.cardsList article',{hasText:'Frais de laboratoire et TP'});
  await row.getByRole('button',{name:'Désactiver'}).click();await toast(/désactivé/);await row.getByRole('button',{name:'Réactiver'}).click();await toast(/réactivé/)});

// ---- tariff assistant
await step('30 tarifs : assistant, grille par niveau',async()=>{await openTab('Tarifs & barèmes');await p.getByRole('button',{name:'Assistant tarifaire'}).click();
  const d=p.getByRole('dialog',{name:/Assistant tarifaire/});await d.getByLabel('Frais *').selectOption({label:'Frais scolaires mensuels'});
  await d.getByLabel('Montant — Toute l’école').fill('15000');await d.getByLabel('Montant — 6e primaire').fill('20000');
  await d.locator('.ta-preview li',{hasText:/^6e primaire A/}).getByText(/20\s?000/).waitFor();
  await d.getByRole('button',{name:'Enregistrer la grille'}).click();await d.waitFor({state:'detached',timeout:60000});await toast(/règle\(s\) tarifaire\(s\) enregistrée\(s\)/)});
await step('31 tarifs : une règle pour 7e et 8e EB à la fois',async()=>{await p.getByRole('button',{name:'Règle sur plusieurs cibles'}).click();const d=p.getByRole('dialog',{name:/Assistant tarifaire/});
  await d.getByLabel('Frais *').selectOption({label:'Frais d’inscription'});await d.getByLabel('Portée').selectOption({label:'Niveau'});
  await d.getByRole('button',{name:'7e EB'}).click();await d.getByRole('button',{name:'8e EB'}).click();await d.getByLabel('Montant *').fill('25000');
  await d.getByText(/Cette règle s’appliquera à \d+ classe/).waitFor();await d.getByRole('button',{name:'Enregistrer',exact:true}).click();await d.waitFor({state:'detached',timeout:60000})});
await step('32 tarifs : frais réglementaires (desktop)',async()=>{await p.getByRole('button',{name:'Configurer les frais réglementaires'}).click();const d=p.getByRole('dialog',{name:/Assistant tarifaire/});
  await d.getByRole('button',{name:'Configurer les frais réglementaires'}).click();await d.waitFor({state:'detached',timeout:90000});await toast(/Frais réglementaires configurés/)});
await step('33 tarifs : règles visibles par frais',async()=>{for(const t of ['Frais de l’État','TENASOSP','Frais techniques','Frais scolaires mensuels'])await p.locator('.tariffGroup h4',{hasText:t}).first().waitFor({timeout:15000})});
await step('34 tarifs : appliquer les barèmes',async()=>{await p.getByRole('button',{name:'Appliquer les barèmes aux classes ouvertes'}).click();
  await p.getByRole('button',{name:'Appliquer les barèmes',exact:true}).last().click();await toast(/échéance\(s\) appliquée\(s\)/)});

// ---- benefit covering several fees
await step('40 avantages : enfants du personnel sur deux frais',async()=>{await openTab('Avantages');const card=p.locator('form.benefitCard',{hasText:'Enfants du personnel'});
  for(const f of ['Frais scolaires mensuels','Frais de l’État']){const c=card.getByLabel(f,{exact:true});if(!await c.isChecked())await c.check()}
  await card.getByRole('button',{name:'Enregistrer'}).click();await toast('Politique Enfants du personnel enregistrée')});
await step('41 avantages : les deux frais restent cochés après rechargement',async()=>{await p.reload();await nav().getByRole('button',{name:'Paramètres',exact:true}).click().catch(()=>{});await openTab('Avantages');
  const card=p.locator('form.benefitCard',{hasText:'Enfants du personnel'});for(const f of ['Frais scolaires mensuels','Frais de l’État'])if(!await card.getByLabel(f,{exact:true}).isChecked())throw new Error(`${f} non coché après rechargement`);
  await p.getByText('Exonérations individuelles').waitFor()});

console.log(`\n${failures} échec(s) · erreurs HTTP : ${http.length ? http.join(', ') : 'aucune'} · console : ${consoleErr.length ? consoleErr.slice(0, 5).join(' | ') : 'aucune'}`);
await b.close();
process.exit(failures ? 1 : 0);
