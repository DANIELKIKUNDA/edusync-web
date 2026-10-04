import fs from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';
const dir=new URL('./',import.meta.url);
const fixtures=JSON.parse(await fs.readFile(new URL('../../.local/http-fixtures.json',dir),'utf8'));
const targets=await(await fetch('http://127.0.0.1:59222/json')).json();
const target=targets.find(x=>x.type==='page');if(!target)throw Error('No isolated Edge target');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});
let sequence=0;const pending=new Map(),exceptions=[],httpErrors=[];
socket.onmessage=event=>{
 const m=JSON.parse(event.data);
 if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}}
 if(m.method==='Runtime.exceptionThrown')exceptions.push(m.params.exceptionDetails.text);
 if(m.method==='Network.responseReceived'){const r=m.params.response;if(r.status>=400&&r.url.includes('/api/'))httpErrors.push({path:new URL(r.url).pathname,status:r.status})}
};
function call(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>reject(Error('CDP timeout '+method)),45000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value}
async function until(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await delay(300)}throw Error('UI readiness timeout')}
await call('Runtime.enable');await call('Page.enable');await call('Network.enable');
await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
await call('Page.navigate',{url:'http://127.0.0.1:55174/'});
await until('document.readyState==="complete"');
const f=fixtures.A;
const status=await evaluate(`(async()=>{const r=await fetch('/api/v1/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({scope:'SCHOOL',school_code:f.code,email:f.email,password:f.password})})});return r.status})()`);
if(status!==200)throw Error('Browser login HTTP '+status);
await call('Page.reload');await until('!!document.querySelector(".smartShell")');
httpErrors.length=0;
const modules=await evaluate('[...document.querySelectorAll(".smartNav .navLabel")].map(e=>e.textContent)');
const results=[];
for(let index=0;index<modules.length;index++){
 const label=modules[index];
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
 await evaluate(`document.querySelectorAll('.smartNav button')[${index}].click()`);
 await delay(1800);
 for(const width of [320,360,390,430,768,1440]){
  await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<768});await delay(200);
  const metrics=await evaluate(`(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,heading:document.querySelector('.smartTopbar h1')?.textContent,mainPresent:!!document.querySelector('.smartMain'),storageKeys:Object.keys(localStorage).filter(k=>/token|session/i.test(k)),overflowElements:[...document.querySelectorAll('main *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.right>innerWidth+2&&getComputedStyle(e).position!=='fixed'&&!e.closest('.tableWrap,.tableScroll,.table-scroll')}).slice(0,8).map(e=>({tag:e.tagName,cls:e.className}))}))()`);
  const item={module:label,viewport:width,...metrics,pass:metrics.scrollWidth<=width&&metrics.storageKeys.length===0};results.push(item);
  if(width===320||width===1440){const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(new URL(`module-${index}-${width}.png`,dir),Buffer.from(shot.data,'base64'))}
  console.log(JSON.stringify({module:label,width,scrollWidth:metrics.scrollWidth,pass:item.pass}));
 }
}
// Exercise the visible mobile menu and its dismissal.
await call('Emulation.setDeviceMetricsOverride',{width:390,height:900,deviceScaleFactor:1,mobile:true});
const mobileMenu=await evaluate(`(()=>{const b=[...document.querySelectorAll('.mobileBottomNav button')].find(e=>e.textContent.includes('Plus'));b?.click();return !!b})()`);
await delay(200);const sheet=await evaluate('!!document.querySelector(".mobileSheet")');
if(sheet)await evaluate('document.querySelector(".mobileSheet button[aria-label=Fermer]").click()');
await fs.writeFile(new URL('browser-modules.json',dir),JSON.stringify({results,exceptions,httpErrors,mobileMenu:mobileMenu&&sheet,scope:'Module landing screens and cookie restore; native phone keyboard and standalone PWA not certified'},null,2));
console.log(JSON.stringify({exceptions,httpErrors,mobileMenu:mobileMenu&&sheet}));socket.close();
if(results.some(x=>!x.pass)||exceptions.length||httpErrors.length)process.exitCode=1;
