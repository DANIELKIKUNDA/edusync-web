import fs from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';
const dir = new URL('./', import.meta.url);
const targets = await (await fetch('http://127.0.0.1:59222/json')).json();
const target = targets.find(x => x.type === 'page');
if (!target) throw new Error('No Edge page target');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject) => {socket.onopen=resolve;socket.onerror=reject;});
let next=0;
const pending=new Map(), exceptions=[];
socket.onmessage=event=>{
  const message=JSON.parse(event.data);
  if(message.id){const entry=pending.get(message.id);if(entry){pending.delete(message.id);clearTimeout(entry.timer);message.error?entry.reject(new Error(JSON.stringify(message.error))):entry.resolve(message.result);}}
  if(message.method==='Runtime.exceptionThrown')exceptions.push(message.params.exceptionDetails.text);
};
function call(method,params={}){return new Promise((resolve,reject)=>{const id=++next;const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP timeout: ${method}`));},20000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
await call('Runtime.enable');await call('Page.enable');
await call('Page.navigate',{url:'http://127.0.0.1:55173/'});
for(let i=0;i<60;i++){if(await evaluate('Boolean(document.querySelector(".modernLoginCard"))'))break;await delay(250);}
const results=[];
for(const width of [320,360,390,430,768,1440]){
  await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<768});
  await delay(150);
  const metrics=await evaluate(`(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,loginPresent:!!document.querySelector('.modernLoginCard'),inputs:[...document.querySelectorAll('.modernLoginCard input')].map(e=>({type:e.type,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height,font:getComputedStyle(e).fontSize})),buttons:[...document.querySelectorAll('.modernLoginCard button')].map(e=>({text:e.textContent,height:e.getBoundingClientRect().height})),sensitiveStorageKeys:Object.keys(localStorage).filter(k=>/token|session/i.test(k))}))()`);
  const screenshot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  await fs.writeFile(new URL(`login-${width}.png`,dir),Buffer.from(screenshot.data,'base64'));
  results.push({viewport:width,...metrics,pass:metrics.loginPresent&&metrics.scrollWidth<=metrics.width&&metrics.sensitiveStorageKeys.length===0});
}
await fs.writeFile(new URL('browser-login.json',dir),JSON.stringify({results,exceptions,scope:'Login page only; no authenticated modules certified'},null,2));
console.log(JSON.stringify({results,exceptions},null,2));
socket.close();
if(results.some(r=>!r.pass)||exceptions.length)process.exitCode=1;
