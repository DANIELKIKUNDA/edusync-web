// Phone settings navigation: section opens as a screen; "‹ Paramètres" and the system back both return to the list.
import {connect, delay, fx, signInSchool} from './cdp.mjs';
const admin = fx.A.users.ADMIN;
const p = await connect();
await p.viewport(390, 844);
await p.go(); await delay(1500);
if (!await p.ev('!!document.querySelector(".es-shell")')) { await signInSchool(p, admin.email, admin.password); await p.waitFor('!!document.querySelector(".es-shell")'); }
await delay(1000);
await p.ev('[...document.querySelectorAll(".es-bottom button, .es-bottom a")].find(b=>/Menu|Plus/.test(b.innerText))?.click()'); await delay(600);
await p.click('Paramètres'); await p.waitFor('!!document.querySelector(".settingsNav")'); await delay(800);
const state = () => p.ev('JSON.stringify({list:!!document.querySelector(".settingsNav")?.offsetParent,section:!!document.querySelector(".settingsContent")?.offsetParent,head:!!document.querySelector(".settingsHeader")?.offsetParent})');
const tap = label => p.ev(`[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes(${JSON.stringify(label)}))?.click()`);
console.log('liste', await state());
await tap('Années scolaires'); await delay(600); console.log('section', await state());
await p.ev('document.querySelector(".settingsBack").click()'); await delay(700); console.log('après ‹ Paramètres', await state());
await tap('Tarifs & barèmes'); await delay(600); console.log('section', await state());
await p.ev('history.back()'); await delay(800); console.log('après retour système', await state(), 'module', await p.ev('document.querySelector(".es-top h1, .es-title")?.innerText||""'));
await p.ev('history.back()'); await delay(800); console.log('2e retour système', await state());
process.exit(0);
