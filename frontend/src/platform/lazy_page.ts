/* Lazy screens and deployments (audit 2026-11-01). An open tab runs one build; after a deployment the server only has the
   files of the NEW build. If this tab then opens a screen it never loaded and the old file is gone from every cache, the
   import fails. Standard remedy (Vite « preloadError » / Next.js chunk recovery): reload ONCE on the new version instead of
   showing an error — guarded so a real network failure can never loop. */
import {lazy, type ComponentType} from 'react';

const KEY = 'edusync.chunk-reload';
const GUARD_MS = 60_000;

export function isChunkError(e: unknown): boolean {
  const err = e as {name?: string; message?: string} | null;
  return err?.name === 'ChunkLoadError' || /dynamically imported module|Importing a module script failed|Loading chunk|error loading dynamically/i.test(String(err?.message || ''));
}

/** True when this tab may reload now (not already done in the last minute) — the caller then reloads. */
export function claimChunkReload(): boolean {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return false;   // offline: an error message, not a loop
  try {
    const last = Number(sessionStorage.getItem(KEY) || 0);
    if (Date.now() - last < GUARD_MS) return false;
    sessionStorage.setItem(KEY, String(Date.now()));
  } catch { return false; }
  return true;
}

export function lazyPage<T extends ComponentType<any>>(load: () => Promise<{default: T}>) {
  return lazy(() => load().catch(error => {
    if (isChunkError(error) && claimChunkReload()) { window.location.reload(); return new Promise<{default: T}>(() => {}); }
    throw error;
  }));
}

/** Preload failures of Vite (CSS or a shared module of a lazy screen): same single reload. */
export function installChunkRecovery() {
  if (typeof window === 'undefined') return;
  window.addEventListener('vite:preloadError', event => { if (claimChunkReload()) { event.preventDefault(); window.location.reload(); } });
}
