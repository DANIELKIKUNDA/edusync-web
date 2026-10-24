// Real administrator walkthrough of the school settings on the LOCAL stack (real API, real database, fresh school C of
// the local fixtures). Never committed with credentials: the test password is read from the local fixtures file.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const FX=JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json','utf8'));
const admin=FX.C.users.ADMIN;const OUT='../.local/walk';fs.mkdirSync(OUT,{recursive:true});
const report=[];const http=[];const consoleErr=[];
const b=await chromium.launch({channel:'msedge'});
const ctx=await b.newContext({viewport:{width:1366,height:900}});const p=await ctx.newPage();
p.on('response',r=>{const u=new URL(r.url());if(u.pathname.startsWith('/api/')&&r.status()>=400)http.push(`${r.request().method()} ${u.pathname} → ${r.status()}`)});
p.on('console',m=>{if(m.type()==='error')consoleErr.push(m.text().slice(0,200))});
const shot=async n=>p.screenshot({path:`${OUT}/${n}.png`,fullPage:true});
async function step(name,fn){const before=http.length;let status='OK',detail='';
  try{await fn();await p.waitForTimeout(700);
    const alerts=(await p.locator('[role=alert]:visible, .error:visible').allInnerTexts()).map(t=>t.trim()).filter(Boolean);
    if(alerts.length){status='ERREUR AFFICHÉE';detail=alerts.join(' | ').slice(0,300)}
  }catch(e){status='ÉCHEC';detail=String(e.message).split('\n')[0].slice(0,240)}
  const newHttp=http.slice(before);report.push({name,status,detail,http:newHttp});console.log(`${status.padEnd(16)} ${name}${detail?` — ${detail}`:''}${newHttp.length?` [${newHttp.join(', ')}]`:''}`);
  await shot(name.replace(/[^a-z0-9]+/gi,'_').toLowerCase());}
const nav=()=>p.getByRole('complementary',{name:'Navigation principale'});
async function openTab(label){await p.locator('.sp-nav').getByRole('button',{name:new RegExp(`^${label}`)}).click();await p.waitForTimeout(500)}

await step('01 connexion',async()=>{await p.goto('http://localhost:5180/');await p.getByLabel('Adresse e-mail').fill(admin.email);await p.getByLabel('Mot de passe',{exact:true}).fill(admin.password);
  await p.getByRole('button',{name:'Se connecter'}).click();await p.locator('.es-shell').waitFor({timeout:20000})});
await step('02 accueil administrateur',async()=>{await p.getByText(/Bonjour/).first().waitFor()});
await step('03 paramètres (vierge)',async()=>{await nav().getByRole('button',{name:'Paramètres',exact:true}).click();await p.getByRole('heading',{name:'Paramètres de l’établissement'}).waitFor()});

// ---- assistant de mise en service
await step('04 assistant étape 1 école et année',async()=>{await p.getByRole('button',{name:'Lancer l’assistant'}).click();const d=p.getByRole('dialog',{name:'Assistant de mise en service'});
  await d.getByLabel('Nom officiel *').fill('Complexe Scolaire Les Bâtisseurs');await d.getByLabel('Téléphone').fill('+243 970 000 111');await d.getByLabel('E-mail').fill('direction@batisseurs.cd');
  await d.getByLabel('Adresse').fill('Av. Kasaï n° 12, quartier Makutano');await d.getByLabel('Ville').fill('Lubumbashi');await d.getByLabel('Province').fill('Haut-Katanga');
  await d.getByRole('button',{name:'Enregistrer et continuer'}).click();await d.getByText('Sections organisées par l’école').waitFor({timeout:15000})});
await step('05 assistant étape 2 sections',async()=>{const d=p.getByRole('dialog',{name:'Assistant de mise en service'});
  for(const s of ['Maternelle','Primaire','Secondaire']){const c=d.getByRole('button',{name:s});if((await c.getAttribute('aria-pressed'))!=='true')await c.click()}
  await d.getByRole('button',{name:'Enregistrer les sections'}).click();await d.getByText(/Humanités générales|Pas de section Secondaire/).first().waitFor({timeout:15000})});
await step('06 assistant étape 3 options humanités',async()=>{const d=p.getByRole('dialog',{name:'Assistant de mise en service'});
  for(const o of ['Commerciale et gestion','Scientifique','Électricité']){await d.getByRole('button',{name:o}).click();await p.waitForTimeout(600)}
  await d.getByRole('button',{name:'Continuer'}).click()});
await step('07 assistant étape 4 classes parallèles',async()=>{const d=p.getByRole('dialog',{name:'Assistant de mise en service'});await d.getByRole('button',{name:/2 classes \(A, B\)/}).click();
  await d.getByRole('button',{name:'Ouvrir les classes'}).click();await d.getByText('L’essentiel est configuré').waitFor({timeout:60000})});
await step('08 assistant terminé',async()=>{await p.getByRole('dialog',{name:'Assistant de mise en service'}).getByRole('button',{name:'Terminer'}).click()});

// ---- onglet par onglet
await step('10 école et identité : enregistrer',async()=>{await openTab('École & identité');await p.getByLabel(/Téléphone/).first().fill('+243 970 000 222');await p.getByRole('button',{name:'Enregistrer'}).last().click();
  await p.getByText('Identité de l’école enregistrée').waitFor({timeout:10000})});
await step('11 années scolaires',async()=>{await openTab('Années scolaires');await p.getByText(/2026|2027|2025/).first().waitFor()});
await step('12 structure et classes',async()=>{await openTab('Structure & classes');await p.getByText(/Pas d’options en Primaire/).waitFor()});
await step('13 structure : ajouter une parallèle C',async()=>{await p.getByRole('button',{name:'Ouvrir des classes'}).click();const d=p.getByRole('dialog',{name:/Ouvrir des classes/});
  await d.getByRole('button',{name:'Primaire'}).click();for(const r of await d.locator('.sw-field').nth(1).getByRole('button').all()){if((await r.getAttribute('aria-pressed'))==='true')await r.click()}
  await d.getByRole('button',{name:'1re primaire'}).click();await d.getByRole('button',{name:/3 \(A, B, C\)/}).click();await d.getByText('1re primaire C').waitFor();
  await d.getByRole('button',{name:'Créer les classes'}).click();await d.waitFor({state:'detached',timeout:20000})});
await step('14 types de frais : modèles + personnalisé',async()=>{await openTab('Types de frais');for(const f of ['Frais d’inscription','Frais scolaires mensuels','Examen d’État']){await p.getByRole('button',{name:new RegExp(f)}).click();await p.waitForTimeout(700)}
  await p.getByLabel('Nom du frais personnalisé').fill('Frais de laboratoire');await p.getByRole('button',{name:'Créer'}).click();await p.getByText('Frais de laboratoire ajouté').waitFor({timeout:10000})});
await step('15 tarifs et barèmes',async()=>{await openTab('Tarifs & barèmes')});
await step('16 inscriptions',async()=>{await openTab('Inscriptions')});
await step('17 avantages',async()=>{await openTab('Avantages')});
await step('18 encaissement',async()=>{await openTab('Encaissement')});
await step('19 plans anticipés',async()=>{await openTab('Plans anticipés')});
await step('20 contributions : modèle savon',async()=>{await openTab('Contributions en nature');await p.getByRole('button',{name:'+ Savon'}).click();await p.getByRole('button',{name:'Ajouter'}).click();await p.getByText('Contribution créée').waitFor({timeout:10000})});
await step('21 articles : pull scolaire',async()=>{await openTab('Articles scolaires');await p.getByRole('button',{name:'+ Pull scolaire'}).click();await p.getByLabel('Prix').fill('15000');await p.getByRole('button',{name:'Ajouter'}).click();await p.getByText('Article créé').waitFor({timeout:10000})});
await step('22 mise en service après parcours',async()=>{await openTab('Mise en service')});
// mobile
await p.setViewportSize({width:390,height:844});
await step('30 mobile paramètres',async()=>{await p.reload();await p.waitForTimeout(1500)});
fs.writeFileSync(`${OUT}/report.json`,JSON.stringify({report,http,consoleErr},null,1));
console.log('\nHTTP >= 400 :',http.length?http.join(' ; '):'aucun');console.log('Erreurs console :',consoleErr.length?consoleErr.slice(0,8).join(' ; '):'aucune');
await b.close();
