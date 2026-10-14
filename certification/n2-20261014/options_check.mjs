// Options (filières) of a section: add, shown as chip, deactivation confirmed. Uses school A of the certification database.
import {connect, delay} from './cdp.mjs';
const p = await connect();
await p.viewport(390, 844); await p.go(); await delay(1800);
await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText))?.click()'); await delay(600);
await p.click('Paramètres'); await p.waitFor('!!document.querySelector(".settingsNav")'); await delay(800);
await p.ev('[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes("Structure")).click()'); await delay(1200);
const label = 'Option certification N2 ' + Date.now().toString(36);
await p.ev('document.querySelector(".addChip").click()'); await delay(300);
await p.type('.optionDraft input', label); await p.ev('document.querySelector(".optionDraft .primaryBtn").click()'); await delay(1500);
const chip = `[...document.querySelectorAll(".optionChips button")].find(b=>b.innerText.startsWith(${JSON.stringify(label)}))`;
console.log('ajoutée', await p.ev(`!!${chip}`), await p.ev(`${chip}?.className`));
await p.shot('settings-options-390', true);
await p.ev(`${chip}.click()`); await delay(400); console.log('confirmation', await p.ev('document.querySelector(".eduDialog h3")?.innerText'));
await p.ev('document.querySelector(".eduDialogActions button[type=submit]").click()'); await delay(1500);
console.log('après désactivation', await p.ev(`${chip}?.className`), await p.ev(`${chip}?.innerText`));
const m = await p.metrics(); console.log('hscroll', m.hscroll);
process.exit(0);
