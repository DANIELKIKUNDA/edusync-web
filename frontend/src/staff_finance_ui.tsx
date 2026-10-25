import {explainHttpError} from './platform/errors';
// N3-F — staff children finance copied from the Desktop golden master (app/db/staff_finance.py): finance mode, open
// charges, payroll deduction confirmed as a NON-CASH settlement (no payment, no receipt, no cash operation), cancellation
// with a reason. Superior authority: GESTIONNAIRE (owner decision 2026-10-15).
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {friendlyError} from './platform/errors';
import {promptText} from './platform/dialogs';
import {formatMoney} from './platform/format';

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';  // same base as api.ts
const auth = (token: string) => ({'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'});
// Server refusals go through the shared explainer (translated, remembered by friendlyError) — 2026-10-25.
async function detail(r: Response, fallback: string) { let body: unknown = null; try { body = await r.json(); } catch { /* non JSON */ } return r.status ? explainHttpError(r.status, body) : fallback; }
async function get<T>(token: string, path: string, fallback: string): Promise<T> { const r = await fetch(`${API}${path}`, {headers: auth(token)}); if (!r.ok) throw new Error(await detail(r, fallback)); return r.json(); }
async function send<T>(token: string, method: string, path: string, body: unknown, fallback: string): Promise<T> {
  const r = await fetch(`${API}${path}`, {method, headers: {...auth(token), 'Idempotency-Key': crypto.randomUUID()}, body: JSON.stringify(body)});
  if (!r.ok) throw new Error(await detail(r, fallback)); return r.json();
}
type Child = {link_id: string; student_id: string; matricule?: string; last_name: string; middle_name?: string; first_name?: string; finance_mode: 'PAYROLL_DEDUCTION' | 'SCHOOL_PAYMENT';
  enrollment_id: string | null; in_order: boolean; totals: Record<string, {expected: string; settled: string; payroll_deducted: string; balance: string}>;
  settlements: {id: string; amount: string; currency: string; period_label?: string | null; reference?: string | null; charge_label: string; cancelled: boolean}[]};
type OpenCharge = {charge_id: string; label: string; currency: string; balance: string};
const money = (v: string | number, c: string) => formatMoney(String(v), c);

export function StaffChildrenFinance({token, staffId, can}: {token: string; staffId: string; can: (p: string) => boolean}) {
  const [items, setItems] = useState<Child[] | null>(null); const [error, setError] = useState(''); const [open, setOpen] = useState<Child | null>(null);
  async function load() { try { setItems((await get<{items: Child[]}>(token, `/personnel/${staffId}/children/finance`, 'Enfants indisponibles')).items); setError(''); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token, staffId]);
  async function setMode(c: Child, mode: 'PAYROLL' | 'FAMILY') {
    try { await send(token, 'PUT', `/personnel/children/${c.link_id}/finance-mode`, {responsibility_mode: mode}, 'Mode refusé'); toast.success(mode === 'PAYROLL' ? 'Retenue à la source activée' : 'Paiement par la famille'); await load(); }
    catch (e) { setError(friendlyError(e)); }
  }
  async function cancel(id: string) {
    const reason = await promptText({title: 'Annuler cette retenue', label: 'Motif d’annulation (obligatoire)', required: true, minLength: 3, confirmLabel: 'Annuler la retenue'});
    if (!reason) return;
    try { await send(token, 'POST', `/personnel/payroll-deductions/${id}/cancel`, {reason}, 'Annulation refusée'); toast.success('Retenue annulée ; le frais redevient dû'); await load(); }
    catch (e) { setError(friendlyError(e)); }
  }
  if (!items) return error ? <div className="error" role="alert">{error}</div> : null;
  if (!items.length) return <div className="personEmpty"><b>Aucun enfant lié</b><small>Le lien doit rester explicite ; il n’est jamais déduit d’un nom de responsable.</small></div>;
  return <div className="staffChildren">
    {error && <div className="error" role="alert">{error}</div>}
    {items.map(c => <article key={c.link_id} className="staffChild">
      <div className="staffChildHead"><div><b>{[c.last_name, c.middle_name, c.first_name].filter(Boolean).join(' ')}</b><small>{c.matricule} · {c.finance_mode === 'PAYROLL_DEDUCTION' ? 'Retenue à la source' : 'Paiement à l’école'} · {c.in_order ? 'En ordre' : 'Reste dû'}</small></div>
        {can('personnel.staff_children.finance_mode') && <button className="ghost" onClick={() => void setMode(c, c.finance_mode === 'PAYROLL_DEDUCTION' ? 'FAMILY' : 'PAYROLL')}>{c.finance_mode === 'PAYROLL_DEDUCTION' ? 'Passer au paiement famille' : 'Activer la retenue à la source'}</button>}</div>
      {Object.entries(c.totals).map(([cur, t]) => <small key={cur}>{cur} : attendu {money(t.expected, cur)} · réglé {money(t.settled, cur)} (dont retenu {money(t.payroll_deducted, cur)}) · reste {money(t.balance, cur)}</small>)}
      {c.settlements.length > 0 && <ul className="dayDetails">{c.settlements.map(s => <li key={s.id}><span>{s.charge_label}{s.period_label ? ` · paie ${s.period_label}` : ''}{s.reference ? ` · ${s.reference}` : ''}{s.cancelled ? ' · annulée' : ''}</span><b>{money(s.amount, s.currency)}</b>
        {!s.cancelled && can('personnel.payroll_deduction.cancel') && <button className="ghost" onClick={() => void cancel(s.id)}>Annuler</button>}</li>)}</ul>}
      {c.finance_mode === 'PAYROLL_DEDUCTION' && c.enrollment_id && !c.in_order && can('personnel.payroll_deduction.confirm') && <button className="primaryBtn compact" onClick={() => setOpen(c)}>Confirmer une retenue</button>}
      {open?.link_id === c.link_id && <DeductionForm token={token} staffId={staffId} child={c} onClose={() => setOpen(null)} onDone={async () => { setOpen(null); await load(); }}/>}
    </article>)}
  </div>;
}

function DeductionForm({token, staffId, child, onClose, onDone}: {token: string; staffId: string; child: Child; onClose: () => void; onDone: () => Promise<void>}) {
  const [rows, setRows] = useState<OpenCharge[]>([]); const [chosen, setChosen] = useState<Record<string, string>>({}); const [reference, setReference] = useState(''); const [period, setPeriod] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => { get<{items: OpenCharge[]}>(token, `/personnel/${staffId}/children/${child.student_id}/open-charges`, 'Frais indisponibles').then(x => setRows(x.items)).catch(e => setError(friendlyError(e))); }, [token, staffId, child.student_id]);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const allocations = Object.entries(chosen).filter(([, v]) => Number(v.replace(',', '.')) > 0).map(([charge_id, v]) => ({charge_id, amount: v.replace(',', '.')}));
    try { setBusy(true); setError(''); await send(token, 'POST', `/personnel/${staffId}/children/${child.student_id}/payroll-deductions`, {allocations: allocations.length ? allocations : null, reference: reference.trim() || null, period_label: period.trim() || null}, 'Retenue refusée');
      toast.success('Retenue confirmée (règlement hors caisse, sans reçu)'); await onDone(); }
    catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <form className="benefitCard" onSubmit={submit} noValidate>
    {error && <div className="error" role="alert">{error}</div>}
    <fieldset disabled={busy}><legend>Retenue sur salaire confirmée</legend>
      <p className="policyHint">Sans ligne cochée, tous les frais encore dus sont réglés. Aucune entrée de caisse ni reçu n’est créé.</p>
      <ul className="dayDetails">{rows.map(r => <li key={r.charge_id}><label className="checkField"><input type="checkbox" checked={r.charge_id in chosen} onChange={e => setChosen(c => { const n = {...c}; if (e.target.checked) n[r.charge_id] = String(Number(r.balance)); else delete n[r.charge_id]; return n; })}/> {r.label}</label>
        <span>{r.charge_id in chosen ? <input aria-label={`Montant retenu pour ${r.label}`} inputMode="decimal" value={chosen[r.charge_id]} onChange={e => setChosen(c => ({...c, [r.charge_id]: e.target.value}))}/> : money(r.balance, r.currency)}</span></li>)}</ul>
      <div className="benefitGrid">
        <label>Mois de paie (facultatif)<input value={period} maxLength={80} onChange={e => setPeriod(e.target.value)}/></label>
        <label>Référence de la paie (facultatif)<input value={reference} maxLength={120} onChange={e => setReference(e.target.value)}/></label>
      </div>
      <div className="formActions"><button type="button" className="ghost" onClick={onClose}>Annuler</button><button className="primaryBtn">{busy ? 'Validation…' : 'Confirmer la retenue'}</button></div>
    </fieldset>
  </form>;
}
