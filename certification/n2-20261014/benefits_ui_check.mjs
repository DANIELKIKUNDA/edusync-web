// Avantages (parity lot L3): the two Desktop policies (large family, staff children) — phone and desktop.
import {connect, delay} from './cdp.mjs';
const p = await connect();
for (const [w, h] of [[390, 844], [1280, 900]]) {
  await p.viewport(w, h); await p.go(); await delay(1800);
  if (w < 768) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText)).click()'); await delay(500);
    await p.ev('[...document.querySelectorAll(".es-drawer-nav button")].find(b=>b.innerText.includes("Paramètres")).click()'); }
  else await p.ev('[...document.querySelectorAll(".es-nav button")].find(b=>(b.getAttribute("aria-label")||"").includes("Paramètres")).click()');
  await p.waitFor('!!document.querySelector(".settingsNav")'); await delay(700);
  await p.ev('[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes("Avantages")).click()'); await delay(1500);
  console.log(w, 'politiques', await p.ev('document.querySelectorAll(".benefitCard").length'));
  await p.shot(`benefits-l3-${w}`, true);
  const m = await p.metrics(); console.log(w, 'hscroll', m.hscroll);
  }
process.exit(0);
