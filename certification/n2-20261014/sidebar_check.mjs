// Checks that the desktop sidebar stays fixed (full viewport height) while a long page scrolls.
import {connect, delay, fx, signInSchool} from './cdp.mjs';

const admin = fx.A.users.ADMIN;
const p = await connect();
await p.viewport(1280, 800);
await signInSchool(p, admin.email, admin.password);
await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1200);
await p.click('Accès & rôles'); await delay(2500);
const measure = () => p.ev(`(()=>{const s=document.querySelector(".es-side").getBoundingClientRect();const cs=getComputedStyle(document.querySelector(".es-side"));
  return {scrollY:Math.round(scrollY),top:Math.round(s.top),height:Math.round(s.height),viewport:innerHeight,position:cs.position,docHeight:document.documentElement.scrollHeight}})()`);
console.log('avant défilement', JSON.stringify(await measure()));
await p.ev('window.scrollTo(0, 1800)'); await delay(600);
console.log('après défilement', JSON.stringify(await measure()));
await p.shot('sidebar-scrolled-1280');
process.exit(0);
