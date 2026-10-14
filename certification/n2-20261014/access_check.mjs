// Visual check of the N2 member management screens (school A administrator), phone then desktop.
import {connect, delay, fx, signInSchool} from './cdp.mjs';

const admin = fx.A.users.ADMIN;
const p = await connect();
await p.viewport(1280, 900);
await signInSchool(p, admin.email, admin.password);
await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
await p.click('Accès & rôles'); await p.waitFor('!!document.querySelector(".memberList")'); await delay(1200);
for (const w of [390, 1280]) {
  await p.viewport(w, w < 768 ? 844 : 900); await delay(700);
  await p.ev('window.scrollTo(0,0)'); await p.shot(`access-members-${w}`);
  const m = await p.metrics(); console.log(w, 'hscroll', m.hscroll, 'hauteur', m.h, 'cibles<36', m.smallTargets);
  await p.ev('[...document.querySelectorAll(".memberRow")].find(b=>!b.innerText.includes("Vous"))?.click()'); await p.waitFor('!!document.querySelector(".memberSheet")'); await delay(700);
  await p.shot(`access-sheet-${w}`);
  await p.ev('document.querySelector(".memberSheet .iconAction")?.click()'); await delay(500);
  await p.click('Ajouter un membre'); await p.waitFor('!!document.querySelector(".addMemberDialog")'); await delay(500);
  await p.shot(`access-add-${w}`);
  await p.ev('document.querySelector(".addMemberDialog button[type=button]")?.click()'); await delay(400);
}
process.exit(0);
