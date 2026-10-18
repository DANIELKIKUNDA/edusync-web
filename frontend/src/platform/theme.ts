/* User preferences of the platform space (lot UX 2026-10): theme only for now (French is the only language).
   Scope, documented: stored in this browser for this account (localStorage key per account e-mail); it survives
   page changes, refresh, closing the browser and signing in again on this device. No server-side preference store
   exists yet, so another device starts from "Système". The theme applies to the platform space only: the school
   space keeps its certified light theme until its own dark mode is reviewed. */
import {useEffect, useState} from 'react';

export type ThemePref = 'light' | 'dark' | 'system';
export const THEME_OPTIONS: {value: ThemePref; label: string; hint: string; icon: string}[] = [
  {value: 'light', label: 'Clair', hint: 'Fond clair en permanence.', icon: 'sun'},
  {value: 'dark', label: 'Sombre', hint: 'Fond sombre, plus reposant le soir.', icon: 'moon'},
  {value: 'system', label: 'Système', hint: 'Suit le réglage de votre appareil.', icon: 'monitor'},
];

const key = (account: string) => `edusync.prefs.theme.${(account || 'anonymous').trim().toLowerCase()}`;
const media = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null);

export function readTheme(account: string): ThemePref {
  try { const v = localStorage.getItem(key(account)); return v === 'light' || v === 'dark' || v === 'system' ? v : 'system'; } catch { return 'system'; }
}

export function resolveTheme(pref: ThemePref): 'light' | 'dark' {
  return pref === 'system' ? (media()?.matches ? 'dark' : 'light') : pref;
}

export function applyTheme(pref: ThemePref | null) {
  const root = document.documentElement;
  if (pref === null) { delete root.dataset.theme; root.style.colorScheme = ''; return; }
  const resolved = resolveTheme(pref);
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolved === 'dark' ? '#0d1526' : '#0f4fbf');
}

/** Theme of the signed-in platform account: applied while the platform space is mounted, removed on sign-out. */
export function usePlatformTheme(account: string): [ThemePref, (p: ThemePref) => void] {
  const [pref, setPref] = useState<ThemePref>(() => readTheme(account));
  useEffect(() => { setPref(readTheme(account)); }, [account]);
  useEffect(() => {
    applyTheme(pref);
    const mq = media();
    const onChange = () => { if (pref === 'system') applyTheme('system'); };
    mq?.addEventListener('change', onChange);
    return () => mq?.removeEventListener('change', onChange);
  }, [pref]);
  useEffect(() => () => applyTheme(null), []);
  const update = (p: ThemePref) => {
    try { localStorage.setItem(key(account), p); } catch { console.warn('[edusync] préférence de thème non enregistrée (stockage local indisponible)'); }
    setPref(p);
  };
  return [pref, update];
}
