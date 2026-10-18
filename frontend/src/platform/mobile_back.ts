/** Android/PWA back coordinator.
 * Browser/Android back closes the top transient layer before leaving the current business screen.
 * It never stores business data or tokens in history.state.
 */
const OVERLAY_SELECTOR='.mobileSheetBackdrop,.wizardBackdrop,.drawerBackdrop,.eduDialogBackdrop';
let suppressOverlayPush=false;
let overlaySerial=0;

function visibleOverlays():HTMLElement[]{
  return Array.from(document.querySelectorAll<HTMLElement>(OVERLAY_SELECTOR)).filter(x=>x.offsetParent!==null || getComputedStyle(x).position==='fixed');
}
function closeTopOverlay():boolean{
  const overlays=visibleOverlays(); const top=overlays[overlays.length-1]; if(!top)return false;
  const close=top.querySelector<HTMLElement>('[aria-label="Fermer"],.drawerClose,.modalHead button,.mobileSheetHead button,.eduDialogClose');
  if(close){suppressOverlayPush=true;close.click();queueMicrotask(()=>{suppressOverlayPush=false});return true}
  return false;
}
export function installMobileBackCoordinator():()=>void{
  const onPop=()=>{ if(closeTopOverlay()) return; window.dispatchEvent(new CustomEvent('edusync:android-back',{detail:history.state||{}})); };
  const observer=new MutationObserver(()=>{
    if(suppressOverlayPush)return;
    const overlays=visibleOverlays();
    const depth=overlays.length;
    const currentDepth=Number(history.state?.edusyncOverlayDepth||0);
    if(depth>currentDepth){overlaySerial+=1;history.pushState({...history.state,edusyncOverlayDepth:depth,edusyncOverlay:overlaySerial},'')}
  });
  observer.observe(document.body,{childList:true,subtree:true});
  window.addEventListener('popstate',onPop);
  return()=>{observer.disconnect();window.removeEventListener('popstate',onPop)};
}
export function pushMobileScreen(scope:'school'|'platform',screen:string):void{
  const s=history.state||{};
  if(s.edusyncScope===scope&&s.edusyncScreen===screen&&!s.edusyncOverlayDepth)return;
  history.pushState({edusyncScope:scope,edusyncScreen:screen},'');
}
export function replaceMobileRoot(scope:'school'|'platform',screen:string):void{
  history.replaceState({edusyncScope:scope,edusyncScreen:screen},'');
}
const dirty=new WeakSet<HTMLFormElement>();
/** A form of the page has been edited and not submitted (used by the update notice before reloading). */
export function hasUnsavedForms():boolean{return Array.from(document.forms).some(f=>dirty.has(f)&&f.isConnected)}
export function installUnsavedFormGuard():()=>void{
  const mark=(e:Event)=>{const form=(e.target as HTMLElement|null)?.closest?.('form');if(form)dirty.add(form)};
  const clear=(e:Event)=>{if(e.target instanceof HTMLFormElement)dirty.delete(e.target)};
  const before=(e:BeforeUnloadEvent)=>{const any=Array.from(document.forms).some(f=>dirty.has(f));if(any){e.preventDefault();e.returnValue=''}};
  document.addEventListener('input',mark,true);document.addEventListener('change',mark,true);document.addEventListener('submit',clear,true);document.addEventListener('reset',clear,true);window.addEventListener('beforeunload',before);
  return()=>{document.removeEventListener('input',mark,true);document.removeEventListener('change',mark,true);document.removeEventListener('submit',clear,true);document.removeEventListener('reset',clear,true);window.removeEventListener('beforeunload',before)};
}
