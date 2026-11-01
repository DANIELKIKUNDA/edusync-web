const CACHE='edusync-shell-2026-10-24-activation';
const SHELL=['/','/manifest.webmanifest','/boot-fallback.js','/icons/edusync-mark.svg','/icons/icon-192.png'];
// Filled at build time (vite.config.ts, edusync-offline-precache): every hashed module of this build, so that the whole
// school app opens without network after one online visit. Empty in development.
const PRECACHE=[];

// On a first visit, boot assets may finish loading before this worker takes
// control. The page supplies only the public, hashed asset URLs it has loaded.
self.addEventListener('message',event=>{
  if(event.data?.type==='PRECACHE_ALL'){event.waitUntil(precacheAll());return;}
  if(event.data?.type!=='CACHE_SHELL_ASSETS'||!Array.isArray(event.data.urls))return;
  const urls=event.data.urls.slice(0,100).filter(raw=>{
    try{const u=new URL(raw,self.location.origin);return u.origin===self.location.origin&&/^\/assets\/[^?#]+\.(js|css|woff2|svg|png)$/.test(u.pathname)&&!u.search;}catch{return false;}
  });
  event.waitUntil(caches.open(CACHE).then(cache=>Promise.all(urls.map(async url=>{
    try{if(await cache.match(url))return;const r=await fetch(url,{credentials:'omit'});if(r.ok)await cache.put(url,r);}catch{/* retry on a future online load */}
  }))));
});

/* Update flow (audit 2026-11-01, standard « prompt for update » of installable apps — web.dev, Workbox):
   1. a new version installs IN THE BACKGROUND and downloads its whole app here, while the current version keeps working;
   2. it then WAITS: the open app is not swapped under the user's feet, the previous copy (and its offline modules) stays;
   3. the page shows « Nouvelle version disponible » only once this download is done; « Mettre à jour » sends
      EDUSYNC_SKIP_WAITING, the worker activates and the page reloads from this cache — instant, even on a weak network.
   First install (no previous worker): nothing to replace, it takes control at once as before. */
self.addEventListener('install',event=>{
  event.waitUntil((async()=>{
    const cache=await caches.open(CACHE);
    await cache.addAll(SHELL);
    await precacheInto(cache);
    if(!self.registration.active)await self.skipWaiting();
  })());
});
// One module failing on a weak network never blocks the others (two tries each); the next online visit completes the copy
// (PRECACHE_ALL, sent by the page at every start).
function precacheInto(cache){
  const one=url=>cache.match(url).then(hit=>hit||fetch(url,{credentials:'omit'}).then(r=>{if(!r.ok)throw new Error(String(r.status));return cache.put(url,r)}));
  return Promise.all(PRECACHE.map(url=>one(url).catch(()=>one(url)).catch(()=>undefined)));
}
function precacheAll(){return caches.open(CACHE).then(precacheInto);}

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
  if(url.origin!==self.location.origin || url.pathname.startsWith('/api/') || ['/version.json','/health-api','/health'].includes(url.pathname) || request.cache==='no-store' || request.headers.has('Authorization')) return;

  if(request.mode==='navigate'){
    // App shell (audit 2026-11-01): the page of THIS version opens from the device at once — no wait on a weak network,
    // at start as after « Mettre à jour ». Freshness comes from the update flow above (sw.js is always revalidated and a
    // new version announces itself once downloaded). Network only if this copy has no shell yet.
    event.respondWith(caches.open(CACHE).then(cache=>cache.match('/')).then(hit=>hit||fetch(request)).catch(()=>fetch(request)));
    return;
  }

  event.respondWith(
    // Hashed public assets do not vary by identity or request Origin. Preview
    // servers can add Vary: Origin; the first-visit cache uses credential-free
    // requests and must still serve these same immutable bytes offline.
    caches.match(request,{ignoreVary:url.pathname.startsWith('/assets/')}).then(cached=>cached || fetch(request).then(response=>{
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
