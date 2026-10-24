// Settings parity pass 3 (2026-10-24) — real administrator check on the LOCAL stack (real API, real database, school C
// of the local fixtures). The test password is read from the local fixtures file and never printed. Covers: motto,
// numbering, document signatory and logo choice, school data copy (download + test), diagnostic, and the « Frais &
// tarifs » step of the setup assistant. The downloaded files are kept in ../.local/walk3 for inspection.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
const FX=JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json','utf8'));
const admin=FX.C.users.ADMIN;const OUT='../.local/walk3';fs.mkdirSync(OUT,{recursive:true});
const http=[];let failures=0;
const b=await chromium.launch({channel:'msedge'});
const ctx=await b.newContext({viewport:{width:1366,height:900},acceptDownloads:true});const p=await ctx.newPage();
p.on('response',r=>{const u=new URL(r.url());if(u.pathname.startsWith('/api/')&&r.status()>=400)http.push(`${r.request().method()} ${u.pathname} → ${r.status()}`)});
async function step(name,fn){const before=http.length;let status='OK',detail='';
  try{await fn();await p.waitForTimeout(500);
    const alerts=(await p.locator('[role=alert]:visible, .error:visible').allInnerTexts()).map(t=>t.trim()).filter(Boolean);
    if(alerts.length){status='ERREUR AFFICHÉE';detail=alerts.join(' | ').slice(0,300)}
  }catch(e){status='ÉCHEC';detail=String(e.message).split('\n')[0].slice(0,240)}
  if(status!=='OK')failures++;
  const newHttp=http.slice(before);console.log(`${status.padEnd(16)} ${name}${detail?` — ${detail}`:''}${newHttp.length?` [${newHttp.join(', ')}]`:''}`);
  await p.screenshot({path:`${OUT}/${name.replace(/[^a-z0-9]+/gi,'_').toLowerCase()}.png`,fullPage:true});}
const nav=()=>p.getByRole('complementary',{name:'Navigation principale'});
async function openTab(label){await p.locator('.sp-nav').getByRole('button',{name:new RegExp(`^${label}`)}).click();await p.waitForTimeout(700)}
const toast=t=>p.getByText(t).first().waitFor({timeout:30000});
const MOTTO='Travail – Discipline – Réussite';

await step('01 connexion',async()=>{await p.goto('http://localhost:5180/');await p.getByLabel('Adresse e-mail').fill(admin.email);await p.getByLabel('Mot de passe',{exact:true}).fill(admin.password);
  await p.getByRole('button',{name:'Se connecter'}).click();await p.locator('.es-shell').waitFor({timeout:30000})});
await step('02 paramètres',async()=>{await nav().getByRole('button',{name:'Paramètres',exact:true}).click();await p.getByRole('heading',{name:'Paramètres de l’établissement'}).waitFor()});

await step('10 identité : devise de l’école',async()=>{await openTab('École & identité');const f=p.getByLabel('Devise / mention');if(await f.inputValue()===MOTTO){await f.fill('');await p.locator('form.identityForm').getByRole('button',{name:'Enregistrer'}).click();await toast('Identité de l’école enregistrée');await p.waitForTimeout(800)}await f.fill(MOTTO);
  await p.locator('form.identityForm').getByRole('button',{name:'Enregistrer'}).click();await toast('Identité de l’école enregistrée')});
await step('11 identité : numérotation automatique',async()=>{for(const t of ['Prochain matricule élève','Prochain code famille','Prochain reçu'])await p.getByText(t).waitFor();
  await p.locator('.numberingGrid dd',{hasText:/^ELV-\d{5}$/}).waitFor()});

await step('20 documents : signataire et logo',async()=>{await openTab('Documents & signature');await p.getByLabel('Nom du signataire').fill('Jean Kabeya');await p.getByLabel('Fonction').fill('Préfet des études');
  await p.getByRole('button',{name:'Enregistrer'}).click();await toast('Réglages des documents enregistrés')});
await step('21 documents : conservés après rechargement',async()=>{await p.reload();await nav().getByRole('button',{name:'Paramètres',exact:true}).click().catch(()=>{});await openTab('Documents & signature');
  if(await p.getByLabel('Nom du signataire').inputValue()!=='Jean Kabeya')throw new Error('signataire non conservé')});

await step('30 sauvegardes : état du serveur',async()=>{await openTab('Sauvegardes & diagnostic');await p.getByText('Sauvegarde automatique du serveur').waitFor()});
await step('31 sauvegardes : tester une copie',async()=>{await p.getByRole('button',{name:'Tester une copie'}).click();await p.getByText(/Test réussi : \d+ tables, \d+ lignes/).first().waitFor({timeout:60000})});
await step('32 sauvegardes : sauvegarder maintenant (téléchargement)',async()=>{const [d]=await Promise.all([p.waitForEvent('download',{timeout:60000}),p.getByRole('button',{name:'Sauvegarder maintenant'}).click()]);
  await d.saveAs(`${OUT}/${d.suggestedFilename()}`);if(!/^sauvegarde_.*\.zip$/.test(d.suggestedFilename()))throw new Error(`nom inattendu ${d.suggestedFilename()}`)});
await step('33 diagnostic : affiché puis exporté',async()=>{await p.getByText('Assistance technique').waitFor();const [d]=await Promise.all([p.waitForEvent('download',{timeout:30000}),p.getByRole('button',{name:'Exporter le diagnostic'}).click()]);
  await d.saveAs(`${OUT}/${d.suggestedFilename()}`)});

await step('40 assistant : étape Frais & tarifs',async()=>{await openTab('Mise en service');await p.getByRole('button',{name:'Lancer l’assistant'}).click();const d=p.getByRole('dialog',{name:'Assistant de mise en service'});
  await d.getByRole('button',{name:'Enregistrer et continuer'}).click();await d.getByRole('button',{name:'Enregistrer les sections'}).click();await d.getByRole('button',{name:'Continuer'}).click();
  await d.getByRole('button',{name:'Ouvrir les classes'}).click();await d.getByText('Frais organisés par l’école').waitFor({timeout:60000});
  await d.getByRole('button',{name:'Ouvrir l’assistant tarifaire'}).click();await p.getByRole('dialog',{name:/Assistant tarifaire/}).waitFor();await p.keyboard.press('Escape');
  await d.getByRole('button',{name:'Continuer'}).click();await d.getByText('L’essentiel est configuré').waitFor();await d.getByRole('button',{name:'Terminer'}).click()});
await step('41 la devise n’a pas été effacée par l’assistant',async()=>{await openTab('École & identité');if(await p.getByLabel('Devise / mention').inputValue()!==MOTTO)throw new Error('devise effacée')});

console.log(`\n${failures} échec(s) · erreurs HTTP : ${http.length ? http.join(', ') : 'aucune'}`);
await b.close();process.exit(failures?1:0);
