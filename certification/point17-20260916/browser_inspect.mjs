import {setTimeout as delay} from 'node:timers/promises';
const targets=await(await fetch('http://127.0.0.1:59222/json')).json();
const ws=new WebSocket(targets.find(x=>x.type==='page').webSocketDebuggerUrl);
await new Promise(r=>ws.onopen=r);let id=0;const p=new Map();
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){p.get(m.id)?.(m.result);p.delete(m.id)}};
function call(method,params={}){return new Promise(r=>{const n=++id;p.set(n,r);ws.send(JSON.stringify({id:n,method,params}))})}
async function evaluate(expression){return (await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})).result?.value}
for(const index of [3,4,8]){
 await call('Emulation.setDeviceMetricsOverride',{width:320,height:900,deviceScaleFactor:1,mobile:true});
 await evaluate(`document.querySelectorAll('.smartNav button')[${index}].click()`);await delay(500);
 const data=await evaluate(`(()=>[...document.querySelectorAll('main *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.right>321}).slice(0,15).map(e=>({cls:e.className,tag:e.tagName,text:e.textContent.slice(0,45),rect:e.getBoundingClientRect().toJSON(),parents:[e.parentElement,e.parentElement?.parentElement].filter(Boolean).map(p=>({cls:p.className,w:p.getBoundingClientRect().width,min:getComputedStyle(p).minWidth,overflow:getComputedStyle(p).overflowX,display:getComputedStyle(p).display}))})))()`);
 console.log(JSON.stringify({index,data}));
}
ws.close();
