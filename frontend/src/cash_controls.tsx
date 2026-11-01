// N3-B — cash-desk integrity copied from the Desktop golden master (app/db/operations.py: record_expense, reverse_payment,
// close_cash_day, reopen_cash_day, daily_financial_report; app/services/documents.py: cash journal and daily report PDFs).
// Web transposition (owner decision 2026-10-15): individual sessions stay; the school's day is closed globally by the
// superior authority (GESTIONNAIRE); a cashier corrects only his own payment while his session is open.
import {previewPdf} from './document_io';
import React, {useEffect, useState} from 'react';
import {createPortal} from 'react-dom';
import {toast} from 'sonner';
import {cashDayPdf, cashExpense, closeSchoolCashDay, reopenSchoolCashDay, reversePayment, schoolCashDay, type SchoolCashDay} from './api';
import {friendlyError} from './platform/errors';
import {confirmAction, promptText} from './platform/dialogs';
import {formatMoney} from './platform/format';
import {useLive} from './platform/live';

const money = (v: string | number, c: string) => formatMoney(String(v), c);

export function CashExpenseForm({token, onDone}: {token: string; onDone: () => Promise<void> | void}) {
  const [category, setCategory] = useState(''); const [amount, setAmount] = useState(''); const [currency, setCurrency] = useState<'CDF' | 'USD'>('CDF');
  const [reason, setReason] = useState(''); const [reference, setReference] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!category.trim() || reason.trim().length < 3) { setError('Catégorie et motif de dépense obligatoires (motif : 3 caractères au moins).'); return; }
    if (!/^\d+([.,]\d{1,2})?$/.test(amount.trim()) || Number(amount.replace(',', '.')) <= 0) { setError('Montant en chiffres, supérieur à zéro.'); return; }
    if (!await confirmAction({title: 'Enregistrer cette dépense ?', message: `${money(amount.replace(',', '.'), currency)} sortiront de votre caisse. Une dépense enregistrée ne se supprime pas.`, confirmLabel: 'Enregistrer'})) return;
    try {
      setBusy(true); setError('');
      const res: any = await cashExpense(token, {category: category.trim(), amount: amount.replace(',', '.'), currency, reason: reason.trim(), reference: reference.trim() || null});
      toast.success(res?.offline_queued ? 'Hors connexion : dépense enregistrée sur cet appareil, envoyée automatiquement' : 'Dépense enregistrée'); setCategory(''); setAmount(''); setReason(''); setReference(''); await onDone();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <form className="cashExpenseBox compact" onSubmit={submit} noValidate>
    <b>Dépense de caisse</b>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="cashExpenseGrid">
      <label>Catégorie<input value={category} maxLength={80} onChange={e => setCategory(e.target.value)} placeholder="Fournitures, transport…"/></label>
      <label>Montant<input inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)}/></label>
      <label>Devise<select value={currency} onChange={e => setCurrency(e.target.value as 'CDF' | 'USD')}><option value="CDF">FC</option><option value="USD">USD</option></select></label>
      <label>Motif<input value={reason} maxLength={500} onChange={e => setReason(e.target.value)}/></label>
      <label>Référence (facultatif)<input value={reference} maxLength={80} onChange={e => setReference(e.target.value)}/></label>
    </div>
    <button className="softBtn" disabled={busy}>{busy ? 'Enregistrement…' : 'Enregistrer la dépense'}</button>
  </form>;
}

/** Counter-operation of a payment: append-only, type and reason required (Desktop reverse_payment). */
export function useReversal(token: string, onDone: () => Promise<void> | void): [(paymentId: string, reference: string) => void, React.ReactNode] {
  const [target, setTarget] = useState<{id: string; ref: string} | null>(null);
  const [kind, setKind] = useState<'ANNULATION' | 'REMBOURSEMENT'>('ANNULATION'); const [reason, setReason] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit() {
    if (!target) return;
    if (reason.trim().length < 3) { setError('Le motif est obligatoire (3 caractères au moins).'); return; }
    try { setBusy(true); setError(''); await reversePayment(token, target.id, {reversal_type: kind, reason: reason.trim()});
      toast.success(kind === 'REMBOURSEMENT' ? 'Remboursement enregistré' : 'Annulation enregistrée'); setTarget(null); await onDone(); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  const node = target ? createPortal(<div className="es-modal-backdrop" onMouseDown={e => e.currentTarget === e.target && setTarget(null)}>
    <div className="es-modal" role="dialog" aria-modal="true" aria-label={`Contre-opération sur le reçu ${target.ref}`}>
      <div className="es-modal-head"><div><h2>Contre-opération · reçu {target.ref}</h2><p>Le paiement reste dans l’historique ; les frais qu’il réglait redeviennent payables.</p></div></div>
      {error && <div className="error" role="alert">{error}</div>}
      <fieldset className="reversalKind" disabled={busy}><legend>Type</legend>
        <label className="checkField"><input type="radio" name="rk" checked={kind === 'ANNULATION'} onChange={() => setKind('ANNULATION')}/> Annulation (erreur de saisie)</label>
        <label className="checkField"><input type="radio" name="rk" checked={kind === 'REMBOURSEMENT'} onChange={() => setKind('REMBOURSEMENT')}/> Remboursement (argent rendu)</label>
      </fieldset>
      <label className="reversalReason">Motif (obligatoire)<textarea value={reason} maxLength={500} rows={3} onChange={e => setReason(e.target.value)} disabled={busy}/></label>
      <div className="es-modal-foot"><button className="es-btn es-btn-ghost" onClick={() => setTarget(null)}>Retour</button>
        <button className="es-btn es-btn-primary" disabled={busy} onClick={() => void submit()}>{busy ? 'Validation…' : 'Valider la contre-opération'}</button></div>
    </div></div>, document.body) : null;
  return [(id, ref) => { setTarget({id, ref}); setKind('ANNULATION'); setReason(''); setError(''); }, node];
}

async function openPdf(token: string, kind: 'journal' | 'report', day: string) {
  try { const b = await cashDayPdf(token, kind, day); previewPdf(b); }
  catch (e) { toast.error(friendlyError(e)); }
}

export function SchoolDayPanel({token, can, day}: {token: string; can: (p: string) => boolean; day: string}) {
  const [d, setD] = useState<SchoolCashDay | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  useLive(['finance'],()=>load());   // live: what another member records here appears without reloading (2026-11-01)
  async function load() { try { setD(await schoolCashDay(token, day)); setError(''); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token, day]);
  const [askReversal, reversalDialog] = useReversal(token, load);   // hooks before any early return
  const today = new Date().toISOString().slice(0, 10);
  async function close() {
    if (!d) return;
    if (!await confirmAction({title: 'Clôturer la journée de l’école ?', message: 'Les totaux du jour sont figés par devise. Plus aucune caisse ne pourra être ouverte ni aucun encaissement fait aujourd’hui sans réouverture motivée.', confirmLabel: 'Clôturer la journée'})) return;
    try { setBusy(true); await closeSchoolCashDay(token); toast.success('Journée de caisse clôturée'); await load(); } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  async function reopen() {
    const reason = await promptText({title: 'Rouvrir la journée de caisse', label: 'Motif (obligatoire, 5 caractères au moins)', required: true, minLength: 5, confirmLabel: 'Rouvrir'});
    if (!reason) return;
    try { setBusy(true); await reopenSchoolCashDay(token, reason); toast.success('Journée rouverte'); await load(); } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  if (!d) return error ? <div className="error" role="alert">{error}</div> : null;
  const canReverse = can('finance.payments.reverse.supervisor');
  return <div className="schoolDay">
    <div className="cashHistoryHead compact"><div><b>Journée de caisse de l’école</b><span>{d.closed ? 'Clôturée' : 'Ouverte'} · {d.sessions} caisse(s), dont {d.open_sessions} ouverte(s){d.reopen_reason ? ` · rouverte : ${d.reopen_reason}` : ''}</span></div>
      <span className={`cashState ${d.closed ? 'closed' : 'open'}`}><i/>{d.closed ? 'CLÔTURÉE' : 'OUVERTE'}</span></div>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="cashTableWrap"><table className="cashSummaryTable"><thead><tr><th>Devise</th><th>Entrées</th><th>Sorties</th><th>Net</th></tr></thead>
      <tbody>{d.totals.map(t => <tr key={t.currency}><th>{t.currency === 'CDF' ? 'FC' : t.currency}</th><td>{money(t.entries, t.currency)}</td><td>{money(t.outflows, t.currency)}</td><td><b>{money(t.net, t.currency)}</b></td></tr>)}
        {d.totals.length === 0 && <tr><td colSpan={4}>Aucune opération ce jour.</td></tr>}</tbody></table></div>
    {d.details.length > 0 && <ul className="dayDetails">{d.details.map((x, i) => <li key={i}><span>{x.label} · {x.direction === 'ENTREE' ? 'entrée' : 'sortie'}</span><b>{money(x.amount, x.currency)}</b></li>)}</ul>}
    {canReverse && !!d.operations?.length && <details className="dayOps"><summary>Encaissements du jour (contre-opération supérieure)</summary>
      <ul>{d.operations.filter(o => o.payment_id).map(o => <li key={o.payment_id!}><span>{o.reference} · {o.user_name || '—'}</span><b>{money(o.amount, o.currency)}</b>
        {o.reversed ? <small>Contre-opération faite</small> : !d.closed && <button className="ghost" onClick={() => askReversal(o.payment_id!, o.reference)}>Contre-opération</button>}</li>)}</ul></details>}
    <div className="dayActions">
      {can('finance.cash.journal.export') && <button className="softBtn" onClick={() => void openPdf(token, 'journal', d.day)}>Journal de caisse (PDF)</button>}
      {can('finance.reports.daily.generate') && <button className="softBtn" onClick={() => void openPdf(token, 'report', d.day)}>Rapport journalier (PDF)</button>}
      {can('finance.cash.day.close') && !d.closed && d.day === today && <button className="collectBtn" disabled={busy} onClick={() => void close()}>Clôturer la journée</button>}
      {can('finance.cash.reopen') && d.closed && d.day === today && <button className="softBtn" disabled={busy} onClick={() => void reopen()}>Rouvrir la journée</button>}
    </div>
    {reversalDialog}
  </div>;
}
