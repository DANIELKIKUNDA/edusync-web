import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import {takeAccountLink} from './account_links';
import './styles.css';
import '@fontsource-variable/inter';
import './platform/modern.css';
import './platform/mobile.css';
import {installMobileEnhancements} from './platform/mobile_enhance';
import { Toaster } from 'sonner';
import { installResilientFetch } from './platform/connectivity';
import { installChunkRecovery } from './platform/lazy_page';
import { ErrorBoundary } from './platform/ErrorBoundary';
installResilientFetch();
installChunkRecovery();
installMobileEnhancements();

if ('serviceWorker' in navigator) window.addEventListener('load',()=>{
  void navigator.serviceWorker.register('/sw.js').then(()=>navigator.serviceWorker.ready).then(registration=>{
    const seen=new Set<string>();
    const cacheAssets=(entries:PerformanceEntry[])=>{
      const urls=entries.map(entry=>entry.name).filter(raw=>{
        const url=new URL(raw);return url.origin===location.origin&&url.pathname.startsWith('/assets/')&&!seen.has(raw);
      });
      urls.forEach(url=>seen.add(url));
      if(urls.length)registration.active?.postMessage({type:'CACHE_SHELL_ASSETS',urls});
    };
    cacheAssets(performance.getEntriesByType('resource'));
    // Every module of this build, in the background (offline proof on a phone, 2026-10-31): a module never opened online
    // must still open without network.
    registration.active?.postMessage({type:'PRECACHE_ALL'});
    // A lazy module may have started before activation and finish afterwards.
    if('PerformanceObserver' in window){const observer=new PerformanceObserver(list=>cacheAssets(list.getEntries()));observer.observe({type:'resource',buffered:true});}
  }).catch(()=>{/* Offline shell unavailable on this device; the online app remains usable. */});
});
// Push click from the service worker: keep the restored session, then ask the school shell to open the exact module.
// The event is also persisted briefly because Android can deliver it while session restoration is still running.
if('serviceWorker' in navigator)navigator.serviceWorker.addEventListener('message',e=>{
  if(e.data?.type==='edusync-push-open'&&typeof e.data.link==='string'){
    try{sessionStorage.setItem('edusync.pending.push',e.data.link)}catch{/* private mode */}
    window.dispatchEvent(new CustomEvent('edusync:navigate',{detail:{path:e.data.link}}));
  }
});
const initialLink=takeAccountLink();
createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><App initialLink={initialLink}/><Toaster position="top-right" richColors closeButton/></ErrorBoundary></React.StrictMode>);

// The static boot screen stays until the session check ends: App (or ErrorBoundary) calls dismissBoot. No timer.
