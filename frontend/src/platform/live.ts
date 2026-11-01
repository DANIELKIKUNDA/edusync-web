// School live changes (owner, 2026-11-01: « quand un caissier encaisse, après la validation, automatiquement tout le monde
// voit sans recharger l'application » — for every school role). One Server-Sent Events connection per session
// (/api/v1/live/stream, read with fetch so the token travels in the Authorization header, never in the URL). The server
// only says WHICH domains changed (finance, students, headcounts…); each screen re-reads its own data through the normal
// API, with the member's own rights. After a lost connection every screen refreshes once (nothing missed).
import {useEffect, useRef} from 'react';

export type LiveDomain = 'finance' | 'students' | 'headcounts' | 'personnel' | 'stock' | 'settings' | 'communications' | 'access' | 'documents';
export const ALL_DOMAINS: LiveDomain[] = ['finance', 'students', 'headcounts', 'personnel', 'stock', 'settings', 'communications', 'access', 'documents'];
const EVENT = 'edusync:live';
const emit = (domains: string[]) => window.dispatchEvent(new CustomEvent(EVENT, {detail: {domains}}));

/** Opens the school channel; returns the function that closes it. */
export function startLive(token: () => string | null): () => void {
  let stopped = false; let ctrl: AbortController | null = null; let delay = 2000; let dropped = false;
  async function connect() {
    while (!stopped) {
      if (navigator.onLine === false) { await new Promise(res => window.addEventListener('online', () => res(null), {once: true})); continue; }
      const t = token(); if (!t) { await new Promise(res => setTimeout(res, 2000)); continue; }
      ctrl = new AbortController();
      try {
        const r = await fetch('/api/v1/live/stream', {headers: {Authorization: `Bearer ${t}`, Accept: 'text/event-stream'}, signal: ctrl.signal, cache: 'no-store'});
        if (!r.ok || !r.body) throw new Error(String(r.status));
        delay = 2000;
        const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = '';
        for (;;) {
          const {value, done} = await reader.read(); if (done) break;
          buf += dec.decode(value, {stream: true});
          let i; while ((i = buf.indexOf('\n\n')) >= 0) {
            const evt = buf.slice(0, i); buf = buf.slice(i + 2);
            if (/^event: ready$/m.test(evt)) { if (dropped) emit(ALL_DOMAINS); dropped = false; }     // catch up after a gap
            else if (/^event: change$/m.test(evt)) {
              try { const d = JSON.parse((evt.match(/^data: (.*)$/m) || [])[1] || '{}'); if (Array.isArray(d.domains) && d.domains.length) emit(d.domains); } catch { /* ignored */ }
            }
          }
        }
        // the server closes every 5 minutes (fresh token, revoked sessions stop): reconnect at once, nothing was missed
      } catch { if (stopped) return; dropped = true; await new Promise(res => setTimeout(res, delay)); delay = Math.min(delay * 2, 30_000); }
    }
  }
  void connect();
  return () => { stopped = true; ctrl?.abort(); };
}

/** Calls `refresh` (grouped within `wait` ms) when one of `domains` changes elsewhere in the school. A hidden tab
 *  refreshes when it becomes visible again (no useless requests in the background). */
export function useLive(domains: LiveDomain[], refresh: () => unknown, wait = 700) {
  const cb = useRef(refresh); cb.current = refresh;
  const key = domains.join(',');
  useEffect(() => {
    let timer: number | undefined; let pending = false;
    const run = () => { timer = undefined; if (document.visibilityState === 'hidden') { pending = true; return; } void cb.current(); };
    const on = (e: Event) => { const d: string[] = (e as CustomEvent).detail?.domains ?? []; if (!d.some(x => key.split(',').includes(x))) return;
      if (timer === undefined) timer = window.setTimeout(run, wait); };
    const visible = () => { if (pending && document.visibilityState === 'visible') { pending = false; void cb.current(); } };
    window.addEventListener(EVENT, on); document.addEventListener('visibilitychange', visible);
    return () => { window.removeEventListener(EVENT, on); document.removeEventListener('visibilitychange', visible); if (timer) clearTimeout(timer); };
  }, [key, wait]);
}
