// Tarifs & barèmes (parity lot L1): rules by target, pending status, new-rule form, billing months — phone and desktop.
import {connect, delay} from './cdp.mjs';
const p = await connect();
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await delay(1800);
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
    await p.ev('[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.includes("Paramètres")).click()'); }
  else await p.ev('[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||"").includes("Paramètres")).click()');
  await p.waitFor('!!document.querySelector(".settingsNav")'); await delay(700);
  await p.ev('[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes("Tarifs")).click()'); await delay(1500);
  console.log(w, 'règles', await p.ev('document.querySelectorAll(".tariffGroup li").length'), 'mois', await p.ev('document.querySelectorAll(".monthGrid input:checked").length'));
  await p.shot(`tariffs-l1-${w}`, true);
  await p.ev('document.querySelector(".addLine")?.click()'); await delay(400);
  await p.ev('(()=>{const s=[...document.querySelectorAll(".ruleForm select")][1];s.value="OPTION_GROUP";s.dispatchEvent(new Event("change",{bubbles:true}))})()'); await delay(300);
  console.log(w, 'cibles groupe', await p.ev('JSON.stringify([...[...document.querySelectorAll(".ruleForm select")][2].options].map(o=>o.text))'));
  const m = await p.metrics(); console.log(w, 'hscroll', m.hscroll);
  await p.shot(`tariffs-l1-form-${w}`, true);
}
process.exit(0);
