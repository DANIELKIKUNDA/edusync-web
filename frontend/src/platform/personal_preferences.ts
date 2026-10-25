import {useEffect, useState} from 'react';

// Personal to one account and one space on this device.
const key = (account: string, scope: string) =>
  `edusync.prefs.reduced-motion.${scope}.${account.trim().toLowerCase()}`;

export function readReducedMotion(account: string, scope: string): boolean {
  try { return localStorage.getItem(key(account, scope)) === 'true'; }
  catch { return false; }
}

export function useReducedMotion(account: string, scope: string): [boolean, (value: boolean) => void] {
  const [enabled, setEnabled] = useState(() => readReducedMotion(account, scope));
  useEffect(() => { setEnabled(readReducedMotion(account, scope)); }, [account, scope]);
  useEffect(() => {
    if (enabled) document.documentElement.dataset.edusyncReduceMotion = 'true';
    else delete document.documentElement.dataset.edusyncReduceMotion;
    return () => { delete document.documentElement.dataset.edusyncReduceMotion; };
  }, [enabled, account, scope]);
  const update = (value: boolean) => {
    try { localStorage.setItem(key(account, scope), String(value)); }
    catch { /* Keep the current-session choice when storage is unavailable. */ }
    setEnabled(value);
  };
  return [enabled, update];
}
