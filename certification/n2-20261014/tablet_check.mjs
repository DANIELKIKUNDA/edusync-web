// Tablet settings navigation and phone tariffs order (list before the collapsed add form).
import {connect, delay} from './cdp.mjs';
const p = await connect();
await p.viewport(768, 1024); await p.go(); await delay(1800);
await p.ev('[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||"").includes("Paramètres")).click()'); await p.waitFor('!!document.querySelector(".settingsNav")'); await delay(800);
await p.ev('[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes("Structure")).click()'); await delay(900);
console.log('768 nav', await p.ev('JSON.stringify({display:getComputedStyle(document.querySelector(".settingsNav")).display,scroll:document.querySelector(".settingsNav").scrollWidth>document.querySelector(".settingsNav").clientWidth+1,hscroll:document.documentElement.scrollWidth>innerWidth})'));
await p.shot('tablet-settings-structure-768');
await p.viewport(390, 844); await p.go(); await delay(1800);
await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
await p.ev('[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.includes("Paramètres")).click()'); await p.waitFor('!!document.querySelector(".settingsNav")'); await delay(800);
await p.ev('[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes("Tarifs")).click()'); await delay(900);
console.log('390 tarifs', await p.ev('JSON.stringify({listTop:Math.round(document.querySelector(".moneyList")?.getBoundingClientRect().top),form:!!document.querySelector(".settingsContent form"),add:!!document.querySelector(".addLine")})'));
await p.shot('phone-settings-tariffs-390');
await p.ev('document.querySelector(".addLine").click()'); await delay(400);
console.log('formulaire ouvert', await p.ev('!!document.querySelector(".settingsContent form")'));
await p.ev('document.querySelector(".formActions .ghost").click()'); await delay(300);
process.exit(0);
