import {connect, delay, fx, signInSchool} from './cdp.mjs';
const p = await connect(); await p.viewport(390, 844);
await signInSchool(p, fx.A.users.ADMIN.email, fx.A.users.ADMIN.password); await p.waitFor('!!document.querySelector(".es-shell")'); await delay(1000);
await p.viewport(1280, 900); await p.click('Accès & rôles'); await p.viewport(390, 844); await p.waitFor('!!document.querySelector(".memberRow")'); await delay(800);
await p.ev('[...document.querySelectorAll(".memberRow")].find(b=>!b.innerText.includes("Vous"))?.click()'); await delay(900);
console.log(JSON.stringify(await p.ev(`(()=>{const s=document.querySelector(".memberSheet"),b=document.querySelector(".sheetBackdrop");if(!s)return 'absent';const r=s.getBoundingClientRect(),cs=getComputedStyle(s),bs=getComputedStyle(b);
 return {sheet:[r.x,r.y,r.width,r.height].map(Math.round),display:cs.display,transform:cs.transform,opacity:cs.opacity,anim:cs.animationName,backdrop:[bs.display,bs.alignItems,bs.justifyContent,bs.zIndex],parentTag:b.parentElement.className.slice(0,40)}})()`)));
process.exit(0);
