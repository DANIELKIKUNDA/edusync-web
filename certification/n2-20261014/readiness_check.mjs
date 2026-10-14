// Guided start: "Prochaine étape" opens the section that settles it. School C (incomplete) on phone, school A (ready) on desktop.
import {connect, delay, fx, signInSchool, signOut} from './cdp.mjs';

const p = await connect();
async function openReadiness(phone) {
  if (phone) { await p.ev('[...document.querySelectorAll(".es-bottom button")].find(b=>/Menu/.test(b.innerText))?.click()'); await delay(600); }
  await p.click('Paramètres'); await p.waitFor('!!document.querySelector(".settingsNav")'); await delay(800);
  await p.ev('[...document.querySelectorAll(".settingsNav button")].find(b=>b.innerText.includes("Mise en service")).click()');
  await p.waitFor('!!document.querySelector(".nextStep")', 15000); await delay(300);
}
for (const [school, w] of [['C', 390], ['A', 1280]]) {
  const admin = fx[school].users.ADMIN;
  await p.viewport(w, w < 768 ? 844 : 900); await p.go(); await delay(1200);
  await signOut(p); await p.go(); await delay(1000);
  await signInSchool(p, admin.email, admin.password); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
  await openReadiness(w < 768);
  console.log(school, w, 'prochaine étape :', JSON.stringify(await p.ev('document.querySelector(".nextStep").innerText')));
  await p.shot(`settings-readiness-${school}-${w}`, true);
  const hasNext = await p.ev('!!document.querySelector(".nextStep .primaryBtn")');
  if (hasNext) {
    await p.ev('document.querySelector(".nextStep .primaryBtn").click()'); await delay(900);
    console.log(school, w, 'section ouverte :', await p.ev('document.querySelector(".settingsContent h3")?.innerText || "?"'));
    await p.shot(`settings-readiness-next-${school}-${w}`, true);
  }
}
process.exit(0);
