// School offline wiring (owner decision 2026-10-25): turns the outbox on for the signed-in school member, keeps the
// offline pack fresh (pupils + payable charges) while the network is there, and SPEAKS: recorded on this device, sent,
// refused by the server (with its reason). The status chip shows what is waiting.
import React, {useEffect, useRef, useState} from 'react';
import {toast} from 'sonner';
import {configureOutbox, savePack, subscribeOutbox, syncOutbox, type OutboxState} from './outbox';

const PACK_EVERY_MS = 10 * 60_000;
export function useSchoolOffline(session: {token: string; school: {id: string}; user: {id: string}; permissions: string[]}) {
  const tokenRef = useRef(session.token); tokenRef.current = session.token;
  useEffect(() => {
    configureOutbox(`${session.school.id}:${session.user.id}`, () => tokenRef.current);
    const sent = (e: Event) => { const d = (e as CustomEvent).detail; toast.success(`Synchronisé : ${d.label}${d.receipt ? ` · reçu ${d.receipt}` : ''}`); };
    const synced = (e: Event) => { const d = (e as CustomEvent).detail; if (d.refused) toast.error(`${d.refused} opération(s) refusée(s) par le serveur à la synchronisation : voir « Synchronisation › À vérifier ».`, {duration: 15000}); };
    window.addEventListener('edusync:outbox-sent', sent); window.addEventListener('edusync:outbox-synced', synced);
    return () => { window.removeEventListener('edusync:outbox-sent', sent); window.removeEventListener('edusync:outbox-synced', synced); };
  }, [session.school.id, session.user.id]);
  // Offline pack: downloaded in the background when online, refreshed every 10 minutes and after each synchronisation.
  useEffect(() => {
    if (!session.permissions.includes('finance.checkout.offline_cash')) return;
    let stop = false;
    const pull = async () => { if (stop || navigator.onLine === false) return;
      try { const r = await fetch('/api/v1/finance/checkout/offline-pack', {headers: {Authorization: `Bearer ${tokenRef.current}`}});
        if (r.ok && r.headers.get('X-EduSync-Offline') !== 'pack') { const j = await r.json(); await savePack({generatedAt: j.generated_at, people: j.people, balances: j.balances}); } }
      catch { /* offline: keep the previous pack */ } };
    const after = () => { void syncOutbox().then(pull); };
    void pull(); const t = setInterval(pull, PACK_EVERY_MS); window.addEventListener('edusync:outbox-synced', after);
    return () => { stop = true; clearInterval(t); window.removeEventListener('edusync:outbox-synced', after); };
  }, [session.school.id, session.user.id, session.permissions.join(',')]);
}

export function OutboxChip({onOpen}: {onOpen?: () => void}) {
  const [s, setS] = useState<OutboxState>({pending: 0, conflicts: 0, syncing: false});
  useEffect(() => subscribeOutbox(setS), []);
  if (!s.pending && !s.conflicts) return null;
  const label = s.syncing ? `Synchronisation… ${s.pending}` : s.pending ? `${s.pending} en attente` : `${s.conflicts} à vérifier`;
  return <button type="button" className={`ob-chip${s.conflicts ? ' warn' : ''}${s.syncing ? ' busy' : ''}`} onClick={onOpen}
    title="Opérations enregistrées sur cet appareil, envoyées automatiquement dès que la connexion revient" aria-label={`Synchronisation : ${label}`}>
    <span aria-hidden="true">⟳</span>{label}{s.conflicts && s.pending ? <em>{s.conflicts} à vérifier</em> : null}</button>;
}
