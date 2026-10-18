const CACHE='edusync-shell-2026-10-updates';
const SHELL=['/','/manifest.webmanifest'];

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()));
});

self.addEventListener('activate',event=>{
  event.waitUntil(Promise.all([
    self.clients.claim(),
    caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))
  ]));
});

self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET') return;
  const url=new URL(request.url);

  // SECURITY / MULTI-TENANT: never cache API or authenticated responses in the shared
  // service-worker cache. Business offline data lives in the scoped IndexedDB layer.
  if(url.origin!==self.location.origin || url.pathname.startsWith('/api/') || url.pathname==='/version.json' || request.headers.has('Authorization')) return;

  if(request.mode==='navigate'){
    event.respondWith(fetch(request).catch(()=>caches.match('/')));
    return;
  }

  event.respondWith(
    caches.match(request).then(cached=>cached || fetch(request).then(response=>{
      if(response.ok && response.type==='basic'){
        const copy=response.clone();
        caches.open(CACHE).then(cache=>cache.put(request,copy));
      }
      return response;
    }))
  );
});

// ---------------------------------------------------------------- Push (Firebase Cloud Messaging, data-only messages)
// EduSync displays push messages itself (no second service worker): title, short text and an internal link only.
// Firebase wraps data-only web push as {"data": {...}}; a plain payload is also accepted. Links are same-origin only.
self.addEventListener('push',event=>{
  let payload={};
  try{payload=event.data?event.data.json():{};}catch(_e){payload={};}
  const data=payload.data||payload;
  const title=String(data.title||'EduSync').slice(0,120);
  const body=String(data.body||'Ouvrez EduSync pour lire le message.').slice(0,240);
  const raw=String(data.link||'/');
  const link=raw.startsWith('/')&&!raw.startsWith('//')?raw:'/';
  event.waitUntil((async()=>{
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    windows.forEach(c=>c.postMessage({type:'edusync-push',title,body,link}));   // foreground: in-app toast as well
    await self.registration.showNotification(title,{body,icon:'/icons/icon-192.png',badge:'/icons/icon-192.png',tag:data.message_id||undefined,data:{link}});
  })());
});

self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const link=(event.notification.data&&event.notification.data.link)||'/';
  const target=new URL(link,self.location.origin);
  if(target.origin!==self.location.origin)return;
  event.waitUntil((async()=>{
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    for(const c of windows){if(new URL(c.url).origin===self.location.origin&&'focus' in c){await c.focus();c.postMessage({type:'edusync-push-open',link:target.pathname+target.search});return;}}
    await self.clients.openWindow(target.href);
  })());
});

// Update notice (lot 2026-10): the page asks the waiting worker to take over before it reloads on the new version.
self.addEventListener('message',event=>{if(event.data&&event.data.type==='EDUSYNC_SKIP_WAITING')self.skipWaiting();});
