// « Sur cet appareil » (2026-10-25): what this device recorded without network — waiting operations (sent automatically,
// in order) and operations the server refused at synchronisation, with the server's reason (concurrency between
// cashiers, month already paid, closed cash day…). Nothing is dropped silently: a refused line is retried or set aside.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {dismissConflict, listOutbox, retryConflict, subscribeOutbox, syncOutbox, type OutboxRequest, type OutboxState} from './outbox';
import {confirmAction} from '../platform/dialogs';

const when = (v: string) => new Date(v).toLocaleString('fr-FR', {day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'});
export function DeviceOutbox() {
  const [rows, setRows] = useState<OutboxRequest[]>([]); const [s, setS] = useState<OutboxState>({pending: 0, conflicts: 0, syncing: false});
  const reload = () => { void listOutbox().then(setRows).catch(() => setRows([])); };
  useEffect(() => { reload(); const off = subscribeOutbox(x => { setS(x); reload(); }); return off; }, []);
  const pending = rows.filter(r => r.status === 'PENDING'), conflicts = rows.filter(r => r.status === 'CONFLICT');
  async function now() { if (navigator.onLine === false) { toast.error('Toujours hors connexion : l’envoi partira tout seul au retour du réseau.'); return; } await syncOutbox(); }
  async function drop(r: OutboxRequest) {
    if (!await confirmAction({title: 'Retirer cette opération ?', message: `« ${r.label} » ne sera pas envoyée. Faites-le seulement après l’avoir réglée autrement (remboursement, correction).`, confirmLabel: 'Retirer'})) return;
    await dismissConflict(r.id); toast.success('Opération retirée de cet appareil');
  }
  return <section className="ob-panel" aria-labelledby="ob-title">
    <header><div><h3 id="ob-title">Sur cet appareil</h3>
      <p>{s.pending || s.conflicts ? `${s.pending} opération(s) en attente · ${s.conflicts} à vérifier` : 'Tout est synchronisé : aucune opération en attente sur cet appareil.'}
        {s.lastSync ? ` · dernière synchronisation à ${new Date(s.lastSync).toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'})}` : ''}</p></div>
      {s.pending > 0 && <button type="button" className="primaryBtn" disabled={s.syncing} onClick={() => void now()}>{s.syncing ? 'Synchronisation…' : 'Synchroniser maintenant'}</button>}</header>
    {pending.length > 0 && <><h4>En attente d’envoi</h4><ul>{pending.map(r => <li key={r.id}><span className="ob-dot wait"/><div><b>{r.label}</b><small>enregistrée le {when(r.createdAt)}{r.attempts ? ` · ${r.attempts} essai(s)` : ''}</small></div></li>)}</ul></>}
    {conflicts.length > 0 && <><h4>À vérifier</h4><ul>{conflicts.map(r => <li key={r.id} className="bad"><span className="ob-dot bad"/><div><b>{r.label}</b><small>enregistrée le {when(r.createdAt)} · refusée : {r.lastError}</small></div>
      <span className="ob-actions"><button type="button" className="softBtn" onClick={() => void retryConflict(r.id)}>Réessayer</button><button type="button" className="ghost" onClick={() => void drop(r)}>Retirer</button></span></li>)}</ul></>}
  </section>;
}
