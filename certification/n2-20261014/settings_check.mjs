// Visual check of the N2 settings centre (school A administrator): phone list → section, then desktop.
import {connect, delay, fx, signInSchool} from './cdp.mjs';

const admin = fx.A.users.ADMIN;
const p = await connect();
await p.viewport(1280, 900);
await signInSchool(p, admin.email, admin.password);
await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
await p.click('Paramètres'); await p.waitFor('!!document.querySelector(".settingsNav")'); await delay(1000);
const openSection = async label => { await p.ev(`[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes(${JSON.stringify(label)}))?.click()`); await delay(800); };
const back = async () => { await p.ev('document.querySelector(".settingsBack")?.click()'); await delay(600); };
const report = async name => { const m = await p.metrics(); console.log(name, 'hscroll', m.hscroll, 'cibles<36', m.smallTargets, 'visible', await p.ev('JSON.stringify({nav:!!document.querySelector(".settingsNav")?.offsetParent,content:!!document.querySelector(".settingsContent")?.offsetParent})')); };

await p.viewport(390, 844); await delay(700); await p.ev('window.scrollTo(0,0)');
await report('home-390'); await p.shot('settings-home-390');
for (const [label, key] of [['Années scolaires', 'years'], ['École & identité', 'identity'], ['Structure & classes', 'structure'], ['Tarifs & barèmes', 'tariffs'], ['Articles scolaires', 'products']]) {
  await openSection(label); await report(`${key}-390`); await p.shot(`settings-${key}-390`, true);
  if (key === 'years') {
    await p.click('Préparer une nouvelle année').catch(() => {}); await delay(500); await p.shot('settings-years-create-390', true);
    await p.ev('[...document.querySelectorAll(".rowActions button")].find(b=>/Clôturer|Activer/.test(b.innerText))?.click()'); await delay(500);
    await p.shot('settings-years-confirm-390'); console.log('confirm dialog', await p.ev('document.querySelector(".eduDialog")?.innerText||"none"'));
    await p.ev('document.querySelector(".eduDialogActions .ghost")?.click()'); await delay(300);
  }
  await back();
}
console.log('back to list', await p.ev('!!document.querySelector(".settingsNav")?.offsetParent'));
await p.viewport(1280, 900); await delay(700);
for (const [label, key] of [['Années scolaires', 'years'], ['École & identité', 'identity'], ['Structure & classes', 'structure'], ['Tarifs & barèmes', 'tariffs']]) {
  await openSection(label); await report(`${key}-1280`); await p.shot(`settings-${key}-1280`);
}
process.exit(0);
