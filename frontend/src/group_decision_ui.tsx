// Décision groupée (owner, 2026-11-20): exempt every child of the staff from chosen fees in one pass — e.g. « les frais
// de l'État ». A preview lists the children and flags those who already have the decision; nothing is written before
// « Exonérer ». One decision per child and fee, visible and cancellable one by one in the register.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {groupDecision, listFeeTypes, type FeeType, type GroupDecisionResult} from './api';
import {friendlyError} from './platform/errors';

export function GroupExemption({token, onDone}: {token: string; onDone: () => Promise<void> | void}) {
  const [open, setOpen] = useState(false); const [fees, setFees] = useState<FeeType[]>([]); const [picked, setPicked] = useState<string[]>([]);
  const [percent, setPercent] = useState('100'); const [from, setFrom] = useState(''); const [reason, setReason] = useState('');
  const [plan, setPlan] = useState<GroupDecisionResult | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => { if (open && !fees.length) listFeeTypes(token).then(f => setFees(f.filter(x => x.enabled))).catch(e => setError(friendlyError(e))); }, [open, token]);
  useEffect(() => { setPlan(null); }, [picked.join(','), percent, from, reason]);
  const state = fees.filter(f => f.regulatory).map(f => f.code);
  const body = () => ({fee_codes: picked, value_type: 'PERCENT' as const, amount: percent.replace(',', '.'), effective_date: from || null, reason: reason.trim(),
    decision_type: Number(percent.replace(',', '.')) >= 100 ? 'EXEMPTION' : 'DISCOUNT'});
  async function preview() {
    if (!picked.length) { setError('Cochez au moins un frais.'); return; }
    if (!/^\d+([.,]\d{1,2})?$/.test(percent) || Number(percent.replace(',', '.')) <= 0 || Number(percent.replace(',', '.')) > 100) { setError('Pourcentage entre 1 et 100.'); return; }
    if (reason.trim().length < 3) { setError('Le motif est obligatoire.'); return; }
    try { setBusy(true); setError(''); setPlan(await groupDecision(token, {...body(), execute: false})); } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  async function execute() {
    try { setBusy(true); setError(''); const r = await groupDecision(token, {...body(), execute: true}); toast.success(`${r.created} décision(s) enregistrée(s) et appliquée(s)`); setPlan(null); setOpen(false); await onDone(); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  if (!open) return <button type="button" className="softBtn" onClick={() => setOpen(true)}>Exonérer les enfants du personnel</button>;
  const fresh = plan?.items.filter(i => i.status === 'NEW') ?? [];
  return <section className="benefitCard decisionForm" aria-label="Exonérer les enfants du personnel">
    {error && <div className="error" role="alert">{error}</div>}
    <fieldset disabled={busy}><legend>Exonérer tous les enfants du personnel</legend>
      <div className="feeChecks" role="group" aria-label="Frais concernés"><span>Frais concernés {state.length > 0 && <button type="button" className="textBtn" onClick={() => setPicked(state)}>Tous les frais de l’État</button>}</span>
        <div className="feeCheckGrid">{fees.map(f => <label key={f.code} className="checkField"><input type="checkbox" checked={picked.includes(f.code)} onChange={e => setPicked(p => e.target.checked ? [...p, f.code] : p.filter(x => x !== f.code))}/> {f.label}{f.regulatory ? ' (État)' : ''}</label>)}</div></div>
      <div className="benefitGrid">
        <label>Pourcentage<input inputMode="decimal" value={percent} onChange={e => setPercent(e.target.value)}/></label>
        <label>À partir du <small>(vide = depuis la rentrée)</small><input type="date" value={from} onChange={e => setFrom(e.target.value)}/></label>
        <label>Motif *<input value={reason} maxLength={500} onChange={e => setReason(e.target.value)} placeholder="Enfants du personnel — décision de la direction"/></label>
      </div>
      {plan && <div className="groupPlan"><p><b>{plan.children} enfant(s) du personnel</b> · à partir du {plan.effective_date.split('-').reverse().join('/')} · {fresh.length} décision(s) à créer{plan.items.length - fresh.length ? `, ${plan.items.length - fresh.length} déjà en place (ignorées)` : ''}.</p>
        <ul className="dayDetails">{plan.items.map(i => <li key={i.enrollment_id + i.fee_code}><span>{i.student} · {i.class_label} — {i.fee_label}</span><b>{i.status === 'NEW' ? 'à créer' : 'déjà en place'}</b></li>)}</ul></div>}
      <div className="formActions"><button type="button" className="ghost" onClick={() => { setOpen(false); setPlan(null); }}>Annuler</button>
        {!plan ? <button type="button" className="primaryBtn" onClick={() => void preview()}>Vérifier la liste</button>
          : <button type="button" className="primaryBtn" disabled={!fresh.length} onClick={() => void execute()}>{fresh.length ? `Enregistrer ${fresh.length} décision(s)` : 'Rien à créer'}</button>}</div>
    </fieldset>
  </section>;
}
