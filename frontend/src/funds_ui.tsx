// N3-D — fonds anticipés copied from the Desktop golden master (app/db/operations.py: receive / allocate /
// reverse_advance_fund, documents.py: export_advance_receipt_pdf). A fund is money received BEFORE any imputation: it is
// kept as an available amount and imputed later. It is NOT a payment plan (Plan anticipé ≠ Fonds anticipé).
import {previewPdf} from './document_io';
import React, {useEffect, useState} from 'react';
import {createPortal} from 'react-dom';
import {toast} from 'sonner';
import {AdvanceFund, advanceFundReceipt, advanceFunds, allocateAdvanceFund, closeAdvanceFund, receiveAdvanceFund, type PaymentOptions} from './api';
import {friendlyError} from './platform/errors';
import {confirmAction} from './platform/dialogs';
import {formatMoney} from './platform/format';

export const FUND_STATUS: Record<string, string> = {ACTIF: 'Disponible', EPUISE: 'Épuisé', ANNULE: 'Annulé', REMBOURSE: 'Remboursé'};
export const FUND_ORIGIN: Record<string, string> = {PAYMENT_ADVANCE: 'Fonds anticipé reçu', DECISION_CREDIT: 'Crédit issu d’une décision'};
const money = (v: string | number, c: string) => formatMoney(String(v), c);
const MODE: Record<string, string> = {CASH: 'Espèces', MOBILE_MONEY: 'Mobile Money', BANQUE: 'Banque', AUTRE: 'Autre'};

export async function openFundReceipt(token: string, id: string) {
  try { const b = await advanceFundReceipt(token, id); previewPdf(b); } catch (e) { toast.error(friendlyError(e)); }
}

/** Cash desk: the active pupil's funds — receive, impute, print the fund receipt. */
export function AdvanceFundsPanel({token, can, enrollmentId, options, onChanged}: {token: string; can: (p: string) => boolean; enrollmentId: string; options: PaymentOptions | null; onChanged: () => Promise<void> | void}) {
  const [items, setItems] = useState<AdvanceFund[]>([]); const [open, setOpen] = useState(false); const [amount, setAmount] = useState(''); const [currency, setCurrency] = useState<'CDF' | 'USD'>('CDF');
  const [mode, setMode] = useState('CASH'); const [reference, setReference] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function load() { try { setItems((await advanceFunds(token, enrollmentId)).items); } catch { setItems([]); } }
  useEffect(() => { void load(); }, [token, enrollmentId]);
  const enabled = options?.advance_payments_enabled !== false;
  async function receive(e: React.FormEvent) {
    e.preventDefault();
    if (!/^\d+([.,]\d{1,2})?$/.test(amount.trim()) || Number(amount.replace(',', '.')) <= 0) { setError('Montant en chiffres, supérieur à zéro.'); return; }
    if (!await confirmAction({title: 'Recevoir ce fonds anticipé ?', message: `${money(amount.replace(',', '.'), currency)} seront conservés comme montant disponible, imputé plus tard sur les frais. Un reçu de fonds anticipé est émis.`, confirmLabel: 'Recevoir'})) return;
    try {
      setBusy(true); setError('');
      const f = await receiveAdvanceFund(token, {enrollment_id: enrollmentId, amount: amount.replace(',', '.'), currency, mode, reference: reference.trim() || null});
      toast.success(`Fonds anticipé reçu · reçu ${f.receipt_number}`); setAmount(''); setReference(''); setOpen(false); await load(); await onChanged();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  async function allocate(f: AdvanceFund) {
    if (!await confirmAction({title: 'Imputer ce fonds sur les frais ?', message: `${money(f.available_amount, f.currency)} disponibles seront imputés sur les frais les plus anciens en ${f.currency}, sans dépasser ce qui reste dû.`, confirmLabel: 'Imputer'})) return;
    try { const r = await allocateAdvanceFund(token, f.id); toast.success(`Imputé : ${money(r.applied, f.currency)} · reste disponible ${money(r.available_amount, f.currency)}`); await load(); await onChanged(); }
    catch (err) { toast.error(friendlyError(err)); }
  }
  if (!can('finance.advance_funds.read') && !can('finance.advance_funds.receive')) return null;
  return <div className="fundsPanel" aria-label="Fonds anticipés">
    <div className="chargeToolbar"><div><b>Fonds anticipés</b><span>Montant reçu avant imputation, distinct d’un plan de paiement anticipé</span></div>
      {can('finance.advance_funds.receive') && enabled && <button onClick={() => setOpen(o => !o)}>{open ? 'Fermer' : 'Recevoir un fonds'}</button>}</div>
    {!enabled && <p className="policyHint">Les fonds anticipés sont désactivés dans les règles d’encaissement de l’école.</p>}
    {open && <form className="cashExpenseBox compact" onSubmit={receive} noValidate>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="cashExpenseGrid">
        <label>Montant<input inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)}/></label>
        <label>Devise<select value={currency} onChange={e => setCurrency(e.target.value as 'CDF' | 'USD')}><option value="CDF">FC</option><option value="USD">USD</option></select></label>
        <label>Mode<select value={mode} onChange={e => setMode(e.target.value)}>{(options?.accepted_modes ?? ['CASH']).map(m => <option key={m} value={m}>{MODE[m] ?? m}</option>)}</select></label>
        <label>Référence (facultatif)<input value={reference} maxLength={120} onChange={e => setReference(e.target.value)}/></label>
      </div>
      <button disabled={busy}>{busy ? 'Validation…' : 'Recevoir le fonds anticipé'}</button>
    </form>}
    {items.length > 0 && <ul className="dayDetails">{items.map(f => <li key={f.id}><span>{FUND_ORIGIN[f.origin_type]}{f.receipt_number ? ` · ${f.receipt_number}` : ''} · {FUND_STATUS[f.status]}<br/><small>reçu {money(f.amount, f.currency)} · imputé {money(f.allocated_amount, f.currency)}</small></span>
      <b>{money(f.available_amount, f.currency)}</b>
      <span className="fundActions">{f.status === 'ACTIF' && can('finance.advance_funds.allocate') && <button className="ghost" onClick={() => void allocate(f)}>Imputer</button>}
        {f.origin_type === 'PAYMENT_ADVANCE' && can('finance.advance_funds.receipt.print') && <button className="ghost" onClick={() => void openFundReceipt(token, f.id)}>Reçu</button>}</span></li>)}</ul>}
  </div>;
}

/** Superior authority (GESTIONNAIRE): cancel or refund a fund with nothing imputed (Desktop reverse_advance_fund). */
export function useFundClosure(token: string, onDone: () => Promise<void> | void): [(fundId: string, label: string) => void, React.ReactNode] {
  const [target, setTarget] = useState<{id: string; label: string} | null>(null);
  const [kind, setKind] = useState<'ANNULATION' | 'REMBOURSEMENT'>('REMBOURSEMENT'); const [reason, setReason] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit() {
    if (!target) return;
    if (reason.trim().length < 3) { setError('Le motif est obligatoire (3 caractères au moins).'); return; }
    try { setBusy(true); setError(''); await closeAdvanceFund(token, target.id, {reversal_type: kind, reason: reason.trim()}); toast.success(kind === 'REMBOURSEMENT' ? 'Fonds remboursé' : 'Fonds annulé'); setTarget(null); await onDone(); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  const node = target ? createPortal(<div className="es-modal-backdrop" onMouseDown={e => e.currentTarget === e.target && setTarget(null)}>
    <div className="es-modal" role="dialog" aria-modal="true" aria-label={`Contre-opération sur ${target.label}`}>
      <div className="es-modal-head"><div><h2>Contre-opération · {target.label}</h2><p>Seul un fonds sans aucune imputation peut être remboursé ou annulé.</p></div></div>
      {error && <div className="error" role="alert">{error}</div>}
      <fieldset className="reversalKind" disabled={busy}><legend>Type</legend>
        <label className="checkField"><input type="radio" name="fk" checked={kind === 'REMBOURSEMENT'} onChange={() => setKind('REMBOURSEMENT')}/> Remboursement (argent rendu)</label>
        <label className="checkField"><input type="radio" name="fk" checked={kind === 'ANNULATION'} onChange={() => setKind('ANNULATION')}/> Annulation (erreur d’enregistrement)</label>
      </fieldset>
      <label className="reversalReason">Motif (obligatoire)<textarea value={reason} maxLength={500} rows={3} onChange={e => setReason(e.target.value)} disabled={busy}/></label>
      <div className="es-modal-foot"><button className="es-btn es-btn-ghost" onClick={() => setTarget(null)}>Retour</button>
        <button className="es-btn es-btn-primary" disabled={busy} onClick={() => void submit()}>{busy ? 'Validation…' : 'Valider'}</button></div>
    </div></div>, document.body) : null;
  return [(id, label) => { setTarget({id, label}); setKind('REMBOURSEMENT'); setReason(''); setError(''); }, node];
}
