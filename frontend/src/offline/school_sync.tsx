// School offline wiring (owner decision 2026-10-25): turns the outbox on for the signed-in school member, keeps the
// offline pack fresh (pupils + payable charges) while the network is there, and SPEAKS: recorded on this device, sent,
// refused by the server (with its reason). The status chip shows what is waiting.
import React, {useEffect, useRef, useState} from 'react';
import {toast} from 'sonner';
import {configureOutbox, savePack, subscribeOutbox, syncOutbox, type OutboxState} from './outbox';
import {DeviceOutbox} from './device_outbox';

const PACK_EVERY_MS = 10 * 60_000;
export function useSchoolOffline(session: {token: string; school: {id: string}; user: {id: string}; permissions: string[]}) {
  const tokenRef = useRef(session.token); tokenRef.current = session.token;
  useEffect(() => {
    configureOutbox(`${session.school.id}:${session.user.id}`, () => tokenRef.current);
    const sent = (e: Event) => { const d = (e as CustomEvent).detail; toast.success(`Synchronisé : ${d.label}${d.receipt ? ` · reçu ${d.receipt}` : ''}`); };
    const synced = (e: Event) => { const d = (e as CustomEvent).detail; if (d.refused) toast.error(`${d.refused} opération(s) refusée(s) par le serveur à la synchronisation : touchez « à vérifier » en haut de l’écran pour voir la raison.`, {duration: 15000}); };
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

// Reference data an offline enrollment needs (offline proof on a phone, 2026-10-31): the enrollment wizard reads the
// classes, the school years and the options. They were kept on the device only if « Élèves » had been opened online, so
// a phone that went offline first showed an empty class choice. They are now read in the background while the network
// is there, through the resilient fetch that keeps the school's read-only copy (same URLs as the screens).
const ENROLLMENT_REFERENCE=['/api/v1/settings/classes/selector','/api/v1/settings/academic-years/selector','/api/v1/settings/options/selector'];
export function useEnrollmentReference(session: {token: string; school: {id: string}; user: {id: string}; permissions: string[]}) {
  const tokenRef = useRef(session.token); tokenRef.current = session.token;
  const enrols = session.permissions.includes('enrollments.create') || session.permissions.includes('enrollments.reenroll');
  useEffect(() => {
    if (!enrols) return; let stop = false;
    const warm = () => { if (stop || navigator.onLine === false) return;
      ENROLLMENT_REFERENCE.forEach(url => { void fetch(url, {headers: {Authorization: `Bearer ${tokenRef.current}`}}).catch(() => undefined); }); };
    const first = setTimeout(warm, 1500); const t = setInterval(warm, PACK_EVERY_MS); window.addEventListener('online', warm);
    return () => { stop = true; clearTimeout(first); clearInterval(t); window.removeEventListener('online', warm); };
  }, [session.school.id, session.user.id, enrols]);
}

// Top bar (2026-10-31): the chip was written but rendered nowhere, and « Sur cet appareil » lived only in the Synchronisation
// module (administration). Every school member now sees what waits on the device and what the server refused, with the reason.
export function OutboxCenter() {
  const [open, setOpen] = useState(false);
  useEffect(() => { if (!open) return; const k = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, [open]);
  return <><OutboxChip onOpen={() => setOpen(true)}/>
    {open && <div className="ob-sheet" onClick={() => setOpen(false)}><div role="dialog" aria-modal="true" aria-label="Opérations sur cet appareil" onClick={e => e.stopPropagation()}>
      <button type="button" className="ob-close" aria-label="Fermer" onClick={() => setOpen(false)}>×</button><DeviceOutbox/></div></div>}</>;
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
