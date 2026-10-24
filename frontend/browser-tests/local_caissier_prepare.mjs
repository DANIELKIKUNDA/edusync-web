// Cashier certification, preparation (2026-10-24): the administrator creates a cashier with the « Ajouter un membre »
// form, the cashier signs in and replaces the temporary password; every visible module is captured. The account is kept
// in ../.local/caissier/.account.json (local only, never printed) for local_caissier_certification.mjs.
import {chromium} from '@playwright/test';
import fs from 'node:fs';
import crypto from 'node:crypto';
const FX=JSON.parse(fs.readFileSync('../.local/claude-fixtures-edusync_claude_fresh.json','utf8'));const a=FX.C.users.ADMIN;
const OUT='../.local/caissier';fs.mkdirSync(OUT,{recursive:true});
const RUN=Date.now().toString(36).slice(-4);const email=`caissier-${RUN}@example.test`;
const b=await chromium.launch({channel:'msedge'});
let p=await (await b.newContext({viewport:{width:1440,height:900}})).newPage();
await p.goto('http://localhost:5180/');await p.getByLabel('Adresse e-mail').fill(a.email);await p.getByLabel('Mot de passe',{exact:true}).fill(a.password);
await p.getByRole('button',{name:'Se connecter'}).click();await p.locator('.es-shell').waitFor({timeout:30000});
await p.getByRole('complementary',{name:'Navigation principale'}).getByRole('button',{name:'Accès & rôles',exact:true}).click();
await p.getByRole('button',{name:'Ajouter un membre'}).click();const d=p.getByRole('dialog',{name:'Ajouter un membre'});
await d.getByLabel('Nom complet *').fill('Caissière Certification');await d.getByLabel('Adresse e-mail *').fill(email);
await d.getByLabel('Rechercher un rôle').fill('caiss');await d.getByRole('radio',{name:/Caissier/}).click();await d.getByRole('button',{name:'Ajouter le membre'}).click();
const code=(await p.locator('.secretBox code').innerText()).trim();await p.getByLabel('J’ai noté ou transmis ce mot de passe').check();await p.getByRole('button',{name:'Terminer'}).click();
await p.context().close();
p=await (await b.newContext({viewport:{width:1440,height:900}})).newPage();
await p.goto('http://localhost:5180/');await p.getByLabel('Adresse e-mail').fill(email);await p.getByLabel('Mot de passe',{exact:true}).fill(code);await p.getByRole('button',{name:'Se connecter'}).click();
const pw=`Cs-${crypto.randomBytes(6).toString('hex')}-Ok`;
await p.getByLabel('Nouveau mot de passe').fill(pw);await p.getByLabel('Confirmer le mot de passe').fill(pw);await p.getByRole('button',{name:/Enregistrer|Changer|Valider/}).first().click();
await p.locator('.es-shell').waitFor({timeout:40000});await p.waitForTimeout(2000);
fs.writeFileSync('../.local/caissier/.account.json',JSON.stringify({email,password:pw}));   // local only, never printed
await p.screenshot({path:`${OUT}/00_accueil.png`,fullPage:true});
const items=await p.getByRole('complementary',{name:'Navigation principale'}).getByRole('button').allInnerTexts();
console.log('menu :',items.map(x=>x.trim()).filter(Boolean).join(' | '));
for(const m of items.map(x=>x.trim()).filter(x=>x&&!/Accueil|EduSync/.test(x))){try{await p.getByRole('complementary',{name:'Navigation principale'}).getByRole('button',{name:m,exact:true}).click();await p.waitForTimeout(2500);await p.screenshot({path:`${OUT}/${m.replace(/[^a-z0-9]+/gi,'_')}.png`,fullPage:true});}catch(e){console.log('module',m,'non ouvert')}}
await b.close();
