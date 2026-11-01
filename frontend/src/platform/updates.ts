/* Update notice (lot 2026-10, audit 2026-11-01). A deployed build publishes /version.json; every open tab compares it
   with the build it is running (__EDUSYNC_BUILD__) at start, every 5 minutes, when the tab comes back to the foreground
   and when the network returns. Standard « prompt for update » flow of installable apps:
   - a newer build makes the browser fetch the new service worker, which downloads the whole new version in the
     background (sw.js install) while the current one keeps working;
   - the top bar says « Nouvelle version disponible » only when that download is finished (registration.waiting);
   - « Mettre à jour » checks that nothing is being sent and that no form holds unsaved input, then activates the
     waiting version and reloads ONCE, from the device: no blank wait on a weak network.
   Without a service worker (first visit, unsupported browser) the notice falls back to a plain reload. */
import {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {subscribeActivity, type WriteActivity} from './connectivity';
import {confirmAction} from './dialogs';
import {hasUnsavedForms} from './mobile_back';

export const CURRENT_BUILD: string = typeof __EDUSYNC_BUILD__ === 'string' ? __EDUSYNC_BUILD__ : 'dev';
export const shortBuild = (b: string) => (/^[0-9a-f]{40}$/.test(b) ? b.slice(0, 7) : b);
/** Release version users read (Semantic Versioning, e.g. 1.2.0); the build id stays the technical identity. */
export const CURRENT_VERSION: string = typeof __EDUSYNC_VERSION__ === 'string' ? __EDUSYNC_VERSION__ : '0.0.0';
/** « 1.2.0 » for people; the commit only as a discreet suffix for support. */
export const versionLabel = (version?: string, build?: string) => version ? version : build ? shortBuild(build) : '';
const POLL_MS = 5 * 60 * 1000;
const MIN_GAP_MS = 45 * 1000;
const JUST_UPDATED = 'edusync.just-updated';

type UpdateState = {available: boolean; build?: string; version?: string; updating: boolean};
/** Without a ready service worker after this delay, the notice is shown anyway (plain reload). */
const READY_FALLBACK_MS = 2 * 60 * 1000;
let pendingSince = 0;
let reloading = false;
let state: UpdateState = {available: false, updating: false};
const listeners = new Set<(s: UpdateState) => void>();
let lastCheck = 0;
let started = false;
let activity: WriteActivity = {pending: 0, retrying: false, last: 'none', at: 0};

function set(patch: Partial<UpdateState>) { state = {...state, ...patch}; listeners.forEach(fn => fn(state)); }

export async function checkForUpdate(force = false): Promise<boolean> {
  if (!force && Date.now() - lastCheck < MIN_GAP_MS) return state.available;
  lastCheck = Date.now();
  try {
    const r = await fetch(`/version.json?t=${Date.now()}`, {cache: 'no-store', credentials: 'omit'});
    if (!r.ok) return state.available;
    const v = await r.json() as {build?: string; version?: string};
    if (typeof v.build === 'string' && v.build && v.build !== CURRENT_BUILD) {
      const version = typeof v.version === 'string' ? v.version : undefined;
      const reg = navigator.serviceWorker?.controller ? await navigator.serviceWorker.getRegistration().catch(() => undefined) : undefined;
      if (!reg) { set({available: true, build: v.build, version}); return true; }        // no worker: plain reload later
      set({build: v.build, version});
      if (reg.waiting) { set({available: true}); return true; }                          // already downloaded
      pendingSince ||= Date.now();
      await reg.update().catch(() => undefined);                                         // download in the background
      if (reg.waiting) set({available: true});
      else if (Date.now() - pendingSince > READY_FALLBACK_MS) set({available: true});    // never stay silent
    }
  } catch { /* offline or server restarting: try again later, never an error for the user */ }
  return state.available;
}

function start() {
  if (started) return; started = true;
  subscribeActivity(a => { activity = a; });
  void checkForUpdate(true);
  window.setInterval(() => { if (document.visibilityState === 'visible') void checkForUpdate(); }, POLL_MS);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') void checkForUpdate(); });
  window.addEventListener('online', () => void checkForUpdate(true));
  window.addEventListener('focus', () => void checkForUpdate());
  // The notice appears when the new version is DOWNLOADED (a worker waiting), not merely deployed.
  navigator.serviceWorker?.getRegistration().then(reg => {
    if (!reg) return;
    if (reg.waiting && navigator.serviceWorker.controller) set({available: true});
    reg.addEventListener('updatefound', () => {
      const w = reg.installing;
      w?.addEventListener('statechange', () => { if (w.state === 'installed' && navigator.serviceWorker.controller) set({available: true}); });
    });
  }).catch(() => undefined);
  // Another tab applied the update: this one is now served by the new version — offer the reload (never forced).
  navigator.serviceWorker?.addEventListener('controllerchange', () => { if (!reloading) set({available: true, updating: false}); });
}

export function useUpdateNotice(): UpdateState {
  const [s, setS] = useState(state);
  useEffect(() => { start(); listeners.add(setS); setS(state); return () => { listeners.delete(setS); }; }, []);
  return s;
}

export async function applyUpdate() {
  if (state.updating) return;
  const busy = activity.pending > 0 || activity.retrying;
  if (busy || hasUnsavedForms()) {
    const ok = await confirmAction({
      title: 'Mettre à jour maintenant ?',
      message: busy ? 'Un enregistrement est encore en cours d’envoi. Attendez la fin de l’envoi, ou mettez à jour maintenant : EduSync empêche les doublons, mais l’opération pourrait devoir être refaite.'
        : 'Un formulaire contient une saisie non enregistrée. La mise à jour recharge la page : cette saisie sera perdue.',
      confirmLabel: 'Mettre à jour quand même', danger: true,
    });
    if (!ok) return;
  }
  set({updating: true});
  try { sessionStorage.setItem(JUST_UPDATED, state.version || state.build || ''); } catch { /* facultatif */ }
  reloading = true;
  try {
    // No network call here: the new version is already on the device (downloaded before the notice appeared).
    const reg = await navigator.serviceWorker?.getRegistration();
    if (reg?.waiting) {
      const switched = new Promise<void>(resolve => { navigator.serviceWorker.addEventListener('controllerchange', () => resolve(), {once: true}); window.setTimeout(resolve, 4000); });
      reg.waiting.postMessage({type: 'EDUSYNC_SKIP_WAITING'});
      await switched;
    }
  } catch { /* the reload below still loads the new version: the HTML shell is always revalidated */ }
  window.location.reload();
}

/** After the reload: confirm the update once. */
export function announceIfJustUpdated() {
  let flag: string | null = null;
  try { flag = sessionStorage.getItem(JUST_UPDATED); sessionStorage.removeItem(JUST_UPDATED); } catch { /* facultatif */ }
  if (flag !== null) toast.success('EduSync est à jour', {description: `Version ${CURRENT_VERSION} installée.`});
}
