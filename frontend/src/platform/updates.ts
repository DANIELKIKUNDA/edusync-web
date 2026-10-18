/* Update notice (lot 2026-10). A deployed build publishes /version.json; every open tab compares it with the build
   it is running (__EDUSYNC_BUILD__) at start, every 5 minutes, when the tab comes back to the foreground and when
   the network returns. A newer build is announced in the top bar; "Mettre à jour" reloads on the new version only
   after checking that nothing is being sent and that no form holds unsaved input (the user then decides). */
import {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {subscribeActivity, type WriteActivity} from './connectivity';
import {confirmAction} from './dialogs';
import {hasUnsavedForms} from './mobile_back';

export const CURRENT_BUILD: string = typeof __EDUSYNC_BUILD__ === 'string' ? __EDUSYNC_BUILD__ : 'dev';
export const shortBuild = (b: string) => (/^[0-9a-f]{40}$/.test(b) ? b.slice(0, 7) : b);
const POLL_MS = 5 * 60 * 1000;
const MIN_GAP_MS = 45 * 1000;
const JUST_UPDATED = 'edusync.just-updated';

type UpdateState = {available: boolean; build?: string; updating: boolean};
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
    const v = await r.json() as {build?: string};
    if (typeof v.build === 'string' && v.build && v.build !== CURRENT_BUILD) set({available: true, build: v.build});
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
  // A new service worker waiting is another signal that a new version has been deployed.
  navigator.serviceWorker?.getRegistration().then(reg => {
    if (!reg) return;
    if (reg.waiting) void checkForUpdate(true);
    reg.addEventListener('updatefound', () => void checkForUpdate(true));
  }).catch(() => undefined);
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
  try { sessionStorage.setItem(JUST_UPDATED, state.build || ''); } catch { /* facultatif */ }
  try {
    const reg = await navigator.serviceWorker?.getRegistration();
    if (reg) {
      await reg.update().catch(() => undefined);
      if (reg.waiting) {
        const switched = new Promise<void>(resolve => { navigator.serviceWorker.addEventListener('controllerchange', () => resolve(), {once: true}); window.setTimeout(resolve, 3000); });
        reg.waiting.postMessage({type: 'EDUSYNC_SKIP_WAITING'});
        await switched;
      }
    }
  } catch { /* the reload below still loads the new version: the HTML shell is always revalidated */ }
  window.location.reload();
}

/** After the reload: confirm the update once. */
export function announceIfJustUpdated() {
  let flag: string | null = null;
  try { flag = sessionStorage.getItem(JUST_UPDATED); sessionStorage.removeItem(JUST_UPDATED); } catch { /* facultatif */ }
  if (flag !== null) toast.success('EduSync est à jour', {description: `Version ${shortBuild(CURRENT_BUILD)} installée.`});
}
